"""Read-only coverage of pinned historical import manifests by retained intake archives."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
from pipelines.intake_overview import collect
from pipelines.verify_lineage_handoff import provenance
from services.api.data_quality import load_quality
from services.api.paths import ROOT


def audit(directory):
    snapshot=collect(directory);recorded=load_quality()
    archives={row['sha256']:row for row in snapshot['archives']}
    rows=[];expected_hashes=set();matched_rows=0
    for month in recorded['months']:
        for manifest in month['manifests']:
            sha=manifest['sha256']
            if sha in expected_hashes: raise ValueError('Duplicate recorded archive identity')
            expected_hashes.add(sha);found=archives.get(sha)
            status='missing' if found is None else 'matched' if found['period']==month['period'] and found['declared_rows']==manifest['rows_read'] else 'claim_mismatch'
            if status=='matched':matched_rows+=manifest['rows_read']
            rows.append({'period':month['period'],'archive_sha256':sha,'recorded_rows_read':manifest['rows_read'],
                'status':status,'verified_accepted_runs':found['runs'] if found else 0})
    matched=sum(r['status']=='matched' for r in rows)
    unlinked=[{'period':r['period'],'archive_sha256':r['sha256'],'declared_rows':r['declared_rows']} for r in snapshot['archives'] if r['sha256'] not in expected_hashes]
    matched_months=sum(bool(m['manifests']) and all(r['status']=='matched' for r in rows if r['period']==m['period']) for m in recorded['months'])
    coverage=bool(rows) and matched==len(rows) and matched_months==len(recorded['months'])
    source=provenance()
    source['source_sha256'].update({p:hashlib.sha256((ROOT/p).read_text(encoding='utf-8').encode()).hexdigest() for p in ('pipelines/lineage_coverage.py','pipelines/intake_overview.py','services/api/data_quality.py')})
    return {'format':'ain-lineage-coverage-v1','checked_at':datetime.now(timezone.utc).isoformat(),**source,
        'recorded_audit_report_sha256':recorded['report_sha256'],'expected_months':len(recorded['months']),'matched_months':matched_months,
        'expected_archives':len(rows),'matched_archives':matched,
        'coverage_complete':coverage,'matched_declared_rows':matched_rows,'archives':rows,'unlinked_accepted_archives':unlinked,
        'accepted_runs_checked':snapshot['accepted_runs'],'repeated_accepted_runs':snapshot['repeated_accepted_runs'],
        'quarantined_runs':snapshot['quarantined_runs'],'unverifiable_runs':snapshot['unverifiable_runs'],
        'needs_review':not coverage or bool(unlinked or snapshot['quarantined_runs'] or snapshot['unverifiable_runs']),
        'receipt_authenticated':False,'rows_rescanned':False,'live_database_checked':False,'import_performed':False,'production_ready':False,
        'scope':'Full archive identity and unsigned row/period claims matched to pinned recorded manifests. Not original-import causality, source authentication or current database coverage.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory',type=Path,nargs='?',default=ROOT/'.local/intake')
    args=parser.parse_args()
    try:report=audit(args.directory)
    except (OSError,ValueError,TypeError,KeyError,OverflowError,RecursionError):
        print(json.dumps({'passed':False,'error':'lineage_coverage_unavailable','production_ready':False}));raise SystemExit(2)
    print(json.dumps(report,indent=2))
    if report['needs_review']:raise SystemExit(1)


if __name__=='__main__':main()
