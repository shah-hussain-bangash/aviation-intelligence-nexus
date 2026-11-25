"""One local attempt to score an explicitly frozen synthetic selection; no fitting."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import re
import stat
from uuid import uuid4

import numpy as np
from scipy.sparse import csr_matrix

from ml.regression_selection import metrics, protocol as selection_protocol
from ml.temporal_preparation import LABEL_FIELDS, feature_time, number
from ml.train_preprocessing import signature, validate as validate_development
from pipelines.synthetic_ingestion import host,local
from pipelines.time_safe_features import airport,identifier,require,timestamp

MAX_BYTES=8*1024*1024
MAX_ROWS=10_000
HASH_FIELDS={'protocol_sha256','selection_sha256','features_sha256','labels_sha256'}


def read_json(path):
    path=local(path)
    before=path.stat();require(stat.S_ISREG(before.st_mode) and 0<before.st_size<=MAX_BYTES,'bounded_json_required')
    with path.open('rb') as stream:data=stream.read(MAX_BYTES+1)
    after=path.stat()
    require(len(data)==before.st_size and (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)==(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns),'artifact_changed')
    def unique(pairs):
        result={}
        for key,value in pairs:
            require(key not in result,'duplicate_json_key');result[key]=value
        return result
    def nonfinite(value):raise ValueError('nonfinite_json')
    return json.loads(data.decode('utf-8'),object_pairs_hook=unique,parse_constant=nonfinite),hashlib.sha256(data).hexdigest()


def validate_freeze(policy,protocol,selection):
    require(type(policy) is dict and set(policy)==HASH_FIELDS|{'format','source_scope','attempt_policy'},'explicit_evaluation_policy_required')
    require(policy['format']=='ain-synthetic-holdout-policy-v1' and policy['source_scope']=='synthetic' and policy['attempt_policy']=='one_local_attempt_no_reset','unsupported_evaluation_policy')
    require(all(isinstance(policy[key],str) and re.fullmatch('[0-9a-f]{64}',policy[key]) for key in HASH_FIELDS),'invalid_artifact_pin')
    require(protocol['format']=='ain-validation-regression-protocol-v1' and protocol['source_scope']=='synthetic' and protocol['test_policy']=='not_accepted_or_evaluated','unsupported_selection_protocol')
    require(protocol==selection_protocol(protocol['boundaries'],experiment_id=protocol['experiment_id'],scope='synthetic'),'changed_selection_protocol')
    require(selection['format']=='ain-validation-regression-selection-v1' and selection['source_scope']=='synthetic' and selection['test_evaluated'] is False and selection['production_ready'] is False,'unsupported_selection')
    require(signature(protocol)==selection['protocol_sha256'] and protocol['experiment_id']==selection['experiment_id'],'selection_protocol_binding_invalid')
    selected=selection['selected'];state=selection['preprocessing']['fit_state']
    require(signature(selected)==selection['selected_state_sha256'] and signature(state)==selected['preprocessing_state_sha256']==selection['preprocessing']['fit_state_sha256'],'selected_state_binding_invalid')
    candidates=selection['candidates'];require(type(candidates) is list and len(candidates)==3,'candidate_record_required')
    require([row['alpha'] for row in candidates]==protocol['alpha_grid'] and selection['predictive_models_fitted']==3,'candidate_grid_mismatch')
    require(all(number(row['validation'][metric]) and row['validation'][metric]>=0 for row in candidates for metric in ('mae','rmse')),'invalid_frozen_validation_metrics')
    winner=min(candidates,key=lambda row:(row['validation']['mae'],row['alpha']))
    require(selected['alpha']==winner['alpha'] and selected['coefficients']==winner['coefficients'] and selected['intercept']==winner['intercept'],'selected_candidate_mismatch')
    origins=state['origin_categories']
    require(type(origins) is list and 1<=len(origins)<=1000 and all(airport(origin) for origin in origins) and len(set(origins))==len(origins),'invalid_frozen_categories')
    require(state['fit_partition']=='train' and state['unknown_origin_policy']=='all_zero_one_hot','unsupported_frozen_preprocessing_policy')
    expected_columns=['origin__origin_'+origin for origin in origins]+['numeric__temperature_c','numeric__wind_knots']
    require(state['numeric_columns']==['temperature_c','wind_knots'] and state['output_columns']==selected['output_columns']==expected_columns,'unsupported_frozen_feature_layout')
    require(len(selected['coefficients'])==len(expected_columns) and all(number(v) for v in selected['coefficients']) and number(selected['intercept']),'invalid_frozen_coefficients')
    require(len(state['numeric_mean'])==len(state['numeric_scale'])==2 and all(number(v) for v in state['numeric_mean']) and all(number(v) and v>0 for v in state['numeric_scale']),'invalid_frozen_scaling')
    require(number(selection['baseline']['value']),'invalid_frozen_baseline')
    bounds=[timestamp(protocol['boundaries'][key]) for key in ('train_start','train_end','validation_end','test_end')]
    require(all(a<b for a,b in zip(bounds,bounds[1:])),'invalid_frozen_boundaries')
    return selected,state,bounds


def evaluate_once(directory):
    result={'format':'ain-synthetic-holdout-evaluation-v1','state':'refused','claim_consumed':False,
            'test_evaluated':False,'source_scope':'synthetic','source_authenticated':False,
            'model_refitted':False,'deployment_performed':False,'production_ready':False}
    try:
        host();directory=local(directory)
        policy,policy_hash=read_json(directory/'holdout-policy.json')
        protocol,protocol_hash=read_json(directory/'registered-protocol.json')
        selection,selection_hash=read_json(directory/'frozen-selection.json')
        selected,state,bounds=validate_freeze(policy,protocol,selection)
        require(protocol_hash==policy['protocol_sha256'] and selection_hash==policy['selection_sha256'],'frozen_artifact_identity_mismatch')
        development,development_file_hash=read_json(directory/'synthetic-development.json')
        require(type(development) is dict and type(development.get('partitions')) is dict and development['partitions'].get('test')==[],'development_test_rows_not_accepted')
        require(signature(development)==selection['development_sha256'],'development_identity_mismatch')
        validate_development(development)
        development_ids={row['query_id'] for rows in development['partitions'].values() for row in rows}
        require(state['training_query_ids']==[row['query_id'] for row in development['partitions']['train']],'training_identity_binding_invalid')
        claim_file=local(directory/'holdout-attempt.json');output=local(directory/'holdout-evaluation.json')
        require(not output.exists(),'evaluation_result_already_exists')
        claim={'format':'ain-synthetic-holdout-attempt-v1','attempt_id':uuid4().hex,
               'started_at':datetime.now(timezone.utc).isoformat(),'policy_sha256':policy_hash,'policy':policy}
        # Atomic exclusive creation happens before opening either holdout data file.
        with claim_file.open('x',encoding='utf-8',newline='\n') as stream:
            result.update(state='failed',claim_consumed=True,attempt_id=claim['attempt_id'],policy_sha256=policy_hash,
                          protocol_sha256=protocol_hash,selection_sha256=selection_hash)
            json.dump(claim,stream,indent=2)
    except Exception:
        result['error']='synthetic_evaluation_admission_refused'
        return result
    try:
        features,features_hash=read_json(directory/'holdout-features.json')
        labels,labels_hash=read_json(directory/'holdout-labels.json')
        require(features_hash==policy['features_sha256'] and labels_hash==policy['labels_sha256'],'holdout_identity_mismatch')
        require(type(features) is list and type(labels) is list and 2<=len(features)==len(labels)<=MAX_ROWS,'complete_bounded_holdout_required')
        targets={}
        for row in labels:
            require(type(row) is dict and set(row)==LABEL_FIELDS and row['source_scope']=='synthetic','invalid_holdout_label')
            require(identifier(row['query_id']) and row['query_id'] not in targets and number(row['arrival_delay_minutes']),'invalid_holdout_label_identity')
            targets[row['query_id']]=row
        seen=set();data=[];indices=[];indptr=[0];truth=[];unknown=0
        origins={origin:index for index,origin in enumerate(state['origin_categories'])}
        for row in features:
            decision=feature_time(row,'synthetic');key=row['query_id']
            require(key not in seen and key not in development_ids and bounds[2]<=decision<bounds[3] and row['status']=='matched','invalid_holdout_feature_cohort')
            seen.add(key);require(key in targets,'missing_holdout_target')
            label=targets[key]
            require(decision<timestamp(label['label_available_at'])<=bounds[3],'immature_holdout_target')
            truth.append(label['arrival_delay_minutes'])
            if row['origin'] in origins:data.append(1.0);indices.append(origins[row['origin']])
            else:unknown+=1
            for index,column in enumerate(state['numeric_columns']):
                value=(row[column]-state['numeric_mean'][index])/state['numeric_scale'][index]
                require(number(value),'nonfinite_holdout_transform')
                if value!=0:data.append(value);indices.append(len(origins)+index)
            indptr.append(len(data))
        require(seen==set(targets),'orphan_holdout_target')
        matrix=csr_matrix((data,indices,indptr),shape=(len(features),len(selected['coefficients'])))
        with np.errstate(over='raise',invalid='raise',divide='raise'):
            prediction=np.asarray(matrix@np.asarray(selected['coefficients']))+selected['intercept']
            target=np.asarray(truth,dtype=np.float64)
            require(np.isfinite(prediction).all(),'nonfinite_holdout_prediction')
            selected_metrics=metrics(target,prediction)
            baseline_metrics=metrics(target,np.full(len(target),selection['baseline']['value']))
        for name,expected in [('holdout-policy.json',policy_hash),('registered-protocol.json',protocol_hash),
                              ('frozen-selection.json',selection_hash),('synthetic-development.json',development_file_hash),
                              ('holdout-features.json',features_hash),('holdout-labels.json',labels_hash)]:
            require(read_json(directory/name)[1]==expected,'evaluation_input_changed')
        result.update(state='evaluated',test_evaluated=True,features_sha256=features_hash,labels_sha256=labels_hash,
                      development_file_sha256=development_file_hash,development_ids_disjoint=True,
                      selected_state_sha256=selection['selected_state_sha256'],selected_metrics=selected_metrics,
                      baseline_metrics=baseline_metrics,unknown_origin_count=unknown,
                      prediction_sha256=signature(prediction.tolist()),query_ids_sha256=signature([row['query_id'] for row in features]))
    except Exception:result['error']='synthetic_evaluation_failed_attempt_consumed'
    result['completed_at']=datetime.now(timezone.utc).isoformat()
    try:
        with output.open('x',encoding='utf-8',newline='\n') as stream:json.dump(result,stream,indent=2,allow_nan=False)
    except Exception:result.update(state='failed',error='evaluation_receipt_write_failed_claim_retained')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('experiment')
    result=evaluate_once(parser.parse_args().experiment)
    print(json.dumps(result,indent=2));raise SystemExit(0 if result['state']=='evaluated' else 2)
