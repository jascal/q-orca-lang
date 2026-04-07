"""Hybrid Classical + Quantum Controller Demo

Demonstrates using a classical Orca state machine (orca-runtime-python) as the
outer orchestration loop, with Q-Orca quantum state machines as the inner
refinement loop.

Workflow:
  idle -> designing -> verifying -> (refining <-> verifying)* -> compiling -> analyzing -> complete

The classical controller manages experiment lifecycle while Q-Orca handles
quantum circuit definition, verification, and compilation.

Requirements:
  pip install orca-runtime-python   # classical state machine runtime
  pip install q-orca                # quantum state machine language (or install from local)
"""

import asyncio
from pathlib import Path

from orca_runtime_python import (
    parse_orca_md,
    OrcaMachine,
    get_event_bus,
    Event,
    EventType,
)

from q_orca import (
    parse_q_orca_markdown,
    verify,
    VerifyOptions,
    compile_to_mermaid,
    compile_to_qasm,
    compile_to_qiskit,
    QSimulationOptions,
)

# ── Quantum circuit definitions ──────────────────────────────────────────────

# A deliberately broken Bell entangler: creates the Bell state |psi> but has no
# measurement transitions. The verifier will catch that |psi> is a DEADLOCK
# (non-final state with no outgoing transitions) and that measure_done is an
# orphan event. The refinement loop adds the missing collapse branches.

BROKEN_BELL_ENTANGLER = """\
# machine BellEntangler

## context
| Field      | Type          | Default   |
|------------|---------------|-----------|
| qubits     | list<qubit>   | [q0, q1]  |
| outcome    | int           | -1        |

## events
- prepare_H
- entangle
- measure_done

## state |00> [initial]
> Ground state, both qubits in |0>

## state |+0>
> Qubit 0 in superposition after Hadamard

## state |psi>
> Bell state (|00> + |11>)/sqrt(2) -- BUG: no measurement transitions!

## transitions
| Source | Event     | Guard | Target | Action              |
|--------|-----------|-------|--------|---------------------|
| |00>   | prepare_H |       | |+0>   | apply_H_on_q0      |
| |+0>   | entangle  |       | |psi>  | apply_CNOT_q0_to_q1 |

## actions
| Name                | Signature        | Effect              |
|---------------------|------------------|----------------------|
| apply_H_on_q0       | (qs) -> qs       | Hadamard(qs[0])     |
| apply_CNOT_q0_to_q1 | (qs) -> qs       | CNOT(qs[0], qs[1]) |

## verification rules
- unitarity: all gates preserve norm
"""

# The fixed version: adds measurement collapse branches from |psi>.
FIXED_BELL_ENTANGLER = """\
# machine BellEntangler

## context
| Field      | Type          | Default   |
|------------|---------------|-----------|
| qubits     | list<qubit>   | [q0, q1]  |
| outcome    | int           | -1        |

## events
- prepare_H
- entangle
- measure_done

## state |00> [initial]
> Ground state, both qubits in |0>

## state |+0>
> Qubit 0 in superposition after Hadamard

## state |psi> = (|00> + |11>)/\\u221a2
> Bell state -- maximally entangled

## state |00_collapsed> [final]
> Measurement collapsed to |00>

## state |11_collapsed> [final]
> Measurement collapsed to |11>

## transitions
| Source | Event        | Guard                   | Target          | Action              |
|--------|--------------|-------------------------|-----------------|---------------------|
| |00>   | prepare_H    |                         | |+0>            | apply_H_on_q0      |
| |+0>   | entangle     |                         | |psi>           | apply_CNOT_q0_to_q1 |
| |psi>  | measure_done | prob_collapse('00')=0.5 | |00_collapsed>  | set_outcome_0       |
| |psi>  | measure_done | prob_collapse('11')=0.5 | |11_collapsed>  | set_outcome_1       |

## guards
| Name                | Expression                                    |
|---------------------|-----------------------------------------------|
| prob_collapse('00') | fidelity(|\\u03c8>, |00>) ** 2 \\u2248 0.5     |
| prob_collapse('11') | fidelity(|\\u03c8>, |11>) ** 2 \\u2248 0.5     |

## actions
| Name                | Signature              | Effect              |
|---------------------|------------------------|----------------------|
| apply_H_on_q0       | (qs) -> qs             | Hadamard(qs[0])     |
| apply_CNOT_q0_to_q1 | (qs) -> qs             | CNOT(qs[0], qs[1]) |
| set_outcome_0       | (ctx, val) -> Context  | ctx.outcome = 0     |
| set_outcome_1       | (ctx, val) -> Context  | ctx.outcome = 1     |

## verification rules
- unitarity: all gates preserve norm
- entanglement: Bell state has Schmidt rank > 1
- no-cloning: no copy operations
"""


# ── Shared workspace ─────────────────────────────────────────────────────────

class QuantumWorkspace:
    """Shared workspace holding quantum machine state across classical transitions."""

    def __init__(self):
        self.quantum_source: str = ""
        self.machine_def = None
        self.verification_errors: list = []
        self.is_valid: bool = False
        self.qasm_output: str = ""
        self.qiskit_output: str = ""
        self.mermaid_output: str = ""


