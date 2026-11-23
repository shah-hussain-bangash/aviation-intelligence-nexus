"""Conservative lexical source coverage before the opt-in context excerpt workflow."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import unicodedata
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS
from rag import scope_guard,context_excerpts
from rag.index import ROOT
from rag.service import Knowledge,Question
from rag.scoped_answers import EXPERIMENTS

POLICY='long-content-term-coverage-v1'
GENERIC=frozenset({'describe','description','explain','explanation','individual','particular','please',
                   'provide','provided','question','requested','research','selection','supplied','understand','information'})


def words(text):
    result=set()
    for word in re.findall(r'[a-z]+',unicodedata.normalize('NFKC',text).casefold()):
        if word in ENGLISH_STOP_WORDS or word in GENERIC:continue
        if len(word)>5:
            if word.endswith('ies'):word=word[:-3]+'y'
            elif word.endswith('s') and not word.endswith('ss'):word=word[:-1]
        result.add(word)
    return result


def assess(question,document):
    question=Question(question=question,generate=False).question
    required=sorted(word for word in words(question) if len(word)>=8)
    vocabulary=words(document);missing=sorted(set(required)-vocabulary)
    return {'policy':POLICY,'decision':'decline' if missing else 'allow','required_terms':required,
            'missing_terms':missing,'matched_terms':sorted(set(required)&vocabulary),
            'vocabulary_sha256':hashlib.sha256(json.dumps(sorted(vocabulary),separators=(',',':')).encode()).hexdigest(),
            'interpretation':'Lexical coverage only; presence does not establish answerability and absence may be a valid paraphrase.'}


def answer(question,experiment,knowledge=None):
    request=Question(question=question,generate=False);guard=scope_guard.decide(request.question,experiment)
    if guard['decision']=='clarification_required':
        return {**scope_guard.answer(request.question,experiment,knowledge),'format':'ain-source-coverage-v1',
                'source_coverage':{'policy':POLICY,'decision':'not_checked_scope_conflict'}}
    knowledge=knowledge or Knowledge();index_hash,payload,*_=knowledge.load();source=EXPERIMENTS[experiment]
    passages=[p for p in payload['chunks'] if p['source']==source]
    if not passages:raise ValueError('Selected source absent from trusted index')
    coverage=assess(request.question,'\n'.join(p['text'] for p in passages))
    if coverage['decision']=='decline':
        result={'format':'ain-source-coverage-v1','question':request.question,'experiment':experiment,'source':source,
                'index_sha256':index_hash,'corpus_revision':payload['revision'],'mode':'source_coverage_declined',
                'claims':[],'retrieved':[],'scope_guard':guard,'source_coverage':coverage,'candidate_invoked':False,
                'generation_status':'not_requested_source_coverage','context_added_count':0,
                'message':'The selected source does not cover all required long content terms. Rephrase or provide an authorized source; no model answer was requested.',
                'live_service_changed':False,'human_review_complete':False,'operational_approval':False,'production_ready':False}
    else:
        result=context_excerpts.answer(request.question,experiment,knowledge)
        if result['index_sha256']!=index_hash:raise ValueError('Index changed before candidate answer')
        result={**result,'format':'ain-source-coverage-v1','source_coverage':coverage}
    if knowledge.load()[0]!=index_hash:raise ValueError('Index changed during source coverage')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--experiment',choices=EXPERIMENTS,required=True)
    parser.add_argument('--question',required=True);parser.add_argument('--output',required=True);args=parser.parse_args()
    supplied=Path(args.output);target=supplied.resolve()
    if not target.is_relative_to(ROOT/'.local') or target.exists() or any(p.is_symlink() for p in (supplied,*supplied.parents)):raise ValueError('Use a new private output')
    result=answer(args.question,args.experiment);target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('x',encoding='utf-8') as stream:stream.write(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'mode':result['mode'],'candidate_invoked':result['candidate_invoked'],'source_coverage':result['source_coverage']['decision'],'production_ready':False}))


if __name__=='__main__':main()
