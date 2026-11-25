"""Versioned synthetic HTTP/recovery rehearsal; explicit images, no primary deployment."""
from pathlib import Path
from datetime import datetime, timezone
from urllib.request import Request, build_opener, HTTPCookieProcessor
from urllib.error import HTTPError
from http.cookiejar import CookieJar
import argparse, json, os, secrets, socket, subprocess, sys
from infra.rehearsal_admission import admit_images, validate_configuration, require
from infra.rehearsal_admission import toolkit_identity
from uuid import uuid4
ROOT = Path(__file__).resolve().parents[1]
from infra.releases import inspect_release
from infra.verify_deployment import verify
from infra.state_contracts import current_contract_digest, contract_digest

def main(*, api_image, web_image, expected_revision, port=18090, scenario='http'):
    admit_images({'api': api_image, 'web': web_image}, expected_revision)
    require(type(port) is int and 1024 <= port <= 65535, 'unprivileged_port_required')
    from infra.rehearsal_scenarios import outage, auto_restart, recovery
    hooks = {'http': None, 'outage': outage, 'automatic_restart': auto_restart, 'restore': recovery}
    require(scenario in hooks, 'unknown_scenario')
    after_auth = hooks[scenario]
    hook_name = scenario
    hook_stage = scenario
    report_prefix = 'AIN_Versioned_' + scenario
    evidence = {'source_revision': expected_revision, 'images': {'api': api_image, 'web': web_image}}
    key = uuid4().hex
    project = 'ain-http-check-' + key[:12]
    case = ROOT / '.local/http-rehearsals' / key
    case.mkdir(parents=True, exist_ok=False)
    env = {k: v for k, v in os.environ.items() if not k.startswith('AIN_') and k != 'PORT'}
    env.update(AIN_ENV='local', AIN_WEB_PORT=str(port), AIN_RELEASE_REVISION=evidence['source_revision'])
    report = {'format': 'ain-isolated-http-rehearsal-v1', 'passed': False, 'checked_at': datetime.now(timezone.utc).isoformat(), 'source_revision': evidence['source_revision'], 'project': project, 'port': port, 'checks': {}, 'synthetic_only': True, 'primary_state_accessed': False, 'primary_deployment_changed': False, 'production_ready': False, 'toolkit_identity': toolkit_identity()}
    started = False
    command = None
    stage = 'preflight'

    def run(args, *, data=None, timeout=120):
        result = subprocess.run(args, cwd=ROOT, env=env, input=data, text=True, capture_output=True, timeout=timeout)
        if result.returncode:
            raise RuntimeError(result.stderr[-2000:] or result.stdout[-2000:])
        return result.stdout
    try:
        require(Path.cwd().resolve() == ROOT, 'rehearsal_check_failed')
        release = inspect_release(evidence['images'])
        require(release['source_revision'] == expected_revision and release['schema_version'] == 8, 'rehearsal_check_failed')
        require(contract_digest(release['contracts']) == current_contract_digest(), 'rehearsal_check_failed')
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', port))
        volume = project + '_state'
        override = {'services': {'api': {'image': release['images']['api'], 'environment': {'AIN_AGENT_JOBS': '0', 'AIN_MONITOR_ENABLED': '0'}, 'restart': 'no'}, 'web': {'image': release['images']['web'], 'restart': 'no'}}, 'volumes': {'state': {'name': volume, 'external': False}}}
        override_path = case / 'isolation.override.json'
        override_path.write_text(json.dumps(override, indent=2) + '\n', encoding='utf-8')
        command = ['docker', 'compose', '-p', project, '-f', str(ROOT / 'compose.yaml'), '-f', str(override_path)]
        config = json.loads(run([*command, 'config', '--format', 'json']))
        validate_configuration(config, project, volume, port, evidence['images'])
        require(config['name'] == project and config['volumes']['state']['name'] == volume, 'rehearsal_check_failed')
        require(not config['volumes']['state'].get('external', False), 'rehearsal_check_failed')
        require(set(config['services']) == {'api', 'web'}, 'rehearsal_check_failed')
        api = config['services']['api']
        web = config['services']['web']
        require(api['image'] == release['images']['api'] and web['image'] == release['images']['web'], 'rehearsal_check_failed')
        require(len(api['volumes']) == 1 and api['volumes'][0]['type'] == 'volume', 'rehearsal_check_failed')
        require(api['volumes'][0]['source'] == 'state' and api['volumes'][0]['target'] == '/app/.local', 'rehearsal_check_failed')
        require(not web.get('volumes') and (not api.get('ports')), 'rehearsal_check_failed')
        require(len(web['ports']) == 1 and web['ports'][0]['host_ip'] == '127.0.0.1' and (int(web['ports'][0]['published']) == port), 'rehearsal_check_failed')
        require(api['environment']['AIN_AGENT_JOBS'] == api['environment']['AIN_MONITOR_ENABLED'] == '0', 'rehearsal_check_failed')
        for service in (api, web):
            require(service['read_only'] and service['cap_drop'] == ['ALL'] and (service['restart'] == 'no'), 'rehearsal_check_failed')
            require('no-new-privileges:true' in service['security_opt'], 'rehearsal_check_failed')
        require(not run(['docker', 'ps', '-aq', '--filter', 'label=com.docker.compose.project=' + project]).strip(), 'rehearsal_check_failed')
        require(not run(['docker', 'volume', 'ls', '-q', '--filter', 'name=^' + volume + '$']).strip(), 'rehearsal_check_failed')
        report['checks']['fresh_isolated_pinned_configuration'] = True
        report['images'] = release['images']
        (case / 'resolved-compose.json').write_text(json.dumps(config, indent=2) + '\n', encoding='utf-8')
        password = secrets.token_urlsafe(32)
        seed = "\nimport json,sys,os\nfrom pathlib import Path\nfrom services.api.main import initialize\nfrom services.api.auth import AuthStore\ndatabase=Path(os.environ['AIN_DB_PATH'])\ninitialize(database);auth=AuthStore(database);password=json.loads(sys.stdin.read())['password']\nfor name,role in [('synthetic-admin','admin'),('synthetic-viewer','viewer')]:\n    auth.create_user(name,password,role)\nprint(json.dumps({'synthetic_accounts_created':2}))\n"
        stage = 'synthetic_seed'
        started = True
        print('Creating only a fresh isolated volume and two synthetic accounts.', flush=True)
        seeded = json.loads(run([*command, 'run', '--rm', '-T', '--no-deps', '--pull', 'never', '--entrypoint', 'python', 'api', '-c', seed], data=json.dumps({'password': password})))
        require(seeded['synthetic_accounts_created'] == 2, 'rehearsal_check_failed')
        stage = 'service_start'
        print(f'Starting pinned services on loopback port {port} for the rehearsal.', flush=True)
        run([*command, 'up', '-d', '--no-build', '--pull', 'never', '--wait', '--wait-timeout', '90'], timeout=150)
        stage = 'container_checks'
        smoke = verify(project, port)
        require(smoke['passed'], 'rehearsal_check_failed')
        report['container_checks'] = smoke['checks']
        for service in ('api', 'web'):
            cid = run([*command, 'ps', '-q', service]).strip()
            info = json.loads(run(['docker', 'inspect', cid]))[0]
            require(info['Image'] == release['images'][service], 'rehearsal_check_failed')
            if service == 'api':
                state_mounts = [m for m in info['Mounts'] if m['Destination'] == '/app/.local']
                require(len(state_mounts) == 1 and state_mounts[0]['Type'] == 'volume' and (state_mounts[0]['Name'] == volume), 'rehearsal_check_failed')
                require(all((m['Type'] == 'tmpfs' or m in state_mounts for m in info['Mounts'])), 'rehearsal_check_failed')
        report['checks']['running_images_and_private_volume'] = True
        stage = 'http_authentication'
        base = 'http://127.0.0.1:' + str(port)

        def client():
            return build_opener(HTTPCookieProcessor(CookieJar()))

        def request(opener, path, *, body=None, headers=None):
            data = None if body is None else json.dumps(body).encode()
            h = {'Accept': 'application/json', **(headers or {})}
            if data is not None:
                h['Content-Type'] = 'application/json'
            req = Request(base + path, data=data, headers=h)
            try:
                response = opener.open(req, timeout=15)
            except HTTPError as error:
                response = error
            with response:
                payload = response.read(2 * 1024 * 1024)
                try:
                    parsed = json.loads(payload)
                except (ValueError, UnicodeDecodeError):
                    parsed = None
                return (response.status, response.headers, payload, parsed)
        anonymous = client()
        status, headers, html, _ = request(anonymous, '/')
        require(status == 200 and b'Aviation' in html, 'rehearsal_check_failed')
        require(headers.get('Content-Security-Policy') and headers.get('X-Content-Type-Options') == 'nosniff', 'rehearsal_check_failed')
        report['checks']['dashboard_and_security_headers'] = True
        require(request(anonymous, '/api/v1/research/summary')[0] == 401, 'rehearsal_check_failed')
        report['checks']['anonymous_research_denied'] = True
        origin = {'Origin': base}
        for username, role in [('synthetic-admin', 'admin'), ('synthetic-viewer', 'viewer')]:
            opener = client()
            status, headers, _, login = request(opener, '/api/v1/auth/login', body={'username': username, 'password': password}, headers=origin)
            require(status == 200 and login['authenticated'] and (login['user']['role'] == role), 'rehearsal_check_failed')
            cookie = headers.get('Set-Cookie', '')
            require(cookie.startswith('ain_release_session=') and 'HttpOnly' in cookie and ('SameSite=strict' in cookie), 'rehearsal_check_failed')
            csrf = login['csrf_token']
            authorized = {**origin, 'X-CSRF-Token': csrf}
            require(request(opener, '/api/v1/auth/session')[3]['user']['role'] == role, 'rehearsal_check_failed')
            require(request(opener, '/api/v1/research/summary')[0] == 200, 'rehearsal_check_failed')
            if role == 'viewer':
                require(request(opener, '/api/v1/research/predict', body={}, headers=authorized)[0] == 403, 'rehearsal_check_failed')
                report['checks']['viewer_mutation_denied'] = True
            require(request(opener, '/api/v1/auth/logout', body={}, headers=origin)[0] == 403, 'rehearsal_check_failed')
            require(request(opener, '/api/v1/auth/logout', body={}, headers={**authorized, 'Origin': 'https://untrusted.example'})[0] == 403, 'rehearsal_check_failed')
            require(request(opener, '/api/v1/auth/logout', body={}, headers=authorized)[0] == 200, 'rehearsal_check_failed')
            require(request(opener, '/api/v1/auth/session')[3]['authenticated'] is False, 'rehearsal_check_failed')
            report['checks'][role + '_login_read_logout'] = True
        report['checks']['origin_and_csrf_enforced'] = True
        if after_auth is not None:
            stage = hook_stage
            report[hook_name] = after_auth(run, command, request, client, project, port)
            require(report[hook_name]['passed'], 'rehearsal_check_failed')
        report['passed'] = True
    except Exception as error:
        report.update(failed_stage=stage, error=str(error)[-2500:])
    finally:
        if started and command:
            try:
                run([*command, 'stop', '--timeout', '10'], timeout=45)
                require(not run(['docker', 'ps', '-q', '--filter', 'label=com.docker.compose.project=' + project]).strip(), 'rehearsal_check_failed')
                report['isolated_services_stopped'] = True
            except Exception as error:
                report.update(passed=False, cleanup_error=str(error)[-1500:], isolated_services_stopped=False)
        report['scope'] = 'Synthetic local HTTP and container checks; no real model inference, browser interaction, cloud deployment or production qualification.'
        target = ROOT / '.local/rehearsal-reports' / (report_prefix + '-' + key[:12] + '.json')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        (case / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'passed': report['passed'], 'stage': stage, 'checks': report['checks'], 'isolated_services_stopped': report.get('isolated_services_stopped'), 'report': str(target), 'error': report.get('error'), 'production_ready': False}, indent=2))
    return 0 if report['passed'] else 2

def cli():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api-image', required=True)
    parser.add_argument('--web-image', required=True)
    parser.add_argument('--expected-revision', required=True)
    parser.add_argument('--port', type=int, default=18090)
    parser.add_argument('--scenario', choices=('http', 'outage', 'automatic_restart', 'restore'), default='http')
    args = parser.parse_args()
    try:
        return main(api_image=args.api_image, web_image=args.web_image, expected_revision=args.expected_revision, port=args.port, scenario=args.scenario)
    except (ValueError, OSError, KeyError, TypeError):
        print(json.dumps({'passed': False, 'error': 'rehearsal_admission_refused', 'production_ready': False}))
        return 2
if __name__ == '__main__':
    raise SystemExit(cli())
