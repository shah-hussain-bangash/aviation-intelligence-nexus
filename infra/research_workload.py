"""Disposable native HTTP research-workflow drill; never accepts a target deployment."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timezone
import hashlib
from http.client import HTTPConnection
from http.cookies import SimpleCookie
import json
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import tempfile
from threading import Thread
import time
from uuid import uuid4

from infra.load_check import summarize

SCENARIO = {'carrier': 'AA', 'origin': 'JFK', 'destination': 'LAX',
            'flight_date': '2025-05-15', 'scheduled_departure': '09:00'}


def bounds(requests, workers):
    if type(requests) is not int or not 1 <= requests <= 30:
        raise ValueError('Use 1-30 prediction requests')
    if type(workers) is not int or not 1 <= workers <= 4:
        raise ValueError('Use 1-4 client workers')


def request(port, method, path, payload=None, headers=None):
    connection = HTTPConnection('127.0.0.1', port, timeout=10)
    started = time.perf_counter()
    try:
        connection.request(method, path, body=json.dumps(payload) if payload is not None else None,
                           headers={'Content-Type': 'application/json', 'Connection': 'close', **(headers or {})})
        response = connection.getresponse()
        body = response.read(2_000_001)
        if len(body) > 2_000_000:
            raise RuntimeError('Oversized local research response')
        return response.status, json.loads(body), response.getheader('Set-Cookie'), (time.perf_counter() - started) * 1000
    finally:
        connection.close()


def run(model_directory, requests=12, workers=2):
    bounds(requests, workers)
    source = Path(model_directory)
    # This is an operator-supplied, locally trusted joblib artifact, not a model upload service.
    report = json.loads((source / 'report.json').read_text(encoding='utf-8'))
    model_bytes = (source / 'model.joblib').read_bytes()
    digest = hashlib.sha256(model_bytes).hexdigest()
    if (digest != report.get('artifact_sha256') or report.get('model_version') != 'delay-v2'
            or report.get('release_assessment', {}).get('research_gate_passed') is not True):
        raise ValueError('Verified research artifact required')
    import uvicorn
    from services.api.auth import COOKIE
    from services.api.main import create_app

    checks = {}
    def require(name, condition):
        checks[name] = bool(condition)
        if not condition:
            raise RuntimeError('Research drill check failed: ' + name)

    with tempfile.TemporaryDirectory(prefix='ain-research-drill-') as folder:
        root = Path(folder)
        model = root / 'model'
        model.mkdir()
        (model / 'model.joblib').write_bytes(model_bytes)
        (model / 'report.json').write_text(json.dumps(report), encoding='utf-8')
        database = root / 'drill.sqlite3'
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen(16)
            port = listener.getsockname()[1]
            settings = {'AIN_AGENT_JOBS': '0', 'AIN_MONITOR_ENABLED': '0', 'AIN_API_PORT': str(port)}
            previous = {key: os.environ.get(key) for key in settings}
            try:
                os.environ.update(settings)
                app = create_app(database, root / 'missing-baseline', model, root / 'missing-index')
            finally:
                for key, value in previous.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value
            server = uvicorn.Server(uvicorn.Config(app, log_level='critical', access_log=False,
                                                   timeout_graceful_shutdown=5))
            thread = Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
            thread.start()
            try:
                deadline = time.monotonic() + 15
                while not server.started and thread.is_alive() and time.monotonic() < deadline:
                    time.sleep(.02)
                require('isolated_server_started', server.started)
                password = secrets.token_urlsafe(32)
                sessions = {}
                for username, role in [('drill-admin', 'admin'), ('drill-researcher', 'researcher'),
                                       ('drill-other', 'researcher'), ('drill-viewer', 'viewer')]:
                    app.state.auth_store.create_user(username, password, role)
                    code, payload, cookie, _ = request(port, 'POST', '/api/v1/auth/login',
                        {'username': username, 'password': password}, {'Origin': f'http://127.0.0.1:{port}'})
                    require('disposable_login_' + role, code == 200 and bool(payload.get('csrf_token')))
                    jar = SimpleCookie()
                    jar.load(cookie)
                    sessions[username] = {'Origin': f'http://127.0.0.1:{port}',
                        'Cookie': f'{COOKIE}={jar[COOKIE].value}', 'X-CSRF-Token': payload['csrf_token']}
                researcher = sessions['drill-researcher']
                require('anonymous_history_denied', request(port, 'GET', '/api/v1/research/history')[0] == 401)
                require('viewer_prediction_denied', request(port, 'POST', '/api/v1/research/predict', SCENARIO,
                    sessions['drill-viewer'])[0] == 403)
                require('missing_csrf_denied', request(port, 'POST', '/api/v1/research/predict', SCENARIO,
                    {k: v for k, v in researcher.items() if k != 'X-CSRF-Token'})[0] == 403)
                require('unknown_vocabulary_denied', request(port, 'POST', '/api/v1/research/predict',
                    {**SCENARIO, 'origin': 'ZZZ'}, researcher)[0] == 422)
                key = str(uuid4())
                replay_headers = {**researcher, 'Idempotency-Key': key}
                code, first, _, cold_ms = request(port, 'POST', '/api/v1/research/predict', SCENARIO, replay_headers)
                probability = first.get('arrival_delay_15_probability')
                require('cold_prediction_verified', code == 200 and first.get('artifact_sha256') == digest
                        and first.get('research_only') is True and first.get('operational_serving_approved') is False
                        and isinstance(probability, (int, float)) and 0 <= probability <= 1)
                code, replay, _, _ = request(port, 'POST', '/api/v1/research/predict', SCENARIO, replay_headers)
                require('same_request_replayed', code == 200 and replay.get('run_id') == first['run_id'] and replay.get('replayed') is True)
                require('changed_request_conflict', request(port, 'POST', '/api/v1/research/predict',
                    {**SCENARIO, 'scheduled_departure': '10:00'}, replay_headers)[0] == 409)
                require('other_owner_key_conflict', request(port, 'POST', '/api/v1/research/predict', SCENARIO,
                    {**sessions['drill-other'], 'Idempotency-Key': key})[0] == 409)

                def predict(_):
                    code, payload, _, duration = request(port, 'POST', '/api/v1/research/predict', SCENARIO,
                        {**researcher, 'Idempotency-Key': str(uuid4())})
                    valid = (code == 200 and payload.get('artifact_sha256') == digest
                        and payload.get('arrival_delay_15_probability') == probability
                        and payload.get('research_only') is True and payload.get('replayed') is False)
                    return {'milliseconds': duration, 'status': code, 'error': None if valid else 'invalid_prediction'}
                started = time.perf_counter()
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    samples = list(pool.map(predict, range(requests)))
                measurement = summarize(samples, time.perf_counter() - started)
                require('concurrent_predictions_valid', measurement['failures'] == 0)
                duplicate_headers = {**researcher, 'Idempotency-Key': str(uuid4())}
                with ThreadPoolExecutor(max_workers=2) as pool:
                    pair = list(pool.map(lambda _: request(port, 'POST', '/api/v1/research/predict', SCENARIO, duplicate_headers), range(2)))
                require('concurrent_duplicate_saved_once', all(row[0] == 200 for row in pair)
                    and pair[0][1]['run_id'] == pair[1][1]['run_id']
                    and sum(row[1].get('replayed') is True for row in pair) == 1)
                code, history, _, _ = request(port, 'GET', '/api/v1/research/history', headers=researcher)
                require('owner_history_readable', code == 200 and len(history.get('runs', [])) == min(10, requests + 2))
                code, other, _, _ = request(port, 'GET', '/api/v1/research/history', headers=sessions['drill-other'])
                require('other_owner_history_empty', code == 200 and other.get('runs') == [])
                with closing(sqlite3.connect(database)) as connection:
                    saved = connection.execute('SELECT COUNT(*) FROM research_runs').fetchone()[0]
                    require('exact_saved_row_count', saved == requests + 2)
                    require('database_integrity', connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok')
                require('logout_succeeded', request(port, 'POST', '/api/v1/auth/logout', {}, researcher)[0] == 200)
                require('revoked_session_denied', request(port, 'GET', '/api/v1/research/history', headers=researcher)[0] == 401)
            finally:
                server.should_exit = True
                thread.join(timeout=15)
                if thread.is_alive():
                    raise RuntimeError('Temporary server did not stop')
        require('temporary_server_stopped', not thread.is_alive())
    require('temporary_state_removed', not root.exists())
    return {'format': 'ain-disposable-research-workload-v1', 'checked_at': datetime.now(timezone.utc).isoformat(),
            'scope': 'Native loopback API with disposable accounts/empty flight database and copied trusted model; not Docker or airline capacity qualification',
            'model_version': 'delay-v2', 'artifact_sha256': digest, 'scenario': SCENARIO,
            'workers': workers, 'prediction_requests': requests, 'cold_prediction_ms': round(cold_ms, 3),
            'warm_prediction_measurement': measurement, 'prediction_probability': probability,
            'saved_rows_before_cleanup': saved, 'checks': checks, 'passed': all(checks.values()),
            'performance_target_assessed': False, 'production_ready': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-directory', default='.local/models/delay-v2')
    parser.add_argument('--requests', type=int, default=12)
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists():
        parser.error('Choose a new evidence file')
    result = run(args.model_directory, args.requests, args.workers)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
