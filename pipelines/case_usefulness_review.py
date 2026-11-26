"""Export a frozen live-rehearsal case for unsigned human self-review; no database writes."""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3

from agents.quality import assess_report,report_evidence
from agents.store import sha
from pipelines.synthetic_ingestion import host,local
from rag.review_page import csp_hash
from rag.semantic_review import read_json,new_output,require
from services.api.paths import ROOT
from services.api.research_cases import ResearchCaseService,digest


def validate_packet(packet):
    require(set(packet)=={'format','receipt_file_sha256','receipt','case','run','evidence','human_identity_verified','independent_review','production_ready'},'Packet fields changed')
    require(packet.get('format')=='ain-case-usefulness-packet-v1','Unsupported case packet')
    receipt=packet['receipt'];case=packet['case'];run=packet['run']
    require(receipt.get('format')=='ain-combined-case-journey-v1' and receipt.get('passed') is True
        and receipt.get('live_ai_requested') is True and receipt.get('generator_executed') is True
        and receipt.get('worker_loop_executed') is True and receipt.get('production_ready') is False
        and receipt.get('genuine_human_acceptance') is False,'A completed live research rehearsal is required')
    require(receipt['case_id']==case['id'] and case['title'].startswith('SYNTHETIC')
        and digest(case)==receipt['final_case_sha256'] and case['operational_approval'] is False
        and case['production_ready'] is False and case['scope']=='historical_us_research','Case binding changed')
    require(run['run_id']==receipt['agent_run_id'] and run['request']['case_context']['case_id']==case['id']
        and digest(run)==receipt['agent_snapshot_sha256'] and run['report_sha256']==receipt['report_sha256']
        and sha({k:run[k] for k in ('request','steps','claims')})==run['report_sha256']
        and run['model']==receipt['local_model'] and run['research_only'] is True
        and run['operational_approval'] is False,'Report binding changed')
    require(any(a['run_id']==run['run_id'] and a['sha256']==digest(run) for a in case['agent_links']),
        'Retained attachment missing')
    require(packet['evidence']==report_evidence(run) and assess_report(run)['passed']
        and 1<=len(run['claims'])<=6,'Evidence or automatic coverage changed')
    require(packet['human_identity_verified'] is False and packet['independent_review'] is False
        and packet['production_ready'] is False,'Review authority changed')
    return packet


def blank(packet,packet_hash):
    return {'format':'ain-case-usefulness-annotations-v1','packet_sha256':packet_hash,'reviewer_label':'',
        'source_checked':False,'own_assessment':False,'question_answered':'',
        'claims':[{'claim_index':i,'citation':c['citation'],'supported':'','relevant':''} for i,c in enumerate(packet['run']['claims'])],
        'notes':''}


def assess(packet,packet_hash,value):
    validate_packet(packet);expected=blank(packet,packet_hash)
    require(isinstance(value,dict) and set(value)==set(expected) and value['format']==expected['format']
        and value['packet_sha256']==packet_hash,'Annotation binding changed')
    require(isinstance(value['reviewer_label'],str) and len(value['reviewer_label'])<=80
        and isinstance(value['notes'],str) and len(value['notes'])<=2000
        and type(value['source_checked']) is bool and type(value['own_assessment']) is bool,'Invalid review fields')
    ratings=('','yes','no','uncertain');decisions=[value['question_answered']]
    require(value['question_answered'] in ratings and isinstance(value['claims'],list)
        and len(value['claims'])==len(expected['claims']),'Claim inventory changed')
    for row,original in zip(value['claims'],expected['claims']):
        require(isinstance(row,dict) and set(row)==set(original) and type(row['claim_index']) is int
            and row['claim_index']==original['claim_index'] and row['citation']==original['citation']
            and row['supported'] in ratings and row['relevant'] in ratings,'Claim rating or binding changed')
        decisions.extend((row['supported'],row['relevant']))
    pending=not value['reviewer_label'].strip() or not value['source_checked'] or not value['own_assessment'] or any(v in ('','uncertain') for v in decisions)
    return {'format':'ain-case-usefulness-self-review-v1','packet_sha256':packet_hash,
        'annotations_sha256':digest(value),'status':'pending' if pending else 'declared_needs_revision' if 'no' in decisions else 'declared_acceptable',
        'human_identity_verified':False,'independent_review':False,'operational_approval':False,'production_ready':False,
        'scope':'Unsigned reviewer declarations only; no case, account or model was changed.'}


