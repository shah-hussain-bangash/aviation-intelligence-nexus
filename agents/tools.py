"""Typed, allowlisted research tools. The model never supplies SQL or paths."""
from contextlib import closing
import json
import sqlite3
import time
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from rag.service import Question
from optimization.gates import GateScenario, optimize


class EmptyArgs(BaseModel):
    model_config = ConfigDict(extra='forbid')


class SearchArgs(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    question: str = Field(min_length=8, max_length=600)


class MonthArgs(EmptyArgs):
    month: Literal['2025-01','2025-02','2025-03','2025-04','2025-05'] | None = None


ARGUMENTS={'flight_metrics':MonthArgs,'knowledge_search':SearchArgs,'gate_simulation':EmptyArgs}


def definitions(simulation):
    descriptions = [
        ('flight_metrics','Read actual historical BTS counts and arrival-delay frequency. Month must equal the user-selected month. Never live or UAE data.',MonthArgs),
        ('knowledge_search','Retrieve cited public project evidence about models, data and optimization. No generated answer in this tool.',SearchArgs)]
    if simulation:
        descriptions.append(('gate_simulation','Compute an independently checked five-flight SYNTHETIC gate proposal, separate from the historical flight data.',EmptyArgs))
    return [{'type':'function','function':{'name':name,'description':description,'parameters':model.model_json_schema()}}
            for name,description,model in descriptions]


def flight_metrics(database, month):
    upper = f'2025-{int(month[-2:])+1:02d}-01'
    deadline = time.monotonic() + 5
    with closing(sqlite3.connect(Path(database).resolve().as_uri()+'?mode=ro',uri=True,timeout=3)) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        db.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
        row = dict(db.execute('''SELECT COUNT(*) AS records,
            SUM(CASE WHEN cancelled=1 THEN 1 ELSE 0 END) AS cancelled,
            SUM(CASE WHEN diverted=1 THEN 1 ELSE 0 END) AS diverted,
            SUM(CASE WHEN cancelled=0 AND diverted=0 AND arrival_delay_minutes IS NOT NULL THEN 1 ELSE 0 END) AS eligible,
            SUM(CASE WHEN cancelled=0 AND diverted=0 AND arrival_delay_minutes>=15 THEN 1 ELSE 0 END) AS delayed_15
            FROM flights WHERE source=? AND flight_date>=? AND flight_date<?''',
            ('BTS_REPORTING_CARRIER',month+'-01',upper)).fetchone())
    if not row['records']:
        return {'data_kind':'historical_bts','month':month,'available':False,'records':0,
            'evidence_text':f'No imported BTS records were found for {month}; no delay rate was calculated.'}
    rate = row['delayed_15']/row['eligible'] if row['eligible'] else None
    text = '\n'.join([f'Historical US BTS data for {month} contains {row["records"]} imported flights.',
        f'There are {row["cancelled"]} cancelled flights and {row["diverted"]} diverted flights.',
        f'The completed, non-diverted observed-delay population contains {row["eligible"]} flights; {row["delayed_15"]} arrived at least 15 minutes late.',
        f'The observed arrival-delay rate is {rate:.4%}.' if rate is not None else 'No observed arrival-delay rate is available.',
        'These are historical US measurements, not predictions, current operations or UAE airline results.'])
    return {**row,'month':month,'available':True,'data_kind':'historical_bts','arrival_delay_rate':rate,
            'query_version':'bts-month-v1','evidence_text':text}


def gate_sample():
    return GateScenario.model_validate({'data_kind':'synthetic','buffer_minutes':10,
        'gates':[{'id':'N1','capacity':'narrow'},{'id':'W1','capacity':'wide'}],
        'flights':[
            {'id':'SIM-101','aircraft':'narrow','arrival':480,'departure':600,'costs':{'N1':6,'W1':1}},
            {'id':'SIM-202','aircraft':'wide','arrival':500,'departure':590,'costs':{'N1':20,'W1':3}},
            {'id':'SIM-303','aircraft':'narrow','arrival':605,'departure':680,'costs':{'N1':2,'W1':2}},
            {'id':'SIM-404','aircraft':'narrow','arrival':700,'departure':760,'costs':{'N1':1,'W1':4}},
            {'id':'SIM-505','aircraft':'wide','arrival':780,'departure':840,'costs':{'N1':20,'W1':2}}]})


def execute(name, arguments, request, database, knowledge):
    if name == 'knowledge_search':
        args = SearchArgs.model_validate(arguments)
        result = knowledge.query(Question(question=args.question,generate=False))
        return {'data_kind':'project_documents','available':bool(result['evidence']),
            'evidence':result['evidence'],'index_sha256':result['index_sha256'],
            'evidence_text':'\n\n'.join(row['text'] for row in result['evidence']) or 'No matching project evidence was retrieved.'}
    if name == 'flight_metrics':
        args=MonthArgs.model_validate(arguments)
        if args.month is not None and args.month != request.month: raise ValueError('Tool month differs from user scope')
        return flight_metrics(database, request.month)
    EmptyArgs.model_validate(arguments)
    if name == 'gate_simulation' and request.include_simulation:
        result = optimize(gate_sample())
        checked, baseline = result['candidate']['verification'], result['baseline']['verification']
        return {'data_kind':'synthetic','available':True,'result':result,
            'evidence_text':f'Synthetic gate demonstration: optimized coverage is {checked["assigned"]} of 5 flights; greedy coverage is {baseline["assigned"]} of 5 flights.\n'
                f'The independently verified assignment cost is {checked["assignment_cost"]} synthetic units.\n'
                'This simulation is independent of the historical BTS data and cannot establish an operational recovery recommendation.'}
    raise ValueError('Tool is not permitted')
