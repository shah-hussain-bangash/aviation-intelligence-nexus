"""Synthetic train-only fitting, sparse transformation and future-split noninterference."""
import argparse
import copy
from datetime import datetime,timezone
import hashlib
import json
from uuid import uuid4

import numpy as np

from ml.temporal_preparation import prepare_splits
from ml.verify_temporal_preparation import fixture as temporal_fixture, BOUNDARIES
from ml.train_preprocessing import fit_training_preprocessor
from pipelines.synthetic_ingestion import host,local
from pipelines.verify_import_safety import identity
from services.api.paths import ROOT

SOURCES=('ml/train_preprocessing.py','ml/verify_train_preprocessing.py','ml/temporal_preparation.py','ml/verify_temporal_preparation.py')


def fixture():
    inputs=temporal_fixture()
    second=dict(inputs['features'][0],query_id='train-second',event_id='train-second',
                decision_at='2025-06-17T09:00:00Z',observed_at='2025-06-17T08:30:00Z',
                available_at='2025-06-17T08:35:00Z',temperature_c=30,wind_knots=15)
    inputs['features'].append(second)
    inputs['labels'].append(dict(query_id='train-second',arrival_delay_minutes=-5,
                                 label_available_at='2025-06-18T00:00:00Z',source_scope='synthetic'))
    for row in inputs['features']:
        if row['query_id']=='validation-ready':row.update(origin='BBB',temperature_c=100)
        if row['query_id']=='test-ready':row['origin']='CCC'
    return prepare_splits(**inputs,**BOUNDARIES,scope='synthetic')


def csr_records(matrices):
    return {name:{'shape':list(matrix.shape),'data':matrix.data.tolist(),
                  'indices':matrix.indices.tolist(),'indptr':matrix.indptr.tolist()}
            for name,matrix in matrices.items()}


def verify(directory):
    host();directory=local(directory);context=identity()
    context['source_sha256'].update({p:hashlib.sha256((ROOT/p).read_text(encoding='utf-8').encode()).hexdigest() for p in SOURCES})
    directory.mkdir(parents=True,exist_ok=False)
    report={'format':'ain-train-preprocessing-drill-v1','checked_at':datetime.now(timezone.utc).isoformat(),
            'case_id':directory.name,**context,'passed':False,'checks':{},'synthetic_only':True,
            'primary_database_accessed':False,'frozen_experiments_accessed':False,
            'predictive_model_trained':False,'deployment_performed':False,'production_ready':False}
    try:
        def retain(name,value):
            data=(json.dumps(value,indent=2,allow_nan=False)+'\n').encode()
            (directory/name).write_bytes(data);return hashlib.sha256(data).hexdigest()
        prepared=fixture();report['prepared_sha256']=retain('synthetic-prepared.json',prepared)
        fitted=fit_training_preprocessor(prepared)
        report['preprocessing_sha256']=retain('preprocessing-state.json',fitted['report'])
        report['matrix_sha256']=retain('sparse-matrices.json',csr_records(fitted['matrices']))
        changed=copy.deepcopy(prepared)
        for name in ('validation','test'):
            for row in changed['partitions'][name]:row['X'].update(origin='DDD',temperature_c=999);row['y']=999
        changed_fit=fit_training_preprocessor(changed)
        metadata=fitted['report'];state=metadata['fit_state']
        report['checks']={
            'fit_partition_is_training':state['fit_partition']=='train' and len(state['training_query_ids'])==2,
            'numeric_mean_training_only':state['numeric_mean']==[25.0,10.0],
            'numeric_scale_training_only':state['numeric_scale']==[5.0,5.0],
            'categories_training_only':state['origin_categories']==['AAA'],
            'unseen_future_origins_reported':metadata['matrices']['validation']['unknown_origin_count']==metadata['matrices']['test']['unknown_origin_count']==1,
            'unknown_origins_do_not_expand_schema':all(matrix.shape[1]==3 for matrix in fitted['matrices'].values()),
            'future_mutation_does_not_change_fit':metadata['fit_state_sha256']==changed_fit['report']['fit_state_sha256'],
            'future_mutation_does_not_change_training_matrix':(fitted['matrices']['train']!=changed_fit['matrices']['train']).nnz==0,
            'finite_sparse_outputs':all(np.isfinite(matrix.data).all() for matrix in fitted['matrices'].values()),
            'source_unchanged':all(hashlib.sha256((ROOT/p).read_text(encoding='utf-8').encode()).hexdigest()==h for p,h in context['source_sha256'].items())}
        report.update(preprocessing=metadata,counts=prepared['counts'])
        report['passed']=all(report['checks'].values())
    except Exception:report['error']='synthetic_train_preprocessing_check_failed'
    (directory/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    return report


if __name__=='__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    result=verify(ROOT/'.local/train-preprocessing'/uuid4().hex)
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['passed'] else 2)
