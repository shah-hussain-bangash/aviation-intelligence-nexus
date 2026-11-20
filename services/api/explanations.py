"""Fixed aggregate permutation evidence; no unpickling, training or flight SQL."""
import hashlib
import json
import math
import statistics
from pathlib import Path
from services.api.paths import ROOT

REPORT='docs/reports/Delay_v2_Permutation.json'
REPORT_SHA256='b8fc7102c0a7d36cb563279dccc0e64b30ff2f92ed9226c858ed4f48a9865677'
PROTOCOL_SHA256='3b1b1da7d092a05007a77a2864e1ab4c52bf669db610cba83098e1cf7788d04c'
GROUPS={'carrier':['carrier'],'origin':['origin'],'destination':['destination'],
    'departure_time':['scheduled_departure_hour','scheduled_departure_minute'],'weekday':['day_of_week']}
MEASURES=['log_loss_increase','roc_auc_decrease','brier_increase']


def validate_report(report):
    if (report['format']!='ain-permutation-v1' or report['model_version']!='delay-v2'
        or report['research_only'] is not True or report['production_ready'] is not False
        or report['source_hashes_unchanged'] is not True or report['sample_records']!=10000
        or report['validation_population']!=577730 or report['protocol_sha256']!=PROTOCOL_SHA256):
        raise ValueError('Unsupported explanation scope')
    p=report['protocol']
    if p['period']!='2025-04' or p['split']!='validation' or p['sample_records']!=10000 or p['repeats']!=3 or p['seed']!=20261120 or p['groups']!=GROUPS:
        raise ValueError('Diagnostic scope changed')
    if report['artifact_sha256']!='71b23232edc615a01daee387e1e7dbb2c0aa3f7dae2b4d1f33fabbc0fbbff732' or report['validation_sha256']!='2dc8e38595d10b664ef19de6b6b73aa63f8b7a90893cedef4797e271d702c3c5':
        raise ValueError('Diagnostic sources changed')
    baseline=report['baseline']
    if not math.isfinite(baseline['log_loss']) or baseline['log_loss']<0 or any(not math.isfinite(baseline[k]) or not 0<=baseline[k]<=1 for k in ['roc_auc','brier_score']):
        raise ValueError('Invalid baseline')
    if len(report['groups'])!=5 or {row['group'] for row in report['groups']}!=set(GROUPS):
        raise ValueError('Incomplete group coverage')
    for row in report['groups']:
        if row['columns']!=GROUPS[row['group']] or len(row['repeats'])!=3:
            raise ValueError('Invalid shuffle group')
        for key in MEASURES:
            values=[r[key] for r in row['repeats']]
            if any(type(v) not in (int,float) or not math.isfinite(v) for v in values):
                raise ValueError('Invalid shuffle measurement')
            if key!='log_loss_increase' and any(not -1<=v<=1 for v in values):
                raise ValueError('Invalid metric difference')
            for observed,expected in [(row['mean'][key],statistics.mean(values)),(row['repeat_std'][key],statistics.stdev(values))]:
                if not math.isclose(observed,expected,rel_tol=1e-9,abs_tol=1e-12):
                    raise ValueError('Inconsistent shuffle summary')
    return report


def load_explanations(root=ROOT):
    path=Path(root)/REPORT
    if path.is_symlink() or path.stat().st_size>100000:
        raise ValueError('Invalid fixed explanation report')
    text=path.read_text(encoding='utf-8')
    if hashlib.sha256(text.encode()).hexdigest()!=REPORT_SHA256:
        raise ValueError('Explanation report integrity mismatch')
    return {**validate_report(json.loads(text)),'integrity_verified':True,'report_sha256':REPORT_SHA256}
