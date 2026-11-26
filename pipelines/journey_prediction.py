"""Copy only the registered, explicitly pinned local research model; never arbitrary pickle input."""
import hashlib
import json
from pathlib import Path
import re

from infra.research_model_recovery import ordinary,unique_object
from pipelines.synthetic_ingestion import local
from services.api.paths import ROOT

SCENARIO={'carrier':'AA','origin':'JFK','destination':'LAX','flight_date':'2025-05-15','scheduled_departure':'09:00'}


def validate_options(live_prediction,model_sha256):
    if type(live_prediction) is not bool:raise ValueError('explicit_live_prediction_boolean_required')
    if live_prediction and (not isinstance(model_sha256,str) or not re.fullmatch('[a-f0-9]{64}',model_sha256)):
        raise ValueError('explicit_registered_model_sha256_required')
    if not live_prediction and model_sha256 is not None:raise ValueError('model_pin_requires_live_prediction')


def source_preserved(metadata):
    source=ROOT/'.local/models/delay-v2'
    return (hashlib.sha256(ordinary(source/'model.joblib',32_000_000).read_bytes()).hexdigest()==metadata['artifact_sha256']
        and hashlib.sha256(ordinary(source/'report.json',1_000_000).read_bytes()).hexdigest()==metadata['report_sha256'])


def copy_registered_model(destination,expected_sha256):
    if not isinstance(expected_sha256,str) or not re.fullmatch('[a-f0-9]{64}',expected_sha256):
        raise ValueError('explicit_registered_model_sha256_required')
    if '..' in Path(destination).parts:raise ValueError('fresh_private_model_directory_required')
    target=local(destination)
    if not target.is_relative_to(ROOT/'.local') or target.exists():raise ValueError('fresh_private_model_directory_required')
    source=ROOT/'.local/models/delay-v2'
    artifact=ordinary(source/'model.joblib',32_000_000);report_path=ordinary(source/'report.json',1_000_000)
    published=ordinary(ROOT/'docs/reports/Delay_v2.json',1_000_000)
    model_bytes=artifact.read_bytes();report_bytes=report_path.read_bytes();public_bytes=published.read_bytes()
    model_hash=hashlib.sha256(model_bytes).hexdigest()
    metadata=json.loads(report_bytes,object_pairs_hook=unique_object);public=json.loads(public_bytes,object_pairs_hook=unique_object)
    if (model_hash!=expected_sha256 or metadata!=public or metadata.get('artifact_sha256')!=expected_sha256
        or metadata.get('model_version')!='delay-v2' or metadata.get('release_assessment',{}).get('research_gate_passed') is not True
        or metadata.get('release_assessment',{}).get('approved_for_operational_serving') is not False):
        raise ValueError('registered_research_model_pin_or_report_mismatch')
    target.mkdir(parents=True,exist_ok=False)
    with (target/'model.joblib').open('xb') as stream:stream.write(model_bytes)
    with (target/'report.json').open('xb') as stream:stream.write(report_bytes)
    return {'artifact_sha256':model_hash,'report_sha256':hashlib.sha256(report_bytes).hexdigest(),
        'public_report_sha256':hashlib.sha256(public_bytes).hexdigest(),'model_version':'delay-v2',
        'registered_source':'.local/models/delay-v2','source_report_matches_committed_report':True,
        'operational_serving_approved':False,'scenario':dict(SCENARIO)}
