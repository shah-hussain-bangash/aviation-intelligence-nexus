"""Fixed aggregate duration evaluation; no training, scoring, SQL or deserialization."""
import hashlib
import json
import math
from pathlib import Path
import re
from services.api.paths import ROOT

REPORT='docs/reports/Delay_Duration_v1.json'
REPORT_SHA256='a38a17fef2511c6306e20da334a3674de84c9324b88597580dbdc7dde971129d'
PROTOCOL_SHA256='814b217e92070cb990f9239804fdca39c768e6a1849f5653fac74c1c36b473f7'


def number(value):
    if type(value) not in (int,float) or not math.isfinite(value):raise ValueError('Invalid regression value')
    return value


def near(a,b):
    if not math.isclose(number(a),number(b),rel_tol=1e-9,abs_tol=1e-8):raise ValueError('Inconsistent regression arithmetic')


def validate_metrics(m,n,sst):
    if type(m['records']) is not int or m['records']!=n or any(number(m[k])<0 for k in ['mae','rmse','sum_absolute_error','sum_squared_error','p50_absolute_error','p90_absolute_error','p95_absolute_error']):raise ValueError('Invalid regression errors')
    near(m['mae'],m['sum_absolute_error']/n);near(m['rmse']**2,m['sum_squared_error']/n);near(m['mean_error'],m['sum_error']/n)
    if not m['p50_absolute_error']<=m['p90_absolute_error']<=m['p95_absolute_error']:raise ValueError('Invalid error quantiles')
    if sst:near(m['r2'],1-m['sum_squared_error']/sst)
    elif m['r2'] is not None:raise ValueError('Constant-target R squared must be undefined')


def validate_report(r):
    if r['format']!='ain-duration-regression-v1' or r['experiment']!='positive-delay-duration-v1' or r['protocol_sha256']!=PROTOCOL_SHA256 or r['research_only'] is not True or r['production_ready'] is not False or r['source_hashes_unchanged'] is not True:raise ValueError('Invalid duration scope')
    for key in ['artifact_sha256','freeze_sha256']:
        if not isinstance(r[key],str) or not re.fullmatch('[a-f0-9]{64}',r[key]):raise ValueError('Missing experiment identity')
    for key in ['mean','median']:
        if number(r['baselines'][key])<0:raise ValueError('Invalid training baseline')
    checks={}
    if set(r['datasets'])!={'train','validation','test'}:raise ValueError('Incomplete duration dataset')
    for split,expected in [('train',1611046),('validation',577730),('test',597574)]:
        data=r['datasets'][split]
        if type(data['records']) is not int or data['records']!=expected or not re.fullmatch('[a-f0-9]{64}',data['sha256']):raise ValueError('Duration split identity mismatch')
        if split=='train':continue
        period=r[split];target=period['target_summary'];n=target['records'];sst=number(target['sum_squared_deviation'])
        if type(n) is not int or n!=expected or sst<0 or not 0<=number(target['median'])<=number(target['max']) or not 0<=number(target['mean'])<=target['max'] or type(target['zero_records']) is not int or not 0<=target['zero_records']<=n:raise ValueError('Invalid duration target population')
        for key in ['model','training_mean_baseline','training_median_baseline']:validate_metrics(period[key],n,sst)
        for key,base in [('training_mean_baseline','mean'),('training_median_baseline','median')]:
            near(period[key]['mean_error'],r['baselines'][base]-target['mean']);near(period[key]['rmse']**2,sst/n+(r['baselines'][base]-target['mean'])**2)
        h=period['residual_histogram']
        if h['sign']!='actual minus predicted; positive means underprediction' or h['labels']!=['below -60','-60 to below -15','-15 to below 0','0 to below 15','15 to below 60','60 and above'] or len(h['counts'])!=6 or any(type(v) is not int or v<0 for v in h['counts']) or sum(h['counts'])!=n:raise ValueError('Invalid residual population')
        tail=period['observed_60_plus']
        if type(tail['records']) is not int or not 0<=tail['records']<=n:raise ValueError('Invalid severe-delay population')
        if tail['records']:
            if number(tail['model_mae'])<0:raise ValueError('Invalid tail MAE')
            number(tail['model_mean_error'])
        elif tail['model_mae'] is not None or tail['model_mean_error'] is not None:raise ValueError('Missing tail must be undefined')
        checks[split]=period['model']['rmse']<=.99*period['training_mean_baseline']['rmse']
    gate=r['research_check']
    if any(type(gate['by_period'][k]) is not bool or gate['by_period'][k]!=v for k,v in checks.items()) or type(gate['passed']) is not bool or gate['passed']!=all(checks.values()) or gate['operational_approval'] is not False:raise ValueError('Invalid RMSE research check')
    if not isinstance(r['limitations'],list) or len(r['limitations'])<7 or any(not isinstance(v,str) or not v for v in r['limitations']):raise ValueError('Missing duration limitations')
    return r


def load_duration(root=ROOT):
    root=Path(root);path=root/REPORT
    if path.is_symlink() or path.stat().st_size>100000:raise ValueError('Invalid fixed duration evidence')
    text=path.read_text(encoding='utf-8')
    if hashlib.sha256(text.encode()).hexdigest()!=REPORT_SHA256:raise ValueError('Duration evidence changed')
    protocol=(root/'ml/duration_protocol.json').read_text(encoding='utf-8')
    if hashlib.sha256(protocol.encode()).hexdigest()!=PROTOCOL_SHA256:raise ValueError('Duration protocol changed')
    r=validate_report(json.loads(text))
    if r['protocol']!=json.loads(protocol):raise ValueError('Duration protocol snapshot mismatch')
    return {**r,'integrity_verified':True,'report_sha256':REPORT_SHA256}
