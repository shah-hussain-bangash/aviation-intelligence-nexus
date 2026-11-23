"""Bounded preceding-sentence context for explanatory excerpt questions; research only."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import re
from rag import excerpt_v2
from rag.index import ROOT
from rag.service import Knowledge

POLICY='preceding-sentence-context-v1'


def enrich(question,claims,corpus,source):
    explanatory=bool(re.search(r'^\s*(?:why|explain)\b|\b(?:reason|rationale|explanation)\b',question,re.I))
    result=[];added=0
    for original in claims:
        claim=deepcopy(original);passage=corpus.get(claim['citation'])
        if passage is None or claim['text']!=claim['quote'] or not 20<=len(claim['quote'])<=400 or claim['quote'] not in passage['text'] or claim['source']!=source or any(claim[k]!=passage[k] for k in ('source','start_line','end_line')):
            raise ValueError('Unverified selected excerpt')
        text=passage['text'];quote=claim['quote']
        if explanatory and text.count(quote)==1:
            start=text.index(quote)
            breaks=list(re.finditer(r'\n[ \t]*\n',text[:start]))
            paragraph_start=breaks[-1].end() if breaks else 0
            before=text[paragraph_start:start].rstrip()
            if before:
                boundaries=list(re.finditer(r'(?<=[.!?])\s+',before))
                previous_start=paragraph_start+(boundaries[-1].end() if boundaries else 0)
                candidate=text[previous_start:start+len(quote)]
                if 20<=len(candidate)<=400 and candidate!=quote:
                    claim['text']=claim['quote']=candidate;added+=1
        result.append(claim)
    return result,added


def answer(question,experiment,knowledge=None):
    knowledge=knowledge or Knowledge();result=excerpt_v2.answer(question,experiment,knowledge)
    original=deepcopy(result['claims']);count=0
    if result['claims']:
        index_hash,payload,*_=knowledge.load()
        if result['index_sha256']!=index_hash:raise ValueError('Index changed before context enrichment')
        result['claims'],count=enrich(result['question'],result['claims'],{p['id']:p for p in payload['chunks']},result['source'])
        if knowledge.load()[0]!=index_hash:raise ValueError('Index changed during context enrichment')
    return {**result,'format':'ain-context-excerpts-v1','context_policy':POLICY,'context_added_count':count,
            'original_claims':original,'answer_style':'Verbatim selected excerpts with bounded source context; relevance requires review'}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--experiment',choices=excerpt_v2.v1.EXPERIMENTS,required=True)
    parser.add_argument('--question',required=True);parser.add_argument('--output',required=True);args=parser.parse_args()
    supplied=Path(args.output);target=supplied.resolve()
    if not target.is_relative_to(ROOT/'.local') or target.exists() or any(p.is_symlink() for p in (supplied,*supplied.parents)):raise ValueError('Use a new private output')
    result=answer(args.question,args.experiment);target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('x',encoding='utf-8') as stream:stream.write(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'mode':result['mode'],'context_added_count':result['context_added_count'],'production_ready':False}))


if __name__=='__main__':main()
