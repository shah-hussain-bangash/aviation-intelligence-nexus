# Gate Allocation Lab

The connected research panel contains a working Operations Research demonstration, separate from the 64 prototype workspaces. It computes proposals for five synthetic flights, lets users vary the departure buffer and gate capacity, compares a chronological greedy baseline, saves results and exports JSON. No actual airport allocation is performed.

## Formulation and checks

SciPy `milp` uses the HiGHS mixed-integer solver. Each flight has a binary variable for each gate and a binary unassigned variable; exactly one is selected. Wide aircraft cannot use narrow gates. Flights whose occupied intervals overlap cannot share a gate. Occupancy is [arrival, departure + buffer), so a gate becomes available exactly at departure + buffer. Buffer applies only after departure.

The objective minimizes assignment cost plus a penalty for every unassigned flight. The penalty is n times the largest declared assignment cost plus one, so assigning another flight takes priority over any cost saving. Costs are invented units, not currency or measured airline benefit.

Requests are bounded to 16 flights, 6 gates, one synthetic day, integer costs 0–1000 and a buffer of 0–60 minutes. The dashboard supplies a fixed five-flight scenario. Each solver invocation has a three-second solver limit and executions are serialized within a process. This is not a production queue or a request-latency guarantee.

A separate event-sweep checker verifies complete accounting, unique assignments, aircraft compatibility, overlapping occupancy and assignment cost. The solver objective must reconcile with that checked plan. Fractional, missing or unverifiable candidates fail closed. A solver-reported optimum is labelled optimal only for the encoded scenario; a time-limited feasible candidate is labelled with optimality unproven.

## Measured demo

`reports/Gate_Optimization_Demo.json` records runs of the exact frontend sample, including scenario, solver status, implementation/scenario hashes and independently checked assignments.

| Buffer | Gates | Optimized assigned | Greedy assigned | Optimized assignment cost |
|---|---|---|---|---|
| 10 minutes | 1 narrow + 1 wide | 5/5 | 4/5 | 14 |
| 20 minutes | 1 narrow + 1 wide | 4/5 | 4/5 | 6 |
| 20 minutes | 2 narrow + 1 wide | 5/5 | 4/5 | 13 |

All three returned optimal, independently feasible plans locally. Costs across different coverage levels are not direct savings comparisons. This tiny designed example demonstrates solver behavior; it is not evidence of airport-scale performance or real airline impact.

## API and access

- POST `/api/v1/research/optimize-gates`: authenticated admin/researcher, Origin/CSRF controls, bounded validated synthetic input and optional UUID Idempotency-Key.
- GET `/api/v1/research/gate-history`: latest ten saved proposals, scoped to the user; administrators can review all.
- SQLite migration 5 adds a separate table without replacing flight, identity or prediction history records. A response is successful only after persistence succeeds.
- Retry keys are owner scoped. Same key and scenario replays the saved result; conflicting reuse returns 409. Saved records include actor, UTC timestamp, scenario and implementation hashes. Local history is not tamper-proof auditing.

Tests cover known solutions, exhaustive enumeration of a small independent problem, insufficient capacity, incompatible aircraft, buffer boundaries, rejected conflicts, time-limited/fractional solver outputs, validation, authenticated persistence/replay and viewer restrictions. The complete suite currently passes 51 Python and 11 Node tests.

Browser verification on 19 November 2026 used the normal signed-in dashboard and confirmed all three scenarios above, persisted history review and a downloaded JSON export. At 390 pixels the form and metric cards remained readable without page overflow. Existing flight records and prediction history remained available after migration and restart.

## Remaining limits

No real stand geometry, adjacent-stand restrictions, closures, aircraft towing, international/domestic segregation, passenger flows, airline policies, uncertainty or multi-day schedules are modeled. This does not establish operational safety, production scale, deployment readiness or automatic recovery. Real airport data and domain validation are required before extending scope.

Solver API reference: [SciPy mixed-integer linear programming](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.milp.html).
