"""OR-Tools CP-SAT solver for one (pincode, date) bucket.

Bipartite assignment between pending inspection requests and (inspector, slot)
pairs. Strict `preferredTime` matching: a request can only land on slots whose
`slotTime` exactly equals the request's preferred time (after UTC→IST
conversion).

Objective: maximize the number of assignments, weighted by urgency.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass

from ortools.sat.python import cp_model

from app.config import settings
from app.core.bucketing import urgency_weight
from app.core.models import (
    Assignment,
    InspectorAvailability,
    PendingRequest,
    SkippedRequest,
)
from app.core.time_utils import format_preferred_time_to_ist_slot

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Candidate:
    inspector_idx: int
    slot_idx: int
    slot_time: str
    employee_id: str


def _build_candidates(
    requests: list[PendingRequest],
    inspectors: list[InspectorAvailability],
) -> tuple[dict[int, list[_Candidate]], list[tuple[int, str]]]:
    """For each request index, list the (inspector, slot) pairs it could land on.

    Returns:
        candidates_by_request: {request_idx: [Candidate, ...]}
        immediate_skips: [(request_idx, reason)] — requests that can be ruled
            out before solving (no preferredTime, no matching slot).
    """
    candidates: dict[int, list[_Candidate]] = {}
    immediate: list[tuple[int, str]] = []

    for r_idx, req in enumerate(requests):
        wanted = format_preferred_time_to_ist_slot(req)
        if not wanted:
            immediate.append((r_idx, "NO_PREFERRED_TIME"))
            continue

        cands: list[_Candidate] = []
        for i_idx, ins in enumerate(inspectors):
            if ins.availability_status != "AVAILABLE":
                continue
            for s_idx, slot in enumerate(ins.slots):
                if slot.is_available and slot.slot_time == wanted:
                    cands.append(
                        _Candidate(
                            inspector_idx=i_idx,
                            slot_idx=s_idx,
                            slot_time=slot.slot_time,
                            employee_id=ins.employee_id,
                        )
                    )

        if not cands:
            immediate.append((r_idx, "NO_SLOT_AT_PREFERRED_TIME"))
            continue

        candidates[r_idx] = cands

    return candidates, immediate


def solve_bucket(
    pincode: str,
    date: str,
    requests: list[PendingRequest],
    inspectors: list[InspectorAvailability],
    time_limit_sec: int | None = None,
) -> tuple[list[Assignment], list[SkippedRequest]]:
    """Solve assignment for a single (pincode, date) bucket using CP-SAT.

    Returns (assignments, skipped). `skipped` includes requests that had no
    feasible candidate as well as any the solver couldn't fit due to
    contention.
    """
    time_limit_sec = time_limit_sec or settings.solver_time_sec
    assignments: list[Assignment] = []
    skipped: list[SkippedRequest] = []

    candidates, immediate = _build_candidates(requests, inspectors)

    for r_idx, reason in immediate:
        skipped.append(
            SkippedRequest(
                request_id=requests[r_idx].request_id,
                reason=reason,
                pincode=pincode,
                date=date,
            )
        )

    if not candidates:
        return assignments, skipped

    model = cp_model.CpModel()

    # x[(r_idx, cand_idx)] ∈ {0,1} — request r_idx assigned to its cand_idx-th candidate.
    # Indexing by candidate index keeps the variable space tight.
    x: dict[tuple[int, int], cp_model.IntVar] = {}
    for r_idx, cands in candidates.items():
        for c_idx, _ in enumerate(cands):
            x[(r_idx, c_idx)] = model.NewBoolVar(f"x_{r_idx}_{c_idx}")

    # Constraint: each request assigned at most once.
    for r_idx, cands in candidates.items():
        model.Add(sum(x[(r_idx, c_idx)] for c_idx in range(len(cands))) <= 1)

    # Constraint: each (inspector, slot) used at most once across all requests.
    slot_uses: dict[tuple[int, int], list[cp_model.IntVar]] = defaultdict(list)
    for r_idx, cands in candidates.items():
        for c_idx, cand in enumerate(cands):
            slot_uses[(cand.inspector_idx, cand.slot_idx)].append(x[(r_idx, c_idx)])
    for vars_ in slot_uses.values():
        if len(vars_) > 1:
            model.Add(sum(vars_) <= 1)

    # Objective: maximize Σ (W_assign + W_urgency · urgency(r)) · x.
    # The W_assign baseline ensures we always prefer assigning over leaving idle,
    # while W_urgency tilts contention toward higher-urgency requests.
    objective_terms: list[cp_model.IntVar] = []
    for r_idx, cands in candidates.items():
        weight = settings.w_assign + settings.w_urgency * urgency_weight(
            requests[r_idx].urgency_level
        )
        for c_idx in range(len(cands)):
            objective_terms.append(weight * x[(r_idx, c_idx)])
    model.Maximize(sum(objective_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit_sec)
    solver.parameters.num_search_workers = 8

    status = solver.Solve(model)
    status_name = solver.StatusName(status)
    logger.info(
        "solver pincode=%s date=%s status=%s requests=%d candidates_total=%d",
        pincode,
        date,
        status_name,
        len(candidates),
        sum(len(c) for c in candidates.values()),
    )

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        for r_idx in candidates:
            skipped.append(
                SkippedRequest(
                    request_id=requests[r_idx].request_id,
                    reason=f"SOLVER_{status_name}",
                    pincode=pincode,
                    date=date,
                )
            )
        return assignments, skipped

    assigned_request_idxs: set[int] = set()
    for (r_idx, c_idx), var in x.items():
        if solver.Value(var) == 1:
            cand = candidates[r_idx][c_idx]
            assignments.append(
                Assignment(
                    request_id=requests[r_idx].request_id,
                    employee_id=cand.employee_id,
                    slot_time=cand.slot_time,
                    pincode=pincode,
                    date=date,
                )
            )
            assigned_request_idxs.add(r_idx)

    for r_idx in candidates:
        if r_idx not in assigned_request_idxs:
            skipped.append(
                SkippedRequest(
                    request_id=requests[r_idx].request_id,
                    reason="SOLVER_CONTENTION",
                    pincode=pincode,
                    date=date,
                )
            )

    return assignments, skipped
