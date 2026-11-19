"""Binary gate assignment on synthetic schedules, with a separate feasibility check."""

import hashlib
import json
from pathlib import Path
from threading import Lock
import time
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Cost = Annotated[int, Field(ge=0, le=1000, strict=True)]
SOLVER_LOCK = Lock()


class Gate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[A-Z0-9-]{1,12}$")
    capacity: Literal["narrow", "wide"]


class Flight(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[A-Z0-9-]{1,16}$")
    aircraft: Literal["narrow", "wide"]
    arrival: int = Field(ge=0, le=1439, strict=True)
    departure: int = Field(ge=1, le=1440, strict=True)
    costs: dict[str, Cost] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def ordered_times(self):
        if self.departure <= self.arrival:
            raise ValueError("Departure must follow arrival within the same synthetic day")
        return self


class GateScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")
    data_kind: Literal["synthetic"]
    buffer_minutes: int = Field(default=10, ge=0, le=60, strict=True)
    gates: list[Gate] = Field(min_length=1, max_length=6)
    flights: list[Flight] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def identifiers(self):
        gate_ids = {gate.id for gate in self.gates}
        if len(gate_ids) != len(self.gates) or len({f.id for f in self.flights}) != len(self.flights):
            raise ValueError("Gate and flight identifiers must be unique")
        if any(set(f.costs) != gate_ids for f in self.flights):
            raise ValueError("Every flight needs one cost for each declared gate")
        return self


def greedy_baseline(scenario):
    assignments, unassigned, occupied = [], [], {g.id: [] for g in scenario.gates}
    gates = {g.id: g for g in scenario.gates}
    for flight in sorted(scenario.flights, key=lambda f: (f.arrival, f.id)):
        for gate_id in sorted(gates, key=lambda g: (flight.costs[g], g)):
            if flight.aircraft == "wide" and gates[gate_id].capacity != "wide":
                continue
            if any(flight.arrival < end and start < flight.departure + scenario.buffer_minutes for start, end in occupied[gate_id]):
                continue
            assignments.append({"flight": flight.id, "gate": gate_id})
            occupied[gate_id].append((flight.arrival, flight.departure + scenario.buffer_minutes))
            break
        else:
            unassigned.append(flight.id)
    return {"assignments": assignments, "unassigned": unassigned}


def verify_plan(scenario, plan):
    """Independent event sweep: checks partition, compatibility and gate occupancy."""
    flights = {flight.id: flight for flight in scenario.flights}
    gates = {gate.id: gate for gate in scenario.gates}
    seen, events, errors, cost = set(), {gate: [] for gate in gates}, [], 0
    for row in plan["assignments"]:
        identifier, gate_id = row.get("flight"), row.get("gate")
        if identifier not in flights or gate_id not in gates or identifier in seen:
            errors.append("Unknown or duplicate assignment")
            continue
        seen.add(identifier)
        flight = flights[identifier]
        if gates[gate_id].capacity == "narrow" and flight.aircraft != "narrow":
            errors.append("Aircraft exceeds gate capacity")
        cost += flight.costs[gate_id]
        events[gate_id].extend([(flight.arrival, 1), (flight.departure + scenario.buffer_minutes, -1)])
    for identifier in plan["unassigned"]:
        if identifier not in flights or identifier in seen:
            errors.append("Unknown or repeated unassigned flight")
        seen.add(identifier)
    if seen != set(flights):
        errors.append("Plan does not account for every flight")
    for gate_id, timeline in events.items():
        active = 0
        for _, change in sorted(timeline):  # End events (-1) precede starts at an exact boundary.
            active += change
            if active > 1:
                errors.append(f"Gate conflict: {gate_id}")
    return {"feasible": not errors, "errors": errors, "assigned": len(plan["assignments"]),
            "unassigned": len(plan["unassigned"]), "assignment_cost": cost}


def optimize(scenario):
    import numpy as np
    from scipy.optimize import Bounds, LinearConstraint, milp
    started = time.monotonic()
    n, m = len(scenario.flights), len(scenario.gates)
    variables = n * (m + 1)  # Each flight has one variable per gate, plus an unassigned variable.
    maximum_cost = max(value for flight in scenario.flights for value in flight.costs.values())
    penalty = n * maximum_cost + 1  # Coverage takes priority over every possible cost saving.
    objective = np.zeros(variables)
    upper = np.ones(variables)
    rows, lower, limits = [], [], []
    for i, flight in enumerate(scenario.flights):
        row = np.zeros(variables)
        row[i * (m + 1):(i + 1) * (m + 1)] = 1
        rows.append(row); lower.append(1); limits.append(1)
        for j, gate in enumerate(scenario.gates):
            index = i * (m + 1) + j
            objective[index] = flight.costs[gate.id]
            if flight.aircraft == "wide" and gate.capacity == "narrow":
                upper[index] = 0
        objective[i * (m + 1) + m] = penalty
    for i, flight in enumerate(scenario.flights):
        for k in range(i + 1, n):
            other = scenario.flights[k]
            if max(flight.arrival, other.arrival) < min(flight.departure, other.departure) + scenario.buffer_minutes:
                for j in range(m):
                    row = np.zeros(variables)
                    row[i * (m + 1) + j] = row[k * (m + 1) + j] = 1
                    rows.append(row); lower.append(-np.inf); limits.append(1)
    with SOLVER_LOCK:
        solution = milp(objective, integrality=np.ones(variables), bounds=Bounds(np.zeros(variables), upper),
            constraints=LinearConstraint(np.asarray(rows), lower, limits),
            options={"time_limit": 3.0, "mip_rel_gap": 0.0, "presolve": True})
    if solution.x is None or solution.status not in (0, 1):
        raise RuntimeError("Solver did not return a verifiable candidate")
    if not np.all(np.isfinite(solution.x)) or np.max(np.abs(solution.x - np.round(solution.x))) > 1e-6:
        raise RuntimeError("Solver returned non-integral values")
    candidate = {"assignments": [], "unassigned": []}
    for i, flight in enumerate(scenario.flights):
        selected = [j for j in range(m + 1) if solution.x[i * (m + 1) + j] > .5]
        if len(selected) != 1:
            raise RuntimeError("Invalid assignment partition")
        if selected[0] == m:
            candidate["unassigned"].append(flight.id)
        else:
            candidate["assignments"].append({"flight": flight.id, "gate": scenario.gates[selected[0]].id})
    verification = verify_plan(scenario, candidate)
    baseline = greedy_baseline(scenario)
    baseline_verification = verify_plan(scenario, baseline)
    if not verification["feasible"] or not baseline_verification["feasible"]:
        raise RuntimeError("Independent plan verification failed")
    expected_objective = verification["assignment_cost"] + penalty * verification["unassigned"]
    if solution.fun is None or not np.isfinite(solution.fun) or abs(solution.fun - expected_objective) > 1e-5:
        raise RuntimeError("Solver objective did not reconcile with the verified plan")
    gap = getattr(solution,"mip_gap",None)
    payload = scenario.model_dump()
    return {"engine": "scipy-highs-milp", "formulation_version": "gate-v1",
        "scenario_sha256": hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
        "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "scenario": payload, "candidate": {**candidate, "verification": verification},
        "baseline": {**baseline, "verification": baseline_verification},
        "solver_status": "optimal" if solution.status == 0 else "time_limited_feasible",
        "objective": float(solution.fun), "unassigned_penalty": penalty,
        "mip_gap": float(gap) if gap is not None and np.isfinite(gap) else None,
        "elapsed_ms": round((time.monotonic() - started) * 1000, 2),
        "research_only": True, "operational_approval": False,
        "limitations": ["Synthetic schedules only; no live airline systems",
            "Only time overlap, aircraft size and assignment costs are represented",
            "No real stand geometry, passenger/crew flows, airline policies or safety qualification",
            "No allocation is applied to an operational system"]}
