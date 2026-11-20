"""Verified, fixed public experiment summary; no model loading or live SQL."""
import hashlib
import json
import math
from pathlib import Path
from services.api.paths import ROOT

REPORT = 'docs/reports/Route_Segments_v1.json'
REPORT_SHA256 = '280e6fed4d8b2de0566b0d95e3ca5f07f5e40cafb262201024520ab4ffad88e6'


def load_segments(root=ROOT):
    path = Path(root) / REPORT
    if path.is_symlink() or path.stat().st_size > 100000:
        raise ValueError('Invalid fixed experiment report')
    text = path.read_text(encoding='utf-8')
    if hashlib.sha256(text.encode()).hexdigest() != REPORT_SHA256:
        raise ValueError('Experiment report integrity mismatch')
    report = json.loads(text)
    if report['experiment'] != 'route-segments-v1' or report['research_only'] is not True or report['production_ready'] is not False:
        raise ValueError('Unsupported experiment claim')
    k = report['selected_k']
    matrix = report['later_period']['transition_counts_training_rows_evaluation_columns']
    overlap = report['later_period']['overlapping_supported_routes']
    changed = sum(value for a, row in enumerate(matrix) for b, value in enumerate(row) if a != b)
    if len(matrix) != k or any(len(row) != k for row in matrix) or sum(map(sum, matrix)) != overlap:
        raise ValueError('Inconsistent route transitions')
    if not math.isclose(changed / overlap, report['later_period']['changed_cluster_fraction_on_overlap']):
        raise ValueError('Inconsistent transition rate')
    selected = next(row for row in report['candidates'] if row['k'] == k)
    return {'format': 'ain-route-patterns-v1', 'experiment': report['experiment'],
        'recorded_at': report['checked_at'], 'report_sha256': REPORT_SHA256,
        'integrity_verified': True, 'research_only': True, 'production_ready': False,
        'source_records_at_experiment': report['source_records'], 'selected_k': k,
        'training_silhouette': selected['training_silhouette'],
        'minimum_training_seed_ari': min(row['training_adjusted_rand_index'] for row in report['training_seed_stability']),
        'coverage': {period: {key: report['coverage'][period][key] for key in
            ['routes_observed', 'routes_supported', 'flights_observed', 'flights_on_supported_routes']}
            for period in ['train', 'evaluation']},
        'profiles': report['profiles'], 'overlapping_routes': overlap, 'changed_routes': changed,
        'transition_counts': matrix,
        'evaluation_routes_outside_training_support': report['later_period']['evaluation_supported_routes_unseen_in_training'],
        'limitations': report['limitations']}
