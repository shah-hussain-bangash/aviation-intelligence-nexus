"""Training/validation-only ridge selection; no test input or predictive deployment."""
import numpy as np
from sklearn.linear_model import Ridge

from ml.train_preprocessing import fit_training_preprocessor, signature
from ml.temporal_preparation import X_COLUMNS, number
from pipelines.time_safe_features import identifier, require

ALPHAS = [0.1,1.0,10.0]


def protocol(boundaries, *, experiment_id, scope):
    require(identifier(experiment_id),'invalid_experiment_identity')
    return {'format':'ain-validation-regression-protocol-v1','experiment_id':experiment_id,
            'source_scope':scope,'boundaries':dict(boundaries),'feature_columns':list(X_COLUMNS),
            'target':'arrival_delay_minutes','alpha_grid':list(ALPHAS),'selection_metric':'validation_mae',
            'tie_break':'smaller_alpha','baseline':'training_median','solver':'lsqr',
            'tol':1e-8,'max_iter':1000,'minimum_training_rows':3,'minimum_validation_rows':2,
            'test_policy':'not_accepted_or_evaluated','production_approval':False}


def metrics(target,prediction):
    residual=target-prediction
    result={'mae':float(np.mean(np.abs(residual))),'rmse':float(np.sqrt(np.mean(residual**2))),
            'records':int(len(target))}
    require(all(np.isfinite(result[k]) for k in ('mae','rmse')),'nonfinite_regression_metrics')
    return result


def select_regression(development, declared_protocol):
    # Refuse test rows before preparation validation/preprocessor access can read them.
    require(type(development) is dict and type(development.get('partitions')) is dict,'development_preparation_required')
    require(set(development)=={'format','source_scope','boundaries','feature_columns','target','partitions','excluded','counts','training_performed','production_ready'},'unexpected_development_fields')
    require(set(development['partitions'])=={'train','validation','test'},'unexpected_development_partitions')
    require(development['partitions'].get('test')==[],'test_partition_not_accepted')
    require(type(declared_protocol) is dict and identifier(declared_protocol.get('experiment_id')),'explicit_protocol_required')
    expected=protocol(development['boundaries'],experiment_id=declared_protocol['experiment_id'],scope=development['source_scope'])
    require(declared_protocol==expected,'unsupported_or_changed_protocol')
    require(all(number(alpha) and alpha>0 for alpha in declared_protocol['alpha_grid']),'invalid_alpha_grid')
    train=development['partitions']['train'];validation=development['partitions']['validation']
    require(len(train)>=3 and len(validation)>=2,'development_cohort_too_small')
    fitted=fit_training_preprocessor(development)
    x_train=fitted['matrices']['train'];x_validation=fitted['matrices']['validation']
    y_train=np.asarray([row['y'] for row in train],dtype=np.float64)
    y_validation=np.asarray([row['y'] for row in validation],dtype=np.float64)
    candidates=[]
    try:
        with np.errstate(over='raise',invalid='raise',divide='raise'):
            require(np.ptp(y_train)>0,'training_target_variance_required')
            baseline_value=float(np.median(y_train))
            baseline=metrics(y_validation,np.full(len(y_validation),baseline_value))
            for alpha in declared_protocol['alpha_grid']:
                model=Ridge(alpha=alpha,solver='lsqr',tol=declared_protocol['tol'],max_iter=declared_protocol['max_iter'])
                model.fit(x_train,y_train)
                prediction=model.predict(x_validation)
                require(np.isfinite(prediction).all() and np.isfinite(model.coef_).all() and np.isfinite(model.intercept_),'nonfinite_regression_model')
                candidates.append({'alpha':alpha,'validation':metrics(y_validation,prediction),
                                   'coefficients':model.coef_.tolist(),'intercept':float(model.intercept_),
                                   'solver_iterations':model.n_iter_.tolist()})
    except (FloatingPointError,OverflowError):
        raise ValueError('regression_numerical_failure') from None
    winner=min(candidates,key=lambda row:(row['validation']['mae'],row['alpha']))
    selected={'alpha':winner['alpha'],'coefficients':winner['coefficients'],'intercept':winner['intercept'],
              'output_columns':fitted['report']['fit_state']['output_columns'],
              'preprocessing_state_sha256':fitted['report']['fit_state_sha256']}
    return {'format':'ain-validation-regression-selection-v1','source_scope':development['source_scope'],
            'experiment_id':declared_protocol['experiment_id'],'protocol_sha256':signature(declared_protocol),
            'development_sha256':signature(development),'preprocessing':fitted['report'],
            'training_records':len(train),'validation_records':len(validation),
            'baseline':{'value':baseline_value,'validation':baseline},'candidates':candidates,
            'selected':selected,'selected_state_sha256':signature(selected),
            'beats_training_median_on_validation':winner['validation']['mae']<baseline['mae'],
            'predictive_models_fitted':len(candidates),'test_evaluated':False,
            'source_authenticated':False,'production_ready':False}
