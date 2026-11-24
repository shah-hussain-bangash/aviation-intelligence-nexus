"""Stream monthly BTS-schema ZIPs into SQLite; generated fixtures require synthetic mode."""

import argparse
from contextlib import closing, contextmanager
import csv
from datetime import date
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import stat
import struct
import tempfile
import time
import zipfile

from services.api.main import ROOT, connect, initialize

SOURCE = "BTS_REPORTING_CARRIER"
SYNTHETIC_SOURCE = 'SYNTHETIC_BTS_SCHEMA'
MAX_ARCHIVE = 512 * 1024 * 1024
MAX_CSV = 2_000_000_000
MAX_ROWS = 5_000_000
SECONDS = 120
REQUIRED = {"FlightDate", "Reporting_Airline", "Flight_Number_Reporting_Airline",
            "Origin", "Dest", "CRSDepTime", "DepDelay", "ArrDelay", "Cancelled", "Diverted"}


def source_url(year, month):
    return ("https://transtats.bts.gov/PREZIP/"
            f"On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{year}_{month}.zip")


def delay(value):
    if not value.strip():
        return None
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Non-finite delay")
    return number


def normalize(row, period):
    flight_date = date.fromisoformat(row["FlightDate"]).isoformat()
    if not flight_date.startswith(period + "-"):
        raise ValueError("Flight date outside declared month")
    carrier, origin, destination = (row[k].strip() for k in ("Reporting_Airline", "Origin", "Dest"))
    if not re.fullmatch(r"[A-Z0-9]{2,3}", carrier):
        raise ValueError("Invalid reporting carrier")
    if not all(re.fullmatch(r"[A-Z]{3}", airport) for airport in (origin, destination)):
        raise ValueError("Invalid airport")
    number = row["Flight_Number_Reporting_Airline"].strip()
    departure = row["CRSDepTime"].strip().zfill(4)
    if not number.isdigit() or not 1 <= int(number) <= 99999:
        raise ValueError("Invalid flight number")
    if not re.fullmatch(r"\d{4}", departure) or not (
        departure == "2400" or (int(departure[:2]) < 24 and int(departure[2:]) < 60)
    ):
        raise ValueError("Invalid scheduled departure")
    flags = [float(row[k]) for k in ("Cancelled", "Diverted")]
    if any(flag not in (0, 1) for flag in flags):
        raise ValueError("Invalid cancellation/diversion flag")
    record_id = "|".join((flight_date, carrier, str(int(number)), origin, destination, departure))
    return (SOURCE, record_id, flight_date, carrier, origin, destination,
            delay(row["DepDelay"]), delay(row["ArrDelay"]), str(int(number)), departure,
            int(flags[0]), int(flags[1]))


def budget(deadline):
    if time.monotonic() >= deadline:raise ValueError('Import exceeded its local time budget')


@contextmanager
def owned_snapshot(archive, deadline):
    """Hash and parse the same private temporary copy; never reopen the source for parsing."""
    archive=Path(archive)
    with archive.open('rb') as source, tempfile.TemporaryFile(mode='w+b') as snapshot:
        before=os.fstat(source.fileno())
        identity=lambda info:(info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns)
        if not stat.S_ISREG(before.st_mode) or identity(archive.lstat())!=identity(before):raise ValueError('Use an ordinary archive file')
        if not 0<before.st_size<=MAX_ARCHIVE:raise ValueError('Archive size is outside the import limit')
        digest=hashlib.sha256();copied=0
        while chunk:=source.read(1024*1024):
            budget(deadline);copied+=len(chunk)
            if copied>MAX_ARCHIVE:raise ValueError('Archive size is outside the import limit')
            snapshot.write(chunk);digest.update(chunk)
        if copied!=before.st_size or identity(os.fstat(source.fileno()))!=identity(before) or identity(archive.lstat())!=identity(before):
            raise ValueError('Archive changed during snapshot capture')
        snapshot.seek(0)
        if hashlib.file_digest(snapshot,'sha256').hexdigest()!=digest.hexdigest():raise ValueError('Archive snapshot could not be verified')
        snapshot.seek(0);budget(deadline)
        yield snapshot,digest.hexdigest()


def bounded_zip_metadata(stream):
    stream.seek(0,2);size=stream.tell();stream.seek(max(0,size-65557));tail=stream.read(65557)
    position=tail.rfind(b'PK\x05\x06')
    if position<0 or len(tail)-position<22:raise ValueError('Invalid ZIP metadata')
    _,disk,start_disk,disk_count,total,directory_size,offset,comment=struct.unpack('<4s4H2LH',tail[position:position+22])
    if len(tail)-position!=22+comment or disk or start_disk or disk_count!=total or not 1<=total<=16 or directory_size>65536 or offset+directory_size>size:
        raise ValueError('Unsupported ZIP metadata')
    stream.seek(0)


