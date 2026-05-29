"""Composition verification — multi-machine invoke/return static checks.

Runs after the classical-context stage. For each `[invoke: …]` state it resolves
the child machine in the same file, type-checks argument and return bindings,
enforces the shots-flag rule, detects invoke cycles, and recursively verifies
resolved children (surfacing their errors with a `child_path` breadcrumb).
See `add-parameterized-invoke`.
"""

from __future__ import annotations

from typing import Optional

from q_orca.ast import (
    QMachineDef,
    QOrcaFile,
    QType,
    QTypeCustom,
    QTypeList,
    QTypeOptional,
    QTypeQubit,
    QTypeScalar,
)
from q_orca.verifier.types import QVerificationError, QVerificationResult


def _type_key(qtype: QType) -> str:
    """Canonical comparable string for a `QType`."""
    if isinstance(qtype, QTypeScalar):
        return qtype.kind
    if isinstance(qtype, QTypeQubit):
        return "qubit"
    if isinstance(qtype, QTypeList):
        return f"list<{qtype.element_type}>"
    if isinstance(qtype, QTypeOptional):
        return f"optional<{qtype.inner_type}>"
    if isinstance(qtype, QTypeCustom):
        return qtype.name
    return str(qtype)


def _machine_has_measurement(machine: QMachineDef) -> bool:
    return any(
        a.measurement is not None or a.mid_circuit_measure is not None
        for a in machine.actions
    )


def _sanitize(name: str) -> str:
    """`bits[0]` → `bits_0`; mirrors the synthesized-aggregate naming."""
    return name.replace("[", "_").replace("]", "").replace(".", "_")


def _synthesized_aggregates(child: QMachineDef) -> dict[str, str]:
    """Aggregate field name → type-key, derived from the child's return statistics."""
    out: dict[str, str] = {}
    for r in child.returns:
        s = _sanitize(r.name)
        for stat in r.statistics:
            if stat == "expectation":
                out[f"prob_{s}"] = "float"
            elif stat == "histogram":
                out[f"hist_{s}"] = "dict<int,int>"
            elif stat == "variance":
                out[f"var_{s}"] = "float"
    return out


def _parent_expr_type(expr: str, parent: QMachineDef) -> tuple[Optional[str], Optional[str]]:
    """Infer the type-key of a parent-side arg expression.

    Returns `(type_key, detail)`. `type_key` is None (and `detail` set) when the
    referenced parent field is undeclared or is indexed but not a list.
    """
    ctx = {f.name: f.type for f in parent.context}
    if "[" in expr:
        base = expr.split("[", 1)[0].strip()
        if base not in ctx:
            return None, f"parent field '{base}' is not declared"
        t = ctx[base]
        if isinstance(t, QTypeList):
            return t.element_type, None
        return None, f"parent field '{base}' is indexed but is not a list type"
    if expr not in ctx:
        return None, f"parent field '{expr}' is not declared"
    return _type_key(ctx[expr]), None


def _invoke_graph(file: QOrcaFile) -> dict[str, set[str]]:
    graph: dict[str, set[str]] = {}
    for m in file.machines:
        graph[m.name] = {
            s.invoke.child_name for s in m.states if s.invoke is not None
        }
    return graph


def _machines_in_cycle(file: QOrcaFile) -> set[str]:
    """Names of machines that can reach themselves through the invoke graph."""
    graph = _invoke_graph(file)
    in_cycle: set[str] = set()
    for start in graph:
        stack = list(graph.get(start, ()))
        seen: set[str] = set()
        while stack:
            node = stack.pop()
            if node == start:
                in_cycle.add(start)
                break
            if node in seen:
                continue
            seen.add(node)
            stack.extend(graph.get(node, ()))
    return in_cycle


