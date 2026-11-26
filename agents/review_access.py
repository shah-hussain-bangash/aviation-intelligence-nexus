"""Explicit, pending-only sharing for optional second-account research review."""
import hashlib
import json


def peer_pending(run):
    try:
        if 'case_context' in run['request']:return False
        expected=hashlib.sha256(json.dumps({k:run[k] for k in ('request','steps','claims')},sort_keys=True).encode()).hexdigest()
        return run['request'].get('require_peer_review') is True and run['state']=='awaiting_review' and run.get('report_sha256')==expected and run['research_only'] is True and run['operational_approval'] is False
    except (ValueError,TypeError,KeyError):return False


def can_read(user,owner_id,run):
    if 'case_context' in run['request']:return user['id']==owner_id
    return user['id']==owner_id or user['role']=='admin' or user['role']=='researcher' and peer_pending(run)


def view(run,user,owner_id):
    if run['request'].get('require_peer_review') is not True:return run
    author=user['id']==owner_id
    return {**run,'review_access':{'second_account_required':True,'is_author':author,
        'can_review':user['role'] in ('researcher','admin') and not author and peer_pending(run),
        'can_withdraw':(author or user['role']=='admin') and peer_pending(run),
        'scope':'Different local account, not proof of a different person or operational authority'}}
