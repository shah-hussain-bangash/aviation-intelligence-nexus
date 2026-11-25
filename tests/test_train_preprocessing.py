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
from scipy.sparse import isspmatrix_csr
from sklearn.compose import ColumnTransformer

from ml.train_preprocessing import fit_training_preprocessor
from ml.verify_train_preprocessing import fixture,verify
from services.api.paths import ROOT


class TrainPreprocessingTests(unittest.TestCase):
    def setUp(self):self.prepared=fixture()

    def test_real_scaler_and_encoder_fit_training_statistics_only(self):
        original=copy.deepcopy(self.prepared)
        result=fit_training_preprocessor(self.prepared)
        state=result['report']['fit_state']
        self.assertEqual(state['origin_categories'],['AAA'])
        self.assertEqual(state['numeric_mean'],[25,10]);self.assertEqual(state['numeric_scale'],[5,5])
        np.testing.assert_allclose(result['matrices']['train'].toarray(),[[1,-1,-1],[1,1,1]])
        np.testing.assert_allclose(result['matrices']['validation'].toarray(),[[0,15,-1]])
        self.assertTrue(all(isspmatrix_csr(m) for m in result['matrices'].values()))
        self.assertEqual(self.prepared,original)
        self.assertFalse(result['report']['predictive_model_trained'])

    def test_fit_receives_only_training_feature_columns_and_no_targets(self):
        seen=[];original=ColumnTransformer.fit
        def tracked(transformer,frame,*args,**kwargs):
            seen.append(frame.copy());return original(transformer,frame,*args,**kwargs)
        with patch.object(ColumnTransformer,'fit',tracked):fit_training_preprocessor(self.prepared)
        self.assertEqual(len(seen),1)
        self.assertEqual(list(seen[0].columns),['origin','temperature_c','wind_knots'])
        self.assertEqual(seen[0]['temperature_c'].tolist(),[20,30])

    def test_future_and_target_mutation_cannot_change_fitted_state(self):
        first=fit_training_preprocessor(self.prepared)
        changed=copy.deepcopy(self.prepared)
        for name,rows in changed['partitions'].items():
            for row in rows:
                row['y']=999
                if name!='train':row['X'].update(origin='ZZZ',temperature_c=10000,wind_knots=500)
        second=fit_training_preprocessor(changed)
        self.assertEqual(first['report']['fit_state_sha256'],second['report']['fit_state_sha256'])
        self.assertEqual((first['matrices']['train']!=second['matrices']['train']).nnz,0)
        self.assertNotEqual(first['report']['prepared_input_sha256'],second['report']['prepared_input_sha256'])

    def test_empty_future_splits_preserve_output_schema(self):
        self.prepared['partitions']['validation']=[];self.prepared['partitions']['test']=[]
        self.prepared['counts'].update(validation=0,test=0,input_features=6,input_labels=5)
        result=fit_training_preprocessor(self.prepared)
        self.assertEqual(result['matrices']['test'].shape,(0,3))
        self.assertEqual(result['matrices']['validation'].shape,(0,3))

    def test_extra_target_columns_and_invalid_numeric_values_refused(self):
        for key,value in [('target',10),('wind_knots',-1),('temperature_c',float('nan')),('wind_knots',True)]:
            data=copy.deepcopy(self.prepared);data['partitions']['train'][0]['X'][key]=value
            with self.assertRaises(ValueError):fit_training_preprocessor(data)

    def test_duplicate_split_identity_and_immature_labels_refused(self):
        data=copy.deepcopy(self.prepared)
        data['partitions']['test'][0]['query_id']=data['partitions']['train'][0]['query_id']
        with self.assertRaisesRegex(ValueError,'duplicate_or_invalid_query'):fit_training_preprocessor(data)
        data=copy.deepcopy(self.prepared)
        data['partitions']['train'][0]['provenance']['label_available_at']='2025-07-02T00:00:00Z'
        with self.assertRaisesRegex(ValueError,'immature_target'):fit_training_preprocessor(data)

    def test_invalid_counts_and_empty_training_are_not_model_ready(self):
        data=copy.deepcopy(self.prepared);data['counts']['train']=0
        with self.assertRaisesRegex(ValueError,'invalid_prepared_counts'):fit_training_preprocessor(data)
        data=copy.deepcopy(self.prepared);data['partitions']['train']=[]
        data['counts'].update(train=0,input_features=6,input_labels=5)
        with self.assertRaisesRegex(ValueError,'nonempty_training'):fit_training_preprocessor(data)

    def test_training_categories_bounded_and_nonfinite_fit_refused(self):
        with patch('ml.train_preprocessing.MAX_ORIGINS',0),self.assertRaisesRegex(ValueError,'origin_limit'):
            fit_training_preprocessor(self.prepared)
        data=copy.deepcopy(self.prepared)
        for row in data['partitions']['train']:row['X']['temperature_c']=1e308
        with self.assertRaises(ValueError):fit_training_preprocessor(data)

    def test_demo_retains_json_state_and_sparse_arrays_without_pickle(self):
        with tempfile.TemporaryDirectory() as temporary:
            case=Path(temporary)/'case';result=verify(case)
            self.assertTrue(result['passed']);self.assertEqual(len(result['checks']),10)
            for name,key in [('synthetic-prepared.json','prepared_sha256'),('preprocessing-state.json','preprocessing_sha256'),('sparse-matrices.json','matrix_sha256')]:
                self.assertEqual(hashlib.sha256((case/name).read_bytes()).hexdigest(),result[key])
            self.assertTrue(all(p.suffix=='.json' for p in case.iterdir()))
            self.assertFalse(result['predictive_model_trained'])
            with self.assertRaises(FileExistsError):verify(case)

    def test_actual_cli_refuses_existing_database_argument(self):
        command=[sys.executable,'-m','ml.verify_train_preprocessing']
        result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr);self.assertTrue(json.loads(result.stdout)['passed'])
        bad=subprocess.run([*command,'--database','PRIVATE_PATH'],cwd=ROOT,capture_output=True,text=True,timeout=30)
        self.assertEqual(bad.returncode,2)


if __name__=='__main__':unittest.main()
