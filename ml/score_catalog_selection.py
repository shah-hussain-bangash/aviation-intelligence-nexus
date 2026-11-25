"""Read-only synthetic scoring bound to an observed catalog revision and input bytes."""
import argparse
import json

from ml.evaluate_synthetic_holdout import read_json
from ml.synthetic_model_bundle import score
from ml.synthetic_model_catalog import pin,status
from ml.train_preprocessing import signature
from pipelines.synthetic_ingestion import host,local
from pipelines.time_safe_features import require


def score_selected(directory,features_path,*,expected_revision,model_sha256,features_sha256):
    host();directory=local(directory)
    require(type(expected_revision) is int and expected_revision>=0 and pin(model_sha256)
            and pin(features_sha256),'explicit_revision_and_pins_required')
    before=status(directory)
    require(before['revision']==expected_revision and before['current']==model_sha256,'selected_version_mismatch')
    features,features_hash=read_json(features_path)
    require(features_hash==features_sha256,'features_identity_mismatch')
    bundle=local(directory/'bundles'/(model_sha256+'.json'))
    scores=score(bundle,features,bundle_sha256=model_sha256)
    require(read_json(features_path)[1]==features_hash,'features_changed')
    after=status(directory)
    require(after==before,'catalog_changed_during_scoring')
    selection=next(event for event in reversed(before['events']) if event['action'] in ('select','rollback'))
    require(selection['model_sha']==model_sha256,'selection_event_mismatch')
    return {'format':'ain-catalog-selected-scores-v1','source_scope':'synthetic','read_only':True,
            'catalog_revision':expected_revision,'catalog_snapshot_sha256':signature(before),
            'selection_event':selection,'features_sha256':features_hash,
            'scores':scores,'prediction_sha256':signature(scores['predictions']),
            'model_refitted':False,'deployment_performed':False,'production_ready':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('catalog');parser.add_argument('features')
    parser.add_argument('--expected-revision',required=True,type=int)
    parser.add_argument('--model-sha256',required=True);parser.add_argument('--features-sha256',required=True)
    args=parser.parse_args()
    try:
        result=score_selected(args.catalog,args.features,expected_revision=args.expected_revision,
                              model_sha256=args.model_sha256,features_sha256=args.features_sha256)
        print(json.dumps(result,indent=2,allow_nan=False))
    except Exception:
        print(json.dumps({'error':'catalog_selected_scoring_refused','production_ready':False}));raise SystemExit(2)
