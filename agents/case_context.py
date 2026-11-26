"""Bounded server-recorded case metadata; no case notes or access grants."""
from typing import Literal
from uuid import UUID
from pydantic import BaseModel,ConfigDict,Field


class CaseContext(BaseModel):
    model_config=ConfigDict(extra='forbid')
    case_id:UUID
    case_version:int=Field(strict=True,ge=1,le=100)
    case_sha256:str=Field(pattern=r'^[0-9a-f]{64}$')
    source_run_id:UUID
    source_sha256:str=Field(pattern=r'^[0-9a-f]{64}$')
    title:str=Field(min_length=1,max_length=160)
    scope:Literal['historical_us_research']


def checked_context(value):
    return CaseContext.model_validate(value).model_dump(mode='json')
