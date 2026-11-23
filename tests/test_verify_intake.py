import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from pipelines.intake_bts import intake
from pipelines.verify_intake import verify_run
from tests.test_intake_bts import FIELDS,ROW
import csv,io,zipfile


class VerifyIntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        raw=self.root/'source.zip';text=io.StringIO();writer=csv.writer(text);writer.writerow(FIELDS);writer.writerow(ROW)
        with zipfile.ZipFile(raw,'w') as z:z.writestr('data.csv',text.getvalue())
        result=intake(raw,self.root/'runs',2025,1)
        self.run=self.root/'runs'/result['disposition']/result['run_id']
        self.receipt=self.run/'receipt.json';self.archive=self.run/'archive.zip'

    def tearDown(self):self.temp.cleanup()
    def edit(self,change):
        value=json.loads(self.receipt.read_text());change(value);self.receipt.write_text(json.dumps(value))

    def test_accepted_verification_reads_without_changing_artifacts_or_granting_import(self):
        before={p.name:p.read_bytes() for p in self.run.iterdir()}
        result=verify_run(self.run)
        self.assertTrue(result['verified']);self.assertFalse(result['import_authorized'])
        self.assertFalse(result['rows_rescanned']);self.assertFalse(result['receipt_authenticated'])
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.run.iterdir()})

    def test_quarantine_consistency_is_not_data_acceptance(self):
        bad=self.root/'bad.zip';bad.write_bytes(b'not a zip')
        result=intake(bad,self.root/'runs',2025,1)
        checked=verify_run(self.root/'runs'/'quarantined'/result['run_id'])
        self.assertTrue(checked['verified']);self.assertEqual(checked['disposition'],'quarantined')
        self.assertFalse(checked['import_authorized'])

    def test_same_length_archive_changes_are_rejected_by_hash(self):
        value=bytearray(self.archive.read_bytes());value[3]^=1;self.archive.write_bytes(value)
        with self.assertRaises(ValueError):verify_run(self.run)

    def test_counter_claims_unknown_fields_and_approval_flags_are_rejected(self):
        original=self.receipt.read_bytes()
        for change in (lambda r:r.update(rows_read=2),lambda r:r.update(production_ready=True),
                       lambda r:r.update(private='DO-NOT-EXPOSE'),lambda r:r.update(archive_size_bytes=True),
                       lambda r:r.update(checked_at='2026-01-01T00:00:00')):
            self.receipt.write_bytes(original);self.edit(change)
            with self.assertRaises(ValueError):verify_run(self.run)

    def test_renamed_or_reclassified_run_does_not_match_receipt(self):
        renamed=self.run.parent/('0'*32);shutil.copytree(self.run,renamed)
        with self.assertRaises(ValueError):verify_run(renamed)
        reclassified=self.root/'quarantined'/self.run.name;shutil.copytree(self.run,reclassified)
        with self.assertRaises(ValueError):verify_run(reclassified)

    def test_unsigned_consistent_counter_edits_are_explicitly_not_authenticated(self):
        self.edit(lambda r:r.update(rows_read=2,unique_identities=2))
        result=verify_run(self.run)
        self.assertTrue(result['verified']);self.assertEqual(result['declared_rows_read'],2)
        self.assertFalse(result['rows_rescanned']);self.assertFalse(result['receipt_authenticated'])

    def test_cli_failure_is_sanitized_and_does_not_print_private_path(self):
        result=subprocess.run([sys.executable,'-m','pipelines.verify_intake',str(self.run)],text=True,capture_output=True)
        self.assertEqual(result.returncode,2)  # CLI cannot inspect outside the checkout's .local boundary.
        self.assertNotIn(str(self.root),result.stdout+result.stderr)
        self.assertFalse(json.loads(result.stdout)['verified'])
