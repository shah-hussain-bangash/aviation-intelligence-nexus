from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import copy
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from agents.evaluate_peer_review import seed,exercise
from agents.runtime import Investigation
from agents.store import AgentStore,Conflict,sha
from agents.jobs import JobQueue
from agents.review_inbox import inbox
from services.api.auth import AuthStore
from services.api.main import initialize


class PeerReviewTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.root=Path(self.folder.name);self.db=self.root/'state.sqlite3';initialize(self.db);self.store=AgentStore(self.db);self.queue=JobQueue(self.store);self.auth=AuthStore(self.db)
        for name,role in [('author','admin'),('reviewer','researcher'),('other','researcher'),('viewer','viewer')]:self.auth.create_user(name,'temporary-peer-review-password',role)
        with closing(sqlite3.connect(self.db)) as db:self.users={row[1]:dict(zip(['id','username','role'],row)) for row in db.execute('SELECT id,username,role FROM auth_users')}
        self.run=seed(self.store,self.users['author'])

    def tearDown(self):self.folder.cleanup()

    def decide(self,user,run=None,decision='reviewed',**kwargs):
        run=run or self.run;return self.store.review(user,run['run_id'],run['report_sha256'],decision,'Checked recorded evidence and limitations.',**kwargs)

    def test_default_identity_and_legacy_review_behavior_are_preserved(self):
        request=Investigation(objective='Inspect recorded evidence and limitations.')
        self.assertNotIn('require_peer_review',request.model_dump());self.assertEqual(request.model_dump(),Investigation.model_validate({**request.model_dump(),'require_peer_review':False}).model_dump())
        opted=Investigation.model_validate({**request.model_dump(),'require_peer_review':True});self.assertTrue(opted.model_dump()['require_peer_review']);self.assertNotEqual(sha(request.model_dump()),sha(opted.model_dump()))
        with self.assertRaises(ValueError):Investigation.model_validate({**request.model_dump(),'require_peer_review':'true'})
        legacy=seed(self.store,self.users['author'],False);self.assertNotIn('review_access',self.queue.get(self.users['author'],legacy['run_id']));self.assertEqual(self.decide(self.users['author'],legacy)['state'],'reviewed')

    def test_opt_in_only_pending_sharing_and_author_admin_is_blocked(self):
        private=seed(self.store,self.users['author'],False)
        self.assertEqual([r['run_id'] for r in inbox(self.db,self.users['reviewer'])['runs']],[self.run['run_id']])
        self.assertEqual(inbox(self.db,self.users['author'])['runs'],[])
        with self.assertRaises(KeyError):self.queue.get(self.users['reviewer'],private['run_id'])
        with self.assertRaises(KeyError):self.queue.get(self.users['viewer'],self.run['run_id'])
        with self.assertRaises(PermissionError):inbox(self.db,self.users['viewer'])
        with self.assertRaises(Conflict):self.decide(self.users['author'])
        self.assertFalse(self.queue.get(self.users['author'],self.run['run_id'])['review_access']['can_review'])
        self.assertTrue(self.queue.get(self.users['reviewer'],self.run['run_id'])['review_access']['can_review'])
        self.assertNotIn('steps',inbox(self.db,self.users['reviewer'])['runs'][0])

    def test_competing_reviewers_record_only_one_decision_and_closed_access_ends(self):
        def submit(user):
            try:return self.decide(user)['state']
            except (Conflict,KeyError):return 'blocked'
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(submit,[self.users['reviewer'],self.users['other']]))
        self.assertEqual(sorted(results),['blocked','reviewed']);saved=self.queue.get(self.users['author'],self.run['run_id']);self.assertEqual(len(saved['reviews']),1);self.assertTrue(saved['reviews'][0]['second_account_review'])
        self.assertFalse(saved['operational_approval']);self.assertEqual(inbox(self.db,self.users['reviewer'])['runs'],[])
        with self.assertRaises(KeyError):self.queue.get(self.users['reviewer'],self.run['run_id'])

    def test_changed_hash_and_incomplete_evidence_cannot_be_accepted(self):
        changed=copy.deepcopy(self.run);changed['request']['objective']='Changed without resealing the report.';self.store.checkpoint(changed)
        with self.assertRaises(KeyError):self.queue.get(self.users['reviewer'],changed['run_id'])
        with self.assertRaises(ValueError):inbox(self.db,self.users['reviewer'])
        self.store.checkpoint(self.run);changed=copy.deepcopy(self.run);changed['claims']=[];changed['report_sha256']=sha({k:changed[k] for k in ['request','steps','claims']});self.store.checkpoint(changed)
        with self.assertRaises(Conflict):self.decide(self.users['reviewer'],changed)
        self.assertEqual(self.decide(self.users['reviewer'],changed,'needs_changes')['state'],'needs_changes')

    def test_current_role_and_session_are_rechecked_inside_review_transaction(self):
        token=self.auth.login('reviewer','temporary-peer-review-password');self.auth.logout(token)
        with self.assertRaises(PermissionError):self.decide(self.users['reviewer'],session_token=token)
        self.auth.set_access('reviewer',role='viewer')
        with self.assertRaises(PermissionError):self.decide(self.users['reviewer'])
        self.auth.set_access('other',disable=True)
        with self.assertRaises(PermissionError):self.decide(self.users['other'])
        self.assertEqual(self.queue.get(self.users['author'],self.run['run_id'])['reviews'],[])

    def test_inbox_bounds_readonly_missing_busy_and_deadline_failures(self):
        for _ in range(21):seed(self.store,self.users['author'])
        result=inbox(self.db,self.users['reviewer']);self.assertEqual(len(result['runs']),20);self.assertTrue(result['has_more'])
        missing=self.root/'missing.sqlite3'
        with self.assertRaises(sqlite3.Error):inbox(missing,self.users['reviewer'])
        self.assertFalse(missing.exists())
        with closing(sqlite3.connect(self.db)) as db:
            db.execute('PRAGMA journal_mode=DELETE');db.execute('BEGIN EXCLUSIVE')
            with self.assertRaises(sqlite3.OperationalError):inbox(self.db,self.users['reviewer'])
            db.rollback()
        with patch('agents.review_inbox.time.monotonic',side_effect=[0,4,4,4]):
            with self.assertRaises((TimeoutError,sqlite3.OperationalError)):inbox(self.db,self.users['reviewer'])

    def test_authenticated_http_workflow_with_disposable_accounts(self):
        with patch('agents.evaluate_peer_review.ROOT',self.root):
            # Seed reads only the public engineering evidence from the real source tree.
            from services.api.paths import ROOT
            target=self.root/'docs/reports/Distribution_Agent_Integration.json';target.parent.mkdir(parents=True);target.write_text((ROOT/'docs/reports/Distribution_Agent_Integration.json').read_text(encoding='utf-8'),encoding='utf-8')
            result=exercise(self.root/'.local/http-review-check')
        self.assertTrue(result['passed']);self.assertTrue(all(result['checks'].values()))
