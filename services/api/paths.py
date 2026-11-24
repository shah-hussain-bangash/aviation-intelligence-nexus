"""Explicit local state location shared by native and container processes."""
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
STATE=Path(os.environ.get('AIN_STATE_ROOT',str(ROOT/'.local'))).resolve()
SCHEMA_VERSION=8
