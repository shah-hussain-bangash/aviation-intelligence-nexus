"""Read-only database snapshot of marginal historical inputs; no fitting."""
import argparse
from contextlib import closing
import sqlite3
from datetime import datetime,timezone
import hashlib
import json
import math
from pathlib import Path
import re
import time
from services.api.paths import ROOT
from services.api.diagnostics import load_diagnostics,REPORT

FEATURES=['carrier','origin','destination','departure_hour','weekday']
PROTOCOL=ROOT/'ml/input_shift_protocol.json'
PROTOCOL_SHA256='f023328d1fa72843732c93c0e5c3b4770e552347eb041f18555838c563465549'


def compare(reference,comparison):
    if any(type(v) is not int or v<0 for counts in (reference,comparison) for v in counts.values()):raise ValueError('Invalid category counts')
    a,b=sum(reference.values()),sum(comparison.values())
    if not a or not b:raise ValueError('Both cohorts need observations')
    rows=[];tv=0.;js=0.;unseen=0
    for label in sorted(set(reference)|set(comparison)):
        left,right=reference.get(label,0),comparison.get(label,0);p,q=left/a,right/b;m=(p+q)/2
        tv+=abs(p-q)/2
        js+=(p*math.log2(p/m) if p else 0)/2+(q*math.log2(q/m) if q else 0)/2
        if not left:unseen+=right
        rows.append({'category':label,'reference_count':left,'comparison_count':right,
            'reference_share':p,'comparison_share':q,'change_percentage_points':100*(q-p)})
    return {'reference_records':a,'comparison_records':b,'category_count':len(rows),
        'total_variation':max(0.,min(1.,tv)),'jensen_shannon_divergence_bits':max(0.,min(1.,js)),
        'comparison_unseen_records':unseen,'comparison_mass_unseen_in_reference':unseen/b,'categories':rows}


HOUR_SQL="CASE WHEN scheduled_departure='2400' THEN '00' WHEN length(scheduled_departure)=4 AND scheduled_departure NOT GLOB '*[^0-9]*' AND substr(scheduled_departure,1,2) BETWEEN '00' AND '23' AND substr(scheduled_departure,3,2) BETWEEN '00' AND '59' THEN substr(scheduled_departure,1,2) ELSE NULL END"
FEATURE_SQL={'carrier':'carrier','origin':'origin','destination':'destination','departure_hour':HOUR_SQL,
    'weekday':"CAST((CAST(strftime('%w',flight_date) AS INTEGER)+6)%7+1 AS TEXT)"}
ELIGIBLE="source='BTS_REPORTING_CARRIER' AND cancelled=0 AND diverted=0 AND arrival_delay_minutes IS NOT NULL AND coalesce(flight_number,'')<>'' AND coalesce(scheduled_departure,'')<>''"


def aggregate(db,start,end):
    result={}
    for key,expression in FEATURE_SQL.items():
        rows=db.execute('SELECT '+expression+' AS category,count(*) AS n FROM flights WHERE '+ELIGIBLE+' AND flight_date>=? AND flight_date<? GROUP BY category',(start,end)).fetchall()
        counts={row[0]:row[1] for row in rows}
        pattern=r'[A-Z0-9]{2,3}' if key=='carrier' else r'[A-Z]{3}' if key in ('origin','destination') else r'(?:[01][0-9]|2[0-3])' if key=='departure_hour' else r'[1-7]'
        if not counts or len(counts)>2000 or any(not isinstance(label,str) or not re.fullmatch(pattern,label) for label in counts):raise ValueError('Invalid or unsupported input categories')
        result[key]=counts
    return result


