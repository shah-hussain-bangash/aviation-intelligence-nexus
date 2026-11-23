"""Opt-in local BTS-schema preflight; snapshot inputs, never access the primary database."""
import argparse
from contextlib import closing
import csv
from datetime import date, datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import stat
import struct
import time
import zipfile
import zlib
from uuid import uuid4
from pipelines.import_bts import REQUIRED, normalize, source_url
from services.api.paths import ROOT
from infra.recovery import private_target

MAX_ARCHIVE = 512 * 1024 * 1024
MAX_CSV = 2_000_000_000
MAX_ROWS = 5_000_000
SECONDS = 120


class Rejected(ValueError):
    def __init__(self, code):self.code = code


def digest(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream, 'sha256').hexdigest()


def zip_metadata(path):
    # Bound central-directory parsing before ZipFile allocates its member objects.
    with Path(path).open('rb') as stream:
        stream.seek(0, 2);size = stream.tell()
        stream.seek(max(0, size - 65557));tail = stream.read(65557)
    position = tail.rfind(b'PK\x05\x06')
    if position < 0 or len(tail) - position < 22:raise Rejected('invalid_zip')
    _, disk, start_disk, disk_count, total, directory_size, offset, comment = struct.unpack('<4s4H2LH', tail[position:position+22])
    if len(tail) - position != 22 + comment or disk or start_disk or disk_count != total or not 1 <= total <= 16 or directory_size > 65536 or offset + directory_size > size:
        raise Rejected('unsupported_zip_metadata')


class LimitedLines:
    def __init__(self, text):self.text = text
    def __iter__(self):return self
    def __next__(self):
        line = self.text.readline(1024 * 1024 + 1)
        if not line:raise StopIteration
        if len(line) > 1024 * 1024:raise Rejected('csv_line_limit')
        return line


