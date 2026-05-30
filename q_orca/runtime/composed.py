"""Composed-machine execution (`add-composed-runtime`).

`run_composed` walks a parent machine and, at each `invoke:` state, executes the
resolved child (classical run-to-completion, quantum single-shot, or quantum
shot-batched), computes the declared return statistics into the synthesized
`prob_`/`hist_`/`var_` aggregates (the same names the composition verifier
checks), and threads them back into the parent context.

v1 supports the classical-orchestrator-parent shape: a parent whose own
transitions are plain or context-update only (its quantum work is delegated to
children). A gate/measurement-bearing action *on an invoke-bearing parent* is
rejected with a clear error — that mixed case is a documented follow-up.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Optional

from q_orca.ast import QMachineDef, QOrcaFile
from q_orca.runtime import context_ops
from q_orca.runtime.iterative import (
    _PendingTransition,
    _enabled_transitions,
    _flush_segment,
    _initial_context,
    _initial_state_name,
    simulate_iterative,
)
from q_orca.runtime.types import (
    ComposedRunResult,
    QIterativeRuntimeError,
    QIterativeSimulationOptions,
)

_DEFAULT_DEPTH_CEILING = 32
_BIT_RETURN_RE = re.compile(r"^bits\[(\d+)\]$")


def _machine_has_measurement(machine: QMachineDef) -> bool:
    return any(
        a.measurement is not None or a.mid_circuit_measure is not None
        for a in machine.actions
    )


def _sanitize_return_name(name: str) -> str:
    """`bits[0]` → `bits_0` — mirrors verifier/composition._sanitize."""
    return name.replace("[", "_").replace("]", "").replace(".", "_")


def run_composed(
    file: QOrcaFile,
    machine: QMachineDef,
    options: Optional[QIterativeSimulationOptions] = None,
    base_path: Optional[str] = None,
    import_graph=None,
    foreign_runners: Optional[dict] = None,
    depth_ceiling: int = _DEFAULT_DEPTH_CEILING,
    _depth: int = 0,
    _initial_overrides: Optional[dict] = None,
) -> ComposedRunResult:
    """Execute `machine` (and everything it invokes); return its final context."""
    opts = options or QIterativeSimulationOptions()
    if _depth > depth_ceiling:
        raise QIterativeRuntimeError(
            f"composition depth ceiling {depth_ceiling} exceeded"
        )

    # No invoke states → the existing single-machine runtime, unchanged.
    if not any(s.invoke is not None for s in machine.states):
        result = simulate_iterative(machine, opts, initial_context=_initial_overrides)
        return ComposedRunResult(
            machine=machine.name,
            success=result.success,
            final_state=result.final_state,
            final_context=result.final_context,
            aggregate_counts=getattr(result, "aggregate_counts", {}) or {},
        )

    return _walk_composed(
        file, machine, opts, base_path, import_graph, foreign_runners,
        depth_ceiling, _depth, _initial_overrides,
    )


def _walk_composed(file, machine, opts, base_path, import_graph, foreign_runners, depth_ceiling, depth, overrides):
    action_map = {a.name: a for a in machine.actions}
    guard_map = {g.name: g for g in machine.guards}
    state_map = {s.name: s for s in machine.states}
    final_states = {s.name for s in machine.states if s.is_final}

    ctx = _initial_context(machine)
    if overrides:
        ctx.update(overrides)
    bits: dict[int, int] = {}
    child_runs: list[dict] = []
    # The parent may carry its own gate/measurement transitions interleaved with
    # invokes; accumulate them into a segment and flush (build + run the circuit)
    # around invoke / context-update / final boundaries, reusing the iterative
    # runtime's segment machinery.
    segment: list = []
    aggregate_counts: dict = {}
    trace: list = []

    def flush():
        nonlocal bits, segment
        bits = _flush_segment(
            machine, opts, ctx, bits, segment, trace, aggregate_counts, steps
        )
        segment = []

    current = _initial_state_name(machine)
    steps = 0
    while True:
        steps += 1
        if steps > opts.iteration_ceiling:
            raise QIterativeRuntimeError(
                f"iteration ceiling {opts.iteration_ceiling} exceeded in {machine.name!r}"
            )
        if current in final_states:
            flush()  # run any trailing parent gate segment
            break

        state = state_map[current]
        if state.invoke is not None:
            flush()  # parent bits observable to the invoke bindings + later guards
            summary, ctx = _run_invoke(
                file, state, ctx, opts, base_path, import_graph, foreign_runners,
                depth_ceiling, depth,
            )
            for key, count in (summary.get("aggregate_counts") or {}).items():
                aggregate_counts[key] = aggregate_counts.get(key, 0) + count
            child_runs.append(summary)
            enabled = _enabled_transitions(machine, current, ctx, bits, guard_map)
            if not enabled:
                break  # invoke state with no outgoing transition → fall through
            current = enabled[0].target
            continue

        enabled = _enabled_transitions(machine, current, ctx, bits, guard_map)
        if not enabled:
            raise QIterativeRuntimeError(
                f"stuck state {current!r} in {machine.name!r}: no guarded transition enabled"
            )
        transition = enabled[0]

        if transition.action:
            action = action_map.get(transition.action)
            if action is not None and action.context_update is not None:
                flush()  # measured bits observable to branch selection
                ctx = context_ops.apply(action.context_update, ctx, bits)
            elif action is not None and (
                action.effect
                or action.gate is not None
                or action.mid_circuit_measure is not None
                or action.measurement is not None
                or action.conditional_gate is not None
            ):
                segment.append(
                    _PendingTransition(transition=transition, action=action, iteration=steps)
                )
        current = transition.target

    return ComposedRunResult(
        machine=machine.name,
        success=True,
        final_state=current,
        final_context=ctx,
        child_runs=child_runs,
        aggregate_counts=aggregate_counts,
    )


def _run_invoke(file, state, ctx, opts, base_path, import_graph, foreign_runners, depth_ceiling, depth):
    inv = state.invoke
    child = _resolve_child(file, inv.child_name, import_graph)
    if child is None:
        # Foreign child: not resolvable in-tool but declared as the other tool's.
        if foreign_runners and inv.child_name in foreign_runners:
            return _run_foreign_invoke(state, inv, ctx, foreign_runners[inv.child_name])
        raise QIterativeRuntimeError(
            f"invoke state {state.name}: child {inv.child_name!r} did not resolve "
            f"(not in this file/import graph, and no foreign runner registered)"
        )

    child_init = {
        param: _eval_parent_expr(expr, ctx) for param, expr in inv.arg_bindings.items()
    }

    is_quantum = _machine_has_measurement(child)
    shot_batched = is_quantum and inv.shots is not None and inv.shots > 1
    child_opts = replace(opts, inner_shots=inv.shots if shot_batched else 1)

    child_has_invokes = any(s.invoke is not None for s in child.states)
    if child_has_invokes:
        # Nested composition: recurse. The composed child surfaces its own
        # measured-bit distribution on its result, so aggregation is identical
        # whether the child is a leaf or composed.
        child_result = run_composed(
            file, child, child_opts, base_path=base_path, import_graph=import_graph,
            foreign_runners=foreign_runners, depth_ceiling=depth_ceiling,
            _depth=depth + 1, _initial_overrides=child_init,
        )
    else:
        child_result = simulate_iterative(child, child_opts, initial_context=child_init)
    aggregate_counts = getattr(child_result, "aggregate_counts", {}) or {}

    returns = _compute_returns(child, child_result.final_context, aggregate_counts, shot_batched)

    new_ctx = dict(ctx)
    for parent_field, child_return in inv.return_bindings.items():
        if child_return in returns:
            new_ctx[parent_field] = returns[child_return]

    summary = {
        "invoke_state": state.name,
        "child": child.name,
        "shots": inv.shots,
        "returns": returns,
        "aggregate_counts": aggregate_counts,  # for upward accumulation
    }
    return summary, new_ctx


def _run_foreign_invoke(state, inv, ctx, runner_argv):
    """Dispatch an invoke to a foreign (other-tool) child over the bridge."""
    from q_orca.bridge.dispatch import dispatch_foreign
    from q_orca.bridge.protocol import build_invocation

    args = {param: _eval_parent_expr(expr, ctx) for param, expr in inv.arg_bindings.items()}
    envelope = build_invocation(inv.child_name, args, inv.shots, dict(inv.return_bindings))
    result = dispatch_foreign(list(runner_argv), envelope)  # raises BridgeError on transport failure
    if result.get("error"):
        raise QIterativeRuntimeError(
            f"invoke state {state.name}: foreign child {inv.child_name!r} returned an "
            f"error: {result['error']}"
        )
    returns = result["returns"]
    new_ctx = dict(ctx)
    for parent_field, child_return in inv.return_bindings.items():
        if child_return in returns:
            new_ctx[parent_field] = returns[child_return]
    summary = {
        "invoke_state": state.name,
        "child": inv.child_name,
        "shots": inv.shots,
        "foreign": True,
        "returns": returns,
    }
    return summary, new_ctx


def _resolve_child(file, name, import_graph):
    for m in file.machines:
        if m.name == name:
            return m
    if import_graph is not None:
        return import_graph.lookup_machine(name)
    return None


def _eval_parent_expr(expr: str, ctx: dict):
    """Resolve a bare field `theta` or an indexed element `theta[0]`."""
    m = re.match(r"^([A-Za-z_]\w*)\[(\d+)\]$", expr)
    if m:
        base, idx = m.group(1), int(m.group(2))
        value = ctx.get(base)
        if isinstance(value, (list, tuple)) and idx < len(value):
            return value[idx]
        return None
    return ctx.get(expr)


def _compute_returns(child, final_ctx, aggregate_counts, shot_batched):
    returns: dict = {}
    for r in child.returns:
        bit_match = _BIT_RETURN_RE.match(r.name)
        if bit_match:
            bit_idx = int(bit_match.group(1))
            prob, hist = _per_bit_stats(aggregate_counts, bit_idx)
            returns[r.name] = 1 if prob >= 0.5 else 0  # raw (dominant) value
            if shot_batched and r.statistics:
                s = _sanitize_return_name(r.name)
                if "expectation" in r.statistics:
                    returns[f"prob_{s}"] = prob
                if "histogram" in r.statistics:
                    returns[f"hist_{s}"] = hist
                if "variance" in r.statistics:
                    returns[f"var_{s}"] = prob * (1.0 - prob)
        else:
            returns[r.name] = final_ctx.get(r.name)
    return returns


def _per_bit_stats(aggregate_counts: dict, bit_idx: int) -> tuple[float, dict]:
    """Marginal P(bit==1) and {0: n0, 1: n1} from full-bitstring shot counts.

    Qiskit counts keys are little-endian (and may contain spaces); reversing
    aligns position `bit_idx` with clbit `bit_idx` (matching the iterative
    runtime's convention).
    """
    total = sum(aggregate_counts.values())
    if total == 0:
        return 0.0, {0: 0, 1: 0}
    ones = 0
    for key, count in aggregate_counts.items():
        bitstr = key.replace(" ", "")[::-1]
        if bit_idx < len(bitstr) and bitstr[bit_idx] == "1":
            ones += count
    return ones / total, {0: total - ones, 1: ones}
