"""Deterministic source-context replay of a frozen model run, not new inference."""
import argparse
from copy import deepcopy
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import time
from rag.index import ROOT
from rag.service import Knowledge
from rag.context_excerpts import enrich,POLICY
from rag.scoped_answers import EXPERIMENTS
from rag.guard_evaluation import summarize

BASELINE=ROOT/'docs/reports/Direct_Excerpt_v2_First.json'
BASELINE_SHA256='f8ca85ea79e5f4ea14f2593e893b3be2367906900cfdcc76e8475988aec658e6'
CODE=('rag/context_excerpts.py','rag/context_replay.py')


def fingerprints():return {p:hashlib.sha256((ROOT/p).read_text(encoding='utf-8').encode()).hexdigest() for p in CODE}


def baseline():
    if BASELINE.is_symlink() or BASELINE.stat().st_size>200000:raise ValueError('Unavailable frozen baseline')
    raw=BASELINE.read_text(encoding='utf-8')
    if hashlib.sha256(raw.encode()).hexdigest()!=BASELINE_SHA256:raise ValueError('Frozen baseline changed')
    report=json.loads(raw)
    if report['format']!='ain-direct-evaluation-v2' or report['metrics']!=summarize(report['cases']):raise ValueError('Invalid baseline arithmetic')
    return report


def replay(knowledge=None):
    before=baseline();knowledge=knowledge or Knowledge();index_hash,payload,*_=knowledge.load();code=fingerprints()
    if before['index_sha256']!=index_hash or before['sources']!=payload['sources']:raise ValueError('Replay corpus differs from frozen run')
    corpus={p['id']:p for p in payload['chunks']};rows=deepcopy(before['cases']);started=time.monotonic();count=0
    for row in rows:
        row['original_claims']=deepcopy(row['claims'])
        row['claims'],added=enrich(row['question'],row['claims'],corpus,EXPERIMENTS[row['experiment']])
        row['context_added_count']=added;count+=added
        row['gold_quote_covered']=bool(row['target_quote'] and any(row['target_quote'] in c['quote'] for c in row['claims']))
        row.pop('elapsed_ms',None)
    if knowledge.load()[0]!=index_hash or baseline()!=before or fingerprints()!=code:raise ValueError('Replay identities changed')
    return {'format':'ain-context-replay-v1','checked_at':datetime.now(timezone.utc).isoformat(),
            'scope':'Deterministic context enrichment of saved v2 selections on inspected development cases; not fresh model inference, held-out accuracy or semantic acceptance.',
            'baseline_sha256':BASELINE_SHA256,'suite_sha256':before['suite_sha256'],'context_policy':POLICY,'code_sha256':code,
            'index_sha256':index_hash,'corpus_revision':payload['revision'],'sources':payload['sources'],
            'metrics_before':before['metrics'],'metrics_after':summarize(rows),'cases':rows,'context_added_count':count,
            'generation_calls_in_this_replay':0,'replay_elapsed_ms':round((time.monotonic()-started)*1000,2),
            'human_review_complete':False,'semantic_answer_accuracy_measured':False,'live_service_changed':False,'operational_approval':False,'production_ready':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);args=parser.parse_args()
    supplied=Path(args.output);target=supplied.resolve()
    if not target.is_relative_to(ROOT/'.local') or target.exists() or any(p.is_symlink() for p in (supplied,*supplied.parents)):raise ValueError('Use a new private output')
    r=replay();target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('x',encoding='utf-8') as stream:stream.write(json.dumps(r,indent=2)+'\n')
    print(json.dumps({'metrics_before':r['metrics_before'],'metrics_after':r['metrics_after'],'context_added_count':r['context_added_count'],'generation_calls_in_this_replay':0,'production_ready':False}))


if __name__=='__main__':main()
