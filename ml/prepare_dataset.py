"""Build a fixed chronological Q1 2025 arrival-delay classification dataset."""

import argparse
from contextlib import closing
import csv
from datetime import date
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

from pipelines.import_bts import SOURCE
from services.api.main import ROOT, connect

FEATURES = ["carrier", "origin", "destination", "flight_number", "month",
            "day_of_month", "day_of_week", "scheduled_departure_hour", "scheduled_departure_minute"]
TARGET = "arrival_delayed_15"
PERIODS = {"train": "2025-01", "validation": "2025-02", "test": "2025-03"}


def next_month(period):
    year, month = map(int, period.split("-"))
    date(year, month, 1)
    return f"{year + (month == 12):04d}-{month % 12 + 1:02d}"


def validate_groups(groups):
    if list(groups) != ["train", "validation", "test"] or any(not months for months in groups.values()):
        raise ValueError("Expected nonempty train, validation and test groups in temporal order")
    flattened = [month for months in groups.values() for month in months]
    if len(set(flattened)) != len(flattened):
        raise ValueError("Overlapping periods")
    for month in flattened:
        if next_month(month) <= month or len(month) != 7:
            raise ValueError("Invalid period")
    if any(next_month(left) != right for left, right in zip(flattened, flattened[1:])):
        raise ValueError("Periods must be consecutive and ordered")


def prepare(database: Path, destination: Path, period_groups=None, dataset_version="bts-q1-2025-v1"):
    groups = period_groups if period_groups is not None else {name: [period] for name, period in PERIODS.items()}
    validate_groups(groups)
    if destination.exists():
        raise ValueError("Dataset destination already exists; choose a new version")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="dataset-", dir=destination.parent))
    report = {
        "dataset_version": dataset_version, "features": FEATURES,
        "target": TARGET, "target_rule": "arrival_delay_minutes >= 15",
        "prediction_context": "Scheduled-flight risk before departure, conditional on completed non-diverted flights",
        "split_policy": "Consecutive chronological groups; no random shuffle", "period_groups": groups,
        "source_scope": "US domestic reporting carriers; not UAE operations",
        "excluded_fields": ["departure_delay_minutes", "arrival_delay_minutes", "cancelled", "diverted"],
        "limitations": ["Historical reported schedules, not point-in-time schedule snapshots",
                       "Short historical coverage does not establish seasonal generalization",
                       "Test labels must remain unused during feature selection and tuning",
                       "No model trained or operational performance measured"],
        "splits": {},
    }
    try:
        with closing(connect(database)) as connection:
            connection.execute("BEGIN")  # Consistent read snapshot across all splits and manifests.
            report["source_imports"] = []
            for name, months in groups.items():
                for period in months:
                    manifests = connection.execute("SELECT sha256, source_url, period, rows_read, rows_inserted, "
                        "duplicate_rows FROM imports WHERE period = ? ORDER BY sha256", (period,)).fetchall()
                    if not manifests:
                        raise ValueError(f"Required imported period missing: {period}")
                    report["source_imports"].extend(dict(row) for row in manifests)
                info = {"period": months[0] if len(months) == 1 else months[0] + ".." + months[-1],
                        "periods": months, "input_records": 0, "eligible_records": 0,
                        "excluded_cancelled": 0, "excluded_diverted": 0,
                        "excluded_missing_or_invalid": 0}
                output = staging / f"{name}.csv"
                with output.open("w", newline="", encoding="utf-8") as stream:
                    writer = csv.writer(stream, lineterminator="\n")
                    writer.writerow(["record_key", "flight_date", *FEATURES, TARGET])
                    rows = connection.execute("SELECT source_record_id, flight_date, carrier, origin, destination, "
                        "flight_number, scheduled_departure, arrival_delay_minutes, cancelled, diverted "
                        "FROM flights WHERE source = ? AND flight_date >= ? AND flight_date < ? "
                        "ORDER BY flight_date, source_record_id", (SOURCE, months[0] + "-01",
                        next_month(months[-1]) + "-01"))
                    for row in rows:
                        info["input_records"] += 1
                        if row["cancelled"] == 1:
                            info["excluded_cancelled"] += 1
                            continue
                        if row["diverted"] == 1:
                            info["excluded_diverted"] += 1
                            continue
                        if (row["cancelled"] != 0 or row["diverted"] != 0 or
                            row["arrival_delay_minutes"] is None or
                            not row["flight_number"] or not row["scheduled_departure"]):
                            info["excluded_missing_or_invalid"] += 1
                            continue
                        day = date.fromisoformat(row["flight_date"])
                        scheduled = row["scheduled_departure"]
                        writer.writerow([row["source_record_id"], row["flight_date"], row["carrier"],
                            row["origin"], row["destination"], row["flight_number"], day.month,
                            day.day, day.isoweekday(), int(scheduled[:2]), int(scheduled[2:]),
                            int(row["arrival_delay_minutes"] >= 15)])
                        info["eligible_records"] += 1
                if not info["eligible_records"]:
                    raise ValueError(f"No eligible records in {period}")
                with output.open("rb") as stream:
                    info["sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
                report["splits"][name] = info
        (staging / "manifest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        staging.rename(destination)
    except BaseException:
        shutil.rmtree(staging)
        raise
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=ROOT / ".local" / "ain.sqlite3")
    parser.add_argument("--output", type=Path, default=ROOT / ".local" / "datasets" / "bts-q1-2025-v1")
    args = parser.parse_args()
    print(json.dumps(prepare(args.database, args.output), indent=2))
