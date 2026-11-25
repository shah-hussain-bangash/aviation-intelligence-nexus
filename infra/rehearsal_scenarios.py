"""Synthetic recovery scenario hooks; invoked only after HTTP isolation admission."""
import json, time, secrets
from pathlib import Path
from infra.rehearsal_admission import require

def outage(run, command, request, client, project, port):
    require(project.startswith('ain-http-check-') and project != 'ain-local-release' and (1024 <= port <= 65535), 'rehearsal_check_failed')

    def info(service):
        cid = run([*command, 'ps', '-a', '-q', service]).strip()
        result = json.loads(run(['docker', 'inspect', cid]))[0]
        require(result['Config']['Labels']['com.docker.compose.project'] == project, 'rehearsal_check_failed')
        require(result['Config']['Labels']['com.docker.compose.service'] == service, 'rehearsal_check_failed')
        return result
    api = info('api')
    web = info('web')
    mounts = [m for m in api['Mounts'] if m['Destination'] == '/app/.local']
    require(len(mounts) == 1 and mounts[0]['Type'] == 'volume' and (mounts[0]['Name'] == project + '_state'), 'rehearsal_check_failed')
    require(not any((m['Type'] == 'bind' for m in api['Mounts'])), 'rehearsal_check_failed')
    fingerprint_code = "\nimport hashlib,json,os,sqlite3\nfrom pathlib import Path\ndb=sqlite3.connect(Path(os.environ['AIN_DB_PATH']).as_uri()+'?mode=ro',uri=True)\ntry:\n    assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'\n    tables=('auth_users','auth_sessions','flights','imports','security_audit','research_runs')\n    rows={table:sorted(db.execute('SELECT * FROM '+table).fetchall(),key=repr) for table in tables}\n    assert len(rows['auth_users'])==2 and not rows['auth_sessions']\n    print(json.dumps({'sha256':hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest(),\n                      'row_counts':{table:len(values) for table,values in rows.items()}}))\nfinally:db.close()\n"

    def state():
        return json.loads(run([*command, 'exec', '-T', 'api', 'python', '-c', fingerprint_code]))
    before = state()
    observer = client()
    require(request(observer, '/__ain/ready')[0] == 200, 'rehearsal_check_failed')
    print('Stopping only the isolated API; checking readiness failure and dashboard availability.', flush=True)
    run([*command, 'stop', '--timeout', '10', 'api'], timeout=30)
    require(not info('api')['State']['Running'], 'rehearsal_check_failed')
    status, _, _, body = request(observer, '/__ain/ready')
    require(status == 503 and body['backend_ready'] is False, 'rehearsal_check_failed')
    frontend_status, _, html, _ = request(observer, '/')
    require(frontend_status == 200 and b'Aviation' in html, 'rehearsal_check_failed')
    proxy_status, _, _, proxy_body = request(observer, '/api/v1/research/summary')
    require(proxy_status == 503 and isinstance(proxy_body, dict), 'rehearsal_check_failed')
    during_web = info('web')
    require(during_web['Id'] == web['Id'] and during_web['State']['StartedAt'] == web['State']['StartedAt'], 'rehearsal_check_failed')
    print('Restarting only the isolated API and checking recovery.', flush=True)
    start = time.monotonic()
    run([*command, 'up', '-d', '--no-build', '--pull', 'never', '--no-deps', '--wait', '--wait-timeout', '90', 'api'], timeout=120)
    status, _, _, body = request(observer, '/__ain/ready')
    require(status == 200 and body['backend_ready'] is True, 'rehearsal_check_failed')
    require(request(observer, '/api/v1/research/summary')[0] == 401, 'rehearsal_check_failed')
    after = state()
    require(before == after, 'rehearsal_check_failed')
    recovered_api = info('api')
    recovered_web = info('web')
    require(recovered_api['Image'] == api['Image'] and recovered_web['Image'] == web['Image'], 'rehearsal_check_failed')
    require(recovered_web['Id'] == web['Id'] and recovered_web['State']['StartedAt'] == web['State']['StartedAt'], 'rehearsal_check_failed')
    return {'passed': True, 'checks': {'isolated_api_stop_confirmed': True, 'readiness_failed_503': True, 'dashboard_available_200': True, 'proxy_failed_closed_503': True, 'web_not_restarted': True, 'readiness_recovered_200': True, 'authentication_still_required': True, 'synthetic_logical_state_preserved': True, 'same_pinned_images': True}, 'synthetic_state_before': before, 'synthetic_state_after': after, 'observed_restart_and_probe_seconds': round(time.monotonic() - start, 3), 'automatic_failover_tested': False, 'production_rto_qualified': False, 'scope': 'Manually induced isolated API stop and explicit restart; dashboard checked over HTTP, not a browser.'}