def evaluate(database,output,protocol_text=None):
    output=Path(output).resolve()
    if not output.is_relative_to((ROOT/'.local').resolve()) or output==(ROOT/'.local').resolve() or output.exists():raise ValueError('Choose a new private experiment directory under .local')
    protocol_text=PROTOCOL.read_text(encoding='utf-8') if protocol_text is None else protocol_text
    if hashlib.sha256(protocol_text.encode()).hexdigest()!=PROTOCOL_SHA256:raise ValueError('Recorded diagnostic protocol changed')
    protocol=json.loads(protocol_text)
    if protocol['features']!=FEATURES or protocol['periods']!={'train':['2025-01','2025-02','2025-03'],'test':['2025-05']} or protocol['smoothing'] is not False or protocol['model_fitting'] is not False or protocol['label_statistics'] is not False or protocol['alert_threshold'] is not None:raise ValueError('Unsupported distribution protocol')
    load_diagnostics();frozen=json.loads((ROOT/REPORT).read_text(encoding='utf-8'))
    output.mkdir(parents=True);started=time.monotonic();deadline=started+120
    protocol_hash=hashlib.sha256(protocol_text.encode()).hexdigest()
    (output/'started.json').write_text(json.dumps({'protocol':protocol,'protocol_sha256':protocol_hash,'started_at':datetime.now(timezone.utc).isoformat()},indent=2)+'\n',encoding='utf-8')
    with closing(sqlite3.connect(Path(database).resolve().as_uri()+'?mode=ro',uri=True,timeout=1)) as db:
        db.execute('PRAGMA query_only=ON');db.set_progress_handler(lambda:int(time.monotonic()>deadline),1000);db.execute('BEGIN')
        reference=aggregate(db,'2025-01-01','2025-04-01');comparison=aggregate(db,'2025-05-01','2025-06-01')
    if any(sum(v.values())!=frozen['training_records'] for v in reference.values()) or any(sum(v.values())!=frozen['test']['model']['records'] for v in comparison.values()):raise ValueError('Cohort counts differ from the frozen model populations')
    report={'format':'ain-input-distributions-v1','checked_at':datetime.now(timezone.utc).isoformat(),'protocol':protocol,'protocol_sha256':protocol_hash,
        'frozen_model_report_sha256':hashlib.sha256((ROOT/REPORT).read_text(encoding='utf-8').encode()).hexdigest(),
        'query_sha256':hashlib.sha256(json.dumps({'features':FEATURE_SQL,'eligibility':ELIGIBLE},sort_keys=True).encode()).hexdigest(),'csv_identity_verified':False,'cohort_counts_match_frozen':True,
        'reference_records':frozen['training_records'],'comparison_records':frozen['test']['model']['records'],
        'features':{key:compare(reference[key],comparison[key]) for key in FEATURES},'elapsed_seconds':round(time.monotonic()-started,3),
        'research_only':True,'production_ready':False,'alert_threshold':None,'model_changed':False,
        'limitations':['Recorded January-March versus May 2025 eligible US cohorts, not current traffic or UAE operations.',
            'Source is the restored database; matching cohort counts do not prove frozen CSV byte identity or identical record membership.',
            'Eligibility conditions on completed non-diverted flights with observed arrival delay; this is not the full flight population.',
            'These are marginal distributions. Hour bins discard minute detail; joint dependence and model preprocessing are not compared.',
            'Descriptive distances have no confidence intervals, significance test or alert threshold here.',
            'A changed input distribution does not establish degraded prediction, causality or a reason for individual errors.',
            'May has already been evaluated; this is a retrospective diagnostic, not a new untouched test or tuning opportunity.']}
    if time.monotonic()>deadline:raise TimeoutError('Distribution comparison budget exceeded')
    (output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--database',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();report=evaluate(args.database,args.output)
    print(json.dumps({'reference_records':report['reference_records'],'comparison_records':report['comparison_records'],'elapsed_seconds':report['elapsed_seconds'],
        'metrics':{k:{m:v[m] for m in ['total_variation','jensen_shannon_divergence_bits','comparison_mass_unseen_in_reference']} for k,v in report['features'].items()}},indent=2))
