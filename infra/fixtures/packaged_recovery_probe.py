"""Synthetic packaged-image probe, streamed on stdin by the host harness."""

from pathlib import Path
from uuid import uuid4
import json,secrets,sqlite3,shutil
from contextlib import closing
from infra.verify_schema8 import seed_fixture,fixture_text,snapshot_rows,FIXTURE_SHA256
from infra.recovery import backup,restore,checksum
from infra.verify_restore_evidence import verify_evidence
from services.api.main import initialize
from services.api.auth import AuthStore
root=Path('/app/.local')
state=root/'synthetic-source'
password=secrets.token_urlsafe(32); token=secrets.token_urlsafe(32); uid=str(uuid4())
seed_fixture(state,fixture_text(),password,token,uid)
db=state/'ain.sqlite3'; before=snapshot_rows(db)
initialize(db)
assert snapshot_rows(db)==before
auth=AuthStore(db)
assert auth.session(token)['id']==uid
auth.login('synthetic-admin',password)
source=snapshot_rows(db,audit=True)
artifacts=('models/delay-v2/model.joblib','models/delay-v2/report.json','knowledge/index.json')
pins={p:checksum(state/p) for p in artifacts}
manifest=backup(state,root/'synthetic-backup')
receipt=restore(root/'synthetic-backup',root/'synthetic-restored')
target=root/'synthetic-restored'; restored=snapshot_rows(target/'ain.sqlite3',audit=True)
assert restored=={**source,'auth_sessions':[],'security_audit':restored['security_audit']}
assert restored['security_audit'][:-1]==source['security_audit']
assert len(restored['security_audit'])==len(source['security_audit'])+1
assert restored['security_audit'][-1][1]==receipt['session_revocation_event_id']
assert receipt['sessions_revoked'] and receipt['revoked_session_rows']>=1
assert {p:checksum(target/p) for p in artifacts}==pins
# All synthetic writers are closed; isolate ordinary files from SQLite sidecars.
offline=root/'offline-evidence';offline.mkdir()
for label,origin in (('backup',root/'synthetic-backup'),('restored',target)):
    destination=offline/label;destination.mkdir()
    for entry in manifest['files']:
        name=entry['path'];out=destination/name;out.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(origin/name,out)
    name='manifest.json' if label=='backup' else 'recovery-receipt.json'
    shutil.copyfile(origin/name,destination/name)
evidence=verify_evidence(offline/'backup',offline/'restored',offline_copy=True)
assert evidence['consistency_verified'], evidence['errors']
recovered=AuthStore(target/'ain.sqlite3')
assert recovered.session(token) is None
assert recovered.session(recovered.login('synthetic-admin',password))['id']==uid
assert snapshot_rows(db,audit=True)==source
print(json.dumps({'passed':True,'fixture_sha256':FIXTURE_SHA256,
 'checks':{'schema7_to_8_preserves_rows':True,'packaged_backup_restore':True,
 'restore_rows_and_audit_preserved':True,'restored_sessions_revoked':True,
 'restore_revocation_audited':True,'restored_credentials_work':True,
 'placeholder_artifact_hash_parity':True,'offline_receipt_consistent':True,
 'synthetic_source_unchanged':True},
 'scope':'Packaged Python recovery functions with synthetic SQLite state and nonexecutable model placeholders; no live HTTP service, real model inference or off-host recovery.'}))
