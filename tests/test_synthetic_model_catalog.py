from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from ml.evaluate_synthetic_holdout import evaluate_once
from ml.synthetic_model_bundle import export_bundle
from ml.synthetic_model_catalog import initialize,register,select,status
from ml.verify_synthetic_evaluation import setup
from services.api.paths import ROOT


class SyntheticModelCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        experiment=self.root/'experiment';setup(experiment);evaluate_once(experiment)
        receipt=hashlib.sha256((experiment/'holdout-evaluation.json').read_bytes()).hexdigest()
        self.a=self.root/'a.json';export_bundle(experiment,self.a,receipt_sha256=receipt)
        self.b=self.root/'b.json';self.b.write_bytes(self.a.read_bytes()+b'\n')
        self.sha_a=hashlib.sha256(self.a.read_bytes()).hexdigest();self.sha_b=hashlib.sha256(self.b.read_bytes()).hexdigest()
        self.case=self.root/'catalog';initialize(self.case)

    def tearDown(self):self.temp.cleanup()

    def register_both(self):
        register(self.case,self.a,bundle_sha256=self.sha_a);register(self.case,self.b,bundle_sha256=self.sha_b)

    def test_register_select_and_previous_rollback_history(self):
        self.register_both()
        select(self.case,self.sha_a,expected_revision=2,reason='Initial synthetic selection')
        select(self.case,self.sha_b,expected_revision=3,reason='Synthetic serialization variant')
        selected=select(self.case,self.sha_a,expected_revision=4,reason='Return to prior bytes',rollback=True)
        result=status(self.case)
        self.assertEqual(result['current'],self.sha_a);self.assertEqual(result['previous'],self.sha_b)
        self.assertEqual(selected['revision'],5)
        self.assertEqual([e['action'] for e in result['events']],['register','register','select','select','rollback'])
        self.assertFalse(result['deployed']);self.assertFalse(result['production_ready'])

    def test_replay_registration_and_read_only_status_preserve_files(self):
        register(self.case,self.a,bundle_sha256=self.sha_a)
        before={p.relative_to(self.case):p.read_bytes() for p in self.case.rglob('*') if p.is_file()}
        self.assertFalse(register(self.case,self.a,bundle_sha256=self.sha_a)['registered'])
        self.assertEqual(status(self.case)['revision'],1)
        self.assertEqual(before,{p.relative_to(self.case):p.read_bytes() for p in self.case.rglob('*') if p.is_file()})

    def test_stale_revision_unknown_version_and_invalid_rollback_leave_state(self):
        self.register_both();before=status(self.case)
        for model,revision,rollback in [(self.sha_a,1,False),('0'*64,2,False),(self.sha_a,2,True)]:
            with self.assertRaises(ValueError):select(self.case,model,expected_revision=revision,reason='Refused',rollback=rollback)
        self.assertEqual(before,status(self.case))

    def test_concurrent_expected_revision_only_one_wins(self):
        self.register_both()
        def attempt(sha):
            try:return select(self.case,sha,expected_revision=2,reason='Concurrent synthetic choice')['revision']
            except ValueError:return 'refused'
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(attempt,[self.sha_a,self.sha_b]))
        self.assertEqual(results.count(3),1);self.assertEqual(results.count('refused'),1)
        self.assertEqual(status(self.case)['revision'],3)

    def test_changed_registered_bytes_block_status_and_selection(self):
        self.register_both();path=self.case/'bundles'/(self.sha_a+'.json');path.write_bytes(b'changed')
        with self.assertRaises(Exception):status(self.case)
        with self.assertRaises(Exception):select(self.case,self.sha_b,expected_revision=2,reason='Must fail')
        with closing(sqlite3.connect(self.case/'catalog.sqlite3')) as db:self.assertEqual(db.execute('SELECT revision FROM catalog').fetchone()[0],2)

    def test_event_history_change_is_not_silently_repaired(self):
        self.register_both()
        with closing(sqlite3.connect(self.case/'catalog.sqlite3')) as db,db:db.execute('DELETE FROM events WHERE revision=1')
        with self.assertRaises(ValueError):status(self.case)

    def test_failed_metadata_commit_leaves_reusable_verified_orphan(self):
        with patch('ml.synthetic_model_catalog.record',side_effect=RuntimeError('injected failure')):
            with self.assertRaises(RuntimeError):register(self.case,self.a,bundle_sha256=self.sha_a)
        self.assertEqual(status(self.case)['revision'],0)
        self.assertTrue((self.case/'bundles'/(self.sha_a+'.json')).exists())
        self.assertTrue(register(self.case,self.a,bundle_sha256=self.sha_a)['registered'])
        self.assertEqual(status(self.case)['revision'],1)

    def test_wrong_artifact_pin_and_existing_directory_refused(self):
        with self.assertRaises(ValueError):register(self.case,self.a,bundle_sha256='0'*64)
        with self.assertRaises(FileExistsError):initialize(self.case)
        self.assertEqual(status(self.case)['revision'],0)

    def test_cli_init_register_select_status(self):
        other=self.root/'cli-catalog';command=[sys.executable,'-m','ml.synthetic_model_catalog',str(other)]
        for args in [['init'],['register',str(self.a),'--bundle-sha256',self.sha_a],
                     ['select',self.sha_a,'--expected-revision','1','--reason','CLI synthetic choice'],['status']]:
            result=subprocess.run(command+args,cwd=ROOT,capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['current'],self.sha_a)
        refused=subprocess.run(command+['select',self.sha_b,'--expected-revision','1','--reason','Stale'],cwd=ROOT,capture_output=True,timeout=30)
        self.assertEqual(refused.returncode,2)


if __name__=='__main__':unittest.main()
