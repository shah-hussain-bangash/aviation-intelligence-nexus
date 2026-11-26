import base64
import hashlib
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from rag import review_page as page
from rag import semantic_review as sr


class ReviewPageTests(unittest.TestCase):
    def packet(self):
        report = json.loads((sr.ROOT / 'docs/reports/Generation_Diagnostics.json').read_text(encoding='utf-8'))
        report['sources'] = [{'path': p, 'sha256': hashlib.sha256((sr.ROOT / p).read_bytes()).hexdigest()} for p in sr.SOURCES]
        return sr.build_packet(report, 'a' * 64)

    def resume_fixture(self, folder):
        packet = self.packet()
        source = Path(folder) / 'packet.json'
        source.write_text(json.dumps(packet), encoding='utf-8')
        pin = hashlib.sha256(source.read_bytes()).hexdigest()
        annotations = sr.template(packet, pin)
        annotations['reviewer_label'] = 'SYNTHETIC RESUME TEST'
        row = annotations['cases'][0]
        row.update(source_checked=True, question_answered='no', notes='Literal <review> note')
        row['claims'][0].update(supported='no', relevant='no')
        review = Path(folder) / 'annotations.json'
        review.write_text(json.dumps(annotations), encoding='utf-8')
        return source, pin, review, annotations

    def test_resume_preserves_decisions_notes_pins_and_inputs(self):
        with tempfile.TemporaryDirectory() as folder:
            source, pin, review, annotations = self.resume_fixture(folder)
            originals = [p.read_bytes() for p in (source, review)]
            target = Path(folder) / 'resumed.html'
            review_hash = hashlib.sha256(review.read_bytes()).hexdigest()
            with patch.object(page, 'new_output', return_value=target):
                result = page.render(source, pin, target, annotations_path=review, annotations_sha256=review_hash)
            data = json.loads(re.search(r'const data = (.*?);\nmountGenerationReview', target.read_text(encoding='utf-8'), re.S).group(1))
            self.assertEqual(data['seed'], annotations)
            self.assertEqual(data['seed_hash'], review_hash)
            self.assertEqual(data['initial']['reviewer_label'], '')
            self.assertEqual(sr.assess(data['packet'], pin, data['seed'])['counts']['declared_needs_revision'], 1)
            self.assertTrue(result['review_declarations_loaded'])
            self.assertIsNone(result['human_ratings_supplied'])
            self.assertEqual(originals, [p.read_bytes() for p in (source, review)])

    def test_resume_refuses_wrong_file_pin_other_packet_and_missing_pair_before_output(self):
        with tempfile.TemporaryDirectory() as folder:
            source, pin, review, annotations = self.resume_fixture(folder)
            target = Path(folder) / 'out.html'
            for kwargs in ({'annotations_path': review}, {'annotations_sha256': 'a' * 64},
                           {'annotations_path': review, 'annotations_sha256': '0' * 64}):
                with patch.object(page, 'new_output') as output, self.assertRaises(ValueError):
                    page.render(source, pin, target, **kwargs)
                output.assert_not_called()
            annotations['packet_sha256'] = 'b' * 64
            review.write_text(json.dumps(annotations))
            with patch.object(page, 'new_output') as output, self.assertRaises(ValueError):
                page.render(source, pin, target, annotations_path=review,
                            annotations_sha256=hashlib.sha256(review.read_bytes()).hexdigest())
            output.assert_not_called()

    def test_resume_keeps_original_template_and_review_files_as_new_output_only(self):
        with tempfile.TemporaryDirectory() as folder:
            source, pin, review, _ = self.resume_fixture(folder)
            def private_output(path):
                with patch.object(sr, 'ROOT', Path(folder)):
                    return sr.new_output(path)
            with patch.object(page, 'new_output', side_effect=private_output):
                target = Path(folder) / '.local/resumed.html'
                args = {'annotations_path': review, 'annotations_sha256': hashlib.sha256(review.read_bytes()).hexdigest()}
                page.render(source, pin, target, **args)
                before = target.read_bytes()
                with self.assertRaises(ValueError):
                    page.render(source, pin, target, **args)
                self.assertEqual(before, target.read_bytes())

    def test_standalone_page_hashes_scripts_and_styles_and_keeps_original_packet(self):
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder) / 'packet.json', Path(folder) / 'review.html'
            source.write_text(json.dumps(self.packet()), encoding='utf-8')
            pin = hashlib.sha256(source.read_bytes()).hexdigest()
            original = source.read_bytes()
            # Only redirect the output in this fixture; production output remains .local-only.
            with patch.object(page, 'new_output', return_value=target):
                result = page.render(source, pin, target)
            html = target.read_text(encoding='utf-8')
            for kind in ('script', 'style'):
                content = re.search(f'<{kind}>(.*?)</{kind}>', html, re.S).group(1)
                digest = base64.b64encode(hashlib.sha256(content.encode()).digest()).decode()
                self.assertIn(f"{kind}-src 'sha256-{digest}'", html)
            self.assertIn("connect-src 'none'", html)
            self.assertNotIn('export function ', html)
            self.assertEqual(html.count('<script>'), 1)
            self.assertNotIn('<script src=', html)
            self.assertFalse(result['human_ratings_supplied'])
            self.assertEqual(original, source.read_bytes())
            self.assertEqual(result['packet_sha256'], pin)

    def test_pinned_packet_and_source_drift_checked_before_output(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'packet.json'
            packet = self.packet(); packet['documents'][0]['text'] = 'changed'
            source.write_text(json.dumps(packet))
            for pin in ('0' * 64, hashlib.sha256(source.read_bytes()).hexdigest()):
                with patch.object(page, 'new_output') as output, self.assertRaises(ValueError):
                    page.render(source, pin, Path(folder) / 'out.html')
                output.assert_not_called()

    def test_embedded_text_cannot_close_the_script_element(self):
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder) / 'packet.json', Path(folder) / 'review.html'
            packet = self.packet()
            packet['report']['cases'][0]['claims'][0]['text'] = '</script><img src=x onerror=alert(1)>'
            # Rebind a structurally valid claim without pretending it is semantically correct.
            packet = sr.build_packet(packet['report'], 'a' * 64)
            source.write_text(json.dumps(packet), encoding='utf-8')
            with patch.object(page, 'new_output', return_value=target):
                page.render(source, hashlib.sha256(source.read_bytes()).hexdigest(), target)
            html = target.read_text(encoding='utf-8')
            self.assertEqual(html.count('</script>'), 1)
            self.assertIn('\\u003c/script>', html)
            self.assertNotIn('<img src=x', html)


if __name__ == '__main__':
    unittest.main()
