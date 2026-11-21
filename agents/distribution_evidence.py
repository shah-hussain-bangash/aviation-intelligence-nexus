"""Small immutable snapshot of recorded marginal distributions, never live profiling."""
import json
from services.api.distributions import load_distributions

LIMIT='Retrospective marginal differences do not prove model degradation or causality, and matching counts do not verify frozen CSV identity; no live drift alert is available.'


def observation():
    report=load_distributions()
    snapshot={'format':'ain-agent-distributions-v1','report_sha256':report['report_sha256'],
        'protocol_sha256':report['protocol_sha256'],'reference_records':report['reference_records'],
        'comparison_records':report['comparison_records'],'periods':report['protocol']['periods'],
        'features':{key:{**{k:f[k] for k in ['category_count','total_variation','jensen_shannon_divergence_bits','comparison_unseen_records','comparison_mass_unseen_in_reference']},
            'largest_changes':sorted(f['categories'],key=lambda row:(-abs(row['change_percentage_points']),row['category']))[:3]} for key,f in report['features'].items()},
        'csv_identity_verified':False,'alert_threshold':None,'research_only':True,'production_ready':False,
        'limitations':report['limitations']}
    lines=[f'Recorded January-March 2025 reference contains {snapshot["reference_records"]} eligible US flights; May 2025 comparison contains {snapshot["comparison_records"]} eligible US flights.']
    for key,f in snapshot['features'].items():
        lines.append(f'{key}: total variation {f["total_variation"]:.6f}; base-2 Jensen-Shannon divergence {f["jensen_shannon_divergence_bits"]:.6f} bits; {f["comparison_unseen_records"]} May records have a category absent from the reference.')
    winner=max(snapshot['features'],key=lambda key:snapshot['features'][key]['total_variation'])
    lines.extend([f'Among these five recorded marginal comparisons, {winner} has the largest total variation, {snapshot["features"][winner]["total_variation"]:.6f}.',LIMIT,
        'Eligibility conditions on completed, non-diverted flights with observed arrival delay; the full-flight population is not compared.',
        'No confidence interval, significance test, model fitting or threshold selection is performed. May was already evaluated in earlier experiments.'])
    return {'data_kind':'recorded_input_distributions','available':True,'snapshot':snapshot,'evidence_text':'\n'.join(lines)}


def valid_observation(saved):
    try:return json.dumps(saved,sort_keys=True,allow_nan=False)==json.dumps(observation(),sort_keys=True,allow_nan=False)
    except (OSError,ValueError,TypeError,KeyError):return False
