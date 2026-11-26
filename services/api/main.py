"""Authenticated local research service. No airline data or trained model is bundled."""

from contextlib import asynccontextmanager, closing
import hashlib
import json
import os
import time
from pathlib import Path
import sqlite3
from datetime import datetime, timezone
from typing import Literal

from fastapi import FastAPI, Header, Request
from pydantic import BaseModel, ConfigDict, Field
import hmac
from uuid import UUID, uuid4
from fastapi.responses import JSONResponse
from services.api.configuration import validate_environment
from services.api.migrations import MigrationHistoryError, history_version, require_current
from infra.recovery_state import require_complete_restore

# Fail before project imports resolve state paths or construct services.
validate_environment(os.environ)
from services.api.prediction import ResearchPredictor, Scenario, ScenarioOutOfScope
from services.api.history import IdempotencyConflict, ResearchHistory
from services.api.auth import AuthStore, COOKIE, SESSION_SECONDS, LoginDenied, LoginLimited, csrf_token
from services.api.account_security import account_sessions, SessionInvalid
from services.api.security_audit import AUDIT_TABLE_SQL, AUDIT_TRIGGER_SQL, latest_events, require_audit_contract
from optimization.gates import GateScenario, optimize
from optimization.history import GateRunStore
from optimization.reviews import GateReview,ReviewConflict
from rag.service import Knowledge, Question
from rag.history import EvidenceHistory
from rag import ollama
from agents.runtime import Investigation, Investigator, Review
from agents.store import AgentStore, Conflict
from services.api.paths import STATE, SCHEMA_VERSION
from infra.status import restore_status, encrypted_drill_status, rollback_drill_status
from infra.local_observer import deployment_status as observer_deployment_status
from services.api.monitoring import Monitor
from services.api.agent_operations import snapshot as agent_operations_snapshot, OperationsUnavailable
from infra.readiness import assessment
from agents.jobs import JobQueue, JobWorker, QueueFull
from agents.archive import ArchiveQuery, page as archive_page
from agents.review_inbox import inbox as review_inbox
from agents.withdrawal import SharingWithdrawal
from services.api.segments import load_segments
from services.api.data_quality import load_quality
from services.api.intake_overview import load_overview
from services.api.batch_lineage import load_lineage
from services.api.request_context import install_request_context
from services.api.diagnostics import load_diagnostics
from services.api.thresholds import load_thresholds
from services.api.duration import load_duration
from services.api.retrieval_evaluation import load_retrieval_evaluation
from services.api.scoped_lab import ScopedLabQuery,run as run_scoped_lab
from services.api.distributions import load_distributions
from services.api.explanations import load_explanations
from services.api.route_history import lookup as lookup_route, LookupBusy, LookupUnavailable, RouteNotObserved
from services.api.synthetic_scoring import SyntheticScoreRequest,SyntheticScoringService
from services.api.research_cases import ResearchCaseService, OpenCase, ChangeCase, AttachEvidence, CaseConflict, CaseMissing
from services.api.case_agents import AttachAgent

ROOT = Path(__file__).resolve().parents[2]


class LoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(pattern=r"^[a-zA-Z0-9_.-]{3,32}$")
    password: str = Field(min_length=1, max_length=128)


class CancelJob(BaseModel):
    model_config = ConfigDict(extra='forbid')
    run_id: UUID


class RevokeSessions(BaseModel):
    model_config=ConfigDict(extra='forbid')
    acknowledged: bool=Field(strict=True)


def connect(database: Path):
    connection = sqlite3.connect(database, timeout=5)
    connection.row_factory = sqlite3.Row
    return connection


