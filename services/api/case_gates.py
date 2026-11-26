"""Captured synthetic gate proposals, not live allocation or solver execution."""
import json
from uuid import UUID
from pydantic import BaseModel,ConfigDict,Field
from optimization.reviews import status,aware


class AttachGate(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_version:int=Field(strict=True,ge=1,le=99)
    gate_run_id:UUID
    gate_sha256:str=Field(pattern=r'^[0-9a-f]{64}$')


def checked_gate(raw,run_id):
    if not isinstance(raw,str) or len(raw.encode('utf-8'))>64_000:raise ValueError('Gate snapshot exceeds bound')
    result=json.loads(raw)
    if not isinstance(result,dict) or result.get('run_id')!=str(run_id) or not isinstance(result.get('review'),dict):
        raise ValueError('Reviewed proposal identity required')
    # Use the recorded review time: later window expiry must not relabel a retained decision.
    # status verifies the proposal/scenario hashes, plans, objective and receipt without solving.
    checked=status(result,aware(result['review']['reviewed_at']))
    if checked['state'] not in ('reviewed','needs_changes') or result['scenario']['data_kind']!='synthetic':
        raise ValueError('A consistent synthetic research review is required')
    return result


def gate_summary(result):
    candidate=result['candidate']['verification'];baseline=result['baseline']['verification']
    return {'data_kind':'synthetic','proposal_sha256':result['proposal_sha256'],'scenario_sha256':result['scenario_sha256'],
        'review_state':result['review']['decision'],'flight_count':len(result['scenario']['flights']),
        'candidate_assigned':candidate['assigned'],'candidate_unassigned':candidate['unassigned'],
        'baseline_assigned':baseline['assigned'],'baseline_unassigned':baseline['unassigned']}
