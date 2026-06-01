"""Compile-time bounded-loop analysis and emission (add-bounded-loop-annotation).

This module is shared by the QASM and Qiskit compilers. It provides:

- ``evaluate_loop_bound`` — evaluate a fixed ``[loop <expr>]`` bound to an int
  at compile time, over the machine's integer context defaults plus the
  whitelisted math functions ``sqrt``/``ceil``/``floor``/``round`` and the
  constant ``pi`` (`evaluate_angle` only covers angle-shaped expressions, so a
  dedicated restricted evaluator is used instead).
- ``analyze_loops`` — map each ``[loop …]`` entry state to its loop body (the
  strongly-connected component it enters), the resolved bound or predicate.
- ``build_gate_sequence`` — a loop-aware BFS over the transition graph,
  emitting ``__loop_start__`` / ``__loop_end__`` sentinels around the body
  steps (or, under ``unroll=True``, the body repeated ``N`` times).
"""

from __future__ import annotations

import ast as _ast
import math
from dataclasses import dataclass
from typing import Callable, Optional

from q_orca.ast import QMachineDef
from q_orca.verifier.roles import _strongly_connected_components

LOOP_START = "__loop_start__"
LOOP_END = "__loop_end__"

# Default worst-case iteration cap used when reporting an adaptive loop's
# resource range `[body_cost, body_cost × MAX_LOOP_BOUND]`.
MAX_LOOP_BOUND = 1000


class LoopBoundError(ValueError):
    """A fixed loop bound could not be evaluated at compile time."""


_ALLOWED_FUNCS: dict[str, Callable] = {
    "sqrt": math.sqrt,
    "ceil": math.ceil,
    "floor": math.floor,
    "round": round,
    "abs": abs,
    "min": min,
    "max": max,
    "log": math.log,
    "log2": math.log2,
    "exp": math.exp,
}
_ALLOWED_CONSTS: dict[str, float] = {"pi": math.pi, "e": math.e}


def _eval_node(node, env: dict):
    if isinstance(node, _ast.Expression):
        return _eval_node(node.body, env)
    if isinstance(node, _ast.Constant):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        raise LoopBoundError(f"unsupported constant {node.value!r} in loop bound")
    if isinstance(node, _ast.Name):
        if node.id in env:
            return env[node.id]
        raise LoopBoundError(f"unknown name {node.id!r} in loop bound")
    if isinstance(node, _ast.BinOp):
        left = _eval_node(node.left, env)
        right = _eval_node(node.right, env)
        op = node.op
        if isinstance(op, _ast.Add):
            return left + right
        if isinstance(op, _ast.Sub):
            return left - right
        if isinstance(op, _ast.Mult):
            return left * right
        if isinstance(op, _ast.Div):
            return left / right
        if isinstance(op, _ast.FloorDiv):
            return left // right
        if isinstance(op, _ast.Mod):
            return left % right
        if isinstance(op, _ast.Pow):
            return left ** right
        raise LoopBoundError(f"unsupported operator {type(op).__name__} in loop bound")
    if isinstance(node, _ast.UnaryOp):
        val = _eval_node(node.operand, env)
        if isinstance(node.op, _ast.USub):
            return -val
        if isinstance(node.op, _ast.UAdd):
            return +val
        raise LoopBoundError("unsupported unary operator in loop bound")
    if isinstance(node, _ast.Call):
        if not isinstance(node.func, _ast.Name) or node.func.id not in _ALLOWED_FUNCS:
            fn = getattr(node.func, "id", "<expr>")
            raise LoopBoundError(f"unsupported function {fn!r} in loop bound")
        args = [_eval_node(a, env) for a in node.args]
        return _ALLOWED_FUNCS[node.func.id](*args)
    raise LoopBoundError(f"unsupported expression {type(node).__name__} in loop bound")


def evaluate_loop_bound(machine: QMachineDef, expr_text: str) -> int:
    """Evaluate a fixed ``[loop <expr>]`` bound to a non-negative integer.

    Integer context fields contribute their declared defaults. Raises
    ``LoopBoundError`` on an unparseable expression, an unknown name, or a
    referenced field with no concrete default.
    """
    env: dict = dict(_ALLOWED_CONSTS)
    for f in machine.context:
        if getattr(f.type, "kind", None) == "int" and f.default_value not in (None, ""):
            try:
                env[f.name] = int(f.default_value)
            except (ValueError, TypeError):
                pass
    try:
        tree = _ast.parse(expr_text, mode="eval")
    except SyntaxError as e:
        raise LoopBoundError(f"could not parse loop bound {expr_text!r}: {e}") from e
    val = _eval_node(tree, env)
    fval = float(val)
    n = int(round(fval)) if abs(fval - round(fval)) < 1e-9 else int(math.ceil(fval))
    if n < 0:
        raise LoopBoundError(f"loop bound {expr_text!r} evaluated to a negative value ({n})")
    return n