def prepare(journey_path,journey_hash,output):
    host();journey_path=local(journey_path)
    require(journey_path.is_relative_to(ROOT/'.local') and journey_path.name=='report.json','Use a private rehearsal report.json')
    receipt,observed=read_json(journey_path,journey_hash)
    sidecar=local(journey_path.parent/'research-cases.sqlite3')
    require(sidecar.is_file() and sidecar.stat().st_size<=16_000_000,'Bounded retained case store required')
    with closing(sqlite3.connect(sidecar.as_uri()+'?mode=ro',uri=True)) as db:
        db.row_factory=sqlite3.Row
        row=db.execute('SELECT * FROM cases WHERE id=?',(receipt.get('case_id'),)).fetchone()
        require(row is not None,'Recorded case unavailable')
        case=object.__new__(ResearchCaseService).projection(db,row)
        attached=db.execute('SELECT snapshot_json FROM case_agents WHERE case_id=? AND agent_run_id=?',
            (row['id'],receipt.get('agent_run_id'))).fetchone()
        require(attached is not None,'Retained agent snapshot unavailable');run=json.loads(attached[0])
    packet=validate_packet({'format':'ain-case-usefulness-packet-v1','receipt_file_sha256':observed,
        'receipt':receipt,'case':case,'run':run,'evidence':report_evidence(run),
        'human_identity_verified':False,'independent_review':False,'production_ready':False})
    target=new_output(output);target.mkdir(exist_ok=False)
    raw=(json.dumps(packet,indent=2,ensure_ascii=False,allow_nan=False)+'\n').encode();packet_hash=hashlib.sha256(raw).hexdigest()
    (target/'packet.json').write_bytes(raw)
    (target/'annotations.json').write_text(json.dumps(blank(packet,packet_hash),indent=2),encoding='utf-8')
    style=(ROOT/'apps/web/case-usefulness-review.css').read_text(encoding='utf-8')
    module=(ROOT/'apps/web/case-usefulness-review.mjs').read_text(encoding='utf-8').replace('export function ','function ')
    data=json.dumps({'packet':packet,'hash':packet_hash},ensure_ascii=True,allow_nan=False).replace('<','\\u003c')
    script=module+'\nconst data='+data+';mount(document.getElementById("review"),data.packet,data.hash);\n'
    policy=f"default-src 'none'; script-src 'sha256-{csp_hash(script)}'; style-src 'sha256-{csp_hash(style)}'; connect-src 'none'; base-uri 'none'; form-action 'none'; object-src 'none'"
    html='<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'+f'<meta http-equiv="Content-Security-Policy" content="{policy}"><title>AIN | Case usefulness review</title><style>{style}</style></head><body><div id="review"></div><script>'+script+'</script></body></html>'
    (target/'review.html').write_text(html,encoding='utf-8')
    return {'page':str(target/'review.html'),'packet':str(target/'packet.json'),'packet_sha256':packet_hash,
        'receipt_file_sha256':observed,'case_id':case['id'],'report_sha256':run['report_sha256'],
        'status':'pending','human_ratings_supplied':False,'source_store_opened_readonly':True,
        'network_required':False,'production_ready':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='action',required=True)
    export=sub.add_parser('prepare');export.add_argument('--journey',required=True,type=Path);export.add_argument('--journey-sha256',required=True);export.add_argument('--output',required=True,type=Path)
    review=sub.add_parser('assess');review.add_argument('--packet',required=True,type=Path);review.add_argument('--packet-sha256',required=True);review.add_argument('--annotations',required=True,type=Path);review.add_argument('--annotations-sha256',required=True)
    args=parser.parse_args()
    if args.action=='prepare':result=prepare(args.journey,args.journey_sha256,args.output)
    else:
        packet,pin=read_json(args.packet,args.packet_sha256);annotations,_=read_json(args.annotations,args.annotations_sha256)
        result=assess(packet,pin,annotations)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
