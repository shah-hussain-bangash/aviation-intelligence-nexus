"""Freeze a prospective June evaluation plan and trusted model copy; never read candidate rows."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

from infra.research_model_recovery import ordinary, unique_object
from pipelines import journey_prediction as registered
from pipelines.import_bts import source_url
from pipelines.synthetic_ingestion import host, local
from pipelines.verify_import_safety import identity
from services.api.paths import ROOT

PLAN_SHA256 = '7a0ddd03436675ed308368a6bf9463d1cffc88b5a94ec80559eff9ee82b7ed50'


def require(ok, message):
    if not ok: raise ValueError(message)


def prepare(directory, model_sha256):
    host()
    registered.validate_options(True, model_sha256)
    require('..' not in Path(directory).parts, 'fresh_private_evaluation_directory_required')
    target = local(directory)
    require(target.is_relative_to(ROOT/'.local') and not target.exists(), 'fresh_private_evaluation_directory_required')
    plan_bytes = ordinary(ROOT/'ml/june_evaluation_plan.json', 64000).read_bytes()
    require(hashlib.sha256(plan_bytes).hexdigest() == PLAN_SHA256, 'frozen_evaluation_plan_changed')
    plan = json.loads(plan_bytes, object_pairs_hook=unique_object)
    # Only the already registered, explicitly pinned local model is copied.
    # This helper never deserializes its joblib file or opens a candidate archive.
    metadata = registered.copy_registered_model(target/'model', model_sha256)
    model_report_bytes = ordinary(target/'model/report.json', 1_000_000).read_bytes()
    require(hashlib.sha256(model_report_bytes).hexdigest() == metadata['report_sha256'], 'copied_report_changed')
    report = json.loads(model_report_bytes, object_pairs_hook=unique_object)
    groups = report.get('protocol', {}).get('period_groups')
    require(isinstance(groups, dict) and list(groups) == ['train', 'validation', 'test'], 'registered_period_groups_required')
    require(all(isinstance(value, list) and value for value in groups.values()), 'registered_period_groups_required')
    used = [period for periods in groups.values() for period in periods]
    require(used == plan['known_model_periods'] and all(period < plan['candidate_period'] for period in used),
            'candidate_period_overlaps_or_reference_periods_changed')
    threshold, prior = report.get('threshold'), report.get('training_delay_prevalence')
    require(all(type(value) in (int, float) and math.isfinite(value) and 0 < value < 1 for value in (threshold, prior)),
            'finite_frozen_threshold_and_training_prior_required')
    require(registered.source_preserved(metadata), 'registered_source_changed')
    require(hashlib.sha256(ordinary(target/'model/model.joblib',32_000_000).read_bytes()).hexdigest()==model_sha256,
            'copied_model_changed')
    require(hashlib.sha256(ordinary(ROOT/'ml/june_evaluation_plan.json',64000).read_bytes()).hexdigest()==PLAN_SHA256,
            'frozen_evaluation_plan_changed')
    provenance = identity()
    provenance['source_sha256'].update({
        'ml/register_evaluation.py': hashlib.sha256(Path(__file__).read_text(encoding='utf-8').encode()).hexdigest(),
        'ml/june_evaluation_plan.json': PLAN_SHA256,
        'pipelines/journey_prediction.py': hashlib.sha256(Path(registered.__file__).read_text(encoding='utf-8').encode()).hexdigest()
    })
    result = {
        'format': 'ain-external-month-registration-v1', 'state': 'plan_prepared',
        'registered_at': datetime.now(timezone.utc).isoformat(), **provenance,
        'plan': plan, 'plan_sha256': PLAN_SHA256,
        'model': {key:value for key,value in metadata.items() if key != 'scenario'},
        'frozen_threshold': threshold, 'constant_training_prior': prior,
        'known_used_periods': used, 'candidate_period': plan['candidate_period'],
        'declared_source_url': source_url(2025,6),
        'later_than_registered_model_periods': True,
        'candidate_archive_registered': False, 'candidate_rows_read': False,
        'candidate_labels_read': False, 'candidate_source_rights_verified': False,
        'globally_untouched_holdout_established': False,
        'model_deserialized': False, 'model_refitted': False, 'inference_executed': False,
        'metrics_computed': False, 'bootstrap_executed': False,
        'evaluation_attempt_created': False, 'global_single_use_enforced': False,
        'registered_source_preserved': True, 'primary_database_accessed': False,
        'deployment_performed': False, 'production_ready': False,
        'next_dependency': 'Obtain and admit the exact candidate archive after this freeze; implement single-attempt evaluation before reading candidate rows.'
    }
    with (target/'plan.json').open('xb') as stream: stream.write(plan_bytes)
    with (target/'registration.json').open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--model-sha256', required=True)
    args = parser.parse_args()
    try: result = prepare(args.directory, args.model_sha256)
    except (OSError, ValueError, KeyError, TypeError):
        parser.exit(2, 'Evaluation plan was not confirmed. Preserve any partial private directory and inspect its inputs.\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__': main()
