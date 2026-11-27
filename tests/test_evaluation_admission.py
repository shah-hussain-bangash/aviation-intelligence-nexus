"""Synthetic bytes prove archive staging does not open member data or admit row quality."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from ml import admit_evaluation_archive as admission, register_evaluation as registration
from pipelines import journey_prediction as registered
from services.api.paths import ROOT


class EvaluationAdmissionTests(unittest.TestCase):
    def setUp(self):
        (ROOT/'.local').mkdir(exist_ok=True)
        folder=tempfile.TemporaryDirectory(prefix='evaluation-admission-test-',dir=ROOT/'.local')
        self.addCleanup(folder.cleanup);self.root=Path(folder.name)
        source=self.root/'.local/models/delay-v2';source.mkdir(parents=True)
        raw=b'SYNTHETIC NON-PICKLE ADMISSION MODEL; DO NOT EXECUTE'
        model_pin=hashlib.sha256(raw).hexdigest();(source/'model.joblib').write_bytes(raw)
        report=json.loads((ROOT/'docs/reports/Delay_v2.json').read_text(encoding='utf-8'))
        report.update(artifact_sha256=model_pin,fixture='SYNTHETIC ADMISSION TEST; no inference or real flight data')
        public=self.root/'docs/reports/Delay_v2.json';public.parent.mkdir(parents=True)
        data=json.dumps(report).encode();public.write_bytes(data);(source/'report.json').write_bytes(data)
        plan=self.root/'ml/june_evaluation_plan.json';plan.parent.mkdir()
        plan.write_bytes((ROOT/'ml/june_evaluation_plan.json').read_bytes())
        for module in (admission,registration,registered):self.enterContext(patch.object(module,'ROOT',self.root))
        registration.prepare(self.root/'.local/plan',model_pin)
        self.record=self.root/'.local/plan/registration.json'
        self.record_pin=hashlib.sha256(self.record.read_bytes()).hexdigest()
        self.archive=self.root/'.local/candidate.zip';self.target=self.root/'.local/staged'

    def archive_fixture(self,names=None,compression=zipfile.ZIP_DEFLATED):
        with zipfile.ZipFile(self.archive,'w',compression=compression) as output:
            for name in names or [admission.CSV_NAME,'readme.html']:
                output.writestr(name,b'SYNTHETIC INVALID ROW SCHEMA; metadata staging must not inspect this.\n')
        return hashlib.sha256(self.archive.read_bytes()).hexdigest()

    def stage(self,archive_pin=None):
        return admission.stage(self.record,self.record_pin,self.archive,
                               archive_pin or hashlib.sha256(self.archive.read_bytes()).hexdigest(),self.target)

    def test_exact_bytes_and_metadata_staged_without_member_or_model_access(self):
        pin=self.archive_fixture();before=self.archive.read_bytes()
        with patch.object(zipfile.ZipFile,'open',side_effect=AssertionError('Member must not be opened')) as opened, \
             patch('joblib.load',side_effect=AssertionError('Model must not execute')) as load:
            result=self.stage(pin)
        opened.assert_not_called();load.assert_not_called()
        self.assertEqual(result['state'],'archive_metadata_staged');self.assertEqual(result['member_count'],2)
        self.assertEqual(result['archive_sha256'],pin);self.assertEqual((self.target/'archive.zip').read_bytes(),before)
        self.assertEqual(self.archive.read_bytes(),before);self.assertIsNone(result['row_count'])
        for key in ('member_data_opened','candidate_rows_parsed','candidate_labels_inspected','csv_schema_verified',
                    'csv_crc_verified','row_period_verified','data_quality_verified','source_origin_verified',
                    'source_rights_verified','evaluation_authorized','global_single_use_enforced','import_performed','production_ready'):
            self.assertIs(result[key],False)

    def test_wrong_archive_pin_creates_no_output(self):
        self.archive_fixture()
        with self.assertRaisesRegex(ValueError,'candidate_archive_pin_mismatch'):self.stage('0'*64)
        self.assertFalse(self.target.exists())

    def test_changed_registration_rejected_before_archive_access(self):
        self.archive_fixture();self.record.write_bytes(self.record.read_bytes()+b' ')
        with patch.object(admission,'owned_snapshot') as capture:
            with self.assertRaisesRegex(ValueError,'pinned_file_changed'):self.stage()
        capture.assert_not_called();self.assertFalse(self.target.exists())

    def test_changed_frozen_model_rejected_without_archive_access(self):
        self.archive_fixture();model=self.record.parent/'model/model.joblib'
        model.write_bytes(model.read_bytes()+b'changed')
        with patch.object(admission,'owned_snapshot') as capture:
            with self.assertRaises(ValueError):self.stage()
        capture.assert_not_called();self.assertFalse(self.target.exists())

    def test_wrong_month_or_multiple_csv_members_rejected_without_rows(self):
        for names in [[admission.CSV_NAME.replace('2025_6','2025_5')],[admission.CSV_NAME,'second.csv']]:
            with self.subTest(names=names):
                self.archive_fixture(names)
                with self.assertRaisesRegex(ValueError,'declared_june_csv_member_required'):self.stage()
                self.assertFalse(self.target.exists())

    def test_unsafe_member_paths_and_unsupported_compression_are_rejected(self):
        for names,compression in [([admission.CSV_NAME,'../outside.txt'],zipfile.ZIP_DEFLATED),
                                  ([admission.CSV_NAME,'C:/outside.txt'],zipfile.ZIP_DEFLATED),
                                  ([admission.CSV_NAME],zipfile.ZIP_BZIP2)]:
            with self.subTest(names=names,compression=compression):
                self.archive_fixture(names,compression)
                with self.assertRaises(ValueError):self.stage()
                self.assertFalse(self.target.exists())

    def test_malformed_zip_is_not_staged(self):
        self.archive.write_bytes(b'SYNTHETIC NOT A ZIP')
        with self.assertRaises(ValueError):self.stage()
        self.assertFalse(self.target.exists())

    def test_existing_or_nonprivate_outputs_preserve_existing_bytes(self):
        self.archive_fixture();self.stage()
        before={p.name:p.read_bytes() for p in self.target.iterdir()}
        with self.assertRaises(ValueError):self.stage()
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.target.iterdir()})
        for target in (self.root/'outside',self.root/'.local'/'..'/'escape'):
            with self.assertRaises(ValueError):
                admission.stage(self.record,self.record_pin,self.archive,hashlib.sha256(self.archive.read_bytes()).hexdigest(),target)

    def test_registration_change_during_capture_retains_partial_bytes_without_success_receipt(self):
        self.archive_fixture();original=admission.archive_metadata
        def changed(stream):
            metadata=original(stream);self.record.write_bytes(self.record.read_bytes()+b' ');return metadata
        with patch.object(admission,'archive_metadata',side_effect=changed):
            with self.assertRaises(ValueError):self.stage()
        self.assertTrue((self.target/'archive.zip').exists());self.assertFalse((self.target/'admission.json').exists())
