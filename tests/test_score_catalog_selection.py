import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from ml.evaluate_synthetic_holdout import evaluate_once
from ml.score_catalog_selection import score_selected
from ml.synthetic_model_bundle import export_bundle,score
from ml.synthetic_model_catalog import initialize,register,select,status
from ml.train_preprocessing import signature
from ml.verify_synthetic_evaluation import setup
from services.api.paths import ROOT


class CatalogSelectedScoringTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        experiment=self.root/'experiment';setup(experiment);self.evaluation=evaluate_once(experiment)
        receipt=hashlib.sha256((experiment/'holdout-evaluation.json').read_bytes()).hexdigest()
        self.bundle=self.root/'a.json';export_bundle(experiment,self.bundle,receipt_sha256=receipt)
        self.model=hashlib.sha256(self.bundle.read_bytes()).hexdigest()
        self.variant=self.root/'b.json';self.variant.write_bytes(self.bundle.read_bytes()+b'\n')
        self.other=hashlib.sha256(self.variant.read_bytes()).hexdigest()
        self.features=self.root/'features.json';self.features.write_bytes((experiment/'holdout-features.json').read_bytes())
        self.features_hash=hashlib.sha256(self.features.read_bytes()).hexdigest()
        self.catalog=self.root/'catalog';initialize(self.catalog)
        register(self.catalog,self.bundle,bundle_sha256=self.model)
        register(self.catalog,self.variant,bundle_sha256=self.other)
        select(self.catalog,self.model,expected_revision=2,reason='Synthetic initial selection')

    def tearDown(self):self.temp.cleanup()

    def call(self,revision=3,model=None):
        return score_selected(self.catalog,self.features,expected_revision=revision,
                              model_sha256=self.model if model is None else model,features_sha256=self.features_hash)

    def test_exact_parity_lineage_and_read_only_files(self):
        before={p.relative_to(self.root):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        result=self.call()
        self.assertEqual(result['catalog_revision'],3)
        self.assertEqual(result['selection_event']['model_sha'],self.model)
        self.assertEqual(result['catalog_snapshot_sha256'],signature(status(self.catalog)))
        self.assertEqual(signature([r['arrival_delay_minutes'] for r in result['scores']['predictions']]),self.evaluation['prediction_sha256'])
        self.assertEqual(result['prediction_sha256'],signature(result['scores']['predictions']))
        self.assertFalse(result['production_ready']);self.assertTrue(result['read_only'])
        self.assertEqual(before,{p.relative_to(self.root):p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_stale_or_nonselected_model_refused_before_feature_read(self):
        self.features.unlink()
        for revision,model in [(2,self.model),(3,self.other)]:
            with self.assertRaisesRegex(ValueError,'selected_version_mismatch'):self.call(revision,model)

    def test_wrong_feature_pin_refused(self):
        self.features_hash='0'*64
        with self.assertRaisesRegex(ValueError,'features_identity_mismatch'):self.call()

    def test_switch_and_rollback_change_bound_selection_event(self):
        select(self.catalog,self.other,expected_revision=3,reason='Synthetic byte variant')
        switched=self.call(4,self.other)
        select(self.catalog,self.model,expected_revision=4,reason='Return to previous bytes',rollback=True)
        rolled=self.call(5)
        self.assertEqual(rolled['scores']['predictions'],switched['scores']['predictions'])
        self.assertEqual(rolled['selection_event']['action'],'rollback')
        self.assertNotEqual(rolled['catalog_snapshot_sha256'],switched['catalog_snapshot_sha256'])

    def test_switch_away_and_back_during_scoring_is_refused(self):
        def changing(*args,**kwargs):
            result=score(*args,**kwargs)
            select(self.catalog,self.other,expected_revision=3,reason='Interleaved switch')
            select(self.catalog,self.model,expected_revision=4,reason='Interleaved return',rollback=True)
            return result
        with patch('ml.score_catalog_selection.score',side_effect=changing):
            with self.assertRaisesRegex(ValueError,'catalog_changed_during_scoring'):self.call()

    def test_feature_changes_during_scoring_are_refused(self):
        def changing(*args,**kwargs):
            result=score(*args,**kwargs);self.features.write_bytes(self.features.read_bytes()+b' ');return result
        with patch('ml.score_catalog_selection.score',side_effect=changing):
            with self.assertRaisesRegex(ValueError,'features_changed'):self.call()

    def test_changed_registered_artifact_refused(self):
        (self.catalog/'bundles'/(self.model+'.json')).write_bytes(b'changed')
        with self.assertRaises(Exception):self.call()

    def test_cli_result_and_generic_refusal_without_prediction_leak(self):
        command=[sys.executable,'-m','ml.score_catalog_selection',str(self.catalog),str(self.features),
                 '--expected-revision','3','--model-sha256',self.model,'--features-sha256',self.features_hash]
        process=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=30)
        self.assertEqual(process.returncode,0,process.stderr)
        self.assertEqual(json.loads(process.stdout),self.call())
        command[-1]='0'*64
        refused=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=30)
        self.assertEqual(refused.returncode,2)
        self.assertEqual(set(json.loads(refused.stdout)),{'error','production_ready'})


if __name__=='__main__':unittest.main()
