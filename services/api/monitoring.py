"""Bounded local monitoring. No request contents, identities or external alerts."""
import asyncio
from collections import Counter, deque
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from threading import Lock
import time
from uuid import uuid4


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def age_between(current,earlier):
    if type(current) not in (int,float) or type(earlier) not in (int,float):return None
    try:
        value=current-earlier
        return value if math.isfinite(value) and value>=0 else None
    except OverflowError:return None


def valid_timing(value):
    try:return type(value) in (int,float) and math.isfinite(value) and value>=0
    except OverflowError:return False


class Monitor:
    def __init__(self, destination, probes, enabled=False, clock=time.monotonic):
        self.destination = Path(destination)
        self.probes = probes
        self.enabled = enabled
        self.clock = clock
        self.started = clock()
        self.instance = str(uuid4())
        self.lock = Lock()
        self.counts = Counter()
        self.durations = deque(maxlen=200)
        self.invalid_latencies = 0
        self.failures = deque(maxlen=50)
        self.incidents = deque(maxlen=50)
        self.components = {}
        self.checked = None
        self.checked_clock = None
        self.persistence_ok = None
        self.task = None
        self.stopping = asyncio.Event()

    def record(self, status, elapsed_ms):
        # Status classes only: never store URLs, headers, input, account IDs or exception text.
        valid_status=type(status) is int and 100<=status<=599
        group = str(status // 100) + 'xx' if valid_status else 'other'
        with self.lock:
            self.counts[group] += 1
            if valid_timing(elapsed_ms):
                self.durations.append(round(elapsed_ms,2))
            else:self.invalid_latencies+=1
            if valid_status and status >= 500:
                self.failures.append({'at': timestamp(), 'status': status})

    def sample(self):
        observations = {}
        for name, probe in self.probes.items():
            try:
                observations[name] = probe() is True
            except Exception:
                observations[name] = False
        with self.lock:
            at = timestamp()
            for name, healthy in observations.items():
                previous = self.components.get(name)
                if previous is None and not healthy or previous is not None and previous != healthy:
                    self.incidents.append({'at': at, 'component': name,
                                           'state': 'recovered' if healthy else 'unavailable'})
            self.components = observations
            self.checked = at
            self.checked_clock = self.clock()
            record = {'format': 'ain-monitor-v1', 'instance': self.instance, 'checked_at': at,
                      'components': observations, 'transitions': list(self.incidents),
                      'request_counts': dict(self.counts), 'recent_server_failures': list(self.failures),
                      'production_ready': False}
        temporary = self.destination.with_suffix('.tmp')
        try:
            self.destination.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
            temporary.replace(self.destination)
            persisted = True
        except OSError:
            persisted = False
        with self.lock:
            self.persistence_ok = persisted

    def snapshot(self):
        with self.lock:
            current=self.clock()
            age = None if self.checked_clock is None else age_between(current,self.checked_clock)
            if age is not None:age=round(age,1)
            uptime=age_between(current,self.started)
            fresh = self.enabled and bool(self.components) and age is not None and age < 90
            durations = sorted(self.durations)
            return {'enabled': self.enabled, 'instance': self.instance, 'checked_at': self.checked,
                    'sample_age_seconds': None if age is None else round(age, 1),
                    'state': 'disabled' if not self.enabled else 'unknown' if not fresh else
                        'healthy' if all(self.components.values()) and self.persistence_ok is True else 'degraded',
                    'components': dict(self.components) if fresh else {},
                    'persistence_ok': self.persistence_ok, 'transitions': list(reversed(self.incidents)),
                    'request_counts': dict(self.counts), 'recent_server_failures': list(reversed(self.failures)),
                    'latency': {'sample_size': len(durations), 'window_limit': 200,
                                'p95_ms': durations[math.ceil(len(durations) * .95) - 1] if durations else None,
                                'invalid_samples':self.invalid_latencies},
                    'uptime_seconds': round(uptime,1) if uptime is not None else None,
                    'interval_seconds': 30, 'stale_after_seconds': 90,
                    'external_alert_delivery': False, 'production_ready': False}

    async def run(self):
        while not self.stopping.is_set():
            await asyncio.to_thread(self.sample)
            try:
                await asyncio.wait_for(self.stopping.wait(), timeout=30)
            except TimeoutError:
                pass

    def start(self):
        if self.enabled:
            self.task = asyncio.create_task(self.run())

    async def stop(self):
        if self.task:
            self.stopping.set()
            await self.task
