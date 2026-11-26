"""Combined workflow fixture checks; no real user or LLM acceptance is inferred."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pipelines import verify_case_journey as journey


class CaseJourneyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def test_combined_api_journey_pins_history_review_and_restart(self):
        report=journey.exercise(self.root/'new')
        self.assertTrue(report['passed']);self.assertTrue(all(report['checks'].values()))
        self.assertEqual([e['version'] for e in report['trace']],list(range(1,7)))
        self.assertEqual([e['action'] for e in report['trace']],['opened','note','evidence','agent','gate','close'])
        self.assertEqual(report['trace'][-1]['status'],'closed')
        self.assertEqual(report['trace'][-1]['case_sha256'],report['final_case_sha256'])
        self.assertEqual(report['trace'][2]['case_sha256'],report['captured_case_sha256'])
        for name in ['no_provider_or_planner_execution','missing_case_store_fail_closed',
                     'worker_unavailable_refuses_submission','other_admin_private_case_denied',
                     'viewer_review_and_case_writes_denied','new_application_instance_preserves_closed_case']:
            self.assertTrue(report['checks'][name])

    def test_existing_directory_is_never_adopted_or_replaced(self):
        target=self.root/'existing';target.mkdir();marker=target/'preserve.txt';marker.write_text('preserve')
        with self.assertRaises(FileExistsError):journey.exercise(target)
        self.assertEqual(marker.read_text(),'preserve');self.assertEqual(list(target.iterdir()),[marker])

    def test_public_verifier_refuses_outside_private_root(self):
        with patch.object(journey,'ROOT',self.root):
            with self.assertRaisesRegex(ValueError,'new_private_directory'):journey.verify(self.root/'outside')
        self.assertFalse((self.root/'outside').exists())

    def test_report_keeps_code_fingerprints_separate_from_prediction_pin(self):
        with patch.object(journey,'ROOT',self.root),patch.object(journey,'SOURCES',()):
            result=journey.verify(self.root/'.local'/'new')
        self.assertTrue(result['passed']);self.assertIsInstance(result['source_sha256'],dict)
        self.assertEqual(len(result['prediction_source_sha256']),64)
        self.assertTrue(result['worker_availability_stubbed']);self.assertTrue(result['deterministic_checkpoint_fixture'])
        for field in ['production_ready','generator_executed','planner_executed','prediction_inference_executed',
                      'retrieval_executed','worker_loop_executed','genuine_human_acceptance','deployment_performed','primary_database_accessed']:
            self.assertFalse(result[field])
        saved=json.loads((self.root/'.local/new/report.json').read_text())
        self.assertEqual(saved,result);self.assertNotIn('password',json.dumps(result).lower())

    def test_failed_rehearsal_does_not_claim_execution_or_leak_private_error(self):
        def fail(directory):
            directory.mkdir(parents=True);raise RuntimeError('PRIVATE_SENTINEL')
        with patch.object(journey,'ROOT',self.root),patch.object(journey,'SOURCES',()),patch.object(journey,'exercise',side_effect=fail):
            report=journey.verify(self.root/'.local'/'failed')
        self.assertFalse(report['passed']);self.assertEqual(report['error'],'combined_journey_check_failed')
        self.assertFalse(report['synthetic_milp_executed']);self.assertFalse(report['recorded_distribution_reader_executed'])
        self.assertNotIn('PRIVATE_SENTINEL',json.dumps(report))


if __name__=='__main__':unittest.main()
