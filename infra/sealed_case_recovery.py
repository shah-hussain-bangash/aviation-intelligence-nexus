"""Opt-in authenticated encryption for paired local case backups; no off-host qualification."""
import argparse
import json
import os
from pathlib import Path
import tarfile
import tempfile
from uuid import uuid4
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher,algorithms,modes
from infra import case_recovery as paired,recovery
from infra.recovery_state import RESTORE_MARKER
from infra.sealed_recovery import load_key,EncryptWriter

MAGIC=b'AINCASE-AES128GCM-1\n'
CHUNK=1024*1024
MAX_BYTES=8*1024**3
ALLOWED=(paired.MANIFEST,paired.CASE_FILE,'application/manifest.json',*('application/'+name for name in recovery.FILES))


def require_key(key):
    paired.require(isinstance(key,bytes) and len(key)==16,'sixteen_byte_key_required')


def seal(source,destination,key,manifest_sha256,*,offline_acknowledged=False):
    paired.require(offline_acknowledged is True,'offline_acknowledgment_required');require_key(key)
    source=paired.local_path(source);destination=paired.target_path(source,destination)
    manifest=paired.verify(source,manifest_sha256);application=recovery.verify(source/'application')
    names=[paired.MANIFEST,paired.CASE_FILE,'application/manifest.json',*('application/'+r['path'] for r in application['files'])]
    files=[paired.file_at(source,name) for name in names]
    paired.require(sum(file.stat().st_size for file in files)<=MAX_BYTES,'snapshot_exceeds_local_bound')
    destination.parent.mkdir(parents=True,exist_ok=True)
    temporary=destination.with_name('.'+destination.name+'.partial-'+uuid4().hex)
    created=False
    try:
        with temporary.open('xb') as output:
            created=True;os.chmod(temporary,0o600)
            header=MAGIC+os.urandom(12);output.write(header)
            encryptor=Cipher(algorithms.AES(key),modes.GCM(header[-12:])).encryptor()
            encryptor.authenticate_additional_data(header)
            with tarfile.open(fileobj=EncryptWriter(output,encryptor),mode='w|gz') as archive:
                for name,file in zip(names,files):
                    info=tarfile.TarInfo(name);info.size=file.stat().st_size;info.mode=0o600
                    with file.open('rb') as incoming:archive.addfile(info,incoming)
            output.write(encryptor.finalize());output.write(encryptor.tag)
            output.flush();os.fsync(output.fileno())
        paired.verify(source,manifest_sha256)
        paired.require(temporary.stat().st_size<=MAX_BYTES,'ciphertext_exceeds_local_bound')
        os.link(temporary,destination) # Exclusive publication: never replace an existing file.
    finally:
        if created:temporary.unlink(missing_ok=True)
    return {'format':'ain-sealed-case-v1','snapshot_id':manifest['snapshot_id'],'manifest_sha256':manifest_sha256,
        'encrypted':True,'encryption':'AES-128-GCM','ciphertext_sha256':recovery.checksum(destination),
        'size_bytes':destination.stat().st_size,'plaintext_source_retained':True,'production_ready':False}


def _unpack_authenticated(source,scratch,key):
    size=source.stat().st_size;header_size=len(MAGIC)+12
    paired.require(header_size+16<size<=MAX_BYTES,'unsupported_ciphertext_size')
    # Decrypted compressed bytes remain scratch data until final tag verification succeeds.
    with tempfile.TemporaryFile(dir=scratch) as compressed,source.open('rb') as encrypted:
        header=encrypted.read(header_size);paired.require(header.startswith(MAGIC),'unsupported_ciphertext_format')
        encrypted.seek(-16,2);tag=encrypted.read(16);encrypted.seek(header_size)
        decryptor=Cipher(algorithms.AES(key),modes.GCM(header[-12:],tag)).decryptor()
        decryptor.authenticate_additional_data(header);remaining=size-header_size-16
        try:
            while remaining:
                block=encrypted.read(min(CHUNK,remaining));paired.require(bool(block),'truncated_ciphertext')
                remaining-=len(block);compressed.write(decryptor.update(block))
            compressed.write(decryptor.finalize())
        except InvalidTag:raise paired.CaseRecoveryError('ciphertext_authentication_failed') from None
        compressed.seek(0);unpacked=scratch/'snapshot';unpacked.mkdir();seen=set();total=0
        with tarfile.open(fileobj=compressed,mode='r|gz') as archive:
            for member in archive:
                paired.require(member.name in ALLOWED and member.name not in seen and member.isfile() and not member.pax_headers,'unapproved_archive_entry')
                seen.add(member.name);total+=member.size
                paired.require(0<=member.size and total<=MAX_BYTES,'archive_exceeds_local_bound')
                if member.name.endswith('.json') and member.name in (paired.MANIFEST,'application/manifest.json'):
                    paired.require(member.size<=64000,'manifest_exceeds_bound')
                target=unpacked/member.name;target.parent.mkdir(parents=True,exist_ok=True)
                with archive.extractfile(member) as incoming,target.open('xb') as output:
                    copied=0
                    while block:=incoming.read(CHUNK):copied+=len(block);output.write(block)
                    paired.require(copied==member.size,'archive_entry_truncated')
        return unpacked


def restore_sealed(source,destination,key,manifest_sha256,*,offline_acknowledged=False):
    paired.require(offline_acknowledged is True,'offline_acknowledgment_required');require_key(key)
    source=paired.local_path(source);paired.require(source.is_file(),'ciphertext_file_required')
    destination=paired.target_path(source,destination)
    paired.require(source.stat().st_size<=MAX_BYTES,'ciphertext_exceeds_local_bound')
    original=recovery.checksum(source);destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.ain-case-unseal-',dir=destination.parent) as folder:
        scratch=paired.local_path(folder);os.chmod(scratch,0o700)
        unpacked=_unpack_authenticated(source,scratch,key)
        paired.verify(unpacked,manifest_sha256)
        paired.require(recovery.checksum(source)==original,'ciphertext_changed_during_read')
        receipt=paired.restore(unpacked,destination,manifest_sha256,offline_acknowledged=True)
        result={'format':'ain-encrypted-case-restore-v1','snapshot_id':receipt['snapshot_id'],'manifest_sha256':manifest_sha256,
            'encrypted_source_authenticated':True,'encryption':'AES-128-GCM','ciphertext_sha256':original,
            'cases':receipt['cases'],'case_contents_preserved':True,'restored_sessions_revoked':receipt['restored_sessions_revoked'],
            'restored_workspace_encrypted':False,'independent_recovery_qualified':False,'production_ready':False}
        try:paired.write_new(destination/'case-encrypted-restore.json',result)
        except Exception:
            paired.write_new(destination/RESTORE_MARKER,{'format':'ain-encrypted-case-receipt-incomplete-v1'})
            raise
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('seal','restore'));parser.add_argument('--source',required=True)
    parser.add_argument('--destination',required=True);parser.add_argument('--key-file',required=True)
    parser.add_argument('--manifest-sha256',required=True);parser.add_argument('--offline-acknowledged',action='store_true')
    args=parser.parse_args()
    try:
        destination=recovery.private_target(paired.local_path(args.destination))
        operation=seal if args.action=='seal' else restore_sealed
        result=operation(args.source,destination,load_key(paired.local_path(args.key_file)),args.manifest_sha256,offline_acknowledged=args.offline_acknowledged)
        print(json.dumps(result,indent=2))
    except Exception:
        print(json.dumps({'passed':False,'error':'encrypted_case_recovery_unverified','production_ready':False}));raise SystemExit(2) from None


if __name__=='__main__':main()
