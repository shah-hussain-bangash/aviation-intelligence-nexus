"""Development regression replay and deterministic controls for the explicit scope guard."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import time
from rag import ollama,scope_guard
from rag.index import ROOT
from rag.service import Knowledge
from rag.scoped_evaluation import load_cases,SUITE

CONTROLS=ROOT/'rag/guard_controls.json'
CODE=('rag/scope_guard.py','rag/guard_evaluation.py','rag/scoped_answers.py','rag/scoped_evaluation.py','rag/service.py','rag/ollama.py')


def fingerprints():
    return {p:hashlib.sha256((ROOT/p).read_text(encoding='utf-8').encode()).hexdigest() for p in CODE}


def controls(path=CONTROLS):
    path=Path(path)
    if path.stat().st_size>50000:raise ValueError('Oversized guard controls')
    raw=path.read_text(encoding='utf-8');data=json.loads(raw);cases=data['cases']
    if data['format']!='ain-guard-controls-v1' or not 2<=len(cases)<=32:raise ValueError('Invalid guard controls')
    seen=set();rows=[]
    for c in cases:
        if set(c)!={'id','experiment','question','expected'} or not isinstance(c['id'],str) or not c['id'] or c['id'] in seen or c['expected'] not in ('allow','clarification_required'):raise ValueError('Invalid guard label')
        seen.add(c['id']);observed=scope_guard.decide(c['question'],c['experiment'])
        rows.append({**c,'observed':observed,'passed':observed['decision']==c['expected']})
    return rows,hashlib.sha256(raw.encode()).hexdigest()


def summarize(rows):
    available=[r for r in rows if r['outcome']!='unavailable_or_rejected']
    positive=[r for r in available if r['kind']=='answerable'];negative=[r for r in available if r['kind']!='answerable']
    return {'total_cases':len(rows),'unavailable_or_rejected_cases':len(rows)-len(available),
            'evaluated_answerable_cases':len(positive),'gold_quote_covered_cases':sum(r['gold_quote_covered'] for r in positive),
            'evaluated_negative_cases':len(negative),'negative_abstentions':sum(r['outcome']=='abstained' for r in negative),
            'negative_clarifications':sum(r['outcome']=='clarification_required' for r in negative),
            'negative_cases_returning_excerpts':sum(r['outcome']=='excerpts' for r in negative),
            'answerable_cases_without_excerpts':sum(r['outcome']!='excerpts' for r in positive),
            'candidate_bypassed_cases':sum(not r['candidate_invoked'] for r in rows),
            'verbatim_excerpts':sum(len(r['claims']) for r in rows)}


def evaluate(knowledge=None,suite_path=SUITE,progress=None):
    cases,suite_hash=load_cases(suite_path);control_rows,control_hash=controls();code=fingerprints()
    knowledge=knowledge or Knowledge();index_hash,payload,*_=knowledge.load();corpus={e['id']:e for e in payload['chunks']}
    models=ollama.models()
    if not models.get(ollama.CHAT_MODEL) or models.get(ollama.EMBED_MODEL)!=payload['embedding_digest']:raise RuntimeError('Required local models unavailable')
    for c in cases:
        if c['target_quote'] and not any(e['source']==scope_guard.scoped_answers.EXPERIMENTS[c['experiment']] and c['target_quote'] in e['text'] for e in corpus.values()):raise ValueError('Indexed target absent')
    rows=[];started=time.monotonic()
    for c in cases:
        begin=time.monotonic()
        try:r=scope_guard.answer(c['question'],c['experiment'],knowledge)
        except (OSError,RuntimeError):r=None
        expected=scope_guard.decide(c['question'],c['experiment'])
        if r is None:
            if expected['decision']=='clarification_required':raise ValueError('Guard unexpectedly reached provider')
            outcome='unavailable_or_rejected';claims=[];retrieved=[];invoked=True
        else:
            if r['experiment']!=c['experiment'] or r['source']!=scope_guard.scoped_answers.EXPERIMENTS[c['experiment']] or r['scope_guard']!=expected:raise ValueError('Guard identity mismatch')
            claims,retrieved,invoked=r['claims'],r['retrieved'],r['candidate_invoked']
            if expected['decision']=='clarification_required':
                if r['mode']!='clarification_required' or invoked is not False or claims or retrieved or r['generation_status']!='not_requested_scope_conflict':raise ValueError('Conflict did not stop before candidate')
                outcome='clarification_required'
            else:
                if invoked is not True or r['index_sha256']!=index_hash or r['generation_digest']!=models[ollama.CHAT_MODEL] or r['embedding_digest']!=models[ollama.EMBED_MODEL]:raise ValueError('Candidate identity mismatch')
                for claim in claims:
                    e=corpus.get(claim['citation'])
                    if not e or claim['text']!=claim['quote'] or claim['quote'] not in e['text'] or claim['source']!=r['source'] or any(claim[k]!=e[k] for k in ('source','start_line','end_line')):raise ValueError('Invalid excerpt provenance')
                if r['generation_status']=='unavailable_or_rejected':
                    if claims or r['mode']!='evidence_only':raise ValueError('Contradictory unavailable result')
                    outcome='unavailable_or_rejected'
                elif r['generation_status'] in ('completed','skipped_no_evidence'):
                    outcome='excerpts' if claims else 'abstained'
                    if r['mode']!=outcome:raise ValueError('Contradictory candidate outcome')
                else:raise ValueError('Unknown generation status')
        row={**c,'outcome':outcome,'scope_guard':expected,'candidate_invoked':invoked,'claims':claims,'retrieved':retrieved,
             'gold_quote_covered':bool(c['target_quote'] and any(c['target_quote'] in e['quote'] for e in claims)),
             'human_review_status':'pending','elapsed_ms':round((time.monotonic()-begin)*1000,2)}
        rows.append(row)
        if progress:progress(row)
    after=ollama.models()
    if knowledge.load()[0]!=index_hash or load_cases(suite_path)[1]!=suite_hash or controls()[1]!=control_hash or fingerprints()!=code or any(after.get(m)!=models[m] for m in (ollama.EMBED_MODEL,ollama.CHAT_MODEL)):raise ValueError('Evaluation identities changed')
    return {'format':'ain-guard-evaluation-v1','checked_at':datetime.now(timezone.utc).isoformat(),
            'scope':'Development replay of the previously inspected 12-case suite plus maintainer-authored deterministic guard controls; no independent held-out or comprehensive security evaluation.',
            'suite_sha256':suite_hash,'controls_sha256':control_hash,'code_sha256':code,'index_sha256':index_hash,
            'corpus_revision':payload['revision'],'sources':payload['sources'],'generation_model':ollama.CHAT_MODEL,
            'generation_digest':models[ollama.CHAT_MODEL],'embedding_digest':models[ollama.EMBED_MODEL],
            'metrics':summarize(rows),'cases':rows,'controls':control_rows,'controls_passed':sum(c['passed'] for c in control_rows),
            'complete':all(r['outcome']!='unavailable_or_rejected' for r in rows),'elapsed_ms':round((time.monotonic()-started)*1000,2),
            'semantic_answer_accuracy_measured':False,'human_review_complete':False,'live_service_changed':False,'production_ready':False,'operational_approval':False}


def run_to_file(output):
    supplied=Path(output);target=supplied.resolve();journal=target.with_suffix(target.suffix+'.progress.jsonl')
    if not target.is_relative_to(ROOT/'.local') or target.exists() or journal.exists() or any(p.is_symlink() for p in (supplied,*supplied.parents)):raise ValueError('Use a new private output; retain prior reports and journals')
    target.parent.mkdir(parents=True,exist_ok=True)
    with journal.open('x',encoding='utf-8') as stream:
        def record(row):stream.write(json.dumps(row)+'\n');stream.flush();os.fsync(stream.fileno())
        record({'event':'started','policy':scope_guard.POLICY})
        try:
            report=evaluate(progress=lambda row:record({'event':'case','result':row}))
            with target.open('x',encoding='utf-8') as final:final.write(json.dumps(report,indent=2)+'\n')
            record({'event':'completed','complete':report['complete']})
        except Exception as error:
            record({'event':'failed','error_type':type(error).__name__});raise
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);args=parser.parse_args()
    r=run_to_file(args.output);print(json.dumps({'metrics':r['metrics'],'controls_passed':r['controls_passed'],'controls_total':len(r['controls']),'complete':r['complete'],'elapsed_ms':r['elapsed_ms'],'production_ready':False}))
    raise SystemExit(0 if r['complete'] and r['controls_passed']==len(r['controls']) else 2)


if __name__=='__main__':main()
