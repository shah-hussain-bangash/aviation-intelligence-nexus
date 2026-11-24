from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import csv
import hashlib
import io
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

from pipelines.import_bts import import_archive, SOURCE, SYNTHETIC_SOURCE
from services.api.main import initialize

FIELDS=['FlightDate','Reporting_Airline','Flight_Number_Reporting_Airline','Origin','Dest','CRSDepTime','DepDelay','ArrDelay','Cancelled','Diverted']
ROW=['2025-01-01','XX','1','AAA','BBB','0900','3','7','0','0']


def fixture(path,rows,fields=FIELDS):
    text=io.StringIO(newline='');writer=csv.writer(text);writer.writerow(fields);writer.writerows(rows)
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED) as zipped:zipped.writestr('synthetic.csv',text.getvalue())
    return path


class ImportSafetyTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.root=Path(self.folder.name);self.db=self.root/'research.sqlite3'
        self.archive=fixture(self.root/'synthetic.zip',[ROW,ROW])

    def tearDown(self):self.folder.cleanup()

    def counts(self):
        with closing(sqlite3.connect(self.db)) as db:
            return db.execute('SELECT COUNT(*) FROM flights').fetchone()[0],db.execute('SELECT COUNT(*) FROM imports').fetchone()[0]

    def test_concurrent_replays_commit_one_batch_and_no_duplicate_rows(self):
        initialize(self.db);barrier=threading.Barrier(3)
        def run(_):barrier.wait(timeout=10);return import_archive(self.archive,self.db,2025,1,synthetic=True)
        with ThreadPoolExecutor(max_workers=3) as workers:results=list(workers.map(run,range(3)))
        self.assertEqual(sorted(r['status'] for r in results),['already_imported','already_imported','imported'])
        self.assertEqual(self.counts(),(1,1))
        self.assertEqual(next(r for r in results if r['status']=='imported')['duplicate_rows'],1)

    def test_generated_scope_is_labelled_and_cannot_be_replayed_as_bts(self):
        result=import_archive(self.archive,self.db,2025,1,synthetic=True)
        self.assertEqual(result['source_url'],'urn:ain:synthetic-bts-schema:2025-01')
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute('SELECT DISTINCT source FROM flights').fetchall(),[(SYNTHETIC_SOURCE,)])
            self.assertEqual(db.execute('SELECT COUNT(*) FROM flights WHERE source=?',(SOURCE,)).fetchone()[0],0)
        with self.assertRaisesRegex(ValueError,'source scope'):import_archive(self.archive,self.db,2025,1)
        self.assertEqual(self.counts(),(1,1))

    def test_original_path_change_after_capture_does_not_change_consumed_bytes(self):
        original=self.archive.read_bytes();changed=[*ROW];changed[7]='99'
        replacement=fixture(self.root/'replacement.zip',[changed]).read_bytes()
        def mutate(path):initialize(path);self.archive.write_bytes(replacement)
        with patch('pipelines.import_bts.initialize',side_effect=mutate):
            result=import_archive(self.archive,self.db,2025,1,synthetic=True)
        self.assertEqual(result['sha256'],hashlib.sha256(original).hexdigest())
        self.assertNotEqual(result['sha256'],hashlib.sha256(self.archive.read_bytes()).hexdigest())
        with closing(sqlite3.connect(self.db)) as db:self.assertEqual(db.execute('SELECT arrival_delay_minutes FROM flights').fetchone()[0],7)

    def test_observed_source_change_during_capture_aborts_before_initialization(self):
        real_open=Path.open;target=self.archive
        class ChangedReader:
            def __init__(self,stream):self.stream=stream;self.changed=False
            def __enter__(self):return self
            def __exit__(self,*args):self.stream.close()
            def fileno(self):return self.stream.fileno()
            def read(self,size):
                chunk=self.stream.read(size)
                if not self.changed:
                    self.changed=True
                    with real_open(target,'ab') as stream:stream.write(b'changed')
                return chunk
        def opened(path,*args,**kwargs):
            stream=real_open(path,*args,**kwargs)
            return ChangedReader(stream) if path==target and args and args[0]=='rb' else stream
        with patch.object(Path,'open',opened),patch('pipelines.import_bts.initialize') as init:
            with self.assertRaisesRegex(ValueError,'changed during'):import_archive(self.archive,self.db,2025,1,synthetic=True)
            init.assert_not_called()
        self.assertFalse(self.db.exists())

    def test_conflict_after_new_record_rolls_back_rows_and_ledger(self):
        import_archive(self.archive,self.db,2025,1,synthetic=True)
        new=[*ROW];new[2]='9';changed=[*ROW];changed[7]='99'
        conflict=fixture(self.root/'conflict.zip',[new,changed])
        with self.assertRaisesRegex(ValueError,'Conflicting duplicate'):import_archive(conflict,self.db,2025,1,synthetic=True)
        self.assertEqual(self.counts(),(1,1))

    def test_bad_shape_and_duplicate_headers_cannot_commit_rows(self):
        for label,rows,fields in [('shape',[ROW,ROW+['extra']],FIELDS),('header',[ROW+['extra']],FIELDS+['ArrDelay'])]:
            with self.subTest(label=label):
                archive=fixture(self.root/(label+'.zip'),rows,fields)
                with self.assertRaises(ValueError):import_archive(archive,self.db,2025,1,synthetic=True)
                self.assertEqual(self.counts(),(0,0))

    def test_resource_limits_and_invalid_mode_are_checked_without_partial_commit(self):
        with patch('pipelines.import_bts.MAX_ARCHIVE',1):
            with self.assertRaises(ValueError):import_archive(self.archive,self.db,2025,1,synthetic=True)
        self.assertFalse(self.db.exists())
        with patch('pipelines.import_bts.SECONDS',0):
            with self.assertRaises(ValueError):import_archive(self.archive,self.db,2025,1,synthetic=True)
        with self.assertRaises(ValueError):import_archive(self.archive,self.db,2025,1,synthetic='yes')
        self.assertFalse(self.db.exists())
        with patch('pipelines.import_bts.MAX_ROWS',1):
            with self.assertRaises(ValueError):import_archive(self.archive,self.db,2025,1,synthetic=True)
        self.assertEqual(self.counts(),(0,0))
