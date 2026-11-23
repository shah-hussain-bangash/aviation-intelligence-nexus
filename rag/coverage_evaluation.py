"""Development evaluation of conservative source coverage, including false refusals."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import time
from rag import source_coverage as sc,scope_guard,ollama
from rag.index import ROOT
from rag.service import Knowledge
from rag.scoped_evaluation import load_cases
from rag.guard_evaluation import controls as scope_controls

SUITE=ROOT/'rag/coverage_cases.json'
CONTROLS=ROOT/'rag/coverage_controls.json'
CODE=('rag/source_coverage.py','rag/coverage_evaluation.py','rag/context_excerpts.py','rag/excerpt_v2.py',
      'rag/scope_guard.py','rag/scoped_answers.py','rag/scoped_evaluation.py','rag/guard_evaluation.py','rag/service.py','rag/ollama.py')


def fingerprints():return {p:hashlib.sha256((ROOT/p).read_text(encoding='utf-8').encode()).hexdigest() for p in CODE}


def controls(path=CONTROLS):
    path=Path(path)
    if path.stat().st_size>50000:raise ValueError('Oversized coverage controls')
    raw=path.read_text(encoding='utf-8');data=json.loads(raw);rows=[];seen=set()
    if data['format']!='ain-coverage-controls-v1' or not 2<=len(data['cases'])<=32:raise ValueError('Invalid coverage controls')
    for c in data['cases']:
        if set(c)!={'id','question','document','expected','source_answerable'} or not isinstance(c['id'],str) or not c['id'] or c['id'] in seen or c['expected'] not in ('allow','decline') or type(c['source_answerable']) is not bool or not isinstance(c['document'],str) or len(c['document'])>5000:raise ValueError('Invalid coverage control')
        seen.add(c['id']);decision=sc.assess(c['question'],c['document'])
        rows.append({**c,'observed':decision,'passed':decision['decision']==c['expected']})
    return rows,hashlib.sha256(raw.encode()).hexdigest()


def summarize(rows):
    valid=[r for r in rows if r['outcome']!='unavailable_or_rejected'];positive=[r for r in valid if r['kind']=='answerable'];negative=[r for r in valid if r['kind']!='answerable']
    return {'total_cases':len(rows),'unavailable_or_rejected_cases':len(rows)-len(valid),
            'evaluated_answerable_cases':len(positive),'gold_quote_covered_cases':sum(r['gold_quote_covered'] for r in positive),
            'answerable_coverage_refusals':sum(r['outcome']=='source_coverage_declined' for r in positive),
            'evaluated_negative_cases':len(negative),'negative_model_abstentions':sum(r['outcome']=='abstained' for r in negative),
            'negative_scope_clarifications':sum(r['outcome']=='clarification_required' for r in negative),
            'negative_coverage_refusals':sum(r['outcome']=='source_coverage_declined' for r in negative),
            'negative_cases_returning_excerpts':sum(r['outcome']=='excerpts' for r in negative),
            'candidate_bypassed_cases':sum(not r['candidate_invoked'] for r in rows),'verbatim_excerpts':sum(len(r['claims']) for r in rows)}


def inspect(r,c,payload,index_hash,models):
    guard=scope_guard.decide(c['question'],c['experiment']);source=sc.EXPERIMENTS[c['experiment']]
    if r['experiment']!=c['experiment'] or r['source']!=source or r['scope_guard']!=guard:raise ValueError('Wrong experiment identity')
    if guard['decision']=='clarification_required':
        if r['mode']!='clarification_required' or r['candidate_invoked'] is not False or r['claims'] or r['retrieved'] or r['source_coverage']!={'policy':sc.POLICY,'decision':'not_checked_scope_conflict'}:raise ValueError('Invalid scope bypass')
        return 'clarification_required'
    document='\n'.join(p['text'] for p in payload['chunks'] if p['source']==source)
    expected=sc.assess(c['question'],document)
    if r['source_coverage']!=expected or r['index_sha256']!=index_hash:raise ValueError('Coverage source or arithmetic changed')
    if expected['decision']=='decline':
        if r['mode']!='source_coverage_declined' or r['candidate_invoked'] is not False or r['claims'] or r['retrieved'] or r['generation_status']!='not_requested_source_coverage':raise ValueError('Coverage refusal did not bypass candidate')
        return 'source_coverage_declined'
    if r['candidate_invoked'] is not True or r['generation_digest']!=models[ollama.CHAT_MODEL] or r['embedding_digest']!=models[ollama.EMBED_MODEL]:raise ValueError('Changed provider identity')
    corpus={p['id']:p for p in payload['chunks']}
    if not isinstance(r['claims'],list) or len(r['claims'])>3:raise ValueError('Invalid claim count')
    for claim in r['claims']:
        p=corpus.get(claim['citation'])
        if not p or claim['text']!=claim['quote'] or not 20<=len(claim['quote'])<=400 or claim['quote'] not in p['text'] or claim['source']!=source or any(claim[k]!=p[k] for k in ('source','start_line','end_line')):raise ValueError('Invalid source excerpt')
    if r['generation_status']=='unavailable_or_rejected':
        if r['claims'] or r['mode']!='evidence_only':raise ValueError('Contradictory unavailable generation')
        return 'unavailable_or_rejected'
    if r['generation_status'] not in ('completed','skipped_no_evidence'):raise ValueError('Unknown generation status')
    outcome='excerpts' if r['claims'] else 'abstained'
    if r['mode']!=outcome:raise ValueError('Contradictory outcome')
    return outcome


def evaluate(knowledge=None,suite_path=SUITE,progress=None):
    cases,suite_hash=load_cases(suite_path);control_rows,control_hash=controls();scope_rows,scope_hash=scope_controls();code=fingerprints()
    knowledge=knowledge or Knowledge();index_hash,payload,*_=knowledge.load();models=ollama.models()
    if not models.get(ollama.CHAT_MODEL) or models.get(ollama.EMBED_MODEL)!=payload['embedding_digest']:raise RuntimeError('Required local models unavailable')
    for c in cases:
        if c['target_quote'] and not any(p['source']==sc.EXPERIMENTS[c['experiment']] and c['target_quote'] in p['text'] for p in payload['chunks']):raise ValueError('Indexed target missing')
    rows=[];started=time.monotonic()
    for c in cases:
        begin=time.monotonic()
        try:r=sc.answer(c['question'],c['experiment'],knowledge)
        except (OSError,RuntimeError):r=None
        if r is None:
            guard=scope_guard.decide(c['question'],c['experiment']);document='\n'.join(p['text'] for p in payload['chunks'] if p['source']==sc.EXPERIMENTS[c['experiment']])
            if guard['decision']=='clarification_required' or sc.assess(c['question'],document)['decision']=='decline':raise ValueError('Deterministic refusal unexpectedly reached provider')
            outcome='unavailable_or_rejected';claims=[];invoked=True;coverage=None
        else:outcome=inspect(r,c,payload,index_hash,models);claims=r['claims'];invoked=r['candidate_invoked'];coverage=r['source_coverage']
        row={**c,'outcome':outcome,'source_coverage':coverage,'candidate_invoked':invoked,
             'claims':claims,'gold_quote_covered':bool(c['target_quote'] and any(c['target_quote'] in p['quote'] for p in claims)),
             'human_review_status':'pending','elapsed_ms':round((time.monotonic()-begin)*1000,2)}
        rows.append(row)
        if progress:progress(row)
    after=ollama.models()
    if knowledge.load()[0]!=index_hash or load_cases(suite_path)[1]!=suite_hash or controls()[1]!=control_hash or scope_controls()[1]!=scope_hash or fingerprints()!=code or any(after.get(m)!=models[m] for m in (ollama.EMBED_MODEL,ollama.CHAT_MODEL)):raise ValueError('Evaluation identity changed')
    return {'format':'ain-source-coverage-evaluation-v1','checked_at':datetime.now(timezone.utc).isoformat(),
            'scope':'Development replay and two additional probes. Conservative lexical coverage is not semantic answerability; false refusals and blind spots are retained.',
            'suite_sha256':suite_hash,'coverage_controls_sha256':control_hash,'scope_controls_sha256':scope_hash,
            'code_sha256':code,'index_sha256':index_hash,'sources':payload['sources'],'corpus_revision':payload['revision'],
            'generation_model':ollama.CHAT_MODEL,'generation_digest':models[ollama.CHAT_MODEL],'embedding_digest':models[ollama.EMBED_MODEL],
            'metrics':summarize(rows),'cases':rows,'coverage_controls':control_rows,'coverage_controls_passed':sum(r['passed'] for r in control_rows),
            'scope_controls_passed':sum(r['passed'] for r in scope_rows),'complete':all(r['outcome']!='unavailable_or_rejected' for r in rows),
            'elapsed_ms':round((time.monotonic()-started)*1000,2),'human_review_complete':False,'semantic_answer_accuracy_measured':False,
            'live_service_changed':False,'production_ready':False,'operational_approval':False}


def run_to_file(output):
    supplied=Path(output);target=supplied.resolve();journal=target.with_suffix(target.suffix+'.progress.jsonl')
    if not target.is_relative_to(ROOT/'.local') or target.exists() or journal.exists() or any(p.is_symlink() for p in (supplied,*supplied.parents)):raise ValueError('Use new private output and retain earlier reports/journals')
    target.parent.mkdir(parents=True,exist_ok=True)
    with journal.open('x',encoding='utf-8') as stream:
        def record(row):stream.write(json.dumps(row)+'\n');stream.flush();os.fsync(stream.fileno())
        record({'event':'started','policy':sc.POLICY})
        try:
            r=evaluate(progress=lambda row:record({'event':'case','result':row}))
            with target.open('x',encoding='utf-8') as final:final.write(json.dumps(r,indent=2)+'\n')
            record({'event':'completed','complete':r['complete']})
        except Exception as error:
            record({'event':'failed','error_type':type(error).__name__});raise
    return r


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);args=parser.parse_args();r=run_to_file(args.output)
    print(json.dumps({'metrics':r['metrics'],'coverage_controls_passed':r['coverage_controls_passed'],'scope_controls_passed':r['scope_controls_passed'],'complete':r['complete'],'elapsed_ms':r['elapsed_ms'],'production_ready':False}))
    raise SystemExit(0 if r['complete'] and r['coverage_controls_passed']==len(r['coverage_controls']) else 2)


if __name__=='__main__':main()
