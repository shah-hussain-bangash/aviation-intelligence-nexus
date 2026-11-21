from contextlib import closing
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4
from fastapi.testclient import TestClient
from ml.input_distributions import compare,aggregate,evaluate,PROTOCOL
from services.api.distributions import load_distributions,validate_report,REPORT
from services.api.diagnostics import REPORT as MODEL_REPORT
from services.api.main import initialize,create_app
from services.api.paths import ROOT


class DistributionTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.root=Path(self.folder.name);self.db=self.root/'state.sqlite3';initialize(self.db)
        with closing(sqlite3.connect(self.db)) as db,db:
            for date,cancelled,arrival in [('2025-01-05',0,10),('2025-05-05',0,20),('2025-01-06',1,5),('2025-01-07',0,None)]:
                db.execute('INSERT INTO flights(source,source_record_id,flight_date,carrier,origin,destination,flight_number,scheduled_departure,cancelled,diverted,arrival_delay_minutes) VALUES(?,?,?,?,?,?,?,?,?,?,?)',('BTS_REPORTING_CARRIER',str(uuid4()),date,'AA','JFK','LAX','1','2400',cancelled,0,arrival))

    def tearDown(self):self.folder.cleanup()

    def test_distances_have_known_endpoints_symmetry_and_unseen_mass(self):
        self.assertEqual(compare({'A':3},{'A':100})['total_variation'],0)
        separated=compare({'A':10},{'B':8});self.assertEqual(separated['total_variation'],1);self.assertEqual(separated['jensen_shannon_divergence_bits'],1);self.assertEqual(separated['comparison_mass_unseen_in_reference'],1)
        left,right={'A':3,'B':1},{'A':1,'C':3};a,b=compare(left,right),compare(right,left)
        self.assertAlmostEqual(a['total_variation'],.75);self.assertAlmostEqual(a['jensen_shannon_divergence_bits'],b['jensen_shannon_divergence_bits']);self.assertAlmostEqual(a['comparison_mass_unseen_in_reference'],.75)
        for first,second in [({},right),({'A':True},right),({'A':-1},right)]:
            with self.assertRaises(ValueError):compare(first,second)

    def test_aggregation_matches_eligibility_midnight_and_iso_weekday_without_mutating_rows(self):
        before=hashlib.sha256(self.db.read_bytes()).hexdigest()
        with closing(sqlite3.connect(self.db)) as db:
            train=aggregate(db,'2025-01-01','2025-04-01');test=aggregate(db,'2025-05-01','2025-06-01')
        self.assertEqual(train['weekday'],{'7':1});self.assertEqual(test['weekday'],{'1':1});self.assertEqual(train['departure_hour'],{'00':1});self.assertEqual(train['carrier'],{'AA':1})
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(),before)

    def test_invalid_time_categories_fail_and_no_empty_cohort_is_silently_compared(self):
        with closing(sqlite3.connect(self.db)) as db,db:
            db.execute("UPDATE flights SET scheduled_departure='2560'")
            with self.assertRaises(ValueError):aggregate(db,'2025-01-01','2025-04-01')
            with self.assertRaises(ValueError):aggregate(db,'2026-01-01','2026-04-01')

    def fixture_evaluation(self,expected=1,deadline=False):
        (self.root/MODEL_REPORT).parent.mkdir(parents=True);(self.root/MODEL_REPORT).write_text(json.dumps({'training_records':expected,'test':{'model':{'records':1}}}),encoding='utf-8')
        with patch('ml.input_distributions.ROOT',self.root),patch('ml.input_distributions.load_diagnostics'):
            if deadline:
                with patch('ml.input_distributions.time.monotonic',side_effect=[0,121,121,121]):return evaluate(self.db,self.root/'.local/experiment')
            return evaluate(self.db,self.root/'.local/experiment')

    def test_evaluation_writes_only_a_new_report_and_requires_frozen_counts(self):
        report=self.fixture_evaluation();self.assertTrue(report['cohort_counts_match_frozen']);self.assertFalse(report['csv_identity_verified']);self.assertEqual(report['reference_records'],1)
        self.assertTrue((self.root/'.local/experiment/report.json').is_file())
        with self.assertRaises(ValueError):evaluate(self.db,self.root/'.local/experiment')

    def test_count_mismatch_and_deadline_never_publish_a_report(self):
        with self.assertRaises(ValueError):self.fixture_evaluation(expected=2)
        self.assertFalse((self.root/'.local/experiment/report.json').exists())
        with tempfile.TemporaryDirectory() as folder:
            original=self.root;self.root=Path(folder)
            try:
                with self.assertRaises((TimeoutError,sqlite3.OperationalError)):self.fixture_evaluation(deadline=True)
                self.assertFalse((self.root/'.local/experiment/report.json').exists())
            finally:self.root=original

    def test_recorded_counts_metrics_scope_and_file_integrity_are_rechecked(self):
        report=load_distributions();self.assertEqual(report['reference_records'],1611046);self.assertEqual(report['comparison_records'],597574)
        for mutation in [lambda r:r.__setitem__('csv_identity_verified',True),lambda r:r.__setitem__('alert_threshold',.1),lambda r:r['features']['carrier'].__setitem__('total_variation',1),lambda r:r['features']['weekday']['categories'][0].__setitem__('reference_share',0)]:
            changed=copy.deepcopy(report);mutation(changed)
            with self.assertRaises(ValueError):validate_report(changed)
        (self.root/REPORT).parent.mkdir(parents=True);(self.root/REPORT).write_text((ROOT/REPORT).read_text(encoding='utf-8')+' ',encoding='utf-8')
        with self.assertRaises(ValueError):load_distributions(self.root)

    def test_authenticated_viewer_read_and_sanitized_integrity_outage(self):
        app=create_app(self.db)
        with TestClient(app) as client:
            path='/api/v1/research/input-distributions';self.assertEqual(client.get(path).status_code,401)
            app.state.auth_store.create_user('fixture-admin','temporary-distribution-password','admin');app.state.auth_store.create_user('fixture-viewer','temporary-distribution-password','viewer')
            client.post('/api/v1/auth/login',json={'username':'fixture-viewer','password':'temporary-distribution-password'},headers={'Origin':'http://127.0.0.1:8080'})
            self.assertTrue(client.get(path).json()['integrity_verified'])
            with patch('services.api.main.load_distributions',side_effect=ValueError('private-path')):
                response=client.get(path);self.assertEqual(response.status_code,503);self.assertNotIn('private-path',response.text)
