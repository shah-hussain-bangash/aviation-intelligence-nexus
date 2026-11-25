"""Separate single-host synthetic artifact catalog; no deployment or production authority."""
import argparse
from contextlib import closing, contextmanager
from datetime import datetime,timezone
import hashlib
import json
import re
import sqlite3

from ml.evaluate_synthetic_holdout import MAX_BYTES, read_json
from ml.synthetic_model_bundle import validate_bundle
from pipelines.synthetic_ingestion import host,local
from pipelines.time_safe_features import require

MAX_MODELS=100
MAX_EVENTS=10_000
TABLES={'catalog','models','events'}


def pin(value):return type(value) is str and re.fullmatch('[0-9a-f]{64}',value)


def initialize(directory):
    host();directory=local(directory);directory.mkdir(parents=True,exist_ok=False)
    (directory/'bundles').mkdir()
    with closing(sqlite3.connect(local(directory/'catalog.sqlite3'))) as db,db:
        db.executescript('''CREATE TABLE catalog(id INTEGER PRIMARY KEY CHECK(id=1),version INTEGER NOT NULL,
          revision INTEGER NOT NULL,current TEXT,previous TEXT);
          INSERT INTO catalog VALUES(1,1,0,NULL,NULL);
          CREATE TABLE models(sha TEXT PRIMARY KEY,state_sha TEXT NOT NULL,receipt_sha TEXT NOT NULL);
          CREATE TABLE events(revision INTEGER PRIMARY KEY,action TEXT NOT NULL,model_sha TEXT NOT NULL,
          prior_sha TEXT,reason TEXT NOT NULL,recorded_at TEXT NOT NULL);''')
    return status(directory)


@contextmanager
def connection(directory,*,write=False):
    host();directory=local(directory);path=local(directory/'catalog.sqlite3')
    require(path.is_file(),'existing_catalog_required')
    with closing(sqlite3.connect(path.as_uri()+('?mode=rw' if write else '?mode=ro'),uri=True,timeout=10)) as db:
        db.row_factory=sqlite3.Row
        db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
        try:
            require({r[0] for r in db.execute("SELECT name FROM sqlite_schema WHERE type='table'") }==TABLES,'unsupported_catalog')
            rows=db.execute('SELECT * FROM catalog').fetchall()
            require(len(rows)==1 and rows[0]['id']==1 and rows[0]['version']==1
                    and type(rows[0]['revision']) is int and 0<=rows[0]['revision']<=MAX_EVENTS,'invalid_catalog_state')
            yield directory,db,dict(rows[0])
            if write:db.commit()
        except Exception:
            if write:db.rollback()
            raise


def inventory(directory,db,state):
    rows=db.execute('SELECT * FROM models ORDER BY sha LIMIT ?',(MAX_MODELS+1,)).fetchall()
    require(len(rows)<=MAX_MODELS,'catalog_limit')
    models={}
    for row in rows:
        require(pin(row['sha']) and pin(row['state_sha']) and pin(row['receipt_sha']),'invalid_catalog_identity')
        bundle,digest=read_json(directory/'bundles'/(row['sha']+'.json'))
        validate_bundle(bundle)
        require(digest==row['sha'] and bundle['state_sha256']==row['state_sha']
                and bundle['evaluation_receipt_sha256']==row['receipt_sha'],'registered_bundle_changed')
        models[row['sha']]=dict(row)
    require(all(state[key] is None or state[key] in models for key in ('current','previous')),'unregistered_selection')
    events=[dict(r) for r in db.execute('SELECT * FROM events ORDER BY revision LIMIT ?',(MAX_EVENTS+1,))]
    require(len(events)==state['revision'] and [r['revision'] for r in events]==list(range(1,state['revision']+1)),'event_history_gap')
    current=None;previous=None;registered=set()
    for event in events:
        require(event['model_sha'] in models and type(event['reason']) is str and 1<=len(event['reason'])<=200,'invalid_event')
        if event['action']=='register':
            require(event['model_sha'] not in registered and event['prior_sha'] is None,'registration_history_invalid')
            registered.add(event['model_sha'])
        else:
            require(event['action'] in ('select','rollback') and event['model_sha'] in registered
                    and event['prior_sha']==current and event['model_sha']!=current,'selection_history_invalid')
            if event['action']=='rollback':require(event['model_sha']==previous,'rollback_history_invalid')
            previous,current=current,event['model_sha']
    require(registered==set(models) and current==state['current'] and previous==state['previous'],'catalog_history_mismatch')
    return models,events


