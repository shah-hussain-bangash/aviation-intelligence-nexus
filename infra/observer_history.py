"""Bounded, editable local endpoint transition history; not a protected audit."""
from copy import deepcopy
from datetime import datetime
import json
import os
from pathlib import Path
import tempfile

FORMAT = 'ain-observer-history-v1'
LIMIT = 100
COMPONENTS = {'api_readiness', 'frontend_liveness'}


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('Invalid observation timestamp')
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError('Observation timestamp must include a timezone')
    return parsed


def components(value):
    if not isinstance(value, dict) or set(value) != COMPONENTS or any(type(v) is not bool for v in value.values()):
        raise ValueError('Invalid observed components')


def validate(record):
    fields = {'format', 'port', 'last_observed_at', 'last_observed_components', 'events', 'events_total', 'events_dropped', 'production_ready'}
    if not isinstance(record, dict) or set(record) != fields or record['format'] != FORMAT or record['production_ready'] is not False:
        raise ValueError('Invalid local incident history')
    if type(record['port']) is not int or record['port'] not in (8090, 8092):
        raise ValueError('Unsupported observer target')
    latest = timestamp(record['last_observed_at'])
    components(record['last_observed_components'])
    events = record['events']
    total, dropped = record['events_total'], record['events_dropped']
    if not isinstance(events, list) or len(events) > LIMIT or type(total) is not int or type(dropped) is not int or total < 0 or dropped < 0 or total - dropped != len(events):
        raise ValueError('Invalid incident history bounds')
    for sequence, event in enumerate(events, dropped + 1):
        if not isinstance(event, dict) or set(event) != {'sequence', 'at', 'component', 'state'}:
            raise ValueError('Invalid incident event')
        if type(event['sequence']) is not int or event['sequence'] != sequence or event['component'] not in COMPONENTS or event['state'] not in ('unavailable', 'recovered') or timestamp(event['at']) > latest:
            raise ValueError('Invalid incident sequence')
    return record


def load(directory):
    path = Path(directory) / 'incidents.json'
    if path.is_symlink():
        raise ValueError('Incident history must be an ordinary file')
    if not path.exists():
        return None
    if path.stat().st_size > 64000:
        raise ValueError('Oversized incident history')
    return validate(json.loads(path.read_text(encoding='utf-8')))


class IncidentHistory:
    """Writer requires the observer's existing exclusive OS lock."""
    def __init__(self, directory, port):
        if type(port) is not int or port not in (8090, 8092):
            raise ValueError('Unsupported observer target')
        self.directory = Path(directory)
        self.port = port
        self.record = load(directory)
        if self.record is not None and self.record['port'] != port:
            raise ValueError('Choose another directory for a different observer target')

    def observe(self, at, observed):
        timestamp(at); components(observed)
        previous = self.record
        if previous is not None and timestamp(at) < timestamp(previous['last_observed_at']):
            raise ValueError('Observation clock moved backwards')
        value = deepcopy(previous) if previous is not None else {
            'format': FORMAT, 'port': self.port, 'events': [], 'events_total': 0,
            'events_dropped': 0, 'production_ready': False,
        }
        prior = {} if previous is None else previous['last_observed_components']
        for component in sorted(COMPONENTS):
            before, after = prior.get(component), observed[component]
            if before is None and not after or before is not None and before != after:
                value['events_total'] += 1
                value['events'].append({'sequence': value['events_total'], 'at': at, 'component': component,
                                        'state': 'recovered' if after else 'unavailable'})
        value['events'] = value['events'][-LIMIT:]
        value['events_dropped'] = value['events_total'] - len(value['events'])
        value.update(last_observed_at=at, last_observed_components=dict(observed))
        validate(value)
        temporary = None
        target = self.directory / 'incidents.json'
        if target.is_symlink():
            raise ValueError('Incident history must be an ordinary file')
        try:
            with tempfile.NamedTemporaryFile(mode='w', dir=self.directory, prefix='.incidents-', suffix='.tmp', encoding='utf-8', delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(value, stream, sort_keys=True)
                stream.flush(); os.fsync(stream.fileno())
            temporary.replace(target)
            self.record = value
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()


def history(directory):
    try:
        record = load(directory)
        if record is None:
            return {'recorded': False, 'state': 'not_recorded', 'events': [], 'external_alert_delivery': False, 'production_ready': False}
        return {'recorded': True, **deepcopy(record), 'retained_event_limit': LIMIT,
                'external_alert_delivery': False,
                'scope': 'Historical local endpoint observations; not live health, full uptime coverage or a protected audit.'}
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return {'recorded': False, 'state': 'unavailable', 'events': [], 'external_alert_delivery': False, 'production_ready': False}
