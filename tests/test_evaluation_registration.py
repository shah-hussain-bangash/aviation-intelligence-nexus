"""Synthetic model bytes test pre-registration; no candidate rows or models execute."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from ml import register_evaluation as registration
from pipelines import journey_prediction as registered
from services.api.paths import ROOT


class EvaluationRegistrationTests(unittest.TestCase):
    def setUp(self):
        (ROOT/'.local').mkdir(exist_ok=True)
        folder=tempfile.TemporaryDirectory(prefix='evaluation-registration-test-',dir=ROOT/'.local')
        self.addCleanup(folder.cleanup);self.root=Path(folder.name)
        self.source=self.root/'.local/models/delay-v2';self.source.mkdir(parents=True)
        self.model=b'SYNTHETIC NON-PICKLE UNIT FIXTURE; MUST NEVER BE DESERIALIZED'
        self.pin=hashlib.sha256(self.model).hexdigest()
        (self.source/'model.joblib').write_bytes(self.model)
        self.public=self.root/'docs/reports/Delay_v2.json';self.public.parent.mkdir(parents=True)
        self.report=json.loads((ROOT/'docs/reports/Delay_v2.json').read_text(encoding='utf-8'))
        self.report.update(artifact_sha256=self.pin,fixture='SYNTHETIC registration metadata; no inference executed')
        self.write_report(self.report)
        self.plan=self.root/'ml/june_evaluation_plan.json';self.plan.parent.mkdir()
        self.plan.write_bytes((ROOT/'ml/june_evaluation_plan.json').read_bytes())
        self.enterContext(patch.object(registration,'ROOT',self.root))
        self.enterContext(patch.object(registered,'ROOT',self.root))

    def write_report(self,value):
        raw=json.dumps(value).encode()
        (self.source/'report.json').write_bytes(raw);self.public.write_bytes(raw)

    def target(self,name='plan'):return self.root/'.local'/name

    def test_freezes_model_baseline_threshold_and_plan_without_deserialization(self):
        before={p:p.read_bytes() for p in self.source.iterdir()}
        with patch('joblib.load') as load:
            result=registration.prepare(self.target(),self.pin)
        load.assert_not_called()
        self.assertEqual(result['state'],'plan_prepared');self.assertEqual(result['candidate_period'],'2025-06')
        self.assertEqual(result['frozen_threshold'],self.report['threshold'])
        self.assertEqual(result['constant_training_prior'],self.report['training_delay_prevalence'])
        self.assertEqual((self.target()/'plan.json').read_bytes(),self.plan.read_bytes())
        self.assertEqual((self.target()/'model/model.joblib').read_bytes(),self.model)
        self.assertEqual(json.loads((self.target()/'registration.json').read_text()),result)
        for field in ('candidate_archive_registered','candidate_rows_read','candidate_labels_read','inference_executed',
                      'metrics_computed','bootstrap_executed','globally_untouched_holdout_established',
                      'evaluation_attempt_created','global_single_use_enforced','primary_database_accessed','production_ready'):
            self.assertIs(result[field],False)
        self.assertEqual(before,{p:p.read_bytes() for p in self.source.iterdir()})

    def test_changed_public_plan_is_rejected_before_private_output(self):
        self.plan.write_bytes(self.plan.read_bytes()+b' ')
        with self.assertRaisesRegex(ValueError,'frozen_evaluation_plan_changed'):
            registration.prepare(self.target(),self.pin)
        self.assertFalse(self.target().exists())

    def test_registered_model_pin_or_changed_bytes_cannot_be_substituted(self):
        with self.assertRaises(ValueError):registration.prepare(self.target(),'0'*64)
        (self.source/'model.joblib').write_bytes(self.model+b'changed')
        with self.assertRaises(ValueError):registration.prepare(self.target(),self.pin)
        self.assertFalse(self.target().exists())

    def test_candidate_period_already_used_is_not_registered(self):
        changed=copy.deepcopy(self.report);changed['protocol']['period_groups']['test'].append('2025-06')
        self.write_report(changed)
        with self.assertRaisesRegex(ValueError,'candidate_period_overlaps'):
            registration.prepare(self.target(),self.pin)
        self.assertFalse((self.target()/'registration.json').exists())
        self.assertTrue((self.target()/'model/model.joblib').exists())  # Failed private copy is retained.

    def test_unrecorded_period_groups_are_not_assumed_untouched(self):
        changed=copy.deepcopy(self.report);changed.pop('protocol')
        self.write_report(changed)
        with self.assertRaisesRegex(ValueError,'registered_period_groups_required'):
            registration.prepare(self.target(),self.pin)
        self.assertFalse((self.target()/'registration.json').exists())

    def test_invalid_or_missing_frozen_baseline_and_threshold_are_rejected(self):
        for index,(key,value) in enumerate([('threshold',True),('threshold',None),
                                          ('training_delay_prevalence',float('nan')),
                                          ('training_delay_prevalence',1)]):
            with self.subTest(key=key,value=value):
                changed=copy.deepcopy(self.report);changed[key]=value;self.write_report(changed)
                with self.assertRaises(ValueError):registration.prepare(self.target(str(index)),self.pin)
                self.assertFalse((self.target(str(index))/'registration.json').exists())

    def test_existing_or_nonprivate_destination_and_retries_preserve_files(self):
        registration.prepare(self.target(),self.pin)
        before={str(p.relative_to(self.target())):p.read_bytes() for p in self.target().rglob('*') if p.is_file()}
        for target in (self.target(),self.root/'outside',self.root/'.local'/'..'/'escape'):
            with self.assertRaises(ValueError):registration.prepare(target,self.pin)
        self.assertEqual(before,{str(p.relative_to(self.target())):p.read_bytes() for p in self.target().rglob('*') if p.is_file()})

    def test_source_change_during_copy_cannot_create_completed_registration(self):
        with patch.object(registered,'source_preserved',return_value=False):
            with self.assertRaisesRegex(ValueError,'registered_source_changed'):
                registration.prepare(self.target(),self.pin)
        self.assertFalse((self.target()/'registration.json').exists())

    def test_cli_failure_is_generic_and_does_not_echo_private_input(self):
        result=subprocess.run([sys.executable,'-m','ml.register_evaluation',str(self.target()),
                               '--model-sha256','PRIVATE-BAD-PIN'],capture_output=True,text=True,cwd=ROOT)
        self.assertEqual(result.returncode,2);self.assertNotIn('PRIVATE-BAD-PIN',result.stderr)
        self.assertIn('not confirmed',result.stderr);self.assertFalse(self.target().exists())
