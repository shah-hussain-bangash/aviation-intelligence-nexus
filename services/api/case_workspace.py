"""Explicit local-only case workspace factory; normal release startup is unchanged."""
import os
from pathlib import Path
from services.api.configuration import validate_environment


def create_case_app():
    settings = validate_environment(os.environ)
    if settings.container or not os.environ.get('AIN_STATE_ROOT') or not os.environ.get('AIN_DB_PATH'):
        raise ValueError('Case workspace requires explicit native local state and database paths')
    from services.api.main import create_app
    from services.api.research_cases import ResearchCaseService
    database = Path(os.environ['AIN_DB_PATH'])
    sidecar = Path(os.environ['AIN_STATE_ROOT']) / 'research-cases.sqlite3'
    return create_app(database, research_cases=ResearchCaseService(database, sidecar))
