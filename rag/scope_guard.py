"""Conservative explicit-version clarification before the opt-in excerpt candidate."""
import argparse
import json
from pathlib import Path
import re
import unicodedata
from rag.index import ROOT
from rag.service import Question
from rag import scoped_answers

POLICY = 'explicit-experiment-guard-v1'


def decide(question, experiment):
    if experiment not in scoped_answers.EXPERIMENTS:
        raise ValueError('Choose delay-v1 or delay-v2 explicitly')
    question = Question(question=question, generate=False).question
    normalized = unicodedata.normalize('NFKC', question).casefold()
    normalized = normalized.translate(str.maketrans({'–':'-', '—':'-', '−':'-'}))
    versions = set(re.findall(r'(?<!\w)(?:delay[\s_-]*)?(?:version|v)[\s_-]*(\d{1,3})(?!\w)', normalized))
    for ordinal, number in [('first','1'), ('second','2')]:
        if re.search(r'\b'+ordinal+r'\s+(?:(?:delay|logistic)\s+)?(?:experiment|model|baseline)\b', normalized):
            versions.add(number)
    mentioned = sorted('delay-v'+number for number in versions)
    unsupported = any(number not in ('1','2') for number in versions)
    conflict = any('delay-v'+number != experiment for number in versions)
    return {'policy':POLICY,'decision':'clarification_required' if unsupported or conflict else 'allow',
            'reason':'unsupported_explicit_version' if unsupported else 'conflicting_explicit_version' if conflict else 'no_explicit_conflict',
            'mentioned_experiments':mentioned}


def answer(question, experiment, knowledge=None):
    question = Question(question=question, generate=False).question
    guard = decide(question, experiment)
    if guard['decision'] == 'clarification_required':
        return {'format':'ain-guarded-excerpts-v1','question':question,'experiment':experiment,
                'source':scoped_answers.EXPERIMENTS[experiment],'mode':'clarification_required',
                'claims':[],'retrieved':[],'generation_status':'not_requested_scope_conflict',
                'scope_guard':guard,'candidate_invoked':False,
                'message':'The question names another or unsupported experiment. Choose one supported experiment and ask about that version only.',
                'live_service_changed':False,'human_review_complete':False,'operational_approval':False,'production_ready':False}
    result = scoped_answers.answer(question, experiment, knowledge)
    return {**result,'format':'ain-guarded-excerpts-v1','scope_guard':guard,'candidate_invoked':True}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment',choices=scoped_answers.EXPERIMENTS,required=True)
    parser.add_argument('--question',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();supplied=Path(args.output);target=supplied.resolve()
    if not target.is_relative_to(ROOT/'.local') or target.exists() or any(p.is_symlink() for p in (supplied,*supplied.parents)):
        raise ValueError('Use a new private output under this checkout .local')
    result=answer(args.question,args.experiment);target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('x',encoding='utf-8') as stream:stream.write(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'mode':result['mode'],'candidate_invoked':result['candidate_invoked'],'claims':len(result['claims']),'production_ready':False}))


if __name__=='__main__':main()
