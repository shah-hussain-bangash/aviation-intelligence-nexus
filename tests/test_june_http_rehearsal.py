import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from agents.verify_june_http import verify, ROOT


def ports():
    with socket.socket() as a,socket.socket() as b:
        a.bind(('127.0.0.1',0));b.bind(('127.0.0.1',0))
        return a.getsockname()[1],b.getsockname()[1]


class JuneHTTPRehearsalTests(unittest.TestCase):
    def setUp(self):
        (ROOT/'.local').mkdir(exist_ok=True)
        self.folder=tempfile.TemporaryDirectory(dir=ROOT/'.local');self.base=Path(self.folder.name)

    def tearDown(self):self.folder.cleanup()

    def test_real_gateway_api_worker_and_sessions_with_fixture_provider(self):
        web,api=ports();r=verify(self.base/'fresh',web_port=web,api_port=api)
        self.assertTrue(r['passed'],r)
        self.assertTrue(all(r['checks'].values()))
        self.assertEqual(r['provider_mode'],'deterministic_fixture');self.assertEqual(r['provider_calls'],[])
        self.assertEqual(r['run']['actor'],'june-http-owner');self.assertEqual(r['run']['reviews'],[])
        self.assertEqual(r['run']['state'],'awaiting_review')
        self.assertNotIn('csrf_token',json.dumps(r));self.assertNotIn('password_hash',json.dumps(r))
        self.assertTrue((self.base/'fresh/evaluation.json').exists())
        for port in (web,api):
            with socket.socket() as probe:self.assertNotEqual(probe.connect_ex(('127.0.0.1',port)),0)

    def test_invalid_existing_and_occupied_ports_are_preserved_before_state(self):
        web,api=ports()
        for output,kwargs in [(self.base,{}),(ROOT/'not-private',{}),(self.base/'..'/'escape',{}),(self.base/'bad',{'live_ai':'yes'}),(self.base/'same',{'web_port':api,'api_port':api})]:
            with self.assertRaises(ValueError):verify(output,**kwargs)
        with socket.socket() as occupied:
            occupied.bind(('127.0.0.1',web));occupied.listen()
            with self.assertRaises(ValueError):verify(self.base/'blocked',web_port=web,api_port=api)
            self.assertFalse((self.base/'blocked').exists())
            self.assertEqual(occupied.getsockname()[1],web)

    def test_explicit_june_sharing_withdrawal_through_gateway_and_fresh_session(self):
        web,api=ports();r=verify(self.base/'sharing',peer_withdrawal=True,web_port=web,api_port=api)
        self.assertTrue(r['passed'],r)
        self.assertEqual(r['format'],'ain-june-sharing-http-v1')
        self.assertEqual(r['provider_mode'],'deterministic_fixture');self.assertEqual(r['provider_calls'],[])
        self.assertEqual(r['run']['state'],'awaiting_review')
        self.assertEqual(r['withdrawn_run']['state'],'withdrawn')
        self.assertEqual(r['withdrawn_run']['reviews'],[])
        self.assertTrue(r['checks']['peer_access_ends_after_withdrawal'])
        self.assertTrue(r['checks']['withdrawal_survives_fresh_session'])
        self.assertIn('agents/store.py',r['execution_source_sha256'])
        from agents.june_usefulness_review import validate
        with self.assertRaises(ValueError):validate(r)
        self.assertNotIn('csrf_token',json.dumps(r));self.assertNotIn('password_hash',json.dumps(r))
        for port in (web,api):
            with socket.socket() as probe:self.assertNotEqual(probe.connect_ex(('127.0.0.1',port)),0)

    def test_nonboolean_sharing_mode_is_refused_without_state(self):
        target=self.base/'invalid-sharing'
        with self.assertRaises(ValueError):verify(target,peer_withdrawal='yes')
        self.assertFalse(target.exists())

    def test_changed_evidence_never_starts_state_or_service(self):
        with patch('agents.verify_june_http.load_june_evaluation',side_effect=ValueError('changed evidence')):
            with self.assertRaises(ValueError):verify(self.base/'changed')
        self.assertFalse((self.base/'changed').exists())

    def test_failed_worker_result_retains_receipt_and_stops_only_isolated_services(self):
        web,api=ports()
        with patch('agents.tools.june_observation',side_effect=ValueError('private fixture details')):
            r=verify(self.base/'failed',web_port=web,api_port=api)
        self.assertFalse(r['passed']);self.assertFalse(r['checks']['owned_completed_draft'])
        self.assertTrue(r['checks']['isolated_services_stopped']);self.assertTrue((self.base/'failed/evaluation.json').exists())
        self.assertEqual(r['run']['state'],'failed');self.assertNotIn('private fixture details',json.dumps(r))
