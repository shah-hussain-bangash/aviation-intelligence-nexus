"""Offline positive-delay regression with read-only SQL and a frozen May boundary."""
import argparse
from contextlib import closing
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import platform
import sqlite3
import time
import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer,OrdinalEncoder
from threadpoolctl import threadpool_limits
from ml.features_v2 import time_features

ROOT=Path(__file__).resolve().parents[1]
PROTOCOL=ROOT/'ml/duration_protocol.json'
PROTOCOL_SHA256='814b217e92070cb990f9239804fdca39c768e6a1849f5653fac74c1c36b473f7'
FEATURES=['carrier','origin','destination','scheduled_departure_hour','scheduled_departure_minute','day_of_week']
TARGET='positive_delay_minutes'
ERROR_LABELS=['below -60','-60 to below -15','-15 to below 0','0 to below 15','15 to below 60','60 and above']
QUERY='''SELECT source_record_id AS record_key,flight_date,carrier,origin,destination,scheduled_departure,arrival_delay_minutes
 FROM flights WHERE source=? AND flight_date>=? AND flight_date<? AND cancelled=0 AND diverted=0
 AND arrival_delay_minutes IS NOT NULL ORDER BY flight_date,source_record_id'''


def digest(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def load_protocol():
    text=PROTOCOL.read_text(encoding='utf-8')
    if hashlib.sha256(text.encode()).hexdigest()!=PROTOCOL_SHA256:raise ValueError('Frozen duration protocol changed; create a new experiment')
    return json.loads(text)


def read_frame(db,bounds,source):
    raw=pd.read_sql_query(QUERY,db,params=[source,*bounds])
    if raw.empty or raw.isna().any().any() or raw.record_key.duplicated().any():raise ValueError('Missing or duplicate eligible duration rows')
    dates=pd.to_datetime(raw.flight_date,format='%Y-%m-%d',errors='raise')
    if not ((dates>=pd.Timestamp(bounds[0]))&(dates<pd.Timestamp(bounds[1]))).all():raise ValueError('Duration temporal scope mismatch')
    for key,pattern in [('carrier',r'[A-Z0-9]{2,3}'),('origin',r'[A-Z]{3}'),('destination',r'[A-Z]{3}')]:
        if not raw[key].str.fullmatch(pattern).all():raise ValueError('Invalid schedule vocabulary')
    schedule=raw.scheduled_departure.astype(str)
    if not schedule.str.fullmatch(r'(?:[01][0-9]|2[0-3])[0-5][0-9]|2400').all():raise ValueError('Invalid scheduled departure')
    values=raw.arrival_delay_minutes.to_numpy(dtype=float)
    if not np.isfinite(values).all():raise ValueError('Invalid duration outcomes')
    frame=raw[['record_key','flight_date','carrier','origin','destination']].copy()
    frame['scheduled_departure_hour']=schedule.str[:2].astype(int);frame['scheduled_departure_minute']=schedule.str[2:].astype(int);frame['day_of_week']=dates.dt.day_of_week+1;frame[TARGET]=np.maximum(0,values)
    return frame


def build_model(protocol):
    if protocol['features']!=FEATURES:raise ValueError('Only frozen predeparture schedule inputs are allowed')
    transform=ColumnTransformer([('categories',OrdinalEncoder(handle_unknown='use_encoded_value',unknown_value=-1,encoded_missing_value=-1,max_categories=200),FEATURES[:3]),
        ('time',FunctionTransformer(time_features,validate=False),FEATURES[3:])],remainder='drop')
    return Pipeline([('features',transform),('regressor',HistGradientBoostingRegressor(**protocol['model'],categorical_features=[True]*3+[False]*4))])


def metrics(y,prediction):
    y=np.asarray(y,dtype=float);p=np.asarray(prediction,dtype=float)
    if y.ndim!=1 or y.size==0 or y.shape!=p.shape or not np.isfinite(y).all() or not np.isfinite(p).all() or np.any(y<0) or np.any(p<0):raise ValueError('Expected finite nonnegative duration observations and estimates')
    error=p-y;absolute=np.abs(error);sse=float(np.square(error).sum());sst=float(np.square(y-y.mean()).sum())
    return {'records':len(y),'mae':float(absolute.mean()),'rmse':float(np.sqrt(sse/len(y))),'r2':1-sse/sst if sst else None,'mean_error':float(error.mean()),
        'p50_absolute_error':float(np.quantile(absolute,.5)),'p90_absolute_error':float(np.quantile(absolute,.9)),'p95_absolute_error':float(np.quantile(absolute,.95)),
        'sum_absolute_error':float(absolute.sum()),'sum_squared_error':sse,'sum_error':float(error.sum())}


def evaluate_frame(model,frame,baselines):
    y=frame[TARGET].to_numpy(dtype=float)
    with threadpool_limits(limits=4):p=np.maximum(0,model.predict(frame[FEATURES]))
    model_metrics=metrics(y,p);tail=y>=60
    return {'target_summary':{'records':len(y),'mean':float(y.mean()),'median':float(np.median(y)),'max':float(y.max()),'zero_records':int(np.count_nonzero(y==0)),'sum_squared_deviation':float(np.square(y-y.mean()).sum())},
        'model':model_metrics,'training_mean_baseline':metrics(y,np.full(len(y),baselines['mean'])),'training_median_baseline':metrics(y,np.full(len(y),baselines['median'])),
        'residual_histogram':{'sign':'actual minus predicted; positive means underprediction','labels':ERROR_LABELS,'counts':np.histogram(y-p,[-np.inf,-60,-15,0,15,60,np.inf])[0].tolist()},
        'observed_60_plus':{'records':int(tail.sum()),'model_mae':float(np.abs(p[tail]-y[tail]).mean()) if tail.any() else None,'model_mean_error':float((p[tail]-y[tail]).mean()) if tail.any() else None}}


def fit_evaluate(db,protocol,output):
    dataset={};started=time.perf_counter()
    def obtain(split):
        frame=read_frame(db,protocol['periods'][split],protocol['source'])
        if len(frame)!=protocol['expected_records'][split]:raise ValueError('Unexpected eligible duration population: '+split)
        path=output/(split+'.csv');frame.to_csv(path,index=False,lineterminator='\n');dataset[split]={'records':len(frame),'sha256':digest(path)};return frame
    training=obtain('train');baselines={'mean':float(training[TARGET].mean()),'median':float(training[TARGET].median())};model=build_model(protocol)
    print('Training fixed duration model on '+str(len(training))+' rows',flush=True)
    with threadpool_limits(limits=4):model.fit(training[FEATURES],training[TARGET])
    del training
    validation=obtain('validation');validation_result=evaluate_frame(model,validation,baselines);del validation
    artifact=output/'model.joblib';joblib.dump(model,artifact);artifact_sha=digest(artifact)
    freeze={'format':'ain-duration-freeze-v1','at':datetime.now(timezone.utc).isoformat(),'protocol_sha256':PROTOCOL_SHA256,'artifact_sha256':artifact_sha,'baselines':baselines,'datasets':dict(dataset),'validation':validation_result,'may_rows_read':False}
    (output/'freeze.json').write_text(json.dumps(freeze,indent=2,allow_nan=False)+'\n',encoding='utf-8');freeze_sha=digest(output/'freeze.json')
    print('Duration artifact and April evidence frozen before May query',flush=True)
    test=obtain('test');test_result=evaluate_frame(model,test,baselines);del test
    if digest(artifact)!=artifact_sha or digest(output/'freeze.json')!=freeze_sha or any(digest(output/(name+'.csv'))!=row['sha256'] for name,row in dataset.items()):raise ValueError('Duration experiment sources changed')
    checks={name:row['model']['rmse']<=.99*row['training_mean_baseline']['rmse'] for name,row in [('validation',validation_result),('test',test_result)]}
    return {'format':'ain-duration-regression-v1','experiment':protocol['experiment'],'checked_at':datetime.now(timezone.utc).isoformat(),'protocol':protocol,'protocol_sha256':PROTOCOL_SHA256,
        'artifact_sha256':artifact_sha,'freeze_sha256':freeze_sha,'datasets':dataset,'baselines':baselines,'validation':validation_result,'test':test_result,
        'research_check':{'criterion':'At least 1% lower RMSE than the constant training-mean baseline in both periods','by_period':checks,'passed':all(checks.values()),'operational_approval':False},
        'elapsed_seconds':round(time.perf_counter()-started,3),'versions':{'python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__,'sklearn':sklearn.__version__},
        'source_hashes_unchanged':True,'research_only':True,'production_ready':False,
        'limitations':['Historical US domestic schedules, not point-in-time predeparture snapshots or UAE airline validation.',
            'Target is nonnegative arrival-delay minutes conditional on a completed non-diverted flight with an observed outcome; cancellation/diversion risk is excluded.',
            'Earlier project experiments inspected this release. May is a frozen model-specific temporal comparison, not a globally untouched holdout.',
            'One fixed squared-error model targets conditional means. Lower RMSE can coexist with worse MAE than a median baseline; both are reported.',
            'Extreme delays are retained and can dominate RMSE. Tail errors and bias do not establish individual-flight reliability.',
            'No uncertainty intervals, causal effects, future-season validation, measured airline benefit or operational approval.',
            'Duration inference is not deployed. The existing delay-v2 probability model and threshold are unchanged.']}


def run(database,output):
    output=Path(output).resolve();database=Path(database).resolve()
    if not output.is_relative_to((ROOT/'.local').resolve()) or output==(ROOT/'.local').resolve() or output.exists():raise ValueError('Choose a new private duration experiment directory under .local')
    protocol=load_protocol()
    # Read-only URI fails without creating a missing database; one snapshot covers all splits.
    with closing(sqlite3.connect(database.as_uri()+'?mode=ro',uri=True,timeout=1)) as db:
        db.execute('PRAGMA query_only=ON');db.execute('PRAGMA temp_store=MEMORY');db.execute('BEGIN')
        imports=[dict(zip(['period','sha256','rows_inserted'],r)) for r in db.execute('SELECT period,sha256,rows_inserted FROM imports WHERE period>=? AND period<=? ORDER BY period,sha256',('2025-01','2025-05'))]
        if {r['period'] for r in imports}!={f'2025-{i:02}' for i in range(1,6)}:raise ValueError('Missing source archive lineage')
        output.mkdir(parents=True);(output/'started.json').write_text(json.dumps({'protocol':protocol,'protocol_sha256':PROTOCOL_SHA256,'started_at':datetime.now(timezone.utc).isoformat()},indent=2)+'\n',encoding='utf-8')
        result=fit_evaluate(db,protocol,output);result['source_imports']=imports
    (output/'report.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8');return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--database',type=Path,default=ROOT/'.local/ain.sqlite3');parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();r=run(args.database,args.output)
    print(json.dumps({'records':{k:v['records'] for k,v in r['datasets'].items()},'validation':r['validation']['model'],'test':r['test']['model'],'research_check':r['research_check'],'elapsed_seconds':r['elapsed_seconds']},indent=2))
