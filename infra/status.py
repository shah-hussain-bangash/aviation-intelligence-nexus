"""Sanitized display of a local restore receipt, not continuous recovery assurance."""
import json
from datetime import datetime
from pathlib import Path
import re
import os
from infra.rollback_evidence import validate_receipt, binding
from services.api.paths import ROOT, SCHEMA_VERSION
from infra.recovery_state import RestoreIncompleteError, restore_incomplete


def restore_status(state):
    try:
        if restore_incomplete(state):raise ValueError('Restore is incomplete')
        file=Path(state)/'recovery-receipt.json'
        if file.stat().st_size>16000:raise ValueError('Oversized receipt')
        receipt=json.loads(file.read_text(encoding='utf-8'))
        flags=('checksums_verified','database_integrity_verified','row_counts_preserved','sessions_revoked')
        if receipt.get('format')!='ain-restore-receipt-v1' or not all(receipt.get(flag) is True for flag in flags):raise ValueError('Unverified receipt')
        if not isinstance(receipt.get('flight_records'),int) or isinstance(receipt['flight_records'],bool) or receipt['flight_records']<0:raise ValueError('Invalid receipt count')
        return {'recorded':True,**{key:receipt.get(key) for key in ('snapshot_id','restored_at','schema_version','flight_records','active_model_restored','knowledge_index_restored','elapsed_ms')},
            **{flag:True for flag in flags},'production_qualified':False}
    except (OSError,ValueError,TypeError,KeyError,RestoreIncompleteError):
        return {'recorded':False,'message':'No verified local restore receipt for this instance.','production_qualified':False}


def encrypted_drill_status(state):
    try:
        file = Path(state) / 'encrypted-recovery-drill.json'
        if file.stat().st_size > 16000:
            raise ValueError('Oversized drill receipt')
        receipt = json.loads(file.read_text(encoding='utf-8'))
        if receipt.get('format') != 'ain-encrypted-drill-v1' or receipt.get('ciphertext_authenticated') is not True or receipt.get('restored_database_verified') is not True:
            raise ValueError('Unverified encrypted drill')
        if receipt.get('encryption') != 'Cobblestone-128' or receipt.get('key_provider') != 'Windows DPAPI CurrentUser' or receipt.get('independent_recovery_qualified') is not False:
            raise ValueError('Unsupported recovery qualification')
        count = receipt['flight_records']
        if type(count) is not int or count < 0:
            raise ValueError('Invalid drill count')
        datetime.fromisoformat(receipt['checked_at'])
        return {'recorded': True, 'checked_at': receipt['checked_at'], 'flight_records': count,
                'encryption': 'Cobblestone-128', 'key_provider': 'Windows DPAPI CurrentUser',
                'independent_recovery_qualified': False, 'production_qualified': False}
    except (OSError, ValueError, TypeError, KeyError):
        return {'recorded': False, 'production_qualified': False}


def rollback_drill_status(state, revision=None, schema_version=SCHEMA_VERSION, root=ROOT):
    try:
        file = Path(state) / 'rollback-drill.json'
        if file.stat().st_size > 16000:
            raise ValueError('Oversized rollback receipt')
        receipt = json.loads(file.read_text(encoding='utf-8'))
        validate_receipt(receipt)
        return {'recorded': True, **{key: receipt[key] for key in ('checked_at', 'candidate_revision', 'rollback_revision', 'flight_records')},
                'binding': binding(receipt, os.environ.get('AIN_RELEASE_REVISION', 'working-tree') if revision is None else revision, schema_version, root),
                'scope': 'Separate restored local volume; main deployment not rolled back', 'production_qualified': False}
    except (OSError, ValueError, TypeError, KeyError):
        return {'recorded': False, 'production_qualified': False}
