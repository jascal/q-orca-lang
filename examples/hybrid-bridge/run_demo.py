#!/usr/bin/env python3
"""Hybrid quantum-classical demo over the cross-tool bridge.

A classical **Orca** orchestrator (`vqe-orchestrator.orca.md`, run by
orca-lang's `orca_runtime_python`) tunes the rotation angle `theta` of a
single-qubit **q-orca** circuit (`forward.q.orca.md`) so that the measured
probability of outcome 1 hits a target. The two tools share no AST and no Python
environment — every iteration crosses the boundary as bridge-protocol 1.0 JSON
envelopes over a subprocess (`q-orca run ... --bridge`, stdin → stdout).

  classical loop (Orca)            quantum forward pass (q-orca)
  ┌───────────────────┐  invoke   ┌──────────────────────────┐
  │ measuring ─────────┼─────────▶ │ Ry(theta) ; measure → bit │
  │  ▲            │     │  envelope │   prob_bits_0 = sin²(θ/2) │
  │  │ next       ▼     │ ◀─────────┼──── result envelope ──────┘
  │ evaluate ◀─ gradient_step      │
  └───────────────────┘ (until converged)

Run it (the two packages live in separate venvs — that's the point):

    Q_ORCA_BIN=/path/to/q-orca-lang/.venv/bin/q-orca \\
      /path/to/orca-lang/.venv/bin/python run_demo.py

`Q_ORCA_BIN` defaults to `q-orca` on PATH; set it to the q-orca venv's console
script if the globally-installed one is older than the `run --bridge` subcommand.
"""

from __future__ import annotations

import asyncio
import math
import os
from pathlib import Path

from orca_runtime_python.machine import OrcaMachine
from orca_runtime_python.parser import parse_orca_md

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE / "vqe-orchestrator.orca.md"
FORWARD = HERE / "forward.q.orca.md"

Q_ORCA_BIN = os.environ.get("Q_ORCA_BIN", "q-orca")

# --- optimization hyperparameters (classical side) -------------------------
# The *target* P(measure 1) is owned by the Orca machine's context (its
# `target` default in vqe-orchestrator.orca.md) — the single source of truth the
# `gradient_step` action and the guards both read. Set the TARGET env var to
# override it for a run (e.g. TARGET=0.85 ⇒ θ* = 2·asin√0.85 ≈ 2.348).
TARGET_OVERRIDE = os.environ.get("TARGET")
GAIN = 2.0          # proportional step size (≈ Newton near the target, where dP/dθ≈0.5)
TOL = 0.04          # convergence band on |target − measured prob|
MAX_ITERS = 12      # hard cap so the loop always terminates
SHOTS = 4096        # measurement shots per forward pass
SEED = 7            # fixed simulator seed → reproducible run


def make_gradient_step(report):
    """Build the `gradient_step` action handler.

    Runs on the `measuring → evaluate` transition, so `ctx["prob"]` already holds
    this iteration's measured expectation (bound back from the child's
    `prob_bits_0`). It records the step, updates `theta` from the error, and sets
    `converged` — the boolean the Orca guards branch on.
    """

    def gradient_step(ctx, event):
        iteration = ctx["iteration"] + 1
        theta_used = ctx["theta"]
        prob = ctx["prob"]
        error = ctx["target"] - prob

        new_theta = min(math.pi - 0.01, max(0.01, theta_used + GAIN * error))
        converged = abs(error) < TOL or iteration >= MAX_ITERS

        report(iteration, theta_used, prob, error, new_theta, converged)
        return {"theta": new_theta, "iteration": iteration, "converged": converged}

    return gradient_step


async def main() -> int:
    machine = OrcaMachine(definition=parse_orca_md(ORCHESTRATOR.read_text()))
    if TARGET_OVERRIDE is not None:
        machine.context["target"] = float(TARGET_OVERRIDE)
    target = machine.context["target"]          # single source of truth (Orca context)
    theta_star = 2 * math.asin(math.sqrt(target))

    print("─" * 72)
    print("Hybrid quantum-classical optimization over the cross-tool bridge")
    print("─" * 72)
    print(f"  classical orchestrator : {ORCHESTRATOR.name}   (orca-lang runtime-python)")
    print(f"  quantum forward pass   : {FORWARD.name}        (q-orca, over the bridge)")
    print(f"  bridge runner          : {Q_ORCA_BIN} run … --bridge")
    print(f"  goal                   : tune θ so P(measure 1) → {target}  (θ* = {theta_star:.4f})")
    print(f"  per pass               : {SHOTS} shots, seed {SEED}")
    print()
    header = f"  {'iter':>4} │ {'θ used':>8} │ {'measured P(1)':>13} │ {'error':>8} │ {'θ → next':>10}"
    print(header)
    print("  " + "─" * (len(header) - 2))

    def report(iteration, theta_used, prob, error, new_theta, converged):
        tail = "(converged)" if converged else f"{new_theta:>10.4f}"
        print(f"  {iteration:>4} │ {theta_used:>8.4f} │ {prob:>13.4f} │ {error:>+8.4f} │ {tail}")

    machine.register_foreign_runner(
        "QForward",
        [Q_ORCA_BIN, "run", str(FORWARD), "--bridge", "--seed", str(SEED)],
    )
    machine.register_action("gradient_step", make_gradient_step(report))

    await machine.start()         # → idle
    await machine.send("begin")   # idle → measuring →(bridge)→ MEASURED → evaluate
    while machine.state.leaf() != "done":
        await machine.send("next")  # evaluate → measuring →(bridge)→ … or → done

    ctx = machine.context
    invocations = ctx["iteration"]
    print()
    print("  " + "─" * (len(header) - 2))
    print(f"  final state : {machine.state.leaf()}")
    print(f"  final θ     : {ctx['theta']:.4f}   (θ* = {theta_star:.4f})")
    print(f"  final P(1)  : {ctx['prob']:.4f}   (target {target})")
    print(f"  quantum calls across the bridge : {invocations}  ({invocations * SHOTS} total shots)")
    print("─" * 72)
    await machine.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
