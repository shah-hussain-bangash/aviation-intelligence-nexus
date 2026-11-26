"""Explicit local-only case workspace factory; normal release startup is unchanged."""
import os
from pathlib import Path
from services.api.configuration import validate_environment


def create_case_app():
    settings = validate_environment(os.environ)
    if settings.container or not os.environ.get('AIN_STATE_ROOT') or not os.environ.get('AIN_DB_PATH'):
        raise ValueError('Case workspace requires explicit native local state and database paths')
    from infra.recovery_state import require_complete_restore
    database = Path(os.environ['AIN_DB_PATH'])
    require_complete_restore(database)
    backup_manifest=database.parent/'case-workspace-backup.json'
    if backup_manifest.exists() or backup_manifest.is_symlink():
        raise ValueError('Backup bundles must be restored to a new workspace before startup')
    from services.api.main import create_app
    from services.api.research_cases import ResearchCaseService
    sidecar = Path(os.environ['AIN_STATE_ROOT']) / 'research-cases.sqlite3'
    return create_app(database, research_cases=ResearchCaseService(database, sidecar))
