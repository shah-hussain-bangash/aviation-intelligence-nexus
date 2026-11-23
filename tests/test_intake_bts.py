import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
import struct
import unittest
from unittest.mock import patch
import zipfile
from pipelines.intake_bts import intake

FIELDS = ['FlightDate','Reporting_Airline','Flight_Number_Reporting_Airline','Origin','Dest','CRSDepTime','DepDelay','ArrDelay','Cancelled','Diverted']
ROW = ['2025-01-01','AA','1','JFK','LAX','0900','','','0','0']


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.root = Path(self.temp.name)
        self.archive = self.root / 'input.zip';self.output = self.root / 'intake'

    def tearDown(self):self.temp.cleanup()
    def write(self, rows=None, fields=None, name='data.csv', readme=False):
        text = io.StringIO(newline='');writer = csv.writer(text);writer.writerow(FIELDS if fields is None else fields)
        writer.writerows([ROW] if rows is None else rows)
        with zipfile.ZipFile(self.archive,'w',compression=zipfile.ZIP_DEFLATED) as zipped:
            zipped.writestr(name,text.getvalue())
            if readme:zipped.writestr('readme.html','<p>Synthetic fixture; do not execute.</p>')
    def run_intake(self):return intake(self.archive,self.output,2025,1)

    def test_official_layout_snapshot_preserved_without_primary_database_calls(self):
        self.write(rows=[ROW+['']],fields=FIELDS+[''],readme=True)
        before=self.archive.read_bytes()
        with patch('pipelines.import_bts.initialize',side_effect=AssertionError('Primary DB touched')), patch('pipelines.import_bts.connect',side_effect=AssertionError('Primary DB touched')):
            result=self.run_intake()
        self.assertEqual(result['disposition'],'accepted');self.assertEqual(result['rows_read'],1)
        self.assertFalse(result['primary_database_accessed']);self.assertFalse(result['origin_verified'])
        self.assertEqual(self.archive.read_bytes(),before)
        saved=self.output/'accepted'/result['run_id']/'archive.zip'
        self.assertEqual(hashlib.sha256(saved.read_bytes()).hexdigest(),result['archive_sha256'])
        self.assertFalse(list(self.output.rglob('*.sqlite3')))

    def test_identical_duplicates_counted_conflicting_duplicate_quarantined(self):
        self.write([ROW,ROW]);result=self.run_intake()
        self.assertEqual(result['unique_identities'],1);self.assertEqual(result['identical_duplicates'],1)
        changed=ROW.copy();changed[7]='20';self.write([ROW,changed]);result=self.run_intake()
        self.assertEqual(result['disposition'],'quarantined');self.assertEqual(result['reason_code'],'conflicting_identity')
        self.assertFalse(result['scan_complete'])

    def test_invalid_period_and_numeric_record_do_not_leak_raw_values(self):
        changed=ROW.copy();changed[0]='PRIVATE-INVALID';self.write([changed])
        result=self.run_intake();self.assertEqual(result['reason_code'],'invalid_record')
        self.assertNotIn('PRIVATE-INVALID',json.dumps(result));self.assertEqual(result['rows_read'],1)
        changed=ROW.copy();changed[7]='NaN';self.write([changed])
        self.assertEqual(self.run_intake()['reason_code'],'invalid_record')

    def test_schema_duplicate_headers_short_rows_and_nonempty_trailing_field_rejected(self):
        for fields,rows,reason in [(FIELDS+[FIELDS[0]],[ROW+['extra']],'schema_invalid'),
                                   (FIELDS,[ROW[:-1]],'record_shape'),(FIELDS+[''],[ROW+['unexpected']],'record_shape')]:
            self.write(rows,fields);self.assertEqual(self.run_intake()['reason_code'],reason)

    def test_unsafe_members_and_multiple_csvs_are_quarantined_without_extraction(self):
        self.write(name='../outside.csv');result=self.run_intake()
        self.assertEqual(result['reason_code'],'unsafe_zip_member');self.assertFalse((self.root/'outside.csv').exists())
        self.write()
        with zipfile.ZipFile(self.archive,'a') as zipped:zipped.writestr('second.csv','x')
        self.assertEqual(self.run_intake()['reason_code'],'csv_member_count')

    def test_empty_and_non_zip_inputs_retained_in_quarantine(self):
        self.write([]);self.assertEqual(self.run_intake()['reason_code'],'empty_csv')
        self.archive.write_bytes(b'not a zip');result=self.run_intake()
        self.assertEqual(result['reason_code'],'invalid_zip')
        self.assertFalse(result['scratch_database_used'])
        self.assertEqual((self.output/'quarantined'/result['run_id']/'archive.zip').read_bytes(),b'not a zip')

    def test_resource_limits_do_not_accept_partial_scans(self):
        self.write([ROW,ROW])
        with patch('pipelines.intake_bts.MAX_ROWS',1):result=self.run_intake()
        self.assertEqual(result['reason_code'],'row_limit');self.assertFalse(result['scan_complete'])
        with patch('pipelines.intake_bts.MAX_ARCHIVE',1):
            with self.assertRaises(ValueError):self.run_intake()

    def test_repeat_runs_preserve_separate_receipts_and_source(self):
        self.write();first=self.run_intake();second=self.run_intake()
        self.assertNotEqual(first['run_id'],second['run_id'])
        self.assertEqual(first['archive_sha256'],second['archive_sha256'])
        self.assertTrue((self.output/'accepted'/first['run_id']/'receipt.json').is_file())

    def test_crc_corruption_is_retained_without_accepting_csv(self):
        self.write()
        with zipfile.ZipFile(self.archive) as zipped:entry=zipped.getinfo('data.csv')
        raw=bytearray(self.archive.read_bytes())
        offset=entry.header_offset+30+len(entry.filename.encode())+len(entry.extra)
        raw[offset+entry.compress_size-2]^=1
        self.archive.write_bytes(raw)
        result=self.run_intake()
        self.assertEqual(result['disposition'],'quarantined')
        self.assertFalse(result['csv_crc_verified'])

    def test_central_directory_entry_limit_precedes_zipfile_allocation(self):
        self.write();raw=bytearray(self.archive.read_bytes());offset=raw.rfind(b'PK\x05\x06')
        struct.pack_into('<H',raw,offset+8,65535);struct.pack_into('<H',raw,offset+10,65535)
        self.archive.write_bytes(raw)
        with patch('pipelines.intake_bts.zipfile.ZipFile',side_effect=AssertionError('Unbounded ZIP parsing attempted')):
            result=self.run_intake()
        self.assertEqual(result['reason_code'],'unsupported_zip_metadata')

    def test_scan_time_budget_quarantines_without_claiming_complete_scan(self):
        self.write();clock=iter([0.0,0.0,121.0,122.0]).__next__
        result=intake(self.archive,self.output,2025,1,clock=clock)
        self.assertEqual(result['reason_code'],'time_budget')
        self.assertFalse(result['scan_complete'])

    def test_invalid_deflate_stream_is_quarantined_as_corrupt_zip(self):
        self.write()
        with zipfile.ZipFile(self.archive) as zipped:entry=zipped.getinfo('data.csv')
        raw=bytearray(self.archive.read_bytes())
        offset=entry.header_offset+30+len(entry.filename.encode())+len(entry.extra)
        raw[offset]|=0x06  # Reserved DEFLATE block type, not merely a CRC mismatch.
        self.archive.write_bytes(raw)
        result=self.run_intake()
        self.assertEqual(result['reason_code'],'corrupt_zip')
        self.assertEqual(result['disposition'],'quarantined')

    def test_signed_zero_delays_follow_importer_numeric_duplicate_equality(self):
        negative=ROW.copy();negative[6]='-0.0'
        positive=ROW.copy();positive[6]='0.0'
        self.write([negative,positive]);result=self.run_intake()
        self.assertEqual(result['disposition'],'accepted')
        self.assertEqual(result['identical_duplicates'],1)
