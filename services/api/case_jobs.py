"""Owner-only job submission with primary-then-case lock ordering; no case mutation."""
from contextlib import closing,contextmanager
import json
import sqlite3
from pydantic import BaseModel,ConfigDict,Field,model_validator
from agents.runtime import Investigation
from agents.case_context import checked_context
from agents.store import Conflict
from services.api.research_cases import CaseConflict,CaseMissing,digest


class CaseInvestigation(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_version:int=Field(strict=True,ge=1,le=100)
    investigation:Investigation

    @model_validator(mode='after')
    def private_case(self):
        if self.investigation.require_peer_review:raise ValueError('Case-bound report sharing is not enabled')
        return self


class CaseJobs:
    def __init__(self,cases):self.cases=cases

    @contextmanager
    def context(self,primary,user,case_id,version,prior=None):
        account=primary.execute('SELECT role,active FROM auth_users WHERE id=?',(user['id'],)).fetchone()
        if not account or not account['active'] or account['role'] not in ('admin','researcher'):raise PermissionError('Researcher access required')
        if prior is not None:
            if 'case_context' not in prior.get('request',{}):raise CaseConflict('Request belongs to an unbound investigation')
            context=checked_context(prior['request'].get('case_context'))
            if context['case_id']!=str(case_id) or context['case_version']!=version:raise CaseConflict('Request belongs to another case version')
            yield context;return
        if not self.cases.case_database.is_file():raise sqlite3.OperationalError('Case store unavailable')
        with closing(self.cases.connect()) as db,db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM cases WHERE id=? AND owner_id=?',(str(case_id),user['id'])).fetchone()
            if row is None:raise CaseMissing('Case unavailable')
            case=self.cases.projection(db,row)
            if case['status']!='open' or case['version']!=version:raise CaseConflict('Case closed or version changed')
            yield checked_context({'case_id':case['id'],'case_version':case['version'],'case_sha256':digest(case),
                'source_run_id':case['source_run_id'],'source_sha256':case['source_sha256'],'title':case['title'],'scope':case['scope']})

    def submission(self,user,case_id,request):
        return lambda primary,prior:self.context(primary,user,case_id,request.expected_version,prior)

    @contextmanager
    def claim_context(self,primary,user,value):
        context=checked_context(value)
        with self.context(primary,user,context['case_id'],context['case_version']) as current:
            if current!=context:raise CaseConflict('Captured case context changed')
            yield current

    def recent(self,user,case_id,store):
        self.cases.get(user,case_id) # Owner-only, even for administrators.
        with closing(store.connection()) as db:
            rows=db.execute("SELECT result_json FROM agent_runs WHERE owner_id=? AND json_extract(result_json,'$.request.case_context.case_id')=? ORDER BY rowid DESC LIMIT 10",(user['id'],str(case_id))).fetchall()
        result=[]
        for row in rows:
            run=json.loads(row['result_json']);context=checked_context(run['request']['case_context'])
            result.append({'run_id':run['run_id'],'state':run['state'],'case_context':context,'updated_at':run['updated_at']})
        return {'jobs':result,'production_ready':False}
