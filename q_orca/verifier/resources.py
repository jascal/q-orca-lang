"""Resource-bound invariant checks (Stage 4c).

Evaluates each `Invariant(kind="resource")` against the corresponding
metric from `q_orca.compiler.resources.estimate_resources`. Bound
violations emit `RESOURCE_BOUND_EXCEEDED` errors; indeterminate metrics
(`"unknown"`) emit `RESOURCE_BOUND_INDETERMINATE` warnings. Machines
without any resource invariant pay zero cost.

The check runs only when at least one resource invariant is present
in `machine.invariants` so the Qiskit transpile cost is opt-in.
"""

from q_orca.ast import QMachineDef
from q_orca.compiler.resources import estimate_resources
from q_orca.verifier.types import QVerificationError


_OP_SYMBOL = {"eq": "==", "ne": "!=", "lt": "<", "le": "<=", "gt": ">", "ge": ">="}
_OP_CHECK = {
    "eq": lambda v, b: v == b,
    "ne": lambda v, b: v != b,
    "lt": lambda v, b: v < b,
    "le": lambda v, b: v <= b,
    "gt": lambda v, b: v > b,
    "ge": lambda v, b: v >= b,
}


def check_resource_invariants(machine: QMachineDef) -> list[QVerificationError]:
    resource_invs = [inv for inv in machine.invariants if inv.kind == "resource"]
    if not resource_invs:
        return []

    resources = estimate_resources(machine)
    errors: list[QVerificationError] = []
    for inv in resource_invs:
        if inv.metric is None or inv.value is None:
            continue
        measured = resources.get(inv.metric)
        sym = _OP_SYMBOL.get(inv.op, inv.op)
        bound = int(inv.value)
        if measured == "unknown":
            errors.append(QVerificationError(
                code="RESOURCE_BOUND_INDETERMINATE",
                message=(
                    f"Resource '{inv.metric}' could not be measured "
                    f"statically; bound {sym} {bound} not checked"
                ),
                severity="warning",
                location={"metric": inv.metric},
            ))
            continue
        if not isinstance(measured, int):
            continue
        check = _OP_CHECK.get(inv.op)
        if check is None or check(measured, bound):
            continue
        errors.append(QVerificationError(
            code="RESOURCE_BOUND_EXCEEDED",
            message=(
                f"Resource '{inv.metric}' = {measured} violates bound "
                f"{sym} {bound}"
            ),
            severity="error",
            location={"metric": inv.metric, "measured": measured, "bound": bound},
        ))
    return errors
