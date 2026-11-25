"""Owner-invoked recovery parity for a pinned, trusted historical model copy."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from uuid import UUID, uuid4

from infra.rehearsal_admission import require
from infra.recovery import checksum, FILES
from services.api.paths import ROOT
from infra.verify_schema8 import source_identity

MODEL = 'models/delay-v2/model.joblib'
REPORT = 'models/delay-v2/report.json'
SCENARIOS = tuple({'carrier': 'AA', 'origin': 'JFK', 'destination': 'LAX',
                   'flight_date': day, 'scheduled_departure': '09:00'}
                  for day in ('2025-01-15', '2025-04-15', '2025-05-15'))


def ordinary(path, limit):
    path = Path(path).absolute()
    require(not str(path).startswith(('\\\\', '//')), 'local_snapshot_required')
    require(not any(p.is_symlink() or getattr(p, 'is_junction', lambda: False)()
                    for p in (path, *path.parents)), 'unredirected_snapshot_required')
    require(path.is_file() and 0 < path.stat().st_size <= limit, 'bounded_ordinary_file_required')
    return path


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate_json_key')
        result[key] = value
    return result


def admit(snapshot, manifest_sha256, *, trusted_local_model=False):
    # Joblib is executable serialization. Only an explicit OS-owner CLI decision
    # admits it; a self-reported digest or research gate alone is not a trust source.
    require(trusted_local_model is True, 'explicit_trusted_local_model_required')
    require(isinstance(manifest_sha256, str) and re.fullmatch('[0-9a-f]{64}', manifest_sha256), 'full_manifest_pin_required')
    snapshot = Path(snapshot).absolute()
    manifest = ordinary(snapshot / 'manifest.json', 64000)
    require(checksum(manifest) == manifest_sha256, 'manifest_pin_mismatch')
    record = json.loads(manifest.read_text(encoding='utf-8'), object_pairs_hook=unique_object)
    require(isinstance(record, dict) and record.get('format') == 'ain-recovery-v1', 'snapshot_format_invalid')
    require(isinstance(record.get('database'), dict) and type(record['database'].get('schema_version')) is int
            and record['database']['schema_version'] in (7, 8), 'recorded_snapshot_schema_invalid')
    require(isinstance(record.get('snapshot_id'), str), 'snapshot_id_invalid')
    UUID(record['snapshot_id'])
    entries = record.get('files')
    require(isinstance(entries, list) and 1 <= len(entries) <= len(FILES), 'snapshot_inventory_invalid')
    inventory = {}
    for entry in entries:
        require(isinstance(entry, dict), 'snapshot_entry_invalid')
        name = entry.get('path')
        require(isinstance(name, str) and name in FILES and name not in inventory, 'snapshot_inventory_invalid')
        require(type(entry.get('size_bytes')) is int and entry['size_bytes'] > 0
                and isinstance(entry.get('sha256'), str)
                and re.fullmatch('[0-9a-f]{64}', entry['sha256']), 'snapshot_entry_invalid')
        inventory[name] = entry
    require(MODEL in inventory and REPORT in inventory, 'model_pair_required')
    for name, limit in ((MODEL, 256 * 1024 * 1024), (REPORT, 1000000)):
        file = ordinary(snapshot / name, limit)
        require(file.stat().st_size == inventory[name]['size_bytes'] and checksum(file) == inventory[name]['sha256'], 'artifact_pin_mismatch')
    metadata = json.loads((snapshot / REPORT).read_text(), object_pairs_hook=unique_object)
    require(isinstance(metadata, dict) and metadata.get('artifact_sha256') == inventory[MODEL]['sha256']
            and metadata.get('model_version') == 'delay-v2'
            and isinstance(metadata.get('release_assessment'), dict)
            and metadata.get('release_assessment', {}).get('research_gate_passed') is True, 'research_model_gate_invalid')
    return record, inventory


def execute_case(case):
    """Called only in a fresh subprocess bound to this case's synthetic state."""
    from contextlib import closing
    import secrets
    import sqlite3
    from services.api.paths import STATE
    from services.api.main import initialize
    from services.api.auth import AuthStore
    from services.api.prediction import ResearchPredictor, Scenario
    from infra.recovery import backup, restore, database_facts
    from infra.verify_restore_evidence import verify_evidence

    case = Path(case).resolve()
    require(case.parent == (ROOT / '.local/research-model-recovery').resolve(), 'private_case_required')
    require(STATE == case / 'state' and os.environ.get('AIN_DB_PATH') == str(STATE / 'ain.sqlite3'), 'isolated_worker_state_required')
    plan = json.loads((case / 'plan.json').read_text())
    for name in (MODEL, REPORT):
        require(checksum(STATE / name) == plan['files'][name]['sha256'], 'copied_artifact_changed')
    initialize(STATE / 'ain.sqlite3')
    auth = AuthStore(STATE / 'ain.sqlite3')
    password = secrets.token_urlsafe(32)
    auth.create_user('synthetic-recovery-admin', password, 'admin')
    old_token = auth.login('synthetic-recovery-admin', password)
    with closing(sqlite3.connect(STATE / 'ain.sqlite3')) as db, db:
        db.execute("INSERT INTO flights(source,source_record_id,flight_date,carrier,origin,destination) VALUES('synthetic_model_recovery_fixture','1','2025-01-01','XX','AAA','BBB')")
    before_predictor = ResearchPredictor(STATE / 'models/delay-v2')
    before = [before_predictor.predict(Scenario.model_validate(row)) for row in SCENARIOS]
    manifest = backup(STATE, case / 'backup')
    receipt = restore(case / 'backup', case / 'restored')
    restored = case / 'restored'
    after_predictor = ResearchPredictor(restored / 'models/delay-v2')
    after = [after_predictor.predict(Scenario.model_validate(row)) for row in SCENARIOS]
    require(before == after, 'prediction_parity_failed')
    require(all(r['research_only'] is True and r['operational_serving_approved'] is False for r in after), 'research_scope_changed')
    require(receipt['active_model_restored'] and receipt['revoked_session_rows'] == 1, 'restore_receipt_incomplete')
    require(AuthStore(restored / 'ain.sqlite3').session(old_token) is None, 'restored_session_not_revoked')
    # Capture quiescent evidence before testing a fresh login in the restored state.
    offline = case / 'offline-evidence'; offline.mkdir()
    for label, source in (('backup', case / 'backup'), ('restored', restored)):
        target = offline / label; target.mkdir()
        for entry in manifest['files']:
            name = entry['path']; out = target / name; out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / name, out)
        name = 'manifest.json' if label == 'backup' else 'recovery-receipt.json'
        shutil.copyfile(source / name, target / name)
    consistency = verify_evidence(offline / 'backup', offline / 'restored', offline_copy=True)
    require(consistency['consistency_verified'], 'offline_consistency_failed')
    restored_auth = AuthStore(restored / 'ain.sqlite3')
    require(restored_auth.session(restored_auth.login('synthetic-recovery-admin', password)) is not None, 'restored_credentials_failed')
    require(database_facts(STATE / 'ain.sqlite3') == manifest['database'], 'synthetic_source_changed')
    return {'passed': True, 'checks': {'executable_model_restored': True, 'three_scenario_exact_prediction_parity': True,
            'restored_session_revoked': True, 'restored_credentials_work': True,
            'offline_restore_evidence_consistent': True, 'synthetic_source_unchanged': True,
            'research_flags_retained': True}, 'prediction_results': after,
            'backup_snapshot_id': manifest['snapshot_id'], 'restoration': receipt,
            'offline_consistency': consistency, 'real_flight_database_restored': False,
            'retrieval_artifact_verified': False, 'model_retrained': False,
            'model_accuracy_evaluated': False}


