"""Exercise real HTTP failure semantics with local synthetic servers."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread
import unittest
from infra.load_check import PATHS, MAX_BODY, percentile, probe, run, summarize, validate


@contextmanager
def server(mode='valid'):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if mode == 'redirect':
                self.send_response(302)
                self.send_header('Location', 'https://example.invalid/')
                self.end_headers()
                return
            if mode == 'invalid':
                body = b'not json'
            elif mode == 'oversized':
                body = b'x' * (MAX_BODY + 1)
            elif self.path == '/':
                body = b'<title>AIN | Aviation Intelligence Nexus</title>'
            else:
                body = json.dumps({'backend_ready': True, 'production_ready': False,
                                   'authenticated': mode == 'authenticated', 'user': None}).encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    instance = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    try:
        yield instance.server_port
    finally:
        instance.shutdown()
        instance.server_close()
        thread.join()


class LoadCheckTests(unittest.TestCase):
    def test_real_http_batch_and_explicit_non_qualification(self):
        with server() as port:
            result = run(port, requests=4, workers=2, timeout=1)
        self.assertTrue(result['all_responses_valid'])
        self.assertFalse(result['performance_target_assessed'])
        self.assertFalse(result['production_ready'])
        self.assertEqual([row['path'] for row in result['endpoints']], list(PATHS))
        self.assertTrue(all(row['measurement']['requests'] == 4 for row in result['endpoints']))

    def test_fail_closed_and_stop_before_batch_on_wrong_server(self):
        with server('invalid') as port:
            result = run(port, requests=100, workers=4)
        self.assertFalse(result['all_responses_valid'])
        self.assertEqual(len(result['endpoints']), 1)
        self.assertIsNone(result['endpoints'][0]['measurement'])

    def test_redirects_are_not_followed_and_payload_is_bounded(self):
        for mode, error in [('redirect', 'unexpected_status'), ('oversized', 'oversized_response'),
                            ('invalid', 'invalid_json'), ('authenticated', 'unexpected_content')]:
            with self.subTest(mode=mode), server(mode) as port:
                sample = probe(port, '/api/v1/auth/session', 1)
                self.assertEqual(sample['error'], error)
                self.assertNotIn('body', sample)

    def test_limits_and_endpoint_allowlist(self):
        for args in [(0, 1, 1, 1), (8090, 101, 1, 1), (8090, 1, 5, 1),
                     (8090, 1, 1, float('nan')), (8090, 1, 1, 6)]:
            with self.assertRaises(ValueError):
                validate(*args)
        with self.assertRaises(ValueError):
            probe(8090, '/api/v1/predict', 1)

    def test_failed_requests_count_in_latencies_and_throughput(self):
        rows = [{'milliseconds': 1, 'status': 200, 'error': None},
                {'milliseconds': 100, 'status': None, 'error': 'transport_error'}]
        result = summarize(rows, 2)
        self.assertEqual(result['latency_ms']['p95'], 100)
        self.assertEqual(result['failures'], 1)
        self.assertEqual(result['completed_requests_per_second'], 1)
        self.assertEqual(result['status_counts'], {'200': 1, 'no_response': 1})
        self.assertEqual(percentile([1, 2, 3, 4], .5), 2)
