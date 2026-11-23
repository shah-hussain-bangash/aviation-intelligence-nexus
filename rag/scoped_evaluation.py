"""Development-only evaluation of the opt-in scoped excerpt candidate."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
from rag import ollama
from rag.index import ROOT
from rag.scoped_answers import EXPERIMENTS, answer
from rag.service import Knowledge, Question

SUITE = ROOT / 'rag/scoped_cases.json'
CODE = ('rag/scoped_answers.py', 'rag/scoped_evaluation.py', 'rag/service.py', 'rag/ollama.py')


def identities():
    return {p: hashlib.sha256((ROOT / p).read_text(encoding='utf-8').encode()).hexdigest() for p in CODE}


def load_cases(path=SUITE):
    path = Path(path)
    if path.stat().st_size > 100000:raise ValueError('Oversized scoped suite')
    raw = path.read_text(encoding='utf-8'); data = json.loads(raw); cases = data['cases']
    if data['format'] != 'ain-scoped-cases-v1' or not isinstance(cases, list) or not 2 <= len(cases) <= 24:
        raise ValueError('Invalid scoped suite')
    seen = set()
    for c in cases:
        if set(c) != {'id','experiment','kind','question','target_quote'} or not isinstance(c['id'],str) or not c['id'] or c['id'] in seen or c['experiment'] not in EXPERIMENTS or c['kind'] not in ('answerable','outside','conflict'):
            raise ValueError('Invalid scoped label')
        seen.add(c['id']); Question(question=c['question'],generate=False)
        if c['kind'] == 'answerable':
            if not isinstance(c['target_quote'],str) or len(c['target_quote']) < 12 or c['target_quote'] not in (ROOT/EXPERIMENTS[c['experiment']]).read_text(encoding='utf-8'):
                raise ValueError('Invalid scoped target quote')
        elif c['target_quote'] is not None:raise ValueError('Unexpected negative-case quote')
    if not any(c['kind']=='answerable' for c in cases) or not any(c['kind']!='answerable' for c in cases):raise ValueError('Both case groups required')
    return cases, hashlib.sha256(raw.encode()).hexdigest()


def summarize(rows):
    valid = [r for r in rows if r['outcome'] in ('excerpts','abstained')]
    positives = [r for r in valid if r['kind']=='answerable']
    negatives = [r for r in valid if r['kind']!='answerable']
    return {'total_cases':len(rows),'unavailable_or_rejected_cases':len(rows)-len(valid),
            'evaluated_answerable_cases':len(positives),'gold_quote_covered_cases':sum(r['gold_quote_covered'] for r in positives),
            'evaluated_negative_cases':len(negatives),'negative_abstentions':sum(r['outcome']=='abstained' for r in negatives),
            'negative_cases_returning_excerpts':sum(r['outcome']=='excerpts' for r in negatives),
            'answerable_abstentions':sum(r['outcome']=='abstained' for r in positives),
            'verbatim_excerpts':sum(len(r['claims']) for r in rows),
            'wrong_source_excerpts':sum(c['source']!=EXPERIMENTS[r['experiment']] for r in rows for c in r['claims'])}


def evaluate(knowledge=None, suite_path=SUITE, progress=None):
    cases,suite_hash=load_cases(suite_path);knowledge=knowledge or Knowledge()
    index_hash,payload,*_=knowledge.load();corpus={c['id']:c for c in payload['chunks']}
    for c in cases:
        if c['target_quote'] and not any(e['source']==EXPERIMENTS[c['experiment']] and c['target_quote'] in e['text'] for e in corpus.values()):raise ValueError('Target absent from indexed scoped source')
    code=identities(); models=ollama.models();rows=[];started=time.monotonic()
    if not models.get(ollama.CHAT_MODEL) or models.get(ollama.EMBED_MODEL)!=payload['embedding_digest']:raise RuntimeError('Required local models unavailable')
    for c in cases:
        begin=time.monotonic()
        try:r=answer(c['question'],c['experiment'],knowledge)
        except (OSError,RuntimeError):r=None
        if r is not None:
            if r['experiment']!=c['experiment'] or r['source']!=EXPERIMENTS[c['experiment']] or r['index_sha256']!=index_hash or r['generation_digest']!=models[ollama.CHAT_MODEL] or r['embedding_digest']!=models[ollama.EMBED_MODEL]:raise ValueError('Scoped identity mismatch')
            for claim in r['claims']:
                e=corpus.get(claim['citation'])
                if not e or claim['source']!=EXPERIMENTS[c['experiment']] or claim['text']!=claim['quote'] or claim['quote'] not in e['text'] or any(claim[k]!=e[k] for k in ('source','start_line','end_line')):raise ValueError('Invalid verbatim excerpt provenance')
            if r['generation_status']=='unavailable_or_rejected':
                if r['claims'] or r['mode']!='evidence_only':raise ValueError('Contradictory unavailable selection')
                outcome='unavailable_or_rejected'
            elif r['generation_status'] in ('completed','skipped_no_evidence'):
                outcome='excerpts' if r['claims'] else 'abstained'
                if r['mode']!=outcome:raise ValueError('Contradictory scoped outcome')
            else:raise ValueError('Unknown scoped generation status')
        else:outcome='unavailable_or_rejected'
        claims=r['claims'] if r else []
        row={**c,'outcome':outcome,'generation_status':r['generation_status'] if r else 'not_observed',
             'claims':claims,'retrieved':r['retrieved'] if r else [],
             'gold_quote_covered':bool(c['target_quote'] and any(c['target_quote'] in claim['quote'] for claim in claims)),
             'human_review_status':'pending','elapsed_ms':round((time.monotonic()-begin)*1000,2)}
        rows.append(row)
        if progress:progress(row)
    after=ollama.models()
    if knowledge.load()[0]!=index_hash or load_cases(suite_path)[1]!=suite_hash or identities()!=code or any(after.get(m)!=models[m] for m in (ollama.EMBED_MODEL,ollama.CHAT_MODEL)):raise ValueError('Evaluation identities changed')
    return {'format':'ain-scoped-evaluation-v1','checked_at':datetime.now(timezone.utc).isoformat(),
            'scope':'Maintainer-authored development challenges with explicit caller experiment context; two known regressions, no independent held-out accuracy or comparison with earlier unscoped input.',
            'suite_sha256':suite_hash,'index_sha256':index_hash,'corpus_revision':payload['revision'],'sources':payload['sources'],
            'generation_model':ollama.CHAT_MODEL,'generation_digest':models[ollama.CHAT_MODEL],'embedding_digest':models[ollama.EMBED_MODEL],
            'code_sha256':code,'metrics':summarize(rows),'cases':rows,'complete':all(r['outcome']!='unavailable_or_rejected' for r in rows),
            'elapsed_ms':round((time.monotonic()-started)*1000,2),'human_review_complete':False,'semantic_answer_accuracy_measured':False,
            'live_service_changed':False,'operational_approval':False,'production_ready':False}


def run_to_file(output):
    supplied=Path(output);target=supplied.resolve();journal=target.with_suffix(target.suffix+'.progress.jsonl')
    if not target.is_relative_to(ROOT/'.local') or target.exists() or journal.exists() or any(p.is_symlink() for p in (supplied,*supplied.parents)):raise ValueError('Use a new private output; previous reports and journals are retained')
    target.parent.mkdir(parents=True,exist_ok=True)
    with journal.open('x',encoding='utf-8') as stream:
        def record(row):stream.write(json.dumps(row)+'\n');stream.flush();os.fsync(stream.fileno())
        record({'event':'started','suite_sha256':load_cases()[1]})
        try:
            report=evaluate(progress=lambda row:record({'event':'case','result':row}))
            with target.open('x',encoding='utf-8') as final:final.write(json.dumps(report,indent=2)+'\n')
            record({'event':'completed','complete':report['complete']})
        except Exception as error:
            record({'event':'failed','error_type':type(error).__name__});raise
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);args=parser.parse_args()
    r=run_to_file(args.output);print(json.dumps({'metrics':r['metrics'],'complete':r['complete'],'elapsed_ms':r['elapsed_ms'],'production_ready':False}))
    raise SystemExit(0 if r['complete'] else 2)


if __name__=='__main__':main()
