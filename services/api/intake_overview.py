"""Bounded, unsigned historical intake metadata; never opens archives or databases."""
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re

FORMAT = 'ain-intake-overview-v1'
MAX_BYTES = 256_000


def require(value):
    if not value: raise ValueError('Intake overview unavailable')


def digest(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()


def validate(payload):
    require(isinstance(payload, dict) and set(payload) == {'format','checked_at','runs_checked','accepted_runs','quarantined_runs','unverifiable_runs','unique_archives','repeated_accepted_runs','declared_rows','archives','quarantine_reasons','receipt_authenticated','rows_rescanned','import_authorized','import_performed','production_ready'})
    require(payload['format'] == FORMAT)
    require(isinstance(payload['checked_at'], str) and datetime.fromisoformat(payload['checked_at']).utcoffset() is not None)
    for key in ('runs_checked','accepted_runs','quarantined_runs','unverifiable_runs','unique_archives','repeated_accepted_runs','declared_rows'):
        require(type(payload[key]) is int and payload[key] >= 0)
    require(payload['runs_checked'] <= 1000 and payload['runs_checked'] == sum(payload[k] for k in ('accepted_runs','quarantined_runs','unverifiable_runs')))
    for key in ('receipt_authenticated','rows_rescanned','import_authorized','import_performed','production_ready'): require(payload[key] is False)
    rows = payload['archives']; require(isinstance(rows, list) and len(rows) <= 100)
    require(payload['unique_archives'] == len(rows) and payload['repeated_accepted_runs'] == payload['accepted_runs'] - len(rows))
    hashes = set(); total = repeats = 0
    for row in rows:
        require(isinstance(row, dict) and set(row) == {'period','sha256','bytes','declared_rows','runs'})
        require(isinstance(row['period'], str) and re.fullmatch(r'[0-9]{4}-(0[1-9]|1[0-2])', row['period']))
        require(isinstance(row['sha256'], str) and re.fullmatch('[0-9a-f]{64}', row['sha256']) and row['sha256'] not in hashes)
        hashes.add(row['sha256'])
        for key, maximum in (('bytes',512*1024*1024),('declared_rows',5_000_000),('runs',1000)):
            require(type(row[key]) is int and 0 < row[key] <= maximum)
        total += row['declared_rows']; repeats += row['runs']
    require(total == payload['declared_rows'] and repeats == payload['accepted_runs'])
    reasons = payload['quarantine_reasons']; require(isinstance(reasons, dict) and len(reasons) <= 30)
    # Reason codes are fixed in the producer; the consumer accepts only bounded identifiers.
    for key, value in reasons.items():
        require(isinstance(key,str) and re.fullmatch('[a-z_]{1,40}',key) and type(value) is int and 0 < value <= 1000)
    require(sum(reasons.values()) == payload['quarantined_runs'])
    return payload


def load_overview(state):
    path = (Path('/intake-status') if os.environ.get('AIN_INTAKE_OVERVIEW_MOUNTED') == '1' else Path(state)/'intake-dashboard')/'snapshot.json'
    require(not path.is_symlink() and path.is_file() and path.stat().st_size <= MAX_BYTES)
    with path.open('rb') as stream: raw = stream.read(MAX_BYTES+1)
    require(len(raw) <= MAX_BYTES)
    envelope = json.loads(raw)
    require(isinstance(envelope,dict) and set(envelope) == {'payload','payload_sha256'})
    payload = validate(envelope['payload'])
    require(envelope['payload_sha256'] == digest(payload))
    return payload
