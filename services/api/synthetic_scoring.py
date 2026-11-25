"""Explicit host-only synthetic fixture service; no client-controlled filesystem paths."""
from types import MappingProxyType

from pydantic import BaseModel,ConfigDict,Field,field_validator


class SyntheticScoreRequest(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    dataset_id:str=Field(pattern=r'^[a-zA-Z0-9_-]{1,64}$')
    expected_revision:int=Field(ge=0,le=10_000)
    model_sha256:str=Field(pattern=r'^[0-9a-f]{64}$')
    features_sha256:str=Field(pattern=r'^[0-9a-f]{64}$')
    acknowledged:bool

    @field_validator('acknowledged')
    @classmethod
    def research_acknowledged(cls,value):
        if value is not True:raise ValueError('synthetic_research_acknowledgment_required')
        return value


class SyntheticScoringService:
    def __init__(self,catalog,datasets):
        # The research importer depends on main; do not load it during API import.
        from pipelines.synthetic_ingestion import host,local
        from ml.synthetic_model_catalog import pin
        from pipelines.time_safe_features import require
        host();self.catalog=local(catalog)
        require(type(datasets) is dict and 1<=len(datasets)<=10,'bounded_dataset_configuration_required')
        configured={}
        for name,(path,digest) in datasets.items():
            # Apply the request's ID grammar to server configuration as well.
            SyntheticScoreRequest(dataset_id=name,expected_revision=0,model_sha256='0'*64,features_sha256='0'*64,acknowledged=True)
            require(pin(digest),'configured_dataset_pin_required')
            configured[name]=(local(path),digest)
        self.datasets=MappingProxyType(configured)

    def context(self):
        from ml.evaluate_synthetic_holdout import read_json
        from ml.synthetic_model_catalog import status
        from pipelines.time_safe_features import require
        snapshot=status(self.catalog)
        for path,digest in self.datasets.values():require(read_json(path)[1]==digest,'configured_dataset_changed')
        return {'format':'ain-synthetic-scoring-context-v1','available':True,
                'catalog_revision':snapshot['revision'],'selected_model_sha256':snapshot['current'],
                'datasets':[{'dataset_id':name,'features_sha256':pair[1]} for name,pair in sorted(self.datasets.items())],
                'source_scope':'synthetic','saved_to_history':False,'operational_approval':False,'production_ready':False}

    def run(self,query:SyntheticScoreRequest):
        from ml.score_catalog_selection import score_selected
        from pipelines.time_safe_features import require
        require(query.dataset_id in self.datasets,'dataset_not_configured')
        path,digest=self.datasets[query.dataset_id]
        require(query.features_sha256==digest,'configured_dataset_identity_mismatch')
        raw=score_selected(self.catalog,path,expected_revision=query.expected_revision,
                           model_sha256=query.model_sha256,features_sha256=digest)
        event=raw['selection_event']
        # Free-text reasons and server paths never cross this projection.
        return {'format':'ain-authenticated-synthetic-scores-v1','dataset_id':query.dataset_id,
                'catalog_revision':raw['catalog_revision'],'catalog_snapshot_sha256':raw['catalog_snapshot_sha256'],
                'features_sha256':raw['features_sha256'],'prediction_sha256':raw['prediction_sha256'],
                'selection_event':{key:event[key] for key in ('revision','action','model_sha','prior_sha','recorded_at')},
                'scores':raw['scores'],'source_scope':'synthetic','saved_to_history':False,
                'model_refitted':False,'operational_approval':False,'production_ready':False}