def check_composition(
    file: QOrcaFile,
    machine: QMachineDef,
    options=None,
    _visited: Optional[frozenset] = None,
) -> QVerificationResult:
    """Static multi-machine checks for `machine`'s invoke states."""
    errors: list[QVerificationError] = []
    invoke_states = [s for s in machine.states if s.invoke is not None]
    if not invoke_states:
        return QVerificationResult(valid=True, errors=[])

    by_name = {m.name: m for m in file.machines}
    cycle_machines = _machines_in_cycle(file)
    in_cycle = machine.name in cycle_machines
    if in_cycle:
        errors.append(QVerificationError(
            code="INVOKE_CYCLE",
            message=(
                f"machine '{machine.name}' invokes itself directly or "
                f"transitively; composition cycles are rejected"
            ),
            severity="error",
            location={"machine": machine.name},
        ))

    for state in invoke_states:
        inv = state.invoke
        loc = {"invoke_state": state.name}
        child = by_name.get(inv.child_name)
        if child is None:
            errors.append(QVerificationError(
                code="UNRESOLVED_CHILD_MACHINE",
                message=(
                    f"invoke state {state.name} references machine "
                    f"'{inv.child_name}', which is not defined in this file"
                ),
                severity="error",
                location=loc,
            ))
            continue

        # Shots-flag rule: shot-batched mode is for quantum children only.
        if inv.shots is not None and not _machine_has_measurement(child):
            errors.append(QVerificationError(
                code="SHOTS_ON_CLASSICAL_CHILD",
                message=(
                    f"invoke state {state.name}: shots={inv.shots} on classical "
                    f"child '{child.name}' (no measurement-bearing transitions)"
                ),
                severity="error",
                location=loc,
            ))

        # Argument binding typing.
        child_ctx = {f.name: f.type for f in child.context}
        for child_param, parent_expr in inv.arg_bindings.items():
            if child_param not in child_ctx:
                errors.append(QVerificationError(
                    code="INVOKE_ARG_UNDECLARED",
                    message=(
                        f"invoke state {state.name}: child '{child.name}' has no "
                        f"context field '{child_param}'"
                    ),
                    severity="error",
                    location=loc,
                ))
                continue
            parent_key, detail = _parent_expr_type(parent_expr, machine)
            child_key = _type_key(child_ctx[child_param])
            if parent_key is None or parent_key != child_key:
                reason = detail or (
                    f"parent type '{parent_key}' does not unify with child type "
                    f"'{child_key}'"
                )
                errors.append(QVerificationError(
                    code="INVOKE_ARG_TYPE_MISMATCH",
                    message=f"invoke state {state.name}: arg '{child_param}={parent_expr}' — {reason}",
                    severity="error",
                    location=loc,
                ))

        # Return binding typing. Under shot-batched mode the RHS refers to a
        # synthesized aggregate; otherwise to a raw declared return.
        shot_batched = inv.shots is not None and inv.shots > 1
        if shot_batched:
            available = _synthesized_aggregates(child)
        else:
            available = {r.name: _type_key(r.type) for r in child.returns}
        parent_ctx = {f.name: f.type for f in machine.context}
        for parent_field, child_return in inv.return_bindings.items():
            if child_return not in available:
                errors.append(QVerificationError(
                    code="INVOKE_RETURN_UNDECLARED",
                    message=(
                        f"invoke state {state.name}: child '{child.name}' does not "
                        f"{'expose aggregate' if shot_batched else 'declare return'} "
                        f"'{child_return}'"
                    ),
                    severity="error",
                    location=loc,
                ))
                continue
            if parent_field not in parent_ctx:
                errors.append(QVerificationError(
                    code="INVOKE_RETURN_TYPE_MISMATCH",
                    message=(
                        f"invoke state {state.name}: parent field '{parent_field}' "
                        f"(bound to '{child_return}') is not declared in parent context"
                    ),
                    severity="error",
                    location=loc,
                ))
                continue
            parent_key = _type_key(parent_ctx[parent_field])
            if parent_key != available[child_return]:
                errors.append(QVerificationError(
                    code="INVOKE_RETURN_TYPE_MISMATCH",
                    message=(
                        f"invoke state {state.name}: parent field '{parent_field}' "
                        f"type '{parent_key}' does not unify with '{child_return}' "
                        f"type '{available[child_return]}'"
                    ),
                    severity="error",
                    location=loc,
                ))

    # Recursive verification of resolved children (skipped on a cycle to avoid
    # unbounded recursion). Child errors surface with a child_path breadcrumb.
    if not in_cycle:
        from q_orca.verifier import verify  # late import — avoids import cycle

        visited = (_visited or frozenset()) | {machine.name}
        for state in invoke_states:
            child = by_name.get(state.invoke.child_name)
            if child is None or child.name in visited:
                continue
            child_result = verify(child, options, file=file, _visited=visited)
            for err in child_result.errors:
                errors.append(QVerificationError(
                    code=err.code,
                    message=err.message,
                    severity=err.severity,
                    location={
                        "invoke_state": state.name,
                        "child_machine": child.name,
                        "child_path": [err.location] if err.location else [],
                    },
                    suggestion=err.suggestion,
                ))

    return QVerificationResult(
        valid=not any(e.severity == "error" for e in errors),
        errors=errors,
    )
