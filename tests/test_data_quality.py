from contextlib import closing
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from services.api.main import initialize,create_app
from services.api.paths import ROOT
from services.api.data_quality import load_quality,validate_report,REPORT,DATASET
from pipelines.audit_quality import audit,run,PERIODS,SOURCE,SQL
from pipelines.import_bts import normalize,source_url


class DataQualityTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.root=Path(self.folder.name);self.db=self.root/'state.sqlite3';initialize(self.db)
        with closing(sqlite3.connect(self.db)) as c,c:
            for month in range(1,6):
                rows=[(0,0,'10')]+([(1,1,''),(0,1,''),(0,0,'')] if month==1 else [])
                for index,(cancelled,diverted,arrival) in enumerate(rows,1):
                    raw={'FlightDate':f'2025-{month:02}-15','Reporting_Airline':'AA','Origin':'JFK','Dest':'LAX',
                        'Flight_Number_Reporting_Airline':str(index),'CRSDepTime':'2400','Cancelled':str(cancelled),'Diverted':str(diverted),'DepDelay':'','ArrDelay':arrival}
                    values=normalize(raw,f'2025-{month:02}')
                    c.execute('INSERT INTO flights(source,source_record_id,flight_date,carrier,origin,destination,departure_delay_minutes,arrival_delay_minutes,flight_number,scheduled_departure,cancelled,diverted) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',values)
                c.execute('INSERT INTO imports(sha256,source_url,period,rows_read,rows_inserted,duplicate_rows) VALUES(?,?,?,?,?,0)',(hashlib.sha256(str(month).encode()).hexdigest(),source_url(2025,month),f'2025-{month:02}',len(rows),len(rows)))
            c.execute("INSERT INTO flights(source,source_record_id,flight_date,carrier,origin,destination) VALUES('synthetic','fixture','2025-01-15','ZZ','AAA','BBB')")

    def tearDown(self):self.folder.cleanup()

    def test_readonly_counts_cohorts_midnight_and_metadata_reconcile(self):
        before=hashlib.sha256(self.db.read_bytes()).hexdigest();report=audit(self.db)
        self.assertTrue(report['checks_passed']);self.assertEqual(report['source_records'],8);self.assertEqual(report['other_source_records'],1)
        self.assertEqual(report['months'][0]['cohorts'],{'eligible_arrivals':1,'excluded_cancelled':1,'excluded_diverted':1,'excluded_missing_or_invalid':1})
        self.assertEqual(report['field_issue_occurrences'],0);self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(),before)
        self.assertIs(validate_report(report),report)

    def test_invalid_fields_and_outside_period_are_visible_without_raw_values(self):
        with closing(sqlite3.connect(self.db)) as c,c:
            c.execute('INSERT INTO flights(source,source_record_id,flight_date,carrier,origin,destination,flight_number,scheduled_departure,cancelled,diverted,arrival_delay_minutes) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(SOURCE,'PRIVATE_RECORD','2025-02-30','aa','J1K','LA','0','2460',-1,0,float('inf')))
            c.execute('INSERT INTO flights(source,source_record_id,flight_date,carrier,origin,destination) VALUES(?,?,?,?,?,?)',(SOURCE,'OUTSIDE_RECORD','2025-06-01','AA','JFK','LAX'))
        r=audit(self.db);self.assertFalse(r['checks_passed']);self.assertEqual(r['unprofiled_source_records'],1);self.assertEqual(r['invalid_dates_all_source'],1)
        self.assertGreater(r['field_issue_occurrences'],1);self.assertEqual(r['months'][1]['field_issues']['arrival_delay'],1)
        self.assertNotIn('PRIVATE_RECORD',json.dumps(r));self.assertNotIn('OUTSIDE_RECORD',json.dumps(r))
        self.assertIs(validate_report(r),r)

    def test_missing_mismatched_or_invalid_imports_do_not_pass_or_leak_urls(self):
        with closing(sqlite3.connect(self.db)) as c,c:
            c.execute("DELETE FROM imports WHERE period='2025-01'")
            c.execute("UPDATE imports SET rows_read=rows_read+1,rows_inserted=rows_inserted+1 WHERE period='2025-02'")
            c.execute("UPDATE imports SET source_url='PRIVATE_URL' WHERE period='2025-03'")
        r=audit(self.db);self.assertEqual(r['months'][0]['import_reconciliation'],'missing');self.assertEqual(r['months'][1]['import_reconciliation'],'mismatched')
        self.assertEqual(r['invalid_manifest_entries'],1);self.assertFalse(r['checks_passed']);self.assertNotIn('PRIVATE_URL',json.dumps(r))

    def test_missing_database_budget_and_private_output_preserve_failure_receipts(self):
        missing=self.root/'missing.sqlite3'
        with self.assertRaises(ValueError):audit(missing)
        self.assertFalse(missing.exists());calls=[0]
        def expired():calls[0]+=1;return 0 if calls[0]==1 else 121
        with self.assertRaises((RuntimeError,sqlite3.OperationalError)):audit(self.db,clock=expired)
        private=self.root/'.local';private.mkdir()
        with patch('pipelines.audit_quality.ROOT',self.root):
            with self.assertRaises(ValueError):run(self.db,self.root/'outside')
            with self.assertRaises(ValueError):run(missing,private/'failed')
            self.assertTrue((private/'failed/started.json').is_file());self.assertFalse((private/'failed/report.json').exists())
            with self.assertRaises(ValueError):run(self.db,private/'failed')

    def test_recorded_actual_report_pinned_with_frozen_population_counts(self):
        r=load_quality();self.assertEqual(r['query_sha256'],hashlib.sha256(SQL.encode()).hexdigest());self.assertEqual(r['source_records'],2835101);self.assertTrue(r['checks_passed'])
        self.assertEqual(r['field_issue_occurrences'],0)
        self.assertEqual([r['modelling_alignment'][k]['audited_eligible'] for k in ['train','validation','test']],[1611046,577730,597574])
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with self.assertRaises(OSError):load_quality(root)
            for name in [REPORT,DATASET]:
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((ROOT/name).read_text(encoding='utf-8').replace('\n','\r\n').encode())
            self.assertTrue(load_quality(root)['integrity_verified'])
            (root/REPORT).write_text((ROOT/REPORT).read_text(encoding='utf-8')+' ',encoding='utf-8')
            with self.assertRaises(ValueError):load_quality(root)

    def test_false_conclusions_and_inconsistent_accounting_are_rejected(self):
        original=load_quality()
        for mutate in [lambda r:r.__setitem__('checks_passed',False),lambda r:r.__setitem__('source_records',1),
                       lambda r:r['months'][0]['cohorts'].__setitem__('eligible_arrivals',0),
                       lambda r:r['months'][0].__setitem__('import_reconciliation','mismatched'),
                       lambda r:r['months'][0]['field_issues'].__setitem__('date',True)]:
            changed=copy.deepcopy(original);mutate(changed)
            with self.assertRaises(ValueError):validate_report(changed)

    def test_authenticated_viewer_readonly_and_safe_unavailability(self):
        app=create_app(self.db)
        with TestClient(app) as client:
            path='/api/v1/research/data-quality';self.assertEqual(client.get(path).status_code,401)
            password='temporary-quality-fixture-123';origin={'Origin':'http://127.0.0.1:8080'}
            app.state.auth_store.create_user('fixture-admin',password,'admin');app.state.auth_store.create_user('fixture-viewer',password,'viewer')
            login=client.post('/api/v1/auth/login',json={'username':'fixture-viewer','password':password},headers=origin)
            self.assertEqual(login.status_code,200);self.assertEqual(client.get(path).status_code,200)
            self.assertEqual(client.get(path).headers['cache-control'],'no-store')
            client.headers.update({**origin,'X-CSRF-Token':login.json()['csrf_token']})
            self.assertEqual(client.post(path,json={}).status_code,405);self.assertEqual(client.get(path+'/arbitrary').status_code,404)
            with patch('services.api.main.load_quality',side_effect=ValueError('PRIVATE PATH')):
                result=client.get(path)
            self.assertEqual(result.status_code,503);self.assertNotIn('months',result.json());self.assertNotIn('PRIVATE PATH',result.text)
