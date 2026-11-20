"""Offline read-only structural audit of the fixed Jan-May 2025 BTS release."""
import argparse
from contextlib import closing
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
import time
from services.api.paths import ROOT,STATE

PERIODS=[f'2025-{month:02}' for month in range(1,6)]
SOURCE='BTS_REPORTING_CARRIER'
GOOD={
    'date':"length(flight_date)=10 AND flight_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]' AND date(flight_date,'+0 days')=flight_date",
    'carrier':"length(carrier) BETWEEN 2 AND 3 AND carrier NOT GLOB '*[^A-Z0-9]*'",
    'origin':"length(origin)=3 AND origin NOT GLOB '*[^A-Z]*'",
    'destination':"length(destination)=3 AND destination NOT GLOB '*[^A-Z]*'",
    'flight_number':"length(flight_number) BETWEEN 1 AND 5 AND flight_number NOT GLOB '*[^0-9]*' AND CAST(flight_number AS INTEGER) BETWEEN 1 AND 99999 AND CAST(CAST(flight_number AS INTEGER) AS TEXT)=flight_number",
    'scheduled_departure':"length(scheduled_departure)=4 AND scheduled_departure NOT GLOB '*[^0-9]*' AND (scheduled_departure='2400' OR (substr(scheduled_departure,1,2) BETWEEN '00' AND '23' AND substr(scheduled_departure,3,2) BETWEEN '00' AND '59'))",
    'flags':"typeof(cancelled)='integer' AND typeof(diverted)='integer' AND cancelled IN (0,1) AND diverted IN (0,1)",
    'arrival_delay':"arrival_delay_minutes IS NULL OR (typeof(arrival_delay_minutes) IN ('integer','real') AND arrival_delay_minutes BETWEEN -1.7976931348623157e308 AND 1.7976931348623157e308)",
    'departure_delay':"departure_delay_minutes IS NULL OR (typeof(departure_delay_minutes) IN ('integer','real') AND departure_delay_minutes BETWEEN -1.7976931348623157e308 AND 1.7976931348623157e308)",
    'record_key':"typeof(source_record_id)='text' AND source_record_id=flight_date||'|'||carrier||'|'||flight_number||'|'||origin||'|'||destination||'|'||scheduled_departure"}
COHORTS=['eligible_arrivals','excluded_cancelled','excluded_diverted','excluded_missing_or_invalid']
SQL="WITH rows AS (SELECT *,"+','.join(f'CASE WHEN ({condition}) THEN 0 ELSE 1 END AS bad_{name}' for name,condition in GOOD.items())+", CASE WHEN cancelled=1 THEN 'excluded_cancelled' WHEN diverted=1 THEN 'excluded_diverted' WHEN cancelled IS NOT 0 OR diverted IS NOT 0 OR arrival_delay_minutes IS NULL OR COALESCE(flight_number,'')='' OR COALESCE(scheduled_departure,'')='' THEN 'excluded_missing_or_invalid' ELSE 'eligible_arrivals' END AS cohort FROM flights WHERE source=? AND substr(flight_date,1,7)=?) SELECT ? AS period,COUNT(*) AS records,COUNT(DISTINCT source_record_id) AS distinct_keys,"+','.join(f'SUM(bad_{name}) AS bad_{name}' for name in GOOD)+','+','.join(f"SUM(cohort='{name}') AS {name}" for name in COHORTS)+" FROM rows"


