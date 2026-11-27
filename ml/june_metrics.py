"""Prespecified frozen-model metrics and whole-day cluster bootstrap; no fitting."""
import numpy as np
from ml.train_baseline import metrics
from ml.register_evaluation import require


def scores(y, probabilities, threshold):
    result=metrics(y,probabilities,threshold)
    result.pop('accuracy')  # Not part of this plan's metric inventory.
    result['confusion_matrix']=result.pop('confusion_matrix_labels_0_1')
    return result


def uncertainty(y,p,prior,dates,plan):
    y=np.asarray(y,dtype=float);p=np.asarray(p,dtype=float)
    _,groups=np.unique(np.asarray(dates),return_inverse=True)
    count=np.bincount(groups)
    require(len(count)>=2,'at_least_two_date_clusters_required')
    eps=np.finfo(np.float64).eps;q=np.clip(p,eps,1-eps);b=float(np.clip(prior,eps,1-eps))
    differences={
        'mean_log_loss_difference_model_minus_prior':-(y*np.log(q)+(1-y)*np.log1p(-q))+(y*np.log(b)+(1-y)*np.log1p(-b)),
        'mean_brier_difference_model_minus_prior':(p-y)**2-(prior-y)**2}
    rng=np.random.default_rng(plan['seed'])
    draws=rng.integers(0,len(count),size=(plan['replicates'],len(count)))
    denominator=count[draws].sum(axis=1)
    results={}
    for name,values in differences.items():
        sums=np.bincount(groups,weights=values)
        bootstrap=sums[draws].sum(axis=1)/denominator
        low,high=np.quantile(bootstrap,[.025,.975])
        results[name]={'point_estimate':float(values.mean()),'lower':float(low),'upper':float(high)}
    return {'method':plan['method'],'replicates':plan['replicates'],'seed':plan['seed'],
            'date_clusters':len(count),'interval':plan['interval'],'statistics':results,
            'interpretation':'Negative differences favour the frozen model; descriptive intervals only.',
            'significance_or_independence_claim':False,'limitations':plan['limitations']}


def summarize(frame,y,p,dates,registration):
    y=np.asarray(y,dtype=int);p=np.asarray(p,dtype=float)
    require(len(y)==len(p)==len(frame) and set(np.unique(y))=={0,1},'two_class_complete_evaluation_required')
    require(np.isfinite(p).all() and ((p>=0)&(p<=1)).all(),'finite_probability_required')
    threshold=registration['frozen_threshold'];prior=registration['constant_training_prior'];plan=registration['plan']
    baseline=np.full(len(y),prior,dtype=float)
    model=scores(y,p,threshold);reference=scores(y,baseline,threshold)
    criteria=plan['research_comparison']
    checks={'auc':model['roc_auc']>=criteria['min_auc'],
            'log_loss':model['log_loss']<=reference['log_loss']*criteria['max_log_loss_ratio_to_training_prior'],
            'brier':model['brier_score']<reference['brier_score']}
    cohorts={}
    for field in plan['cohort_diagnostics']['groups']:
        cohorts[field]=[]
        for value in sorted(frame[field].unique()):
            mask=(frame[field].to_numpy()==value);n=int(mask.sum());labels=y[mask]
            row={'value':str(value),'records':n,'positive_targets':int(labels.sum())}
            if n<plan['cohort_diagnostics']['minimum_eligible_rows'] or len(np.unique(labels))<2:
                row.update(state='insufficient_for_predeclared_cohort_metrics')
            else:
                row.update(state='reported',model=scores(labels,p[mask],threshold),
                           constant_training_prior=scores(labels,baseline[mask],threshold))
            cohorts[field].append(row)
    return {'model':model,'constant_training_prior':reference,'frozen_threshold':threshold,
            'constant_probability':prior,'research_comparison':{'checks':checks,'passed':all(checks.values()),
              'authority':criteria['authority'],'operational_approval':False},
            'uncertainty':uncertainty(y,p,prior,dates,plan['uncertainty_plan']),
            'cohort_diagnostics':cohorts}
