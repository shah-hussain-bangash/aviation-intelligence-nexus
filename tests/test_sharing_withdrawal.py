from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import copy
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4
from agents.evaluate_peer_review import seed
from agents.evaluate_withdrawal import exercise
from agents.store import AgentStore,Conflict
from agents.jobs import JobQueue
from agents.review_inbox import inbox
from agents.withdrawal import SharingWithdrawal
from agents.archive import ArchiveQuery,page
from services.api.agent_operations import snapshot
from services.api.auth import AuthStore
from services.api.main import initialize


class SharingWithdrawalTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.root=Path(self.folder.name);self.db=self.root/'state.sqlite3';initialize(self.db);self.store=AgentStore(self.db);self.queue=JobQueue(self.store);self.auth=AuthStore(self.db)
        for name,role in [('author','admin'),('peer','researcher'),('admin','admin')]:self.auth.create_user(name,'temporary-withdrawal-password',role)
        with closing(sqlite3.connect(self.db)) as db:self.users={r[1]:dict(zip(['id','username','role'],r)) for r in db.execute('SELECT id,username,role FROM auth_users')}
        self.run=seed(self.store,self.users['author']);self.request=SharingWithdrawal(run_id=self.run['run_id'],report_sha256=self.run['report_sha256'],withdrawal_key=uuid4(),note='End sharing; preserve recorded evidence.',acknowledged=True)

    def tearDown(self):self.folder.cleanup()

    def withdraw(self,user='author',request=None,**kwargs):return self.store.withdraw_sharing(self.users[user],request or self.request,**kwargs)

    def test_preserves_evidence_and_ends_peer_access_across_restart(self):
        result=self.withdraw();self.assertEqual(result['state'],'withdrawn');self.assertFalse(result['withdrawal_replayed'])
        for k in ['request','steps','claims','report_sha256','reviews']:self.assertEqual(result[k],self.run[k])
        self.assertFalse(result['operational_approval']);self.assertEqual(inbox(self.db,self.users['peer'])['runs'],[])
        with self.assertRaises(KeyError):self.queue.get(self.users['peer'],self.run['run_id'])
        self.store.recover();self.assertEqual(JobQueue(AgentStore(self.db)).get(self.users['author'],self.run['run_id'])['sharing_withdrawal'],result['sharing_withdrawal'])
        self.assertEqual(page(self.db,self.users['author'],ArchiveQuery(state='withdrawn'))['runs'][0]['run_id'],self.run['run_id'])
        with closing(sqlite3.connect(self.db)) as db,db:db.execute("UPDATE agent_runs SET result_json=json_set(result_json,'$.execution','local-background-queue-v1') WHERE id=?",(self.run['run_id'],))
        self.assertEqual(snapshot(self.db,{'enabled':False,'alive':False,'error':None})['totals']['withdrawn'],1)

    def test_owner_viewer_and_active_admin_can_withdraw_but_peer_cannot(self):
        with self.assertRaises(KeyError):self.withdraw('peer')
        self.auth.set_access('author',role='viewer');self.users['author']['role']='viewer';self.assertEqual(self.withdraw()['state'],'withdrawn')
        run=seed(self.store,self.users['author']);request=self.request.model_copy(update={'run_id':run['run_id']});self.assertEqual(self.withdraw('admin',request)['sharing_withdrawal']['actor'],'admin')

    def test_current_account_and_session_checked_inside_write_transaction(self):
        token=self.auth.login('author','temporary-withdrawal-password');self.auth.logout(token)
        with self.assertRaises(PermissionError):self.withdraw(session_token=token)
        self.auth.set_access('admin',role='viewer')
        with self.assertRaises(PermissionError):self.withdraw('admin')
        self.auth.set_access('admin',role='admin')
        self.auth.set_access('author',disable=True)
        with self.assertRaises(PermissionError):self.withdraw()
        self.assertEqual(self.queue.get(self.users['author'],self.run['run_id'])['state'],'awaiting_review')

    def test_review_race_has_exactly_one_terminal_outcome(self):
        def action(kind):
            try:
                if kind=='withdraw':return self.withdraw()['state']
                return self.store.review(self.users['peer'],self.run['run_id'],self.run['report_sha256'],'reviewed','Checked recorded evidence and limitations.')['state']
            except (Conflict,KeyError):return 'blocked'
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(action,['review','withdraw']))
        saved=self.queue.get(self.users['author'],self.run['run_id']);self.assertEqual(results.count('blocked'),1)
        self.assertIn(saved['state'],['reviewed','withdrawn']);self.assertEqual(bool(saved['reviews']),saved['state']=='reviewed');self.assertEqual('sharing_withdrawal' in saved,saved['state']=='withdrawn')

    def test_exact_retry_reuses_receipt_and_changed_retries_conflict(self):
        saved=self.withdraw();retry=self.withdraw();self.assertTrue(retry['withdrawal_replayed']);self.assertEqual(saved['sharing_withdrawal'],retry['sharing_withdrawal'])
        for changes in [{'withdrawal_key':uuid4()},{'note':'A different sharing withdrawal reason.'}]:
            with self.assertRaises(Conflict):self.withdraw(request=self.request.model_copy(update=changes))
        with self.assertRaises(Conflict):self.withdraw('admin')

    def test_unshared_decided_running_and_changed_reports_blocked(self):
        for state in ['reviewed','needs_changes','queued','running','cancelled','interrupted','failed']:
            changed=copy.deepcopy(self.run);changed['state']=state;self.store.checkpoint(changed)
            with self.assertRaises(Conflict):self.withdraw()
        changed=copy.deepcopy(self.run);changed['claims']=[];self.store.checkpoint(changed)
        with self.assertRaises(Conflict):self.withdraw()
        private=seed(self.store,self.users['author'],False)
        with self.assertRaises(Conflict):self.withdraw(request=self.request.model_copy(update={'run_id':private['run_id'],'report_sha256':private['report_sha256']}))
        for ack in [False,'true',1]:
            with self.assertRaises(ValueError):SharingWithdrawal.model_validate({**self.request.model_dump(),'acknowledged':ack})

    def test_authenticated_http_exercise(self):
        with patch('agents.evaluate_withdrawal.ROOT',self.root):result=exercise(self.root/'.local/http-withdrawal')
        self.assertTrue(result['passed']);self.assertEqual(len(result['checks']),12)
