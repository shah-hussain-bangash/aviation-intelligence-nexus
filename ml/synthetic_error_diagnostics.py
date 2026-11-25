"""Read-only descriptive diagnostics for an already evaluated synthetic experiment."""
import argparse
import hashlib
import json
import re

import numpy as np
from scipy.sparse import csr_matrix

from ml.evaluate_synthetic_holdout import MAX_ROWS, read_json, validate_freeze
from ml.regression_selection import metrics
from ml.temporal_preparation import LABEL_FIELDS, feature_time, number
from ml.train_preprocessing import signature, validate
from pipelines.synthetic_ingestion import host, local
from pipelines.time_safe_features import identifier, require, timestamp

FILES=('holdout-evaluation.json','holdout-attempt.json','holdout-policy.json',
       'registered-protocol.json','frozen-selection.json','synthetic-development.json',
       'holdout-features.json','holdout-labels.json')


def diagnostics(directory, *, receipt_sha256):
    """Return aggregates only; never create an attempt, fit, select or write files."""
    result={'format':'ain-synthetic-error-diagnostics-v1','verified':False,
            'source_scope':'synthetic','read_only':True,'new_evaluation_attempt':False,
            'model_refitted':False,'source_authenticated':False,'production_ready':False}
    try:
        host();directory=local(directory)
        require(isinstance(receipt_sha256,str) and re.fullmatch('[0-9a-f]{64}',receipt_sha256),'receipt_pin_required')
        evaluation,receipt_hash=read_json(directory/FILES[0])
        require(receipt_hash==receipt_sha256,'receipt_identity_mismatch')
        require(evaluation['format']=='ain-synthetic-holdout-evaluation-v1' and evaluation['state']=='evaluated'
                and evaluation['test_evaluated'] is True and evaluation['claim_consumed'] is True
                and evaluation['source_scope']=='synthetic' and evaluation['model_refitted'] is False
                and evaluation['production_ready'] is False,'completed_synthetic_receipt_required')
        artifacts={FILES[0]:(evaluation,receipt_hash)}
        for name in FILES[1:]:artifacts[name]=read_json(directory/name)
        value=lambda name:artifacts[name][0]
        digest=lambda name:artifacts[name][1]
        claim=value('holdout-attempt.json');policy=value('holdout-policy.json')
        protocol=value('registered-protocol.json');selection=value('frozen-selection.json')
        selected,state,bounds=validate_freeze(policy,protocol,selection)
        require(claim['format']=='ain-synthetic-holdout-attempt-v1' and identifier(claim['attempt_id'])
                and claim['attempt_id']==evaluation['attempt_id'] and claim['policy']==policy
                and claim['policy_sha256']==evaluation['policy_sha256']==digest('holdout-policy.json'),'claim_binding_invalid')
        for name,key in [('registered-protocol.json','protocol_sha256'),('frozen-selection.json','selection_sha256'),
                         ('holdout-features.json','features_sha256'),('holdout-labels.json','labels_sha256')]:
            require(digest(name)==policy[key]==evaluation[key],'input_binding_invalid')
        development=value('synthetic-development.json')
        require(signature(development)==selection['development_sha256']
                and digest('synthetic-development.json')==evaluation['development_file_sha256'],'development_binding_invalid')
        validate(development)
        require(development['partitions']['test']==[] and evaluation['development_ids_disjoint'] is True,'development_test_rows_refused')
        require(state['training_query_ids']==[r['query_id'] for r in development['partitions']['train']],'training_binding_invalid')
        development_ids={r['query_id'] for rows in development['partitions'].values() for r in rows}
        features=value('holdout-features.json');labels=value('holdout-labels.json')
        require(type(features) is list and type(labels) is list and 2<=len(features)==len(labels)<=MAX_ROWS,'complete_cohort_required')
        targets={}
        for row in labels:
            require(type(row) is dict and set(row)==LABEL_FIELDS and row['source_scope']=='synthetic'
                    and identifier(row['query_id']) and row['query_id'] not in targets
                    and number(row['arrival_delay_minutes']),'invalid_label')
            targets[row['query_id']]=row
        seen=set();data=[];indices=[];indptr=[0];truth=[];known=[]
        origins={origin:index for index,origin in enumerate(state['origin_categories'])}
        for row in features:
            decision=feature_time(row,'synthetic');key=row['query_id']
            require(key not in seen and key not in development_ids and key in targets
                    and bounds[2]<=decision<bounds[3] and row['status']=='matched','invalid_cohort')
            seen.add(key);target=targets[key]
            require(decision<timestamp(target['label_available_at'])<=bounds[3],'immature_target')
            truth.append(target['arrival_delay_minutes']);known.append(row['origin'] in origins)
            if known[-1]:data.append(1.0);indices.append(origins[row['origin']])
            for index,column in enumerate(state['numeric_columns']):
                scaled=(row[column]-state['numeric_mean'][index])/state['numeric_scale'][index]
                require(number(scaled),'nonfinite_transform')
                if scaled!=0:data.append(scaled);indices.append(len(origins)+index)
            indptr.append(len(data))
        require(seen==set(targets),'orphan_target')
        matrix=csr_matrix((data,indices,indptr),shape=(len(features),len(selected['coefficients'])))
        with np.errstate(over='raise',invalid='raise',divide='raise'):
            prediction=np.asarray(matrix@np.asarray(selected['coefficients']))+selected['intercept']
            truth=np.asarray(truth,dtype=np.float64)
            baseline=np.full(len(truth),selection['baseline']['value'])
            require(signature(prediction.tolist())==evaluation['prediction_sha256']
                    and signature([r['query_id'] for r in features])==evaluation['query_ids_sha256']
                    and selection['selected_state_sha256']==evaluation['selected_state_sha256'],'prediction_binding_invalid')
            for key,pred in [('selected_metrics',prediction),('baseline_metrics',baseline)]:
                actual=metrics(truth,pred);recorded=evaluation[key]
                require(type(recorded) is dict and set(recorded)==set(actual) and type(recorded['records']) is int
                        and recorded['records']==actual['records'],'metric_count_mismatch')
                require(all(number(recorded[m]) and np.isclose(actual[m],recorded[m],rtol=1e-12,atol=1e-12)
                            for m in ('mae','rmse')),'metric_mismatch')
            require(type(evaluation['unknown_origin_count']) is int
                    and evaluation['unknown_origin_count']==known.count(False),'unknown_count_mismatch')

            def summarize(mask):
                count=int(mask.sum())
                if not count:return {'records':0,'selected':None,'baseline':None,'mean_prediction_minus_actual':None,'small_cohort':True}
                return {'records':count,'selected':metrics(truth[mask],prediction[mask]),
                        'baseline':metrics(truth[mask],baseline[mask]),
                        'mean_prediction_minus_actual':float(np.mean(prediction[mask]-truth[mask])),
                        'small_cohort':count<30}

            by_origin=[{'origin':origin,**summarize(np.asarray([r['origin']==origin for r in features]))}
                       for origin in sorted({r['origin'] for r in features})]
            by_category=[{'category':name,**summarize(np.asarray(known)==flag)}
                         for name,flag in [('known_origin',True),('unknown_origin',False)]]
            overall=summarize(np.ones(len(features),dtype=bool))
        # Reject observable changes during inspection; this is not a filesystem snapshot.
        require(all(read_json(directory/name)[1]==pair[1] for name,pair in artifacts.items()),'inputs_changed')
        result.update(verified=True,attempt_id=evaluation['attempt_id'],receipt_sha256=receipt_hash,
                      input_sha256={name:pair[1] for name,pair in artifacts.items()},overall=overall,
                      by_origin=by_origin,by_training_category=by_category,
                      interpretation='Descriptive synthetic diagnostics only; no model selection, significance, real-airline quality or deployment approval.')
    except Exception:result['error']='synthetic_diagnostics_refused'
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('experiment');parser.add_argument('--receipt-sha256',required=True)
    args=parser.parse_args();result=diagnostics(args.experiment,receipt_sha256=args.receipt_sha256)
    print(json.dumps(result,indent=2,allow_nan=False));raise SystemExit(0 if result['verified'] else 2)
