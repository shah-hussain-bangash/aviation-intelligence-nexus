import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from sklearn.linear_model import Ridge

from ml.evaluate_synthetic_holdout import evaluate_once
from ml.synthetic_model_bundle import export_bundle, score
from ml.train_preprocessing import signature
from ml.verify_synthetic_evaluation import setup
from services.api.paths import ROOT


class SyntheticModelBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.experiment=self.root/'experiment';setup(self.experiment)
        self.evaluated=evaluate_once(self.experiment)
        self.pin=hashlib.sha256((self.experiment/'holdout-evaluation.json').read_bytes()).hexdigest()
        self.bundle=self.root/'bundle.json'
        self.exported=export_bundle(self.experiment,self.bundle,receipt_sha256=self.pin)
        self.features=json.loads((self.experiment/'holdout-features.json').read_text(encoding='utf-8'))

    def tearDown(self):self.temp.cleanup()

    def scoring(self,features=None):
        return score(self.bundle,self.features if features is None else features,bundle_sha256=self.exported['bundle_sha256'])

    def test_parity_without_source_directory_or_fit(self):
        shutil.rmtree(self.experiment)
        before=self.bundle.read_bytes()
        with patch.object(Ridge,'fit',side_effect=AssertionError('no fitting')):result=self.scoring()
        self.assertEqual(signature([r['arrival_delay_minutes'] for r in result['predictions']]),self.evaluated['prediction_sha256'])
        self.assertEqual(result['records'],8);self.assertFalse(result['production_ready'])
        self.assertEqual(self.bundle.read_bytes(),before)
        value=json.loads(before)
        self.assertNotIn('training_query_ids',json.dumps(value));self.assertNotIn('holdout-labels',json.dumps(value))

    def test_wrong_pin_and_changed_bundle_refused(self):
        with self.assertRaises(ValueError):score(self.bundle,self.features,bundle_sha256='0'*64)
        self.bundle.write_bytes(self.bundle.read_bytes()+b' ')
        with self.assertRaises(ValueError):self.scoring()

    def test_re_pinned_invalid_scaling_and_extra_fields_refused(self):
        original=json.loads(self.bundle.read_bytes())
        for change in ('scale','extra'):
            value=json.loads(json.dumps(original))
            if change=='scale':value['state']['numeric_scale'][0]=0;value['state_sha256']=signature(value['state'])
            else:value['executable']='no'
            self.bundle.write_text(json.dumps(value),encoding='utf-8')
            pin=hashlib.sha256(self.bundle.read_bytes()).hexdigest()
            with self.assertRaises(ValueError):score(self.bundle,self.features,bundle_sha256=pin)

    def test_duplicate_real_scope_missing_and_oversize_features_refused(self):
        cases=[[],self.features*126,[self.features[0],self.features[0]]]
        real=dict(self.features[0]);real['source_scope']='historical';cases.append([real])
        missing=dict(self.features[0]);missing['status']='unavailable';cases.append([missing])
        labelled=dict(self.features[0]);labelled['arrival_delay_minutes']=1;cases.append([labelled])
        for rows in cases:
            with self.assertRaises(ValueError):self.scoring(rows)

    def test_unknown_origin_uses_same_layout_and_explicit_count(self):
        rows=[dict(self.features[0])];rows[0]['origin']='ZZZ'
        result=self.scoring(rows)
        self.assertEqual(result['unknown_origin_count'],1)
        state=json.loads(self.bundle.read_bytes())['state']
        expected=state['intercept']+sum((rows[0][col]-state['numeric_mean'][i])/state['numeric_scale'][i]*state['coefficients'][len(state['origin_categories'])+i] for i,col in enumerate(state['numeric_columns']))
        self.assertAlmostEqual(result['predictions'][0]['arrival_delay_minutes'],expected)

    def test_export_does_not_overwrite_or_write_inside_experiment(self):
        before=self.bundle.read_bytes()
        with self.assertRaises(FileExistsError):export_bundle(self.experiment,self.bundle,receipt_sha256=self.pin)
        self.assertEqual(self.bundle.read_bytes(),before)
        destination=self.experiment/'new.json'
        with self.assertRaises(ValueError):export_bundle(self.experiment,destination,receipt_sha256=self.pin)
        self.assertFalse(destination.exists())

    def test_invalid_receipt_never_exports(self):
        destination=self.root/'invalid.json'
        with self.assertRaises(ValueError):export_bundle(self.experiment,destination,receipt_sha256='0'*64)
        self.assertFalse(destination.exists())

    def test_actual_export_and_score_cli(self):
        destination=self.root/'cli-bundle.json'
        command=[sys.executable,'-m','ml.synthetic_model_bundle']
        export=subprocess.run(command+['export',str(self.experiment),str(destination),'--receipt-sha256',self.pin],cwd=ROOT,capture_output=True,text=True,timeout=30)
        self.assertEqual(export.returncode,0,export.stderr)
        pin=json.loads(export.stdout)['bundle_sha256']
        args=command+['score',str(destination),str(self.experiment/'holdout-features.json'),'--bundle-sha256',pin]
        scores=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=30)
        self.assertEqual(scores.returncode,0,scores.stderr)
        self.assertEqual(json.loads(scores.stdout),self.scoring())
        args[-1]='0'*64
        self.assertEqual(subprocess.run(args,cwd=ROOT,capture_output=True,timeout=30).returncode,2)


if __name__=='__main__':unittest.main()
