"""Bounded snapshot of pinned public model experiments, never live inference."""
import json
from services.api.diagnostics import load_diagnostics
from services.api.explanations import load_explanations


def observation():
    diagnostics=load_diagnostics();reliance=load_explanations()
    keys=['records','roc_auc','log_loss','brier_score','binned_ece','precision','recall',
        'confusion_matrix_labels_0_1','false_alerts','missed_delays']
    snapshot={'format':'ain-agent-model-snapshot-v1','model_version':'delay-v2',
        'diagnostics_sha256':diagnostics['report_sha256'],'reliance_sha256':reliance['report_sha256'],
        'threshold':diagnostics['threshold'],
        'periods':{period:{**{key:row['model'][key] for key in keys},'baseline':row['baseline']}
            for period,row in diagnostics['periods'].items()},
        'input_reliance':{'period':'2025-04','sample_records':reliance['sample_records'],
            'validation_population':reliance['validation_population'],'repeats':3,
            'baseline':reliance['baseline'],
            'groups':[{key:row[key] for key in ['group','columns','mean','repeat_std']} for row in reliance['groups']]},
        'limitations':diagnostics['limitations']+reliance['limitations'],
        'research_only':True,'production_ready':False}
    lines=['Frozen delay-v2 recorded model evidence; no live inference or model fitting.']
    for key,label in [('validation','April validation'),('test','May test')]:
        m=snapshot['periods'][key]
        lines.append(f'{label}: {m["records"]} eligible flights; ROC-AUC {m["roc_auc"]:.4f}; log loss {m["log_loss"]:.4f}; binned calibration error {m["binned_ece"]:.2%}; {m["false_alerts"]} false alerts and {m["missed_delays"]} missed delays at the fixed 0.17 threshold.')
    time=next(row for row in reliance['groups'] if row['group']=='departure_time')
    lines.append(f'April-only input-reliance diagnostic: {reliance["sample_records"]} sampled flights, three shuffles per group. Scheduled departure time had the largest mean log-loss increase, {time["mean"]["log_loss_increase"]:.5f}, with repeat sample SD {time["repeat_std"]["log_loss_increase"]:.5f}.')
    lines.extend(['Shuffle variation is not a confidence interval; correlated inputs and implausible shuffled combinations limit interpretation.',
        'Input reliance is not causality or an individual-flight explanation. These are recorded US domestic experiments with no UAE validation or operational approval.',
        'The April diagnostic sample is not a new untouched holdout. No new model, threshold or calibration selection was performed.'])
    return {'data_kind':'recorded_model_evidence','available':True,'snapshot':snapshot,'evidence_text':'\n'.join(lines)}


def valid_observation(saved):
    try:
        # Canonical JSON preserves number/bool distinctions and detects altered text as well as metrics.
        return json.dumps(saved,sort_keys=True,allow_nan=False)==json.dumps(observation(),sort_keys=True,allow_nan=False)
    except (OSError,ValueError,TypeError,KeyError):
        return False
