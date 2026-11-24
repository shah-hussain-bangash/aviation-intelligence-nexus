"""Synthetic local schedule -> UTC decision -> available-weather research trace."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

from pipelines.decision_times import decision_queries
from pipelines.time_safe_features import weather_features
from pipelines.verify_import_safety import identity
from services.api.configuration import validate_environment
from services.api.paths import ROOT

SOURCES = ('pipelines/decision_times.py', 'pipelines/verify_decision_times.py', 'pipelines/time_safe_features.py')


def fixture():
    def flight(name, day, clock, origin):
        return dict(flight_id=name, flight_date=day, scheduled_departure=clock, origin=origin, source_scope='synthetic')
    def mapping(zone, name, end='2026-01-01'):
        return dict(timezone=zone, reference_id=name, valid_from='2025-01-01', valid_until=end, source_scope='synthetic')
    def event(name, origin, observed, available):
        return dict(event_id=name, airport=origin, observed_at=observed, available_at=available,
                    temperature_c=20, wind_knots=5, source_scope='synthetic')
    return {'flights': [flight('dubai-illustration', '2025-01-01', '1000', 'AAA'),
                        flight('midnight', '2025-01-01', '2400', 'BBB'),
                        flight('spring-gap', '2025-03-09', '0230', 'BBB'),
                        flight('fall-fold', '2025-11-02', '0130', 'BBB'),
                        flight('after-spring', '2025-03-09', '0330', 'BBB'),
                        flight('unknown-airport', '2025-01-01', '1000', 'CCC'),
                        flight('expired-reference', '2025-01-02', '1000', 'DDD')],
            'mappings': {'AAA': mapping('Asia/Dubai', 'synthetic-dubai-reference'),
                         'BBB': mapping('America/New_York', 'synthetic-new-york-reference'),
                         'DDD': mapping('Etc/UTC', 'synthetic-expired-reference', '2025-01-02')},
            'events': [event('available-dubai', 'AAA', '2025-01-01T05:00:00Z', '2025-01-01T05:20:00Z'),
                       event('late-dubai', 'AAA', '2025-01-01T05:10:00Z', '2025-01-01T05:31:00Z'),
                       event('available-midnight', 'BBB', '2025-01-02T04:00:00Z', '2025-01-02T04:15:00Z'),
                       event('available-spring', 'BBB', '2025-03-09T06:30:00Z', '2025-03-09T06:45:00Z')],
            'lead_minutes': 30}


def verify(directory):
    config = validate_environment(os.environ)
    if config.container or any(os.environ.get(k) == '1' for k in ('AIN_AGENT_JOBS', 'AIN_MONITOR_ENABLED', 'AIN_OBSERVER_MOUNTED', 'AIN_INTAKE_OVERVIEW_MOUNTED')):
        raise ValueError('host_research_environment_required')
    directory = Path(directory)
    if any(p.is_symlink() or getattr(p, 'is_junction', lambda: False)() for p in (directory, *directory.parents)):
        raise ValueError('unredirected_case_required')
    context = identity()
    context['source_sha256'].update({p: hashlib.sha256((ROOT/p).read_text(encoding='utf-8').encode()).hexdigest() for p in SOURCES})
    directory.mkdir(parents=True, exist_ok=False)
    report = {'format': 'ain-decision-time-drill-v1', 'checked_at': datetime.now(timezone.utc).isoformat(),
              'case_id': directory.name if len(directory.name) == 32 and all(c in '0123456789abcdef' for c in directory.name) else None,
              **context, 'passed': False, 'checks': {}, 'synthetic_only': True,
              'primary_database_accessed': False, 'training_performed': False,
              'deployment_performed': False, 'production_ready': False}
    try:
        def retain(name, data):
            encoded = (json.dumps(data, indent=2, allow_nan=False)+'\n').encode()
            (directory/name).write_bytes(encoded)
            return hashlib.sha256(encoded).hexdigest()
        inputs = fixture()
        report['fixture_sha256'] = retain('synthetic-input.json', inputs)
        decisions = decision_queries(inputs['flights'], inputs['mappings'], scope='synthetic', lead_minutes=inputs['lead_minutes'])
        joined = weather_features(decisions['queries'], inputs['events'], scope='synthetic')
        result = {**decisions, 'features': joined}
        report['results_sha256'] = retain('joined-results.json', result)
        rows = {row['flight_id']: row for row in decisions['decisions']}
        features = {row['query_id']: row for row in joined}
        report['checks'] = {
            'every_schedule_accounted': len(rows) == 7 and len(decisions['queries']) == 3,
            'dubai_offset_and_lead': rows['dubai-illustration']['decision_at'] == '2025-01-01T05:30:00Z',
            'midnight_rolls_to_next_date': rows['midnight']['scheduled_departure_utc'] == '2025-01-02T05:00:00Z',
            'spring_gap_excluded': rows['spring-gap']['status'] == 'excluded_nonexistent_local_time',
            'fall_fold_excluded': rows['fall-fold']['status'] == 'excluded_ambiguous_local_time',
            'valid_dst_conversion': rows['after-spring']['decision_at'] == '2025-03-09T07:00:00Z',
            'unknown_mapping_excluded': rows['unknown-airport']['status'] == 'excluded_missing_mapping',
            'expired_mapping_excluded': rows['expired-reference']['status'] == 'excluded_mapping_period',
            'late_weather_excluded': features['dubai-illustration']['event_id'] == 'available-dubai',
            'all_ready_queries_joined': len(joined) == 3 and all(row['status'] == 'matched' for row in joined),
            'timezone_evidence_retained': all(row['tzdata_version'] and row['timezone_sha256'] and row['mapping_reference'] for row in rows.values() if row['status'] == 'ready'),
            'synthetic_labels_retained': all(row['source_scope'] == 'synthetic' for row in [*rows.values(), *joined]),
            'source_unchanged': all(hashlib.sha256((ROOT/p).read_text(encoding='utf-8').encode()).hexdigest() == h for p, h in context['source_sha256'].items())}
        report['counts'] = {'schedules': 7, 'ready': len(decisions['queries']), 'excluded': 7-len(decisions['queries']), 'weather_matched': sum(row['status'] == 'matched' for row in joined)}
        report['passed'] = all(report['checks'].values())
    except Exception:
        report['error'] = 'synthetic_decision_time_check_failed'
    (directory/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n', encoding='utf-8', newline='\n')
    return report


if __name__ == '__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    result = verify(ROOT/'.local/decision-times'/uuid4().hex)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['passed'] else 2)
