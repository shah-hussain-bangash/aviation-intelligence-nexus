"""Structural fixtures never constitute genuine human semantic judgments."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from rag import semantic_review as sr


class SemanticReviewTests(unittest.TestCase):
    def setUp(self):
        self.report = json.loads((sr.ROOT / 'docs/reports/Generation_Diagnostics.json').read_text(encoding='utf-8'))
        # Test portability only: Windows checkout bytes differ from Linux LF bytes.
        # Production export never rewrites historical hashes to admit a stale corpus.
        self.report['sources'] = [{'path': p, 'sha256': hashlib.sha256((sr.ROOT / p).read_bytes()).hexdigest()} for p in sr.SOURCES]
        self.packet = sr.build_packet(self.report, 'a' * 64)
        self.pin = sr.digest(sr.canonical(self.packet))
        self.annotations = sr.template(self.packet, self.pin)

    def assess(self, annotations=None, packet=None):
        return sr.assess(packet or self.packet, self.pin, annotations or self.annotations)

    def test_initial_packet_preserves_failures_and_never_auto_rates(self):
        result = self.assess()
        self.assertEqual(result['counts'], {'pending': 22, 'not_evaluable': 2,
                                           'declared_acceptable': 0, 'declared_needs_revision': 0})
        self.assertFalse(result['all_evaluable_cases_assessed'])
        for field in ('human_identity_verified', 'independent_review', 'semantic_benchmark_accuracy_measured',
                      'operational_approval', 'production_ready'):
            self.assertIs(result[field], False)
        self.assertIn('April', self.packet['report']['cases'][0]['claims'][0]['text'])
        self.assertIn('February', self.packet['report']['cases'][0]['claims'][0]['quote'])
        self.assertEqual(self.packet['report'], self.report)

    def test_explicit_negative_rating_and_source_gate(self):
        row = self.annotations['cases'][0]
        self.annotations['reviewer_label'] = 'SYNTHETIC TEST REVIEWER'
        row['question_answered'] = 'no'
        for claim in row['claims']:
            claim.update(supported='no', relevant='no')
        self.assertEqual(self.assess()['counts']['pending'], 22)
        row['source_checked'] = True
        result = self.assess()
        self.assertEqual(result['counts']['declared_needs_revision'], 1)
        self.assertEqual(result['counts']['pending'], 21)

    def test_all_declared_assessments_keep_unavailable_separate(self):
        self.annotations['reviewer_label'] = 'SYNTHETIC TEST REVIEWER'
        for row in self.annotations['cases']:
            row['source_checked'] = True
            for key in ('question_answered', 'abstention_appropriate'):
                if row[key] == 'uncertain':
                    row[key] = 'yes'
            for claim in row['claims']:
                claim.update(supported='yes', relevant='yes')
        result = self.assess()
        self.assertTrue(result['all_evaluable_cases_assessed'])
        self.assertEqual(result['counts']['declared_acceptable'], 22)
        self.assertEqual(result['counts']['not_evaluable'], 2)
        self.assertFalse(result['semantic_benchmark_accuracy_measured'])
        self.assertFalse(result['independent_review'])

    def test_annotation_binding_rejects_changed_missing_or_extra_fields(self):
        mutations = [lambda a: a.update(packet_sha256='b' * 64),
                     lambda a: a['cases'].pop(),
                     lambda a: a['cases'][0].update(id='different'),
                     lambda a: a['cases'][0].update(case_sha256='b' * 64),
                     lambda a: a['cases'][0]['claims'].pop(),
                     lambda a: a['cases'][0]['claims'][0].update(citation='other'),
                     lambda a: a['cases'][0]['claims'][0].update(claim_index=True),
                     lambda a: a['cases'][0]['claims'][0].update(supported='correct'),
                     lambda a: a['cases'][0].update(source_checked=1),
                     lambda a: a['cases'][0].update(notes='x' * 2001),
                     lambda a: a.update(reviewer_label='x' * 81),
                     lambda a: a.update(independent_review=True),
                     lambda a: a['cases'][1].update(abstention_appropriate='yes')]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                annotations = deepcopy(self.annotations)
                mutate(annotations)
                with self.assertRaises(ValueError):
                    self.assess(annotations)

    def test_packet_evidence_and_recorded_sources_cannot_drift(self):
        mutations = [lambda p: p['reviews'][0]['evidence'][0].update(text='changed'),
                     lambda p: p['documents'][0].update(text='changed'),
                     lambda p: p['report']['sources'][0].update(sha256='b' * 64),
                     lambda p: p['report']['cases'][0]['claims'][0].update(quote='invented'),
                     lambda p: p['report']['cases'][0]['retrieved'][0].update(start_line=999),
                     lambda p: p['report']['cases'][0].update(outcome='abstained'),
                     lambda p: p['report']['metrics'].update(total_cases=25),
                     lambda p: p['report'].update(suite_sha256='b' * 64)]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                packet = deepcopy(self.packet)
                mutate(packet)
                with self.assertRaises(ValueError):
                    self.assess(packet=packet)

    def test_strict_input_pins_duplicates_and_nonfinite_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'input.json'
            for raw in ('{"x":1,"x":2}', '{"x":NaN}'):
                path.write_text(raw)
                with self.assertRaises((ValueError, RuntimeError)):
                    sr.read_json(path)
            path.write_text('{}')
            with self.assertRaises(ValueError):
                sr.read_json(path, '0' * 64)
            self.assertEqual(sr.read_json(path, sr.digest(path.read_bytes()))[0], {})

    def test_new_private_exports_assessment_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(sr, 'ROOT', Path(directory)):
            # Validation corpus remains the real repository; only output location changes.
            with patch.object(sr, 'build_packet', return_value=self.packet):
                source = Path(directory) / 'report.json'
                source.write_bytes(sr.canonical(self.report))
                info = sr.export(source, sr.digest(source.read_bytes()))
                packet, pin = sr.read_json(info['packet'], info['packet_sha256'])
                annotations, _ = sr.read_json(info['annotations'])
                self.assertEqual(sr.assess(packet, pin, annotations)['counts']['pending'], 22)
                self.assertTrue((Path(info['packet']).parent / 'READ_ME.txt').is_file())
                with self.assertRaises(ValueError):
                    sr.write_new(info['packet'], {})
            for outside in (Path(directory) / 'public.json', Path(directory) / '.local/../public.json'):
                with self.assertRaises(ValueError):
                    sr.write_new(outside, {})

    def test_redirected_output_refused(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(sr, 'ROOT', Path(directory)):
            local = Path(directory) / '.local'
            target = Path(directory) / 'target'
            target.mkdir()
            local.mkdir()
            link = local / 'redirect'
            try:
                link.symlink_to(target, target_is_directory=True)
            except OSError:
                self.skipTest('OS does not allow test symlink creation')
            with self.assertRaises(ValueError):
                sr.write_new(link / 'out.json', {})


if __name__ == '__main__':
    unittest.main()
