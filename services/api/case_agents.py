"""Validate captured agent records; no execution, semantic certification or access grant."""
import hashlib
import json
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from agents.case_context import checked_context


class AttachAgent(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_version:int=Field(strict=True,ge=1,le=99)
    agent_run_id:UUID
    agent_sha256:str=Field(pattern=r'^[0-9a-f]{64}$')


def checked_agent(raw,run_id,owner_id):
    if not isinstance(raw,str) or len(raw.encode('utf-8'))>128_000:raise ValueError('Agent snapshot exceeds bound')
    result=json.loads(raw)
    if not isinstance(result,dict) or result.get('run_id')!=str(run_id) or result.get('research_only') is not True or result.get('operational_approval') is not False:
        raise ValueError('Research report identity required')
    if result.get('runtime')!='bounded-ollama-tools-v2' or result.get('state') not in ('reviewed','needs_changes'):
        raise ValueError('A completed research review is required')
    request=result.get('request')
    if not isinstance(request,dict) or not isinstance(request.get('objective'),str) or not 1<=len(request['objective'])<=600:
        raise ValueError('Bounded objective required')
    if not isinstance(request.get('require_peer_review',False),bool):raise ValueError('Review policy malformed')
    if 'case_context' in request:
        checked_context(request['case_context'])
        if request.get('require_peer_review'):raise ValueError('Case report sharing unavailable')
    if not isinstance(result.get('steps'),list) or len(result['steps'])>3 or not isinstance(result.get('claims'),list) or len(result['claims'])>3:
        raise ValueError('Bounded report required')
    report_hash=hashlib.sha256(json.dumps({k:result[k] for k in ('request','steps','claims')},sort_keys=True,allow_nan=False).encode()).hexdigest()
    if result.get('report_sha256')!=report_hash:raise ValueError('Report fingerprint changed')
    reviews=result.get('reviews')
    if not isinstance(reviews,list) or not 1<=len(reviews)<=10:raise ValueError('Recorded review required')
    for review in reviews:
        if not isinstance(review,dict) or review.get('report_sha256')!=report_hash or review.get('decision') not in ('reviewed','needs_changes') or not isinstance(review.get('actor'),str) or not review['actor']:
            raise ValueError('Review report binding changed')
        if request.get('require_peer_review') is True and (review.get('second_account_review') is not True or not isinstance(review.get('reviewer_id'),str) or not review['reviewer_id'] or review['reviewer_id']==owner_id):
            raise ValueError('Second-account review record required')
    if reviews[-1]['decision']!=result['state']:raise ValueError('Review state changed')
    return result


def agent_summary(result):
    return {'objective':result['request']['objective'],'review_state':result['state'],
        'review_kind':'second_account' if result['request'].get('require_peer_review') is True else 'standard',
        'report_sha256':result['report_sha256'],'step_count':len(result['steps'])}