def initialize(database: Path):
    require_complete_restore(database)
    database.parent.mkdir(parents=True, exist_ok=True)
    with closing(connect(database)) as connection, connection:
        # Reject bad history before changing journal mode; repeat under the write lock.
        existing_version = history_version(connection, SCHEMA_VERSION, allow_empty=True)
        if existing_version == SCHEMA_VERSION:
            require_audit_contract(connection)
        # Local WAL permits checkpoint writes while the dashboard holds a historical read snapshot.
        if connection.execute('PRAGMA journal_mode=WAL').fetchone()[0] != 'wal':
            raise RuntimeError('Local database could not enable concurrent read/checkpoint storage')
        connection.execute("BEGIN IMMEDIATE")
        version = history_version(connection, SCHEMA_VERSION, allow_empty=True)
        connection.execute("CREATE TABLE IF NOT EXISTS schema_migrations "
                           "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL "
                           "DEFAULT CURRENT_TIMESTAMP)")
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
        if version < 4:
            connection.execute("CREATE TABLE auth_users(id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE, "
                               "password_hash TEXT NOT NULL, role TEXT NOT NULL, active INTEGER NOT NULL)")
            connection.execute("CREATE TABLE auth_sessions(token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires_at REAL NOT NULL)")
            connection.execute("CREATE TABLE auth_limits(key TEXT PRIMARY KEY, failures INTEGER NOT NULL, window_start REAL NOT NULL)")
            connection.execute("ALTER TABLE research_runs ADD COLUMN owner_id TEXT")
            connection.execute("CREATE INDEX research_runs_owner ON research_runs(owner_id,created_at)")
            connection.execute("INSERT INTO schema_migrations(version) VALUES (4)")
        if version < 5:
            connection.execute("CREATE TABLE gate_runs(id TEXT PRIMARY KEY,owner_id TEXT NOT NULL,request_key TEXT NOT NULL, "
                "scenario_hash TEXT NOT NULL,result_json TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(owner_id,request_key))")
            connection.execute("CREATE INDEX gate_runs_owner ON gate_runs(owner_id,created_at)")
            connection.execute("INSERT INTO schema_migrations(version) VALUES (5)")
        if version < 6:
            connection.execute("CREATE TABLE knowledge_runs(id TEXT PRIMARY KEY,owner_id TEXT NOT NULL,result_json TEXT NOT NULL,created_at TEXT NOT NULL)")
            connection.execute("CREATE INDEX knowledge_runs_owner ON knowledge_runs(owner_id,created_at)")
            connection.execute("INSERT INTO schema_migrations(version) VALUES (6)")
        if version < 7:
            connection.execute("CREATE TABLE agent_runs(id TEXT PRIMARY KEY,owner_id TEXT NOT NULL,request_key TEXT NOT NULL,input_hash TEXT NOT NULL,result_json TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(owner_id,request_key))")
            connection.execute("CREATE INDEX agent_runs_owner ON agent_runs(owner_id,updated_at)")
            connection.execute("INSERT INTO schema_migrations(version) VALUES (7)")
        if version < 8:
            connection.execute(AUDIT_TABLE_SQL)
            for sql in AUDIT_TRIGGER_SQL.values():
                connection.execute(sql)
            connection.execute("INSERT INTO schema_migrations(version) VALUES (8)")
        require_current(connection, SCHEMA_VERSION)
        require_audit_contract(connection)


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
               research_model_directory: Path | None = None, knowledge_index: Path | None = None,
               synthetic_scoring: SyntheticScoringService | None = None,
               research_cases: ResearchCaseService | None = None):
    config=validate_environment(os.environ)
    database = Path(database) if database is not None else Path(
        os.environ.get("AIN_DB_PATH", str(STATE / "ain.sqlite3")))
    model_directory = model_directory if model_directory is not None else STATE / "models/delay-baseline-v1"
    if research_cases is not None and research_cases.source_database.resolve() != database.resolve():
        raise ValueError('Research case source must match the authenticated database')
    research_model_directory = research_model_directory if research_model_directory is not None else STATE / "models/delay-v2"
    predictor = ResearchPredictor(research_model_directory)
    history = ResearchHistory(database)
    gate_history = GateRunStore(database)
    knowledge = Knowledge() if knowledge_index is None else Knowledge(knowledge_index)
    knowledge_history = EvidenceHistory(database)
    agent_store = AgentStore(database)
    investigator = Investigator(database,knowledge,agent_store)
    job_queue = JobQueue(agent_store)
    job_worker = JobWorker(job_queue, investigator, enabled=config.agent_jobs)
    auth = AuthStore(database)
    def database_probe():
        with closing(connect(database)) as connection:
            require_current(connection, SCHEMA_VERSION)
            require_audit_contract(connection)
            return True

    def ai_probe():
        installed = ollama.models()
        return ollama.EMBED_MODEL in installed and ollama.CHAT_MODEL in installed

    monitor = Monitor(database.parent / 'monitoring.json', {
        'database': database_probe,
        'active_model': lambda: read_model_report(research_model_directory) is not None,
        'local_ai_models': ai_probe,
    }, enabled=config.monitor)
    origins = {f"http://{host}:{port}" for host in ("127.0.0.1", "localhost")
               for port in (config.web_port,config.api_port)}

    @asynccontextmanager
    async def lifespan(app):
        initialize(database)
        agent_store.recover()
        monitor.start()
        job_worker.start()
        try:
            yield
        finally:
            await job_worker.stop()
            await monitor.stop()

    app = FastAPI(
        title="Aviation Intelligence Nexus — Local API",
        version="0.2.0",
        description="Local authenticated research service with server-enforced roles. Loopback development only; no operational approval.",
        lifespan=lifespan,
    )
    app.state.auth_store = auth
    app.state.monitor = monitor
    app.state.job_worker = job_worker

    @app.middleware("http")
    async def require_session(request: Request, call_next):
        if not request.url.path.startswith("/api/v1/"):
            return await call_next(request)
        unsafe = request.method not in ("GET", "HEAD", "OPTIONS")
        if unsafe and request.headers.get("origin") not in origins:
            return JSONResponse(status_code=403, content={"error": "origin_rejected"})
        try:
            token = request.cookies.get(COOKIE, "")
            user = auth.session(token)
            request.state.user = user
            public = request.url.path in ("/api/v1/auth/login", "/api/v1/auth/session")
            if not public and not user:
                return JSONResponse(status_code=401, content={"error": "sign_in_required"})
            if unsafe and request.url.path != "/api/v1/auth/login":
                if not user or not hmac.compare_digest(request.headers.get("x-csrf-token", ""), csrf_token(token)):
                    return JSONResponse(status_code=403, content={"error": "csrf_rejected"})
            if request.url.path in ("/api/v1/research/predict", "/api/v1/research/optimize-gates", "/api/v1/research/gate-review", "/api/v1/research/knowledge-query", "/api/v1/research/scoped-query", "/api/v1/research/synthetic-score", "/api/v1/research/agent-run", "/api/v1/research/agent-review", "/api/v1/research/agent-jobs", "/api/v1/research/agent-cancel") and request.method == "POST" and user["role"] not in ("admin", "researcher"):
                return JSONResponse(status_code=403, content={"error": "researcher_role_required"})
        except sqlite3.Error:
            return JSONResponse(status_code=503, content={"error": "identity_store_unavailable"})
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.middleware('http')
    async def measure_requests(request: Request, call_next):
        started = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            monitor.record(500, (time.monotonic() - started) * 1000)
            raise
        # Health probes and metrics polling should not inflate research request metrics.
        if request.url.path.startswith('/api/v1/') and (request.url.path != '/api/v1/research/monitoring' or response.status_code >= 400):
            monitor.record(response.status_code, (time.monotonic() - started) * 1000)
        return response

    # Registered last so early identity/CSRF failures also receive a server request ID.
    install_request_context(app)

    @app.get('/api/v1/research/agent-operations')
    def agent_operations(request: Request):
        if request.state.user['role']!='admin':
            return JSONResponse(status_code=403,content={'error':'administrator_role_required'})
        try:
            return agent_operations_snapshot(database,job_worker.status())
        except OperationsUnavailable:
            return JSONResponse(status_code=503,content={'error':'agent_operations_unavailable',
                'message':'Current queue observations could not be verified. Previous status must be cleared.'})

    @app.get('/api/v1/research/monitoring')
    def monitoring(request: Request):
        if request.state.user['role'] != 'admin':
            return JSONResponse(status_code=403, content={'error': 'admin_role_required'})
        return monitor.snapshot()

    @app.get('/api/v1/research/security-audit')
    def security_audit(request: Request):
        if request.state.user['role'] != 'admin':
            return JSONResponse(status_code=403, content={'error':'admin_role_required'})
        if request.query_params:
            return JSONResponse(status_code=422, content={'error':'query_not_allowed'})
        try:
            return latest_events(database)
        except (sqlite3.Error, OSError, ValueError):
            return JSONResponse(status_code=503, content={'error':'security_audit_unavailable'})

    @app.get('/api/v1/research/input-distributions')
    def input_distributions(request: Request):
        try:return load_distributions()
        except (OSError,ValueError,KeyError,TypeError):return JSONResponse(status_code=503,content={'error':'recorded_input_distributions_unavailable'})

    @app.get("/api/v1/auth/session")
    def auth_session(request: Request):
        user = request.state.user
        try:
            return {"authenticated": bool(user), "user": user,
                    "csrf_token": csrf_token(request.cookies[COOKIE]) if user else None,
                    "enrollment_required": auth.enrollment_required(), "local_development_only": True}
        except sqlite3.Error:
            return JSONResponse(status_code=503, content={"error": "identity_store_unavailable"})

    @app.post("/api/v1/auth/login")
    def login(credentials: LoginInput, request: Request):
        try:
            token = auth.login(credentials.username, credentials.password, request_id=request.state.request_id)
            response = JSONResponse({"authenticated": True, "user": auth.session(token), "csrf_token": csrf_token(token)})
            response.set_cookie(COOKIE, token, max_age=SESSION_SECONDS, httponly=True, samesite="strict", secure=False, path="/api")
            return response
        except LoginLimited:
            return JSONResponse(status_code=429, content={"error": "login_rate_limited", "message": "Try again after one minute."})
        except LoginDenied:
            return JSONResponse(status_code=401, content={"error": "invalid_credentials"})
        except sqlite3.Error:
            return JSONResponse(status_code=503, content={"error": "identity_store_unavailable"})

    @app.post("/api/v1/auth/logout")
    def logout(request: Request):
        try:
            auth.logout(request.cookies[COOKIE], request_id=request.state.request_id)
        except sqlite3.Error:
            return JSONResponse(status_code=503, content={'error':'sign_out_unconfirmed'})
        response = JSONResponse({"authenticated": False})
        response.delete_cookie(COOKIE, path="/api", httponly=True, samesite="strict")
        return response

    @app.get('/api/v1/auth/security')
    def account_security(request: Request):
        if request.query_params:return JSONResponse(status_code=422,content={'error':'unexpected_security_parameters'})
        try:return account_sessions(database,request.cookies.get(COOKIE,''))
        except SessionInvalid:return JSONResponse(status_code=401,content={'error':'sign_in_required'})
        except (sqlite3.Error,OSError,TimeoutError,ValueError,TypeError,OverflowError):return JSONResponse(status_code=503,content={'error':'account_security_unavailable'})

    @app.post('/api/v1/auth/revoke-other-sessions')
    def revoke_other_sessions(confirmation: RevokeSessions,request: Request):
        if request.query_params or not confirmation.acknowledged:return JSONResponse(status_code=422,content={'error':'explicit_confirmation_required'})
        try:return account_sessions(database,request.cookies.get(COOKIE,''),revoke_others=True,request_id=request.state.request_id)
        except SessionInvalid:return JSONResponse(status_code=401,content={'error':'sign_in_required'})
        except (sqlite3.Error,OSError,TimeoutError,ValueError,TypeError,OverflowError):return JSONResponse(status_code=503,content={'error':'session_revocation_unconfirmed'})

    @app.get("/health/live")
    def live():
        return {"status": "ok", "service": "ain-api"}

    @app.get("/health/ready")
    def ready():
        try:
            with closing(connect(database)) as connection:
                require_current(connection, SCHEMA_VERSION)
                require_audit_contract(connection)
                connection.execute("SELECT id FROM flights LIMIT 1").fetchone()
            return {"status": "ready", "database": "reachable"}
        except (sqlite3.Error, MigrationHistoryError):
            return JSONResponse(status_code=503, content={"status": "not_ready", "database": "unavailable"})

    @app.get("/api/v1/status")
    def status():
        try:
            with closing(connect(database)) as connection:
                require_current(connection, SCHEMA_VERSION)
                require_audit_contract(connection)
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
        except (sqlite3.Error, MigrationHistoryError):
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
    def predict_scenario(scenario: Scenario, request: Request, idempotency_key: UUID | None = Header(default=None)):
        key = str(idempotency_key or uuid4())
        payload = scenario.model_dump(mode="json")
        try:
            existing = history.lookup(key, payload, request.state.user["id"])
            if existing:
                return existing
            return history.save(key, payload, predictor.predict(scenario), request.state.user)
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
    def research_history(request: Request):
        try:
            user = request.state.user
            return {"runs": history.recent(user["id"], user["role"] == "admin"), "limit": 10,
                    "actor_scope": "all_local_runs" if user["role"] == "admin" else "own_runs",
                    "research_only": True, "tamper_proof": False}
        except (sqlite3.Error, ValueError):
            return JSONResponse(status_code=503, content={"error": "research_history_unavailable"})

    @app.post("/api/v1/research/optimize-gates")
    def optimize_gates(scenario: GateScenario, request: Request, idempotency_key: UUID | None = Header(default=None)):
        key = str(idempotency_key or uuid4())
        user = request.state.user
        try:
            existing = gate_history.lookup(user,key,scenario.model_dump())
            return existing or gate_history.save(user,key,optimize(scenario))
        except ValueError:
            return JSONResponse(status_code=409,content={"error":"request_key_conflict"})
        except (RuntimeError,sqlite3.Error):
            return JSONResponse(status_code=503,content={"error":"verified_optimization_unavailable"})

    @app.post('/api/v1/research/gate-review')
    def review_gate_proposal(review: GateReview, request: Request):
        try:
            return gate_history.review(request.state.user,review)
        except PermissionError:
            return JSONResponse(status_code=403,content={'error':'researcher_role_required'})
        except KeyError:
            return JSONResponse(status_code=404,content={'error':'gate_proposal_unavailable'})
        except ReviewConflict as error:
            return JSONResponse(status_code=409,content={'error':'gate_review_blocked','message':str(error)})
        except (sqlite3.Error,ValueError,TypeError):
            return JSONResponse(status_code=503,content={'error':'gate_review_unavailable','message':'No decision confirmed. Refresh the saved proposal before retrying.'})

    @app.get("/api/v1/research/gate-history")
    def gate_runs(request: Request):
        try:
            return {"runs":gate_history.recent(request.state.user),"research_only":True}
        except (sqlite3.Error,ValueError,TypeError,KeyError):
            return JSONResponse(status_code=503,content={"error":"optimization_history_unavailable"})

    @app.get('/api/v1/research/knowledge-status')
    def knowledge_status():
        return knowledge.status()

    def case_response(request, operation, write=False):
        if request.query_params:
            return JSONResponse(status_code=422,content={'error':'unexpected_case_parameters'})
        user = auth.session(request.cookies.get(COOKIE,''))
        if not user or user['id'] != request.state.user['id'] or (write and user['role'] not in ('admin','researcher')):
            return JSONResponse(status_code=403,content={'error':'case_access_denied'})
        if research_cases is None:
            return JSONResponse(status_code=503,content={'error':'research_cases_not_configured'})
        try: return operation(user)
        except PermissionError: return JSONResponse(status_code=403,content={'error':'case_access_denied'})
        except CaseMissing: return JSONResponse(status_code=404,content={'error':'case_or_source_unavailable'})
        except CaseConflict: return JSONResponse(status_code=409,content={'error':'case_version_or_request_conflict'})
        except (sqlite3.Error, ValueError, TypeError, KeyError):
            return JSONResponse(status_code=503,content={'error':'research_case_unavailable'})

    @app.get('/api/v1/research/case-sources')
    def case_sources(request: Request):
        return case_response(request,lambda user:{'sources':research_cases.sources(user),'production_ready':False})

    @app.get('/api/v1/research/cases')
    def case_list(request: Request):
        return case_response(request,lambda user:{'cases':research_cases.recent(user),'production_ready':False})

    @app.get('/api/v1/research/cases/{case_id}')
    def case_detail(case_id: UUID, request: Request):
        return case_response(request,lambda user:research_cases.get(user,case_id))

    @app.post('/api/v1/research/cases')
    def case_open(payload: OpenCase, request: Request, idempotency_key: UUID = Header(alias='Idempotency-Key')):
        return case_response(request,lambda user:research_cases.open(user,payload,idempotency_key),write=True)

    @app.post('/api/v1/research/cases/{case_id}/events')
    def case_event(case_id: UUID, payload: ChangeCase, request: Request):
        return case_response(request,lambda user:research_cases.change(user,case_id,payload),write=True)

    @app.get('/api/v1/research/case-evidence-sources')
    def case_evidence_sources(request: Request):
        return case_response(request,lambda user:{'sources':research_cases.evidence_sources(user),'production_ready':False})

    @app.post('/api/v1/research/cases/{case_id}/evidence')
    def case_attach_evidence(case_id:UUID,payload:AttachEvidence,request:Request):
        return case_response(request,lambda user:research_cases.attach_evidence(user,case_id,payload),write=True)

    @app.get('/api/v1/research/cases/{case_id}/evidence/{run_id}')
    def case_attached_evidence(case_id:UUID,run_id:UUID,request:Request):
        return case_response(request,lambda user:research_cases.attached_evidence(user,case_id,run_id))

    @app.get('/api/v1/research/case-agent-sources')
    def case_agent_sources(request:Request):
        return case_response(request,lambda user:{'sources':research_cases.agent_sources(user),'production_ready':False})

    @app.post('/api/v1/research/cases/{case_id}/agents')
    def case_attach_agent(case_id:UUID,payload:AttachAgent,request:Request):
        return case_response(request,lambda user:research_cases.attach_agent(user,case_id,payload),write=True)

    @app.get('/api/v1/research/cases/{case_id}/agents/{run_id}')
    def case_attached_agent(case_id:UUID,run_id:UUID,request:Request):
        return case_response(request,lambda user:research_cases.attached_agent(user,case_id,run_id))

    @app.get('/api/v1/research/synthetic-scoring')
    def synthetic_scoring_context(request:Request):
        if request.state.user['role'] not in ('admin','researcher'):
            return JSONResponse(status_code=403,content={'error':'researcher_role_required'})
        if request.query_params:return JSONResponse(status_code=422,content={'error':'unexpected_synthetic_scoring_parameters'})
        if synthetic_scoring is None:return {'available':False,'source_scope':'synthetic','production_ready':False}
        try:return synthetic_scoring.context()
        except Exception:return JSONResponse(status_code=503,content={'error':'synthetic_scoring_unavailable'})

    @app.post('/api/v1/research/synthetic-score')
    def synthetic_score(query:SyntheticScoreRequest,request:Request):
        if request.query_params:return JSONResponse(status_code=422,content={'error':'unexpected_synthetic_scoring_parameters'})
        try:
            token=request.cookies.get(COOKIE,'');current=auth.session(token)
            if not current or current['role'] not in ('admin','researcher') or current['id']!=request.state.user['id']:
                return JSONResponse(status_code=403,content={'error':'researcher_role_required'})
            if synthetic_scoring is None:return JSONResponse(status_code=503,content={'error':'synthetic_scoring_not_configured'})
            result=synthetic_scoring.run(query)
            after=auth.session(token)
            if not after or after['id']!=current['id'] or after['role'] not in ('admin','researcher'):
                return JSONResponse(status_code=403,content={'error':'access_changed'})
            return result
        except Exception:return JSONResponse(status_code=503,content={'error':'synthetic_scoring_unavailable'})

    @app.post('/api/v1/research/scoped-query')
    def scoped_query(query:ScopedLabQuery,request:Request):
        if request.query_params:return JSONResponse(status_code=422,content={'error':'unexpected_scoped_query_parameters'})
        try:
            token=request.cookies.get(COOKIE,'');current=auth.session(token)
            if not current or current['role'] not in ('admin','researcher') or current['id']!=request.state.user['id']:
                return JSONResponse(status_code=403,content={'error':'researcher_role_required'})
            result=run_scoped_lab(query,knowledge)
            after=auth.session(token)
            if not after or after['id']!=current['id'] or after['role'] not in ('admin','researcher'):
                return JSONResponse(status_code=403,content={'error':'access_changed','message':'Access changed during the query. Results were withheld.'})
            return result
        except (OSError,ValueError,KeyError,TypeError,RuntimeError,sqlite3.Error):
            return JSONResponse(status_code=503,content={'error':'scoped_query_unavailable','message':'No verified result returned. Check the trusted index and local model service.'})

    @app.post('/api/v1/research/knowledge-query')
    def knowledge_query(question: Question, request: Request):
        try:
            return knowledge_history.save(request.state.user, knowledge.query(question))
        except (OSError, ValueError, KeyError, TypeError, RuntimeError, sqlite3.Error):
            return JSONResponse(status_code=503, content={'error': 'knowledge_unavailable',
                'message': 'No saved result returned. Check the index, local models and database.'})

    @app.get('/api/v1/research/knowledge-history')
    def knowledge_runs(request: Request):
        try:
            return {'runs': knowledge_history.recent(request.state.user), 'research_only': True}
        except (sqlite3.Error, ValueError):
            return JSONResponse(status_code=503, content={'error': 'knowledge_history_unavailable'})

    @app.get('/api/v1/research/agent-status')
    def agent_status():
        try:
            available = ollama.CHAT_MODEL in ollama.models()
        except (OSError, ValueError, KeyError, TypeError):
            available = False
        return {'available':available,'model':ollama.CHAT_MODEL,'max_tool_calls':3,
            'background_worker':job_worker.status(),
            'tools':['flight_metrics','knowledge_search','model_evidence (explicit opt-in; recorded experiments)','route_history (explicit route scope required)','gate_simulation (opt-in synthetic only)'],
            'research_only':True,'operational_writes':False}

    @app.post('/api/v1/research/agent-run')
    def agent_run(investigation: Investigation,request: Request,idempotency_key: UUID = Header()):
        if job_worker.enabled:
            return JSONResponse(status_code=409, content={'error': 'background_jobs_required', 'message': 'Submit this investigation to the saved background queue.'})
        try:
            return investigator.run(request.state.user,str(idempotency_key),investigation)
        except Conflict:
            return JSONResponse(status_code=409,content={'error':'request_conflict_or_busy','message':'Refresh saved investigations before retrying; use a new request key only for a new request.'})
        except (OSError,ValueError,KeyError,TypeError,RuntimeError,sqlite3.Error):
            return JSONResponse(status_code=503,content={'error':'agent_unavailable','message':'No completed investigation could be confirmed. Refresh saved investigations.'})

    @app.get('/api/v1/research/agent-history')
    def agent_history(request: Request):
        try: return {'runs':agent_store.recent(request.state.user),'research_only':True}
        except (sqlite3.Error,ValueError): return JSONResponse(status_code=503,content={'error':'agent_history_unavailable'})

    @app.get('/api/v1/research/agent-archive')
    def agent_archive(request: Request):
        try:
            pairs=list(request.query_params.multi_items())
            if len(pairs)!=len(dict(pairs)):raise ValueError('Repeated parameters')
            query=ArchiveQuery.model_validate(dict(pairs))
        except ValueError:
            return JSONResponse(status_code=422,content={'error':'invalid_archive_query'})
        try:return archive_page(database,request.state.user,query)
        except (sqlite3.Error,ValueError,OSError,TimeoutError,TypeError):
            return JSONResponse(status_code=503,content={'error':'agent_archive_unavailable'})

    @app.get('/api/v1/research/agent-review-inbox')
    def agent_review_inbox(request: Request):
        if request.query_params:return JSONResponse(status_code=422,content={'error':'unexpected_review_query'})
        try:return review_inbox(database,request.state.user)
        except PermissionError:return JSONResponse(status_code=403,content={'error':'researcher_role_required'})
        except (sqlite3.Error,OSError,ValueError,TypeError,TimeoutError):return JSONResponse(status_code=503,content={'error':'review_inbox_unavailable'})

    @app.post('/api/v1/research/agent-jobs', status_code=202)
    def enqueue_investigation(investigation: Investigation, request: Request, idempotency_key: UUID = Header()):
        if not job_worker.enabled or not job_worker.task or job_worker.task.done() or job_worker.last_error:
            return JSONResponse(status_code=503, content={'error': 'background_worker_unavailable'})
        try:
            return job_queue.enqueue(request.state.user, str(idempotency_key), investigation)
        except QueueFull:
            return JSONResponse(status_code=429, content={'error': 'investigation_queue_full', 'message': 'Waiting queue is full. Wait for existing jobs; retry the same request key.'})
        except Conflict:
            return JSONResponse(status_code=409, content={'error': 'request_key_conflict'})
        except (sqlite3.Error, OSError, ValueError):
            return JSONResponse(status_code=503, content={'error': 'investigation_queue_unavailable'})

    @app.get('/api/v1/research/agent-jobs/{run_id}')
    def investigation_job(run_id: UUID, request: Request):
        try:
            return job_queue.get(request.state.user, str(run_id))
        except KeyError:
            return JSONResponse(status_code=404, content={'error': 'investigation_unavailable'})
        except (sqlite3.Error, ValueError):
            return JSONResponse(status_code=503, content={'error': 'investigation_queue_unavailable'})

    @app.post('/api/v1/research/agent-cancel')
    def cancel_investigation(job: CancelJob, request: Request):
        try:
            result=job_queue.cancel(request.state.user, str(job.run_id))
            return JSONResponse(status_code=202,content=result) if result['state']=='running' else result
        except KeyError:
            return JSONResponse(status_code=404, content={'error': 'investigation_unavailable'})
        except PermissionError:
            return JSONResponse(status_code=403,content={'error':'researcher_role_required'})
        except Conflict:
            return JSONResponse(status_code=409, content={'error': 'investigation_not_active', 'message': 'The investigation is no longer queued or running. Refresh saved state; completed reports are unchanged.'})
        except (sqlite3.Error, ValueError):
            return JSONResponse(status_code=503, content={'error': 'investigation_queue_unavailable'})

    @app.post('/api/v1/research/agent-review')
    def agent_review(review: Review,request: Request):
        try: return agent_store.review(request.state.user,str(review.run_id),review.report_sha256,review.decision,review.note,session_token=request.cookies.get(COOKIE,''))
        except PermissionError:return JSONResponse(status_code=403,content={'error':'researcher_role_required'})
        except KeyError: return JSONResponse(status_code=404,content={'error':'investigation_unavailable'})
        except Conflict as error: return JSONResponse(status_code=409,content={'error':'review_blocked','message':str(error)})
        except (sqlite3.Error,ValueError): return JSONResponse(status_code=503,content={'error':'review_not_saved'})

    @app.post('/api/v1/research/agent-withdraw-sharing')
    def withdraw_agent_sharing(withdrawal: SharingWithdrawal,request: Request):
        try:return agent_store.withdraw_sharing(request.state.user,withdrawal,session_token=request.cookies.get(COOKIE,''))
        except KeyError:return JSONResponse(status_code=404,content={'error':'investigation_unavailable'})
        except PermissionError:return JSONResponse(status_code=403,content={'error':'sharing_withdrawal_not_permitted'})
        except Conflict:return JSONResponse(status_code=409,content={'error':'sharing_withdrawal_conflict','message':'Refresh the saved report; it changed, was withdrawn or already has a research decision.'})
        except (sqlite3.Error,ValueError,TypeError):return JSONResponse(status_code=503,content={'error':'sharing_withdrawal_unconfirmed'})

    @app.get('/api/v1/research/platform-status')
    def platform_status():
        try:
            with closing(connect(database)) as db:
                require_current(db, SCHEMA_VERSION)
                require_audit_contract(db)
            database_ready=True
        except (sqlite3.Error, MigrationHistoryError):
            database_ready=False
        try:
            installed=ollama.models();ai_models_present=ollama.EMBED_MODEL in installed and ollama.CHAT_MODEL in installed
        except (OSError,ValueError,KeyError,TypeError,RuntimeError):ai_models_present=False
        return {'runtime':'local-container' if os.environ.get('AIN_CONTAINER')=='1' else 'local-native',
            'release_revision':os.environ.get('AIN_RELEASE_REVISION','development-working-tree'),
            'database_ready':database_ready,'schema_version':SCHEMA_VERSION if database_ready else None,
            'active_model_verified':read_model_report(research_model_directory) is not None,
            'ai_models_present':ai_models_present,'recovery':restore_status(database.parent),
            'encrypted_backup_drill':encrypted_drill_status(database.parent),
            'independent_observer':observer_deployment_status(database.parent),
            'rollback_drill':rollback_drill_status(database.parent, schema_version=SCHEMA_VERSION if database_ready else None),
            'production_ready':False,'limitations':['Local deployment and recorded recovery checks do not establish production qualification.',
                'No managed TLS, cloud monitoring, protected backup storage or high-availability worker service is configured.']}

    @app.get('/api/v1/research/readiness')
    def release_readiness():
        try:
            return assessment()
        except (OSError, ValueError, KeyError, TypeError):
            return JSONResponse(status_code=503, content={'error': 'readiness_evidence_unavailable',
                'message': 'The scope/evidence assessment could not be verified. No readiness claim is returned.'})

    @app.get('/api/v1/research/batch-lineage')
    def batch_lineage(request: Request):
        if request.query_params:
            return JSONResponse(status_code=422,content={'error':'query_not_allowed'})
        try: return load_lineage(database.parent,request.state.user['role'])
        except (OSError,ValueError,TypeError,KeyError,OverflowError,RecursionError):
            return JSONResponse(status_code=503,content={'error':'batch_lineage_unavailable'})

    @app.get('/api/v1/research/intake-overview')
    def intake_overview(request: Request):
        if request.state.user['role'] != 'admin':
            return JSONResponse(status_code=403,content={'error':'admin_role_required'})
        if request.query_params:
            return JSONResponse(status_code=422,content={'error':'query_not_allowed'})
        try: return load_overview(database.parent)
        except (OSError,ValueError,TypeError,KeyError,OverflowError,RecursionError):
            return JSONResponse(status_code=503,content={'error':'intake_overview_unavailable'})

    @app.get('/api/v1/research/data-quality')
    def data_quality():
        try:
            return load_quality()
        except (OSError,ValueError,KeyError,TypeError):
            return JSONResponse(status_code=503,content={'error':'data_quality_evidence_unavailable',
                'message':'The recorded data audit could not be verified. Audit results are withheld.'})

    @app.get('/api/v1/research/model-explanations')
    def model_explanations():
        try:
            return load_explanations()
        except (OSError, ValueError, KeyError, TypeError, ZeroDivisionError):
            return JSONResponse(status_code=503, content={'error':'model_explanations_unavailable',
                'message':'Recorded permutation evidence could not be verified. Explanations are withheld.'})

    @app.get('/api/v1/research/retrieval-diagnostics')
    def retrieval_diagnostics(request: Request):
        if request.query_params:return JSONResponse(status_code=422,content={'error':'retrieval_query_not_supported'})
        try:return load_retrieval_evaluation()
        except (OSError,ValueError,KeyError,TypeError,ZeroDivisionError):return JSONResponse(status_code=503,content={'error':'retrieval_evidence_unavailable','message':'Recorded retrieval evidence could not be verified. Results are withheld.'})

    @app.get('/api/v1/research/duration-evaluation')
    def duration_evaluation(request: Request):
        if request.query_params:return JSONResponse(status_code=422,content={'error':'duration_query_not_supported'})
        try:return load_duration()
        except (OSError,ValueError,KeyError,TypeError,ZeroDivisionError):return JSONResponse(status_code=503,content={'error':'duration_evidence_unavailable','message':'Recorded duration evidence could not be verified. Results are withheld.'})

    @app.get('/api/v1/research/threshold-tradeoffs')
    def threshold_tradeoffs(request: Request):
        if request.query_params:return JSONResponse(status_code=422,content={'error':'threshold_query_not_supported'})
        try:return load_thresholds()
        except (OSError,ValueError,KeyError,TypeError,ZeroDivisionError):return JSONResponse(status_code=503,content={'error':'threshold_evidence_unavailable','message':'Recorded April threshold evidence could not be verified. Previous results must be cleared.'})

    @app.get('/api/v1/research/model-diagnostics')
    def model_diagnostics():
        try:
            return load_diagnostics()
        except (OSError, ValueError, KeyError, TypeError, ZeroDivisionError):
            return JSONResponse(status_code=503, content={'error':'model_diagnostics_unavailable',
                'message':'The recorded model evaluation could not be verified. Results are withheld.'})

    @app.get('/api/v1/research/route-segments')
    def route_segments():
        try:
            return load_segments()
        except (OSError, ValueError, KeyError, TypeError, StopIteration, ZeroDivisionError):
            return JSONResponse(status_code=503, content={'error': 'segmentation_evidence_unavailable',
                'message': 'The recorded route experiment could not be verified. No groups are returned.'})

    @app.get('/api/v1/research/route-profile')
    def route_profile(request: Request):
        items = list(request.query_params.multi_items())
        if len(items) != 2 or {key for key, _ in items} != {'origin', 'destination'}:
            return JSONResponse(status_code=422, content={'error': 'invalid_route_query'})
        try:
            return lookup_route(database, request.query_params['origin'], request.query_params['destination'])
        except ValueError:
            return JSONResponse(status_code=422, content={'error': 'invalid_route_query'})
        except RouteNotObserved:
            return JSONResponse(status_code=404, content={'error': 'route_not_observed'})
        except LookupBusy:
            return JSONResponse(status_code=429, content={'error': 'route_lookup_busy'}, headers={'Retry-After': '2'})
        except LookupUnavailable:
            return JSONResponse(status_code=503, content={'error': 'route_history_unavailable'}, headers={'Retry-After': '2'})

    return app


app = create_app()
