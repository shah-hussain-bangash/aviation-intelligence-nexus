"""Bounded point-in-time research split preparation; no training or frozen-data access."""
import math

from pipelines.time_safe_features import QUERY_FIELDS, SCOPES, airport, identifier, require, timestamp

FEATURE_FIELDS = QUERY_FIELDS | {'status','event_id','observed_at','available_at','age_seconds','temperature_c','wind_knots','max_age_seconds'}
LABEL_FIELDS = {'query_id','arrival_delay_minutes','label_available_at','source_scope'}
MAX_ROWS = 50_000
X_COLUMNS = ('origin','temperature_c','wind_knots')


def number(value):
    return type(value) in (int,float) and -1e308<=value<=1e308 and math.isfinite(value)


def feature_time(row, scope):
    require(type(row) is dict and set(row)==FEATURE_FIELDS,'invalid_feature_fields')
    require(row['source_scope']==scope,'source_scope_mismatch')
    require(identifier(row['query_id']) and airport(row['origin']),'invalid_feature_identity')
    decision=timestamp(row['decision_at'])
    require(type(row['max_age_seconds']) is int and 1<=row['max_age_seconds']<=86400,'invalid_feature_age_policy')
    require(row['status'] in ('matched','stale','unavailable'),'invalid_feature_status')
    if row['status']=='unavailable':
        require(all(row[key] is None for key in ('event_id','observed_at','available_at','age_seconds','temperature_c','wind_knots')),'invalid_unavailable_feature')
    else:
        observed,available=timestamp(row['observed_at']),timestamp(row['available_at'])
        require(observed<=available<=decision,'feature_not_available_at_decision')
        age=int((decision-observed).total_seconds())
        require(identifier(row['event_id']) and type(row['age_seconds']) is int and row['age_seconds']==age,'feature_provenance_mismatch')
        if row['status']=='matched':
            require(age<=row['max_age_seconds'] and number(row['temperature_c']) and number(row['wind_knots']) and row['wind_knots']>=0,'invalid_matched_feature')
        else:
            require(age>row['max_age_seconds'] and row['temperature_c'] is None and row['wind_knots'] is None,'invalid_stale_feature')
    return decision


def prepare_splits(features, labels, *, train_start, train_end, validation_end, test_end, scope):
    require(type(scope) is str and scope in SCOPES,'explicit_research_scope_required')
    boundaries=[timestamp(value) for value in (train_start,train_end,validation_end,test_end)]
    require(all(left<right for left,right in zip(boundaries,boundaries[1:])),'strict_chronological_boundaries_required')
    targets={}
    for count,row in enumerate(labels,1):
        require(count<=MAX_ROWS,'label_limit_exceeded')
        require(type(row) is dict and set(row)==LABEL_FIELDS,'invalid_label_fields')
        require(row['source_scope']==scope and identifier(row['query_id']),'invalid_label_identity_or_scope')
        require(row['query_id'] not in targets,'duplicate_label_identity')
        require(number(row['arrival_delay_minutes']),'invalid_label_value')
        targets[row['query_id']]=(dict(row),timestamp(row['label_available_at']))
    partitions={name:[] for name in ('train','validation','test')}
    excluded=[];seen=set()
    for count,row in enumerate(features,1):
        require(count<=MAX_ROWS,'feature_limit_exceeded')
        decision=feature_time(row,scope)
        key=row['query_id'];require(key not in seen,'duplicate_feature_identity');seen.add(key)
        target,available=targets.get(key,(None,None))
        if target is not None:require(available>decision,'label_not_after_decision')
        index=next((i for i in range(3) if boundaries[i]<=decision<boundaries[i+1]),None)
        reason=None
        if index is None:reason='outside_experiment_window'
        elif row['status']!='matched':reason='weather_not_matched'
        elif target is None:reason='missing_label'
        elif available>boundaries[index+1]:reason='label_not_available_at_split_cutoff'
        if reason:
            excluded.append({'query_id':key,'reason':reason,'source_scope':scope})
            continue
        name=('train','validation','test')[index]
        partitions[name].append({'query_id':key,'decision_at':row['decision_at'],
                                 'X':{column:row[column] for column in X_COLUMNS},
                                 'y':target['arrival_delay_minutes'],
                                 'provenance':{'source_scope':scope,'weather_event_id':row['event_id'],
                                               'weather_observed_at':row['observed_at'],'weather_available_at':row['available_at'],
                                               'label_available_at':target['label_available_at']}})
    require(set(targets)<=seen,'orphan_label_identity')
    for rows in partitions.values():rows.sort(key=lambda row:(row['decision_at'],row['query_id']))
    excluded.sort(key=lambda row:row['query_id'])
    return {'format':'ain-temporal-preparation-v1','source_scope':scope,
            'boundaries':dict(train_start=train_start,train_end=train_end,validation_end=validation_end,test_end=test_end),
            'feature_columns':list(X_COLUMNS),'target':'arrival_delay_minutes','partitions':partitions,
            'excluded':excluded,'counts':{**{name:len(rows) for name,rows in partitions.items()},'excluded':len(excluded),'input_features':len(seen),'input_labels':len(targets)},
            'training_performed':False,'production_ready':False}
