"""Register and select synthetic development-only regression; never evaluate a test set."""
import argparse
import copy
from datetime import datetime,timedelta,timezone
import hashlib
import json
from uuid import uuid4

from ml.regression_selection import protocol,select_regression
from ml.temporal_preparation import prepare_splits
from ml.verify_temporal_preparation import BOUNDARIES
from pipelines.time_safe_features import weather_features
from pipelines.synthetic_ingestion import host,local
from pipelines.verify_import_safety import identity
from services.api.paths import ROOT

SOURCES=('ml/regression_selection.py','ml/verify_regression_selection.py','ml/train_preprocessing.py',
         'ml/temporal_preparation.py','ml/verify_temporal_preparation.py','pipelines/time_safe_features.py')


def fixture():
    queries=[];events=[];labels=[]
    for month,count in ((6,20),(7,8)):
        for index in range(count):
            day=datetime(2025,month,1)+timedelta(days=index)
            stamp=day.strftime('%Y-%m-%d');name=f'synthetic-{month}-{index}'
            origin=('AAA','BBB')[index%2];temperature=10+index;wind=2+index%5
            queries.append(dict(query_id=name,origin=origin,decision_at=stamp+'T09:00:00Z',source_scope='synthetic'))
            events.append(dict(event_id=name,airport=origin,observed_at=stamp+'T08:30:00Z',available_at=stamp+'T08:35:00Z',
                               temperature_c=temperature,wind_knots=wind,source_scope='synthetic'))
            labels.append(dict(query_id=name,arrival_delay_minutes=1.5*temperature+2*wind+(3 if origin=='BBB' else 0)-20+0.1*(-1)**index,
                               label_available_at=(day+timedelta(days=1)).strftime('%Y-%m-%dT00:00:00Z'),source_scope='synthetic'))
    return prepare_splits(weather_features(queries,events,scope='synthetic'),labels,**BOUNDARIES,scope='synthetic')


def verify(directory):
    host();directory=local(directory);context=identity()
    context['source_sha256'].update({p:hashlib.sha256((ROOT/p).read_text(encoding='utf-8').encode()).hexdigest() for p in SOURCES})
    directory.mkdir(parents=True,exist_ok=False)
    report={'format':'ain-regression-selection-drill-v1','checked_at':datetime.now(timezone.utc).isoformat(),
            'case_id':directory.name,**context,'passed':False,'checks':{},'synthetic_only':True,
            'primary_database_accessed':False,'frozen_experiments_accessed':False,
            'test_evaluated':False,'deployment_performed':False,'production_ready':False}
    try:
        def retain(name,value):
            data=(json.dumps(value,indent=2,allow_nan=False)+'\n').encode()
            (directory/name).write_bytes(data);return hashlib.sha256(data).hexdigest()
        development=fixture()
        declared=protocol(development['boundaries'],experiment_id='synthetic-arrival-regression-v1',scope='synthetic')
        report['protocol_file_sha256']=retain('registered-protocol.json',declared)
        report['development_file_sha256']=retain('synthetic-development.json',development)
        selection=select_regression(development,declared)
        report['selection_file_sha256']=retain('frozen-selection.json',selection)
        changed=copy.deepcopy(development)
        for row in changed['partitions']['validation']:row['y']+=100
        changed_selection=select_regression(changed,declared)
        bad_protocol=copy.deepcopy(declared);bad_protocol['selection_metric']='test_mae'
        try:select_regression(development,bad_protocol);refused=False
        except ValueError:refused=True
        report['checks']={
            'registered_protocol_preserved':hashlib.sha256((directory/'registered-protocol.json').read_bytes()).hexdigest()==report['protocol_file_sha256'],
            'development_contains_no_test_rows':development['partitions']['test']==[] and development['counts']['test']==0,
            'training_and_validation_counts':selection['training_records']==20 and selection['validation_records']==8,
            'fixed_candidates_fitted':len(selection['candidates'])==selection['predictive_models_fitted']==3,
            'selection_uses_validation_mae':selection['selected']['alpha']==min(selection['candidates'],key=lambda row:(row['validation']['mae'],row['alpha']))['alpha'],
            'baseline_recorded':selection['baseline']['validation']['records']==8,
            'validation_mutation_cannot_change_training_preprocessing':selection['preprocessing']['fit_state_sha256']==changed_selection['preprocessing']['fit_state_sha256'],
            'candidate_coefficients_ignore_validation_targets':[(r['coefficients'],r['intercept']) for r in selection['candidates']]==[(r['coefficients'],r['intercept']) for r in changed_selection['candidates']],
            'test_metric_protocol_refused':refused,
            'source_unchanged':all(hashlib.sha256((ROOT/p).read_text(encoding='utf-8').encode()).hexdigest()==h for p,h in context['source_sha256'].items())}
        report['selection']=selection;report['passed']=all(report['checks'].values())
    except Exception:report['error']='synthetic_regression_selection_check_failed'
    (directory/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    return report


if __name__=='__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    result=verify(ROOT/'.local/regression-selection'/uuid4().hex)
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['passed'] else 2)
