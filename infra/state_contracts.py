"""Selected persisted-state contracts; this is deliberately not full compatibility proof."""
import hashlib
import json
import re
from services.api.paths import ROOT

CONTRACTS = ('services/api/paths.py', 'services/api/prediction.py', 'agents/jobs.py',
             'agents/store.py', 'agents/runtime.py', 'optimization/history.py',
             'optimization/reviews.py', 'optimization/gates.py', 'rag/index.py', 'infra/recovery.py',
             'services/api/auth.py', 'services/api/account_security.py', 'services/api/security_audit.py',
             'services/api/migrations.py')


def contract_digest(contracts):
    if set(contracts) != set(CONTRACTS) or any(not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value) for value in contracts.values()):
        raise ValueError('Incomplete state contracts')
    return hashlib.sha256(json.dumps(contracts, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def current_contract_digest(root=ROOT):
    contracts = {}
    root = root.resolve()
    for name in CONTRACTS:
        path = root / name
        if path.is_symlink() or not path.resolve().is_relative_to(root) or path.stat().st_size > 2000000:
            raise ValueError('Unavailable state contract')
        contracts[name] = hashlib.sha256(path.read_text(encoding='utf-8').encode()).hexdigest()
    return contract_digest(contracts)
