"""Read-only source-index admission and isolated evidence-only retrieval recovery."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from uuid import UUID, uuid4

from infra.rehearsal_admission import require
from infra.research_model_recovery import ordinary, unique_object
from infra.recovery import FILES, checksum
from infra.verify_schema8 import source_identity
from services.api.paths import ROOT

INDEX_FILE = 'knowledge/index.json'
QUERIES = (
    {'question': 'What are the operational limitations of the second delay model?', 'source': 'docs/DELAY_V2.md', 'expect_evidence': True},
    {'question': 'How does synthetic gate allocation minimize assignment cost?', 'source': 'docs/GATE_OPTIMIZATION.md', 'expect_evidence': True},
    {'question': 'Explain photosynthesis in chloroplast organelles', 'source': None, 'expect_evidence': False},
)


def admit(snapshot, manifest_sha256):
    from rag.index import SOURCES, ROOT as CORPUS_ROOT, chunks_for
    from rag.service import Knowledge
    from rag import ollama

    require(isinstance(manifest_sha256, str) and re.fullmatch('[0-9a-f]{64}', manifest_sha256), 'full_manifest_pin_required')
    snapshot = Path(snapshot).absolute()
    manifest = ordinary(snapshot / 'manifest.json', 64000)
    require(checksum(manifest) == manifest_sha256, 'manifest_pin_mismatch')
    record = json.loads(manifest.read_text(encoding='utf-8'), object_pairs_hook=unique_object)
    require(isinstance(record, dict) and record.get('format') == 'ain-recovery-v1', 'snapshot_format_invalid')
    require(isinstance(record.get('database'), dict) and type(record['database'].get('schema_version')) is int
            and record['database']['schema_version'] in (7, 8), 'recorded_snapshot_schema_invalid')
    require(isinstance(record.get('snapshot_id'), str), 'snapshot_id_invalid'); UUID(record['snapshot_id'])
    entries = record.get('files')
    require(isinstance(entries, list) and 1 <= len(entries) <= len(FILES), 'snapshot_inventory_invalid')
    inventory = {}
    for entry in entries:
        require(isinstance(entry, dict), 'snapshot_entry_invalid')
        name = entry.get('path')
        require(isinstance(name, str) and name in FILES and name not in inventory, 'snapshot_inventory_invalid')
        require(type(entry.get('size_bytes')) is int and entry['size_bytes'] > 0
                and isinstance(entry.get('sha256'), str) and re.fullmatch('[0-9a-f]{64}', entry['sha256']), 'snapshot_entry_invalid')
        inventory[name] = entry
    require(INDEX_FILE in inventory, 'knowledge_index_required')
    index = ordinary(snapshot / INDEX_FILE, 4_000_000)
    require(index.stat().st_size == inventory[INDEX_FILE]['size_bytes']
            and checksum(index) == inventory[INDEX_FILE]['sha256'], 'index_pin_mismatch')
    envelope = json.loads(index.read_text(encoding='utf-8'), object_pairs_hook=unique_object)
    require(isinstance(envelope, dict) and isinstance(envelope.get('payload'), dict), 'index_envelope_invalid')
    payload = envelope['payload']
    require(payload.get('embedding_model') == ollama.EMBED_MODEL and isinstance(payload.get('embedding_digest'), str)
            and re.fullmatch('[0-9a-f]{64}', payload['embedding_digest']), 'embedding_identity_invalid')
    # Verify actual quoted text/ranges/IDs against current allowlisted documents,
    # not just a self-consistent payload digest. No embedding/model request here.
    expected_chunks = []
    for source in SOURCES:
        raw = ordinary(CORPUS_ROOT / source, 100000).read_bytes()
        expected_chunks.extend(chunks_for(source, raw.decode('utf-8')))
    require(payload.get('chunks') == expected_chunks, 'corpus_chunk_binding_mismatch')
    Knowledge(index).load()  # Hash, source order/bytes, normalized dense vectors and lexical cache.
    return record, inventory[INDEX_FILE], payload['embedding_digest']


def execute_case(case):
    from contextlib import closing
    import secrets
    import sqlite3
    from services.api.paths import STATE
    from services.api.main import initialize
    from services.api.auth import AuthStore
    from infra.recovery import backup, restore, database_facts
    from infra.verify_restore_evidence import verify_evidence
    from rag import ollama
    from rag.service import Knowledge, Question

    case = Path(case).resolve()
    require(case.parent == (ROOT / '.local/retrieval-recovery').resolve(), 'private_case_required')
    require(STATE == case / 'state' and os.environ.get('AIN_DB_PATH') == str(STATE / 'ain.sqlite3'), 'isolated_worker_state_required')
    require(os.environ.get('AIN_OLLAMA_HOST') == '127.0.0.1', 'loopback_embedding_provider_required')
    plan = json.loads((case / 'plan.json').read_text(encoding='utf-8'))
    index = STATE / INDEX_FILE
    require(checksum(index) == plan['index_sha256'], 'copied_index_changed')
    require(ollama.models().get(ollama.EMBED_MODEL) == plan['embedding_digest'], 'embedding_provider_unavailable_or_changed')
    initialize(STATE / 'ain.sqlite3')
    auth = AuthStore(STATE / 'ain.sqlite3'); password = secrets.token_urlsafe(32)
    auth.create_user('synthetic-retrieval-admin', password, 'admin')
    token = auth.login('synthetic-retrieval-admin', password)
    with closing(sqlite3.connect(STATE / 'ain.sqlite3')) as db, db:
        db.execute("INSERT INTO flights(source,source_record_id,flight_date,carrier,origin,destination) VALUES('synthetic_retrieval_recovery_fixture','1','2025-01-01','XX','AAA','BBB')")

    def retrieve(path):
        knowledge = Knowledge(path); results = []
        for row in QUERIES:
            result = knowledge.query(Question(question=row['question'], generate=False), source_document=row['source'])
            require(result['research_only'] is True and result['operational_approval'] is False
                    and result['claims'] == [] and result['generation']['status'] == 'not_requested', 'retrieval_scope_changed')
            if row['expect_evidence']:
                require(result['mode'] == 'evidence_only' and bool(result['evidence'])
                        and all(e['source'] == row['source'] for e in result['evidence']), 'expected_scoped_evidence_missing')
            else:
                require(result['mode'] == 'abstained' and result['evidence'] == [], 'unrelated_question_did_not_abstain')
            results.append(result)
        return results

    before = retrieve(index)
    manifest = backup(STATE, case / 'backup')
    receipt = restore(case / 'backup', case / 'restored')
    restored = case / 'restored'
    after = retrieve(restored / INDEX_FILE)
    require(before == after, 'retrieved_evidence_parity_failed')
    require(ollama.models().get(ollama.EMBED_MODEL) == plan['embedding_digest'], 'embedding_provider_changed')
    require(receipt['knowledge_index_restored'] and not receipt['active_model_restored'], 'restore_artifact_scope_mismatch')
    require(AuthStore(restored / 'ain.sqlite3').session(token) is None, 'restored_session_not_revoked')
    offline = case / 'offline-evidence'; offline.mkdir()
    for label, source in (('backup', case / 'backup'), ('restored', restored)):
        target = offline / label; target.mkdir()
        for entry in manifest['files']:
            name = entry['path']; out = target / name; out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / name, out)
        name = 'manifest.json' if label == 'backup' else 'recovery-receipt.json'
        shutil.copyfile(source / name, target / name)
    evidence = verify_evidence(offline / 'backup', offline / 'restored', offline_copy=True)
    require(evidence['consistency_verified'], 'offline_consistency_failed')
    require(database_facts(STATE / 'ain.sqlite3') == manifest['database']
            and checksum(index) == checksum(restored / INDEX_FILE) == plan['index_sha256'], 'source_or_index_changed')
    return {'passed': True, 'checks': {'index_bytes_preserved': True, 'two_scoped_evidence_results_identical': True,
            'unrelated_query_abstention_preserved': True, 'embedding_digest_observed_before_after': True,
            'restored_session_revoked_and_audited': True, 'offline_receipt_and_rows_consistent': True,
            'synthetic_source_unchanged': True, 'no_generated_claims': True},
            'retrieval_results': after, 'embedding_model': ollama.EMBED_MODEL,
            'embedding_digest': plan['embedding_digest'], 'restoration': receipt,
            'offline_consistency': evidence, 'index_rebuilt': False,
            'generation_evaluated': False, 'semantic_answer_quality_evaluated': False,
            'embedding_weights_restored': False, 'real_flight_database_restored': False}


def run_check(snapshot, manifest_sha256):
    record, entry, embedding_digest = admit(snapshot, manifest_sha256)
    snapshot = Path(snapshot).absolute()
    case = ROOT / '.local/retrieval-recovery' / uuid4().hex
    state = case / 'state'; (state / 'knowledge').mkdir(parents=True, exist_ok=False)
    report = {'format': 'ain-retrieval-recovery-v1', 'passed': False,
              'checked_at': datetime.now(timezone.utc).isoformat(), 'toolkit_identity': source_identity(),
              'verifier_sha256': checksum(Path(__file__)),
              'admission_helper_sha256': checksum(ROOT / 'infra/research_model_recovery.py'),
              'source_snapshot_id': record['snapshot_id'], 'source_manifest_sha256': manifest_sha256,
              'index_file_sha256': entry['sha256'], 'source_snapshot_authenticated': False,
              'source_database_accessed': False, 'primary_state_accessed': False,
              'synthetic_recovery_database': True, 'production_ready': False}
    try:
        shutil.copyfile(snapshot / INDEX_FILE, state / INDEX_FILE)
        require(checksum(state / INDEX_FILE) == entry['sha256'], 'copied_index_mismatch')
        (case / 'plan.json').write_text(json.dumps({'index_sha256': entry['sha256'], 'embedding_digest': embedding_digest}), encoding='utf-8')
        env = {k: v for k, v in os.environ.items() if not k.startswith('AIN_') and k != 'PORT'}
        env.update(AIN_ENV='local', AIN_CONTAINER='0', AIN_AGENT_JOBS='0', AIN_MONITOR_ENABLED='0',
                   AIN_OLLAMA_HOST='127.0.0.1', AIN_STATE_ROOT=str(state), AIN_DB_PATH=str(state / 'ain.sqlite3'))
        worker = 'import json,sys;from infra.retrieval_recovery import execute_case;print(json.dumps(execute_case(sys.argv[1])))'
        result = subprocess.run([sys.executable, '-c', worker, str(case)], cwd=ROOT, env=env,
                                capture_output=True, text=True, timeout=180)
        require(result.returncode == 0, 'isolated_worker_failed')
        outcome = json.loads(result.stdout); require(outcome['passed'] is True, 'retrieval_recovery_failed')
        admit(snapshot, manifest_sha256)
        report.update(outcome)
    except (ValueError, OSError, RuntimeError, KeyError, TypeError, subprocess.SubprocessError):
        report.update(passed=False, error='retrieval_recovery_unverified')
    report['scope'] = 'Native copied-index/evidence-only parity using the observed existing loopback embedding model; synthetic recovery database; no index rebuild, generated answer, provider-weight restore, full database or off-host recovery.'
    target = case / 'report.json'; target.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'report': str(target), 'production_ready': False}, indent=2))
    return report, target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--manifest-sha256', required=True)
    args = parser.parse_args()
    try:
        report, _ = run_check(args.snapshot, args.manifest_sha256)
        return 0 if report['passed'] else 2
    except (ValueError, OSError, RuntimeError, KeyError, TypeError):
        print(json.dumps({'passed': False, 'error': 'retrieval_recovery_admission_refused', 'production_ready': False}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
