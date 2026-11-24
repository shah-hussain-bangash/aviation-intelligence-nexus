from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import UUID
from fastapi.testclient import TestClient
from services.api.main import create_app


class RequestContextTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.app=create_app(self.root/'ain.sqlite3')
    def tearDown(self):self.temp.cleanup()
    def request_id(self,response):
        value=response.headers['x-request-id'];self.assertEqual(UUID(value).version,4)
        self.assertEqual(response.headers['cache-control'],'no-store');return value
    def login(self,client):
        password='synthetic-context-fixture-123';self.app.state.auth_store.create_user('context-admin',password,'admin')
        self.assertEqual(client.post('/api/v1/auth/login',json={'username':'context-admin','password':password},headers={'Origin':'http://127.0.0.1:8080'}).status_code,200)

    def test_success_identity_origin_and_validation_errors_have_request_ids(self):
        with TestClient(self.app) as client:
            cases=[client.get('/api/v1/auth/session'),client.get('/api/v1/research/summary'),client.post('/api/v1/auth/login',json={}),client.post('/api/v1/auth/login',json={},headers={'Origin':'http://127.0.0.1:8080'})]
            self.assertEqual([r.status_code for r in cases],[200,401,403,422])
            self.assertEqual(len({self.request_id(r) for r in cases}),4)

    def test_caller_ids_are_ignored_and_parallel_requests_remain_distinct(self):
        supplied='11111111-1111-4111-8111-111111111111'
        with TestClient(self.app) as client:
            with ThreadPoolExecutor(max_workers=4) as pool:
                responses=list(pool.map(lambda _:client.get('/api/v1/auth/session',headers={'X-Request-ID':supplied}),range(8)))
            ids={self.request_id(r) for r in responses}
            self.assertEqual(len(ids),8);self.assertNotIn(supplied,ids)

    def test_unhandled_error_is_sanitized_and_correlated_without_sensitive_log_values(self):
        secret='PRIVATE-QUESTION-PASSWORD-COOKIE'
        @self.app.get('/api/v1/context-error')
        def fail():raise RuntimeError(secret)
        with TestClient(self.app) as client:
            self.login(client)
            with self.assertLogs('ain.requests',level='INFO') as logs:
                response=client.get('/api/v1/context-error?question='+secret,headers={'X-Private':secret})
            self.assertEqual(response.status_code,500);rid=self.request_id(response)
            self.assertEqual(response.json(),{'error':'internal_error','request_id':rid})
            event=json.loads(logs.records[-1].getMessage())
            self.assertEqual(event['request_id'],rid);self.assertEqual(event['outcome'],'unhandled_exception')
            self.assertEqual(event['route'],'/api/v1/context-error')
            self.assertEqual(set(event),{'event','timestamp','request_id','method','route','status','response_prepare_ms','outcome'})
            self.assertEqual(event['event'],'api_response_prepared')
            self.assertNotIn(secret,response.text+str(logs.output));self.assertNotIn('Traceback',response.text+str(logs.output))

    def test_route_parameters_are_not_logged_and_telemetry_failure_does_not_break_requests(self):
        @self.app.get('/api/v1/context-items/{item}')
        def item(item:str):return {'ok':True}
        with TestClient(self.app) as client:
            self.login(client)
            with self.assertLogs('ain.requests',level='INFO') as logs:
                response=client.get('/api/v1/context-items/PRIVATE-IDENTIFIER')
            self.assertEqual(response.status_code,200)
            self.assertEqual(json.loads(logs.records[-1].getMessage())['route'],'/api/v1/context-items/{item}')
            self.assertNotIn('PRIVATE-IDENTIFIER',str(logs.output))
            with patch('services.api.request_context.LOGGER.info',side_effect=OSError('sink unavailable')):
                self.assertEqual(client.get('/api/v1/auth/session').status_code,200)

    def test_early_denial_logs_no_raw_path_or_query(self):
        with TestClient(self.app) as client:
            with self.assertLogs('ain.requests',level='INFO') as logs:
                response=client.get('/api/v1/PRIVATE-PATH?token=PRIVATE-TOKEN')
            self.assertEqual(response.status_code,401);self.request_id(response)
            self.assertEqual(json.loads(logs.records[-1].getMessage())['route'],'unresolved_api_route')
            self.assertNotIn('PRIVATE-',str(logs.output))
