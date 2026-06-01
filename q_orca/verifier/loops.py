"""Bounded-loop verifier rules (add-bounded-loop-annotation).

Three rules that fire automatically whenever a `## state` carries a
`[loop …]` annotation:

- ``loop_body_well_formed`` — the loop body is the strongly-connected
  component entered through the annotated state. An ambiguous body — two
  ``[loop …]``-annotated states sharing one cycle, which also covers nested
  loops in v1 — is rejected with ``LOOP_AMBIGUOUS_BODY``.
- ``loop_body_unitarity`` — a fixed ``[loop N]`` body must be unitary, so a
  measurement on an in-body transition (other than the ``loop_done`` exit
  edge) emits ``NON_UNITARY_ACTION`` (``U^N`` is unitary iff ``U`` is). An
  adaptive ``[loop until: …]`` body is exempt: its per-iteration measurement
  is how the classical exit predicate is updated.
- ``loop_termination_reachable`` — an adaptive ``[loop until: P]`` whose
  predicate is over integer counters is accepted; one that involves a
  floating-point context field (whose progress cannot be checked statically)
  emits the ``LOOP_TERMINATION_UNCHECKED`` warning.

See ``openspec/changes/add-bounded-loop-annotation/`` and
``docs/language/bounded-loops.md``.
"""

from __future__ import annotations

import re

from q_orca.ast import QMachineDef, QTypeScalar
from q_orca.verifier.types import QVerificationError, QVerificationResult
from q_orca.verifier.roles import _strongly_connected_components

_IDENT_RE = re.compile(r"[A-Za-z_]\w*")


def _loop_states(machine: QMachineDef) -> list:
    """States carrying a `[loop …]` annotation."""
    return [s for s in machine.states if getattr(s, "loop", None) is not None]


def _build_sccs(machine: QMachineDef) -> list[set[str]]:
    nodes = [s.name for s in machine.states]
    edges: dict[str, list[str]] = {n: [] for n in nodes}
    for t in machine.transitions:
        if t.source in edges:
            edges[t.source].append(t.target)
    return _strongly_connected_components(nodes, edges)


def _scc_containing(sccs: list[set[str]], name: str) -> set[str]:
    for comp in sccs:
        if name in comp:
            return comp
    return set()


def _is_cyclic(comp: set[str], machine: QMachineDef) -> bool:
    if len(comp) > 1:
        return True
    n = next(iter(comp))
    return any(t.source == n and t.target == n for t in machine.transitions)


def _action_measures(action) -> bool:
    """True if the action performs a (non-unitary) measurement."""
    if action is None:
        return False
    return (
        getattr(action, "mid_circuit_measure", None) is not None
        or getattr(action, "measurement", None) is not None
    )


def loop_body_well_formed(machine: QMachineDef) -> list[QVerificationError]:
    """Reject ambiguous loop bodies (`LOOP_AMBIGUOUS_BODY`)."""
    loop_states = _loop_states(machine)
    if not loop_states:
        return []
    loop_names = {s.name for s in loop_states}
    sccs = _build_sccs(machine)
    errors: list[QVerificationError] = []
    reported: set[tuple] = set()
    for comp in sccs:
        if not _is_cyclic(comp, machine):
            continue
        annotated = sorted(n for n in comp if n in loop_names)
        if len(annotated) >= 2:
            key = tuple(annotated)
            if key in reported:
                continue
            reported.add(key)
            errors.append(QVerificationError(
                code="LOOP_AMBIGUOUS_BODY",
                message=(
                    f"loop body is ambiguous: states {annotated} are all "
                    f"[loop …]-annotated and share one cycle "
                    f"({sorted(comp)}); v1 supports a single loop per body "
                    f"and no nesting"
                ),
                severity="error",
                location={"states": annotated, "cycle": sorted(comp)},
                suggestion=(
                    "keep a single [loop …] annotation per cycle; factor a "
                    "nested inner loop into a separate machine until "
                    "nested-loop support lands"
                ),
            ))
    return errors


