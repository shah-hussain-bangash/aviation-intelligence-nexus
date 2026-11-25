"""Verify packaged synthetic recovery with explicitly pinned local images; no build or deployment."""
import argparse, json, subprocess
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4
from infra.rehearsal_admission import admit_images, require
from infra.releases import inspect_release
from infra.state_contracts import current_contract_digest, contract_digest
from infra.rehearsal_admission import toolkit_identity
from services.api.paths import ROOT
PROBE = ROOT / 'infra/fixtures/packaged_recovery_probe.py'

def run_check(api_image, web_image, expected_revision):
    images = {'api': api_image, 'web': web_image}
    admit_images(images, expected_revision)
    case = ROOT / '.local/packaged-image-recovery' / uuid4().hex
    case.mkdir(parents=True, exist_ok=False)
    report = {'format': 'ain-packaged-image-recovery-v1', 'passed': False, 'checked_at': datetime.now(timezone.utc).isoformat(), 'source_revision': expected_revision, 'toolkit_identity': toolkit_identity(), 'images': images, 'synthetic_only': True, 'primary_state_accessed': False, 'deployment_performed': False, 'production_ready': False}
    launched = False
    try:
        release = inspect_release(images)
        require(release['source_revision'] == expected_revision and release['schema_version'] == 8, 'image_revision_or_schema_mismatch')
        require(contract_digest(release['contracts']) == current_contract_digest(), 'selected_state_contracts_mismatch')
        report['release'] = release
        command = ['docker', 'run', '--rm', '-i', '--name', 'ain-image-recovery-check-' + case.name[:12], '--network', 'none', '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true', '--pids-limit', '128', '--memory', '1g', '--cpus', '2', '--tmpfs', '/tmp:rw,size=64m,mode=1777', '--tmpfs', '/app/.local:rw,size=128m,uid=10001,gid=10001,mode=0700', '-e', 'AIN_ENV=local', '-e', 'AIN_CONTAINER=1', '-e', 'AIN_AGENT_JOBS=0', '-e', 'AIN_MONITOR_ENABLED=0', '-e', 'AIN_SESSION_COOKIE=ain_release_session', '-e', 'AIN_STATE_ROOT=/app/.local/active', '-e', 'AIN_DB_PATH=/app/.local/active/ain.sqlite3', '--entrypoint', 'python', api_image, '-']
        command[command.index('--network'):command.index('--network')] = ['--label', 'ain.synthetic-recovery=' + case.name]
        launched = True
        result = subprocess.run(command, cwd=ROOT, input=PROBE.read_text(encoding='utf-8'), text=True, capture_output=True, timeout=180)
        require(result.returncode == 0, 'packaged_recovery_failed')
        recovery = json.loads(result.stdout)
        require(recovery['passed'] and all((v is True for v in recovery['checks'].values())), 'packaged_checks_incomplete')
        report.update(passed=True, packaged_recovery=recovery)
    except (ValueError, OSError, subprocess.SubprocessError, KeyError, TypeError):
        report['error'] = 'packaged_image_recovery_unverified'
    finally:
        if launched:
            try:
                # The client can time out before Docker removes its temporary container.
                ids = subprocess.check_output(['docker', 'ps', '-aq', '--filter',
                       'label=ain.synthetic-recovery=' + case.name], text=True, timeout=20).split()
                require(len(ids) <= 1, 'unexpected_probe_container_set')
                for identifier in ids:
                    info = json.loads(subprocess.check_output(['docker', 'inspect', identifier], text=True, timeout=20))[0]
                    require(info['Config']['Labels'].get('ain.synthetic-recovery') == case.name
                            and info['Name'] == '/ain-image-recovery-check-' + case.name[:12], 'probe_identity_mismatch')
                    subprocess.run(['docker', 'rm', '-f', identifier], check=True, capture_output=True, timeout=30)
                report['temporary_probe_cleaned'] = True
            except (ValueError, OSError, subprocess.SubprocessError, KeyError, TypeError):
                report.update(passed=False, error='probe_cleanup_unverified')
    target = case / 'report.json'
    target.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'report': str(target), 'production_ready': False}, indent=2))
    return 0 if report['passed'] else 2

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api-image', required=True)
    parser.add_argument('--web-image', required=True)
    parser.add_argument('--expected-revision', required=True)
    args = parser.parse_args()
    try:
        return run_check(args.api_image, args.web_image, args.expected_revision)
    except (ValueError, OSError):
        print(json.dumps({'passed': False, 'error': 'rehearsal_admission_refused', 'production_ready': False}))
        return 2
if __name__ == '__main__':
    raise SystemExit(main())
