"""Opt-in local-provider June agent check, using fresh private engineering state."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import time
from unittest.mock import patch
from uuid import uuid4

from agents.runtime import Investigation, Investigator
from agents.store import AgentStore, now
from agents.june_evidence import valid_observation
from agents.quality import assess_report
from pipelines.synthetic_ingestion import host, local
from pipelines.verify_import_safety import identity
from rag import ollama
from services.api.main import initialize
from services.api.paths import ROOT
from services.api.june_evaluation import load_june_evaluation, REPORT

OBJECTIVE = ('Use june_evidence only to review the frozen June comparison, descriptive uncertainty '
             'and full research limitations. Include each complete required quotation. Do not query '
             'SQL, documents or simulation, infer causes, refit or recommend operational action.')
SOURCES = ('agents/evaluate_june_agent.py', 'agents/runtime.py', 'agents/tools.py',
           'agents/quality.py', 'agents/june_evidence.py', 'rag/ollama.py',
           'services/api/june_evaluation.py', REPORT)


def write_new(path, value):
    raw = (json.dumps(value, indent=2, allow_nan=False) + '\n').encode()
    with path.open('xb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())


def evaluate(output):
    host()
    if '..' in Path(output).parts:
        raise ValueError('fresh_private_engineering_directory_required')
    output = local(output)
    if not output.is_relative_to(ROOT / '.local') or output == ROOT / '.local' or output.exists():
        raise ValueError('fresh_private_engineering_directory_required')
    # Verify only public aggregate evidence before creating state or contacting a provider.
    summary = load_june_evaluation()
    provenance = identity()
    source_hashes = {name: hashlib.sha256((ROOT/name).read_text(encoding='utf-8').encode()).hexdigest() for name in SOURCES}
    request = Investigation(objective=OBJECTIVE, include_june_evidence=True, required_tools=['june_evidence'])
    output.mkdir(parents=True, exist_ok=False)
    write_new(output/'request.json', request.model_dump())
    events = []; run = None; replay = None; failure_type = None
    original_call = ollama.call

    def observed(route, payload=None, **kwargs):
        event = {'route': route, 'purpose': 'planner' if payload and 'tools' in payload else 'generator' if route == 'chat' else 'model_inventory'}
        events.append(event); started = time.perf_counter()
        try:
            response = original_call(route, payload, **kwargs)
            event.update(state='returned')
            if route == 'chat':
                event.update(done=response.get('done'), done_reason=response.get('done_reason'))
            return response
        except Exception as error:
            event.update(state='failed', error_type=type(error).__name__)
            raise
        finally:
            event['elapsed_ms'] = round((time.perf_counter()-started)*1000, 2)

    started = time.perf_counter(); calls_before_replay = None
    try:
        database = output/'checkpoints.sqlite3'; initialize(database)
        runtime = Investigator(database, None, AgentStore(database))
        actor = {'id':'engineering-june-agent', 'username':'engineering-june-agent', 'role':'researcher'}
        key = str(uuid4())
        # Instrumentation delegates every response unchanged; no provider outputs are substituted.
        with patch.object(ollama, 'call', side_effect=observed):
            run = runtime.run(actor, key, request)
            calls_before_replay = len(events)
            replay = runtime.run(actor, key, request)
    except Exception as error:
        failure_type = type(error).__name__
    elapsed = round((time.perf_counter()-started)*1000, 2)
    steps = run.get('steps', []) if isinstance(run, dict) else []
    june = [s for s in steps if s['tool']=='june_evidence']
    quality = assess_report(run) if isinstance(run, dict) else None
    chats = [e for e in events if e['route']=='chat']
    model = run.get('model', {}) if isinstance(run, dict) else {}
    digest = model.get('digest')
    try:
        preserved = all(hashlib.sha256((ROOT/p).read_text(encoding='utf-8').encode()).hexdigest()==value for p,value in source_hashes.items())
    except OSError:
        preserved = False
    checks = {
        'only_june_tool_completed': len(steps)==1 and len(june)==1 and june[0]['state']=='completed',
        'canonical_snapshot_retained': len(june)==1 and valid_observation(june[0].get('observation')),
        'mandatory_quotes_present': len(june)==1 and june[0]['state']=='completed' and bool(quality) and bool(run.get('claims')) and not quality['june_required_quotes_missing'],
        'coverage_passed': bool(quality) and quality['passed'],
        'actual_planner_and_generator_responses': bool(chats) and {'planner','generator'}.issubset({e['purpose'] for e in chats})
            and all(e['state']=='returned' and e.get('done') is True and e.get('done_reason')=='stop' for e in chats),
        'provider_calls_within_runtime_bounds': sum(e['purpose']=='planner' for e in chats)<=3 and sum(e['purpose']=='generator' for e in chats)<=2,
        'model_identity_recorded': model.get('name')==ollama.CHAT_MODEL and isinstance(digest,str) and bool(re.fullmatch('[a-f0-9]{64}',digest)),
        'awaiting_human_review': bool(run) and run['state']=='awaiting_review' and not run['reviews'],
        'retry_replayed_without_provider_calls': bool(replay) and replay.get('replayed') is True and replay['run_id']==run['run_id'] and len(events)==calls_before_replay,
        'operational_approval_false': bool(run) and run['operational_approval'] is False,
        'public_evidence_unchanged': preserved,
    }
    result = {'format':'ain-june-agent-provider-check-v1', 'checked_at':now(),
        'scope':'Direct native Ollama runtime; separate engineering identity/database; not an authenticated user journey, usefulness rating or model holdout evaluation',
        **provenance, 'execution_source_sha256':source_hashes, 'report_sha256':summary['report_sha256'],
        'provider_instrumentation':'Unmodified call passthrough; route/status/timing only, no raw provider payloads',
        'elapsed_ms':elapsed, 'provider_calls':events, 'checks':checks,
        'passed':failure_type is None and all(checks.values()), 'failure_type':failure_type,
        'run':run, 'genuine_human_usefulness_assessed':False, 'evaluation_repeated':False, 'production_ready':False}
    write_new(output/'evaluation.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', type=Path, required=True)
    result = evaluate(parser.parse_args().output)
    print(json.dumps({k:result[k] for k in ('passed','elapsed_ms','checks','failure_type')}, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
