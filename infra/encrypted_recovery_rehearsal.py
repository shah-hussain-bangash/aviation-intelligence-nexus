"""Encrypt only the measured synthetic schema-8 snapshot; never select primary state."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, json, os, shutil, subprocess, sys
from infra.rehearsal_admission import admit_images, require
from infra.releases import inspect_release
from infra.rehearsal_admission import toolkit_identity
from uuid import uuid4
ROOT = Path(__file__).resolve().parents[1]
from infra.recovery import verify, checksum, database_facts
from infra.sealed_recovery import load_key, seal, restore_sealed, Cobblestone128Encryptor
from infra.verify_restore_evidence import verify_evidence
from infra.state_contracts import current_contract_digest, contract_digest

def run_check(restore_report, key_file, expected_revision):
    key_id = uuid4().hex
    case = ROOT / '.local/current-encrypted-recovery' / key_id
    case.mkdir(parents=True, exist_ok=False)
    report = {'format': 'ain-current-encrypted-recovery-v1', 'passed': False, 'checked_at': datetime.now(timezone.utc).isoformat(), 'checks': {}, 'synthetic_only': True, 'primary_state_accessed': False, 'plaintext_sources_retained': True, 'independent_recovery_qualified': False, 'production_ready': False, 'toolkit_identity': toolkit_identity()}
    helper = None
    stage = 'admission'

    def run(args, timeout=60):
        return subprocess.check_output(args, cwd=ROOT, text=True, timeout=timeout).strip()
    try:
        require(Path.cwd().resolve() == ROOT, 'rehearsal_check_failed')
        require(not restore_report.is_symlink() and restore_report.stat().st_size < 1024 * 1024, 'ordinary_small_restore_report_required')
        evidence = json.loads(restore_report.read_text(encoding='utf-8'))
        admit_images(evidence['images'], expected_revision)
        require(evidence['passed'] is True and evidence['synthetic_only'] is True and (evidence['isolated_services_stopped'] is True), 'successful_synthetic_restore_required')
        require(evidence['source_revision'] == expected_revision, 'restore_revision_mismatch')
        if 'restored_http' not in evidence:
            evidence['restored_http'] = evidence['restore']
        release = inspect_release(evidence['images'])
        require(release['source_revision'] == expected_revision and release['schema_version'] == 8, 'image_revision_or_schema_mismatch')
        require(current_contract_digest() == contract_digest(release['contracts']), 'selected_state_contracts_mismatch')
        project = evidence['project']
        require(project.startswith('ain-http-check-'), 'rehearsal_check_failed')
        source_volume = project + '_state'
        volume = json.loads(run(['docker', 'volume', 'inspect', source_volume]))[0]
        require(volume['Name'] == source_volume and volume['Labels']['com.docker.compose.project'] == project, 'rehearsal_check_failed')
        require(not run(['docker', 'ps', '-q', '--filter', 'volume=' + source_volume]), 'Synthetic source volume is in use')
        stage = 'existing_windows_key'
        key = load_key(key_file)
        report['key_provider'] = 'Existing Windows DPAPI CurrentUser key; no independent escrow'
        report['source_revision'] = evidence['source_revision']
        stage = 'synthetic_snapshot_copy'
        print('Copying only the retained synthetic backup through a read-only helper.', flush=True)
        name = 'ain-encrypted-copy-' + key_id[:12]
        helper = run(['docker', 'run', '-d', '--name', name, '--label', 'ain.synthetic-copy=' + key_id, '--network', 'none', '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true', '--pids-limit', '32', '--memory', '128m', '--mount', 'type=volume,source=' + source_volume + ',target=/source,readonly', '--entrypoint', 'python', evidence['images']['api'], '-c', 'import time;time.sleep(180)'])
        info = json.loads(run(['docker', 'inspect', helper]))[0]
        require(info['Config']['Labels']['ain.synthetic-copy'] == key_id, 'rehearsal_check_failed')
        require(info['Image'] == evidence['images']['api'], 'rehearsal_check_failed')
        require(len(info['Mounts']) == 1 and info['Mounts'][0]['Name'] == source_volume and (info['Mounts'][0]['RW'] is False), 'rehearsal_check_failed')
        snapshot = case / 'snapshot'
        run(['docker', 'cp', helper + ':/source/http-backup', str(snapshot)])
        manifest = verify(snapshot)
        require(manifest['snapshot_id'] == evidence['restored_http']['snapshot_id'], 'rehearsal_check_failed')
        require(checksum(snapshot / 'manifest.json') == evidence['restored_http']['manifest_sha256'], 'rehearsal_check_failed')
        require(manifest['database']['row_counts']['auth_users'] == 3, 'rehearsal_check_failed')
        require(manifest['database']['row_counts']['auth_sessions'] == 1, 'rehearsal_check_failed')
        require(manifest['database']['row_counts']['flights'] == 1, 'rehearsal_check_failed')
        source_hashes = {e['path']: checksum(snapshot / e['path']) for e in manifest['files']}
        report['checks']['copied_snapshot_matches_http_restore_evidence'] = True
        stage = 'encryption_and_restore'
        print('Encrypting and restoring to a fresh private directory with the existing key.', flush=True)
        encrypted = case / 'synthetic.ainseal'
        restored = case / 'restored'
        sealed = seal(snapshot, encrypted, key)
        receipt = restore_sealed(encrypted, restored, key)
        require(receipt['encrypted_source_authenticated'] and receipt['sessions_revoked'], 'rehearsal_check_failed')
        require(receipt['revoked_session_rows'] == 1 and receipt['snapshot_id'] == manifest['snapshot_id'], 'rehearsal_check_failed')
        offline = case / 'offline-evidence'
        offline.mkdir()
        for label, source in (('backup', snapshot), ('restored', restored)):
            dest = offline / label
            dest.mkdir()
            for entry in manifest['files']:
                relative = entry['path']
                out = dest / relative
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source / relative, out)
            relative = 'manifest.json' if label == 'backup' else 'recovery-receipt.json'
            shutil.copyfile(source / relative, dest / relative)
        consistency = verify_evidence(offline / 'backup', offline / 'restored', offline_copy=True)
        require(consistency['consistency_verified'], consistency['errors'])
        report['checks'].update(encrypted_restore_authenticated=True, restored_sessions_revoked_and_audited=True, offline_restored_rows_and_receipt_consistent=True)
        stage = 'ciphertext_negative_checks'
        original = encrypted.read_bytes()
        variants = [('wrong-key', original, Cobblestone128Encryptor.generate_key()), ('truncated', original[:-1], key), ('appended', original + b'altered', key), ('modified', original[:40] + bytes([original[40] ^ 1]) + original[41:], key)]
        for label, content, test_key in variants:
            damaged = case / (label + '.ainseal')
            damaged.write_bytes(content)
            target = case / ('refused-' + label)
            try:
                restore_sealed(damaged, target, test_key)
            except ValueError:
                pass
            else:
                raise AssertionError('Invalid encrypted input was accepted: ' + label)
            require(not target.exists(), 'rehearsal_check_failed')
            require(not list(case.glob('.ain-unseal-*')), 'rehearsal_check_failed')
            report['checks'][label.replace('-', '_') + '_rejected_without_target'] = True
        require({e['path']: checksum(snapshot / e['path']) for e in manifest['files']} == source_hashes, 'rehearsal_check_failed')
        require(checksum(encrypted) == sealed['sha256'], 'rehearsal_check_failed')
        report['checks']['original_snapshot_and_ciphertext_preserved'] = True
        report.update(passed=True, snapshot_id=manifest['snapshot_id'], encryption=sealed, restoration=receipt, offline_consistency=consistency)
    except Exception as error:
        report.update(failed_stage=stage, error=str(error)[-1800:])
    finally:
        if helper:
            try:
                info = json.loads(run(['docker', 'inspect', helper]))[0]
                require(info['Config']['Labels']['ain.synthetic-copy'] == key_id, 'rehearsal_check_failed')
                run(['docker', 'rm', '-f', helper])
                report['readonly_helper_removed'] = True
            except Exception as error:
                report.update(passed=False, cleanup_error=str(error)[-1000:])
        report['scope'] = 'Current-revision, same-Windows-user synthetic encrypted restore; plaintext sources retained; no off-host recovery, key escrow or real model recovery.'
        target = ROOT / '.local/rehearsal-reports' / ('AIN_Current_Encrypted_Recovery_Checks-' + key_id[:12] + '.json')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        (case / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'passed': report['passed'], 'stage': stage, 'checks': report['checks'], 'report': str(target), 'error': report.get('error'), 'production_ready': False}, indent=2))
    return 0 if report['passed'] else 2

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--restore-report', type=Path, required=True)
    parser.add_argument('--key-file', type=Path, required=True)
    parser.add_argument('--expected-revision', required=True)
    args = parser.parse_args()
    return run_check(args.restore_report, args.key_file, args.expected_revision)
if __name__ == '__main__':
    raise SystemExit(main())
