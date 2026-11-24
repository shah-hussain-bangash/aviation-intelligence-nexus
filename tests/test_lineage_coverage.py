from contextlib import redirect_stdout
import io
import json
import unittest
from unittest.mock import patch
from pipelines import lineage_coverage
from pipelines.intake_bts import intake
from tests import test_verify_intake


class LineageCoverageTests(unittest.TestCase):
    def setUp(self):
        test_verify_intake.VerifyIntakeTests.setUp(self)
        receipt=json.loads(self.receipt.read_text(encoding='utf-8'))
        self.recorded={'report_sha256':'a'*64,'months':[{'period':'2025-01','manifests':[{'sha256':receipt['archive_sha256'],'rows_read':1}]}]}
        self.patch=patch('pipelines.lineage_coverage.load_quality',return_value=self.recorded);self.patch.start()
    def tearDown(self):self.patch.stop();self.temp.cleanup()

    def test_repeated_accepted_runs_count_once_and_input_files_unchanged(self):
        intake(self.root/'source.zip',self.root/'runs',2025,1)
        before={str(p):p.read_bytes() for p in (self.root/'runs').rglob('*') if p.is_file()}
        r=lineage_coverage.audit(self.root/'runs')
        self.assertTrue(r['coverage_complete']);self.assertFalse(r['needs_review'])
        self.assertEqual((r['matched_months'],r['matched_archives'],r['matched_declared_rows']),(1,1,1))
        self.assertEqual((r['accepted_runs_checked'],r['repeated_accepted_runs']),(2,1))
        self.assertEqual(before,{str(p):p.read_bytes() for p in (self.root/'runs').rglob('*') if p.is_file()})
        self.assertNotIn(str(self.root),json.dumps(r));self.assertFalse(r['rows_rescanned']);self.assertFalse(r['live_database_checked'])

    def test_missing_month_and_same_count_wrong_hash_do_not_match(self):
        self.recorded['months'].append({'period':'2025-02','manifests':[{'sha256':'b'*64,'rows_read':1}]})
        r=lineage_coverage.audit(self.root/'runs');self.assertFalse(r['coverage_complete']);self.assertEqual(r['archives'][1]['status'],'missing')
        self.recorded['months'][0]['manifests'][0]['sha256']='c'*64
        r=lineage_coverage.audit(self.root/'runs');self.assertEqual(r['matched_declared_rows'],0)
        self.assertEqual(len(r['unlinked_accepted_archives']),1);self.assertTrue(r['needs_review'])

    def test_consistent_unsigned_counter_edit_is_reported_as_claim_mismatch(self):
        receipt=json.loads(self.receipt.read_text(encoding='utf-8'));receipt.update(rows_read=2,unique_identities=2)
        self.receipt.write_text(json.dumps(receipt),encoding='utf-8')
        r=lineage_coverage.audit(self.root/'runs')
        self.assertEqual(r['archives'][0]['status'],'claim_mismatch');self.assertFalse(r['coverage_complete']);self.assertEqual(r['matched_declared_rows'],0)

    def test_quarantine_and_changed_archive_cannot_fill_coverage(self):
        bad=self.root/'bad.zip';bad.write_bytes(b'not a zip');intake(bad,self.root/'runs',2025,1)
        r=lineage_coverage.audit(self.root/'runs');self.assertTrue(r['coverage_complete']);self.assertTrue(r['needs_review']);self.assertEqual(r['quarantined_runs'],1)
        raw=bytearray(self.archive.read_bytes());raw[-1]^=1;self.archive.write_bytes(raw)
        r=lineage_coverage.audit(self.root/'runs');self.assertFalse(r['coverage_complete']);self.assertEqual(r['unverifiable_runs'],1)

    def test_empty_manifest_month_and_duplicate_expected_hash_cannot_report_complete(self):
        self.recorded['months'].append({'period':'2025-02','manifests':[]})
        self.assertFalse(lineage_coverage.audit(self.root/'runs')['coverage_complete'])
        self.recorded['months'][1]['manifests']=[dict(self.recorded['months'][0]['manifests'][0])]
        with self.assertRaises(ValueError):lineage_coverage.audit(self.root/'runs')

    def test_cli_uses_distinct_review_and_unavailable_exit_codes_without_exception_details(self):
        for result,code in (({'needs_review':True},1),(ValueError('PRIVATE-DETAIL'),2)):
            output=io.StringIO();kwargs={'side_effect':result} if isinstance(result,Exception) else {'return_value':result}
            with patch('sys.argv',['lineage_coverage']),patch.object(lineage_coverage,'audit',**kwargs),redirect_stdout(output):
                with self.assertRaises(SystemExit) as error:lineage_coverage.main()
            self.assertEqual(error.exception.code,code);self.assertNotIn('PRIVATE-DETAIL',output.getvalue())
