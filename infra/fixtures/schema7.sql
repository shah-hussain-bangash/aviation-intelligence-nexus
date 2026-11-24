-- Synthetic empty schema-7 fixture. No user or aviation records.
-- DDL from initializer at 515cb8c8121aa8a41e09f5e4d05e62280554b955.
BEGIN;
CREATE TABLE agent_runs(id TEXT PRIMARY KEY,owner_id TEXT NOT NULL,request_key TEXT NOT NULL,input_hash TEXT NOT NULL,result_json TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(owner_id,request_key));
CREATE TABLE auth_limits(key TEXT PRIMARY KEY, failures INTEGER NOT NULL, window_start REAL NOT NULL);
CREATE TABLE auth_sessions(token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires_at REAL NOT NULL);
CREATE TABLE auth_users(id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, role TEXT NOT NULL, active INTEGER NOT NULL);
CREATE TABLE flights (
                id INTEGER PRIMARY KEY,
                source TEXT NOT NULL,
                source_record_id TEXT NOT NULL,
                flight_date TEXT NOT NULL,
                carrier TEXT NOT NULL,
                origin TEXT NOT NULL,
                destination TEXT NOT NULL,
                departure_delay_minutes REAL,
                arrival_delay_minutes REAL, flight_number TEXT, scheduled_departure TEXT, cancelled INTEGER, diverted INTEGER,
                UNIQUE(source, source_record_id)
            );
CREATE TABLE gate_runs(id TEXT PRIMARY KEY,owner_id TEXT NOT NULL,request_key TEXT NOT NULL, scenario_hash TEXT NOT NULL,result_json TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(owner_id,request_key));
CREATE TABLE imports (
                sha256 TEXT PRIMARY KEY, source_url TEXT NOT NULL,
                period TEXT NOT NULL, rows_read INTEGER NOT NULL,
                rows_inserted INTEGER NOT NULL, duplicate_rows INTEGER NOT NULL,
                imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
CREATE TABLE knowledge_runs(id TEXT PRIMARY KEY,owner_id TEXT NOT NULL,result_json TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE research_runs (
                id TEXT PRIMARY KEY, request_key TEXT NOT NULL UNIQUE,
                input_sha256 TEXT NOT NULL, scenario_json TEXT NOT NULL,
                result_json TEXT NOT NULL, model_version TEXT NOT NULL,
                artifact_sha256 TEXT NOT NULL, created_at TEXT NOT NULL
            , owner_id TEXT);
CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX agent_runs_owner ON agent_runs(owner_id,updated_at);
CREATE INDEX gate_runs_owner ON gate_runs(owner_id,created_at);
CREATE INDEX knowledge_runs_owner ON knowledge_runs(owner_id,created_at);
CREATE INDEX research_runs_created ON research_runs(created_at);
CREATE INDEX research_runs_owner ON research_runs(owner_id,created_at);
INSERT INTO schema_migrations(version) VALUES (1);
INSERT INTO schema_migrations(version) VALUES (2);
INSERT INTO schema_migrations(version) VALUES (3);
INSERT INTO schema_migrations(version) VALUES (4);
INSERT INTO schema_migrations(version) VALUES (5);
INSERT INTO schema_migrations(version) VALUES (6);
INSERT INTO schema_migrations(version) VALUES (7);
COMMIT;
