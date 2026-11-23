"""Development-only replay of versioned direct-answer excerpt selection."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import time
from rag import ollama,excerpt_v2,scope_guard
from rag.index import ROOT
from rag.service import Knowledge
from rag.scoped_evaluation import load_cases
from rag.guard_evaluation import controls,summarize

SUITE=ROOT/'rag/direct_excerpt_cases.json'
CODE=('rag/excerpt_v2.py','rag/direct_evaluation.py','rag/scope_guard.py','rag/scoped_answers.py',
      'rag/scoped_evaluation.py','rag/guard_evaluation.py','rag/service.py','rag/ollama.py')


def fingerprints():return {p:hashlib.sha256((ROOT/p).read_text(encoding='utf-8').encode()).hexdigest() for p in CODE}


def inspect(result,case,corpus,index_hash,models):
    decision=scope_guard.decide(case['question'],case['experiment'])
    source=excerpt_v2.v1.EXPERIMENTS[case['experiment']]
    if result['experiment']!=case['experiment'] or result['source']!=source or result['selector_version']!='direct-excerpts-v2' or result['scope_guard']!=decision:raise ValueError('Unexpected candidate identity')
    if decision['decision']=='clarification_required':
        if result['candidate_invoked'] is not False or result['mode']!='clarification_required' or result['claims'] or result['retrieved'] or result['generation_status']!='not_requested_scope_conflict':raise ValueError('Invalid conflict bypass')
        return 'clarification_required'
    if result['candidate_invoked'] is not True or result['index_sha256']!=index_hash or result['generation_digest']!=models[ollama.CHAT_MODEL] or result['embedding_digest']!=models[ollama.EMBED_MODEL] or result['selector_prompt_sha256']!=hashlib.sha256(excerpt_v2.SYSTEM.encode()).hexdigest():raise ValueError('Changed model, corpus or prompt')
    if not isinstance(result['claims'],list) or len(result['claims'])>3:raise ValueError('Invalid excerpt count')
    for claim in result['claims']:
        original=corpus.get(claim['citation'])
        if not original or claim['text']!=claim['quote'] or not 20<=len(claim['quote'])<=400 or claim['quote'] not in original['text'] or claim['source']!=source or any(claim[k]!=original[k] for k in ('source','start_line','end_line')):raise ValueError('Invalid excerpt provenance')
    status=result['generation_status'];mode=result['mode']
    if status=='unavailable_or_rejected':
        if result['claims'] or mode!='evidence_only':raise ValueError('Contradictory unavailable answer')
        return 'unavailable_or_rejected'
    if status not in ('completed','skipped_no_evidence'):raise ValueError('Unknown selector status')
    outcome='excerpts' if result['claims'] else 'abstained'
    if mode!=outcome or (status=='skipped_no_evidence' and (result['claims'] or result['retrieved'])):raise ValueError('Contradictory answer')
    return outcome


def evaluate(knowledge=None,suite_path=SUITE,progress=None):
    cases,suite_hash=load_cases(suite_path);control_rows,control_hash=controls();code=fingerprints()
    knowledge=knowledge or Knowledge();index_hash,payload,*_=knowledge.load();corpus={c['id']:c for c in payload['chunks']};models=ollama.models()
    if not models.get(ollama.CHAT_MODEL) or models.get(ollama.EMBED_MODEL)!=payload['embedding_digest']:raise RuntimeError('Required local models unavailable')
    if any(not any(e['source']==excerpt_v2.v1.EXPERIMENTS[c['experiment']] and c['target_quote'] in e['text'] for e in corpus.values()) for c in cases if c['target_quote']):raise ValueError('Indexed gold target absent')
    rows=[];started=time.monotonic()
    for c in cases:
        begin=time.monotonic()
        try:r=excerpt_v2.answer(c['question'],c['experiment'],knowledge)
        except (OSError,RuntimeError):r=None
        if r is None:
            if scope_guard.decide(c['question'],c['experiment'])['decision']=='clarification_required':raise ValueError('Conflict reached provider')
            outcome='unavailable_or_rejected';claims=[];retrieved=[];invoked=True
        else:
            outcome=inspect(r,c,corpus,index_hash,models);claims=r['claims'];retrieved=r['retrieved'];invoked=r['candidate_invoked']
        row={**c,'outcome':outcome,'scope_guard':scope_guard.decide(c['question'],c['experiment']),
             'candidate_invoked':invoked,'claims':claims,'retrieved':retrieved,
             'gold_quote_covered':bool(c['target_quote'] and any(c['target_quote'] in e['quote'] for e in claims)),
             'human_review_status':'pending','elapsed_ms':round((time.monotonic()-begin)*1000,2)}
        rows.append(row)
        if progress:progress(row)
    after=ollama.models()
    if knowledge.load()[0]!=index_hash or load_cases(suite_path)[1]!=suite_hash or controls()[1]!=control_hash or fingerprints()!=code or any(after.get(m)!=models[m] for m in (ollama.EMBED_MODEL,ollama.CHAT_MODEL)):raise ValueError('Evaluation identities changed')
    return {'format':'ain-direct-evaluation-v2','checked_at':datetime.now(timezone.utc).isoformat(),
            'scope':'Prompt revised after a known miss. Twelve inspected regressions plus four maintainer-authored reason cases; no independent held-out, semantic accuracy or security claim.',
            'suite_sha256':suite_hash,'controls_sha256':control_hash,'code_sha256':code,'index_sha256':index_hash,
            'corpus_revision':payload['revision'],'sources':payload['sources'],'generation_model':ollama.CHAT_MODEL,
            'generation_digest':models[ollama.CHAT_MODEL],'embedding_digest':models[ollama.EMBED_MODEL],
            'selector_prompt_sha256':hashlib.sha256(excerpt_v2.SYSTEM.encode()).hexdigest(),
            'metrics':summarize(rows),'cases':rows,'controls_passed':sum(r['passed'] for r in control_rows),'controls':control_rows,
            'complete':all(r['outcome']!='unavailable_or_rejected' for r in rows),'elapsed_ms':round((time.monotonic()-started)*1000,2),
            'human_review_complete':False,'semantic_answer_accuracy_measured':False,'live_service_changed':False,'production_ready':False,'operational_approval':False}


def run_to_file(output):
    supplied=Path(output);target=supplied.resolve();journal=target.with_suffix(target.suffix+'.progress.jsonl')
    if not target.is_relative_to(ROOT/'.local') or target.exists() or journal.exists() or any(p.is_symlink() for p in (supplied,*supplied.parents)):raise ValueError('Use a new private output; retain previous reports/journals')
    target.parent.mkdir(parents=True,exist_ok=True)
    with journal.open('x',encoding='utf-8') as stream:
        def record(row):stream.write(json.dumps(row)+'\n');stream.flush();os.fsync(stream.fileno())
        record({'event':'started','selector_version':'direct-excerpts-v2'})
        try:
            report=evaluate(progress=lambda row:record({'event':'case','result':row}))
            with target.open('x',encoding='utf-8') as final:final.write(json.dumps(report,indent=2)+'\n')
            record({'event':'completed','complete':report['complete']})
        except Exception as error:
            record({'event':'failed','error_type':type(error).__name__});raise
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);args=parser.parse_args();r=run_to_file(args.output)
    print(json.dumps({'metrics':r['metrics'],'complete':r['complete'],'controls_passed':r['controls_passed'],'elapsed_ms':r['elapsed_ms'],'production_ready':False}))
    raise SystemExit(0 if r['complete'] and r['controls_passed']==len(r['controls']) else 2)


if __name__=='__main__':main()
