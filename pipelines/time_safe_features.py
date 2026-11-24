"""Bounded research weather joins using recorded availability, never arrival outcomes."""
from bisect import bisect_right
from datetime import datetime, timezone
import math
import re

MAX_EVENTS = 200_000
MAX_QUERIES = 50_000
SCOPES = ('synthetic', 'historical_research')
EVENT_FIELDS = {'event_id', 'airport', 'observed_at', 'available_at', 'temperature_c', 'wind_knots', 'source_scope'}
QUERY_FIELDS = {'query_id', 'origin', 'decision_at', 'source_scope'}


def require(condition, code):
    if not condition:
        raise ValueError(code)


def timestamp(value):
    require(isinstance(value, str) and bool(re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', value)), 'canonical_utc_timestamp_required')
    try:
        return datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
    except ValueError:
        raise ValueError('invalid_utc_timestamp') from None


def identifier(value):
    return isinstance(value, str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{1,80}', value))


def airport(value):
    return isinstance(value, str) and bool(re.fullmatch(r'[A-Z]{3}', value))


def weather_features(queries, events, *, scope, max_age_seconds=3600):
    """Return one result per query, in input order; refuse ambiguous event revisions.

    Availability must represent the time the research system could actually consume
    the event, including ingestion delay. Caller declarations are not authenticated.
    No prediction, target, flight outcome, database or external service is accessed.
    """
    require(type(scope) is str and scope in SCOPES, 'explicit_research_scope_required')
    require(type(max_age_seconds) is int and 1 <= max_age_seconds <= 86400, 'invalid_maximum_age')
    timelines = {}
    seen = {}
    slots = set()
    for count, event in enumerate(events, 1):
        require(count <= MAX_EVENTS, 'event_limit_exceeded')
        require(type(event) is dict and set(event) == EVENT_FIELDS, 'invalid_event_fields')
        require(event['source_scope'] == scope, 'source_scope_mismatch')
        require(identifier(event['event_id']) and airport(event['airport']), 'invalid_event_identity')
        observed = timestamp(event['observed_at'])
        available = timestamp(event['available_at'])
        require(observed <= available, 'observation_after_availability')
        for field in ('temperature_c', 'wind_knots'):
            require(type(event[field]) in (int, float) and -1.7976931348623157e308 <= event[field] <= 1.7976931348623157e308 and math.isfinite(event[field]), 'invalid_weather_measurement')
        require(event['wind_knots'] >= 0, 'negative_wind_speed')
        previous = seen.get(event['event_id'])
        if previous is not None:
            require(previous == event, 'conflicting_event_identity')
            continue
        slot = event['airport'], available
        require(slot not in slots, 'ambiguous_availability_revision')
        slots.add(slot)
        seen[event['event_id']] = dict(event)
        timelines.setdefault(event['airport'], []).append((available, observed, dict(event)))
    for timeline in timelines.values():
        timeline.sort(key=lambda item: item[0])
    keys = {key: [row[0] for row in timeline] for key, timeline in timelines.items()}
    results = []
    query_ids = set()
    for count, query in enumerate(queries, 1):
        require(count <= MAX_QUERIES, 'query_limit_exceeded')
        require(type(query) is dict and set(query) == QUERY_FIELDS, 'invalid_query_fields')
        require(query['source_scope'] == scope, 'source_scope_mismatch')
        require(identifier(query['query_id']) and airport(query['origin']), 'invalid_query_identity')
        require(query['query_id'] not in query_ids, 'duplicate_query_identity')
        query_ids.add(query['query_id'])
        cutoff = timestamp(query['decision_at'])
        result = {**query, 'status': 'unavailable', 'event_id': None, 'observed_at': None,
                  'available_at': None, 'age_seconds': None, 'temperature_c': None,
                  'wind_knots': None, 'max_age_seconds': max_age_seconds}
        index = bisect_right(keys.get(query['origin'], []), cutoff) - 1
        if index >= 0:
            available, observed, event = timelines[query['origin']][index]
            age = int((cutoff - observed).total_seconds())
            result.update(event_id=event['event_id'], observed_at=event['observed_at'],
                          available_at=event['available_at'], age_seconds=age)
            if age <= max_age_seconds:
                result.update(status='matched', temperature_c=event['temperature_c'], wind_knots=event['wind_knots'])
            else:
                result['status'] = 'stale'
        results.append(result)
    return results
