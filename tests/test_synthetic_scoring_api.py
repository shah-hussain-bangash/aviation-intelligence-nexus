import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from auth_helpers import authenticated_client
from ml.evaluate_synthetic_holdout import evaluate_once
from ml.synthetic_model_bundle import export_bundle
from ml.synthetic_model_catalog import initialize,register,select
from services.api.auth import COOKIE
from services.api.main import create_app
from services.api.synthetic_scoring import SyntheticScoreRequest,SyntheticScoringService
from ml.verify_synthetic_evaluation import setup

CONTEXT='/api/v1/research/synthetic-scoring'
SCORE='/api/v1/research/synthetic-score'


class SyntheticScoringApiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        experiment=self.root/'experiment';setup(experiment);evaluate_once(experiment)
        receipt=hashlib.sha256((experiment/'holdout-evaluation.json').read_bytes()).hexdigest()
        bundle=self.root/'bundle.json';exported=export_bundle(experiment,bundle,receipt_sha256=receipt)
        self.model=exported['bundle_sha256'];self.features=experiment/'holdout-features.json'
        self.features_hash=hashlib.sha256(self.features.read_bytes()).hexdigest()
        self.catalog=self.root/'catalog';initialize(self.catalog)
        register(self.catalog,bundle,bundle_sha256=self.model)
        select(self.catalog,self.model,expected_revision=1,reason='PRIVATE-CATALOG-REASON')
        self.service=SyntheticScoringService(self.catalog,{'synthetic-fixture':(self.features,self.features_hash)})
        self.app=create_app(self.root/'api.sqlite3',synthetic_scoring=self.service)
        self.body={'dataset_id':'synthetic-fixture','expected_revision':2,'model_sha256':self.model,
                   'features_sha256':self.features_hash,'acknowledged':True}

    def tearDown(self):self.temp.cleanup()

    def test_admin_context_score_projection_and_catalog_preserved(self):
        before={p.relative_to(self.catalog):p.read_bytes() for p in self.catalog.rglob('*') if p.is_file()}
        with authenticated_client(self.app) as client:
            context=client.get(CONTEXT);self.assertEqual(context.status_code,200)
            self.assertEqual(context.json()['selected_model_sha256'],self.model)
            result=client.post(SCORE,json=self.body);self.assertEqual(result.status_code,200,result.text)
            self.assertEqual(result.json()['scores']['records'],8)
            self.assertEqual(result.json()['scores']['bundle_sha256'],self.model)
            self.assertNotIn('reason',result.json()['selection_event'])
            self.assertNotIn('PRIVATE-CATALOG-REASON',result.text)
            self.assertNotIn(str(self.root),context.text+result.text)
            self.assertFalse(result.json()['saved_to_history']);self.assertFalse(result.json()['production_ready'])
            self.assertEqual(result.headers['cache-control'],'no-store')
            self.assertIn('x-request-id',result.headers)
        self.assertEqual(before,{p.relative_to(self.catalog):p.read_bytes() for p in self.catalog.rglob('*') if p.is_file()})

    def test_anonymous_denied_before_service(self):
        with TestClient(self.app) as client,patch.object(self.service,'run') as run:
            self.assertEqual(client.get(CONTEXT).status_code,401)
            self.assertEqual(client.post(SCORE,json=self.body,headers={'Origin':'http://127.0.0.1:8080'}).status_code,401)
            run.assert_not_called()

    def test_researcher_allowed_viewer_denied(self):
        with authenticated_client(self.app) as client,patch.object(self.service,'run',wraps=self.service.run) as run:
            for role in ('researcher','viewer'):
                self.app.state.auth_store.create_user('fixture-'+role,'temporary-fixture-password',role)
                login=client.post('/api/v1/auth/login',json={'username':'fixture-'+role,'password':'temporary-fixture-password'})
                client.headers['X-CSRF-Token']=login.json()['csrf_token']
                expected=200 if role=='researcher' else 403
                self.assertEqual(client.get(CONTEXT).status_code,expected)
                self.assertEqual(client.post(SCORE,json=self.body).status_code,expected)
            self.assertEqual(run.call_count,1)

    def test_origin_csrf_query_and_extra_path_rejected_before_execution(self):
        with authenticated_client(self.app) as client,patch.object(self.service,'run') as run:
            self.assertEqual(client.post(SCORE,json=self.body,headers={'Origin':'https://unrelated.example'}).status_code,403)
            self.assertEqual(client.post(SCORE,json=self.body,headers={'X-CSRF-Token':'wrong'}).status_code,403)
            self.assertEqual(client.post(SCORE+'?path=private',json=self.body).status_code,422)
            self.assertEqual(client.get(CONTEXT+'?path=private').status_code,422)
            self.assertEqual(client.post(SCORE,json={**self.body,'file_path':'../../private'}).status_code,422)
            run.assert_not_called()

    def test_default_factory_does_not_enable_service(self):
        app=create_app(self.root/'disabled.sqlite3')
        with authenticated_client(app) as client:
            self.assertFalse(client.get(CONTEXT).json()['available'])
            result=client.post(SCORE,json=self.body)
            self.assertEqual(result.status_code,503)
            self.assertEqual(result.json()['error'],'synthetic_scoring_not_configured')

    def test_revoked_session_during_scoring_withholds_predictions(self):
        with authenticated_client(self.app) as client:
            original=self.service.run;token=client.cookies.get(COOKIE)
            def revoked(query):
                result=original(query);self.app.state.auth_store.logout(token);return result
            with patch.object(self.service,'run',side_effect=revoked):result=client.post(SCORE,json=self.body)
            self.assertEqual(result.status_code,403)
            self.assertEqual(result.json()['error'],'access_changed');self.assertNotIn('predictions',result.text)

    def test_unknown_dataset_wrong_pin_stale_revision_and_artifact_failure_are_generic(self):
        with authenticated_client(self.app) as client:
            for change in ({'dataset_id':'unknown'},{'features_sha256':'0'*64},{'expected_revision':1}):
                result=client.post(SCORE,json={**self.body,**change});self.assertEqual(result.status_code,503)
                self.assertEqual(result.json(),{'error':'synthetic_scoring_unavailable'})
            (self.catalog/'bundles'/(self.model+'.json')).write_bytes(b'PRIVATE-BROKEN')
            result=client.post(SCORE,json=self.body);self.assertEqual(result.status_code,503)
            self.assertNotIn('PRIVATE-BROKEN',result.text);self.assertNotIn(str(self.root),result.text)

    def test_strict_request_and_configuration(self):
        for change in ({'acknowledged':False},{'acknowledged':1},{'expected_revision':'2'},
                       {'expected_revision':True},{'dataset_id':'../private'},{'model_sha256':'x'},
                       {'features':[]},{'expected_revision':10001}):
            with self.assertRaises(ValueError):SyntheticScoreRequest.model_validate({**self.body,**change})
        with self.assertRaises(ValueError):SyntheticScoringService(self.catalog,{})


if __name__=='__main__':unittest.main()