def audit(database,clock=time.monotonic):
    database=Path(database).resolve()
    if not database.is_file():raise ValueError('Historical database must already exist')
    started=clock();deadline=started+120
    with closing(sqlite3.connect(database.as_uri()+'?mode=ro',uri=True,timeout=1)) as db:
        db.row_factory=sqlite3.Row;db.execute('PRAGMA query_only=ON');db.set_progress_handler(lambda:int(clock()>=deadline),1000);db.execute('BEGIN')
        scope=dict(db.execute("SELECT COUNT(*) AS all_records,SUM(source=?) AS source_records,SUM(CASE WHEN source=? AND ("+GOOD['date']+") THEN 0 WHEN source=? THEN 1 ELSE 0 END) AS invalid_dates_all_source FROM flights",(SOURCE,SOURCE,SOURCE)).fetchone())
        observed={}
        for period in PERIODS:
            row=dict(db.execute(SQL,(SOURCE,period,period)).fetchone())
            observed[period]={key:(value if value is not None or key=='period' else 0) for key,value in row.items()}
        manifests=[dict(row) for row in db.execute("SELECT period,sha256,source_url,rows_read,rows_inserted,duplicate_rows FROM imports WHERE period BETWEEN '2025-01' AND '2025-05' ORDER BY period,sha256 LIMIT 1001")]
        if len(manifests)>1000:raise ValueError('Import manifest observation bound exceeded')
    months=[];bad_manifests=sum(m['period'] not in PERIODS for m in manifests)
    for period in PERIODS:
        row=observed.get(period,{'records':0,'distinct_keys':0,**{f'bad_{key}':0 for key in GOOD},**{key:0 for key in COHORTS}})
        entries=[];inserted=0
        for item in [m for m in manifests if m['period']==period]:
            url=f'https://transtats.bts.gov/PREZIP/On_Time_Reporting_Carrier_On_Time_Performance_1987_present_2025_{int(period[-2:])}.zip'
            valid=isinstance(item['sha256'],str) and bool(re.fullmatch('[0-9a-f]{64}',item['sha256'])) and item['source_url']==url and all(type(item[k]) is int and item[k]>=0 for k in ['rows_read','rows_inserted','duplicate_rows'])
            valid=valid and item['rows_read']==item['rows_inserted']+item['duplicate_rows']
            if not valid:bad_manifests+=1;continue
            inserted+=item['rows_inserted'];entries.append({k:item[k] for k in ['sha256','rows_read','rows_inserted','duplicate_rows']})
        months.append({'period':period,'records':row['records'],'duplicate_keys':row['records']-row['distinct_keys'],
            'field_issues':{key:row['bad_'+key] for key in GOOD},'cohorts':{key:row[key] for key in COHORTS},
            'manifests':entries,'manifest_rows_inserted':inserted,
            'import_reconciliation':'missing' if not entries else 'matched' if inserted==row['records'] else 'mismatched'})
    source_records=scope['source_records'] or 0;profiled=sum(m['records'] for m in months)
    issues=sum(sum(m['field_issues'].values())+m['duplicate_keys'] for m in months)
    passed=bool(source_records) and profiled==source_records and not (scope['invalid_dates_all_source'] or issues or bad_manifests) and all(m['records']>0 and m['import_reconciliation']=='matched' for m in months)
    if clock()>=deadline:raise RuntimeError('Audit observation budget exceeded')
    return {'format':'ain-data-quality-v1','checked_at':datetime.now(timezone.utc).isoformat(),'source':SOURCE,'audited_periods':PERIODS,
        'source_records':source_records,'profiled_records':profiled,'other_source_records':scope['all_records']-source_records,
        'unprofiled_source_records':source_records-profiled,'invalid_dates_all_source':scope['invalid_dates_all_source'] or 0,
        'invalid_manifest_entries':bad_manifests,'field_issue_occurrences':issues,'months':months,'checks_passed':passed,
        'elapsed_seconds':round(clock()-started,3),'sqlite_version':sqlite3.sqlite_version,
        'query_sha256':hashlib.sha256(SQL.encode()).hexdigest(),'research_only':True,'production_ready':False,
        'limitations':['Recorded structural audit, not a current database health check or verification that source values are true.',
            'Import hashes are recorded lineage metadata; archive files are not re-read or re-hashed by this audit.',
            'Field issue counts can overlap on a record. Modelling cohorts are mutually exclusive and follow the existing dataset-builder exclusion priority.',
            'Missing arrival delay is allowed in storage; cancellation/diversion/missing-target rows are excluded from the modelling population.',
            'Five historical US domestic months only; no UAE transfer, live-feed freshness or production data-governance approval.']}


def run(database,output):
    output=Path(output).resolve()
    if not output.is_relative_to((ROOT/'.local').resolve()) or output==(ROOT/'.local').resolve() or output.exists():
        raise ValueError('Choose a new private audit directory under .local')
    output.mkdir(parents=True)
    (output/'started.json').write_text(json.dumps({'started_at':datetime.now(timezone.utc).isoformat(),'scope':'Read-only Jan-May BTS structural audit'})+'\n',encoding='utf-8')
    report=audit(database)
    (output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--database',type=Path,default=STATE/'ain.sqlite3');parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();report=run(args.database,args.output)
    print(json.dumps({k:report[k] for k in ['source_records','profiled_records','checks_passed','field_issue_occurrences','elapsed_seconds']},indent=2))
    sys.exit(0 if report['checks_passed'] else 1)
