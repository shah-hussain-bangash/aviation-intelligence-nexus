from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from pipelines.verify_import_safety import verify
from pipelines.import_bts import SYNTHETIC_SOURCE


class ImportDrillTests(unittest.TestCase):
    def setUp(self):
        self.environment={k:v for k,v in os.environ.items() if not k.startswith('AIN_') and k!='PORT'}
        self.clean=patch.dict(os.environ,self.environment,clear=True);self.clean.start()
        self.folder=tempfile.TemporaryDirectory();self.root=Path(self.folder.name)

    def tearDown(self):self.folder.cleanup();self.clean.stop()

    def test_complete_drill_retains_reconcilable_synthetic_evidence(self):
        directory=self.root/'case';report=verify(directory)
        self.assertTrue(report['passed'],report);self.assertTrue(all(report['checks'].values()))
        self.assertTrue(report['synthetic_only']);self.assertFalse(report['external_data_imported'])
        self.assertFalse(report['primary_database_accessed']);self.assertFalse(report['production_ready'])
        lineage=report['fixture_lineage'];self.assertEqual(lineage['source'],SYNTHETIC_SOURCE)
        self.assertEqual((lineage['rows_read'],lineage['rows_inserted'],lineage['identical_duplicates']),(4,3,1))
        with closing(sqlite3.connect(directory/'research.sqlite3')) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM flights').fetchone()[0],3)
            self.assertEqual(db.execute('SELECT sha256 FROM imports').fetchone()[0],lineage['archive_sha256'])
        self.assertEqual(json.loads((directory/'report.json').read_text(encoding='utf-8')),report)
        self.assertNotIn(str(directory),json.dumps(report))

    def test_existing_directory_and_runtime_modes_do_not_modify_prior_work(self):
        existing=self.root/'existing';existing.mkdir();marker=existing/'keep.txt';marker.write_text('previous')
        with self.assertRaises(FileExistsError):verify(existing)
        self.assertEqual(marker.read_text(),'previous');self.assertEqual(list(existing.iterdir()),[marker])
        with patch.dict(os.environ,{'AIN_AGENT_JOBS':'1'}):
            with self.assertRaises(ValueError):verify(self.root/'must-not-exist')
        self.assertFalse((self.root/'must-not-exist').exists())

    def test_failure_retains_fixture_and_fixed_error_without_private_details(self):
        directory=self.root/'failed'
        with patch('pipelines.verify_import_safety.import_archive',side_effect=ValueError('PRIVATE-DETAILS')):report=verify(directory)
        self.assertFalse(report['passed']);self.assertEqual(report['failed_stage'],'first_import')
        self.assertTrue((directory/'synthetic.zip').exists());self.assertTrue((directory/'report.json').exists())
        self.assertNotIn('PRIVATE-DETAILS',json.dumps(report))

    def test_real_cli_creates_new_case_and_accepts_no_existing_database_argument(self):
        command=[sys.executable,'-m','pipelines.verify_import_safety']
        result=subprocess.run(command,env=self.environment,capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        report=json.loads(result.stdout);self.assertTrue(report['passed']);self.assertRegex(report['case_id'],'^[0-9a-f]{32}$')
        refused=subprocess.run(command+['--database','PRIVATE-STATE'],env=self.environment,capture_output=True,text=True,timeout=15)
        self.assertEqual(refused.returncode,2)
