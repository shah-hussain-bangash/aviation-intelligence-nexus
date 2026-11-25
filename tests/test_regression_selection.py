import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from sklearn.linear_model import Ridge

from ml.regression_selection import metrics,protocol,select_regression
from ml.verify_regression_selection import fixture,verify
from services.api.paths import ROOT


class RegressionSelectionTests(unittest.TestCase):
    def setUp(self):
        self.development=fixture()
        self.protocol=protocol(self.development['boundaries'],experiment_id='synthetic-regression',scope='synthetic')

    def test_actual_models_baseline_and_validation_selection(self):
        original=copy.deepcopy(self.development)
        result=select_regression(self.development,self.protocol)
        self.assertEqual((result['training_records'],result['validation_records']),(20,8))
        self.assertEqual([r['alpha'] for r in result['candidates']],[0.1,1,10])
        selected=min(result['candidates'],key=lambda row:(row['validation']['mae'],row['alpha']))
        self.assertEqual(result['selected']['alpha'],selected['alpha'])
        self.assertEqual(result['baseline']['value'],float(np.median([r['y'] for r in original['partitions']['train']])))
        self.assertEqual(self.development,original)
        self.assertFalse(result['test_evaluated']);self.assertFalse(result['production_ready'])

    def test_model_fit_receives_training_targets_and_never_validation_targets(self):
        seen=[];original=Ridge.fit
        def tracked(model,x,y,*args,**kwargs):
            seen.append((x.shape,y.tolist()));return original(model,x,y,*args,**kwargs)
        with patch.object(Ridge,'fit',tracked):select_regression(self.development,self.protocol)
        expected=[r['y'] for r in self.development['partitions']['train']]
        self.assertEqual(len(seen),3)
        self.assertTrue(all(shape[0]==20 and labels==expected for shape,labels in seen))

    def test_validation_target_mutation_leaves_models_and_preprocessor_unchanged(self):
        first=select_regression(self.development,self.protocol)
        changed=copy.deepcopy(self.development)
        for row in changed['partitions']['validation']:row['y']+=123
        second=select_regression(changed,self.protocol)
        self.assertEqual(first['preprocessing']['fit_state_sha256'],second['preprocessing']['fit_state_sha256'])
        self.assertEqual([(r['coefficients'],r['intercept']) for r in first['candidates']],[(r['coefficients'],r['intercept']) for r in second['candidates']])
        self.assertNotEqual(first['candidates'][0]['validation'],second['candidates'][0]['validation'])

    def test_test_partition_refused_before_any_preprocessing_fit(self):
        self.development['partitions']['test']=[{'PRIVATE_TEST_TARGET':999}]
        with patch('ml.regression_selection.fit_training_preprocessor') as fit,self.assertRaisesRegex(ValueError,'test_partition_not_accepted'):
            select_regression(self.development,self.protocol)
        fit.assert_not_called()

    def test_changed_protocol_cannot_silently_change_selection_policy(self):
        for field,value in [('alpha_grid',[1,100]),('selection_metric','test_mae'),('target','cancelled'),('production_approval',True)]:
            changed=copy.deepcopy(self.protocol);changed[field]=value
            with self.assertRaisesRegex(ValueError,'unsupported_or_changed_protocol'):
                select_regression(self.development,changed)

    def test_hidden_extra_holdout_field_refused_before_fit_or_hashing(self):
        self.development['hidden_holdout_labels']=[999]
        with patch('ml.regression_selection.fit_training_preprocessor') as fit,self.assertRaisesRegex(ValueError,'unexpected_development_fields'):
            select_regression(self.development,self.protocol)
        fit.assert_not_called()

    def test_minimum_development_and_nonconstant_target_requirements(self):
        data=copy.deepcopy(self.development);data['partitions']['validation']=data['partitions']['validation'][:1]
        with self.assertRaisesRegex(ValueError,'cohort_too_small'):select_regression(data,self.protocol)
        data=copy.deepcopy(self.development)
        for row in data['partitions']['train']:row['y']=10
        with self.assertRaisesRegex(ValueError,'variance_required'):select_regression(data,self.protocol)

    def test_metrics_against_hand_calculation(self):
        result=metrics(np.asarray([0.,2.,4.]),np.asarray([1.,2.,1.]))
        self.assertAlmostEqual(result['mae'],4/3)
        self.assertAlmostEqual(result['rmse'],(10/3)**0.5)
        self.assertEqual(result['records'],3)

    def test_demo_protocol_exists_before_any_candidate_fit_and_hashes_match(self):
        with tempfile.TemporaryDirectory() as temporary:
            case=Path(temporary)/'case';original=Ridge.fit;seen=[]
            def tracked(model,*args,**kwargs):
                seen.append((case/'registered-protocol.json').is_file())
                return original(model,*args,**kwargs)
            with patch.object(Ridge,'fit',tracked):result=verify(case)
            self.assertTrue(result['passed']);self.assertTrue(all(seen));self.assertEqual(len(result['checks']),10)
            for name,key in [('registered-protocol.json','protocol_file_sha256'),('synthetic-development.json','development_file_sha256'),('frozen-selection.json','selection_file_sha256')]:
                self.assertEqual(hashlib.sha256((case/name).read_bytes()).hexdigest(),result[key])
            self.assertFalse(result['test_evaluated'])
            with self.assertRaises(FileExistsError):verify(case)

    def test_actual_cli_and_no_existing_database_argument(self):
        command=[sys.executable,'-m','ml.verify_regression_selection']
        result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr);self.assertTrue(json.loads(result.stdout)['passed'])
        bad=subprocess.run([*command,'--database','PRIVATE_PATH'],cwd=ROOT,capture_output=True,text=True,timeout=30)
        self.assertEqual(bad.returncode,2)


if __name__=='__main__':unittest.main()
