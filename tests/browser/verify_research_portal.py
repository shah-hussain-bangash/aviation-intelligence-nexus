"""Run the real AIN gateway and API in a disposable authenticated browser rehearsal."""

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from urllib.error import URLError
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright


SEED = """
from pathlib import Path
import os
import sqlite3
from uuid import uuid4
from services.api.auth import AuthStore
from services.api.history import ResearchHistory
from services.api.main import initialize

database = Path(os.environ["AIN_DB_PATH"])
initialize(database)
auth = AuthStore(database)
auth.create_user("demo-researcher", os.environ["AIN_BROWSER_PASSWORD"], "admin")
auth.create_user("demo-viewer", os.environ["AIN_BROWSER_PASSWORD"], "viewer")
if os.environ["AIN_BROWSER_CASE"] == "1":
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT id, username, role FROM auth_users WHERE username = ?",
            ("demo-researcher",),
        ).fetchone()
    owner = dict(zip(("id", "username", "role"), row))
    ResearchHistory(database).save(
        str(uuid4()), {"scope": "synthetic browser fixture"},
        {"model_version": "delay-v2", "artifact_sha256": "a" * 64,
         "research_only": True, "operational_serving_approved": False,
         "arrival_delay_15_probability": 0.2,
         "limitations": ["Synthetic stored result. No model inference was executed."]},
        owner,
    )
"""


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def stop(process):
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=6)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def wait_for_ready(url, processes):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if any(process.poll() is not None for process in processes):
            break
        try:
            with urlopen(url + "/__ain/ready", timeout=1) as response:
                if response.status == 200:
                    return
        except (URLError, TimeoutError):
            pass
        time.sleep(0.15)
    raise RuntimeError("The isolated API and dashboard did not become ready.")


def sign_in(page, url, username, password):
    page.goto(url)
    button = page.get_by_role("button", name="Sign in", exact=True)
    expect(button).to_be_enabled()
    page.get_by_label("Username", exact=True).fill(username)
    page.get_by_label("Password", exact=True).fill(password)
    button.click()
    expect(page.locator("#researchConnection")).to_have_text("Backend connected · historical data")


def verify_case(page):
    case = page.locator("#research-cases")
    title = "Synthetic delay review and gate scenario"
    expect(case.get_by_label("Saved prediction")).to_be_enabled()
    case.get_by_label("Saved prediction").select_option(index=1)
    case.get_by_label("Investigation title").fill(title)
    case.get_by_role("button", name="Create research case").click()
    expect(case.get_by_role("heading", name=title)).to_be_visible()
    case.get_by_label("Note or research outcome").fill("Recorded fixture context for the synthetic gate analysis.")
    case.get_by_role("button", name="Save research record").click()
    version = case.locator(".case-detail .research-badge")
    expect(version).to_contain_text("version 2")
    case.get_by_role("button", name="Refresh cases and predictions").click()
    case.get_by_label("My recent cases").select_option(index=1)
    expect(version).to_contain_text("version 2")
    proposals = case.get_by_label("My reviewed synthetic gate proposals")
    expect(proposals).to_be_enabled()
    proposals.select_option(index=0)
    case.get_by_role("button", name="Attach synthetic gate proposal").click()
    expect(version).to_contain_text("version 3")
    expect(case.locator(".case-detail li").filter(has_text="gate · v3")).to_be_visible()
    return ["case_note_survives_refresh", "reviewed_gate_proposal_attached_at_version_3"]


