"""Proposal-bound synthetic research review, never airport authorization."""
from datetime import datetime,timedelta,timezone
import hashlib
import json
import math
from typing import Literal
from uuid import UUID
from pydantic import BaseModel,ConfigDict,Field,model_validator
from optimization.gates import GateScenario,verify_plan

WINDOW=timedelta(hours=24)


class GateReview(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    run_id:UUID
    proposal_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    review_key:UUID
    decision:Literal['reviewed','needs_changes']
    note:str=Field(min_length=5,max_length=1000)
    acknowledged:bool=Field(strict=True)

    @model_validator(mode='after')
    def research_acknowledgment(self):
        if not self.acknowledged:raise ValueError('Acknowledge synthetic research scope')
        return self


class ReviewConflict(ValueError):
    pass


def now():return datetime.now(timezone.utc)


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,allow_nan=False).encode()).hexdigest()


def proposal_hash(run):
    return digest({k:v for k,v in run.items() if k not in ('proposal_sha256','review','review_status','replayed','review_replayed')})


def aware(value):
    value=datetime.fromisoformat(value)
    if value.tzinfo is None:raise ValueError('Missing time zone')
    return value


def verify_core(run):
    if run['research_only'] is not True or run['operational_approval'] is not False or run['engine']!='scipy-highs-milp' or run['formulation_version']!='gate-v1' or run['solver_status'] not in ('optimal','time_limited_feasible'):
        raise ValueError('Unsupported proposal scope')
    scenario=GateScenario.model_validate(run['scenario'])
    if digest(scenario.model_dump())!=run['scenario_sha256']:raise ValueError('Scenario changed')
    for name in ['candidate','baseline']:
        checked=verify_plan(scenario,run[name])
        if not checked['feasible'] or digest(checked)!=digest(run[name]['verification']):
            raise ValueError('Independent plan verification failed')
    penalty=len(scenario.flights)*max(v for f in scenario.flights for v in f.costs.values())+1
    if type(run['unassigned_penalty']) is not int or run['unassigned_penalty']!=penalty or not math.isfinite(run['objective']) or not math.isclose(run['objective'],run['candidate']['verification']['assignment_cost']+penalty*run['candidate']['verification']['unassigned'],abs_tol=1e-8):
        raise ValueError('Objective reconciliation failed')


def seal(run):
    verify_core(run)
    sealed={**run,'review_expires_at':(aware(run['saved_at'])+WINDOW).isoformat(),'review':None}
    sealed['proposal_sha256']=proposal_hash(sealed)
    return sealed


def status(run,current=None):
    base={'state':'invalid','eligible':False,'window_hours':24,'expires_at':None,
        'scope':'Synthetic research review only; no independent-reviewer or operational approval claim'}
    if 'proposal_sha256' not in run and 'review_expires_at' not in run:return {**base,'state':'legacy'}
    try:
        if proposal_hash(run)!=run['proposal_sha256']:return base
        verify_core(run)
        saved=aware(run['saved_at']);expires=aware(run['review_expires_at']);current=current or now()
        if current.tzinfo is None or current<saved or expires-saved!=WINDOW:return base
        receipt=run.get('review')
        if receipt is not None:
            if not isinstance(receipt,dict) or set(receipt)!={'review_key','reviewer','proposal_sha256','decision','note','reviewed_at','decision_sha256','acknowledged'}:return base
            if receipt['acknowledged'] is not True or not isinstance(receipt['reviewer'],str) or not isinstance(receipt['note'],str) or not 5<=len(receipt['note'])<=1000 or receipt['decision'] not in ('reviewed','needs_changes') or receipt['proposal_sha256']!=run['proposal_sha256'] or digest({k:v for k,v in receipt.items() if k!='decision_sha256'})!=receipt['decision_sha256'] or not saved<=aware(receipt['reviewed_at'])<expires:return base
            return {**base,'state':receipt['decision'],'expires_at':expires.isoformat()}
        return {**base,'state':'expired' if current>=expires else 'pending','eligible':current<expires,'expires_at':expires.isoformat()}
    except (ValueError,TypeError,KeyError,OverflowError,AttributeError):return base


def view(run,current=None):return {**run,'review_status':status(run,current)}
