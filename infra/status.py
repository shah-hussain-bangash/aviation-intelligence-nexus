"""Sanitized display of a local restore receipt, not continuous recovery assurance."""
import json
from pathlib import Path


def restore_status(state):
    try:
        file=Path(state)/'recovery-receipt.json'
        if file.stat().st_size>16000:raise ValueError('Oversized receipt')
        receipt=json.loads(file.read_text(encoding='utf-8'))
        flags=('checksums_verified','database_integrity_verified','row_counts_preserved','sessions_revoked')
        if receipt.get('format')!='ain-restore-receipt-v1' or not all(receipt.get(flag) is True for flag in flags):raise ValueError('Unverified receipt')
        if not isinstance(receipt.get('flight_records'),int) or isinstance(receipt['flight_records'],bool) or receipt['flight_records']<0:raise ValueError('Invalid receipt count')
        return {'recorded':True,**{key:receipt.get(key) for key in ('snapshot_id','restored_at','schema_version','flight_records','active_model_restored','knowledge_index_restored','elapsed_ms')},
            **{flag:True for flag in flags},'production_qualified':False}
    except (OSError,ValueError,TypeError,KeyError):
        return {'recorded':False,'message':'No verified local restore receipt for this instance.','production_qualified':False}
