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
