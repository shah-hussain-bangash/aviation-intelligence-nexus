"""Fit an explicit feature transformer on training rows only; no predictive model fitting."""
import hashlib
import json

import numpy as np
import pandas as pd
import sklearn
from scipy.sparse import csr_matrix
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from ml.temporal_preparation import MAX_ROWS, X_COLUMNS, number
from pipelines.time_safe_features import SCOPES, airport, identifier, require, timestamp

MAX_ORIGINS = 1000
ROW_FIELDS = {'query_id','decision_at','X','y','provenance'}
PROVENANCE_FIELDS = {'source_scope','weather_event_id','weather_observed_at','weather_available_at','label_available_at'}


def signature(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def validate(prepared):
    require(type(prepared) is dict and prepared.get('format')=='ain-temporal-preparation-v1','prepared_dataset_required')
    require(prepared.get('source_scope') in SCOPES and prepared.get('feature_columns')==list(X_COLUMNS),'unsupported_feature_contract')
    require(prepared.get('target')=='arrival_delay_minutes' and prepared.get('training_performed') is False and prepared.get('production_ready') is False,'unsupported_preparation_scope')
    names=('train','validation','test')
    require(type(prepared.get('partitions')) is dict and set(prepared['partitions'])==set(names),'invalid_partitions')
    boundaries=prepared['boundaries']
    require(set(boundaries)=={'train_start','train_end','validation_end','test_end'},'invalid_boundaries')
    times=[timestamp(boundaries[key]) for key in ('train_start','train_end','validation_end','test_end')]
    require(all(a<b for a,b in zip(times,times[1:])),'invalid_boundaries')
    seen=set()
    for index,name in enumerate(names):
        rows=prepared['partitions'][name]
        require(type(rows) is list and len(rows)<=MAX_ROWS,'bounded_partition_required')
        for row in rows:
            require(type(row) is dict and set(row)==ROW_FIELDS,'invalid_prepared_row')
            require(identifier(row['query_id']) and row['query_id'] not in seen,'duplicate_or_invalid_query')
            seen.add(row['query_id']);require(len(seen)<=MAX_ROWS,'dataset_limit_exceeded')
            decision=timestamp(row['decision_at'])
            require(times[index]<=decision<times[index+1],'row_outside_declared_split')
            x=row['X'];provenance=row['provenance']
            require(type(x) is dict and set(x)==set(X_COLUMNS),'unexpected_model_input')
            require(airport(x['origin']) and number(x['temperature_c']) and number(x['wind_knots']) and x['wind_knots']>=0,'invalid_model_input')
            require(number(row['y']),'invalid_target')
            require(type(provenance) is dict and set(provenance)==PROVENANCE_FIELDS,'invalid_provenance')
            require(provenance['source_scope']==prepared['source_scope'] and identifier(provenance['weather_event_id']),'invalid_provenance')
            require(timestamp(provenance['weather_observed_at'])<=timestamp(provenance['weather_available_at'])<=decision,'feature_not_available_at_decision')
            require(decision<timestamp(provenance['label_available_at'])<=times[index+1],'immature_target')
    excluded=prepared.get('excluded')
    require(type(excluded) is list and len(excluded)+len(seen)<=MAX_ROWS,'invalid_exclusion_count')
    for row in excluded:
        require(type(row) is dict and set(row)=={'query_id','reason','source_scope'},'invalid_exclusion')
        require(identifier(row['query_id']) and row['query_id'] not in seen and row['source_scope']==prepared['source_scope'],'invalid_exclusion')
        require(row['reason'] in ('outside_experiment_window','weather_not_matched','missing_label','label_not_available_at_split_cutoff'),'invalid_exclusion')
        seen.add(row['query_id'])
    counts=prepared['counts']
    require(set(counts)=={'train','validation','test','excluded','input_features','input_labels'} and all(type(value) is int and value>=0 for value in counts.values()),'invalid_prepared_counts')
    require(all(counts[name]==len(prepared['partitions'][name]) for name in names),'invalid_prepared_counts')
    require(counts['excluded']==len(excluded) and counts['input_features']==len(seen) and sum(counts[n] for n in names)<=counts['input_labels']<=counts['input_features'],'invalid_prepared_counts')
    require(prepared['partitions']['train'],'nonempty_training_split_required')


def fit_training_preprocessor(prepared):
    validate(prepared)
    partitions=prepared['partitions']
    origins=sorted({row['X']['origin'] for row in partitions['train']})
    require(len(origins)<=MAX_ORIGINS,'training_origin_limit_exceeded')
    transformer=ColumnTransformer([
        ('origin',OneHotEncoder(handle_unknown='ignore',sparse_output=True),['origin']),
        ('numeric',StandardScaler(),['temperature_c','wind_knots'])],remainder='drop',sparse_threshold=1.0)
    frame=lambda rows:pd.DataFrame([row['X'] for row in rows],columns=list(X_COLUMNS))
    try:
        with np.errstate(over='raise',invalid='raise',divide='raise'):
            transformer.fit(frame(partitions['train']))
            scaler=transformer.named_transformers_['numeric']
            require(all(np.isfinite(values).all() for values in (scaler.mean_,scaler.var_,scaler.scale_)),'nonfinite_preprocessor_state')
            columns=transformer.get_feature_names_out().tolist()
            matrices={name:csr_matrix(transformer.transform(frame(rows))) if rows else csr_matrix((0,len(columns)),dtype=np.float64)
                      for name,rows in partitions.items()}
            require(all(np.isfinite(matrix.data).all() for matrix in matrices.values()),'nonfinite_transformed_features')
    except (FloatingPointError,OverflowError):
        raise ValueError('preprocessing_numerical_failure') from None
    state={'fit_partition':'train','training_query_ids':[row['query_id'] for row in partitions['train']],
           'training_feature_sha256':signature([row['X'] for row in partitions['train']]),
           'origin_categories':transformer.named_transformers_['origin'].categories_[0].tolist(),
           'numeric_columns':['temperature_c','wind_knots'],'numeric_mean':scaler.mean_.tolist(),
           'numeric_variance':scaler.var_.tolist(),'numeric_scale':scaler.scale_.tolist(),
           'output_columns':columns,'unknown_origin_policy':'all_zero_one_hot'}
    report={'format':'ain-train-preprocessing-v1','source_scope':prepared['source_scope'],
            'prepared_input_sha256':signature(prepared),'fit_state':state,'fit_state_sha256':signature(state),
            'matrices':{name:{'rows':matrix.shape[0],'columns':matrix.shape[1],'nonzero_values':matrix.nnz,
                              'unknown_origin_count':sum(row['X']['origin'] not in origins for row in partitions[name])}
                        for name,matrix in matrices.items()},
            'software':{'scikit_learn':sklearn.__version__,'numpy':np.__version__,'pandas':pd.__version__},
            'preprocessor_fitted':True,'predictive_model_trained':False,'input_authenticated':False,
            'point_in_time_preparation_recomputed':False,'production_ready':False}
    return {'transformer':transformer,'matrices':matrices,'report':report}
