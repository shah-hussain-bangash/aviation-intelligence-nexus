"""Single-process local dashboard observer; no external notification delivery."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener
from infra.recovery import private_target
from services.api.monitoring import Monitor
from infra.observer_history import IncidentHistory, history


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def probe(port, readiness):
    if type(port) is not int or port not in (8090, 8092):
        raise ValueError('Only approved loopback dashboard ports are supported')
    path = '/__ain/ready' if readiness else '/__ain/health'
    try:
        # Bypass environment proxies and never follow redirects away from the fixed origin.
        with build_opener(ProxyHandler({}), NoRedirect()).open(
                f'http://127.0.0.1:{port}{path}', timeout=3) as response:
            raw = response.read(4097)
            if response.status != 200 or len(raw) > 4096:
                return False
            payload = json.loads(raw.decode('utf-8'))
            return isinstance(payload, dict) and payload.get('service') == 'ain-dashboard' and (
                not readiness or payload.get('backend_ready') is True and payload.get('production_ready') is False)
    except (OSError, ValueError, UnicodeError):
        return False


@contextmanager
def exclusive(directory):
    path = Path(directory) / 'observer.lock'
    if path.is_symlink():
        raise ValueError('Observer lock must be an ordinary file')
    with path.open('a+b') as stream:
        if stream.tell() == 0:
            stream.write(b'0'); stream.flush()
        stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Closing the OS handle releases the lock after normal exit or process termination.
        yield


def status(directory, now=None):
    try:
        path = Path(directory) / 'health.json'
        if path.is_symlink() or path.stat().st_size > 64000:
            raise ValueError('Invalid observer record')
        record = json.loads(path.read_text(encoding='utf-8'))
        assert record['format'] == 'ain-monitor-v1' and record['production_ready'] is False
        checked = datetime.fromisoformat(record['checked_at'])
        assert checked.utcoffset() is not None
        age = (datetime.now(timezone.utc) if now is None else now).timestamp() - checked.timestamp()
        assert 0 <= age < 15
        age = round(age, 2)
        assert age < 15
        components = record['components']
        assert isinstance(components, dict)
        assert set(components) == {'api_readiness', 'frontend_liveness'}
        assert all(type(value) is bool for value in components.values())
        return {'state': 'healthy' if all(components.values()) else 'degraded',
                'checked_at': record['checked_at'], 'components': components,
                'sample_age_seconds': round(age, 2), 'external_alert_delivery': False,
                'production_ready': False}
    except (OSError, ValueError, TypeError, KeyError, AssertionError, OverflowError):
        return {'state': 'unknown', 'components': {}, 'external_alert_delivery': False, 'production_ready': False}


def deployment_status(state):
    """Read only the fixed observer directory selected by the deployment, never a request path."""
    container = os.environ.get('AIN_CONTAINER') == '1'
    mounted = os.environ.get('AIN_OBSERVER_MOUNTED') == '1'
    if container and not mounted:
        result = {'state': 'unknown', 'components': {}, 'external_alert_delivery': False, 'production_ready': False}
        mode = 'not_configured'
    else:
        result = status(Path('/observer') if container else Path(state) / 'observer')
        mode = 'container_readonly_mount' if container else 'native_local_file'
    return {**result, 'source_mode': mode, 'task_runtime_verified': False}


def observe(directory, port=8090, once=False):
    directory = private_target(directory)
    if port not in (8090, 8092):
        raise ValueError('Unsupported dashboard port')
    directory.mkdir(parents=True, exist_ok=True)
    record = directory / 'health.json'
    stop = directory / 'stop.request'
    if record.is_symlink() or stop.is_symlink():
        raise ValueError('Observer files must not be symbolic links')
    if stop.exists():
        raise ValueError('Remove the existing stop request explicitly before starting')
    with exclusive(directory):
        journal = IncidentHistory(directory, port)
        monitor = Monitor(record, {'api_readiness': lambda: probe(port, True),
                                  'frontend_liveness': lambda: probe(port, False)}, enabled=True)
        while not stop.exists():
            monitor.sample()
            if monitor.persistence_ok is not True:
                raise OSError('Observer record could not be persisted')
            observation = monitor.snapshot()
            journal.observe(observation['checked_at'], observation['components'])
            if once:
                return
            time.sleep(5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['run', 'status', 'history'])
    parser.add_argument('--directory', required=True)
    parser.add_argument('--port', type=int, choices=[8090, 8092], default=8090)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    directory = private_target(args.directory)
    if args.action == 'status':
        print(json.dumps(status(directory)))
    elif args.action == 'history':
        print(json.dumps(history(directory)))
    else:
        observe(directory, args.port, args.once)


if __name__ == '__main__':
    main()
