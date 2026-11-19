"""Stream an official monthly BTS ZIP into SQLite. Abort atomically on invalid data."""

import argparse
from contextlib import closing
import csv
from datetime import date
import hashlib
import io
import json
import math
from pathlib import Path
import re
import zipfile

from services.api.main import ROOT, connect, initialize

SOURCE = "BTS_REPORTING_CARRIER"
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


def import_archive(archive: Path, database: Path, year: int, month: int):
    date(year, month, 1)  # Validate period before any database mutation.
    period = f"{year:04d}-{month:02d}"
    with archive.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    initialize(database)
    with closing(connect(database)) as connection, connection:
        prior = connection.execute("SELECT * FROM imports WHERE sha256 = ?", (digest,)).fetchone()
        if prior:
            if prior["period"] != period:
                raise ValueError("Previously imported archive has a different declared period")
            return {"status": "already_imported", **dict(prior)}
        with zipfile.ZipFile(archive) as zipped:
            members = [entry for entry in zipped.infolist() if entry.filename.lower().endswith(".csv")]
            if len(members) != 1 or members[0].file_size > 2_000_000_000:
                raise ValueError("Expected one CSV smaller than 2 GB")
            # Read directly from ZIP; never extract supplied paths to disk.
            with zipped.open(members[0]) as raw, io.TextIOWrapper(raw, encoding="utf-8-sig", newline="") as text:
                reader = csv.DictReader(text)
                if not REQUIRED.issubset(reader.fieldnames or []):
                    raise ValueError("Missing required BTS columns")
                count = inserted = duplicates = 0
                for count, row in enumerate(reader, 1):
                    try:
                        values = normalize(row, period)
                    except (ValueError, TypeError, AttributeError) as error:
                        raise ValueError(f"Invalid data at CSV record {count}") from error
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
        url = source_url(year, month)
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
    args = parser.parse_args()
    print(json.dumps(import_archive(args.archive, args.database, args.year, args.month), indent=2))