def scan(path, scratch, period, stats, deadline, clock):
    zip_metadata(path)
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if not 1 <= len(entries) <= 16:raise Rejected('unsupported_zip_metadata')
        csv_entries = [entry for entry in entries if entry.filename.lower().endswith('.csv')]
        if len(csv_entries) != 1:raise Rejected('csv_member_count')
        for entry in entries:
            name = entry.filename
            if any(char in name for char in ('/', '\\', ':')) or name in ('.', '..') or len(name) > 512 or entry.is_dir() or stat.S_ISLNK(entry.external_attr >> 16):raise Rejected('unsafe_zip_member')
            if entry.flag_bits & 1:raise Rejected('encrypted_zip')
            if entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):raise Rejected('unsupported_compression')
            if entry is not csv_entries[0] and (name.lower() not in ('readme.html', 'readme.txt') or entry.file_size > 1024 * 1024):raise Rejected('unsupported_zip_member')
        member = csv_entries[0]
        if member.file_size > MAX_CSV:raise Rejected('csv_size_limit')
        with closing(sqlite3.connect(scratch)) as db, db:
            stats['scratch_database_used'] = True
            # Disposable disk-backed keys only; these settings never affect the application DB.
            db.execute('PRAGMA journal_mode=OFF');db.execute('PRAGMA synchronous=OFF');db.execute('PRAGMA cache_size=-8192')
            db.execute('CREATE TABLE seen(identity TEXT PRIMARY KEY, value_digest TEXT NOT NULL)')
            with archive.open(member) as raw, io.TextIOWrapper(raw, encoding='utf-8-sig', newline='') as text:
                reader = csv.DictReader(LimitedLines(text), strict=True)
                fields = reader.fieldnames or []
                nonblank = [field for field in fields if field]
                if len(fields) > 200 or len(nonblank) != len(set(nonblank)) or not REQUIRED.issubset(fields) or ('' in fields and (fields.count('') != 1 or fields[-1] != '')):
                    raise Rejected('schema_invalid')
                stats['csv_columns'] = len(fields)
                for index, row in enumerate(reader, 1):
                    stats['rows_read'] = index
                    if clock() >= deadline:raise Rejected('time_budget')
                    if index > MAX_ROWS:raise Rejected('row_limit')
                    if None in row or any(row.get(field) is None for field in nonblank) or row.get('', '') not in ('', None):raise Rejected('record_shape')
                    try:values = normalize(row, period)
                    except (ValueError, TypeError, AttributeError, OverflowError):raise Rejected('invalid_record') from None
                    identity = values[1]
                    # Match numeric equality in the importer: -0.0 and 0.0 are the same value.
                    canonical = [0.0 if isinstance(value, float) and value == 0 else value for value in values]
                    value_hash = hashlib.sha256(json.dumps(canonical, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
                    prior = db.execute('SELECT value_digest FROM seen WHERE identity=?', (identity,)).fetchone()
                    if prior:
                        if prior[0] != value_hash:raise Rejected('conflicting_identity')
                        stats['identical_duplicates'] += 1
                    else:
                        db.execute('INSERT INTO seen VALUES (?,?)', (identity, value_hash));stats['unique_identities'] += 1
                if not stats['rows_read']:raise Rejected('empty_csv')
                stats['scan_complete'] = True
                stats['csv_crc_verified'] = True


def intake(archive, root, year, month, clock=time.monotonic):
    date(year, month, 1)
    archive, root = Path(archive), Path(root).resolve()
    if archive.is_symlink() or not archive.is_file():raise ValueError('Choose an ordinary source archive')
    # Operational errors are not classified as bad data. A complete owned snapshot is required.
    if archive.stat().st_size > MAX_ARCHIVE:raise ValueError('Source exceeds the 512 MiB archive limit')
    run_id = uuid4().hex
    stage = root / 'staging' / run_id
    stage.mkdir(parents=True, exist_ok=False)
    snapshot, scratch = stage / 'archive.zip', stage / 'keys.sqlite3'
    started = clock();deadline = started + SECONDS
    copied = 0
    with archive.open('rb') as incoming, snapshot.open('xb') as output:
        while block := incoming.read(1024 * 1024):
            copied += len(block)
            if copied > MAX_ARCHIVE:raise ValueError('Source grew beyond the archive limit')
            if clock() >= deadline:raise TimeoutError('Snapshot copy exceeded the time budget')
            output.write(block)
    archive_hash = digest(snapshot)
    stats = {'rows_read': 0, 'unique_identities': 0, 'identical_duplicates': 0,
             'csv_columns': None, 'scan_complete': False, 'csv_crc_verified': False, 'scratch_database_used': False}
    reason = None
    try:
        scan(snapshot, scratch, f'{year:04d}-{month:02d}', stats, deadline, clock)
    except Rejected as error:reason = error.code
    except (zipfile.BadZipFile, EOFError, zlib.error):reason = 'corrupt_zip'
    except (UnicodeError, csv.Error):reason = 'invalid_csv_encoding_or_syntax'
    finally:
        if scratch.exists():
            assert scratch.resolve().is_relative_to(stage.resolve())
            scratch.unlink()
    if digest(snapshot) != archive_hash:raise ValueError('Owned snapshot changed during validation')
    disposition = 'quarantined' if reason else 'accepted'
    destination = root / disposition / run_id
    assert destination.resolve().is_relative_to(root) and stage.resolve().is_relative_to(root)
    destination.mkdir(parents=True, exist_ok=False)
    # Exclusive local publication; no source is moved, replaced or extracted.
    import os
    os.link(snapshot, destination / 'archive.zip')
    if digest(destination / 'archive.zip') != archive_hash:raise ValueError('Published snapshot identity differs')
    receipt = {'format': 'ain-bts-intake-v1', 'policy_version': 'bts-intake-v1', 'run_id': run_id,
        'checked_at': datetime.now(timezone.utc).isoformat(), 'disposition': disposition,
        'declared_period': f'{year:04d}-{month:02d}', 'declared_source_url': source_url(year, month),
        'origin_verified': False, 'archive_sha256': archive_hash, 'archive_size_bytes': copied,
        **stats, 'reason_code': reason, 'primary_database_accessed': False,
        'import_performed': False, 'training_performed': False, 'raw_snapshot_retained': True,
        'limits': {'archive_bytes': MAX_ARCHIVE, 'csv_bytes': MAX_CSV, 'rows': MAX_ROWS, 'seconds': SECONDS},
        'elapsed_seconds': round(clock() - started, 3), 'production_ready': False,
        'scope': 'Selected-field local structural preflight; not source authorization, business accuracy or operational acceptance.'}
    with (destination / 'receipt.json').open('x', encoding='utf-8') as stream:json.dump(receipt, stream, indent=2)
    snapshot.unlink()  # Only this run's owned staging link; retained snapshot remains intact.
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--year', type=int, required=True);parser.add_argument('--month', type=int, required=True)
    parser.add_argument('--directory', type=Path, default=ROOT / '.local/intake')
    args = parser.parse_args()
    result = intake(args.archive, private_target(args.directory), args.year, args.month)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['disposition'] == 'accepted' else 2)


if __name__ == '__main__':main()
