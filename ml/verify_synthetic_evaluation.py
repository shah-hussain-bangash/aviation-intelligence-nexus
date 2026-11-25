"""Freeze a new synthetic selection, register its evaluation policy and consume one holdout attempt."""
import argparse
from datetime import datetime,timedelta,timezone
import hashlib
import json
from uuid import uuid4

from ml.evaluate_synthetic_holdout import evaluate_once
from ml.verify_regression_selection import verify as verify_selection
from pipelines.time_safe_features import weather_features
from pipelines.synthetic_ingestion import host,local
from pipelines.verify_import_safety import identity
from services.api.paths import ROOT

SOURCES=('ml/evaluate_synthetic_holdout.py','ml/verify_synthetic_evaluation.py','ml/regression_selection.py',
         'ml/verify_regression_selection.py','ml/train_preprocessing.py','ml/temporal_preparation.py','pipelines/time_safe_features.py')


def holdout():
    queries=[];events=[];labels=[]
    for index in range(8):
        day=datetime(2025,8,1)+timedelta(days=index);stamp=day.strftime('%Y-%m-%d')
        name='synthetic-test-'+str(index);origin=('AAA','BBB')[index%2]
        temperature=12+index;wind=3+index%4
        queries.append(dict(query_id=name,origin=origin,decision_at=stamp+'T09:00:00Z',source_scope='synthetic'))
        events.append(dict(event_id=name,airport=origin,observed_at=stamp+'T08:30:00Z',available_at=stamp+'T08:35:00Z',
                           temperature_c=temperature,wind_knots=wind,source_scope='synthetic'))
        labels.append(dict(query_id=name,arrival_delay_minutes=1.5*temperature+2*wind+(3 if origin=='BBB' else 0)-20+0.1*(-1)**index,
                           label_available_at=(day+timedelta(days=1)).strftime('%Y-%m-%dT00:00:00Z'),source_scope='synthetic'))
    return weather_features(queries,events,scope='synthetic'),labels


def setup(directory):
    selected=verify_selection(directory)
    if not selected['passed']:raise ValueError('synthetic_selection_failed')
    features,labels=holdout()  # Only generated after the development selection was frozen.
    feature_bytes=(json.dumps(features,indent=2)+'\n').encode();label_bytes=(json.dumps(labels,indent=2)+'\n').encode()
    policy={'format':'ain-synthetic-holdout-policy-v1','source_scope':'synthetic','attempt_policy':'one_local_attempt_no_reset',
            'protocol_sha256':hashlib.sha256((directory/'registered-protocol.json').read_bytes()).hexdigest(),
            'selection_sha256':hashlib.sha256((directory/'frozen-selection.json').read_bytes()).hexdigest(),
            'features_sha256':hashlib.sha256(feature_bytes).hexdigest(),'labels_sha256':hashlib.sha256(label_bytes).hexdigest()}
    (directory/'holdout-policy.json').write_text(json.dumps(policy,indent=2)+'\n',encoding='utf-8',newline='\n')
    (directory/'holdout-features.json').write_bytes(feature_bytes);(directory/'holdout-labels.json').write_bytes(label_bytes)
    return selected,policy


def verify(directory):
    host();directory=local(directory);context=identity()
    context['source_sha256'].update({p:hashlib.sha256((ROOT/p).read_text(encoding='utf-8').encode()).hexdigest() for p in SOURCES})
    directory.mkdir(parents=True,exist_ok=False)
    report={'format':'ain-synthetic-evaluation-drill-v1','checked_at':datetime.now(timezone.utc).isoformat(),
            'case_id':directory.name,**context,'passed':False,'checks':{},'synthetic_only':True,
            'primary_database_accessed':False,'frozen_experiments_accessed':False,
            'deployment_performed':False,'production_ready':False}
    try:
        case=directory/'experiment';selected,policy=setup(case)
        before={name:hashlib.sha256((case/name).read_bytes()).hexdigest() for name in ('registered-protocol.json','frozen-selection.json','holdout-policy.json','holdout-features.json','holdout-labels.json')}
        first=evaluate_once(case)
        receipt=(case/'holdout-evaluation.json').read_bytes();claim=(case/'holdout-attempt.json').read_bytes()
        second=evaluate_once(case)
        report['checks']={
            'development_selection_passed':selected['passed'] and not selected['selection']['test_evaluated'],
            'first_attempt_evaluated':first['state']=='evaluated' and first['test_evaluated'],
            'attempt_claim_retained':json.loads(claim)['attempt_id']==first['attempt_id'],
            'pinned_selection_used':first['selection_sha256']==policy['selection_sha256'],
            'complete_synthetic_cohort_scored':first['selected_metrics']['records']==first['baseline_metrics']['records']==8,
            'selected_model_not_refitted':first['model_refitted'] is False,
            'repeat_attempt_refused':second['state']=='refused' and not second['test_evaluated'] and not second['claim_consumed'],
            'repeat_preserved_receipt_and_claim':receipt==(case/'holdout-evaluation.json').read_bytes() and claim==(case/'holdout-attempt.json').read_bytes(),
            'frozen_inputs_preserved':all(hashlib.sha256((case/name).read_bytes()).hexdigest()==digest for name,digest in before.items()),
            'source_unchanged':all(hashlib.sha256((ROOT/p).read_text(encoding='utf-8').encode()).hexdigest()==h for p,h in context['source_sha256'].items())}
        report.update(evaluation=first,repeat_attempt=second,policy=policy,selection_file_sha256=policy['selection_sha256'],
                      evaluation_receipt_sha256=hashlib.sha256(receipt).hexdigest(),attempt_receipt_sha256=hashlib.sha256(claim).hexdigest(),
                      frozen_input_sha256=before)
        report['passed']=all(report['checks'].values())
    except Exception:report['error']='synthetic_evaluation_check_failed'
    (directory/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    return report


if __name__=='__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    result=verify(ROOT/'.local/synthetic-evaluation'/uuid4().hex)
    print(json.dumps(result,indent=2));raise SystemExit(0 if result['passed'] else 2)