def auto_restart(run, command, request, client, project, port):
    require(project.startswith('ain-http-check-') and project != 'ain-local-release' and (1024 <= port <= 65535), 'rehearsal_check_failed')

    def info(service):
        cid = run([*command, 'ps', '-a', '-q', service]).strip()
        value = json.loads(run(['docker', 'inspect', cid]))[0]
        require(value['Config']['Labels']['com.docker.compose.project'] == project, 'rehearsal_check_failed')
        require(value['Config']['Labels']['com.docker.compose.service'] == service, 'rehearsal_check_failed')
        return value
    api = info('api')
    web = info('web')
    cid = api['Id']
    mounts = [m for m in api['Mounts'] if m['Destination'] == '/app/.local']
    require(len(mounts) == 1 and mounts[0]['Type'] == 'volume' and (mounts[0]['Name'] == project + '_state'), 'rehearsal_check_failed')
    require(not any((m['Type'] == 'bind' for m in api['Mounts'])), 'rehearsal_check_failed')
    require(api['HostConfig']['RestartPolicy']['Name'] == 'no', 'rehearsal_check_failed')
    state_code = "\nimport hashlib,json,os,sqlite3\nfrom pathlib import Path\nwith sqlite3.connect(Path(os.environ['AIN_DB_PATH']).as_uri()+'?mode=ro',uri=True) as db:\n    assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'\n    rows={t:sorted(db.execute('SELECT * FROM '+t).fetchall(),key=repr) for t in\n          ('auth_users','auth_sessions','flights','imports','security_audit','research_runs')}\n    assert len(rows['auth_users'])==2 and not rows['auth_sessions']\n    print(json.dumps({'sha256':hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest(),\n                      'row_counts':{t:len(v) for t,v in rows.items()}}))\n"
    before = json.loads(run([*command, 'exec', '-T', 'api', 'python', '-c', state_code]))
    discover = "\nfrom pathlib import Path\nimport json,os\nfound=[]\nfor path in Path('/proc').iterdir():\n    if not path.name.isdigit() or int(path.name)<=1 or int(path.name)==os.getpid():continue\n    try:\n        args=(path/'cmdline').read_bytes().split(b'\\0')\n        if args[1:4]!=[b'-m',b'uvicorn',b'services.api.main:app']:continue\n        status=(path/'status').read_text()\n        assert 'PPid:\\t1\\n' in status\n        assert path.stat().st_uid==os.getuid()\n        found.append({'pid':int(path.name),'start_ticks':(path/'stat').read_text().split()[21]})\n    except FileNotFoundError:pass\nassert len(found)==1,'Unique Uvicorn child of container init required'\nprint(json.dumps(found[0]))\n"
    target = json.loads(run(['docker', 'exec', cid, 'python', '-c', discover]))
    observer = client()
    require(request(observer, '/__ain/ready')[0] == 200, 'rehearsal_check_failed')
    enabled = False
    try:
        print('Enabling bounded restart-on-failure only for the isolated API.', flush=True)
        run(['docker', 'update', '--restart', 'on-failure:3', cid])
        enabled = True
        policy = info('api')['HostConfig']['RestartPolicy']
        require(policy['Name'] == 'on-failure' and policy['MaximumRetryCount'] == 3, 'rehearsal_check_failed')
        time.sleep(10)
        since = str(int(time.time()) - 1)
        started = time.monotonic()
        kill_code = f"import os,signal,time;from pathlib import Path;p=Path('/proc/{target['pid']}');assert p.joinpath('stat').read_text().split()[21]=={target['start_ticks']!r};assert p.joinpath('cmdline').read_bytes().split(b'\\0')[1:4]==[b'-m',b'uvicorn',b'services.api.main:app'];time.sleep(.5);os.kill({target['pid']},signal.SIGKILL)"
        print('Injecting one Uvicorn process failure; waiting for Docker automatic recovery.', flush=True)
        run(['docker', 'exec', '-d', cid, 'python', '-c', kill_code])
        deadline = time.monotonic() + 120
        recovered = None
        observed_unready = False
        while time.monotonic() < deadline:
            current = info('api')
            require(current['Id'] == cid and current['Image'] == api['Image'], 'rehearsal_check_failed')
            status, _, _, body = request(observer, '/__ain/ready')
            if status == 503:
                observed_unready = True
            if current['RestartCount'] > api['RestartCount'] and status == 200 and (body.get('backend_ready') is True) and (current['State'].get('Health', {}).get('Status') == 'healthy'):
                recovered = current
                break
            time.sleep(1)
        require(recovered is not None, 'Automatic API restart not confirmed within 120 seconds')
        elapsed = round(time.monotonic() - started, 3)
        events = [json.loads(line) for line in run(['docker', 'events', '--since', since, '--until', str(int(time.time()) + 1), '--filter', 'container=' + cid, '--format', '{{json .}}']).splitlines() if line.strip()]
        dies = [e for e in events if e.get('Action') == 'die' and e.get('Actor', {}).get('Attributes', {}).get('exitCode') == '137']
        require(dies, 'Nonzero process-failure container exit evidence missing')
        require(any((e.get('Action') == 'start' for e in events)), 'Automatic container start event missing')
        require(recovered['RestartCount'] == api['RestartCount'] + 1, 'rehearsal_check_failed')
        require(recovered['State']['StartedAt'] != api['State']['StartedAt'], 'rehearsal_check_failed')
        after = json.loads(run([*command, 'exec', '-T', 'api', 'python', '-c', state_code]))
        require(after == before, 'rehearsal_check_failed')
        require(request(observer, '/api/v1/research/summary')[0] == 401, 'rehearsal_check_failed')
        require(request(observer, '/')[0] == 200, 'rehearsal_check_failed')
        web_after = info('web')
        require(web_after['Id'] == web['Id'] and web_after['State']['StartedAt'] == web['State']['StartedAt'], 'rehearsal_check_failed')
        result = {'passed': True, 'checks': {'bounded_restart_policy_verified': True, 'uvicorn_child_identity_verified': True, 'nonzero_exit_137_recorded': True, 'automatic_restart_count_incremented_once': True, 'same_api_container_and_image': True, 'readiness_and_container_health_recovered': True, 'web_not_restarted': True, 'authentication_still_required': True, 'synthetic_logical_state_preserved': True}, 'restart_count_before': api['RestartCount'], 'restart_count_after': recovered['RestartCount'], 'observed_unready_sample': observed_unready, 'observed_recovery_seconds': elapsed, 'synthetic_state_before': before, 'synthetic_state_after': after, 'automatic_failover_tested': False, 'production_rto_qualified': False, 'scope': 'Single process crash and Docker restart policy in an isolated synthetic container; no host reboot, health-only hang recovery or redundant-node failover.'}
    finally:
        if enabled:
            run(['docker', 'update', '--restart', 'no', cid])
            require(info('api')['HostConfig']['RestartPolicy']['Name'] == 'no', 'rehearsal_check_failed')
    result['checks']['original_restart_policy_restored'] = True
    return result

