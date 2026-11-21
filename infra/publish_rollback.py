"""Operator-only publication of a completed isolated drill receipt; never switches releases."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import uuid
from infra.rollback_evidence import FLAGS, binding, validate_receipt
from infra.state_contracts import contract_digest
from services.api.paths import ROOT, STATE, SCHEMA_VERSION

PRIMARY = 'ain-local-release'
FIELDS = ('format', 'checked_at', 'candidate_revision', 'rollback_revision', 'candidate_images',
          'rollback_images', 'schema_version', 'contracts_sha256', 'flight_records',
          'active_jobs_at_start', 'production_qualified', *FLAGS)


def sanitized(receipt):
    validate_receipt(receipt)
    if receipt['format'] != 'ain-rollback-drill-v2':
        raise ValueError('Historical receipts cannot be published as current-build evidence')
    return {key: receipt[key] for key in FIELDS}


def install_receipt(receipt, state=STATE, revision=None, schema_version=SCHEMA_VERSION, root=ROOT):
    receipt = sanitized(receipt)
    context = binding(receipt, os.environ.get('AIN_RELEASE_REVISION') if revision is None else revision, schema_version, root)
    if context['candidate_matches_current_build'] is not True:
        raise ValueError('Receipt does not cover the running candidate and selected state contracts')
    state = Path(state)
    target = state / 'rollback-drill.json'
    if state.is_symlink() or target.is_symlink():
        raise ValueError('Receipt paths must not be symbolic links')
    payload = json.dumps(receipt, sort_keys=True, indent=2) + '\n'
    if target.exists():
        if target.stat().st_size > 16000:
            raise ValueError('Oversized existing receipt; operator review required')
        old = target.read_text(encoding='utf-8')
        if old == payload:
            return {'installed': True, 'unchanged': True, 'production_qualified': False}
        # Preserve previous evidence before the atomic display-receipt replacement.
        history = state / ('rollback-drill-history-' + uuid.uuid4().hex + '.json')
        with history.open('x', encoding='utf-8') as stream:
            stream.write(old)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', dir=state, prefix='.rollback-', suffix='.tmp', encoding='utf-8', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(target)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return {'installed': True, 'unchanged': False, 'production_qualified': False}


def publish(receipt):
    # Fixed project; no arbitrary host paths, release switching, or web write endpoint.
    from infra.releases import deployed_images, inspect_release
    receipt = sanitized(receipt)
    running = inspect_release(deployed_images(PRIMARY))
    if running['images'] != receipt['candidate_images'] or running['source_revision'] != receipt['candidate_revision'] or running['schema_version'] != receipt['schema_version'] or contract_digest(running['contracts']) != receipt['contracts_sha256']:
        raise ValueError('Receipt does not match the deployed immutable image pair')
    code = ('import json,sys,sqlite3;from infra.publish_rollback import install_receipt;from services.api.paths import STATE,SCHEMA_VERSION;'
            "db=sqlite3.connect((STATE/'ain.sqlite3').as_uri()+'?mode=ro',uri=True);"
            "assert db.execute('SELECT MAX(version) FROM schema_migrations').fetchone()[0]==SCHEMA_VERSION,'Unverified database schema';"
            'db.close();print(json.dumps(install_receipt(json.load(sys.stdin))))')
    result = subprocess.run(['docker', 'compose', '-p', PRIMARY, '-f', str(ROOT / 'compose.yaml'), 'exec', '-T', 'api', 'python', '-c', code],
                            input=json.dumps(receipt), capture_output=True, text=True, cwd=ROOT, timeout=30, check=True)
    return json.loads(result.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', required=True)
    args = parser.parse_args()
    source = Path(args.receipt)
    if source.stat().st_size > 16000:
        raise ValueError('Oversized receipt')
    print(json.dumps(publish(json.loads(source.read_text(encoding='utf-8')))))


if __name__ == '__main__':
    main()
