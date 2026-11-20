"""Authenticated streaming backups with a Windows user-protected local key.

No key bytes are accepted on command lines or printed. This is local recovery,
not an independently recoverable off-site backup or a key escrow service.
"""
import argparse
import ctypes
import json
import os
from pathlib import Path
import tarfile
import tempfile
from uuid import uuid4
from cryptography.cobblestone import Cobblestone128Encryptor, Cobblestone128Decryptor
from cryptography.exceptions import InvalidTag
from infra.recovery import FILES, safe_file, verify, restore, private_target, checksum
from services.api.paths import ROOT

MAGIC = b'AINSEAL1\n'
CONTEXT = b'AIN trusted recovery snapshot v1'
CHUNK = 1024 * 1024
MAX_BYTES = 8 * 1024 ** 3


def protect_key(data, decrypt=False):
    if os.name != 'nt':
        raise RuntimeError('The local key provider requires Windows DPAPI')
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]

    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source = Blob(len(data), buffer)
    result = Blob()
    library = ctypes.WinDLL('crypt32', use_last_error=True)
    function = library.CryptUnprotectData if decrypt else library.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob),
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    # UI_FORBIDDEN only: never enable the machine-wide decryption flag.
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result)):
        raise RuntimeError('Windows could not access the user-protected recovery key')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    try:
        return ctypes.string_at(result.data, result.size)
    finally:
        kernel.LocalFree(result.data)


def key_path(value):
    path = Path(value).resolve()
    if path.is_relative_to(ROOT):
        raise ValueError('Recovery keys must stay outside the project checkout')
    return path


def create_key(path):
    path = key_path(path)
    protected = protect_key(Cobblestone128Encryptor.generate_key())
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(protected)
    return {'key_created': True, 'provider': 'Windows DPAPI CurrentUser', 'key_exported': False}


def load_key(path):
    path = key_path(path)
    if path.is_symlink() or path.stat().st_size > 16384:
        raise ValueError('Invalid protected key file')
    key = protect_key(path.read_bytes(), decrypt=True)
    if len(key) != 16:
        raise ValueError('Invalid recovery key length')
    return key


class EncryptWriter:
    def __init__(self, output, encryptor):
        self.output, self.encryptor = output, encryptor

    def write(self, value):
        self.output.write(self.encryptor.update(value))
        return len(value)


def seal(source, destination, key):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    manifest = verify(source)
    if (source / 'manifest.json').is_symlink():
        raise ValueError('Manifest must be an ordinary snapshot file')
    if destination.exists():
        raise FileExistsError('Encrypted backup already exists')
    if sum(entry['size_bytes'] for entry in manifest['files']) > MAX_BYTES:
        raise ValueError('Snapshot exceeds the supported eight GiB local envelope')
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name('.' + destination.name + '.partial-' + str(uuid4()))
    created = False
    try:
        with temporary.open('xb') as output:
            created = True
            os.chmod(temporary, 0o600)
            output.write(MAGIC)
            encryptor = Cobblestone128Encryptor(key, context=CONTEXT)
            with tarfile.open(fileobj=EncryptWriter(output, encryptor), mode='w|gz') as archive:
                for name in ['manifest.json', *[entry['path'] for entry in manifest['files']]]:
                    file = source / name if name == 'manifest.json' else safe_file(source, name)
                    info = tarfile.TarInfo(name)
                    info.size = file.stat().st_size
                    info.mode = 0o600
                    with file.open('rb') as stream:
                        archive.addfile(info, stream)
            output.write(encryptor.finalize())
            output.flush()
            os.fsync(output.fileno())
        # Exclusive publication: hard-link creation cannot replace another backup.
        os.link(temporary, destination)
    finally:
        if created and temporary.exists():
            temporary.unlink()
    return {'format': 'ain-sealed-v1', 'snapshot_id': manifest['snapshot_id'],
            'encrypted': True, 'authenticated_encryption': 'Cobblestone-128',
            'size_bytes': destination.stat().st_size, 'sha256': checksum(destination),
            'production_qualified': False}


def restore_sealed(source, destination, key):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination.exists():
        raise FileExistsError('Restore target already exists')
    if source.stat().st_size > MAX_BYTES or source.stat().st_size < len(MAGIC):
        raise ValueError('Unsupported encrypted backup size')
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Only newly created scratch files under the intended restore parent are cleaned.
    with tempfile.TemporaryDirectory(prefix='.ain-unseal-', dir=destination.parent) as scratch:
        scratch = Path(scratch).resolve()
        if not scratch.is_relative_to(destination.parent):
            raise ValueError('Invalid private staging directory')
        with tempfile.TemporaryFile(dir=scratch) as compressed, source.open('rb') as encrypted:
            if encrypted.read(len(MAGIC)) != MAGIC:
                raise ValueError('Unsupported encrypted backup format')
            decryptor = Cobblestone128Decryptor(key, context=CONTEXT)
            try:
                while block := encrypted.read(CHUNK):
                    compressed.write(decryptor.update(block))
                compressed.write(decryptor.finalize())
            except InvalidTag:
                raise ValueError('Encrypted backup authentication failed') from None
            # No archive parsing, extraction or target writes before full authentication.
            compressed.seek(0)
            unpacked = scratch / 'snapshot'
            unpacked.mkdir()
            seen = set()
            total = 0
            with tarfile.open(fileobj=compressed, mode='r|gz') as archive:
                for member in archive:
                    if member.name not in (*FILES, 'manifest.json') or member.name in seen or not member.isfile():
                        raise ValueError('Encrypted archive contains an unapproved entry')
                    total += member.size
                    if member.size < 0 or total > MAX_BYTES or member.name == 'manifest.json' and member.size > 64000:
                        raise ValueError('Encrypted archive exceeds extraction limits')
                    seen.add(member.name)
                    target = unpacked / member.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.extractfile(member) as incoming, target.open('xb') as output:
                        while block := incoming.read(CHUNK):
                            output.write(block)
            verify(unpacked)
            receipt = restore(unpacked, destination)
    receipt['encrypted_source_authenticated'] = True
    receipt['encryption'] = 'Cobblestone-128'
    (destination / 'recovery-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['keygen', 'seal', 'restore'])
    parser.add_argument('--key-file', required=True)
    parser.add_argument('--source')
    parser.add_argument('--destination')
    args = parser.parse_args()
    try:
        if args.action == 'keygen':
            result = create_key(args.key_file)
        else:
            if not args.source or not args.destination:
                raise ValueError('Source and a new destination are required')
            destination = private_target(args.destination)
            operation = seal if args.action == 'seal' else restore_sealed
            result = operation(args.source, destination, load_key(args.key_file))
        print(json.dumps(result, indent=2))
    except (OSError, ValueError, RuntimeError, tarfile.TarError):
        parser.exit(1, 'Recovery action failed. Check the trusted source, Windows key owner, available space and new destination. No recovery secret is logged.\n')


if __name__ == '__main__':
    main()