def recovery(run, command, request, client, project, port):
    require(project.startswith('ain-http-check-') and project != 'ain-local-release' and (1024 <= port <= 65535), 'rehearsal_check_failed')
    api_id = run([*command, 'ps', '-q', 'api']).strip()
    api = json.loads(run(['docker', 'inspect', api_id]))[0]
    require(api['Config']['Labels']['com.docker.compose.project'] == project, 'rehearsal_check_failed')
    mounts = [m for m in api['Mounts'] if m['Destination'] == '/app/.local']
    source = project + '_state'
    destination = project + '_restored'
    require(len(mounts) == 1 and mounts[0]['Type'] == 'volume' and (mounts[0]['Name'] == source), 'rehearsal_check_failed')
    require(not any((m['Type'] == 'bind' for m in api['Mounts'])), 'rehearsal_check_failed')
    password = secrets.token_urlsafe(32)
    seed = '\nimport json,os,sys,sqlite3\nfrom pathlib import Path\nfrom services.api.auth import AuthStore\ndb=Path(os.environ[\'AIN_DB_PATH\']);auth=AuthStore(db)\nauth.create_user(\'synthetic-recovery\',json.loads(sys.stdin.read())[\'password\'],\'researcher\')\nwith sqlite3.connect(db) as connection:\n    connection.execute("INSERT INTO flights(source,source_record_id,flight_date,carrier,origin,destination) VALUES(\'synthetic_restore_fixture\',\'1\',\'2025-01-01\',\'XX\',\'AAA\',\'BBB\')")\nprint(json.dumps({\'synthetic_fixture_created\':True}))\n'
    seeded = json.loads(run([*command, 'exec', '-T', 'api', 'python', '-c', seed], data=json.dumps({'password': password})))
    require(seeded['synthetic_fixture_created'], 'rehearsal_check_failed')
    opener = client()
    origin = {'Origin': 'http://127.0.0.1:' + str(port)}
    login = request(opener, '/api/v1/auth/login', body={'username': 'synthetic-recovery', 'password': password}, headers=origin)
    require(login[0] == 200 and login[3]['user']['role'] == 'researcher', 'rehearsal_check_failed')
    require(request(opener, '/api/v1/auth/session')[3]['authenticated'], 'rehearsal_check_failed')
    print('Stopping only the isolated services before taking their synthetic backup.', flush=True)
    run([*command, 'stop', '--timeout', '10'], timeout=40)
    snapshot = "\nimport json\nfrom infra.recovery import backup,checksum\nfrom pathlib import Path\nmanifest=backup('/app/.local/active','/app/.local/http-backup')\nassert manifest['database']['row_counts']['flights']==1\nassert manifest['database']['row_counts']['auth_sessions']==1\nprint(json.dumps({'manifest_sha256':checksum(Path('/app/.local/http-backup/manifest.json')),\n                  'snapshot_id':manifest['snapshot_id'],'row_counts':manifest['database']['row_counts']}))\n"
    backup = json.loads(run([*command, 'run', '--rm', '-T', '--no-deps', '--pull', 'never', '--entrypoint', 'python', 'api', '-c', snapshot]))
    require(not run(['docker', 'volume', 'ls', '-q', '--filter', 'name=^' + destination + '$']).strip(), 'rehearsal_check_failed')
    created = run(['docker', 'volume', 'create', '--label', 'ain.synthetic-recovery=' + project, destination]).strip()
    require(created == destination, 'rehearsal_check_failed')
    restore = "\nimport json\nfrom pathlib import Path\nfrom infra.recovery import restore,checksum\nsource=Path('/source/http-backup');before=checksum(source/'manifest.json')\nreceipt=restore(source,'/app/.local/active')\nassert checksum(source/'manifest.json')==before\nassert receipt['flight_records']==1 and receipt['revoked_session_rows']==1\nassert receipt['sessions_revoked'] and receipt['session_revocation_audited']\nprint(json.dumps({'receipt':receipt,'manifest_sha256':before}))\n"
    print('Restoring into a new isolated volume; original synthetic state is retained.', flush=True)
    result = json.loads(run(['docker', 'run', '--rm', '--network', 'none', '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true', '--pids-limit', '128', '--memory', '1g', '--tmpfs', '/tmp:size=64m,mode=1777', '--mount', 'type=volume,source=' + source + ',target=/source,readonly', '--mount', 'type=volume,source=' + destination + ',target=/app/.local', '-e', 'AIN_ENV=local', '-e', 'AIN_CONTAINER=1', '-e', 'AIN_AGENT_JOBS=0', '-e', 'AIN_MONITOR_ENABLED=0', '-e', 'AIN_STATE_ROOT=/app/.local/active', '-e', 'AIN_DB_PATH=/app/.local/active/ain.sqlite3', '-e', 'AIN_SESSION_COOKIE=ain_release_session', '--entrypoint', 'python', api['Image'], '-c', restore]))
    require(result['manifest_sha256'] == backup['manifest_sha256'], 'rehearsal_check_failed')
    require(result['receipt']['snapshot_id'] == backup['snapshot_id'], 'rehearsal_check_failed')
    switch_path = Path(command[-1]).with_name('restored-volume.override.json')
    switch_path.write_text(json.dumps({'volumes': {'state': {'name': destination, 'external': False}}}, indent=2) + '\n')
    restored_command = [*command, '-f', str(switch_path)]
    config = json.loads(run([*restored_command, 'config', '--format', 'json']))
    require(config['name'] == project and config['volumes']['state']['name'] == destination, 'rehearsal_check_failed')
    require(config['services']['api']['image'] == api['Image'], 'rehearsal_check_failed')
    require(len(config['services']['api']['volumes']) == 1, 'rehearsal_check_failed')
    require(config['services']['api']['volumes'][0]['source'] == 'state', 'rehearsal_check_failed')
    print('Starting the isolated dashboard against restored state and verifying HTTP access.', flush=True)
    run([*restored_command, 'up', '-d', '--no-build', '--pull', 'never', '--wait', '--wait-timeout', '90'], timeout=150)
    restored_id = run([*restored_command, 'ps', '-q', 'api']).strip()
    restored_info = json.loads(run(['docker', 'inspect', restored_id]))[0]
    require(restored_info['Config']['Labels']['com.docker.compose.project'] == project, 'rehearsal_check_failed')
    require(restored_info['Image'] == api['Image'], 'rehearsal_check_failed')
    restored_mounts = [m for m in restored_info['Mounts'] if m['Destination'] == '/app/.local']
    require(len(restored_mounts) == 1 and restored_mounts[0]['Name'] == destination, 'rehearsal_check_failed')
    require(request(client(), '/__ain/ready')[3]['backend_ready'] is True, 'rehearsal_check_failed')
    require(request(opener, '/api/v1/auth/session')[3]['authenticated'] is False, 'rehearsal_check_failed')
    require(request(opener, '/api/v1/research/summary')[0] == 401, 'rehearsal_check_failed')
    fresh = client()
    login = request(fresh, '/api/v1/auth/login', body={'username': 'synthetic-recovery', 'password': password}, headers=origin)
    require(login[0] == 200 and login[3]['user']['role'] == 'researcher', 'rehearsal_check_failed')
    summary = request(fresh, '/api/v1/research/summary')
    require(summary[0] == 200 and summary[3]['dataset']['records'] == 0, 'rehearsal_check_failed')
    inspect_state = "\nimport json,os,sqlite3\nwith sqlite3.connect(os.environ['AIN_DB_PATH']) as db:\n    rows=db.execute('SELECT source,source_record_id,carrier,origin,destination FROM flights').fetchall()\n    assert rows==[('synthetic_restore_fixture','1','XX','AAA','BBB')]\n    assert db.execute('SELECT COUNT(*) FROM auth_users').fetchone()[0]==3\nprint(json.dumps({'synthetic_row_preserved':True,'accounts':3}))\n"
    state = json.loads(run([*restored_command, 'exec', '-T', 'api', 'python', '-c', inspect_state]))
    require(state['synthetic_row_preserved'], 'rehearsal_check_failed')
    require(request(fresh, '/api/v1/auth/logout', body={}, headers={**origin, 'X-CSRF-Token': login[3]['csrf_token']})[0] == 200, 'rehearsal_check_failed')
    require(request(fresh, '/api/v1/auth/session')[3]['authenticated'] is False, 'rehearsal_check_failed')
    require(request(client(), '/')[0] == 200, 'rehearsal_check_failed')
    return {'passed': True, 'checks': {'stopped_source_backup': True, 'new_volume_restored': True, 'snapshot_receipt_binding': True, 'restore_revocation_audited': True, 'restored_volume_selected_in_running_api': True, 'restored_readiness': True, 'old_http_session_rejected': True, 'same_credentials_http_login': True, 'restored_synthetic_row_and_accounts_preserved': True, 'synthetic_row_excluded_from_real_data_summary': True, 'restored_http_logout': True}, 'snapshot_id': backup['snapshot_id'], 'manifest_sha256': backup['manifest_sha256'], 'receipt': result['receipt'], 'restored_volume': destination, 'encrypted': False, 'independent_recovery_qualified': False, 'scope': 'Same-host synthetic backup restored into a fresh Docker volume and served over HTTP; no real model, encrypted or off-host recovery qualification.'}
