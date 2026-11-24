"""Synthetic feature-availability and label-maturity split demonstration; no model fitting."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from uuid import uuid4

from ml.temporal_preparation import prepare_splits
from pipelines.time_safe_features import weather_features
from pipelines.synthetic_ingestion import host,local
from pipelines.verify_import_safety import identity
from services.api.paths import ROOT

SOURCES=('ml/temporal_preparation.py','ml/verify_temporal_preparation.py','pipelines/time_safe_features.py')
BOUNDARIES=dict(train_start='2025-06-01T00:00:00Z',train_end='2025-07-01T00:00:00Z',
                validation_end='2025-08-01T00:00:00Z',test_end='2025-09-01T00:00:00Z')


def fixture():
    queries=[];events=[];labels=[]
    for name,day,ready in [('train-ready','2025-06-15','2025-06-16'),
                           ('train-late-label','2025-06-30','2025-07-02'),
                           ('validation-ready','2025-07-15','2025-07-16'),
                           ('test-ready','2025-08-15','2025-08-16'),
                           ('test-late-label','2025-08-31','2025-09-02'),
                           ('missing-weather','2025-08-20','2025-08-21'),
                           ('missing-label','2025-06-20',None)]:
        origin='BBB' if name=='missing-weather' else 'AAA'
        queries.append(dict(query_id=name,origin=origin,decision_at=day+'T09:00:00Z',source_scope='synthetic'))
        if name!='missing-weather':events.append(dict(event_id=name,airport=origin,observed_at=day+'T08:30:00Z',available_at=day+'T08:35:00Z',temperature_c=20,wind_knots=5,source_scope='synthetic'))
        if ready:labels.append(dict(query_id=name,arrival_delay_minutes=10,label_available_at=ready+'T00:00:00Z',source_scope='synthetic'))
    return {'features':weather_features(queries,events,scope='synthetic'),'labels':labels}


def verify(directory):
    host();directory=local(directory);context=identity()
    context['source_sha256'].update({p:hashlib.sha256((ROOT/p).read_text(encoding='utf-8').encode()).hexdigest() for p in SOURCES})
    directory.mkdir(parents=True,exist_ok=False)
    report={'format':'ain-temporal-preparation-drill-v1','checked_at':datetime.now(timezone.utc).isoformat(),
            'case_id':directory.name,**context,'passed':False,'checks':{},'synthetic_only':True,
            'frozen_experiments_accessed':False,'primary_database_accessed':False,
            'training_performed':False,'deployment_performed':False,'production_ready':False}
    try:
        def retain(name,value):
            encoded=(json.dumps(value,indent=2,allow_nan=False)+'\n').encode()
            (directory/name).write_bytes(encoded);return hashlib.sha256(encoded).hexdigest()
        inputs=fixture();report['fixture_sha256']=retain('synthetic-input.json',inputs)
        result=prepare_splits(**inputs,**BOUNDARIES,scope='synthetic')
        report['preparation_sha256']=retain('prepared-splits.json',result)
        changed=[dict(row,arrival_delay_minutes=999) if row['query_id']=='test-ready' else dict(row) for row in inputs['labels']]
        second=prepare_splits(inputs['features'],changed,**BOUNDARIES,scope='synthetic')
        excluded={row['query_id']:row['reason'] for row in result['excluded']}
        partitions=result['partitions']
        report['checks']={
            'one_mature_example_per_split':all(len(rows)==1 for rows in partitions.values()),
            'late_training_label_excluded':excluded['train-late-label']=='label_not_available_at_split_cutoff',
            'late_test_label_excluded':excluded['test-late-label']=='label_not_available_at_split_cutoff',
            'missing_weather_excluded':excluded['missing-weather']=='weather_not_matched',
            'missing_label_excluded':excluded['missing-label']=='missing_label',
            'test_targets_cannot_change_training':partitions['train']==second['partitions']['train'] and partitions['validation']==second['partitions']['validation'],
            'target_not_in_features':all(set(row['X'])=={'origin','temperature_c','wind_knots'} for rows in partitions.values() for row in rows),
            'counts_reconciled':sum(len(rows) for rows in partitions.values())+len(result['excluded'])==len(inputs['features'])==7,
            'synthetic_provenance_retained':all(row['provenance']['source_scope']=='synthetic' for rows in partitions.values() for row in rows),
            'source_unchanged':all(hashlib.sha256((ROOT/p).read_text(encoding='utf-8').encode()).hexdigest()==h for p,h in context['source_sha256'].items())}
        report['counts']=result['counts'];report['passed']=all(report['checks'].values())
    except Exception:report['error']='synthetic_temporal_preparation_check_failed'
    (directory/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    return report


if __name__=='__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    result=verify(ROOT/'.local/temporal-preparation'/uuid4().hex)
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['passed'] else 2)
