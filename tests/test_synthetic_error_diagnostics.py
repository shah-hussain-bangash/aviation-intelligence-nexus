import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from sklearn.linear_model import Ridge

from ml.evaluate_synthetic_holdout import evaluate_once
from ml.synthetic_error_diagnostics import FILES, diagnostics
from ml.verify_synthetic_evaluation import setup
from services.api.paths import ROOT


class SyntheticErrorDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'experiment'
        setup(self.root);self.evaluation=evaluate_once(self.root)
        self.pin=hashlib.sha256((self.root/'holdout-evaluation.json').read_bytes()).hexdigest()

    def tearDown(self):self.temp.cleanup()

    def run_report(self):return diagnostics(self.root,receipt_sha256=self.pin)

    def write(self,name,value):
        (self.root/name).write_text(json.dumps(value),encoding='utf-8')

    def test_descriptive_counts_and_weighted_error_reconcile_without_writes_or_fit(self):
        before={name:(self.root/name).read_bytes() for name in FILES}
        with patch.object(Ridge,'fit',side_effect=AssertionError('no fit')):
            report=self.run_report()
        self.assertTrue(report['verified'],report)
        self.assertEqual(report['overall']['selected'],self.evaluation['selected_metrics'])
        self.assertEqual(sum(r['records'] for r in report['by_origin']),8)
        for grouping in ('by_origin','by_training_category'):
            weighted=sum(r['selected']['mae']*r['records'] for r in report[grouping] if r['records'])/8
            self.assertAlmostEqual(weighted,report['overall']['selected']['mae'])
        self.assertTrue(all(r['small_cohort'] for r in report['by_origin']))
        self.assertEqual(report['by_training_category'][1]['records'],0)
        self.assertIsNone(report['by_training_category'][1]['selected'])
        self.assertFalse(report['new_evaluation_attempt']);self.assertFalse(report['production_ready'])
        self.assertEqual(before,{name:(self.root/name).read_bytes() for name in FILES})
        self.assertEqual(set(p.name for p in self.root.iterdir()),set(before)|{'report.json'})
        self.assertEqual(report,self.run_report())

    def test_wrong_receipt_pin_refused(self):
        self.assertFalse(diagnostics(self.root,receipt_sha256='0'*64)['verified'])
        self.assertFalse(diagnostics(self.root,receipt_sha256=None)['verified'])

    def test_changed_frozen_input_refused(self):
        path=self.root/'holdout-features.json';rows=json.loads(path.read_text(encoding='utf-8'))
        rows[0]['temperature_c']+=1;self.write(path.name,rows)
        self.assertFalse(self.run_report()['verified'])

    def test_re_pinned_incorrect_aggregate_refused(self):
        value=dict(self.evaluation);value['selected_metrics']={**value['selected_metrics'],'mae':999}
        self.write('holdout-evaluation.json',value)
        self.pin=hashlib.sha256((self.root/'holdout-evaluation.json').read_bytes()).hexdigest()
        self.assertFalse(self.run_report()['verified'])

    def test_missing_or_mismatched_claim_refused_without_replacement(self):
        path=self.root/'holdout-attempt.json';value=json.loads(path.read_text(encoding='utf-8'))
        value['attempt_id']='different';self.write(path.name,value)
        self.assertFalse(self.run_report()['verified'])
        path.unlink();self.assertFalse(self.run_report()['verified']);self.assertFalse(path.exists())

    def test_failed_receipt_refused(self):
        value={**self.evaluation,'state':'failed'};self.write('holdout-evaluation.json',value)
        self.pin=hashlib.sha256((self.root/'holdout-evaluation.json').read_bytes()).hexdigest()
        self.assertFalse(self.run_report()['verified'])

    def test_unknown_origin_and_bias_match_independent_dense_calculation(self):
        # New disposable experiment, before its evaluation; never reset a consumed claim.
        other=Path(self.temp.name)/'unknown';setup(other)
        features=json.loads((other/'holdout-features.json').read_text(encoding='utf-8'))
        features[0]['origin']='ZZZ'
        data=json.dumps(features).encode();(other/'holdout-features.json').write_bytes(data)
        policy=json.loads((other/'holdout-policy.json').read_text(encoding='utf-8'))
        policy['features_sha256']=hashlib.sha256(data).hexdigest()
        (other/'holdout-policy.json').write_text(json.dumps(policy),encoding='utf-8')
        evaluated=evaluate_once(other);self.assertEqual(evaluated['state'],'evaluated')
        pin=hashlib.sha256((other/'holdout-evaluation.json').read_bytes()).hexdigest()
        report=diagnostics(other,receipt_sha256=pin);self.assertTrue(report['verified'],report)
        self.assertEqual(report['by_training_category'][1]['records'],1)
        selection=json.loads((other/'frozen-selection.json').read_text(encoding='utf-8'))
        state=selection['preprocessing']['fit_state'];selected=selection['selected']
        x=[0.0]*len(state['origin_categories'])+[(features[0][col]-state['numeric_mean'][i])/state['numeric_scale'][i] for i,col in enumerate(state['numeric_columns'])]
        prediction=float(np.asarray(x)@np.asarray(selected['coefficients'])+selected['intercept'])
        target=json.loads((other/'holdout-labels.json').read_text(encoding='utf-8'))[0]['arrival_delay_minutes']
        group=report['by_training_category'][1]
        self.assertAlmostEqual(group['mean_prediction_minus_actual'],prediction-target)
        self.assertAlmostEqual(group['selected']['mae'],abs(prediction-target))

    def test_cli_exit_status_and_no_row_level_values(self):
        command=[sys.executable,'-m','ml.synthetic_error_diagnostics',str(self.root),'--receipt-sha256',self.pin]
        process=subprocess.run(command,cwd=ROOT,text=True,capture_output=True,timeout=30)
        self.assertEqual(process.returncode,0,process.stderr)
        report=json.loads(process.stdout);self.assertTrue(report['verified'])
        self.assertNotIn('synthetic-test-0',process.stdout)
        command[-1]='0'*64
        self.assertEqual(subprocess.run(command,cwd=ROOT,capture_output=True,timeout=30).returncode,2)


if __name__=='__main__':unittest.main()
