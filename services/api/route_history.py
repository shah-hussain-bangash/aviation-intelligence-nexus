"""Bounded read-only directional-route aggregates and descriptive Wilson intervals."""
from contextlib import closing
from datetime import datetime, timezone
import math
from pathlib import Path
import re
import sqlite3
from threading import BoundedSemaphore
import time

SOURCE = 'BTS_REPORTING_CARRIER'
_SLOT = BoundedSemaphore(1)
QUERY_SECONDS = 5


class LookupBusy(RuntimeError):
    pass


class LookupUnavailable(RuntimeError):
    pass


class RouteNotObserved(LookupError):
    pass


def proportion(events, observations):
    if type(events) is not int or type(observations) is not int or not 0 <= events <= observations:
        raise ValueError('Invalid binomial counts')
    if observations == 0:
        return {'events': events, 'observations': observations, 'rate': None, 'wilson_95': None}
    z = 1.959963984540054
    rate = events / observations
    denominator = 1 + z * z / observations
    center = (rate + z * z / (2 * observations)) / denominator
    half = z * math.sqrt(rate * (1 - rate) / observations + z * z / (4 * observations ** 2)) / denominator
    return {'events': events, 'observations': observations, 'rate': rate,
            'wilson_95': [0.0 if events == 0 else max(0, center - half),
                          1.0 if events == observations else min(1, center + half)]}


def lookup(database, origin, destination):
    if not all(isinstance(code, str) and re.fullmatch('[A-Z]{3}', code) for code in [origin, destination]) or origin == destination:
        raise ValueError('Use two different three-letter uppercase airport codes')
    if not _SLOT.acquire(blocking=False):
        raise LookupBusy('One route lookup is already active')
    started = time.monotonic()
    try:
        with closing(sqlite3.connect(Path(database).resolve().as_uri() + '?mode=ro', uri=True, timeout=.5)) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute('PRAGMA query_only=ON')
            connection.execute('BEGIN')
            deadline = started + QUERY_SECONDS
            connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
            rows = connection.execute('''
                SELECT CASE WHEN flight_date<'2025-04-01' THEN 'train' ELSE 'evaluation' END AS period,
                  COUNT(*) AS flights,
                  SUM(CASE WHEN cancelled=0 AND diverted=0 AND arrival_delay_minutes IS NOT NULL THEN 1 ELSE 0 END) AS completed,
                  SUM(CASE WHEN cancelled=0 AND diverted=0 AND arrival_delay_minutes>=15 THEN 1 ELSE 0 END) AS delayed_15,
                  SUM(CASE WHEN cancelled=0 AND diverted=0 AND arrival_delay_minutes>=60 THEN 1 ELSE 0 END) AS delayed_60,
                  SUM(CASE WHEN cancelled=1 THEN 1 ELSE 0 END) AS cancelled,
                  SUM(CASE WHEN diverted=1 THEN 1 ELSE 0 END) AS diverted,
                  SUM(CASE WHEN cancelled=0 AND diverted=0 AND arrival_delay_minutes IS NULL THEN 1 ELSE 0 END) AS missing_arrival,
                  SUM(CASE WHEN cancelled=0 AND diverted=0 AND arrival_delay_minutes IS NOT NULL
                      THEN MAX(0,MIN(arrival_delay_minutes,180)) ELSE 0 END) AS positive_delay_sum,
                  SUM(CASE WHEN cancelled NOT IN (0,1) OR cancelled IS NULL OR diverted NOT IN (0,1) OR diverted IS NULL THEN 1 ELSE 0 END) AS invalid_flags
                FROM flights WHERE source=? AND origin=? AND destination=?
                  AND ((flight_date>='2025-01-01' AND flight_date<'2025-04-01')
                    OR (flight_date>='2025-05-01' AND flight_date<'2025-06-01'))
                GROUP BY period
                ''', (SOURCE, origin, destination)).fetchall()
            if time.monotonic() > deadline:
                raise LookupUnavailable('Route query exceeded its local deadline')
        if not rows:
            raise RouteNotObserved('No official observations in the defined periods')
        observed = {row['period']: dict(row) for row in rows}
        periods = []
        for name, threshold in [('train', 200), ('evaluation', 50)]:
            row = observed.get(name)
            if row is not None and row['invalid_flags']:
                raise LookupUnavailable('Source status flags could not be verified')
            counts = {key: int(row[key]) if row else 0 for key in
                      ['flights', 'completed', 'delayed_15', 'delayed_60', 'cancelled', 'diverted', 'missing_arrival']}
            completed = counts['completed']
            mean = float(row['positive_delay_sum']) / completed if completed else None
            if mean is not None and (not math.isfinite(mean) or not 0 <= mean <= 180):
                raise LookupUnavailable('Source delay aggregate could not be verified')
            periods.append({'id': name, **counts, 'available': counts['flights'] > 0,
                'support_threshold': threshold, 'meets_support': completed >= threshold,
                'delay_15': proportion(counts['delayed_15'], completed),
                'delay_60': proportion(counts['delayed_60'], completed),
                'cancellation': proportion(counts['cancelled'], counts['flights']),
                'mean_positive_delay_capped_180': mean})
        supported = all(row['meets_support'] for row in periods)
        change = (periods[1]['delay_15']['rate'] - periods[0]['delay_15']['rate']) * 100 if supported else None
        return {'format': 'ain-route-history-v1', 'source': SOURCE, 'route': {'origin': origin, 'destination': destination},
            'checked_at': datetime.now(timezone.utc).isoformat(), 'periods': periods,
            'comparison_support_met': supported, 'delay_15_change_percentage_points': change,
            'group_assignment': None, 'elapsed_ms': round((time.monotonic() - started) * 1000, 3),
            'interval_method': '95% Wilson score, independent-binomial descriptive model',
            'research_only': True, 'production_ready': False,
            'limitations': ['Currently imported historical US domestic rows; carriers combined; April excluded.',
                'Intervals treat observations as independent binomial trials; shared weather/operations can violate that assumption.',
                'No correction for repeated route searches or causal/significance claim; displayed difference is descriptive.',
                'No cluster assignment, forecast, operational recommendation or UAE validation.']}
    except sqlite3.Error as error:
        raise LookupUnavailable('Historical route data could not be read within local limits') from error
    finally:
        _SLOT.release()