workspace = QuantumWorkspace()


# ── Action handlers (called during classical state machine transitions) ──────

def init_experiment(ctx, payload=None):
    """Load the (broken) quantum machine spec into the workspace."""
    spec = (payload or {}).get("spec", "Bell state entangler")
    workspace.quantum_source = BROKEN_BELL_ENTANGLER

    parsed = parse_q_orca_markdown(workspace.quantum_source)
    machine = parsed.file.machines[0]
    workspace.machine_def = machine

    print(f"\n  [init_experiment] Loaded quantum spec: {spec}")
    print(f"  [init_experiment] Machine: {machine.name}")
    print(f"  [init_experiment] States: {[s.name for s in machine.states]}")
    print(f"  [init_experiment] Transitions: {len(machine.transitions)}")

    return {"experiment": spec, "status": "designing", "iteration": 0}


def verify_circuit(ctx, payload=None):
    """Run Q-Orca verification pipeline on the current quantum source."""
    iteration = ctx.get("iteration", 0)
    print(f"\n  [verify_circuit] Q-Orca 5-stage verification (iteration {iteration})...")

    parsed = parse_q_orca_markdown(workspace.quantum_source)
    machine = parsed.file.machines[0]
    workspace.machine_def = machine

    opts = VerifyOptions(skip_completeness=True, skip_dynamic=True)
    result = verify(machine, opts)

    workspace.verification_errors = result.errors
    workspace.is_valid = result.valid
    error_count = sum(1 for e in result.errors if e.severity == "error")
    warning_count = sum(1 for e in result.errors if e.severity == "warning")

    print(f"  [verify_circuit] Machine: {machine.name} "
          f"({len(machine.states)} states, {len(machine.transitions)} transitions)")
    print(f"  [verify_circuit] Result: {'PASS' if result.valid else 'FAIL'} "
          f"({error_count} errors, {warning_count} warnings)")

    for err in result.errors:
        marker = "ERROR" if err.severity == "error" else "WARN "
        print(f"  [verify_circuit]   [{marker}] {err.code}: {err.message}")
        if err.suggestion:
            print(f"  [verify_circuit]            -> {err.suggestion}")

    return {"error_count": error_count, "status": "verified" if result.valid else "invalid"}


def refine_circuit(ctx, payload=None):
    """Fix the quantum machine based on verification errors.

    In production this would use refine_skill() with an LLM provider.
    For this demo we apply a deterministic fix: adding the missing
    measurement/collapse branches to the Bell entangler.
    """
    iteration = ctx.get("iteration", 0) + 1

    print(f"\n  [refine_circuit] Refinement iteration {iteration}")
    print(f"  [refine_circuit] Fixing {len(workspace.verification_errors)} issue(s):")

    for err in workspace.verification_errors:
        if err.severity == "error":
            print(f"  [refine_circuit]   -> {err.code}: {err.message}")

    # Apply the deterministic fix
    workspace.quantum_source = FIXED_BELL_ENTANGLER

    print(f"  [refine_circuit] Applied fix:")
    print(f"  [refine_circuit]   + Added state expression for |psi> (Bell state)")
    print(f"  [refine_circuit]   + Added |00_collapsed> and |11_collapsed> final states")
    print(f"  [refine_circuit]   + Added measure_done transitions with collapse guards")
    print(f"  [refine_circuit]   + Added probability guards and outcome actions")

    return {"iteration": iteration, "status": "refined"}


def compile_circuit(ctx, payload=None):
    """Compile the verified quantum machine to QASM, Qiskit, and Mermaid."""
    print(f"\n  [compile_circuit] Compiling to multiple targets...")

    machine = workspace.machine_def

    workspace.mermaid_output = compile_to_mermaid(machine)
    workspace.qasm_output = compile_to_qasm(machine)
    workspace.qiskit_output = compile_to_qiskit(
        machine, QSimulationOptions(analytic=True, run=False)
    )

    print(f"  [compile_circuit] Mermaid diagram: {len(workspace.mermaid_output)} chars")
    print(f"  [compile_circuit] OpenQASM 3.0:    {len(workspace.qasm_output)} chars")
    print(f"  [compile_circuit] Qiskit script:   {len(workspace.qiskit_output)} chars")

    return {"status": "compiled"}


def analyze_results(ctx, payload=None):
    """Display the compiled quantum circuit outputs."""
    print(f"\n  [analyze_results] Compiled outputs:\n")

    print("  --- OpenQASM 3.0 ---")
    for line in workspace.qasm_output.strip().splitlines():
        print(f"    {line}")

    print(f"\n  --- Mermaid State Diagram ---")
    for line in workspace.mermaid_output.strip().splitlines():
        print(f"    {line}")

    qiskit_lines = workspace.qiskit_output.strip().splitlines()
    print(f"\n  --- Qiskit Script ({len(qiskit_lines)} lines) ---")
    for line in qiskit_lines[:12]:
        print(f"    {line}")
    if len(qiskit_lines) > 12:
        print(f"    ... ({len(qiskit_lines) - 12} more lines)")

    return {"status": "analyzed"}


