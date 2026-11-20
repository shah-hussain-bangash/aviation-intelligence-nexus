"""Recorded model diagnostics only: no fitting, inference or database access."""
import hashlib
import json
import math
from pathlib import Path
from services.api.paths import ROOT

REPORT = 'docs/reports/Delay_v2.json'
REPORT_SHA256 = 'e58f44086ba8c271f2e00c1965a136911018f2dd82bc625cbf7fb2752fb0c3f9'


def summarize(metrics):
    n = metrics['records']
    matrix = metrics['confusion_matrix_labels_0_1']
    if type(n) is not int or n <= 0 or len(matrix) != 2 or any(len(row) != 2 for row in matrix):
        raise ValueError('Invalid population')
    tn, fp, fn, tp = [v for row in matrix for v in row]
    if any(type(v) is not int or v < 0 for row in matrix for v in row) or tn+fp+fn+tp != n:
        raise ValueError('Invalid confusion counts')
    derived = {'delay_prevalence':(fn+tp)/n, 'accuracy':(tn+tp)/n,
        'precision':tp/(tp+fp) if tp+fp else 0, 'recall':tp/(tp+fn) if tp+fn else 0,
        'f1':2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0}
    for key, value in derived.items():
        if not math.isclose(metrics[key], value, rel_tol=1e-9, abs_tol=1e-12):
            raise ValueError('Inconsistent recorded metric')
    for key in ['roc_auc','average_precision','brier_score']:
        if type(metrics[key]) not in (int,float) or not math.isfinite(metrics[key]) or not 0 <= metrics[key] <= 1:
            raise ValueError('Invalid recorded score')
    if not math.isfinite(metrics['log_loss']) or metrics['log_loss'] < 0:
        raise ValueError('Invalid recorded loss')
    bins = metrics['calibration_bins']
    ids = set()
    for row in bins:
        if type(row['bin']) is not int or not 0 <= row['bin'] <= 9 or row['bin'] in ids or type(row['count']) is not int or row['count'] <= 0:
            raise ValueError('Invalid calibration population')
        ids.add(row['bin'])
        for key in ['mean_probability','observed_rate']:
            if not math.isfinite(row[key]) or not 0 <= row[key] <= 1:
                raise ValueError('Invalid calibration rate')
    if sum(row['count'] for row in bins) != n or not math.isclose(sum(row['count']*row['observed_rate'] for row in bins),fn+tp,abs_tol=1e-6):
        raise ValueError('Calibration counts do not reconcile')
    return {**metrics, 'binned_ece':sum(row['count']*abs(row['mean_probability']-row['observed_rate']) for row in bins)/n,
        'false_alerts':fp,'missed_delays':fn,'alert_count':tp+fp}


def load_diagnostics(root=ROOT):
    path = Path(root)/REPORT
    if path.is_symlink() or path.stat().st_size > 200000:
        raise ValueError('Invalid fixed report')
    text = path.read_text(encoding='utf-8')
    if hashlib.sha256(text.encode()).hexdigest() != REPORT_SHA256:
        raise ValueError('Recorded model report integrity mismatch')
    report = json.loads(text)
    if report['model_version'] != 'delay-v2' or report['production_ready'] is not False or report['release_assessment']['approved_for_operational_serving'] is not False:
        raise ValueError('Unsupported model claim')
    periods = {key:{'model':summarize(report[key]['model']),
        'baseline':{k:report[key]['constant_training_prior'][k] for k in ['records','log_loss','brier_score','roc_auc']}}
        for key in ['validation','test']}
    carriers = {key:summarize(value) for key,value in report['test_by_carrier'].items()}
    if sum(row['records'] for row in carriers.values()) != periods['test']['model']['records']:
        raise ValueError('Carrier populations do not reconcile')
    for a in range(2):
        for b in range(2):
            if sum(row['confusion_matrix_labels_0_1'][a][b] for row in carriers.values()) != periods['test']['model']['confusion_matrix_labels_0_1'][a][b]:
                raise ValueError('Carrier outcomes do not reconcile')
    return {'format':'ain-model-diagnostics-v1','model_version':report['model_version'],
        'report_sha256':REPORT_SHA256,'integrity_verified':True,'research_only':True,'production_ready':False,
        'threshold':report['threshold'],'periods':periods,'carriers':carriers,'limitations':report['limitations'],
        'method':'Recorded April validation and May test, at the April-selected fixed threshold. ECE is count-weighted absolute calibration error over the recorded bins; it depends on binning and is not a statistical significance test.'}