def browser_checks(url, password, case_workspace):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=os.environ.get("AIN_BROWSER_CHROMIUM") or None,
        )
        page = browser.new_page(viewport={"width": 1440, "height": 1050})
        viewer = browser.new_page()
        errors = []
        for tab in (page, viewer):
            tab.on("pageerror", lambda error: errors.append(str(error)))
        assert page.request.get(url + "/api/v1/research/gate-history").status == 401

        sign_in(page, url, "demo-researcher", password)
        expect(page.locator("#nav").get_by_role("button", name="All workspaces 64")).to_be_visible()
        expect(page.locator("#data-quality").get_by_role("button", name="Export audit JSON")).to_be_enabled()
        expect(page.locator("#threshold-tradeoffs [data-tradeoff-status]")).to_contain_text("Verified recorded April evidence")

        gate = page.locator("#gate-lab")
        with page.expect_response(lambda r: r.url.endswith("/optimize-gates") and r.request.method == "POST") as solved:
            gate.get_by_role("button", name="Compute gate proposal").click()
        assert solved.value.ok
        proposal = solved.value.json()
        assert proposal["candidate"]["verification"]["assigned"] == 5
        assert proposal["baseline"]["verification"]["assigned"] == 4
        assert proposal["research_only"] and not proposal["operational_approval"]

        gate.get_by_label("Review note").fill("Reviewed aircraft compatibility and turnaround in the synthetic scenario.")
        gate.get_by_role("checkbox").check()
        with page.expect_response(lambda r: r.url.endswith("/gate-review") and r.request.method == "POST") as reviewed:
            gate.get_by_role("button", name="Save research decision").click()
        assert reviewed.value.ok
        receipt = reviewed.value.json()
        assert receipt["run_id"] == proposal["run_id"]
        assert receipt["review"]["proposal_sha256"] == proposal["proposal_sha256"]
        expect(gate.locator(".gate-review-state strong")).to_have_text("Reviewed as research")

        sign_in(viewer, url, "demo-viewer", password)
        expect(viewer.get_by_role("button", name="Compute gate proposal")).to_be_disabled()
        checks = [
            "anonymous_gate_history_denied", "authenticated_workspace_available",
            "recorded_lineage_and_threshold_evidence_rendered",
            "synthetic_gate_solver_5_of_5_vs_greedy_4_of_5",
            "research_review_matches_exact_proposal", "viewer_cannot_compute",
        ]
        if case_workspace:
            checks.extend(verify_case(page))
        assert not errors, errors
        browser.close()
        return checks


def run(repository, case_workspace):
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository, text=True).strip()
    with TemporaryDirectory(prefix="ain-browser-") as scratch, ExitStack() as cleanup:
        state = Path(scratch)
        api_port, web_port = free_port(), free_port()
        while web_port == api_port:
            web_port = free_port()
        url = f"http://127.0.0.1:{web_port}"
        password = secrets.token_urlsafe(32)
        env = {key: value for key, value in os.environ.items() if not key.startswith("AIN_")}
        env.update(
            PYTHONPATH=str(repository), AIN_STATE_ROOT=scratch, AIN_DB_PATH=str(state / "ain.sqlite3"),
            AIN_API_PORT=str(api_port), PORT=str(web_port), AIN_ENV="test",
        )
        subprocess.run([sys.executable, "-c", SEED], cwd=repository, check=True, timeout=20,
                       env={**env, "AIN_BROWSER_PASSWORD": password, "AIN_BROWSER_CASE": str(int(case_workspace))})
        entry = ["services.api.case_workspace:create_case_app", "--factory"] if case_workspace else ["services.api.main:app"]
        commands = [
            [sys.executable, "-m", "uvicorn", *entry, "--host", "127.0.0.1", "--port", str(api_port), "--no-access-log"],
            ["node", "scripts/dev.mjs"],
        ]
        log = cleanup.enter_context((state / "server.log").open("w"))
        processes = []
        for command in commands:
            process = subprocess.Popen(command, cwd=repository, env=env, stdout=log, stderr=log)
            cleanup.callback(stop, process)
            processes.append(process)
        try:
            wait_for_ready(url, processes)
        except RuntimeError:
            print((state / "server.log").read_text(), file=sys.stderr)
            raise
        checks = browser_checks(url, password, case_workspace)
    return {
        "format": "ain-research-portal-browser-v1",
        "source_revision": revision,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "versioned-case-fixture" if case_workspace else "local-research",
        "passed": True,
        "checks": checks,
        "synthetic_gate_scenario": True,
        "prediction_fixture_used": case_workspace,
        "model_inference_executed": False,
        "operational_approval": False,
        "production_ready": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case-workspace", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.repository.resolve(), args.case_workspace)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as destination:
        json.dump(report, destination, indent=2)
        destination.write("\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
