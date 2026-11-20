"""Bounded, anonymous loopback HTTP measurements; no AI or state-changing calls."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.client import HTTPConnection, HTTPException
import json
import math
from pathlib import Path
import time

PATHS = ('/', '/__ain/ready', '/api/v1/auth/session')
MAX_BODY = 2_000_000


def validate(port, requests, workers, timeout):
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('Invalid loopback port')
    if type(requests) is not int or not 1 <= requests <= 100:
        raise ValueError('Use 1-100 measured requests per endpoint')
    if type(workers) is not int or not 1 <= workers <= 4:
        raise ValueError('Use 1-4 client workers')
    if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 0.1 <= timeout <= 5:
        raise ValueError('Use a finite 0.1-5 second socket timeout')


def probe(port, path, timeout):
    if path not in PATHS:
        raise ValueError('Endpoint is not allowlisted')
    started = time.perf_counter()
    connection = HTTPConnection('127.0.0.1', port, timeout=timeout)
    error = None
    status = None
    try:
        # A new connection for each request; no cookies, redirects or credentials.
        connection.request('GET', path, headers={'Connection': 'close'})
        response = connection.getresponse()
        status = response.status
        body = response.read(MAX_BODY + 1)
        if len(body) > MAX_BODY:
            error = 'oversized_response'
        elif status != 200:
            error = 'unexpected_status'
        elif path == '/':
            if b'<title>AIN | Aviation Intelligence Nexus</title>' not in body:
                error = 'unexpected_content'
        else:
            payload = json.loads(body)
            if not isinstance(payload, dict):
                error = 'unexpected_content'
            elif path == '/__ain/ready':
                if payload.get('backend_ready') is not True or payload.get('production_ready') is not False:
                    error = 'unexpected_content'
            elif payload.get('authenticated') is not False or payload.get('user', 'missing') is not None:
                error = 'unexpected_content'
    except (OSError, ValueError, HTTPException) as exc:
        # Do not retain response bodies, stack traces, tokens or arbitrary exception text.
        error = 'invalid_json' if isinstance(exc, ValueError) else 'transport_error'
    finally:
        connection.close()
    return {'milliseconds': (time.perf_counter() - started) * 1000,
            'status': status, 'error': error}


def percentile(values, quantile):
    """Nearest-rank percentile (not interpolated), including failed request durations."""
    ordered = sorted(values)
    return round(ordered[max(0, math.ceil(quantile * len(ordered)) - 1)], 3)


def summarize(samples, elapsed):
    durations = [sample['milliseconds'] for sample in samples]
    errors = {}
    statuses = {}
    for sample in samples:
        if sample['error']:
            errors[sample['error']] = errors.get(sample['error'], 0) + 1
        status = str(sample['status']) if sample['status'] is not None else 'no_response'
        statuses[status] = statuses.get(status, 0) + 1
    return {'requests': len(samples), 'failures': sum(errors.values()),
            'error_classes': errors, 'status_counts': statuses,
            'elapsed_seconds': round(elapsed, 6),
            'completed_requests_per_second': round(len(samples) / elapsed, 3),
            'latency_ms': {'min': round(min(durations), 3),
                           'p50': percentile(durations, .5),
                           'p95': percentile(durations, .95),
                           'max': round(max(durations), 3)}}


def run(port=8090, requests=30, workers=2, timeout=3):
    validate(port, requests, workers, timeout)
    endpoints = []
    for path in PATHS:
        warmup = probe(port, path, timeout)
        # Stop before generating a batch against a missing/misidentified/unhealthy service.
        if warmup['error']:
            endpoints.append({'path': path, 'warmup': warmup, 'measurement': None})
            break
        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            samples = list(pool.map(lambda _: probe(port, path, timeout), range(requests)))
        endpoints.append({'path': path, 'warmup': warmup,
                          'measurement': summarize(samples, time.perf_counter() - started)})
    passed = len(endpoints) == len(PATHS) and all(
        row['measurement'] is not None and row['measurement']['failures'] == 0 for row in endpoints)
    return {'format': 'ain-local-http-measurement-v1',
            'checked_at': datetime.now(timezone.utc).isoformat(),
            'scope': 'Anonymous local HTTP correctness and latency sample; not capacity, browser rendering or production qualification',
            'client': {'host': '127.0.0.1', 'port': port, 'workers': workers,
                       'requests_per_endpoint': requests, 'socket_timeout_seconds': timeout,
                       'connection_reuse': False, 'warmups_per_endpoint': 1},
            'percentile_method': 'nearest-rank; all measured request durations including failures',
            'endpoints': endpoints, 'all_responses_valid': passed,
            'performance_target_assessed': False, 'production_ready': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8090)
    parser.add_argument('--requests', type=int, default=30)
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--timeout', type=float, default=3)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    target = Path(args.output)
    if target.exists():
        parser.error('Choose a new output file; existing measurements are never replaced')
    result = run(args.port, args.requests, args.workers, args.timeout)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    return 0 if result['all_responses_valid'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
