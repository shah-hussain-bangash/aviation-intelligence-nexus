from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from sklearn.linear_model import Ridge

from ml.evaluate_synthetic_holdout import evaluate_once
from ml.verify_synthetic_evaluation import setup,verify
from services.api.paths import ROOT


class SyntheticEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.case=self.root/'experiment';setup(self.case)

    def tearDown(self):self.temp.cleanup()

    def test_one_attempt_scores_selected_model_without_refitting(self):
        with patch.object(Ridge,'fit',side_effect=AssertionError('must not refit')):
            result=evaluate_once(self.case)
        self.assertEqual(result['state'],'evaluated',result)
        self.assertTrue(result['test_evaluated']);self.assertTrue(result['claim_consumed'])
        self.assertFalse(result['model_refitted']);self.assertFalse(result['source_authenticated'])
        self.assertEqual(result['selected_metrics']['records'],8)
        self.assertEqual(result['baseline_metrics']['records'],8)

    def test_attempt_marker_exists_before_any_holdout_file_open(self):
        original=Path.open;seen=[];case=self.case
        def tracked(path,*args,**kwargs):
            if path.name in ('holdout-features.json','holdout-labels.json'):
                seen.append((case/'holdout-attempt.json').exists())
            return original(path,*args,**kwargs)
        with patch.object(Path,'open',tracked):result=evaluate_once(self.case)
        self.assertEqual(result['state'],'evaluated');self.assertTrue(seen and all(seen))

    def test_repeated_call_never_reopens_holdout_or_changes_receipt(self):
        evaluate_once(self.case)
        before=(self.case/'holdout-evaluation.json').read_bytes();original=Path.open
        def guarded(path,*args,**kwargs):
            if path.name in ('holdout-features.json','holdout-labels.json'):raise AssertionError('holdout reread')
            return original(path,*args,**kwargs)
        with patch.object(Path,'open',guarded):result=evaluate_once(self.case)
        self.assertEqual(result['state'],'refused');self.assertFalse(result['claim_consumed'])
        self.assertEqual((self.case/'holdout-evaluation.json').read_bytes(),before)

    def test_changed_holdout_consumes_attempt_without_automatic_reset(self):
        (self.case/'holdout-labels.json').write_bytes(b'changed')
        first=evaluate_once(self.case)
        self.assertEqual(first['state'],'failed');self.assertTrue(first['claim_consumed'])
        self.assertTrue((self.case/'holdout-attempt.json').exists())
        self.assertFalse(first['test_evaluated'])
        self.assertEqual(evaluate_once(self.case)['state'],'refused')

    def test_changed_frozen_selection_refused_before_claim_or_label_read(self):
        selected=self.case/'frozen-selection.json';value=json.loads(selected.read_text(encoding='utf-8'))
        value['selected']['intercept']+=1
        selected.write_text(json.dumps(value),encoding='utf-8')
        result=evaluate_once(self.case)
        self.assertEqual(result['state'],'refused');self.assertFalse(result['claim_consumed'])
        self.assertFalse((self.case/'holdout-attempt.json').exists())

    def test_concurrent_calls_allow_only_one_evaluation(self):
        with ThreadPoolExecutor(max_workers=2) as workers:
            results=list(workers.map(lambda _:evaluate_once(self.case),range(2)))
        self.assertEqual(sorted(row['state'] for row in results),['evaluated','refused'])
        self.assertEqual(sum(row['claim_consumed'] for row in results),1)
        self.assertEqual(json.loads((self.case/'holdout-attempt.json').read_text(encoding='utf-8'))['format'],'ain-synthetic-holdout-attempt-v1')

    def test_invalid_temporal_cohort_rejected_after_claim(self):
        path=self.case/'holdout-features.json';features=json.loads(path.read_text(encoding='utf-8'))
        features[0]['decision_at']='2025-07-01T09:00:00Z'
        data=json.dumps(features).encode();path.write_bytes(data)
        policy_path=self.case/'holdout-policy.json';policy=json.loads(policy_path.read_text(encoding='utf-8'))
        policy['features_sha256']=hashlib.sha256(data).hexdigest();policy_path.write_text(json.dumps(policy),encoding='utf-8')
        result=evaluate_once(self.case)
        self.assertEqual(result['state'],'failed');self.assertTrue(result['claim_consumed'])
        self.assertFalse(result['test_evaluated'])

    def test_separate_processes_compete_for_one_atomic_claim(self):
        command=[sys.executable,'-m','ml.evaluate_synthetic_holdout',str(self.case)]
        first=subprocess.Popen(command,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        second=subprocess.Popen(command,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        out_a,err_a=first.communicate(timeout=60);out_b,err_b=second.communicate(timeout=60)
        self.assertEqual(sorted([first.returncode,second.returncode]),[0,2],err_a+err_b)
        self.assertEqual(sorted([json.loads(out_a)['state'],json.loads(out_b)['state']]),['evaluated','refused'])

    def test_development_query_identity_cannot_reappear_in_holdout(self):
        development=json.loads((self.case/'synthetic-development.json').read_text(encoding='utf-8'))
        reused=development['partitions']['validation'][0]['query_id']
        policy_path=self.case/'holdout-policy.json';policy=json.loads(policy_path.read_text(encoding='utf-8'))
        for name,key in [('holdout-features.json','features_sha256'),('holdout-labels.json','labels_sha256')]:
            path=self.case/name;rows=json.loads(path.read_text(encoding='utf-8'));rows[0]['query_id']=reused
            data=json.dumps(rows).encode();path.write_bytes(data);policy[key]=hashlib.sha256(data).hexdigest()
        policy_path.write_text(json.dumps(policy),encoding='utf-8')
        result=evaluate_once(self.case)
        self.assertEqual(result['state'],'failed');self.assertTrue(result['claim_consumed'])
        self.assertFalse(result['test_evaluated'])

    def test_demo_hashes_freeze_and_repeat_refusal(self):
        result=verify(self.root/'drill')
        self.assertTrue(result['passed']);self.assertEqual(len(result['checks']),10)
        case=self.root/'drill/experiment'
        self.assertEqual(hashlib.sha256((case/'holdout-evaluation.json').read_bytes()).hexdigest(),result['evaluation_receipt_sha256'])
        self.assertEqual(hashlib.sha256((case/'holdout-attempt.json').read_bytes()).hexdigest(),result['attempt_receipt_sha256'])
        self.assertFalse(result['frozen_experiments_accessed'])
        with self.assertRaises(FileExistsError):verify(self.root/'drill')

    def test_actual_cli_evaluates_once_then_refuses(self):
        command=[sys.executable,'-m','ml.evaluate_synthetic_holdout',str(self.case)]
        first=subprocess.run(command,cwd=ROOT,text=True,capture_output=True,timeout=30)
        self.assertEqual(first.returncode,0,first.stderr)
        second=subprocess.run(command,cwd=ROOT,text=True,capture_output=True,timeout=30)
        self.assertEqual(second.returncode,2);self.assertEqual(json.loads(second.stdout)['state'],'refused')


if __name__=='__main__':unittest.main()