def status(directory):
    with connection(directory) as (directory,db,state):
        models,events=inventory(directory,db,state)
        return {'format':'ain-synthetic-model-catalog-v1','revision':state['revision'],
                'current':state['current'],'previous':state['previous'],'models':list(models.values()),'events':events,
                'source_scope':'synthetic','deployed':False,'source_authenticated':False,'production_ready':False}


def record(db,state,action,model,prior,reason,current,previous):
    require(state['revision']<MAX_EVENTS,'event_limit')
    require(type(reason) is str and 1<=len(reason.strip())<=200 and all(ord(c)>=32 for c in reason),'explicit_short_reason_required')
    revision=state['revision']+1
    db.execute('INSERT INTO events VALUES(?,?,?,?,?,?)',(revision,action,model,prior,reason,datetime.now(timezone.utc).isoformat()))
    db.execute('UPDATE catalog SET revision=?,current=?,previous=? WHERE id=1',(revision,current,previous))
    return revision


def register(directory,bundle_path,*,bundle_sha256):
    require(pin(bundle_sha256),'bundle_pin_required')
    bundle,digest=read_json(bundle_path);require(digest==bundle_sha256,'bundle_identity_mismatch');validate_bundle(bundle)
    # Capture the exact verified bytes, never reserialize or overwrite registered versions.
    with local(bundle_path).open('rb') as stream:data=stream.read(MAX_BYTES+1)
    require(len(data)<=MAX_BYTES and hashlib.sha256(data).hexdigest()==digest,'bundle_changed')
    with connection(directory,write=True) as (directory,db,state):
        models,_=inventory(directory,db,state)
        if digest in models:return {'registered':False,'revision':state['revision'],'bundle_sha256':digest,'production_ready':False}
        require(len(models)<MAX_MODELS,'catalog_limit')
        destination=local(directory/'bundles'/(digest+'.json'))
        if destination.exists():require(read_json(destination)[1]==digest,'orphan_bundle_mismatch')
        else:
            with destination.open('xb') as stream:stream.write(data)
        require(read_json(destination)[1]==digest,'copied_bundle_mismatch')
        db.execute('INSERT INTO models VALUES(?,?,?)',(digest,bundle['state_sha256'],bundle['evaluation_receipt_sha256']))
        revision=record(db,state,'register',digest,None,'Register verified synthetic bundle',state['current'],state['previous'])
        return {'registered':True,'revision':revision,'bundle_sha256':digest,'production_ready':False}


def select(directory,model_sha,*,expected_revision,reason,rollback=False):
    require(type(expected_revision) is int and expected_revision>=0 and type(rollback) is bool,'expected_revision_required')
    with connection(directory,write=True) as (directory,db,state):
        models,_=inventory(directory,db,state)
        require(state['revision']==expected_revision,'stale_catalog_revision')
        require(pin(model_sha) and model_sha in models and model_sha!=state['current'],'different_registered_model_required')
        if rollback:require(state['previous']==model_sha,'previous_version_required')
        revision=record(db,state,'rollback' if rollback else 'select',model_sha,state['current'],reason,model_sha,state['current'])
        return {'revision':revision,'current':model_sha,'previous':state['current'],
                'source_scope':'synthetic','deployed':False,'production_ready':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory')
    commands=parser.add_subparsers(dest='command',required=True)
    commands.add_parser('init');commands.add_parser('status')
    registration=commands.add_parser('register');registration.add_argument('bundle');registration.add_argument('--bundle-sha256',required=True)
    for action in ('select','rollback'):
        selection=commands.add_parser(action);selection.add_argument('model_sha');selection.add_argument('--expected-revision',type=int,required=True);selection.add_argument('--reason',required=True)
    args=parser.parse_args()
    try:
        if args.command=='init':result=initialize(args.directory)
        elif args.command=='status':result=status(args.directory)
        elif args.command=='register':result=register(args.directory,args.bundle,bundle_sha256=args.bundle_sha256)
        else:result=select(args.directory,args.model_sha,expected_revision=args.expected_revision,reason=args.reason,rollback=args.command=='rollback')
        print(json.dumps(result,indent=2,allow_nan=False))
    except Exception:
        print(json.dumps({'error':'synthetic_catalog_operation_refused','production_ready':False}));raise SystemExit(2)
