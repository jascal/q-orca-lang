"""Iterative runtime walker for machines with context-update actions.

Walks the machine's transition graph at runtime, evaluates guards against
live context, accumulates gate-carrying actions into a segment, flushes the
segment into an in-process Qiskit circuit run, applies context mutations,
records a per-transition trace, and enforces a hard iteration ceiling.

See `openspec/changes/run-context-updates/design.md` for the full design.
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Optional

from q_orca.ast import (
    ContextField,
    QActionSignature,
    QMachineDef,
    QTransition,
    QTypeList,
    QTypeScalar,
)
from q_orca.runtime import context_ops
from q_orca.runtime.guards import evaluate_guard
from q_orca.runtime.types import (
    QIterationTrace,
    QIterativeRuntimeError,
    QIterativeSimulationOptions,
    QIterativeSimulationResult,
)


def simulate_iterative(
    machine: QMachineDef,
    options: QIterativeSimulationOptions,
) -> QIterativeSimulationResult:
    """Run one end-to-end iterative simulation of the machine."""
    action_map = {a.name: a for a in machine.actions}
    guard_map = {g.name: g for g in machine.guards}
    initial_state = _initial_state_name(machine)
    final_states = {s.name for s in machine.states if s.is_final}

    ctx = _initial_context(machine)
    bits: dict[int, int] = {}
    trace: list[QIterationTrace] = []
    aggregate_counts: dict[str, int] = {}

    current_state = initial_state
    iteration = 0

    # A segment is a contiguous run of gate/measurement-bearing transitions
    # that execute as one circuit. We flush on: context-update transition,
    # reaching a final state, or exhausting outgoing transitions.
    segment: list[_PendingTransition] = []

    while True:
        if iteration > options.iteration_ceiling:
            raise QIterativeRuntimeError(
                f"iteration ceiling {options.iteration_ceiling} exceeded"
            )

        if current_state in final_states:
            bits = _flush_segment(
                machine, options, ctx, bits, segment, trace, aggregate_counts, iteration
            )
            segment = []
            break

        enabled = _enabled_transitions(
            machine, current_state, ctx, bits, guard_map
        )
        if not enabled:
            raise QIterativeRuntimeError(
                f"stuck state {current_state!r}: no guarded transition is enabled"
            )
        transition = enabled[0]
        action = action_map.get(transition.action) if transition.action else None

        if action is not None and action.context_update is not None:
            # Flush the accumulated gate segment first so any measurement
            # bits are observable to the context-update branch selection.
            bits = _flush_segment(
                machine, options, ctx, bits, segment, trace, aggregate_counts, iteration
            )
            segment = []
            ctx = context_ops.apply(action.context_update, ctx, bits)
            if options.record_trace:
                trace.append(
                    QIterationTrace(
                        iteration=iteration,
                        source_state=transition.source,
                        target_state=transition.target,
                        event=transition.event,
                        action=transition.action,
                        measurement_bits=dict(bits),
                        context_snapshot=deepcopy(ctx),
                    )
                )
        else:
            segment.append(
                _PendingTransition(
                    transition=transition, action=action, iteration=iteration
                )
            )

        current_state = transition.target
        iteration += 1

    return QIterativeSimulationResult(
        machine=machine.name,
        success=True,
        final_state=current_state,
        final_context=ctx,
        trace=trace,
        aggregate_counts=aggregate_counts,
    )


class _PendingTransition:
    """A transition buffered in a segment, with its resolved action."""
    __slots__ = ("transition", "action", "iteration")

    def __init__(
        self,
        transition: QTransition,
        action: Optional[QActionSignature],
        iteration: int,
    ):
        self.transition = transition
        self.action = action
        self.iteration = iteration


def _initial_state_name(machine: QMachineDef) -> str:
    for state in machine.states:
        if state.is_initial:
            return state.name
    raise QIterativeRuntimeError(
        f"machine {machine.name!r} has no [initial] state"
    )


def _enabled_transitions(
    machine: QMachineDef,
    state_name: str,
    ctx: dict,
    bits: dict,
    guard_map: dict,
) -> list[QTransition]:
    out = []
    for t in machine.transitions:
        if t.source != state_name:
            continue
        guard_expr = None
        if t.guard is not None:
            guard_def = guard_map.get(t.guard.name)
            if guard_def is not None:
                guard_expr = guard_def.expression
        passed = evaluate_guard(guard_expr, ctx, bits)
        if t.guard is not None and t.guard.negated:
            passed = not passed
        if passed:
            out.append(t)
    return out


def _flush_segment(
    machine: QMachineDef,
    options: QIterativeSimulationOptions,
    ctx: dict,
    bits: dict,
    segment: list[_PendingTransition],
    trace: list[QIterationTrace],
    aggregate_counts: dict,
    iteration: int,
) -> dict:
    """Run the accumulated segment, update `bits`, and emit trace entries.

    Returns the updated bits dict. Caller is responsible for resetting the
    segment buffer after the call returns.
    """
    if not segment:
        return bits

    gate_actions = [pt.action for pt in segment if pt.action is not None]
    has_measurement = any(
        a.mid_circuit_measure is not None for a in gate_actions
    )

    new_bits = dict(bits)
    counts: dict[str, int] = {}

    if gate_actions:
        from q_orca.compiler.qiskit import build_circuit_for_iteration

        qc = build_circuit_for_iteration(machine, ctx, gate_actions)
        if has_measurement:
            counts = _run_circuit_counts(qc, options, iteration)
            # Pick the most-frequent outcome; for inner_shots=1 there's
            # only one. Deterministic tie-break on the lexicographically
            # smallest bitstring to keep seeded runs reproducible.
            top = max(counts.items(), key=lambda kv: (kv[1], -_bitstring_rank(kv[0])))[0]
            # Qiskit counts keys are little-endian — reverse to match our
            # bit-index convention (bit 0 = clbit 0).
            outcome_bits = top.replace(" ", "")[::-1]
            for idx, ch in enumerate(outcome_bits):
                new_bits[idx] = int(ch)
            for outcome, c in counts.items():
                aggregate_counts[outcome] = aggregate_counts.get(outcome, 0) + c

    if options.record_trace:
        for pt in segment:
            trace.append(
                QIterationTrace(
                    iteration=pt.iteration,
                    source_state=pt.transition.source,
                    target_state=pt.transition.target,
                    event=pt.transition.event,
                    action=pt.transition.action,
                    measurement_bits=dict(new_bits),
                    context_snapshot=deepcopy(ctx),
                )
            )
    return new_bits


def _bitstring_rank(bitstring: str) -> int:
    try:
        return int(bitstring.replace(" ", ""), 2)
    except ValueError:
        return 0


def _run_circuit_counts(qc, options: QIterativeSimulationOptions, iteration: int) -> dict:
    try:
        from qiskit.providers.basic_provider import BasicSimulator
    except ImportError as exc:  # pragma: no cover - qiskit is a hard dep
        raise QIterativeRuntimeError(
            "qiskit is required for the iterative runtime"
        ) from exc

    sim = BasicSimulator()
    try:
        from qiskit import transpile

        compiled = transpile(qc, sim)
    except Exception:
        compiled = qc

    seed = getattr(options, "seed_simulator", None)
    per_iter_seed = (seed + iteration) if seed is not None else None

    run_kwargs = {"shots": options.inner_shots}
    if per_iter_seed is not None:
        run_kwargs["seed_simulator"] = per_iter_seed

    result = sim.run(compiled, **run_kwargs).result()
    return dict(result.get_counts())


def _initial_context(machine: QMachineDef) -> dict:
    """Build the initial context dict from `machine.context` defaults.

    Only numeric/list<float> fields are exposed as mutable; list<qubit> and
    list<bit> defaults describe the physical register layout and are not
    relevant to runtime guards or mutations.
    """
    ctx: dict = {}
    for field in machine.context:
        value = _default_for_field(field)
        if value is _UNSET:
            continue
        ctx[field.name] = value
    return ctx


class _Unset:
    pass


_UNSET = _Unset()


def _default_for_field(field: ContextField):
    if isinstance(field.type, QTypeScalar):
        if not field.default_value:
            return _UNSET
        try:
            if field.type.kind == "int":
                return int(field.default_value.strip())
            if field.type.kind == "float":
                return float(field.default_value.strip())
            if field.type.kind == "bool":
                return field.default_value.strip().lower() == "true"
        except ValueError:
            return _UNSET
        return field.default_value.strip()

    if isinstance(field.type, QTypeList):
        if field.type.element_type in ("int", "float"):
            if not field.default_value:
                return _UNSET
            items = re.findall(r"-?\d+(?:\.\d+)?", field.default_value)
            cast = float if field.type.element_type == "float" else int
            return [cast(x) for x in items]
        # list<qubit>, list<bit>, list<anything-else> — not runtime context.
        return _UNSET

    return _UNSET
