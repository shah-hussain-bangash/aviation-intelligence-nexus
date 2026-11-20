"""Read-only route-level historical segmentation with train-only selection."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sqlite3
import time

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / 'ml/route_segments_v1.json'
PROTOCOL_SHA256 = 'd01519802b488be5fa94a13da5ac24e38ce7f3b180da43eeb37dc3861d588774'


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False, separators=(',', ':')).encode()).hexdigest()


def load_protocol():
    content = PROTOCOL_PATH.read_text(encoding='utf-8')
    if hashlib.sha256(content.encode()).hexdigest() != PROTOCOL_SHA256:
        raise ValueError('Frozen route experiment changed; create a new version')
    return json.loads(content)


def aggregate(connection, period, source):
    # Only aggregate official source rows; routes combine reporting carriers and remain directional.
    frame = pd.read_sql_query('''
        SELECT origin,destination,COUNT(*) AS flights,
          SUM(CASE WHEN cancelled=0 AND diverted=0 AND arrival_delay_minutes IS NOT NULL THEN 1 ELSE 0 END) AS completed,
          SUM(CASE WHEN cancelled=0 AND diverted=0 AND arrival_delay_minutes>=15 THEN 1 ELSE 0 END) AS delayed_15,
          SUM(CASE WHEN cancelled=0 AND diverted=0 AND arrival_delay_minutes>=60 THEN 1 ELSE 0 END) AS delayed_60,
          SUM(CASE WHEN cancelled=0 AND diverted=0 AND arrival_delay_minutes IS NOT NULL
              THEN MAX(0,MIN(arrival_delay_minutes,180)) ELSE 0 END) AS positive_delay_sum,
          SUM(CASE WHEN cancelled=1 THEN 1 ELSE 0 END) AS cancelled_count,
          SUM(CASE WHEN cancelled NOT IN (0,1) OR cancelled IS NULL OR diverted NOT IN (0,1) OR diverted IS NULL THEN 1 ELSE 0 END) AS invalid_flags
        FROM flights WHERE source=? AND flight_date>=? AND flight_date<?
        GROUP BY origin,destination ORDER BY origin,destination
        ''', connection, params=[source, *period])
    if frame.empty or frame['invalid_flags'].sum() or frame[['origin', 'destination']].isna().any().any():
        raise ValueError('Missing routes or invalid status flags')
    denominator = frame['completed'].replace(0, np.nan)
    frame['delay_15_rate'] = frame['delayed_15'] / denominator
    frame['delay_60_rate'] = frame['delayed_60'] / denominator
    frame['mean_positive_delay_capped_180'] = frame['positive_delay_sum'] / denominator
    frame['cancellation_rate'] = frame['cancelled_count'] / frame['flights']
    return frame


def supported(frame, minimum, features):
    selected = frame.loc[frame['completed'] >= minimum].copy().reset_index(drop=True)
    if len(selected) < 8 or not np.isfinite(selected[features].to_numpy()).all():
        raise ValueError('Insufficient finite route support')
    return selected


def fit(train, protocol):
    scaler = StandardScaler().fit(train[protocol['features']])
    values = scaler.transform(train[protocol['features']])
    candidates = []
    models = {}
    for k in protocol['candidates']:
        if k >= len(values):
            continue
        model = KMeans(n_clusters=k, random_state=protocol['seed'], n_init=protocol['n_init']).fit(values)
        counts = np.bincount(model.labels_, minlength=k)
        distinct = len(np.unique(model.labels_)) == k
        support = distinct and counts.min() >= max(protocol['minimum_cluster_routes'],
                                                     len(values) * protocol['minimum_cluster_fraction'])
        score = None
        if distinct:
            try:
                score = float(silhouette_score(values, model.labels_, sample_size=min(len(values), protocol['silhouette_sample_size']),
                                               random_state=protocol['seed']))
            except ValueError:
                pass
        candidates.append({'k': k, 'training_routes_per_cluster': counts.tolist(),
            'training_silhouette': score, 'support_passed': bool(support), 'inertia': float(model.inertia_)})
        models[k] = model
    eligible = [row for row in candidates if row['support_passed'] and row['training_silhouette'] is not None]
    if not eligible:
        raise ValueError('No training candidate meets the frozen support constraints')
    selected = max(eligible, key=lambda row: (row['training_silhouette'], -row['k']))
    model = models[selected['k']]
    stability = []
    for seed in protocol['stability_seeds']:
        alternative = KMeans(n_clusters=selected['k'], random_state=seed, n_init=protocol['n_init']).fit(values)
        stability.append({'seed': seed, 'training_adjusted_rand_index': float(adjusted_rand_score(model.labels_, alternative.labels_))})
    return scaler, model, candidates, stability


def profiles(frame, labels, features):
    copy = frame.assign(cluster=labels)
    rows = []
    for cluster, group in copy.groupby('cluster', sort=True):
        rows.append({'cluster': int(cluster), 'routes': len(group), 'flights': int(group['flights'].sum()),
            'completed_with_observed_arrival': int(group['completed'].sum()),
            'unweighted_mean_route_features': {name: float(group[name].mean()) for name in features}})
    return rows


def experiment(database, output):
    protocol = load_protocol()
    if output.exists():
        raise ValueError('Experiment output exists; preserve it and choose a new version')
    output.mkdir(parents=True)
    (output / 'started.json').write_text(json.dumps({'protocol_sha256': PROTOCOL_SHA256,
        'started_at': datetime.now(timezone.utc).isoformat()}) + '\n', encoding='utf-8')
    started = time.perf_counter()
    # URI read-only plus query_only: no migrations, insertion or account/history writes.
    with closing(sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True, timeout=5)) as connection:
        connection.execute('PRAGMA query_only=ON')
        connection.execute('BEGIN')
        deadline = time.monotonic() + 120
        connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
        train_all = aggregate(connection, protocol['train'], protocol['source'])
        evaluation_all = aggregate(connection, protocol['evaluation'], protocol['source'])
        imports = pd.read_sql_query('SELECT period,sha256,rows_inserted FROM imports ORDER BY period', connection).to_dict('records')
        source_rows = connection.execute('SELECT COUNT(*) FROM flights WHERE source=?', (protocol['source'],)).fetchone()[0]
    features = protocol['features']
    train = supported(train_all, protocol['minimum_train_completed'], features)
    evaluation = supported(evaluation_all, protocol['minimum_evaluation_completed'], features)
    with threadpool_limits(limits=2):
        scaler, model, candidates, stability = fit(train, protocol)
        evaluation_values = scaler.transform(evaluation[features])
        later_labels = model.predict(evaluation_values)
    # Cluster IDs are ordered by training delay-15 rate solely for readable stable labels.
    raw_profiles = profiles(train, model.labels_, features)
    order = sorted(raw_profiles, key=lambda row: (row['unweighted_mean_route_features']['delay_15_rate'], row['cluster']))
    mapping = {row['cluster']: rank for rank, row in enumerate(order)}
    train_labels = np.array([mapping[int(value)] for value in model.labels_])
    evaluation_labels = np.array([mapping[int(value)] for value in later_labels])
    left = train[['origin', 'destination']].assign(train_cluster=train_labels)
    right = evaluation[['origin', 'destination']].assign(evaluation_cluster=evaluation_labels)
    overlap = left.merge(right, on=['origin', 'destination'], how='inner', validate='one_to_one')
    transitions = [[int(((overlap['train_cluster'] == a) & (overlap['evaluation_cluster'] == b)).sum())
                     for b in range(model.n_clusters)] for a in range(model.n_clusters)]
    artifact = output / 'model.joblib'
    joblib.dump({'scaler': scaler, 'kmeans': model, 'cluster_mapping': mapping, 'features': features,
                 'protocol_sha256': PROTOCOL_SHA256}, artifact)
    assignments = train[['origin', 'destination']].assign(period='training', cluster=train_labels)
    pd.concat([assignments, evaluation[['origin', 'destination']].assign(period='evaluation', cluster=evaluation_labels)]).to_csv(output / 'route_assignments.csv', index=False)
    def coverage(all_routes, selected):
        return {'routes_observed': len(all_routes), 'routes_supported': len(selected),
            'flights_observed': int(all_routes['flights'].sum()), 'flights_on_supported_routes': int(selected['flights'].sum()),
            'completed_observed_arrivals': int(all_routes['completed'].sum()),
            'aggregate_sha256': canonical_hash(all_routes.drop(columns=features).to_dict('records'))}
    result = {'experiment': protocol['experiment'], 'checked_at': datetime.now(timezone.utc).isoformat(),
        'scope': 'Retrospective US domestic directional-route segmentation; routes combine carriers; no operational approval',
        'protocol': protocol, 'protocol_sha256': PROTOCOL_SHA256, 'source_records': source_rows,
        'source_imports': imports, 'coverage': {'train': coverage(train_all, train), 'evaluation': coverage(evaluation_all, evaluation)},
        'selected_k': int(model.n_clusters), 'candidates': candidates, 'training_seed_stability': stability,
        'training_scaler_mean': scaler.mean_.tolist(), 'training_scaler_scale': scaler.scale_.tolist(),
        'profiles': {'train': profiles(train, train_labels, features), 'evaluation': profiles(evaluation, evaluation_labels, features)},
        'later_period': {'overlapping_supported_routes': len(overlap),
            'evaluation_supported_routes_unseen_in_training': len(evaluation) - len(overlap),
            'changed_cluster_fraction_on_overlap': float((overlap['train_cluster'] != overlap['evaluation_cluster']).mean()) if len(overlap) else None,
            'transition_counts_training_rows_evaluation_columns': transitions,
            'mean_feature_shift_in_training_standard_deviations': dict(zip(features, evaluation_values.mean(axis=0).tolist()))},
        'artifact_sha256': hashlib.sha256(artifact.read_bytes()).hexdigest(),
        'elapsed_seconds': round(time.perf_counter() - started, 3),
        'environment': {'python': platform.python_version(), 'sklearn': sklearn.__version__, 'pandas': pd.__version__, 'numpy': np.__version__},
        'research_only': True, 'production_ready': False,
        'limitations': ['Descriptive segments use observed arrival/cancellation outcomes, not pre-departure features or future predictions.',
            'KMeans assumes Euclidean approximately convex groups; standardized correlated features affect geometry.',
            'Silhouette is a training selection diagnostic, not label accuracy or business value; no semantic ground truth.',
            'Seed agreement is not bootstrap stability; minimum support excludes sparse routes.',
            'Later outcomes were previously available for other experiments; this is a fixed temporal comparison, not a newly untouched holdout.',
            'US domestic January-March/May 2025 only; no UAE data, full-season validation or causal/cost benefit.',
            'All routes have equal fitting weight; flight-weighted business outcomes and airline-specific differences are not validated.']}
    (output / 'report.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=ROOT / '.local/ain.sqlite3')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(experiment(args.database, args.output), indent=2, allow_nan=False))
