"""Explicit research schedule-to-UTC conversion; reject unresolved civil-time ambiguity."""
from datetime import date, datetime, time, timedelta, timezone
import hashlib
from importlib.resources import files
import io
import re
from zoneinfo import ZoneInfo

import tzdata

from pipelines.time_safe_features import SCOPES, airport, identifier, require

FLIGHT_FIELDS = {'flight_id', 'flight_date', 'scheduled_departure', 'origin', 'source_scope'}
MAPPING_FIELDS = {'timezone', 'reference_id', 'source_scope', 'valid_from', 'valid_until'}
MAX_FLIGHTS = 50_000
MAX_MAPPINGS = 2_000


def calendar_date(value):
    require(isinstance(value, str) and bool(re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value)), 'canonical_date_required')
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError('invalid_calendar_date') from None


def packaged_zone(name):
    """Always use installed pinned tzdata bytes, independent of the host zone database."""
    require(isinstance(name, str) and len(name) <= 80 and bool(re.fullmatch(r'(?:[A-Za-z][A-Za-z0-9_+-]*/)*[A-Za-z][A-Za-z0-9_+-]*', name)), 'invalid_timezone_name')
    try:
        with files('tzdata.zoneinfo').joinpath(*name.split('/')).open('rb') as stream:
            data = stream.read(1024*1024+1)
        require(len(data) <= 1024*1024, 'timezone_resource_limit')
        return ZoneInfo.from_file(io.BytesIO(data), key=name), hashlib.sha256(data).hexdigest()
    except (OSError, ValueError):
        raise ValueError('unsupported_timezone_resource') from None


def utc_candidates(day, departure, zone):
    require(isinstance(departure, str) and bool(re.fullmatch(r'[0-9]{4}', departure)), 'invalid_scheduled_departure')
    hour, minute = int(departure[:2]), int(departure[2:])
    try:
        if departure == '2400':
            day, hour = day+timedelta(days=1), 0
        require(hour < 24 and minute < 60, 'invalid_scheduled_departure')
        local = datetime.combine(day, time(hour, minute))
        candidates = set()
        for fold in (0, 1):
            utc = local.replace(tzinfo=zone, fold=fold).astimezone(timezone.utc)
            if utc.astimezone(zone).replace(tzinfo=None) == local:
                candidates.add(utc)
        return local, candidates
    except (OverflowError, ValueError):
        raise ValueError('invalid_schedule_range') from None


def decision_queries(flights, mappings, *, scope, lead_minutes=120):
    """Derive weather queries plus one provenance/exclusion record for every schedule.

    Mappings are caller-declared research references, not authenticated airport facts.
    Validity dates cover the normalized local departure date; the end is exclusive.
    """
    require(type(scope) is str and scope in SCOPES, 'explicit_research_scope_required')
    require(type(lead_minutes) is int and 0 <= lead_minutes <= 1440, 'invalid_decision_lead')
    require(type(mappings) is dict and len(mappings) <= MAX_MAPPINGS, 'invalid_timezone_mappings')
    prepared = {}
    zones = {}
    for origin, mapping in mappings.items():
        require(airport(origin) and type(mapping) is dict and set(mapping) == MAPPING_FIELDS, 'invalid_timezone_mapping')
        require(mapping['source_scope'] == scope, 'source_scope_mismatch')
        require(identifier(mapping['reference_id']), 'invalid_mapping_reference')
        first, end = calendar_date(mapping['valid_from']), calendar_date(mapping['valid_until'])
        require(first < end, 'invalid_mapping_period')
        name = mapping['timezone']
        require(type(name) is str, 'invalid_timezone_name')
        zone, digest = packaged_zone(name) if name not in zones else zones[name]
        zones[name] = zone, digest
        prepared[origin] = dict(mapping), first, end, zone, digest
    queries, decisions, seen = [], [], set()
    for count, flight in enumerate(flights, 1):
        require(count <= MAX_FLIGHTS, 'flight_limit_exceeded')
        require(type(flight) is dict and set(flight) == FLIGHT_FIELDS, 'invalid_schedule_fields')
        require(flight['source_scope'] == scope, 'source_scope_mismatch')
        require(identifier(flight['flight_id']) and airport(flight['origin']), 'invalid_schedule_identity')
        require(flight['flight_id'] not in seen, 'duplicate_flight_identity')
        seen.add(flight['flight_id'])
        day = calendar_date(flight['flight_date'])
        # Validate clock syntax/range even for rows lacking a timezone mapping.
        normalized, _ = utc_candidates(day, flight['scheduled_departure'], timezone.utc)
        result = {**flight, 'status': 'excluded_missing_mapping', 'lead_minutes': lead_minutes,
                  'timezone': None, 'mapping_reference': None, 'mapping_valid_from': None,
                  'mapping_valid_until': None, 'tzdata_version': tzdata.__version__,
                  'timezone_sha256': None, 'local_departure': None,
                  'scheduled_departure_utc': None, 'decision_at': None}
        if flight['origin'] in prepared:
            mapping, first, end, zone, digest = prepared[flight['origin']]
            result.update(timezone=mapping['timezone'], mapping_reference=mapping['reference_id'],
                          mapping_valid_from=mapping['valid_from'], mapping_valid_until=mapping['valid_until'],
                          timezone_sha256=digest)
            if not first <= normalized.date() < end:
                result['status'] = 'excluded_mapping_period'
            else:
                local, candidates = utc_candidates(day, flight['scheduled_departure'], zone)
                result['local_departure'] = local.isoformat(timespec='seconds')
                if not candidates:
                    result['status'] = 'excluded_nonexistent_local_time'
                elif len(candidates) > 1:
                    result['status'] = 'excluded_ambiguous_local_time'
                else:
                    departure = candidates.pop()
                    try:
                        decision = departure-timedelta(minutes=lead_minutes)
                    except OverflowError:
                        raise ValueError('invalid_decision_range') from None
                    result.update(status='ready', scheduled_departure_utc=departure.isoformat(timespec='seconds').replace('+00:00', 'Z'),
                                  decision_at=decision.isoformat(timespec='seconds').replace('+00:00', 'Z'))
                    queries.append(dict(query_id=flight['flight_id'], origin=flight['origin'],
                                        decision_at=result['decision_at'], source_scope=scope))
        decisions.append(result)
    return {'queries': queries, 'decisions': decisions}
