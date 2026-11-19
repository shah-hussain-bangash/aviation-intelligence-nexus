# Local backend foundation

Python 3.14 is the tested interpreter. From the repository root, use a separate terminal while the dashboard runs:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m uvicorn services.api.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/docs for interactive API documentation, or http://127.0.0.1:8000/api/v1/status for actual local status. Stop with Ctrl+C. If port 8000 is occupied, inspect the running service or select another local port.

The default database is `.local/ain.sqlite3`, excluded from Git. `AIN_DB_PATH` overrides it. Startup applies schema version 1 transactionally and preserves existing records on restart. A future schema version is rejected. Health readiness returns 503 if the database query fails; liveness remains independent.

No sample flights are inserted at startup. A fresh database starts at zero; the development database now contains the BTS import described in `DATA_INGESTION.md`. Test fixtures exist only in temporary test databases. Schema version 2 adds flight identity fields, cancellation/diversion flags and an import provenance table.

This is a read-only local development API. Bind only to loopback. Authentication, permissions, predictions, dashboard integration, cloud deployment and recovery qualification are still pending. The dependency file pins direct packages; a complete dependency lock and isolated CI verification remain release work.
