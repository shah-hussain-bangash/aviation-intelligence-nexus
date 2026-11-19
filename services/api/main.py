"""Read-only local service. No airline data or trained model is bundled."""

from contextlib import asynccontextmanager, closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from datetime import datetime, timezone
from typing import Literal

from fastapi import FastAPI, Header
from uuid import UUID, uuid4
from fastapi.responses import JSONResponse
from services.api.prediction import ResearchPredictor, Scenario, ScenarioOutOfScope
from services.api.history import IdempotencyConflict, ResearchHistory

ROOT = Path(__file__).resolve().parents[2]


def connect(database: Path):
    connection = sqlite3.connect(database, timeout=5)
    connection.row_factory = sqlite3.Row
    return connection


def initialize(database: Path):
    database.parent.mkdir(parents=True, exist_ok=True)
    with closing(connect(database)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("CREATE TABLE IF NOT EXISTS schema_migrations "
                           "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL "
                           "DEFAULT CURRENT_TIMESTAMP)")
        version = connection.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations").fetchone()[0]
        if version > 3:
            raise RuntimeError("Database schema is newer than this service supports")
        if version == 0:
            connection.execute("""CREATE TABLE flights (
                id INTEGER PRIMARY KEY,
                source TEXT NOT NULL,
                source_record_id TEXT NOT NULL,
                flight_date TEXT NOT NULL,
                carrier TEXT NOT NULL,
                origin TEXT NOT NULL,
                destination TEXT NOT NULL,
                departure_delay_minutes REAL,
                arrival_delay_minutes REAL,
                UNIQUE(source, source_record_id)
            )""")
            connection.execute("INSERT INTO schema_migrations(version) VALUES (1)")
        if version < 2:
            for column, datatype in [("flight_number", "TEXT"), ("scheduled_departure", "TEXT"),
                                     ("cancelled", "INTEGER"), ("diverted", "INTEGER")]:
                connection.execute(f"ALTER TABLE flights ADD COLUMN {column} {datatype}")
            connection.execute("""CREATE TABLE imports (
                sha256 TEXT PRIMARY KEY, source_url TEXT NOT NULL,
                period TEXT NOT NULL, rows_read INTEGER NOT NULL,
                rows_inserted INTEGER NOT NULL, duplicate_rows INTEGER NOT NULL,
                imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )""")
            connection.execute("INSERT INTO schema_migrations(version) VALUES (2)")
        if version < 3:
            connection.execute("""CREATE TABLE research_runs (
                id TEXT PRIMARY KEY, request_key TEXT NOT NULL UNIQUE,
                input_sha256 TEXT NOT NULL, scenario_json TEXT NOT NULL,
                result_json TEXT NOT NULL, model_version TEXT NOT NULL,
                artifact_sha256 TEXT NOT NULL, created_at TEXT NOT NULL
            )""")
            connection.execute("CREATE INDEX research_runs_created ON research_runs(created_at)")
            connection.execute("INSERT INTO schema_migrations(version) VALUES (3)")


def read_model_report(directory: Path):
    try:
        report = json.loads((directory / "report.json").read_text(encoding="utf-8"))
        with (directory / "model.joblib").open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != report["artifact_sha256"]:
            return None
        return report
    except (OSError, ValueError, KeyError, TypeError):
        return None


def create_app(database: Path | None = None, model_directory: Path | None = None,
               research_model_directory: Path | None = None):
    database = Path(database) if database is not None else Path(
        os.environ.get("AIN_DB_PATH", str(ROOT / ".local" / "ain.sqlite3")))
    model_directory = model_directory if model_directory is not None else ROOT / ".local/models/delay-baseline-v1"
    research_model_directory = research_model_directory if research_model_directory is not None else ROOT / ".local/models/delay-v2"
    predictor = ResearchPredictor(research_model_directory)
    history = ResearchHistory(database)

    @asynccontextmanager
    async def lifespan(app):
        initialize(database)
        yield

    app = FastAPI(
        title="Aviation Intelligence Nexus — Local API",
        version="0.2.0",
        description="Local research service: historical aggregates, model reports and bounded scenario inference. No authentication or operational approval.",
        lifespan=lifespan,
    )

    @app.get("/health/live")
    def live():
        return {"status": "ok", "service": "ain-api"}

    @app.get("/health/ready")
    def ready():
        try:
            with closing(connect(database)) as connection:
                connection.execute("SELECT id FROM flights LIMIT 1").fetchone()
            return {"status": "ready", "database": "reachable"}
        except sqlite3.Error:
            return JSONResponse(status_code=503, content={"status": "not_ready", "database": "unavailable"})

    @app.get("/api/v1/status")
    def status():
        try:
            with closing(connect(database)) as connection:
                count = connection.execute("SELECT COUNT(*) FROM flights").fetchone()[0]
            return {
                "stage": "local_backend_foundation",
                "flight_records": count,
                "data_status": "not_imported" if count == 0 else "stored_records_available",
                "model_status": "trained_research_only" if read_model_report(model_directory) else "not_available",
                "prediction_serving": False,
                "research_scenario_endpoint_available": True,
                "dashboard_integration_available": True,
                "production_ready": False,
            }
        except sqlite3.Error:
            return JSONResponse(status_code=503, content={"error": "database_unavailable"})

    @app.get("/api/v1/model/report")
    def model_report():
        report = read_model_report(model_directory)
        if report is None:
            return JSONResponse(status_code=404, content={"error": "verified_model_report_unavailable"})
        return report

    @app.get("/api/v1/models/{version}/report")
    def versioned_report(version: Literal["delay-baseline-v1", "delay-v2"]):
        report = read_model_report(model_directory if version == "delay-baseline-v1" else research_model_directory)
        if report is None:
            return JSONResponse(status_code=404, content={"error": "verified_model_report_unavailable"})
        return report

    @app.get("/api/v1/research/summary")
    def research_summary():
        try:
            with closing(connect(database)) as connection:
                connection.execute("BEGIN")
                dataset = dict(connection.execute("""SELECT COUNT(*) AS records,
                    MIN(flight_date) AS first_date, MAX(flight_date) AS last_date,
                    COUNT(DISTINCT carrier) AS carriers FROM flights WHERE source = 'BTS_REPORTING_CARRIER'""").fetchone())
                monthly = [dict(row) for row in connection.execute("""SELECT substr(flight_date,1,7) AS period,
                    COUNT(*) AS records, SUM(cancelled) AS cancelled, SUM(diverted) AS diverted
                    FROM flights WHERE source = 'BTS_REPORTING_CARRIER'
                    GROUP BY substr(flight_date,1,7) ORDER BY period""")]
                imports = [dict(row) for row in connection.execute(
                    "SELECT period, sha256, source_url, rows_inserted FROM imports ORDER BY period, sha256")]
            report = read_model_report(research_model_directory)
            model = None
            if report:
                try:
                    model = {"version": report["model_version"], "algorithm": report["algorithm"],
                        "training_records": report["training_records"],
                        "validation_records": report["validation"]["model"]["records"],
                        "test_records": report["test"]["model"]["records"],
                        "test_periods": report["protocol"]["period_groups"]["test"],
                        "model_metrics": report["test"]["model"],
                        "baseline_metrics": report["test"]["constant_training_prior"],
                        "threshold": report["threshold"],
                        "research_gate_passed": report["release_assessment"]["research_gate_passed"],
                        "operational_serving_approved": False}
                except (KeyError, TypeError):
                    model = None
            return {"generated_at": datetime.now(timezone.utc).isoformat(),
                "source_scope": "US domestic historical flights; not UAE airline operations",
                "dataset": {**dataset, "monthly": monthly, "imports": imports},
                "model": model, "prediction_serving": False, "production_ready": False}
        except sqlite3.Error:
            return JSONResponse(status_code=503, content={"error": "research_database_unavailable"})

    @app.post("/api/v1/research/predict")
    def predict_scenario(scenario: Scenario, idempotency_key: UUID | None = Header(default=None)):
        key = str(idempotency_key or uuid4())
        payload = scenario.model_dump(mode="json")
        try:
            existing = history.lookup(key, payload)
            if existing:
                return existing
            return history.save(key, payload, predictor.predict(scenario))
        except IdempotencyConflict:
            return JSONResponse(status_code=409, content={"error": "request_key_conflict",
                "message": "This request key belongs to different inputs. Use a new request key."})
        except sqlite3.Error:
            return JSONResponse(status_code=503, content={"error": "research_history_unavailable",
                "message": "The local database is unavailable. No new result was saved or returned."})
        except ScenarioOutOfScope as error:
            return JSONResponse(status_code=422, content={"error": "outside_training_vocabulary",
                "fields": error.fields, "message": "Use carrier and airport codes observed in the US training data. No probability was produced."})
        except Exception:
            return JSONResponse(status_code=503, content={"error": "research_model_unavailable",
                "message": "A verified research model could not produce a result. No probability was produced."})

    @app.get("/api/v1/research/history")
    def research_history():
        try:
            return {"runs": history.recent(), "limit": 10, "actor_scope": "anonymous_local",
                    "research_only": True, "tamper_proof": False}
        except (sqlite3.Error, ValueError):
            return JSONResponse(status_code=503, content={"error": "research_history_unavailable"})

    return app


app = create_app()
