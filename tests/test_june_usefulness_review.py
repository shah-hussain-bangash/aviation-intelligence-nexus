import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from agents.june_usefulness_review import assess, blank, prepare, validate, ROOT
from agents.verify_june_http import verify
from rag.semantic_review import canonical
from tests.test_june_http_rehearsal import ports


class JuneUsefulnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(dir=ROOT / '.local')
        cls.base = Path(cls.folder.name)
        web, api = ports()
        cls.receipt = verify(cls.base / 'fixture', web_port=web, api_port=api)
        if not cls.receipt['passed']: raise AssertionError(cls.receipt)
        # Synthetic provider metadata exercises validation only; never native execution evidence.
        cls.receipt['provider_mode'] = 'live_ollama'
        cls.receipt['checks']['actual_provider_completed_within_bounds'] = True
        cls.receipt['provider_calls'] = [{'route': 'chat', 'purpose': p, 'state': 'returned',
            'done': True, 'done_reason': 'stop'} for p in ('planner', 'generator')]
        cls.source = cls.base / 'synthetic-receipt.json'
        cls.source.write_bytes(canonical(cls.receipt))
        cls.source_hash = hashlib.sha256(cls.source.read_bytes()).hexdigest()

    @classmethod
    def tearDownClass(cls): cls.folder.cleanup()

    def packet(self):
        packet = {'format': 'ain-june-usefulness-packet-v1', 'receipt_sha256': self.source_hash,
                  'receipt': copy.deepcopy(self.receipt)}
        pin = hashlib.sha256(canonical(packet)).hexdigest()
        return packet, pin

    def test_export_blank_and_source_preserved(self):
        result = prepare(self.source, self.source_hash, self.base / 'review')
        packet = json.loads((self.base / 'review/packet.json').read_bytes())
        value = json.loads((self.base / 'review/annotations.json').read_bytes())
        self.assertEqual(assess(packet, result['packet_sha256'], value)['status'], 'pending')
        self.assertEqual(value['question_answered'], '')
        self.assertFalse(result['human_ratings_supplied'])
        self.assertIn(self.receipt['run']['claims'][0]['text'], (self.base / 'review/review.txt').read_text(encoding='utf-8'))
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), self.source_hash)
        with self.assertRaises(ValueError): prepare(self.source, self.source_hash, self.base / 'review')

    def test_changed_or_fixture_execution_refused(self):
        for change in ('fixture', 'checks', 'evidence', 'finding', 'provider', 'reviewed'):
            receipt = copy.deepcopy(self.receipt)
            if change == 'fixture': receipt['provider_mode'] = 'deterministic_fixture'
            if change == 'checks': receipt['checks'].pop('csrf_enforced')
            if change == 'evidence': receipt['run']['steps'][0]['observation']['evidence_text'] += 'changed'
            if change == 'finding': receipt['run']['claims'][0]['text'] += 'changed'
            if change == 'provider': receipt['provider_calls'][0]['done_reason'] = 'length'
            if change == 'reviewed': receipt['run']['reviews'] = [{}]
            with self.subTest(change=change), self.assertRaises(ValueError): validate(receipt)

    def test_exact_binding_and_strict_fields(self):
        packet, pin = self.packet(); value = blank(packet, pin)
        for changed in ({**value, 'packet_sha256': '0' * 64}, {**value, 'extra': True},
                        {**value, 'source_checked': 1}, {**value, 'claims': []}):
            with self.assertRaises(ValueError): assess(packet, pin, changed)
        value['claims'][0]['claim_sha256'] = '0' * 64
        with self.assertRaises(ValueError): assess(packet, pin, value)
        with self.assertRaises(ValueError): assess(packet, '0' * 64, blank(packet, pin))

    def test_unsigned_negative_uncertain_and_acknowledgements(self):
        packet, pin = self.packet(); value = blank(packet, pin)
        value.update(reviewer_label='SYNTHETIC TEST', question_answered='yes', source_checked=True, own_assessment=True)
        for row in value['claims']: row.update(supported='yes', relevant='yes')
        result = assess(packet, pin, value)
        self.assertEqual(result['status'], 'declared_acceptable')
        self.assertFalse(result['human_identity_verified']); self.assertFalse(result['production_ready'])
        value['claims'][0]['supported'] = 'no'
        self.assertEqual(assess(packet, pin, value)['status'], 'declared_needs_revision')
        value['claims'][0]['supported'] = 'uncertain'
        self.assertEqual(assess(packet, pin, value)['status'], 'pending')
        value['claims'][0]['supported'] = 'yes'; value['own_assessment'] = False
        self.assertEqual(assess(packet, pin, value)['status'], 'pending')

    def test_wrong_source_hash_has_no_output(self):
        target = self.base / 'wrong-hash'
        with self.assertRaises(ValueError): prepare(self.source, '0' * 64, target)
        self.assertFalse(target.exists())
