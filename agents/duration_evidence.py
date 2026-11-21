"""Canonical negative-regression evidence; never fits, scores or queries flights."""
import json
from services.api.duration import load_duration

LIMIT='The duration model failed the preset 1% RMSE improvement check in both April and May; duration inference is not deployed. This already inspected US release is not a fresh holdout, causal explanation or operational approval.'


def required_quotes(saved):
    text=saved.get('evidence_text') if isinstance(saved,dict) else None
    lines=text.splitlines() if isinstance(text,str) else []
    return {'may_baselines':next((line for line in lines if line.startswith('May 2025:')),''),
        'severe_errors':next((line for line in lines if line.startswith('Among ')),''),'negative_scope':LIMIT}


def observation():
    report=load_duration()
    if report['research_check']['passed'] is not False:raise ValueError('This tool version requires the frozen negative duration result')
    snapshot={'format':'ain-agent-duration-v1','evaluation':report,'research_only':True,'production_ready':False,'duration_inference_deployed':False}
    lines=[f'Frozen duration regression trained on {report["datasets"]["train"]["records"]} January-March 2025 eligible US flights; April has {report["datasets"]["validation"]["records"]} and May has {report["datasets"]["test"]["records"]} evaluation flights.']
    for key,label in [('validation','April 2025'),('test','May 2025')]:
        p=report[key]
        lines.append(f'{label}: model RMSE {p["model"]["rmse"]:.6f} minutes versus training-mean baseline {p["training_mean_baseline"]["rmse"]:.6f}; model MAE {p["model"]["mae"]:.6f} minutes versus training-median baseline {p["training_median_baseline"]["mae"]:.6f}.')
    tail=report['test']['observed_60_plus']
    lines.extend([f'Among {tail["records"]} observed May delays of at least 60 minutes, model MAE was {tail["model_mae"]:.6f} minutes and bias (predicted minus actual) was {tail["model_mean_error"]:.6f} minutes.',LIMIT,
        'Target is max(0, arrival-delay minutes), without upper clipping, conditional on completed non-diverted flights with observed arrivals.',
        'The artifact and April evaluation were frozen before the May query; earlier project experiments had already inspected this five-month release.',
        'Squared-error fitting targets conditional means; improvement in RMSE can coexist with worse MAE than a median baseline.',
        'The severe-delay group is defined retrospectively using actual outcomes, not identified prospectively by this model.',
        'These measurements do not identify why the model underperformed. No weather evidence, refitting, threshold change, uncertainty interval or individual-flight estimate is supplied.'])
    return {'data_kind':'recorded_duration_regression','available':True,'snapshot':snapshot,'evidence_text':'\n'.join(lines)}


def valid_observation(saved):
    try:return json.dumps(saved,sort_keys=True,allow_nan=False)==json.dumps(observation(),sort_keys=True,allow_nan=False)
    except (OSError,ValueError,TypeError,KeyError):return False
