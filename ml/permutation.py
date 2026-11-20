"""Offline grouped permutation diagnostic of a frozen model; never trains or opens May."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import joblib
import numpy as np
from sklearn.metrics import log_loss, roc_auc_score, brier_score_loss
from threadpoolctl import threadpool_limits
from ml.prepare_dataset import FEATURES, TARGET
from ml.train_baseline import sha256
from ml.train_v2 import load_split
from services.api.diagnostics import load_diagnostics, REPORT
from services.api.paths import ROOT

PROTOCOL = ROOT/'ml/importance_protocol.json'
PROTOCOL_SHA256 = '3b1b1da7d092a05007a77a2864e1ab4c52bf669db610cba83098e1cf7788d04c'


def scores(y, probabilities):
    probabilities=np.asarray(probabilities)
    if probabilities.shape != (len(y),) or not np.isfinite(probabilities).all() or np.any((probabilities<0)|(probabilities>1)):
        raise ValueError('Invalid probability output')
    return {'log_loss':float(log_loss(y,probabilities,labels=[0,1])),
        'roc_auc':float(roc_auc_score(y,probabilities)),
        'brier_score':float(brier_score_loss(y,probabilities))}


def permutation_results(model, frame, groups, repeats=3, seed=20261120):
    if repeats != 3 or len(frame)<2 or set(frame[TARGET].unique()) != {0,1}:
        raise ValueError('Diagnostic needs three repeats and both target classes')
    used=[column for columns in groups.values() for column in columns]
    if not used or len(set(used))!=len(used) or any(column not in FEATURES for column in used):
        raise ValueError('Groups must contain distinct allowlisted input columns')
    x=frame[FEATURES].copy(deep=True);y=frame[TARGET]
    rng=np.random.default_rng(seed)
    permutations=[rng.permutation(len(x)) for _ in range(repeats)]
    with threadpool_limits(limits=2):
        baseline=scores(y,model.predict_proba(x)[:,1])
        results=[]
        for name,columns in groups.items():
            runs=[]
            for order in permutations:
                shuffled=x.copy(deep=True)
                shuffled.loc[:,columns]=x.iloc[order][columns].to_numpy()
                measured=scores(y,model.predict_proba(shuffled)[:,1])
                runs.append({'log_loss_increase':measured['log_loss']-baseline['log_loss'],
                    'roc_auc_decrease':baseline['roc_auc']-measured['roc_auc'],
                    'brier_increase':measured['brier_score']-baseline['brier_score']})
            results.append({'group':name,'columns':columns,'repeats':runs,
                'mean':{key:float(np.mean([row[key] for row in runs])) for key in runs[0]},
                'repeat_std':{key:float(np.std([row[key] for row in runs],ddof=1)) for key in runs[0]}})
    return {'baseline':baseline,'groups':results}


def evaluate(dataset, model_directory, output):
    output=Path(output).resolve()
    if not output.is_relative_to((ROOT/'.local').resolve()) or output==(ROOT/'.local').resolve() or output.exists():
        raise ValueError('Choose a new private experiment directory under .local')
    protocol_text=PROTOCOL.read_text(encoding='utf-8')
    if hashlib.sha256(protocol_text.encode()).hexdigest()!=PROTOCOL_SHA256:
        raise ValueError('Diagnostic protocol changed; create a new experiment')
    protocol=json.loads(protocol_text)
    if protocol['split']!='validation' or protocol['period']!='2025-04' or protocol['sample_records']!=10000 or protocol['repeats']!=3:
        raise ValueError('Unsupported diagnostic protocol')
    load_diagnostics()  # Checks the frozen public model report before deserialization.
    report=json.loads((ROOT/REPORT).read_text(encoding='utf-8'))
    dataset,model_directory=Path(dataset),Path(model_directory)
    artifact=model_directory/'model.joblib'
    if sha256(artifact)!=report['artifact_sha256']:
        raise ValueError('Frozen model hash mismatch')
    # The pinned report supplies the exact split byte hash/count, independent of mutable private manifests.
    manifest={'splits':{'validation':{'sha256':report['dataset_hashes']['validation'],
        'eligible_records':report['validation']['model']['records']}}}
    output.mkdir(parents=True)
    started=time.perf_counter()
    (output/'started.json').write_text(json.dumps({'protocol':protocol,'started_at':datetime.now(timezone.utc).isoformat()},indent=2)+'\n',encoding='utf-8')
    frame=load_split(dataset,'validation',manifest,report['protocol'])
    rng=np.random.default_rng(protocol['seed'])
    positions=np.sort(rng.choice(len(frame),size=protocol['sample_records'],replace=False))
    sample=frame.iloc[positions].copy()
    sample_hash=hashlib.sha256('\n'.join(sample['record_key']).encode()).hexdigest()
    # Only the locally created, pinned artifact is eligible for trusted joblib loading.
    model=joblib.load(artifact)
    results=permutation_results(model,sample,protocol['groups'],protocol['repeats'],protocol['seed'])
    if sha256(artifact)!=report['artifact_sha256'] or sha256(dataset/'validation.csv')!=report['dataset_hashes']['validation']:
        raise ValueError('Source changed during diagnostic')
    result={'format':'ain-permutation-v1','checked_at':datetime.now(timezone.utc).isoformat(),
        'model_version':'delay-v2','artifact_sha256':report['artifact_sha256'],
        'validation_sha256':report['dataset_hashes']['validation'],
        'protocol':protocol,'protocol_sha256':hashlib.sha256(PROTOCOL.read_text(encoding='utf-8').encode()).hexdigest(),
        'validation_population':len(frame),'sample_records':len(sample),'sample_key_sha256':sample_hash,
        **results,'elapsed_seconds':round(time.perf_counter()-started,3),
        'source_hashes_unchanged':True,'research_only':True,'production_ready':False,
        'limitations':['Post-hoc April validation subset, not a new untouched holdout or full-population estimate.',
            'Permutation measures this frozen model\'s performance reliance, not causality or a reason for one flight.',
            'Correlated inputs can share or mask importance; independent shuffling can create implausible schedules/routes.',
            'Departure hour and minute are shuffled together; derived cyclic pairs are recomputed by the frozen pipeline.',
            'Three-repeat sample standard deviation measures shuffle variation only, not a confidence interval or sampling uncertainty.',
            'Negative importance is possible. No model, feature, threshold or calibration selection is performed.',
            'US domestic history only; no UAE validation or operational approval.']}
    (output/'report.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,default=ROOT/'.local/datasets/bts-jan-may-2025-v2')
    parser.add_argument('--model',type=Path,default=ROOT/'.local/models/delay-v2')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=evaluate(args.dataset,args.model,args.output)
    print(json.dumps({'sample_records':result['sample_records'],'baseline':result['baseline'],
        'groups':[{k:row[k] for k in ['group','mean','repeat_std']} for row in result['groups']],
        'elapsed_seconds':result['elapsed_seconds']},indent=2))
