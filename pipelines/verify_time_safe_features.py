"""Create one isolated synthetic availability-time join demonstration; no existing inputs."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

from pipelines.time_safe_features import weather_features
from pipelines.verify_import_safety import identity
from services.api.configuration import validate_environment
from services.api.paths import ROOT

SOURCES = ('pipelines/time_safe_features.py', 'pipelines/verify_time_safe_features.py')


def fixture():
    def event(name, station, observed, available, temperature, wind):
        return dict(event_id=name, airport=station, observed_at='2025-01-01T'+observed+'Z',
                    available_at='2025-01-01T'+available+'Z', temperature_c=temperature,
                    wind_knots=wind, source_scope='synthetic')
    def query(name, origin, time):
        return dict(query_id=name, origin=origin, decision_at='2025-01-01T'+time+'Z', source_scope='synthetic')
    return {'events': [event('initial', 'AAA', '08:00:00', '08:05:00', 20, 5),
                       event('late-report', 'AAA', '08:30:00', '09:10:00', 21, 7),
                       event('other-airport', 'BBB', '08:50:00', '08:55:00', 25, 9)],
            'queries': [query('before-first', 'AAA', '08:04:59'), query('at-first', 'AAA', '08:05:00'),
                        query('before-late', 'AAA', '09:00:00'), query('at-late', 'AAA', '09:10:00'),
                        query('stale', 'AAA', '10:00:01'), query('other', 'BBB', '09:00:00'),
                        query('missing-airport', 'CCC', '09:00:00')]}


def source_hashes():
    return {name: hashlib.sha256((ROOT/name).read_text(encoding='utf-8').encode()).hexdigest() for name in SOURCES}


def verify(directory):
    config = validate_environment(os.environ)
    if config.container or any(os.environ.get(key) == '1' for key in ('AIN_AGENT_JOBS', 'AIN_MONITOR_ENABLED', 'AIN_OBSERVER_MOUNTED', 'AIN_INTAKE_OVERVIEW_MOUNTED')):
        raise ValueError('host_research_environment_required')
    directory = Path(directory)
    if any(path.is_symlink() or getattr(path, 'is_junction', lambda: False)() for path in (directory, *directory.parents)):
        raise ValueError('unredirected_case_required')
    context = identity()
    context['source_sha256'].update(source_hashes())
    directory.mkdir(parents=True, exist_ok=False)
    report = {'format': 'ain-time-safe-features-drill-v1', 'checked_at': datetime.now(timezone.utc).isoformat(),
              **context, 'passed': False, 'checks': {}, 'synthetic_only': True,
              'primary_database_accessed': False, 'training_performed': False,
              'deployment_performed': False, 'production_ready': False}
    try:
        inputs = fixture()
        encoded = json.dumps(inputs, indent=2, allow_nan=False)+'\n'
        (directory/'synthetic-input.json').write_text(encoded, encoding='utf-8', newline='\n')
        report['fixture_sha256'] = hashlib.sha256(encoded.encode()).hexdigest()
        joined = weather_features(**inputs, scope='synthetic')
        results_encoded = json.dumps(joined, indent=2, allow_nan=False)+'\n'
        (directory/'joined-results.json').write_text(results_encoded, encoding='utf-8', newline='\n')
        report['results_sha256'] = hashlib.sha256(results_encoded.encode()).hexdigest()
        by_id = {row['query_id']: row for row in joined}
        without_late = weather_features(inputs['queries'][:3], [e for e in inputs['events'] if e['event_id'] != 'late-report'], scope='synthetic')
        report['checks'] = {
            'one_result_per_query': len(joined) == 7,
            'not_available_before_publication': by_id['before-first']['status'] == 'unavailable',
            'available_at_exact_cutoff': by_id['at-first']['event_id'] == 'initial',
            'late_report_excluded_before_availability': by_id['before-late']['event_id'] == 'initial',
            'future_event_noninterference': joined[:3] == without_late,
            'late_report_eligible_at_availability': by_id['at-late']['event_id'] == 'late-report',
            'stale_measurements_not_features': by_id['stale']['status'] == 'stale' and by_id['stale']['temperature_c'] is None and by_id['stale']['wind_knots'] is None,
            'airports_do_not_cross': by_id['other']['event_id'] == 'other-airport' and by_id['missing-airport']['status'] == 'unavailable',
            'scope_labels_retained': all(row['source_scope'] == 'synthetic' for row in joined),
            'source_unchanged': all(hashlib.sha256((ROOT/p).read_text(encoding='utf-8').encode()).hexdigest() == h for p, h in context['source_sha256'].items())}
        report['counts'] = {status: sum(row['status'] == status for row in joined) for status in ('matched', 'stale', 'unavailable')}
        report['passed'] = all(report['checks'].values())
    except Exception:
        report['error'] = 'synthetic_time_join_check_failed'
    (directory/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n', encoding='utf-8', newline='\n')
    return report


if __name__ == '__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    result = verify(ROOT/'.local/time-safe-features'/uuid4().hex)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['passed'] else 2)
