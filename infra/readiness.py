"""Read-only, dated scope assessment with allowlisted public evidence integrity."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from services.api.paths import ROOT


def evidence_path(root, name):
    if not isinstance(name, str) or not re.fullmatch(r'docs/(?:reports/)?[A-Za-z0-9_.-]+\.(?:md|json)', name):
        raise ValueError('Unsupported evidence path')
    target = root / name
    if target.is_symlink() or not target.resolve().is_relative_to(root.resolve()):
        raise ValueError('Evidence path escapes public source')
    return target


def digest(path):
    if path.stat().st_size > 2_000_000:
        raise ValueError('Oversized public evidence')
    # Git checkouts can convert text line endings on Windows. Compare canonical LF text.
    return hashlib.sha256(path.read_text(encoding='utf-8').encode('utf-8')).hexdigest()


def assessment(root=ROOT):
    root = Path(root)
    catalog_path = root / 'infra/readiness.json'
    if catalog_path.stat().st_size > 128000:
        raise ValueError('Oversized readiness assessment')
    catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
    rows = catalog['requirements']
    if catalog.get('format') != 'ain-readiness-v1' or catalog.get('production_ready') is not False or catalog.get('fingerprint_policy') != 'sha256-utf8-lf-v1':
        raise ValueError('Unsupported readiness claim')
    datetime.fromisoformat(catalog['assessed_at'])
    if len(rows) != 24 or {r['id'] for r in rows} != {f'P{i:02}' for i in range(1, 25)}:
        raise ValueError('Incomplete requirement coverage')
    baseline = evidence_path(root, catalog['baseline_path'])
    if digest(baseline) != catalog['baseline_sha256']:
        raise ValueError('Baseline changed; reassessment required')
    baseline_ids = {r['id'] for r in json.loads(baseline.read_text(encoding='utf-8'))['production_requirements']}
    if baseline_ids != {r['id'] for r in rows}:
        raise ValueError('Requirement scope differs from baseline')
    revision = os.environ.get('AIN_RELEASE_REVISION', '')
    revision = revision if re.fullmatch('[0-9a-f]{40}', revision) else 'main'
    result = []
    for row in rows:
        if row['production_accepted'] is not False or any(dep not in baseline_ids for dep in row['dependencies']):
            raise ValueError('Unsupported acceptance or dependency')
        for field in ['name', 'owner_role', 'local_progress', 'remaining', 'acceptance']:
            if not isinstance(row[field], str) or not row[field].strip():
                raise ValueError('Missing assessment content')
        evidence = []
        for item in row['evidence']:
            path = evidence_path(root, item['path'])
            if not re.fullmatch('[0-9a-f]{64}', item['sha256']):
                raise ValueError('Invalid evidence fingerprint')
            try:
                available = digest(path) == item['sha256']
            except OSError:
                available = False
            evidence.append({**item, 'integrity_verified': available,
                'url': f'https://github.com/zenithdevelopers7-source/aviation-intelligence-nexus/blob/{revision}/{item["path"]}'})
        state = 'local_evidence' if evidence and all(e['integrity_verified'] for e in evidence) else 'evidence_unavailable' if evidence else 'planned'
        result.append({**row, 'evidence': evidence, 'assessment_state': state})
    return {'format': catalog['format'], 'assessed_at': catalog['assessed_at'], 'scope': catalog['scope'],
            'checked_at': datetime.now(timezone.utc).isoformat(),
            'source_revision': revision, 'catalog_sha256': digest(catalog_path),
            'requirements': result, 'total': 24, 'production_accepted': 0, 'production_open': 24,
            'with_local_evidence': sum(r['assessment_state'] == 'local_evidence' for r in result),
            'evidence_unavailable': sum(r['assessment_state'] == 'evidence_unavailable' for r in result),
            'production_ready': False,
            'meaning': 'File integrity verifies recorded public evidence, not implementation correctness, current runtime health or independent production acceptance.'}
