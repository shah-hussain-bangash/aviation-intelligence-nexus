"""Exact-report, explicitly acknowledged sharing withdrawal input."""
from uuid import UUID
from pydantic import BaseModel,ConfigDict,Field,model_validator


class SharingWithdrawal(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    run_id:UUID
    report_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    withdrawal_key:UUID
    note:str=Field(min_length=5,max_length=500)
    acknowledged:bool=Field(strict=True)

    @model_validator(mode='after')
    def confirmation(self):
        if not self.acknowledged:raise ValueError('Confirm the sharing withdrawal')
        return self
