"""Integrity-pinned April aggregate evidence; no model loading, scoring or flight SQL."""
import hashlib
import json
from pathlib import Path
from services.api.paths import ROOT
from services.api.diagnostics import load_diagnostics

REPORT='docs/reports/April_Threshold_Tradeoffs.json'
REPORT_SHA256='922e4216dc175d70b1310d95a9baeb307689f432d9c6441d52f63c8d23b9e275'
PROTOCOL_SHA256='db5cef69999a445491cda6b34ad7eddfafa68a69ff9e949b068cc086060ab77d'


def validate_report(r):
    if r['format']!='ain-threshold-tradeoffs-v1' or r['model_version']!='delay-v2' or r['period']!='2025-04' or r['research_only'] is not True or r['production_ready'] is not False or r['source_hashes_unchanged'] is not True or r['frozen_counts_reproduced'] is not True:
        raise ValueError('Invalid threshold diagnostic scope')
    p=r['protocol']
    if r['protocol_sha256']!=PROTOCOL_SHA256 or p['split']!='validation' or p['period']!='2025-04' or p['positive_rule']!='probability >= threshold' or p['threshold_percent']!={'start':0,'stop':100,'step':1} or p['production_ready'] is not False:
        raise ValueError('Invalid threshold protocol')
    n=r['records'];positive=r['positives']
    if type(n) is not int or type(positive) is not int or not 0<positive<n or type(r['frozen_threshold_percent']) is not int or not 0<=r['frozen_threshold_percent']<=100 or len(r['rows'])!=101:
        raise ValueError('Invalid threshold population')
    for index,row in enumerate(r['rows']):
        if set(row)!={'threshold_percent','tn','fp','fn','tp'} or type(row['threshold_percent']) is not int or row['threshold_percent']!=index or any(type(row[k]) is not int or row[k]<0 for k in ['tn','fp','fn','tp']):raise ValueError('Invalid threshold counts')
        if row['fn']+row['tp']!=positive or row['tn']+row['fp']!=n-positive:raise ValueError('Threshold counts do not reconcile')
        if index and (row['tp']>r['rows'][index-1]['tp'] or row['fp']>r['rows'][index-1]['fp']):raise ValueError('Nonmonotonic alert counts')
    if r['rows'][0]['fn']!=0 or r['rows'][0]['tn']!=0:raise ValueError('Zero threshold must alert every record')
    if not isinstance(r['limitations'],list) or len(r['limitations'])<6 or any(not isinstance(v,str) or not v for v in r['limitations']):raise ValueError('Missing limitations')
    return r


def load_thresholds(root=ROOT):
    root=Path(root);path=root/REPORT
    if path.is_symlink() or path.stat().st_size>100000:raise ValueError('Invalid fixed evidence path')
    text=path.read_text(encoding='utf-8')
    if hashlib.sha256(text.encode()).hexdigest()!=REPORT_SHA256:raise ValueError('Threshold evidence changed')
    protocol=(root/'ml/threshold_protocol.json').read_text(encoding='utf-8')
    if hashlib.sha256(protocol.encode()).hexdigest()!=PROTOCOL_SHA256:raise ValueError('Threshold protocol changed')
    r=validate_report(json.loads(text))
    if r['protocol']!=json.loads(protocol):raise ValueError('Protocol snapshot mismatch')
    original=load_diagnostics(root);frozen=original['periods']['validation']['model'];row=r['rows'][r['frozen_threshold_percent']]
    if r['records']!=frozen['records'] or r['frozen_threshold_percent']!=round(original['threshold']*100) or [[row['tn'],row['fp']],[row['fn'],row['tp']]]!=frozen['confusion_matrix_labels_0_1']:raise ValueError('Frozen April evidence mismatch')
    return {**r,'report_sha256':REPORT_SHA256,'integrity_verified':True}
