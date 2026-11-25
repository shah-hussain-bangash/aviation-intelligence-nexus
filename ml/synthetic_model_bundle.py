"""Portable JSON scoring state for the supported synthetic regressor; no deployment."""
import argparse
import hashlib
import json
import re

import numpy as np
from scipy.sparse import csr_matrix

from ml.evaluate_synthetic_holdout import read_json
from ml.synthetic_error_diagnostics import diagnostics
from ml.temporal_preparation import feature_time, number
from ml.train_preprocessing import signature
from pipelines.synthetic_ingestion import host, local
from pipelines.time_safe_features import airport, require

FIELDS={'format','source_scope','production_ready','evaluation_receipt_sha256','selection_sha256',
        'state','state_sha256'}
STATE_FIELDS={'origin_categories','numeric_columns','numeric_mean','numeric_scale','coefficients',
              'intercept','baseline','unknown_origin_policy','output_columns'}
MAX_SCORE_ROWS=1000


def validate_bundle(bundle):
    require(type(bundle) is dict and set(bundle)==FIELDS,'bundle_schema_invalid')
    require(bundle['format']=='ain-synthetic-model-bundle-v1' and bundle['source_scope']=='synthetic'
            and bundle['production_ready'] is False,'synthetic_bundle_required')
    require(all(type(bundle[k]) is str and re.fullmatch('[0-9a-f]{64}',bundle[k])
                for k in ('state_sha256','selection_sha256','evaluation_receipt_sha256')),'bundle_hash_invalid')
    state=bundle['state']
    require(type(state) is dict and set(state)==STATE_FIELDS and signature(state)==bundle['state_sha256'],'state_binding_invalid')
    origins=state['origin_categories']
    require(type(origins) is list and 1<=len(origins)<=1000 and all(airport(v) for v in origins)
            and len(set(origins))==len(origins),'invalid_categories')
    require(state['numeric_columns']==['temperature_c','wind_knots']
            and state['unknown_origin_policy']=='all_zero_one_hot','unsupported_transform')
    require(state['output_columns']==['origin__origin_'+v for v in origins]+['numeric__temperature_c','numeric__wind_knots'],'invalid_layout')
    for key in ('numeric_mean','numeric_scale'):
        require(type(state[key]) is list and len(state[key])==2 and all(number(v) for v in state[key]),'invalid_scaling')
    require(all(v>0 for v in state['numeric_scale']),'nonpositive_scale')
    require(type(state['coefficients']) is list and len(state['coefficients'])==len(origins)+2
            and all(number(v) for v in state['coefficients']) and number(state['intercept'])
            and number(state['baseline']),'invalid_coefficients')
    return state


def export_bundle(experiment, destination, *, receipt_sha256):
    host();experiment=local(experiment);destination=local(destination)
    require(not destination.is_relative_to(experiment),'export_must_be_outside_experiment')
    checked=diagnostics(experiment,receipt_sha256=receipt_sha256)
    require(checked['verified'],'completed_diagnostics_required')
    selection,digest=read_json(experiment/'frozen-selection.json')
    require(digest==checked['input_sha256']['frozen-selection.json'],'selection_changed')
    fitted=selection['preprocessing']['fit_state'];selected=selection['selected']
    state={key:fitted[key] for key in ('origin_categories','numeric_columns','numeric_mean','numeric_scale',
                                      'unknown_origin_policy','output_columns')}
    state.update(coefficients=selected['coefficients'],intercept=selected['intercept'],baseline=selection['baseline']['value'])
    bundle={'format':'ain-synthetic-model-bundle-v1','source_scope':'synthetic','production_ready':False,
            'evaluation_receipt_sha256':receipt_sha256,'selection_sha256':digest,
            'state':state,'state_sha256':signature(state)}
    validate_bundle(bundle)
    # Recheck all observed evidence before exporting. This is not a filesystem snapshot.
    require(all(read_json(experiment/name)[1]==h for name,h in checked['input_sha256'].items()),'evidence_changed')
    data=(json.dumps(bundle,indent=2,allow_nan=False)+'\n').encode('utf-8')
    with destination.open('xb') as stream:stream.write(data)
    return {'format':'ain-synthetic-model-export-v1','bundle_sha256':hashlib.sha256(data).hexdigest(),
            'state_sha256':bundle['state_sha256'],'evaluation_receipt_sha256':receipt_sha256,
            'source_scope':'synthetic','production_ready':False}


def score(bundle_path, features, *, bundle_sha256):
    host();require(type(bundle_sha256) is str and re.fullmatch('[0-9a-f]{64}',bundle_sha256),'explicit_bundle_pin_required')
    bundle,digest=read_json(bundle_path);require(digest==bundle_sha256,'bundle_identity_mismatch')
    state=validate_bundle(bundle)
    require(type(features) is list and 1<=len(features)<=MAX_SCORE_ROWS,'bounded_feature_list_required')
    origins={v:i for i,v in enumerate(state['origin_categories'])}
    data=[];indices=[];indptr=[0];seen=set();unknown=0
    for row in features:
        feature_time(row,'synthetic')
        require(row['status']=='matched' and row['query_id'] not in seen,'complete_unique_features_required')
        seen.add(row['query_id'])
        if row['origin'] in origins:data.append(1.0);indices.append(origins[row['origin']])
        else:unknown+=1
        for i,column in enumerate(state['numeric_columns']):
            scaled=(row[column]-state['numeric_mean'][i])/state['numeric_scale'][i]
            require(number(scaled),'nonfinite_transform')
            if scaled!=0:data.append(scaled);indices.append(len(origins)+i)
        indptr.append(len(data))
    with np.errstate(over='raise',invalid='raise',divide='raise'):
        matrix=csr_matrix((data,indices,indptr),shape=(len(features),len(state['coefficients'])))
        prediction=np.asarray(matrix@np.asarray(state['coefficients']))+state['intercept']
        require(np.isfinite(prediction).all(),'nonfinite_prediction')
    require(read_json(bundle_path)[1]==digest,'bundle_changed')
    return {'format':'ain-synthetic-model-scores-v1','source_scope':'synthetic','bundle_sha256':digest,
            'state_sha256':bundle['state_sha256'],'evaluation_receipt_sha256':bundle['evaluation_receipt_sha256'],
            'records':len(features),'unknown_origin_count':unknown,
            'predictions':[{'query_id':row['query_id'],'arrival_delay_minutes':float(value),
                            'baseline_minutes':state['baseline']} for row,value in zip(features,prediction)],
            'model_refitted':False,'production_ready':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);commands=parser.add_subparsers(dest='command',required=True)
    export=commands.add_parser('export');export.add_argument('experiment');export.add_argument('destination');export.add_argument('--receipt-sha256',required=True)
    scoring=commands.add_parser('score');scoring.add_argument('bundle');scoring.add_argument('features');scoring.add_argument('--bundle-sha256',required=True)
    args=parser.parse_args()
    try:
        if args.command=='export':result=export_bundle(args.experiment,args.destination,receipt_sha256=args.receipt_sha256)
        else:result=score(args.bundle,read_json(args.features)[0],bundle_sha256=args.bundle_sha256)
        print(json.dumps(result,indent=2,allow_nan=False))
    except Exception:
        print(json.dumps({'error':'synthetic_bundle_operation_refused','production_ready':False}));raise SystemExit(2)
