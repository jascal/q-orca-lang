"""Bridge dispatch: outbound (run a foreign child) and inbound (be a q-orca child).

Transport is process + JSON: an invocation envelope on the runner's stdin, a
result envelope on its stdout. `dispatch_foreign` is q-orca invoking the other
tool; `run_inbound` is q-orca serving as the child a foreign parent invokes.
"""

from __future__ import annotations

import json
import subprocess
from typing import Optional

from q_orca.ast import QOrcaFile
from q_orca.bridge.protocol import BridgeError, make_result, parse_invocation, parse_result

_DEFAULT_TIMEOUT_S = 30


def dispatch_foreign(runner_argv: list[str], invocation: dict, timeout: float = _DEFAULT_TIMEOUT_S) -> dict:
    """Run a foreign child via `runner_argv`, passing the invocation envelope on
    stdin and reading a result envelope from stdout. Raises `BridgeError` for any
    transport failure (unlaunchable, timeout, non-JSON / unsupported version)."""
    payload = json.dumps(invocation)
    try:
        proc = subprocess.run(
            runner_argv, input=payload, capture_output=True, text=True, timeout=timeout
        )
    except FileNotFoundError as exc:
        raise BridgeError(f"foreign runner not found: {runner_argv[0]!r}") from exc
    except subprocess.TimeoutExpired as exc:
        raise BridgeError(f"foreign runner timed out after {timeout}s") from exc

    try:
        return parse_result(proc.stdout)
    except BridgeError:
        # A runner that emitted a valid result envelope (even one carrying a
        # child error) is honoured above; reaching here means the output was not
        # a usable envelope, which is a transport failure.
        if proc.returncode != 0:
            raise BridgeError(
                f"foreign runner exited {proc.returncode}: {proc.stderr.strip()[:200]}"
            )
        raise


def run_inbound(file: QOrcaFile, invocation, seed: Optional[int] = None) -> dict:
    """Serve as the q-orca child a foreign parent invoked.

    Resolves the named child in `file`, runs it with the envelope's `args` and
    `shots`, and returns a result envelope. A child that fails to resolve or
    raises at run time yields a result envelope with an `error` field (a child
    error — not a `BridgeError`).
    """
    from q_orca.runtime.composed import _compute_returns, _machine_has_measurement
    from q_orca.runtime.iterative import simulate_iterative
    from q_orca.runtime.types import QIterativeSimulationOptions

    inv = parse_invocation(invocation)  # accepts a raw envelope (dict) or JSON string
    child = next((m for m in file.machines if m.name == inv["child"]), None)
    if child is None:
        return make_result("", {}, error={
            "code": "UNRESOLVED_CHILD",
            "message": f"machine {inv['child']!r} not found in the supplied file",
        })

    shots = inv.get("shots")
    is_quantum = _machine_has_measurement(child)
    shot_batched = is_quantum and shots is not None and shots > 1
    opts = QIterativeSimulationOptions(
        inner_shots=shots if shot_batched else 1, seed_simulator=seed
    )
    try:
        result = simulate_iterative(child, opts, initial_context=inv.get("args") or {})
    except Exception as exc:  # child reached a runtime failure
        return make_result("", {}, error={
            "code": "CHILD_RUNTIME_ERROR", "message": str(exc),
        })

    returns = _compute_returns(
        child, result.final_context, getattr(result, "aggregate_counts", {}) or {}, shot_batched
    )
    return make_result(result.final_state, returns)
