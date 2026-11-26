import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from services.api.case_workspace import create_case_app


class CaseWorkspaceTests(unittest.TestCase):
    def test_explicit_paths_required_before_sidecar_creation(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError): create_case_app()
        with patch.dict(os.environ, {'AIN_CONTAINER':'1','AIN_STATE_ROOT':'/app/.local/active','AIN_DB_PATH':'/app/.local/active/ain.sqlite3'}, clear=True):
            with self.assertRaises(ValueError): create_case_app()

    def test_factory_uses_separate_fixed_store_in_explicit_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with patch.dict(os.environ, {'AIN_ENV':'test','AIN_STATE_ROOT':directory,'AIN_DB_PATH':str(root/'auth.sqlite3')}, clear=True):
                app=create_case_app()
            self.assertTrue((root/'research-cases.sqlite3').is_file())
            self.assertIsNotNone(app)
