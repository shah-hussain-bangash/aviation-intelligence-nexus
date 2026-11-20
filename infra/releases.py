"""Pinned local application rollback drill. Mutations target only ain-rollback-drill."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
from infra.recovery import private_target
from infra.verify_deployment import compose, verify
from services.api.paths import ROOT

PROJECT = 'ain-rollback-drill'
PORT = 8091
CONTRACTS = ('services/api/paths.py', 'services/api/prediction.py', 'agents/jobs.py',
             'agents/store.py', 'agents/runtime.py', 'rag/index.py', 'infra/recovery.py')
OVERRIDE = ROOT / '.local/releases/rollback-drill.override.json'


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def docker(*args):
    return subprocess.check_output(['docker', *args], cwd=ROOT, text=True, timeout=150)


def validate_release(release):
    if release.get('format') != 'ain-local-release-v1' or type(release.get('schema_version')) is not int:
        raise ValueError('Unsupported release record')
    if set(release.get('images', {})) != {'api', 'web'} or set(release.get('contracts', {})) != set(CONTRACTS):
        raise ValueError('Incomplete pinned release')
    if any(not re.fullmatch(r'sha256:[0-9a-f]{64}', value) for value in release['images'].values()):
        raise ValueError('Only local immutable image IDs are accepted')
    if any(not re.fullmatch(r'[0-9a-f]{64}', value) for value in release['contracts'].values()):
        raise ValueError('Invalid state-contract fingerprint')
    if not re.fullmatch(r'[a-z0-9-]{1,64}', release.get('source_revision', '')):
        raise ValueError('Invalid source revision')
    return release


def image_revision(image):
    info = json.loads(docker('image', 'inspect', image))[0]
    if info['Id'] != image or info.get('Os') != 'linux' or info.get('Architecture') != 'amd64':
        raise ValueError('Unavailable or unsupported pinned image')
    return info['Config'].get('Labels', {}).get('org.opencontainers.image.revision')


def inspect_release(images):
    if set(images) != {'api', 'web'} or any(not re.fullmatch(r'sha256:[0-9a-f]{64}', image) for image in images.values()):
        raise ValueError('Use pinned API and web image IDs')
    revisions = [image_revision(images[service]) for service in ('api', 'web')]
    if revisions[0] != revisions[1]:
        raise ValueError('API and web revisions differ')
    code = ('import json,hashlib;from pathlib import Path;from services.api.paths import SCHEMA_VERSION;'
            f'paths={CONTRACTS!r};'
            'print(json.dumps({"schema_version":SCHEMA_VERSION,"contracts":{p:hashlib.sha256(Path(p).read_text(encoding="utf-8").encode()).hexdigest() for p in paths}}))')
    contracts = json.loads(docker('run', '--rm', '--network', 'none', '--read-only', '--cap-drop', 'ALL',
        '--security-opt', 'no-new-privileges:true', '--entrypoint', 'python', images['api'], '-c', code))
    return validate_release({'format': 'ain-local-release-v1', 'captured_at': timestamp(),
        'source_revision': revisions[0], 'images': images, **contracts})


def deployed_images(project):
    images = {}
    for service in ('api', 'web'):
        identifier = compose(project, 'ps', '-a', '-q', service).strip()
        if not identifier:
            raise RuntimeError('Required deployment container is missing')
        container = json.loads(docker('inspect', identifier))[0]
        if container['Config']['Labels'].get('com.docker.compose.project') != project:
            raise ValueError('Unexpected container project')
        if service == 'api' and project == PROJECT:
            mounts = [m for m in container['Mounts'] if m['Destination'] == '/app/.local']
            if len(mounts) != 1 or mounts[0]['Type'] != 'volume' or mounts[0].get('Name') != PROJECT + '_state':
                raise ValueError('Drill must use its own named state volume')
        images[service] = container['Image']
    return images


def compatible(current, target, state):
    validate_release(current); validate_release(target)
    if current['schema_version'] != target['schema_version'] or state['schema_version'] != current['schema_version']:
        raise ValueError('Schema rollback is not supported')
    if current['contracts'] != target['contracts']:
        raise ValueError('State contracts changed; rollback is not qualified')
    if state['active_jobs'] != 0:
        raise ValueError('Waiting or running investigations block release changes')


def override_document(release):
    validate_release(release)
    return {'services': {'api': {'image': release['images']['api'], 'environment': {'AIN_AGENT_JOBS': '0'}},
                         'web': {'image': release['images']['web']}}}


def write_override(release):
    output = private_target(OVERRIDE)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix('.tmp')
    temporary.write_text(json.dumps(override_document(release), indent=2) + '\n', encoding='utf-8')
    temporary.replace(output)


def switch(release):
    # Hard-coded mutation scope; never select the main project, a host path or another volume.
    write_override(release)
    env = {**os.environ, 'AIN_WEB_PORT': str(PORT)}
    command = ['docker', 'compose', '-p', PROJECT, '-f', str(ROOT / 'compose.yaml'), '-f', str(OVERRIDE)]
    subprocess.run([*command, 'stop', 'web'], cwd=ROOT, env=env, check=True, timeout=30)
    subprocess.run([*command, 'up', '-d', '--no-build', '--pull', 'never', '--wait', '--wait-timeout', '90', 'api', 'web'],
                   cwd=ROOT, env=env, check=True, timeout=150)
    if deployed_images(PROJECT) != release['images']:
        raise RuntimeError('Pinned image identity differs after switching')
    checks = verify(PROJECT, PORT)
    if not checks['passed']:
        raise RuntimeError('Release health or isolation checks failed')
    return checks


def state_facts():
    code = '''import json,hashlib,sqlite3
from services.api.paths import STATE
from infra.recovery import database_facts,checksum
from services.api.prediction import ResearchPredictor,Scenario
db=STATE/'ain.sqlite3'
facts=database_facts(db)
with sqlite3.connect(db) as connection:
 accounts=connection.execute('SELECT id,username,password_hash,role,active FROM auth_users ORDER BY id').fetchall()
 active=connection.execute("SELECT COUNT(*) FROM agent_runs WHERE json_extract(result_json,'$.state') IN ('queued','running')").fetchone()[0]
scenario=Scenario(carrier='AA',origin='JFK',destination='LAX',flight_date='2025-05-15',scheduled_departure='09:00')
prediction=ResearchPredictor(STATE/'models/delay-v2').predict(scenario)
print(json.dumps({**facts,'active_jobs':active,'account_fingerprint':hashlib.sha256(json.dumps(accounts).encode()).hexdigest(),'model_sha256':checksum(STATE/'models/delay-v2/model.joblib'),'index_sha256':checksum(STATE/'knowledge/index.json'),'probability':prediction['arrival_delay_15_probability']}))'''
    # Captured internally; account fingerprints and personal paths are excluded from public receipts.
    return json.loads(compose(PROJECT, 'exec', '-T', 'api', 'python', '-c', code))


def drill(current, target):
    # Verify retained local images still match captured source/state contract records.
    for release in (current, target):
        actual = inspect_release(release['images'])
        if any(actual[key] != release[key] for key in ('schema_version', 'contracts', 'source_revision')):
            raise ValueError('Pinned release no longer matches its record')
    if current['source_revision'] == target['source_revision'] or current['images'] == target['images']:
        raise ValueError('The drill requires a genuinely different recorded version')
    if deployed_images(PROJECT) != current['images'] or not verify(PROJECT, PORT)['passed']:
        raise ValueError('Start the recorded candidate on the isolated drill project first')
    before = state_facts()
    compatible(current, target, before)
    rolled_back = False
    target_state = None
    try:
        switch(target)
        target_state = state_facts()
        if target_state != before:
            raise RuntimeError('State or prediction changed in the rollback target')
        rolled_back = True
    finally:
        # Always try returning the isolated drill to its known starting candidate.
        switch(current)
    after = state_facts()
    preserved = before == after
    if not rolled_back or not preserved:
        raise RuntimeError('Drill did not preserve the recorded state')
    return {'format': 'ain-rollback-drill-v1', 'checked_at': timestamp(),
        'scope': 'Separate restored local volume; main deployment not changed by this drill',
        'candidate_revision': current['source_revision'], 'rollback_revision': target['source_revision'],
        'candidate_images': current['images'], 'rollback_images': target['images'],
        'schema_version': before['schema_version'], 'flight_records': before['row_counts']['flights'],
        'pinned_images_verified': True, 'same_volume_preserved': True, 'row_counts_preserved': True,
        'account_records_preserved': True, 'model_index_preserved': True, 'prediction_parity': True,
        'prediction_probability': before['probability'], 'candidate_returned_healthy': True,
        'rollback_target_healthy': True, 'active_jobs_at_start': 0, 'production_qualified': False}


def load_release(path):
    path = Path(path)
    if path.stat().st_size > 64000:
        raise ValueError('Oversized release record')
    return validate_release(json.loads(path.read_text(encoding='utf-8')))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['capture', 'inspect', 'prepare', 'drill'])
    parser.add_argument('--project', default='ain-local-release')
    parser.add_argument('--api-image'); parser.add_argument('--web-image')
    parser.add_argument('--current'); parser.add_argument('--target'); parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = private_target(args.output)
    if output.exists():
        raise FileExistsError('Release evidence output already exists')
    if args.action == 'capture':
        result = inspect_release(deployed_images(args.project))
    elif args.action == 'inspect':
        result = inspect_release({'api': args.api_image, 'web': args.web_image})
    elif args.action == 'prepare':
        result = load_release(args.current)
        write_override(result)
    else:
        result = drill(load_release(args.current), load_release(args.target))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
