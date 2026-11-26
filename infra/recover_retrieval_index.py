"""Explicit offline repair of a retained index in an interrupted private retrieval rehearsal."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from uuid import uuid4

from infra.rehearsal_admission import require
from infra.research_model_recovery import ordinary, unique_object
from infra.recovery import checksum
from infra.verify_schema8 import source_identity
from services.api.paths import ROOT


def unredirected(path):
    require(not any(p.is_symlink() or getattr(p, 'is_junction', lambda: False)()
                    for p in (path, *path.parents)), 'unredirected_repair_path_required')


def admit(case, plan_sha256, *, offline=False):
    require(offline is True, 'explicit_offline_declaration_required')
    require(isinstance(plan_sha256, str) and re.fullmatch('[0-9a-f]{64}', plan_sha256), 'full_plan_pin_required')
    case = Path(case).absolute()
    require(case.parent == (ROOT / '.local/restored-api').absolute()
            and re.fullmatch('[0-9a-f]{32}', case.name), 'owned_retrieval_case_required')
    unredirected(case)
    plan_path = ordinary(case / 'plan.json', 1_000_000)
    require(checksum(plan_path) == plan_sha256, 'repair_plan_pin_mismatch')
    def invalid(value): raise ValueError('nonfinite_plan_value')
    plan = json.loads(plan_path.read_text(encoding='utf-8'), object_pairs_hook=unique_object, parse_constant=invalid)
    require(isinstance(plan, dict) and plan.get('with_retrieval') is True
            and plan.get('with_retrieval_recovery') is True and plan.get('with_prediction') is False,
            'retrieval_recovery_plan_required')
    require(isinstance(plan.get('files'), dict), 'repair_inventory_required')
    pin = plan['files'].get('knowledge/index.json')
    require(isinstance(pin, str) and re.fullmatch('[0-9a-f]{64}', pin), 'recorded_index_pin_required')
    retained = ordinary(case / 'retained-knowledge-index.json', 4_000_000)
    require(checksum(retained) == pin, 'retained_index_pin_mismatch')
    target = case / 'state/knowledge/index.json'
    unredirected(target)
    require(target.parent.is_dir() and not target.exists(), 'missing_index_destination_required')
    # Offline structural/corpus verification only. No provider or database is contacted.
    from rag.index import ROOT as CORPUS_ROOT, SOURCES, chunks_for
    from rag.service import Knowledge
    from rag.ollama import EMBED_MODEL
    index_hash, payload, *_ = Knowledge(retained).load()
    require(payload.get('embedding_model') == EMBED_MODEL
            and isinstance(payload.get('embedding_digest'), str) and re.fullmatch('[0-9a-f]{64}', payload['embedding_digest'])
            and isinstance(payload.get('revision'), str) and re.fullmatch('[0-9a-f]{40}', payload['revision']),
            'retained_index_identity_invalid')
    chunks = []
    for name in SOURCES:
        chunks.extend(chunks_for(name, (CORPUS_ROOT / name).read_text(encoding='utf-8')))
    require(payload['chunks'] == chunks, 'retained_corpus_binding_failed')
    return plan_path, retained, target, pin, index_hash


def run_repair(case, plan_sha256, *, offline=False):
    plan, retained, target, pin, index_hash = admit(case, plan_sha256, offline=offline)
    output = ROOT / '.local/index-repairs' / uuid4().hex
    unredirected(output)
    output.mkdir(parents=True, exist_ok=False)
    report = {'format': 'ain-owned-index-repair-v1', 'passed': False,
        'checked_at': datetime.now(timezone.utc).isoformat(), 'toolkit_identity': source_identity(),
        'repair_tool_sha256': checksum(Path(__file__)), 'case_id': target.parents[2].name,
        'plan_sha256': plan_sha256, 'retained_index_sha256': pin, 'index_sha256': index_hash,
        'offline_asserted': True, 'service_shutdown_verified': False,
        'database_accessed': False, 'provider_contacted': False, 'model_weights_restored': False,
        'production_ready': False}
    try:
        with retained.open('rb') as source:
            raw = source.read(4_000_001)
        require(0 < len(raw) <= 4_000_000 and hashlib.sha256(raw).hexdigest() == pin
                and checksum(plan) == plan_sha256, 'repair_inputs_changed')
        # Exclusive creation refuses a destination appearing after admission. Retained
        # evidence stays independent: do not hardlink it to a potentially rebuilt index.
        with target.open('xb') as stream:
            require(stream.write(raw) == len(raw), 'index_copy_incomplete')
        require(checksum(ordinary(target, 4_000_000)) == pin and checksum(retained) == pin
                and checksum(plan) == plan_sha256, 'repair_post_copy_binding_failed')
        report.update(passed=True, retained_source_preserved=True, restored_file_sha256=pin)
    except (OSError, ValueError, RuntimeError):
        report.update(error='index_repair_unverified', destination_may_need_inspection=target.exists())
    report['scope'] = ('Unsigned operator-selected offline artifact repair; original retained file is kept. '
                       'No service restart, database repair, search execution, human judgment or production approval.')
    path = output / 'report.json'
    with path.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
    return report, path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', required=True, type=Path)
    parser.add_argument('--plan-sha256', required=True)
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args()
    try:
        report, path = run_repair(args.case, args.plan_sha256, offline=args.offline)
        print(json.dumps({'passed': report['passed'], 'report': str(path), 'production_ready': False}))
        return 0 if report['passed'] else 2
    except (OSError, ValueError, RuntimeError, KeyError, TypeError):
        print(json.dumps({'passed': False, 'error': 'index_repair_admission_refused', 'production_ready': False}))
        return 2


if __name__ == '__main__': raise SystemExit(main())
