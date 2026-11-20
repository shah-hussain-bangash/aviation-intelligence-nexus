"""Small curated engineering checks, not an independent generalization benchmark."""
import json
import time
from rag.service import Knowledge, Question
from rag.index import ROOT

CASES = [
    ('What were the May ROC-AUC and false alerts for the second delay model?', 'docs/DELAY_V2.md', True),
    ('How does the gate optimizer prioritize coverage and assignment cost?', 'docs/GATE_OPTIMIZATION.md', True),
    ('How many flights were imported in January 2025?', 'docs/DATA_INGESTION.md', False),
    ('What chronological training validation and testing months were used in the second experiment?', 'docs/DELAY_V2.md', False),
    ('What are the admin researcher and viewer permissions?', 'docs/LOCAL_IDENTITY.md', False),
    ('Why was the logistic baseline rejected for operational serving?', 'docs/DELAY_BASELINE.md', False),
    ('Who is the CEO of Emirates?', None, True),
    ('What is the best pizza recipe?', None, True),
]


def evaluate():
    knowledge, rows = Knowledge(), []
    for question, expected, generate in CASES:
        started = time.monotonic()
        result = knowledge.query(Question(question=question, generate=generate))
        passed = any(e['source'] == expected for e in result['evidence']) if expected else result['mode'] == 'abstained' and not result['claims']
        rows.append({'question':question,'expected_source':expected,'retrieval_passed':passed,
            'mode':result['mode'],'generation':result['generation'],'claims':result['claims'],
            'retrieved': [{'id':e['id'],'source':e['source'],'heading':e['heading'],'score':e['score']} for e in result['evidence']],
            'elapsed_ms':round((time.monotonic()-started)*1000,2)})
    report = {'scope':'Curated engineering checks on six public project documents; not a held-out airline QA benchmark',
        'status':knowledge.status(),'cases':rows,'retrieval_passed':sum(row['retrieval_passed'] for row in rows),
        'total':len(rows),'generated_answers':sum(row['mode']=='generated' for row in rows),
        'semantic_review':'Pending manual review of the saved claims; exact quotation checks do not establish entailment'}
    (ROOT/'docs/reports/Knowledge_Demo.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'retrieval_passed':report['retrieval_passed'],'total':report['total'],'generated_answers':report['generated_answers']}))


if __name__ == '__main__':
    evaluate()
