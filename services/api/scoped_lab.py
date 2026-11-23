"""Strict public projection for the opt-in unsaved scoped research query."""
import re
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,field_validator
from rag import scope_guard,source_coverage


class ScopedLabQuery(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,str_strip_whitespace=True)
    question:str=Field(min_length=8,max_length=600)
    experiment:Literal['delay-v1','delay-v2']
    acknowledged:bool=Field(strict=True)

    @field_validator('acknowledged')
    @classmethod
    def require_acknowledgment(cls,value):
        if value is not True:raise ValueError('Acknowledge the research limitations')
        return value


def project_result(raw,query):
    source=source_coverage.EXPERIMENTS[query.experiment];guard=scope_guard.decide(query.question,query.experiment)
    if raw['question']!=query.question or raw['experiment']!=query.experiment or raw['source']!=source or raw['scope_guard']!=guard or any(raw[k] is not False for k in ('human_review_complete','operational_approval','production_ready')):
        raise ValueError('Unexpected query identity or scope')
    mode,status,claims=raw['mode'],raw['generation_status'],raw['claims']
    coverage=raw['source_coverage'];public_coverage={'decision':coverage['decision'],'required_terms':[],'missing_terms':[],'matched_terms':[]}
    if guard['decision']=='clarification_required':
        if mode!='clarification_required' or status!='not_requested_scope_conflict' or raw['candidate_invoked'] is not False or claims or raw['retrieved'] or coverage!={'policy':source_coverage.POLICY,'decision':'not_checked_scope_conflict'}:raise ValueError('Invalid scope refusal')
        revision=None
    else:
        if coverage['policy']!=source_coverage.POLICY or not re.fullmatch('[a-f0-9]{64}',coverage['vocabulary_sha256']):raise ValueError('Invalid vocabulary identity')
        required=sorted(w for w in source_coverage.words(query.question) if len(w)>=8)
        missing,matched=coverage['missing_terms'],coverage['matched_terms']
        if coverage['required_terms']!=required or any(not isinstance(group,list) or group!=sorted(set(group)) or any(w not in required for w in group) for group in (missing,matched)) or set(missing)&set(matched) or sorted(missing+matched)!=required or coverage['decision']!=('decline' if missing else 'allow'):raise ValueError('Contradictory source coverage')
        public_coverage.update(required_terms=required,missing_terms=missing,matched_terms=matched)
        revision=raw['corpus_revision']
        if not isinstance(revision,str) or not re.fullmatch('[a-f0-9]{40}',revision) or not re.fullmatch('[a-f0-9]{64}',raw['index_sha256']):raise ValueError('Invalid corpus identity')
        if missing:
            if mode!='source_coverage_declined' or status!='not_requested_source_coverage' or raw['candidate_invoked'] is not False or claims or raw['retrieved']:raise ValueError('Invalid vocabulary refusal')
        else:
            if raw['candidate_invoked'] is not True:raise ValueError('Invalid candidate state')
            if mode=='excerpts':
                if status!='completed' or not claims:raise ValueError('Invalid excerpt outcome')
            elif mode=='abstained':
                if status not in ('completed','skipped_no_evidence') or claims:raise ValueError('Invalid abstention')
            elif mode=='evidence_only':
                if status!='unavailable_or_rejected' or claims:raise ValueError('Unavailable is not abstention')
            else:raise ValueError('Unknown candidate outcome')
    if not isinstance(claims,list) or len(claims)>3:raise ValueError('Invalid excerpt count')
    public=[]
    for c in claims:
        if not isinstance(c['quote'],str) or not 20<=len(c['quote'])<=400 or c['text']!=c['quote'] or c['source']!=source or not re.fullmatch('[a-f0-9]{20}',c['citation']) or type(c['start_line']) is not int or type(c['end_line']) is not int or not 1<=c['start_line']<=c['end_line']<=100000:raise ValueError('Invalid excerpt identity')
        public.append({k:c[k] for k in ('text','quote','citation','source','start_line','end_line')})
    added=raw.get('context_added_count',0)
    if type(added) is not int or not 0<=added<=len(public):raise ValueError('Invalid context count')
    return {'format':'ain-scoped-lab-v1','question':query.question,'experiment':query.experiment,'source':source,
            'mode':mode,'generation_status':status,'scope_guard':{k:guard[k] for k in ('decision','reason','mentioned_experiments')},
            'coverage':public_coverage,'corpus_revision':revision,'claims':public,'context_added_count':added,
            'saved_to_history':False,'human_review_complete':False,'operational_approval':False,'production_ready':False}


def run(query,knowledge):
    return project_result(source_coverage.answer(query.question,query.experiment,knowledge),query)