@dataclass
class LoopInfo:
    entry: str
    kind: str  # 'fixed' | 'adaptive'
    body_states: set
    bound: Optional[int] = None       # fixed only (resolved int)
    bound_expr: Optional[str] = None  # fixed only (source text)
    predicate: Optional[str] = None   # adaptive only

    @property
    def label(self) -> str:
        """Short back-edge label for Mermaid (≤ 30 chars)."""
        if self.kind == "fixed":
            n = self.bound if self.bound is not None else self.bound_expr
            return f"×{n}"
        cond = f"until {self.predicate or ''}".strip()
        return cond if len(cond) <= 30 else cond[:27] + "..."


def analyze_loops(machine: QMachineDef, *, evaluate: bool = True) -> dict[str, LoopInfo]:
    """Map each unambiguous ``[loop …]`` entry state to its ``LoopInfo``.

    Ambiguous bodies (two annotated states in one cycle) are skipped — the
    verifier rejects those with ``LOOP_AMBIGUOUS_BODY`` before compilation.
    """
    loop_states = {s.name: s for s in machine.states if getattr(s, "loop", None) is not None}
    if not loop_states:
        return {}
    nodes = [s.name for s in machine.states]
    edges: dict[str, list[str]] = {n: [] for n in nodes}
    for t in machine.transitions:
        if t.source in edges:
            edges[t.source].append(t.target)
    sccs = _strongly_connected_components(nodes, edges)

    out: dict[str, LoopInfo] = {}
    for entry_name, state in loop_states.items():
        comp = next((c for c in sccs if entry_name in c), {entry_name})
        if sum(1 for n in comp if n in loop_states) >= 2:
            continue  # ambiguous — verifier handles it
        info = LoopInfo(entry=entry_name, kind=state.loop.kind, body_states=set(comp))
        if state.loop.kind == "fixed":
            info.bound_expr = state.loop.bound_expr
            if evaluate:
                info.bound = evaluate_loop_bound(machine, state.loop.bound_expr)
        else:
            info.predicate = state.loop.bound_expr
        out[entry_name] = info
    return out


def _collect_loop_body(entry: str, info: LoopInfo, machine: QMachineDef,
                       gates_for: Callable, comment_for: Callable):
    """Return (body_steps, exit_steps, exit_targets) for a loop body.

    Body steps are the in-body (non-`loop_done`, in-body-target) transition
    actions in BFS order; exit steps are the `loop_done`/body-leaving transition
    actions (emitted after the loop block); exit targets continue the outer BFS.
    """
    body = info.body_states
    body_steps: list = []
    exit_steps: list = []
    exit_targets: list[str] = []
    seen: set[str] = set()
    queue = [entry]
    while queue:
        cur = queue.pop(0)
        if cur in seen:
            continue
        seen.add(cur)
        for t in (t for t in machine.transitions if t.source == cur):
            leaves = t.loop_done or t.target not in body
            if leaves:
                if t.action:
                    exit_steps.append((t.action, gates_for(t), comment_for(t)))
                exit_targets.append(t.target)
            else:
                if t.action:
                    body_steps.append((t.action, gates_for(t), comment_for(t)))
                if t.target not in seen:
                    queue.append(t.target)
    return body_steps, exit_steps, exit_targets


def build_gate_sequence(machine: QMachineDef, gates_for: Callable, comment_for: Callable,
                        *, unroll: bool = False) -> list:
    """Loop-aware BFS gate-sequence extraction shared by both compilers.

    ``gates_for(transition) -> list`` builds the gate list for a transition's
    action; ``comment_for(transition) -> str`` builds the step comment. Returns
    ``(action_name, [gates], comment)`` triples. When a state carries a
    ``[loop …]`` annotation, its body is wrapped in ``__loop_start__`` /
    ``__loop_end__`` sentinel steps (the ``LoopInfo`` rides in the comment
    slot); under ``unroll=True`` a fixed body is repeated ``bound`` times and an
    adaptive body is emitted once.
    """
    action_map = {a.name: a for a in machine.actions}
    initial = next((s for s in machine.states if s.is_initial), None)
    if not initial:
        return []
    loops = analyze_loops(machine, evaluate=True)

    steps: list = []
    visited: set[str] = set()
    queue = [initial.name]
    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)

        if current in loops:
            info = loops[current]
            visited |= info.body_states
            body_steps, exit_steps, exit_targets = _collect_loop_body(
                current, info, machine, gates_for, comment_for)
            if unroll and info.kind == "fixed":
                for _ in range(info.bound or 0):
                    steps.extend(body_steps)
            elif unroll:  # adaptive — unknown count, emit once
                steps.extend(body_steps)
            else:
                steps.append((LOOP_START, [], info))
                steps.extend(body_steps)
                steps.append((LOOP_END, [], info))
            steps.extend(exit_steps)
            for tgt in exit_targets:
                if tgt not in visited:
                    queue.append(tgt)
            continue

        for t in (t for t in machine.transitions if t.source == current):
            if t.action:
                steps.append((t.action, gates_for(t), comment_for(t)))
            transition_action = action_map.get(t.action) if t.action else None
            is_mid_circuit = (
                transition_action is not None
                and transition_action.mid_circuit_measure is not None
            )
            is_terminal_measure = (
                ("measure" in t.event.lower() or "collapse" in t.event.lower())
                and not is_mid_circuit
            )
            if not is_terminal_measure and t.target not in visited:
                queue.append(t.target)
    return steps
