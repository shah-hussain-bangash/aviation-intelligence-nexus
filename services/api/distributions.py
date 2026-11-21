"""Pinned retrospective input counts only; HTTP never profiles a database."""
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
from ml.input_distributions import compare,FEATURES,PROTOCOL_SHA256
from services.api.paths import ROOT
from services.api.diagnostics import load_diagnostics,REPORT as MODEL_REPORT,REPORT_SHA256 as MODEL_SHA

REPORT='docs/reports/Input_Distributions.json'
REPORT_SHA256='d2e8ea875e1a0e1f385f19332a8687a17c4fec55e6ec97c5a5f65c40366bdfcd'


def validate_report(report):
    if report['format']!='ain-input-distributions-v1' or report['research_only'] is not True or report['production_ready'] is not False or report['model_changed'] is not False or report['alert_threshold'] is not None or report['csv_identity_verified'] is not False or report['cohort_counts_match_frozen'] is not True:raise ValueError('Unsupported distribution scope')
    if report['protocol_sha256']!=PROTOCOL_SHA256 or report['frozen_model_report_sha256']!=MODEL_SHA or not re.fullmatch('[0-9a-f]{64}',report['query_sha256']):raise ValueError('Unknown source protocol')
    if datetime.fromisoformat(report['checked_at']).tzinfo is None or type(report['elapsed_seconds']) not in (int,float) or not math.isfinite(report['elapsed_seconds']) or report['elapsed_seconds']<0:raise ValueError('Invalid recorded time')
    if list(report['features'])!=FEATURES:raise ValueError('Incomplete input coverage')
    if report['protocol']['features']!=FEATURES or report['protocol']['periods']!={'train':['2025-01','2025-02','2025-03'],'test':['2025-05']}:raise ValueError('Unsupported periods')
    if any(type(report[key]) is not int or report[key]<=0 for key in ['reference_records','comparison_records']):raise ValueError('Invalid population')
    for key,feature in report['features'].items():
        rows=feature['categories'];labels=[r['category'] for r in rows]
        if not 1<=len(rows)<=2000 or any(not isinstance(v,str) or not v or len(v)>30 for v in labels) or len(set(labels))!=len(labels):raise ValueError('Invalid category support')
        rebuilt=compare({r['category']:r['reference_count'] for r in rows},{r['category']:r['comparison_count'] for r in rows})
        if feature['reference_records']!=report['reference_records'] or feature['comparison_records']!=report['comparison_records']:raise ValueError('Inconsistent input cohort')
        for name,value in rebuilt.items():
            if name=='categories':continue
            if type(feature[name]) is not type(value) or (not math.isclose(feature[name],value,rel_tol=1e-10,abs_tol=1e-12) if isinstance(value,float) else feature[name]!=value):raise ValueError('Inconsistent distribution metric')
        for saved,expected in zip(rows,rebuilt['categories']):
            if saved['category']!=expected['category'] or any(type(saved[name]) not in (int,float) or not math.isfinite(saved[name]) or not math.isclose(saved[name],expected[name],abs_tol=1e-10) for name in ['reference_share','comparison_share','change_percentage_points']):raise ValueError('Inconsistent category shares')
    return report


def load_distributions(root=ROOT):
    path=Path(root)/REPORT
    if path.is_symlink() or path.stat().st_size>1000000:raise ValueError('Invalid distribution report')
    text=path.read_text(encoding='utf-8')
    if hashlib.sha256(text.encode()).hexdigest()!=REPORT_SHA256:raise ValueError('Distribution report integrity mismatch')
    report=validate_report(json.loads(text));load_diagnostics(root)
    model=json.loads((Path(root)/MODEL_REPORT).read_text(encoding='utf-8'))
    if report['reference_records']!=model['training_records'] or report['comparison_records']!=model['test']['model']['records']:raise ValueError('Recorded cohort mismatch')
    return {**report,'integrity_verified':True,'report_sha256':REPORT_SHA256}
