"""Pinned June aggregate projection. Never opens an archive, model or local receipt."""
import hashlib
import json
from pathlib import Path

from services.api.paths import ROOT

REPORT = 'docs/reports/June_2025_Frozen_Evaluation.json'
REPORT_SHA256 = '1928b626dfe131611bd3668bdd48e8baeaf022b0bf8919c364a682ec0298c372'
MAX_BYTES = 600_000
METRICS = ('records', 'delay_prevalence', 'roc_auc', 'average_precision',
           'log_loss', 'brier_score', 'precision', 'recall', 'f1')


def load_june_evaluation(root=ROOT):
    path = Path(root) / REPORT
    if path.is_symlink():
        raise ValueError('Invalid fixed June report')
    with path.open('rb') as source:
        raw = source.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('June report exceeds bound')
    text = raw.decode('utf-8').replace('\r\n', '\n')
    if hashlib.sha256(text.encode('utf-8')).hexdigest() != REPORT_SHA256:
        raise ValueError('June report changed')
    report = json.loads(text)
    if (report['format'] != 'ain-june-frozen-public-report-v1'
            or report['state'] != 'evaluated' or report['candidate_period'] != '2025-06'
            or report['production_ready'] is not False
            or report['operational_approval'] is not False):
        raise ValueError('Unsupported June scope')
    evaluation = report['evaluation']
    return {
        'format': 'ain-june-evaluation-summary-v1',
        'candidate_period': report['candidate_period'],
        'completed_at': report['completed_at'],
        'source_scope': report['source_scope'],
        'execution_revision': report['execution_revision'],
        'execution_tree_sha': report['execution_tree_sha'],
        'report_path': REPORT, 'report_sha256': REPORT_SHA256,
        'archive_sha256': report['archive_sha256'],
        'model_sha256': report['model_sha256'], 'plan_sha256': report['plan_sha256'],
        'data_counts': report['data_counts'],
        'model': {key: evaluation['model'][key] for key in METRICS},
        'constant_training_prior': {key: evaluation['constant_training_prior'][key] for key in METRICS},
        'frozen_threshold': evaluation['frozen_threshold'],
        'constant_probability': evaluation['constant_probability'],
        'research_comparison': evaluation['research_comparison'],
        'uncertainty': evaluation['uncertainty'],
        'cohort_inventory': {key: len(evaluation['cohort_diagnostics'][key])
                             for key in ('carrier', 'origin')},
        'limitations': report['limitations'],
        'integrity_verified': True, 'research_only': True,
        'inference_executed_by_request': False,
        'globally_untouched_holdout_established': False,
        'source_rights_verified': False, 'operational_approval': False,
        'production_ready': False,
    }
