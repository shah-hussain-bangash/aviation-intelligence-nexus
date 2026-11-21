"""Offline full-April threshold counts for a frozen trusted model; never reads May."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import time
import joblib
import numpy as np
from threadpoolctl import threadpool_limits
from ml.prepare_dataset import FEATURES,TARGET
from ml.train_baseline import sha256
from ml.train_v2 import load_split
from services.api.diagnostics import load_diagnostics,REPORT
from services.api.paths import ROOT

PROTOCOL=ROOT/'ml/threshold_protocol.json'
PROTOCOL_SHA256='db5cef69999a445491cda6b34ad7eddfafa68a69ff9e949b068cc086060ab77d'


def threshold_counts(y,probabilities):
    y=np.asarray(y);p=np.asarray(probabilities)
    if y.ndim!=1 or len(y)<2 or set(y.tolist())!={0,1} or p.shape!=y.shape or not np.issubdtype(p.dtype,np.number) or not np.isfinite(p).all() or np.any((p<0)|(p>1)):
        raise ValueError('Expected binary labels and finite probabilities in [0,1]')
    positive=y==1;rows=[]
    for percent in range(101):
        alert=p>=percent/100;tp=int(np.count_nonzero(alert&positive));fp=int(np.count_nonzero(alert&~positive));fn=int(positive.sum())-tp;tn=len(y)-tp-fp-fn
        rows.append({'threshold_percent':percent,'tn':tn,'fp':fp,'fn':fn,'tp':tp})
    return rows


def evaluate(dataset,model_directory,output):
    output=Path(output).resolve()
    if not output.is_relative_to((ROOT/'.local').resolve()) or output==(ROOT/'.local').resolve() or output.exists():raise ValueError('Choose a new private output directory under .local')
    text=PROTOCOL.read_text(encoding='utf-8')
    if hashlib.sha256(text.encode()).hexdigest()!=PROTOCOL_SHA256:raise ValueError('Threshold protocol changed; create a new diagnostic')
    protocol=json.loads(text);load_diagnostics()
    report=json.loads((ROOT/REPORT).read_text(encoding='utf-8'));dataset=Path(dataset);artifact=Path(model_directory)/'model.joblib'
    if sha256(artifact)!=report['artifact_sha256']:raise ValueError('Frozen model identity mismatch')
    manifest={'splits':{'validation':{'sha256':report['dataset_hashes']['validation'],'eligible_records':report['validation']['model']['records']}}}
    output.mkdir(parents=True);started=time.perf_counter()
    (output/'started.json').write_text(json.dumps({'protocol_sha256':PROTOCOL_SHA256,'started_at':datetime.now(timezone.utc).isoformat(),'scope':protocol['policy']},indent=2)+'\n',encoding='utf-8')
    frame=load_split(dataset,'validation',manifest,report['protocol'])
    model=joblib.load(artifact)  # Only a pinned, locally created trusted artifact is eligible.
    with threadpool_limits(limits=2):probabilities=model.predict_proba(frame[FEATURES])[:,1]
    rows=threshold_counts(frame[TARGET],probabilities);fixed=int(round(report['threshold']*100))
    original=report['validation']['model']['confusion_matrix_labels_0_1'];at_fixed=rows[fixed]
    if [[at_fixed['tn'],at_fixed['fp']],[at_fixed['fn'],at_fixed['tp']]]!=original:raise ValueError('Frozen April confusion counts did not reproduce')
    if sha256(artifact)!=report['artifact_sha256'] or sha256(dataset/'validation.csv')!=report['dataset_hashes']['validation']:raise ValueError('Sources changed during scoring')
    result={'format':'ain-threshold-tradeoffs-v1','checked_at':datetime.now(timezone.utc).isoformat(),'protocol':protocol,'protocol_sha256':PROTOCOL_SHA256,
        'model_version':'delay-v2','period':'2025-04','records':len(frame),'positives':int(frame[TARGET].sum()),'frozen_threshold_percent':fixed,
        'artifact_sha256':report['artifact_sha256'],'validation_sha256':report['dataset_hashes']['validation'],
        'probabilities_sha256':hashlib.sha256(np.asarray(probabilities,dtype='<f8').tobytes()).hexdigest(),'rows':rows,
        'elapsed_seconds':round(time.perf_counter()-started,3),'source_hashes_unchanged':True,'frozen_counts_reproduced':True,'research_only':True,'production_ready':False,
        'limitations':['April already selected the model and demonstration threshold; this is post-hoc validation exploration, not a new holdout estimate.',
            'No May outcomes are read, no model is fitted and no deployed threshold changes.',
            'Hypothetical error costs are user assumptions, not measured airline money, savings or operational benefit; all other costs are excluded.',
            'Review capacity is a proportion of this historical population, not a staffed queue, staffing estimate or future workload forecast.',
            'Alerts at nearby thresholds are dependent; no confidence intervals, significance tests, prospective validation or UAE transfer is established.',
            'Probabilities have limited calibration. This tool neither calibrates them nor recommends an operational threshold.']}
    (output/'report.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8');return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--dataset',type=Path,required=True);parser.add_argument('--model',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();r=evaluate(args.dataset,args.model,args.output)
    print(json.dumps({k:r[k] for k in ['records','positives','frozen_threshold_percent','elapsed_seconds','frozen_counts_reproduced','source_hashes_unchanged']},indent=2))