class BoundedLines:
    def __init__(self,text,deadline):self.text=text;self.deadline=deadline
    def __iter__(self):return self
    def __next__(self):
        budget(self.deadline);line=self.text.readline(1024*1024+1)
        if not line:raise StopIteration
        if len(line)>1024*1024:raise ValueError('CSV line exceeds the import limit')
        return line


def import_archive(archive: Path, database: Path, year: int, month: int, *, synthetic=False):
    date(year, month, 1)  # Validate period before any database mutation.
    if type(synthetic) is not bool:raise ValueError('Synthetic mode must be explicit')
    period = f"{year:04d}-{month:02d}"
    url = 'urn:ain:synthetic-bts-schema:'+period if synthetic else source_url(year,month)
    deadline=time.monotonic()+SECONDS
    with owned_snapshot(archive,deadline) as (snapshot,digest):
        bounded_zip_metadata(snapshot)
        initialize(database)
        with closing(connect(database)) as connection, connection:
            # The replay lookup and all row/ledger writes share one writer transaction.
            connection.execute('BEGIN IMMEDIATE')
            connection.set_progress_handler(lambda:int(time.monotonic()>=deadline),1000)
            return _import_snapshot(snapshot,connection,digest,period,url,synthetic,deadline)


def _import_snapshot(snapshot,connection,digest,period,url,synthetic,deadline):
    budget(deadline)
    prior = connection.execute("SELECT * FROM imports WHERE sha256 = ?", (digest,)).fetchone()
    if prior:
        if prior["period"] != period or prior['source_url']!=url:
            raise ValueError("Previously imported archive has a different declared period or source scope")
        return {"status": "already_imported", **dict(prior)}
    with zipfile.ZipFile(snapshot) as zipped:
        if not 1<=len(zipped.infolist())<=16:raise ValueError('Unsupported ZIP member count')
        if any(entry.flag_bits&1 or entry.compress_type not in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED) for entry in zipped.infolist()):
            raise ValueError('Unsupported ZIP member encoding')
        members = [entry for entry in zipped.infolist() if entry.filename.lower().endswith(".csv")]
        if len(members) != 1 or members[0].file_size > MAX_CSV:
            raise ValueError("Expected one CSV smaller than 2 GB")
        # Read directly from ZIP; never extract supplied paths to disk.
        with zipped.open(members[0]) as raw, io.TextIOWrapper(raw, encoding="utf-8-sig", newline="") as text:
            reader = csv.DictReader(BoundedLines(text,deadline))
            if not REQUIRED.issubset(reader.fieldnames or []) or len(reader.fieldnames)!=len(set(reader.fieldnames)):
                raise ValueError("Missing required BTS columns")
            count = inserted = duplicates = 0
            for count, row in enumerate(reader, 1):
                budget(deadline)
                if count>MAX_ROWS:raise ValueError('CSV record count exceeds the import limit')
                if None in row or any(value is None for value in row.values()):raise ValueError(f'Invalid CSV shape at record {count}')
                try:
                    values = normalize(row, period)
                except (ValueError, TypeError, AttributeError) as error:
                    raise ValueError(f"Invalid data at CSV record {count}") from error
                if synthetic:values=(SYNTHETIC_SOURCE,*values[1:])
                previous = connection.execute("SELECT source, source_record_id, flight_date, carrier, "
                    "origin, destination, departure_delay_minutes, arrival_delay_minutes, "
                    "flight_number, scheduled_departure, cancelled, diverted FROM flights "
                    "WHERE source = ? AND source_record_id = ?", values[:2]).fetchone()
                if previous:
                    if tuple(previous) != values:
                        raise ValueError(f"Conflicting duplicate at CSV record {count}; revision review required")
                    duplicates += 1
                    continue
                connection.execute("INSERT INTO flights (source, source_record_id, flight_date, carrier, "
                    "origin, destination, departure_delay_minutes, arrival_delay_minutes, flight_number, "
                    "scheduled_departure, cancelled, diverted) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", values)
                inserted += 1
            if count == 0:
                raise ValueError("Empty archive")
    budget(deadline)
    connection.execute("INSERT INTO imports (sha256, source_url, period, rows_read, rows_inserted, "
                       "duplicate_rows) VALUES (?,?,?,?,?,?)", (digest, url, period, count, inserted, duplicates))
    return {"status": "imported", "sha256": digest, "source_url": url, "period": period,
            "rows_read": count, "rows_inserted": inserted, "duplicate_rows": duplicates}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True)
    parser.add_argument("--database", type=Path, default=ROOT / ".local" / "ain.sqlite3")
    parser.add_argument('--synthetic',action='store_true',help='Label generated fixtures as synthetic; never as observed BTS data')
    args = parser.parse_args()
    print(json.dumps(import_archive(args.archive, args.database, args.year, args.month,synthetic=args.synthetic), indent=2))
