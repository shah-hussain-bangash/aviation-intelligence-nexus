from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from infra.rollback_evidence import FLAGS, binding, validate_receipt
from infra.state_contracts import current_contract_digest
from infra.publish_rollback import install_receipt, publish
from infra.status import rollback_drill_status


def receipt():
    return {'format': 'ain-rollback-drill-v2', 'checked_at': datetime.now(timezone.utc).isoformat(),
            'candidate_revision': 'a' * 40, 'rollback_revision': 'b' * 40,
            'candidate_images': {'api': 'sha256:' + 'a' * 64, 'web': 'sha256:' + 'c' * 64},
            'rollback_images': {'api': 'sha256:' + 'b' * 64, 'web': 'sha256:' + 'd' * 64},
            'schema_version': 7, 'contracts_sha256': current_contract_digest(),
            'flight_records': 100, 'active_jobs_at_start': 0, 'production_qualified': False,
            **{key: True for key in FLAGS}}


class RollbackBindingTests(unittest.TestCase):
    def test_build_schema_and_contracts_must_all_match(self):
        value = receipt()
        self.assertTrue(binding(value, 'a' * 40, 7)['candidate_matches_current_build'])
        self.assertEqual(binding(value, 'b' * 40, 7)['relation'], 'different_release')
        self.assertEqual(binding(value, 'a' * 40, 8)['relation'], 'schema_mismatch')
        self.assertEqual(binding(value, 'working-tree', 7)['relation'], 'unverified_build')
        value['contracts_sha256'] = '0' * 64
        self.assertEqual(binding(value, 'a' * 40, 7)['relation'], 'contract_mismatch')
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(binding(value, 'a' * 40, 7, Path(folder))['relation'], 'unavailable_contracts')

    def test_legacy_receipt_is_historical_even_when_revision_matches(self):
        value = receipt(); value['format'] = 'ain-rollback-drill-v1'
        del value['contracts_sha256']
        self.assertEqual(binding(value, 'a' * 40, 7)['relation'], 'legacy_unbound')

    def test_malformed_or_contradictory_receipts_fail_closed(self):
        for key, replacement in [('checked_at', '2026-01-01'), ('checked_at', '2099-01-01T00:00:00Z'), ('candidate_revision', 'working-tree'), ('contracts_sha256', 'bad'), ('active_jobs_at_start', True), ('production_qualified', True), ('flight_records', True), ('schema_version', True), ('prediction_parity', False), ('candidate_images', {'api': 'tag:latest'})]:
            with self.subTest(key=key, replacement=replacement):
                value = receipt(); value[key] = replacement
                with self.assertRaises((ValueError, TypeError)): validate_receipt(value)
        value = receipt(); value['rollback_images'] = deepcopy(value['candidate_images'])
        with self.assertRaises(ValueError): validate_receipt(value)

    def test_status_exports_only_allowlisted_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            value = receipt(); value['password_hash'] = 'DO-NOT-EXPOSE'
            path = Path(folder) / 'rollback-drill.json'; path.write_text(json.dumps(value), encoding='utf-8')
            state = rollback_drill_status(folder, revision='a' * 40)
            self.assertTrue(state['binding']['candidate_matches_current_build'])
            self.assertNotIn('DO-NOT-EXPOSE', json.dumps(state))
            self.assertNotIn('candidate_images', state)
            path.write_text('{}' * 9000, encoding='utf-8')
            self.assertFalse(rollback_drill_status(folder)['recorded'])

    def test_installer_preserves_previous_receipt_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'rollback-drill.json'; target.write_text('{"old":"receipt"}', encoding='utf-8')
            value = receipt(); value['password_hash'] = 'DO-NOT-EXPOSE'
            result = install_receipt(value, folder, revision='a' * 40)
            self.assertFalse(result['unchanged'])
            self.assertNotIn('DO-NOT-EXPOSE', target.read_text(encoding='utf-8'))
            self.assertEqual(len(list(Path(folder).glob('rollback-drill-history-*.json'))), 1)
            self.assertTrue(install_receipt(value, folder, revision='a' * 40)['unchanged'])
            self.assertEqual(len(list(Path(folder).glob('rollback-drill-history-*.json'))), 1)

    def test_install_rejects_wrong_build_without_touching_existing_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'rollback-drill.json'; target.write_text('previous', encoding='utf-8')
            with self.assertRaises(ValueError): install_receipt(receipt(), folder, revision='b' * 40)
            self.assertEqual(target.read_text(encoding='utf-8'), 'previous')

    def test_operator_publication_requires_exact_deployed_image_pair(self):
        value = receipt()
        running = {'images': value['rollback_images'], 'source_revision': value['candidate_revision'], 'schema_version': 7, 'contracts': {}}
        with patch('infra.releases.deployed_images', return_value=running['images']), patch('infra.releases.inspect_release', return_value=running), patch('infra.publish_rollback.subprocess.run') as run:
            with self.assertRaises(ValueError): publish(value)
            run.assert_not_called()
