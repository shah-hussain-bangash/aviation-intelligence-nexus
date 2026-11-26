import copy
from contextlib import closing
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

from pipelines import case_usefulness_review as review
from pipelines.verify_case_journey import exercise
from services.api.research_cases import digest


class CaseUsefulnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from services.api.paths import ROOT
        (ROOT/'.local').mkdir(exist_ok=True)
        cls.temp=tempfile.TemporaryDirectory(prefix='case-review-tests-',dir=ROOT/'.local');cls.root=Path(cls.temp.name)
        # This test fixture is explicitly labelled; it does not contact a model.
        receipt=exercise(cls.root/'fixture')
        receipt.update(format='ain-combined-case-journey-v1',live_ai_requested=True,generator_executed=True,worker_loop_executed=True,
            production_ready=False,genuine_human_acceptance=False,local_model={'name':'SYNTHETIC TEST MODEL','digest':'fixture'})
        import sqlite3
        with closing(sqlite3.connect(cls.root/'fixture/research-cases.sqlite3')) as db,db:
            run=json.loads(db.execute('SELECT snapshot_json FROM case_agents').fetchone()[0])
            run['model']=receipt['local_model'];pin=digest(run)
            db.execute('UPDATE case_agents SET snapshot_json=?,agent_sha256=?',(json.dumps(run),pin))
        receipt['agent_snapshot_sha256']=pin
        # Reproject the deliberately amended synthetic store for this renderer fixture.
        from services.api.research_cases import ResearchCaseService
        with closing(sqlite3.connect(cls.root/'fixture/research-cases.sqlite3')) as db:
            db.row_factory=sqlite3.Row;row=db.execute('SELECT * FROM cases').fetchone()
            receipt['final_case_sha256']=digest(object.__new__(ResearchCaseService).projection(db,row))
        cls.receipt=receipt

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def prepare(self):
        report=self.root/'fixture/report.json';report.write_text(json.dumps(self.receipt))
        folder=self.root/'reviews'/uuid4().hex
        folder.parent.mkdir(exist_ok=True)
        result=review.prepare(report,hashlib.sha256(report.read_bytes()).hexdigest(),folder)
        packet=json.loads(Path(result['packet']).read_text(encoding='utf-8'));return result,packet

    def test_packet_and_blank_page_preserve_readonly_source_and_ratings(self):
        db=self.root/'fixture/research-cases.sqlite3';before=hashlib.sha256(db.read_bytes()).hexdigest()
        result,p=self.prepare();self.assertEqual(before,hashlib.sha256(db.read_bytes()).hexdigest())
        initial=review.blank(p,result['packet_sha256']);self.assertEqual(review.assess(p,result['packet_sha256'],initial)['status'],'pending')
        self.assertFalse(result['human_ratings_supplied']);html=Path(result['page']).read_text(encoding='utf-8')
        self.assertIn("connect-src 'none'",html);self.assertIn('Choose your rating',html)

    def test_changed_report_or_evidence_is_rejected(self):
        _,p=self.prepare()
        for mutate in [lambda v:v['run'].update(report_sha256='0'*64),lambda v:v['evidence'][0].update(text='changed'),lambda v:v.update(production_ready=True)]:
            changed=copy.deepcopy(p);mutate(changed)
            with self.assertRaises(ValueError):review.validate_packet(changed)

    def test_declarations_remain_unsigned_and_changed_binding_is_rejected(self):
        result,p=self.prepare();v=review.blank(p,result['packet_sha256'])
        v.update(reviewer_label='SYNTHETIC UNIT TEST',source_checked=True,own_assessment=True,question_answered='yes')
        for c in v['claims']:c.update(supported='yes',relevant='no')
        assessed=review.assess(p,result['packet_sha256'],v);self.assertEqual(assessed['status'],'declared_needs_revision')
        self.assertFalse(assessed['human_identity_verified']);v['packet_sha256']='0'*64
        with self.assertRaises(ValueError):review.assess(p,result['packet_sha256'],v)

    def test_wrong_receipt_pin_creates_no_output(self):
        report=self.root/'fixture/report.json';report.write_text(json.dumps(self.receipt))
        output=self.root/'reviews'/uuid4().hex
        with self.assertRaises(ValueError):review.prepare(report,'0'*64,output)
        self.assertFalse(output.exists())

    def test_existing_review_folder_and_blank_ratings_are_preserved(self):
        result,p=self.prepare();folder=Path(result['page']).parent
        original={f.name:f.read_bytes() for f in folder.iterdir()}
        report=self.root/'fixture/report.json'
        with self.assertRaises(ValueError):review.prepare(report,hashlib.sha256(report.read_bytes()).hexdigest(),folder)
        self.assertEqual(original,{f.name:f.read_bytes() for f in folder.iterdir()})


if __name__=='__main__':unittest.main()
