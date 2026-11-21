"""Validate local drill receipts and bind them to a specific running source build."""
from datetime import datetime, timezone, timedelta
import re
from infra.state_contracts import current_contract_digest
from services.api.paths import ROOT

FLAGS = ('pinned_images_verified', 'same_volume_preserved', 'row_counts_preserved',
         'account_records_preserved', 'model_index_preserved', 'prediction_parity',
         'candidate_returned_healthy', 'rollback_target_healthy')


def validate_receipt(receipt):
    if not isinstance(receipt, dict) or receipt.get('format') not in ('ain-rollback-drill-v1', 'ain-rollback-drill-v2'):
        raise ValueError('Unsupported rollback receipt')
    if not all(receipt.get(flag) is True for flag in FLAGS) or receipt.get('production_qualified') is not False:
        raise ValueError('Unverified rollback checks')
    if type(receipt.get('flight_records')) is not int or receipt['flight_records'] < 0:
        raise ValueError('Invalid flight count')
    checked = datetime.fromisoformat(receipt['checked_at'])
    if checked.tzinfo is None or checked > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise ValueError('Invalid check timestamp')
    modern = receipt['format'] == 'ain-rollback-drill-v2'
    pattern = '[0-9a-f]{40}' if modern else '[a-z0-9-]{1,64}'
    for field in ('candidate_revision', 'rollback_revision'):
        if not isinstance(receipt.get(field), str) or not re.fullmatch(pattern, receipt[field]):
            raise ValueError('Invalid release revision')
    if modern:
        if receipt['candidate_revision'] == receipt['rollback_revision'] or type(receipt.get('schema_version')) is not int or receipt['schema_version'] < 1 or type(receipt.get('active_jobs_at_start')) is not int or receipt['active_jobs_at_start'] != 0:
            raise ValueError('Invalid drill context')
        if not isinstance(receipt.get('contracts_sha256'), str) or not re.fullmatch('[0-9a-f]{64}', receipt['contracts_sha256']):
            raise ValueError('Missing selected-state contract digest')
        for field in ('candidate_images', 'rollback_images'):
            images = receipt.get(field)
            if not isinstance(images, dict) or set(images) != {'api', 'web'} or any(not isinstance(value, str) or not re.fullmatch('sha256:[0-9a-f]{64}', value) for value in images.values()):
                raise ValueError('Invalid pinned images')
        if receipt['candidate_images'] == receipt['rollback_images']:
            raise ValueError('Identical drill images')
    return receipt


def binding(receipt, revision, schema_version, root=ROOT):
    validate_receipt(receipt)
    result = {'relation': 'legacy_unbound', 'candidate_matches_current_build': False,
              'schema_matches': None, 'state_contracts_match': None, 'current_revision': revision if isinstance(revision, str) and re.fullmatch('[0-9a-f]{40}', revision) else None}
    if receipt['format'] != 'ain-rollback-drill-v2':
        return result
    result['relation'] = 'unverified_build'
    if result['current_revision'] is None:
        return result
    result['schema_matches'] = type(schema_version) is int and schema_version == receipt['schema_version']
    try:
        result['state_contracts_match'] = current_contract_digest(root) == receipt['contracts_sha256']
    except (OSError, ValueError, UnicodeError):
        result['relation'] = 'unavailable_contracts'
        return result
    result['relation'] = ('schema_mismatch' if not result['schema_matches'] else
                          'contract_mismatch' if not result['state_contracts_match'] else
                          'different_release' if revision != receipt['candidate_revision'] else 'matches_current_candidate')
    result['candidate_matches_current_build'] = result['relation'] == 'matches_current_candidate'
    return result