def loop_body_unitarity(machine: QMachineDef) -> list[QVerificationError]:
    """A fixed `[loop N]` body must be unitary (`NON_UNITARY_ACTION`)."""
    loop_states = _loop_states(machine)
    if not loop_states:
        return []
    action_map = {a.name: a for a in machine.actions}
    sccs = _build_sccs(machine)
    loop_names = {s.name for s in loop_states}
    errors: list[QVerificationError] = []
    reported: set[tuple] = set()
    for entry in loop_states:
        if entry.loop.kind != "fixed":
            # Adaptive bodies measure each iteration to update the exit
            # predicate, so they are exempt from the body-unitarity rule.
            continue
        comp = _scc_containing(sccs, entry.name)
        if not _is_cyclic(comp, machine):
            continue
        # Ambiguous bodies are handled by loop_body_well_formed; skip here.
        if sum(1 for n in comp if n in loop_names) >= 2:
            continue
        for t in machine.transitions:
            if (
                t.source in comp
                and t.target in comp
                and not t.loop_done
                and t.action
            ):
                action = action_map.get(t.action)
                if _action_measures(action):
                    key = (entry.name, t.action, t.source, t.target)
                    if key in reported:
                        continue
                    reported.add(key)
                    errors.append(QVerificationError(
                        code="NON_UNITARY_ACTION",
                        message=(
                            f"action {t.action!r} performs a measurement inside "
                            f"the fixed [loop …] body of state {entry.name!r}; a "
                            f"fixed loop body must be unitary (U^N is unitary "
                            f"iff U is)"
                        ),
                        severity="error",
                        location={
                            "action": t.action,
                            "state": entry.name,
                            "transition": [t.source, t.target],
                        },
                        suggestion=(
                            "move the measurement onto the loop_done exit edge, "
                            "or use an adaptive [loop until: …] if you need a "
                            "per-iteration measurement"
                        ),
                    ))
    return errors


def _scalar_kind_map(machine: QMachineDef) -> dict[str, str]:
    out: dict[str, str] = {}
    for f in machine.context:
        if isinstance(f.type, QTypeScalar):
            out[f.name] = f.type.kind
    return out


def loop_termination_reachable(machine: QMachineDef) -> list[QVerificationError]:
    """Warn when an adaptive predicate cannot be checked statically.

    An ``until:`` predicate over integer counters is accepted; one that
    involves a floating-point context field — or references no recognizable
    bounded counter — emits a ``LOOP_TERMINATION_UNCHECKED`` warning.
    """
    adaptive = [s for s in _loop_states(machine) if s.loop.kind == "adaptive"]
    if not adaptive:
        return []
    kinds = _scalar_kind_map(machine)
    errors: list[QVerificationError] = []
    for s in adaptive:
        pred = s.loop.bound_expr
        referenced = [tok for tok in _IDENT_RE.findall(pred) if tok in kinds]
        has_float = any(kinds[name] == "float" for name in referenced)
        has_int = any(kinds[name] == "int" for name in referenced)
        if has_int and not has_float:
            continue  # integer-counter predicate — statically checkable
        detail = (
            " (it compares a floating-point context field)"
            if has_float
            else " (no integer counter the body bounds is referenced)"
        )
        errors.append(QVerificationError(
            code="LOOP_TERMINATION_UNCHECKED",
            message=(
                f"adaptive loop on state {s.name!r} has predicate {pred!r} "
                f"whose termination cannot be checked statically{detail}"
            ),
            severity="warning",
            location={"state": s.name, "predicate": pred},
            suggestion=(
                "express the exit condition over an integer counter the loop "
                "body increments, or accept the runtime-only termination "
                "guarantee"
            ),
        ))
    return errors


def check_loop_rules(machine: QMachineDef) -> QVerificationResult:
    """Run the automatic bounded-loop structural rules."""
    errors: list[QVerificationError] = []
    if not _loop_states(machine):
        return QVerificationResult(valid=True, errors=errors)
    errors.extend(loop_body_well_formed(machine))
    errors.extend(loop_body_unitarity(machine))
    errors.extend(loop_termination_reachable(machine))
    return QVerificationResult(
        valid=not any(e.severity == "error" for e in errors),
        errors=errors,
    )
