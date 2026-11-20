"""Explicit local-release API outage drill; always attempts recovery before returning."""
import json
from pathlib import Path
import subprocess
from urllib.error import HTTPError
from urllib.request import urlopen
from infra.verify_deployment import compose,verify

PROJECT='ain-local-release'


def facts():
    code="from services.api.paths import STATE;from infra.recovery import database_facts;import json;print(json.dumps(database_facts(STATE/'ain.sqlite3')))"
    return json.loads(compose(PROJECT,'exec','-T','api','python','-c',code))


def drill():
    before=facts();readiness_failed=False;liveness_preserved=False
    try:
        compose(PROJECT,'stop','api')
        try:
            with urlopen('http://127.0.0.1:8090/__ain/ready',timeout=5) as response:pass
        except HTTPError as error:readiness_failed=error.code==503
        with urlopen('http://127.0.0.1:8090/__ain/health',timeout=5) as response:liveness_preserved=response.status==200
    finally:
        compose(PROJECT,'start','api')
        compose(PROJECT,'up','-d','--wait','--wait-timeout','90','api','web')
    after=facts();steady=verify(PROJECT,8090)
    return {'scope':'Controlled local API stop/start on this AIN release only; not an infrastructure disaster simulation',
        'readiness_returned_503':readiness_failed,'frontend_liveness_preserved':liveness_preserved,
        'row_counts_preserved':before==after,'services_healthy_after_restart':steady['passed'],
        'flight_records_after_restart':after['row_counts']['flights'],
        'passed':readiness_failed and liveness_preserved and before==after and steady['passed'],'production_ready':False}


if __name__=='__main__':
    result=drill();output=Path('.local/recovery/outage-drill.json');output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,indent=2));raise SystemExit(0 if result['passed'] else 1)
