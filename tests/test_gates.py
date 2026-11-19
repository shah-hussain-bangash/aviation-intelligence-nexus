from itertools import product
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from pydantic import ValidationError
import numpy as np

from auth_helpers import authenticated_client
from optimization.gates import GateScenario, optimize, verify_plan
from services.api.main import create_app


def scenario(buffer=10):
    return GateScenario.model_validate({"data_kind":"synthetic","buffer_minutes":buffer,
        "gates":[{"id":"N1","capacity":"narrow"},{"id":"W1","capacity":"wide"}],
        "flights":[
            {"id":"F1","aircraft":"narrow","arrival":480,"departure":600,"costs":{"N1":6,"W1":1}},
            {"id":"F2","aircraft":"wide","arrival":500,"departure":590,"costs":{"N1":20,"W1":3}},
            {"id":"F3","aircraft":"narrow","arrival":605,"departure":680,"costs":{"N1":2,"W1":2}}]})


class GateSolverTests(unittest.TestCase):
    def test_solver_preserves_wide_gate_capacity_and_beats_greedy_coverage(self):
        result=optimize(scenario())
        self.assertEqual(result["candidate"]["verification"]["assigned"],3)
        self.assertEqual(result["baseline"]["verification"]["assigned"],2)
        self.assertEqual(result["candidate"]["verification"]["assignment_cost"],11)
        self.assertEqual(result["solver_status"],"optimal")
        self.assertFalse(result["operational_approval"])

    def test_longer_buffer_reduces_coverage_and_no_compatible_gate_is_explicit(self):
        self.assertEqual(optimize(scenario(20))["candidate"]["verification"]["assigned"],2)
        payload=scenario().model_dump()
        payload["gates"]=[payload["gates"][0]]
        payload["flights"]=[payload["flights"][1]]
        payload["flights"][0]["costs"]={"N1":20}
        result=optimize(GateScenario.model_validate(payload))
        self.assertEqual(result["candidate"]["unassigned"],["F2"])
        self.assertTrue(result["candidate"]["verification"]["feasible"])

    def test_independent_checker_rejects_conflicts_and_incompatible_assignments(self):
        invalid={"assignments":[{"flight":"F1","gate":"W1"},{"flight":"F2","gate":"W1"}],"unassigned":["F3"]}
        self.assertFalse(verify_plan(scenario(),invalid)["feasible"])
        invalid["assignments"][1]["gate"]="N1"
        self.assertFalse(verify_plan(scenario(),invalid)["feasible"])

    def test_solution_matches_exhaustive_small_problem_oracle(self):
        problem=scenario()
        best=None
        for choices in product([None,"N1","W1"],repeat=3):
            valid=True
            for i,choice in enumerate(choices):
                if choice=="N1" and problem.flights[i].aircraft=="wide":valid=False
                for k in range(i):
                    if choice is not None and choice==choices[k]:
                        earlier,later=sorted([problem.flights[i],problem.flights[k]],key=lambda f:f.arrival)
                        if later.arrival < earlier.departure+problem.buffer_minutes:valid=False
            if valid:
                score=(choices.count(None),sum(f.costs[g] for f,g in zip(problem.flights,choices) if g is not None))
                best=score if best is None or score<best else best
        result=optimize(problem)["candidate"]["verification"]
        self.assertEqual((result["unassigned"],result["assignment_cost"]),best)

    def test_time_limited_candidate_is_not_claimed_optimal_and_fractional_result_fails(self):
        payload=scenario().model_dump();payload["flights"]=payload["flights"][:1]
        problem=GateScenario.model_validate(payload)
        candidate=SimpleNamespace(x=np.array([0.,1.,0.]),status=1,fun=1.,mip_gap=None)
        with patch('scipy.optimize.milp',return_value=candidate):
            self.assertEqual(optimize(problem)["solver_status"],"time_limited_feasible")
        candidate.x=np.array([.5,.5,0.])
        with patch('scipy.optimize.milp',return_value=candidate),self.assertRaises(RuntimeError):optimize(problem)

    def test_invalid_input_contract_is_rejected(self):
        for change in [{"data_kind":"live"},{"buffer_minutes":-1},{"buffer_minutes":True}]:
            with self.assertRaises(ValidationError):GateScenario.model_validate({**scenario().model_dump(),**change})
        payload=scenario().model_dump();payload["flights"][0]["costs"]["UNKNOWN"]=1
        with self.assertRaises(ValidationError):GateScenario.model_validate(payload)


class GateApiTests(unittest.TestCase):
    def test_authenticated_runs_persist_and_replay_without_duplicate(self):
        with tempfile.TemporaryDirectory() as folder:
            database=Path(folder)/"test.sqlite3"
            with authenticated_client(create_app(database)) as client:
                headers={"Idempotency-Key":str(uuid4())}
                first=client.post('/api/v1/research/optimize-gates',json=scenario().model_dump(),headers=headers)
                self.assertEqual(first.status_code,200)
                second=client.post('/api/v1/research/optimize-gates',json=scenario().model_dump(),headers=headers)
                self.assertTrue(second.json()["replayed"])
                self.assertEqual(first.json()["run_id"],second.json()["run_id"])
                self.assertEqual(len(client.get('/api/v1/research/gate-history').json()["runs"]),1)
                self.assertEqual(client.post('/api/v1/research/optimize-gates',json=scenario(20).model_dump(),headers=headers).status_code,409)
            with authenticated_client(create_app(database)) as restarted:
                self.assertEqual(restarted.get('/api/v1/research/gate-history').json()["runs"][0]["run_id"],first.json()["run_id"])

    def test_viewer_cannot_compute_or_read_another_users_proposals(self):
        with tempfile.TemporaryDirectory() as folder:
            app=create_app(Path(folder)/"test.sqlite3")
            with authenticated_client(app) as client:
                self.assertEqual(client.post('/api/v1/research/optimize-gates',json=scenario().model_dump()).status_code,200)
                app.state.auth_store.create_user('gate-viewer','temporary-viewer-fixture-123','viewer')
                login=client.post('/api/v1/auth/login',json={'username':'gate-viewer','password':'temporary-viewer-fixture-123'})
                client.headers['X-CSRF-Token']=login.json()['csrf_token']
                self.assertEqual(client.post('/api/v1/research/optimize-gates',json=scenario().model_dump()).status_code,403)
                self.assertEqual(client.get('/api/v1/research/gate-history').json()['runs'],[])
