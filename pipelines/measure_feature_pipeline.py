"""Host-only synthetic schedule/weather resource measurement; no application database."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import time
import tracemalloc
from uuid import uuid4

import tzdata

from pipelines.decision_times import MAX_FLIGHTS, decision_queries
from pipelines.time_safe_features import MAX_EVENTS, MAX_QUERIES, timestamp, weather_features
from pipelines.verify_import_safety import identity
from services.api.configuration import validate_environment
from services.api.paths import ROOT

SCALES = {'smoke': (500, 2000), 'capacity': (50_000, 200_000)}
AIRPORTS = ('AAA', 'BBB', 'CCC', 'DDD')
ZONES = ('Etc/UTC', 'Asia/Dubai', 'America/New_York', 'Australia/Perth')
SOURCES = ('pipelines/measure_feature_pipeline.py', 'pipelines/decision_times.py', 'pipelines/time_safe_features.py')


def records_hash(records):
    digest = hashlib.sha256()
    for row in records:
        digest.update((json.dumps(row, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n').encode())
    return digest.hexdigest()


def recipe(scale):
    if type(scale) is not str or scale not in SCALES:
        raise ValueError('unsupported_measurement_scale')
    flights, events = SCALES[scale]
    if not 1 <= flights <= min(MAX_FLIGHTS, MAX_QUERIES) or not 4 <= events <= MAX_EVENTS:
        raise ValueError('measurement_exceeds_library_bounds')
    return {'format': 'ain-synthetic-feature-recipe-v1', 'scale': scale, 'schedules': flights,
            'events': events, 'start_local': '2025-01-01T00:00:00', 'lead_minutes': 120,
            'weather_start': '2024-12-30T00:00:00Z', 'weather_step_seconds': math.ceil((flights*60+4*86400)/(events-1)),
            'weather_receipt_lag_seconds': 90, 'airports': list(AIRPORTS),
            'timezones': list(ZONES), 'source_scope': 'synthetic'}


def inputs(spec):
    schedules, events = [], []
    start = datetime(2025, 1, 1)
    weather_start = datetime(2024, 12, 30, tzinfo=timezone.utc)
    mappings = {airport: dict(timezone=zone, reference_id='synthetic-reference-'+airport,
                              source_scope='synthetic', valid_from='2024-01-01', valid_until='2026-01-01')
                for airport, zone in zip(AIRPORTS, ZONES)}
    for index in range(spec['schedules']):
        local = start+timedelta(minutes=index)
        schedules.append(dict(flight_id='synthetic-flight-'+str(index), flight_date=local.date().isoformat(),
                              scheduled_departure=local.strftime('%H%M'), origin=AIRPORTS[index % 4], source_scope='synthetic'))
    for index in range(spec['events']):
        observed = weather_start+timedelta(seconds=index*spec['weather_step_seconds'])
        available = observed+timedelta(seconds=spec['weather_receipt_lag_seconds'])
        events.append(dict(event_id='synthetic-weather-'+str(index), airport=AIRPORTS[index % 4],
                           observed_at=observed.isoformat().replace('+00:00', 'Z'),
                           available_at=available.isoformat().replace('+00:00', 'Z'),
                           temperature_c=(index % 41)-10, wind_knots=index % 31, source_scope='synthetic'))
    return schedules, mappings, events


def sample_agreement(queries, events, features):
    if not queries or len(features) != len(queries):
        return False, 0
    selected = sorted(set(range(min(4, len(queries)))) | {len(queries)//4, len(queries)//2, 3*len(queries)//4, len(queries)-1})
    for index in selected:
        query, actual = queries[index], features[index]
        # Independent linear scan, rather than reusing the production binary search.
        candidate = None
        for event in events:
            if event['airport'] == query['origin'] and event['available_at'] <= query['decision_at']:
                if candidate is None or event['available_at'] > candidate['available_at']:
                    candidate = event
        if candidate is None:
            return False, len(selected)
        age = int((timestamp(query['decision_at'])-timestamp(candidate['observed_at'])).total_seconds())
        if not (actual['query_id'] == query['query_id'] and actual['event_id'] == candidate['event_id']
                and actual['observed_at'] == candidate['observed_at'] and actual['available_at'] == candidate['available_at']
                and actual['age_seconds'] == age and age <= 3600 and actual['status'] == 'matched'
                and actual['temperature_c'] == candidate['temperature_c'] and actual['wind_knots'] == candidate['wind_knots']):
            return False, len(selected)
    return True, len(selected)


def measure(directory, *, scale='smoke'):
    config = validate_environment(os.environ)
    if config.container or any(os.environ.get(key) == '1' for key in ('AIN_AGENT_JOBS', 'AIN_MONITOR_ENABLED', 'AIN_OBSERVER_MOUNTED', 'AIN_INTAKE_OVERVIEW_MOUNTED')):
        raise ValueError('host_research_environment_required')
    if tracemalloc.is_tracing():
        raise ValueError('independent_memory_tracker_required')
    spec = recipe(scale)
    directory = Path(directory)
    if any(path.is_symlink() or getattr(path, 'is_junction', lambda: False)() for path in (directory, *directory.parents)):
        raise ValueError('unredirected_case_required')
    context = identity()
    context['source_sha256'].update({p: hashlib.sha256((ROOT/p).read_text(encoding='utf-8').encode()).hexdigest() for p in SOURCES})
    directory.mkdir(parents=True, exist_ok=False)
    report = {'format': 'ain-feature-resource-measurement-v1', 'checked_at': datetime.now(timezone.utc).isoformat(),
              'case_id': directory.name if len(directory.name) == 32 and all(c in '0123456789abcdef' for c in directory.name) else None,
              **context, 'passed': False, 'recipe': spec, 'checks': {}, 'phases': {},
              'software': {'python': platform.python_version(), 'tzdata': tzdata.__version__},
              'synthetic_only': True, 'primary_database_accessed': False, 'training_performed': False,
              'deployment_performed': False, 'production_ready': False}
    encoded = (json.dumps(spec, indent=2)+'\n').encode()
    (directory/'recipe.json').write_bytes(encoded)
    report['recipe_sha256'] = hashlib.sha256(encoded).hexdigest()
    (directory/'started.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8', newline='\n')
    tracemalloc.start(1)
    started, cpu_started = time.perf_counter(), time.process_time()
    stage = 'generation'
    try:
        def phase(name, function):
            start, cpu = time.perf_counter(), time.process_time()
            result = function()
            report['phases'][name] = {'wall_seconds': round(time.perf_counter()-start, 6),
                                     'cpu_seconds': round(time.process_time()-cpu, 6)}
            return result
        schedules, mappings, events = phase(stage, lambda: inputs(spec))
        stage = 'utc_decisions'
        decisions = phase(stage, lambda: decision_queries(schedules, mappings, scope='synthetic', lead_minutes=spec['lead_minutes']))
        stage = 'weather_join'
        features = phase(stage, lambda: weather_features(decisions['queries'], events, scope='synthetic'))
        stage = 'verification'
        def verify():
            agreement, checked = sample_agreement(decisions['queries'], events, features)
            return agreement, checked, {
                'schedules': records_hash(schedules), 'mappings': records_hash([{**value, 'airport': key} for key, value in sorted(mappings.items())]),
                'weather': records_hash(events), 'decisions': records_hash(decisions['decisions']),
                'queries': records_hash(decisions['queries']), 'features': records_hash(features)}
        agreement, checked, fingerprints = phase(stage, verify)
        report['record_stream_sha256'] = fingerprints
        report['independent_sample_size'] = checked
        report['counts'] = {'schedules': len(schedules), 'events': len(events), 'ready': len(decisions['queries']),
                            'excluded': sum(row['status'] != 'ready' for row in decisions['decisions']),
                            'matched': sum(row['status'] == 'matched' for row in features)}
        report['timezone_resources'] = {row['timezone']: row['timezone_sha256'] for row in decisions['decisions']}
        report['checks'] = {
            'input_counts_reconciled': len(schedules) == spec['schedules'] and len(events) == spec['events'],
            'all_schedules_ready': len(decisions['decisions']) == len(decisions['queries']) == spec['schedules'] and report['counts']['excluded'] == 0,
            'all_queries_matched': len(features) == report['counts']['matched'] == spec['schedules'],
            'independent_sample_agrees': agreement,
            'labels_retained': all(row['source_scope'] == 'synthetic' for rows in (schedules, events, decisions['decisions'], decisions['queries'], features) for row in rows),
            'timezone_evidence_retained': len(report['timezone_resources']) == 4 and all(report['timezone_resources'].values()),
            'source_unchanged': all(hashlib.sha256((ROOT/p).read_text(encoding='utf-8').encode()).hexdigest() == h for p, h in context['source_sha256'].items())}
        report['passed'] = all(report['checks'].values())
    except Exception:
        report['error'] = 'synthetic_resource_measurement_failed'
        report['failed_stage'] = stage
    finally:
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        report['measurement'] = {'wall_seconds': round(time.perf_counter()-started, 6),
                                 'cpu_seconds': round(time.process_time()-cpu_started, 6),
                                 'python_traced_current_bytes': current, 'python_traced_peak_bytes': peak,
                                 'includes_generation_and_verification': True, 'tracemalloc_frames': 1,
                                 'whole_process_rss_measured': False, 'instrumentation_overhead_included': True}
    (directory/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n', encoding='utf-8', newline='\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scale', choices=tuple(SCALES), default='smoke')
    result = measure(ROOT/'.local/feature-measurements'/uuid4().hex, scale=parser.parse_args().scale)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['passed'] else 2)
