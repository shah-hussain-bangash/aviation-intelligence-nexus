"""Host-only synthetic import drill. Never selects an existing application database."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import csv
from datetime import datetime,timezone
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import threading
from unittest.mock import patch
from uuid import uuid4
import zipfile

from pipelines.import_bts import import_archive, normalize, SOURCE, SYNTHETIC_SOURCE
from services.api.configuration import validate_environment
from services.api.main import initialize
from services.api.paths import ROOT, SCHEMA_VERSION

FIELDS=['FlightDate','Reporting_Airline','Flight_Number_Reporting_Airline','Origin','Dest','CRSDepTime','DepDelay','ArrDelay','Cancelled','Diverted']
BASE=[['2025-01-01','XX','1','AAA','BBB','0900','3','7','0','0'],
      ['2025-01-01','XX','1','AAA','BBB','0900','3','7','0','0'],
      ['2025-01-01','XX','2','AAA','CCC','1000','','','1','0'],
      ['2025-01-02','XX','3','BBB','AAA','1400','10','','0','1']]
SOURCES=('pipelines/import_bts.py','pipelines/verify_import_safety.py','services/api/main.py',
         'services/api/paths.py','services/api/migrations.py','services/api/security_audit.py','infra/recovery_state.py')


def hashes():return {p:hashlib.sha256((ROOT/p).read_text(encoding='utf-8').encode()).hexdigest() for p in SOURCES}


def identity():
    result={'source_sha256':hashes()};env=dict(os.environ)
    try:
        def quote(value):return "'"+value.replace("'","'\\''")+"'"
        count=int(env.get('GIT_CONFIG_COUNT','0'))
        pairs=[quote(env.pop(f'GIT_CONFIG_KEY_{i}')+'='+env.pop(f'GIT_CONFIG_VALUE_{i}')) for i in range(count)]
        if count:
            env['GIT_CONFIG_PARAMETERS']=(env.get('GIT_CONFIG_PARAMETERS','')+' '+' '.join(pairs)).strip();env['GIT_CONFIG_COUNT']='0'
        command=['git','-c','safe.directory='+ROOT.as_posix()]
        result['source_revision']=subprocess.check_output([*command,'rev-parse','HEAD'],cwd=ROOT,env=env,text=True,stderr=subprocess.DEVNULL,timeout=10).strip()
        result['working_tree_changes']=bool(subprocess.check_output([*command,'status','--porcelain'],cwd=ROOT,env=env,text=True,stderr=subprocess.DEVNULL,timeout=10).strip())
    except (OSError,subprocess.SubprocessError,KeyError,ValueError):result.update(source_revision=None,working_tree_changes=None)
    return result


def fixture(path,rows):
    text=io.StringIO(newline='');writer=csv.writer(text);writer.writerow(FIELDS);writer.writerows(rows)
    entry=zipfile.ZipInfo('synthetic.csv',(2025,1,1,0,0,0));entry.compress_type=zipfile.ZIP_DEFLATED
    with zipfile.ZipFile(path,'w') as archive:archive.writestr(entry,text.getvalue())


def counts(database):
    with closing(sqlite3.connect(database)) as db:
        return db.execute('SELECT COUNT(*) FROM flights').fetchone()[0],db.execute('SELECT COUNT(*) FROM imports').fetchone()[0]


def require(value):
    if not value:raise ValueError('synthetic_import_check_failed')


def verify(directory):
    config=validate_environment(os.environ)
    if config.container or any(os.environ.get(k)=='1' for k in ('AIN_AGENT_JOBS','AIN_MONITOR_ENABLED','AIN_OBSERVER_MOUNTED','AIN_INTAKE_OVERVIEW_MOUNTED')):
        raise ValueError('host_research_environment_required')
    directory=Path(directory)
    if any(p.is_symlink() or getattr(p,'is_junction',lambda:False)() for p in (directory,*directory.parents)):
        raise ValueError('unredirected_case_required')
    context=identity();directory.mkdir(parents=True,exist_ok=False)
    report={'format':'ain-synthetic-import-drill-v1','checked_at':datetime.now(timezone.utc).isoformat(),
            'case_id':directory.name if len(directory.name)==32 and all(c in '0123456789abcdef' for c in directory.name) else None,
            **context,'passed':False,'checks':{},'synthetic_only':True,'external_data_imported':False,
            'source_schema_version':SCHEMA_VERSION,
            'primary_database_accessed':False,'training_performed':False,'deployment_performed':False,'production_ready':False}
    stage='fixture'
    try:
        archive=directory/'synthetic.zip';fixture(archive,BASE);database=directory/'research.sqlite3'
        archive_hash=hashlib.sha256(archive.read_bytes()).hexdigest()
        stage='first_import';first=import_archive(archive,database,2025,1,synthetic=True)
        require(first['sha256']==archive_hash and (first['rows_read'],first['rows_inserted'],first['duplicate_rows'])==(4,3,1))
        replay=import_archive(archive,database,2025,1,synthetic=True)
        require(replay['status']=='already_imported' and counts(database)==(3,1))
        record_id=normalize(dict(zip(FIELDS,BASE[0])),'2025-01')[1]
        with closing(sqlite3.connect(database)) as db:
            row=db.execute('SELECT source,source_record_id,arrival_delay_minutes FROM flights WHERE source=? AND source_record_id=?',(SYNTHETIC_SOURCE,record_id)).fetchone()
            ledger=db.execute('SELECT sha256,source_url,period,rows_read,rows_inserted,duplicate_rows FROM imports').fetchone()
            require(row==(SYNTHETIC_SOURCE,record_id,7) and ledger==(archive_hash,'urn:ain:synthetic-bts-schema:2025-01','2025-01',4,3,1))
            require(db.execute('SELECT COUNT(*) FROM flights WHERE source=?',(SOURCE,)).fetchone()[0]==0)
        report['checks'].update(import_counts_reconciled=True,replay_is_idempotent=True,synthetic_labels_retained=True,fixture_row_matches_archive_ledger=True)
        report['fixture_lineage']={'scope':'isolated synthetic single batch only; not general per-row production lineage',
                                  'archive_sha256':archive_hash,'source':SYNTHETIC_SOURCE,'source_record_id':record_id,
                                  'ledger_source_url':ledger[1],'period':'2025-01','rows_read':4,'rows_inserted':3,'identical_duplicates':1}
        stage='scope_replay'
        try:import_archive(archive,database,2025,1)
        except ValueError:scope_refused=True
        else:scope_refused=False
        require(scope_refused and counts(database)==(3,1));report['checks']['cannot_relabel_replay_as_observed_bts']=True
        stage='rollback'
        new=[*BASE[0]];new[2]='9';conflict=[*BASE[0]];conflict[7]='99'
        malformed=[*BASE[0]];malformed[0]='2025-02-01'
        for name,rows in (('conflict',[new,conflict]),('invalid',[new,malformed])):
            bad=directory/(name+'.zip');fixture(bad,rows)
            try:import_archive(bad,database,2025,1,synthetic=True)
            except ValueError:refused=True
            else:refused=False
            require(refused and counts(database)==(3,1));report['checks'][name+'_batch_rolled_back']=True
        stage='concurrent_replay'
        concurrent=directory/'concurrent.sqlite3';initialize(concurrent);barrier=threading.Barrier(3)
        def worker(_):barrier.wait(timeout=10);return import_archive(archive,concurrent,2025,1,synthetic=True)['status']
        with ThreadPoolExecutor(max_workers=3) as workers:statuses=list(workers.map(worker,range(3)))
        require(sorted(statuses)==['already_imported','already_imported','imported'] and counts(concurrent)==(3,1))
        report['checks']['concurrent_replays_commit_once']=True
        stage='captured_bytes'
        changing=directory/'changing.zip';changing.write_bytes(archive.read_bytes())
        replacement=[*BASE[0]];replacement[7]='88'
        other=directory/'replacement.zip';fixture(other,[replacement])
        def change_path(database):initialize(database);changing.write_bytes(other.read_bytes())
        captured_database=directory/'captured.sqlite3'
        with patch('pipelines.import_bts.initialize',side_effect=change_path):
            captured=import_archive(changing,captured_database,2025,1,synthetic=True)
        require(captured['sha256']==archive_hash and hashlib.sha256(changing.read_bytes()).hexdigest()!=archive_hash)
        with closing(sqlite3.connect(captured_database)) as db:
            require(db.execute('SELECT arrival_delay_minutes FROM flights WHERE source_record_id=?',(record_id,)).fetchone()[0]==7)
        report['checks']['consumed_private_snapshot_matches_ledger_hash']=True
        stage='source_binding';require(hashes()==context['source_sha256'])
        report['checks']['source_unchanged_during_drill']=True
        require(all(report['checks'].values()));report['passed']=True
    except (OSError,ValueError,RuntimeError,sqlite3.Error,zipfile.BadZipFile,csv.Error,KeyError,TypeError):
        report.update(failed_stage=stage,error='synthetic_import_drill_failed')
    with (directory/'report.json').open('x',encoding='utf-8') as stream:json.dump(report,stream,indent=2);stream.write('\n')
    return report


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    try:report=verify(ROOT/'.local/import-safety'/uuid4().hex)
    except (OSError,ValueError):report={'format':'ain-synthetic-import-drill-v1','passed':False,'error':'drill_admission_refused','production_ready':False}
    print(json.dumps(report,indent=2));return 0 if report['passed'] else 2


if __name__=='__main__':raise SystemExit(main())
