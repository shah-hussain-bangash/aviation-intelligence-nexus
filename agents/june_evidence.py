"""Canonical recorded June evidence; no model, archive, SQL or provider access."""
import json
from services.api.june_evaluation import load_june_evaluation

LIMIT = ('This frozen later-month US comparison does not establish a globally untouched holdout, '
         'statistical significance, causality, UAE validation or operational approval. '
         'No refit, threshold change, new inference or deployment is performed by this tool.')


def required_quotes(saved):
    text = saved.get('evidence_text') if isinstance(saved, dict) else None
    lines = text.splitlines() if isinstance(text, str) else []
    return {'june_comparison': next((s for s in lines if s.startswith('June 2025:')), ''),
            'descriptive_intervals': next((s for s in lines if s.startswith('Descriptive uncertainty:')), ''),
            'research_scope': LIMIT}


def observation():
    r = load_june_evaluation()
    m, b, u = r['model'], r['constant_training_prior'], r['uncertainty']
    ll = u['statistics']['mean_log_loss_difference_model_minus_prior']
    bs = u['statistics']['mean_brier_difference_model_minus_prior']
    lines = [
        f'June 2025: {m["records"]} eligible flights; frozen-model ROC-AUC {m["roc_auc"]:.6f}; '
        f'log loss {m["log_loss"]:.6f} versus training-prior baseline {b["log_loss"]:.6f}; '
        f'Brier score {m["brier_score"]:.6f} versus baseline {b["brier_score"]:.6f}.',
        f'Descriptive uncertainty: {u["replicates"]} seeded resamples of {u["date_clusters"]} complete flight-date clusters; '
        f'model-minus-prior 95% percentile intervals are [{ll["lower"]:.6f}, {ll["upper"]:.6f}] for mean log loss '
        f'and [{bs["lower"]:.6f}, {bs["upper"]:.6f}] for mean Brier score; negative differences favour the model.',
        LIMIT,
        f'The fixed decision threshold is {r["frozen_threshold"]:.2f}; report fingerprint {r["report_sha256"]}. '
        'The monthly SQL selector and January-May prediction window are unchanged.',
    ]
    return {'data_kind': 'recorded_june_evaluation', 'available': True,
            'snapshot': {'format': 'ain-agent-june-v1', 'evaluation': r,
                         'research_only': True, 'production_ready': False},
            'evidence_text': '\n'.join(lines)}


def valid_observation(saved):
    try:
        return json.dumps(saved, sort_keys=True, allow_nan=False) == json.dumps(observation(), sort_keys=True, allow_nan=False)
    except (OSError, ValueError, KeyError, TypeError):
        return False
