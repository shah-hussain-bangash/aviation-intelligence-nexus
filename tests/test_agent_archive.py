from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4
from fastapi.testclient import TestClient
from agents.archive import ArchiveQuery,page
from agents.store import AgentStore
from services.api.main import initialize,create_app


class AgentArchiveTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.database=Path(self.folder.name)/'state.sqlite3';initialize(self.database)
        self.store=AgentStore(self.database);self.user={'id':'owner','username':'fixture-owner','role':'researcher'}

    def tearDown(self):self.folder.cleanup()

    def add(self,objective='Saved model evidence for research.',user=None,state='cancelled'):
        run=self.store.begin(user or self.user,str(uuid4()),{'objective':objective})
        run.update(state=state,private_fixture_note='must not be returned');self.store.checkpoint(run);return run

    def test_all_pages_are_owner_scoped_bounded_metadata_and_admin_can_see_other_owners(self):
        own=[self.add() for _ in range(23)];self.add(user={**self.user,'id':'foreign','username':'foreign'})
        found=[];query=ArchiveQuery()
        while True:
            result=page(self.database,self.user,query);self.assertLessEqual(len(result['runs']),10);found.extend(r['run_id'] for r in result['runs'])
            self.assertNotIn('private_fixture_note',str(result));self.assertNotIn('submission_keys',str(result))
            if result['next_before'] is None:break
            query=ArchiveQuery(before=result['next_before'],through=result['through'])
        self.assertEqual(found,[r['run_id'] for r in reversed(own)])
        self.assertEqual(len(page(self.database,{**self.user,'role':'admin'},ArchiveQuery())['runs']),10)
        self.assertEqual(page(self.database,{**self.user,'role':'viewer'},ArchiveQuery())['runs'][0]['run_id'],own[-1]['run_id'])
        self.assertEqual(page(self.database,{**self.user,'id':'nobody'},ArchiveQuery())['runs'],[])

    def test_literal_search_and_state_filter_do_not_interpret_sql_or_wildcards(self):
        special=self.add("Review literal %_ ' evidence.",state='failed');self.add('Review ordinary evidence.',state='reviewed')
        for text in ['%_',"'",'LITERAL']:
            rows=page(self.database,self.user,ArchiveQuery(q=text,state='failed'))['runs'];self.assertEqual([r['run_id'] for r in rows],[special['run_id']])
        self.assertEqual(page(self.database,self.user,ArchiveQuery(q="' OR 1=1 --"))['runs'],[])
        self.assertEqual(page(self.database,self.user,ArchiveQuery(q='literal',state='reviewed'))['runs'],[])

    def test_insertions_and_updates_do_not_move_the_page_boundary(self):
        own=[self.add() for _ in range(13)];first=page(self.database,self.user,ArchiveQuery())
        newest=self.add();own[0]['state']='reviewed';self.store.checkpoint(own[0])
        second=page(self.database,self.user,ArchiveQuery(before=first['next_before'],through=first['through']))
        self.assertEqual([r['run_id'] for r in second['runs']],[r['run_id'] for r in reversed(own[:3])]);self.assertIsNone(second['next_before'])
        self.assertEqual(page(self.database,self.user,ArchiveQuery())['runs'][0]['run_id'],newest['run_id'])

    def test_query_validation_rejects_unknown_duplicate_scope_and_oversized_cursors(self):
        for value in [{'q':'x'*121},{'state':'approved'},{'before':'1'},{'before':'3','through':'2'},{'through':str(2**63)},{'through':'-1'},{'through':'01'},{'path':'private'}]:
            with self.assertRaises(ValueError):ArchiveQuery.model_validate(value)
        self.assertEqual(page(self.database,self.user,ArchiveQuery(through='0'))['runs'],[])

    def test_read_only_missing_busy_and_corrupt_state_never_create_or_return_partial_history(self):
        missing=Path(self.folder.name)/'missing.sqlite3'
        with self.assertRaises(sqlite3.Error):page(missing,self.user,ArchiveQuery())
        self.assertFalse(missing.exists());self.add()
        with closing(sqlite3.connect(self.database)) as db:
            db.execute('PRAGMA journal_mode=DELETE')
            db.execute('BEGIN EXCLUSIVE')
            with self.assertRaises(sqlite3.OperationalError):page(self.database,self.user,ArchiveQuery())
            db.rollback();db.execute("UPDATE agent_runs SET result_json='broken' WHERE owner_id=?",(self.user['id'],));db.commit()
        with self.assertRaises(sqlite3.Error):page(self.database,self.user,ArchiveQuery())

    def test_processing_deadline_fails_closed(self):
        self.add()
        with patch('agents.archive.time.monotonic',side_effect=[0,4,4,4]):
            with self.assertRaises((TimeoutError,sqlite3.OperationalError)):page(self.database,self.user,ArchiveQuery())

    def test_http_auth_viewer_validation_and_sanitized_outage(self):
        app=create_app(self.database)
        with TestClient(app) as client:
            path='/api/v1/research/agent-archive';self.assertEqual(client.get(path).status_code,401)
            app.state.auth_store.create_user('archive-admin','temporary-archive-fixture-123','admin')
            app.state.auth_store.create_user('archive-viewer','temporary-archive-fixture-123','viewer')
            login=client.post('/api/v1/auth/login',json={'username':'archive-viewer','password':'temporary-archive-fixture-123'},headers={'Origin':'http://127.0.0.1:8080'});self.assertEqual(login.status_code,200)
            self.assertEqual(client.get(path).json()['runs'],[])
            for query in ['q=a&q=b','state=approved','url=private','before=1','through=9223372036854775808']:
                self.assertEqual(client.get(path+'?'+query).status_code,422)
            with patch('services.api.main.archive_page',side_effect=sqlite3.OperationalError('private-database-path')):
                response=client.get(path);self.assertEqual(response.status_code,503);self.assertNotIn('private-database',response.text)