def run_check(snapshot, manifest_sha256, *, trusted_local_model=False):
    record, inventory = admit(snapshot, manifest_sha256, trusted_local_model=trusted_local_model)
    snapshot = Path(snapshot).absolute()
    case = ROOT / '.local/research-model-recovery' / uuid4().hex
    state = case / 'state'; state.mkdir(parents=True, exist_ok=False)
    report = {'format': 'ain-research-model-recovery-v1', 'passed': False,
              'checked_at': datetime.now(timezone.utc).isoformat(), 'toolkit_identity': source_identity(),
              'verifier_sha256': checksum(Path(__file__)), 'source_snapshot_id': record['snapshot_id'],
              'source_manifest_sha256': manifest_sha256, 'model_sha256': inventory[MODEL]['sha256'],
              'model_report_sha256': inventory[REPORT]['sha256'], 'source_database_accessed': False,
              'source_snapshot_authenticated': False, 'primary_state_accessed': False,
              'synthetic_recovery_database': True, 'production_ready': False}
    try:
        for name in (MODEL, REPORT):
            target = state / name; target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(snapshot / name, target)
            require(checksum(target) == inventory[name]['sha256'], 'copied_artifact_mismatch')
        (case / 'plan.json').write_text(json.dumps({'files': {n: inventory[n] for n in (MODEL, REPORT)}}), encoding='utf-8')
        env = {k: v for k, v in os.environ.items() if not k.startswith('AIN_') and k != 'PORT'}
        env.update(AIN_ENV='local', AIN_CONTAINER='0', AIN_AGENT_JOBS='0', AIN_MONITOR_ENABLED='0',
                   AIN_STATE_ROOT=str(state), AIN_DB_PATH=str(state / 'ain.sqlite3'))
        worker = 'import json,sys;from infra.research_model_recovery import execute_case;print(json.dumps(execute_case(sys.argv[1])))'
        result = subprocess.run([sys.executable, '-c', worker, str(case)], cwd=ROOT, env=env,
                                capture_output=True, text=True, timeout=120)
        require(result.returncode == 0, 'isolated_worker_failed')
        outcome = json.loads(result.stdout)
        require(outcome['passed'] is True, 'model_recovery_failed')
        admit(snapshot, manifest_sha256, trusted_local_model=trusted_local_model)
        report.update(outcome)
    except (ValueError, OSError, RuntimeError, KeyError, TypeError, subprocess.SubprocessError):
        report.update(passed=False, error='research_model_recovery_unverified')
    report['scope'] = 'Artifact and inference parity in a synthetic schema-8 recovery state; no original snapshot database opened, no real airline accuracy evaluation, deployment or independent recovery.'
    target = case / 'report.json'; target.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'report': str(target), 'production_ready': False}, indent=2))
    return report, target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--trusted-local-model', action='store_true', help='Explicitly trust the pinned local executable joblib artifact')
    args = parser.parse_args()
    try:
        report, _ = run_check(args.snapshot, args.manifest_sha256, trusted_local_model=args.trusted_local_model)
        return 0 if report['passed'] else 2
    except (ValueError, OSError, KeyError, TypeError):
        print(json.dumps({'passed': False, 'error': 'research_model_recovery_admission_refused', 'production_ready': False}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