def log_failure(ctx, payload=None):
    """Log experiment failure after max retries."""
    print(f"\n  [log_failure] FAILED after {ctx.get('iteration', 0)} refinement attempts")
    return {"status": "failed"}


def log_success(ctx, payload=None):
    """Log successful experiment completion."""
    print(f"\n  [log_success] COMPLETE -- "
          f"{ctx.get('iteration', 0)} refinement iteration(s) needed")
    return {"status": "complete"}


# ── Main demo ────────────────────────────────────────────────────────────────

async def main():
    print("""
+------------------------------------------------------------------+
|  HYBRID CLASSICAL + QUANTUM CONTROLLER DEMO                      |
|                                                                   |
|  Outer loop: Classical Orca state machine (orca-runtime-python)  |
|  Inner loop: Q-Orca quantum circuit refinement (q-orca)          |
+------------------------------------------------------------------+
""")

    # ── 1. Parse the classical controller ─────────────────────────────────
    print("=" * 66)
    print("  PHASE 1: Load classical controller state machine")
    print("=" * 66)

    controller_path = Path(__file__).parent / "controller.orca.md"
    controller_def = parse_orca_md(controller_path.read_text())

    print(f"  Machine:     {controller_def.name}")
    print(f"  States:      {[s.name for s in controller_def.states]}")
    print(f"  Transitions: {len(controller_def.transitions)}")

    # ── 2. Create and wire up the classical machine ───────────────────────
    print(f"\n{'=' * 66}")
    print("  PHASE 2: Start classical controller + register quantum actions")
    print("=" * 66)

    bus = get_event_bus()

    async def on_transition(event: Event):
        p = event.payload
        print(f"\n  >> STATE: {p.get('from', '?')} -> {p.get('to', '?')}")

    bus.subscribe(EventType.TRANSITION_COMPLETED, on_transition)

    controller = OrcaMachine(
        definition=controller_def,
        context={
            "experiment": "",
            "iteration": 0,
            "max_iterations": 3,
            "error_count": 0,
            "status": "idle",
        },
    )

    # Register action handlers that bridge classical and quantum worlds
    for name, handler in [
        ("init_experiment", init_experiment),
        ("verify_circuit", verify_circuit),
        ("refine_circuit", refine_circuit),
        ("compile_circuit", compile_circuit),
        ("analyze_results", analyze_results),
        ("log_failure", log_failure),
        ("log_success", log_success),
    ]:
        controller.register_action(name, handler)

    await controller.start()
    print(f"  Controller ready in state: {controller.state}")

    # ── 3. Drive the outer loop ───────────────────────────────────────────
    print(f"\n{'=' * 66}")
    print("  PHASE 3: Run experiment (outer classical loop)")
    print("=" * 66)

    # Start the experiment -- loads the broken quantum machine
    print(f"\n--- [event] START_EXPERIMENT ---")
    await controller.send("START_EXPERIMENT", {"spec": "Bell state entangler"})

    # Design complete -- trigger first verification
    print(f"\n--- [event] DESIGN_COMPLETE ---")
    await controller.send("DESIGN_COMPLETE")

    # ── 4. Inner refinement loop ──────────────────────────────────────────
    print(f"\n{'=' * 66}")
    print("  PHASE 4: Inner loop (quantum verify -> refine -> re-verify)")
    print("=" * 66)

    for _ in range(5):  # safety limit
        if workspace.is_valid:
            # Verification passed -- move to compilation
            print(f"\n--- [event] VERIFICATION_PASSED ---")
            await controller.send("VERIFICATION_PASSED")
            break
        else:
            # Verification failed -- attempt refinement
            print(f"\n--- [event] VERIFICATION_FAILED ---")
            result = await controller.send("VERIFICATION_FAILED")

            if controller.state.leaf() == "failed":
                break

            # Refinement done -- re-verify
            print(f"\n--- [event] REFINEMENT_COMPLETE ---")
            await controller.send("REFINEMENT_COMPLETE")

    # ── 5. Compile and analyze ────────────────────────────────────────────
    if controller.state.leaf() == "compiling":
        print(f"\n{'=' * 66}")
        print("  PHASE 5: Compile & analyze verified quantum circuit")
        print("=" * 66)

        print(f"\n--- [event] COMPILE_COMPLETE ---")
        await controller.send("COMPILE_COMPLETE")

        print(f"\n--- [event] ANALYSIS_COMPLETE ---")
        await controller.send("ANALYSIS_COMPLETE")

    # ── Result ────────────────────────────────────────────────────────────
    await controller.stop()

    ctx = controller.context
    print(f"\n{'=' * 66}")
    print("  RESULT")
    print("=" * 66)
    print(f"  Final state:           {controller.state}")
    print(f"  Experiment:            {ctx.get('experiment')}")
    print(f"  Refinement iterations: {ctx.get('iteration', 0)}")
    print(f"  Status:                {ctx.get('status')}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
