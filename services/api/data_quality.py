"""Pinned recorded structural audit; HTTP reads public aggregates only."""
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
from services.api.paths import ROOT

REPORT='docs/reports/BTS_Data_Quality.json'
REPORT_SHA256='f81ec38046dfcf2da7e9cfa173cb4cd6a99d324f04292314fe08812a8f01b424'
DATASET='docs/reports/BTS_Jan_May_2025_Dataset_v2.json'
DATASET_SHA256='93899afd60771a9c1c17ad0411fefcd249b486b655b7c8ebf8c20800dee9c0a1'
PERIODS=[f'2025-{m:02}' for m in range(1,6)]
FIELDS=['date','carrier','origin','destination','flight_number','scheduled_departure','flags','arrival_delay','departure_delay','record_key']
COHORTS=['eligible_arrivals','excluded_cancelled','excluded_diverted','excluded_missing_or_invalid']


def integer(value):
    if type(value) is not int or value<0:raise ValueError('Invalid audit count')
    return value


def validate_report(report):
    if report['format']!='ain-data-quality-v1' or report['research_only'] is not True or report['production_ready'] is not False or report['source']!='BTS_REPORTING_CARRIER' or report['audited_periods']!=PERIODS:
        raise ValueError('Unsupported audit scope')
    if datetime.fromisoformat(report['checked_at']).tzinfo is None:raise ValueError('Missing audit time zone')
    if type(report['elapsed_seconds']) not in (int,float) or not math.isfinite(report['elapsed_seconds']) or report['elapsed_seconds']<0 or not re.fullmatch('[0-9a-f]{64}',report['query_sha256']):raise ValueError('Invalid audit measurement')
    if [m['period'] for m in report['months']]!=PERIODS:raise ValueError('Incomplete month coverage')
    issues=0;records=0
    for row in report['months']:
        n=integer(row['records']);records+=n
        if sorted(row['field_issues'])!=sorted(FIELDS) or sorted(row['cohorts'])!=sorted(COHORTS):raise ValueError('Incomplete audit checks')
        if any(integer(v)>n for v in row['field_issues'].values()) or integer(row['duplicate_keys'])>n or sum(integer(v) for v in row['cohorts'].values())!=n:
            raise ValueError('Invalid field/cohort accounting')
        issues+=sum(row['field_issues'].values())+row['duplicate_keys']
        if len(row['manifests'])>1000:raise ValueError('Manifest bound exceeded')
        for entry in row['manifests']:
            if not re.fullmatch('[0-9a-f]{64}',entry['sha256']) or integer(entry['rows_read'])!=integer(entry['rows_inserted'])+integer(entry['duplicate_rows']):
                raise ValueError('Invalid recorded import accounting')
        inserted=sum(e['rows_inserted'] for e in row['manifests'])
        expected='missing' if not row['manifests'] else 'matched' if inserted==n else 'mismatched'
        if row['manifest_rows_inserted']!=inserted or row['import_reconciliation']!=expected:raise ValueError('Invalid import reconciliation')
    if records!=integer(report['profiled_records']) or records+integer(report['unprofiled_source_records'])!=integer(report['source_records']) or issues!=integer(report['field_issue_occurrences']) or integer(report['invalid_dates_all_source'])>report['source_records']:
        raise ValueError('Audit totals do not reconcile')
    integer(report['other_source_records']);integer(report['invalid_manifest_entries'])
    passed=bool(report['source_records']) and report['profiled_records']==report['source_records'] and not (report['invalid_dates_all_source'] or issues or report['invalid_manifest_entries']) and all(m['records']>0 and m['import_reconciliation']=='matched' for m in report['months'])
    if report['checks_passed'] is not passed:raise ValueError('Unsupported audit result')
    return report


def read_pinned(root,name,expected):
    path=Path(root)/name
    if path.is_symlink() or path.stat().st_size>150000:raise ValueError('Invalid fixed audit evidence')
    text=path.read_text(encoding='utf-8')
    if hashlib.sha256(text.encode()).hexdigest()!=expected:raise ValueError('Audit evidence changed')
    return json.loads(text)


def load_quality(root=ROOT):
    report=validate_report(read_pinned(root,REPORT,REPORT_SHA256))
    dataset=read_pinned(root,DATASET,DATASET_SHA256)
    eligible={m['period']:m['cohorts']['eligible_arrivals'] for m in report['months']}
    alignment={}
    for split,periods in dataset['period_groups'].items():
        observed=sum(eligible[p] for p in periods);frozen=dataset['splits'][split]['eligible_records']
        alignment[split]={'audited_eligible':observed,'frozen_eligible':frozen,'counts_match':observed==frozen}
    return {**report,'integrity_verified':True,'report_sha256':REPORT_SHA256,'dataset_report_sha256':DATASET_SHA256,
        'modelling_alignment':alignment,'alignment_meaning':'Count reconciliation only; not proof of row identity, CSV hashes, source truth or live database state.'}
