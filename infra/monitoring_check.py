"""Disposable authenticated monitoring checks; no primary services are stopped."""
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import secrets
from unittest.mock import patch
from fastapi.testclient import TestClient
from services.api.main import create_app
from services.api.monitoring import Monitor
from services.api.paths import ROOT


def exercise(output):
    output=Path(output).resolve()
    if not output.is_relative_to((ROOT/'.local').resolve()) or output==(ROOT/'.local').resolve() or output.exists():raise ValueError('Choose a new private monitoring directory under .local')
    output.mkdir(parents=True);password=secrets.token_urlsafe(24);origin={'Origin':'http://127.0.0.1:8080'}
    with patch.dict(os.environ,{'AIN_MONITOR_ENABLED':'0','AIN_AGENT_JOBS':'0'}):app=create_app(output/'fixture.sqlite3',research_model_directory=output/'missing-model')
    with TestClient(app) as client:
        path='/api/v1/research/monitoring';checks={'anonymous_denied':client.get(path).status_code==401}
        for name,role in [('fixture-monitor-admin','admin'),('fixture-monitor-viewer','viewer')]:app.state.auth_store.create_user(name,password,role)
        def login(name):
            response=client.post('/api/v1/auth/login',json={'username':name,'password':password},headers=origin)
            if response.status_code!=200:raise RuntimeError('Fixture sign-in failed')
            return {**origin,'X-CSRF-Token':response.json()['csrf_token']}
        login('fixture-monitor-viewer');checks['viewer_denied']=client.get(path).status_code==403;headers=login('fixture-monitor-admin')
        monitor=app.state.monitor;clock=[0.0];health=[True];monitor.clock=lambda:clock[0];monitor.started=0;monitor.enabled=True
        monitor.probes={'database':lambda:True,'active_model':lambda:True,'local_ai_models':lambda:health[0]}
        monitor.sample();healthy=client.get(path).json();checks['fresh_healthy']=healthy['state']=='healthy' and all(healthy['components'].values())
        health[0]=False;monitor.sample();degraded=client.get(path).json();checks['component_failure_degraded']=degraded['state']=='degraded' and degraded['components']['local_ai_models'] is False
        health[0]=True;monitor.sample();recovered=client.get(path).json();checks['recovery_recorded']=recovered['state']=='healthy' and recovered['transitions'][0]['state']=='recovered'
        clock[0]=90;expired=client.get(path).json();checks['exact_expiry_unknown']=expired['state']=='unknown' and expired['components']=={}
        clock[0]=-1;bad_clock=client.get(path).json();checks['backward_clock_unknown']=bad_clock['state']=='unknown' and bad_clock['sample_age_seconds'] is None
        clock[0]=91
        with patch.object(Path,'replace',side_effect=OSError('PRIVATE filesystem detail')):monitor.sample()
        persistence=client.get(path).json();checks['write_failure_degraded']=persistence['state']=='degraded' and persistence['persistence_ok'] is False
        monitor.record(200,float('nan'));monitor.record(200,-1);timing=client.get(path).json();checks['invalid_timings_counted']=timing['latency']['invalid_samples']==2
        response=client.post('/api/v1/research/predict?private=PRIVATE-MARKER',headers=headers,json={'carrier':'AA','origin':'JFK','destination':'LAX','flight_date':'2025-05-15','scheduled_departure':'09:00'})
        failed=client.get(path).json();checks['real_api_failure_recorded']=response.status_code==503 and failed['request_counts']['5xx']>=1 and failed['recent_server_failures'][0]['status']==503
        monitor.sample();final=client.get(path).json();checks['persistence_recovered']=final['state']=='healthy' and final['persistence_ok'] is True
        serialized=json.dumps([healthy,degraded,recovered,expired,bad_clock,persistence,timing,failed,final],allow_nan=False)
        checks['request_and_credential_redaction']=all(value not in serialized for value in [password,'PRIVATE','JFK','LAX','fixture-monitor-admin'])
        restarted=Monitor(output/'monitoring.json',monitor.probes,enabled=True,clock=lambda:92);checks['restart_does_not_reuse_health']=restarted.snapshot()['state']=='unknown' and restarted.snapshot()['components']=={}
    result={'format':'ain-monitoring-integrity-check-v1','checked_at':datetime.now(timezone.utc).isoformat(),
        'scope':'In-process authenticated HTTP with disposable accounts/database, simulated component probes/clock/write failure, and a real missing-model API response. No primary state, account, provider or service is changed or stopped.',
        'checks':checks,'passed':all(checks.values()),'snapshots':{'healthy':healthy,'degraded':degraded,'recovered':recovered,'expired':expired,'invalid_clock':bad_clock,'persistence_failure':persistence,'invalid_timings':timing,'api_failure':failed,'final':final},'production_ready':False}
    (output/'report.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8');return result


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);result=exercise(parser.parse_args().output)
    print(json.dumps({'checks':result['checks'],'passed':result['passed']},indent=2));raise SystemExit(0 if result['passed'] else 1)
