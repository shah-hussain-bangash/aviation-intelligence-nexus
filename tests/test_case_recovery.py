from contextlib import closing
from datetime import datetime,timedelta,timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4
from fastapi.testclient import TestClient
from agents.evaluate_peer_review import seed as seed_agent
from agents.store import AgentStore,sha
from agents.tools import gate_sample
from optimization.gates import optimize
from optimization.history import GateRunStore
from optimization.reviews import GateReview
from rag.history import EvidenceHistory
from services.api.auth import AuthStore
from services.api.main import initialize,create_app
from services.api.research_cases import ResearchCaseService,OpenCase,ChangeCase,AttachEvidence,digest
from services.api.case_agents import AttachAgent
from services.api.case_gates import AttachGate
from services.api.case_workspace import create_case_app
from infra import case_recovery as paired
from infra import recovery
from infra.recovery_state import RESTORE_MARKER,RestoreIncompleteError

PASSWORD='synthetic-case-recovery-only-2026'


def seed_workspace(state):
    state=Path(state);state.mkdir();database=state/'ain.sqlite3';initialize(database)
    auth=AuthStore(database);auth.create_user('case-owner',PASSWORD,'admin');auth.create_user('case-viewer',PASSWORD,'viewer')
    with closing(sqlite3.connect(database)) as db:row=db.execute("SELECT id,username,role FROM auth_users WHERE username='case-owner'").fetchone()
    user=dict(zip(('id','username','role'),row));token=auth.login('case-owner',PASSWORD)
    from services.api.history import ResearchHistory
    saved=ResearchHistory(database).save(str(uuid4()),{'scope':'SYNTHETIC recovery fixture'},
        {'model_version':'delay-v2','artifact_sha256':'a'*64,'research_only':True,'operational_serving_approved':False,'arrival_delay_15_probability':0.2,'limitations':['SYNTHETIC stored prediction; no model inference']},user)
    service=ResearchCaseService(database,state/paired.CASE_FILE)
    record=service.open(user,OpenCase(source_run_id=saved['run_id'],source_sha256=digest(saved),title='SYNTHETIC combined case recovery'),uuid4())
    case_id=record['id'];service.change(user,case_id,ChangeCase(expected_version=1,action='note',note='SYNTHETIC investigation note retained through recovery'))
    evidence=EvidenceHistory(database).save(user,{'question':'SYNTHETIC recovery evidence','mode':'evidence_only','evidence':[{'text':'Synthetic saved evidence; no retrieval executed'}],'claims':[],'research_only':True,'operational_approval':False})
    service.attach_evidence(user,case_id,AttachEvidence(expected_version=2,evidence_run_id=evidence['run_id'],evidence_sha256=digest(evidence)))
    store=AgentStore(database);agent=seed_agent(store,user,False);agent['request']['objective']='SYNTHETIC recovery report; recorded public fixture, no new agent execution.'
    agent['report_sha256']=sha({k:agent[k] for k in ('request','steps','claims')});store.checkpoint(agent)
    store.review(user,agent['run_id'],agent['report_sha256'],'needs_changes','SYNTHETIC review; no genuine human acceptance')
    with closing(sqlite3.connect(database)) as db:agent=json.loads(db.execute('SELECT result_json FROM agent_runs WHERE id=?',(agent['run_id'],)).fetchone()[0])
    service.attach_agent(user,case_id,AttachAgent(expected_version=3,agent_run_id=agent['run_id'],agent_sha256=digest(agent)))
    gate_store=GateRunStore(database);gate=gate_store.save(user,str(uuid4()),optimize(gate_sample()))
    gate_store.review(user,GateReview(run_id=gate['run_id'],proposal_sha256=gate['proposal_sha256'],review_key=uuid4(),decision='needs_changes',note='SYNTHETIC recovery review; no airport decision',acknowledged=True))
    with closing(sqlite3.connect(database)) as db:gate=json.loads(db.execute('SELECT result_json FROM gate_runs WHERE id=?',(gate['run_id'],)).fetchone()[0])
    service.attach_gate(user,case_id,AttachGate(expected_version=4,gate_run_id=gate['run_id'],gate_sha256=digest(gate)))
    service.change(user,case_id,ChangeCase(expected_version=5,action='close',note='SYNTHETIC closing outcome; no airline action'))
    return {'user':user,'token':token,'case_id':case_id,'record':service.get(user,case_id),'evidence_id':evidence['run_id'],'agent_id':agent['run_id'],'gate_id':gate['run_id']}


class CaseRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.state=self.root/'state';self.fixture=seed_workspace(self.state);self.bundle=self.root/'bundle';self.target=self.root/'restored'

    def backup(self):return paired.backup(self.state,self.bundle,offline_acknowledged=True)

    def test_paired_restore_preserves_all_records_owners_and_revokes_only_restored_sessions(self):
        before=paired.case_facts(self.state/'ain.sqlite3',self.state/paired.CASE_FILE)
        source_pins={n:recovery.checksum(self.state/n) for n in ('ain.sqlite3',paired.CASE_FILE)}
        backup=self.backup();receipt=paired.restore(self.bundle,self.target,backup['manifest_sha256'],offline_acknowledged=True)
        self.assertEqual(before,receipt['cases']);self.assertEqual(before['row_counts'],{'cases':1,'case_events':6,'case_evidence':1,'case_agents':1,'case_gates':1})
        self.assertEqual(source_pins,{n:recovery.checksum(self.state/n) for n in source_pins})
        self.assertIsNotNone(AuthStore(self.state/'ain.sqlite3').session(self.fixture['token']))
        self.assertIsNone(AuthStore(self.target/'ain.sqlite3').session(self.fixture['token']))
        service=ResearchCaseService(self.target/'ain.sqlite3',self.target/paired.CASE_FILE)
        self.assertEqual(service.get(self.fixture['user'],self.fixture['case_id']),self.fixture['record'])
        with TestClient(create_app(self.target/'ain.sqlite3',research_cases=service)) as client:
            login=client.post('/api/v1/auth/login',json={'username':'case-owner','password':PASSWORD},headers={'Origin':'http://127.0.0.1:8080'})
            self.assertEqual(login.status_code,200);path='/api/v1/research/cases/'+self.fixture['case_id']
            self.assertEqual(client.get(path).json(),self.fixture['record'])
            for kind,key in [('evidence','evidence_id'),('agents','agent_id'),('gates','gate_id')]:self.assertEqual(client.get(path+'/'+kind+'/'+self.fixture[key]).status_code,200)
            viewer=client.post('/api/v1/auth/login',json={'username':'case-viewer','password':PASSWORD},headers={'Origin':'http://127.0.0.1:8080'})
            self.assertEqual(viewer.status_code,200);self.assertEqual(client.get(path).status_code,404)
            for kind,key in [('evidence','evidence_id'),('agents','agent_id'),('gates','gate_id')]:self.assertEqual(client.get(path+'/'+kind+'/'+self.fixture[key]).status_code,404)

    def test_both_database_writers_are_excluded_during_capture(self):
        original=recovery.backup
        def guarded(source,destination):
            for name,sql in [('ain.sqlite3','UPDATE auth_users SET active=active'),(paired.CASE_FILE,"UPDATE cases SET title='blocked'")]:
                with closing(sqlite3.connect(self.state/name,timeout=.01)) as writer:
                    with self.assertRaises(sqlite3.OperationalError):writer.execute(sql)
            return original(source,destination)
        with patch.object(recovery,'backup',side_effect=guarded):self.backup()
        self.assertEqual(paired.verify(self.bundle,recovery.checksum(self.bundle/paired.MANIFEST))['cases']['row_counts']['cases'],1)

    def test_offline_new_target_and_active_jobs_are_required(self):
        with self.assertRaises(paired.CaseRecoveryError):paired.backup(self.state,self.bundle)
        self.assertFalse(self.bundle.exists())
        with self.assertRaises(paired.CaseRecoveryError):paired.backup(self.state,self.state/'nested',offline_acknowledged=True)
        AgentStore(self.state/'ain.sqlite3').begin(self.fixture['user'],str(uuid4()),{'objective':'SYNTHETIC unfinished work'})
        with self.assertRaisesRegex(paired.CaseRecoveryError,'active_agent_work'):self.backup()
        self.assertFalse(self.bundle.exists())

    def test_changed_bundle_pin_case_file_and_extra_files_fail_before_restore(self):
        backup=self.backup();pin=backup['manifest_sha256']
        with self.assertRaises(paired.CaseRecoveryError):paired.restore(self.bundle,self.target,'0'*64,offline_acknowledged=True)
        self.assertFalse(self.target.exists());(self.bundle/'unexpected.txt').write_text('fixture')
        with self.assertRaises(paired.CaseRecoveryError):paired.verify(self.bundle,pin)
        (self.bundle/'unexpected.txt').unlink()
        with (self.bundle/paired.CASE_FILE).open('ab') as stream:stream.write(b'changed')
        with self.assertRaises(paired.CaseRecoveryError):paired.restore(self.bundle,self.target,pin,offline_acknowledged=True)
        self.assertFalse(self.target.exists())

    def test_missing_owner_and_future_schema_cannot_be_backed_up(self):
        with closing(sqlite3.connect(self.state/paired.CASE_FILE)) as db,db:db.execute('PRAGMA user_version=5')
        with self.assertRaises(paired.CaseRecoveryError):self.backup()
        self.assertFalse(self.bundle.exists())
        with closing(sqlite3.connect(self.state/paired.CASE_FILE)) as db,db:db.execute('PRAGMA user_version=4')
        with closing(sqlite3.connect(self.state/'ain.sqlite3')) as db,db:db.execute('DELETE FROM auth_users WHERE id=?',(self.fixture['user']['id'],))
        with self.assertRaisesRegex(paired.CaseRecoveryError,'case_owner_missing'):self.backup()
        self.assertFalse(self.bundle.exists())

    def test_interrupted_restore_stays_blocked_before_case_store_creation(self):
        backup=self.backup();original=paired.shutil.copyfile
        def fail(source,target,*args,**kwargs):
            if Path(target).resolve()==(self.target/paired.CASE_FILE).resolve():raise OSError('SYNTHETIC copy fault')
            return original(source,target,*args,**kwargs)
        with patch.object(paired.shutil,'copyfile',side_effect=fail),self.assertRaises(OSError):paired.restore(self.bundle,self.target,backup['manifest_sha256'],offline_acknowledged=True)
        self.assertTrue((self.target/RESTORE_MARKER).exists());self.assertFalse((self.target/paired.CASE_FILE).exists())
        with patch.dict(os.environ,{'AIN_ENV':'test','AIN_STATE_ROOT':str(self.target),'AIN_DB_PATH':str(self.target/'ain.sqlite3')},clear=True),self.assertRaises(RestoreIncompleteError):create_case_app()
        self.assertFalse((self.target/paired.CASE_FILE).exists())

    def test_backup_bundle_cannot_be_started_as_a_workspace(self):
        self.backup()
        with patch.dict(os.environ,{'AIN_ENV':'test','AIN_STATE_ROOT':str(self.bundle),'AIN_DB_PATH':str(self.bundle/'ain.sqlite3')},clear=True),self.assertRaises(ValueError):create_case_app()
        self.assertFalse((self.bundle/'ain.sqlite3').exists())

    def test_optional_model_and_index_bytes_are_preserved_without_deserialization(self):
        model=self.state/'models/delay-v2';model.mkdir(parents=True);artifact=b'SYNTHETIC inert bytes; never deserialized';(model/'model.joblib').write_bytes(artifact)
        (model/'report.json').write_text(json.dumps({'artifact_sha256':hashlib.sha256(artifact).hexdigest()}))
        knowledge=self.state/'knowledge';knowledge.mkdir();payload={'fixture':'synthetic envelope; not a usable index'}
        (knowledge/'index.json').write_text(json.dumps({'payload':payload,'sha256':hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()}))
        backup=self.backup();paired.restore(self.bundle,self.target,backup['manifest_sha256'],offline_acknowledged=True)
        for name in ('models/delay-v2/model.joblib','models/delay-v2/report.json','knowledge/index.json'):self.assertEqual((self.state/name).read_bytes(),(self.target/name).read_bytes())

    def test_actual_cli_verifies_new_private_bundle_and_rejects_existing_destination(self):
        (recovery.ROOT/'.local').mkdir(exist_ok=True)
        folder=tempfile.TemporaryDirectory(dir=recovery.ROOT/'.local');target=Path(folder.name).resolve()
        self.assertTrue(target.is_relative_to((recovery.ROOT/'.local').resolve()));self.addCleanup(folder.cleanup)
        env={k:v for k,v in os.environ.items() if not k.startswith('AIN_') and k!='PORT'}
        command=[sys.executable,'-m','infra.case_recovery']
        result=subprocess.run(command+['backup','--source',str(self.state),'--destination',str(target/'bundle'),'--offline-acknowledged'],cwd=recovery.ROOT,env=env,capture_output=True,text=True,timeout=60)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr);pin=json.loads(result.stdout)['manifest_sha256']
        verified=subprocess.run(command+['verify','--source',str(target/'bundle'),'--manifest-sha256',pin],cwd=recovery.ROOT,env=env,capture_output=True,text=True,timeout=60)
        self.assertEqual(verified.returncode,0,verified.stdout+verified.stderr)
        restored=subprocess.run(command+['restore','--source',str(target/'bundle'),'--destination',str(target/'restored'),'--manifest-sha256',pin,'--offline-acknowledged'],cwd=recovery.ROOT,env=env,capture_output=True,text=True,timeout=60)
        self.assertEqual(restored.returncode,0,restored.stdout+restored.stderr);self.assertTrue(json.loads(restored.stdout)['case_contents_preserved'])
        failed=subprocess.run(command+['restore','--source',str(target/'bundle'),'--destination',str(target/'bundle'),'--manifest-sha256',pin,'--offline-acknowledged'],cwd=recovery.ROOT,env=env,capture_output=True,text=True,timeout=60)
        self.assertEqual(failed.returncode,2);self.assertNotIn(str(self.state),failed.stdout);self.assertNotIn(PASSWORD,result.stdout)
