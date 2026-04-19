"""Regression tests for common quantum machine failure modes.

These tests verify that the verifier correctly catches:
- Cloning attempt (copying a quantum state)
- Non-deterministic guards (unguarded transitions)
- Deadlock (non-final state with no outgoing)
- Unreachable state (orphan)
- Superposition leak (unguarded measurement from superposition)
- Guard overlap (non-mutually-exclusive guards)
- Incomplete event handling (missing (state, event) transitions)
- Quantum-specific violations (bad qubit index)
"""

import math
from pathlib import Path

import pytest

from q_orca.parser.markdown_parser import parse_q_orca_markdown
from q_orca.verifier import verify
from q_orca.verifier.structural import check_structural
from q_orca.verifier.completeness import check_completeness
from q_orca.verifier.determinism import check_determinism
from q_orca.verifier.quantum import verify_quantum
from q_orca.verifier.superposition import check_superposition_leaks


def _machine(source: str):
    return parse_q_orca_markdown(source).file.machines[0]


# ── Cloning attempt ──────────────────────────────────────────────────────────

class TestCloningAttempt:
    """Machine attempting to copy a quantum state must be rejected."""

    def test_copy_gate_rejected(self):
        """A Copy gate action should be flagged as no-cloning violation."""
        source = """\
# machine CloningAttempt

## context
| Field  | Type        | Default |
|--------|-------------|---------|
| qubits | list<qubit> | [q0, q1] |

## events
- copy

## state |psi0> [initial]
> Initial state to be copied

## state |psi1> [final]
> Copy target

## transitions
| Source | Event | Guard | Target | Action  |
|--------|-------|-------|--------|---------|
| |psi0> | copy  |       | |psi1>  | Copy(qs[0], qs[1]) |

## actions
| Name | Signature           | Effect             |
|------|---------------------|--------------------|
| Copy | (qs, qs) -> (qs, qs) | Copy(qs[0], qs[1]) |

## verification rules
- no-cloning: no copy operations allowed
"""
        machine = _machine(source)
        result = verify_quantum(machine)
        codes = [e.code for e in result.errors if e.severity == "error"]
        assert "NO_CLONING" in "".join(codes), \
            f"Expected NO_CLONING_VIOLATION error, got: {codes}"


# ── Non-deterministic guards ─────────────────────────────────────────────────

class TestNonDeterministicGuards:
    """Multiple unguarded transitions for the same (state, event) pair."""

    def test_two_unguarded_transitions_rejected(self):
        """Two transitions from same state without guards → NON_DETERMINISTIC."""
        source = """\
# machine NonDetGuards

## events
- go

## state |start> [initial]
> Start

## state |a> [final]
> End A

## state |b> [final]
> End B

## transitions
| Source | Event | Guard | Target | Action |
|--------|-------|-------|--------|--------|
| |start> | go    |       | |a>    |        |
| |start> | go    |       | |b>    |        |
"""
        machine = _machine(source)
        result = check_determinism(machine)
        error_codes = [e.code for e in result.errors if e.severity == "error"]
        assert "NON_DETERMINISTIC" in error_codes, \
            f"Expected NON_DETERMINISTIC error, got: {error_codes}"

    def test_overlapping_guards_warns(self):
        """Guards that may overlap should produce a warning."""
        source = """\
# machine OverlapGuards

## context
| Field | Type  | Default |
|-------|-------|---------|
| x     | int   | 5      |

## events
- go

## state |start> [initial]
> Start

## state |a> [final]
> End A

## state |b> [final]
> End B

## transitions
| Source | Event | Guard  | Target | Action |
|--------|-------|--------|--------|--------|
| |start> | go    | g1     | |a>    |        |
| |start> | go    | g2     | |b>    |        |

## guards
| Name | Expression |
|------|------------|
| g1 | x > 3     |
| g2 | x > 5     |
"""
        machine = _machine(source)
        result = check_determinism(machine)
        overlap_codes = [e.code for e in result.errors if e.code == "GUARD_OVERLAP"]
        assert len(overlap_codes) > 0, "Expected GUARD_OVERLAP warning"

    def test_negated_guard_pair_no_warning(self):
        """Negated and non-negated guards for the same condition are mutually exclusive."""
        source = """\
# machine NegatedPair

## context
| Field | Type  | Default |
|-------|-------|---------|
| b     | bool  | true   |

## events
- go

## state |start> [initial]
> Start

## state |a> [final]
> End A

## state |b> [final]
> End B

## transitions
| Source | Event | Guard | Target | Action |
|--------|-------|-------|--------|--------|
| |start> | go    | b     | |a>    |        |
| |start> | go    | !b    | |b>    |        |

## guards
| Name | Expression |
|------|------------|
| b   | b == true  |
"""
        machine = _machine(source)
        result = check_determinism(machine)
        overlap_codes = [e.code for e in result.errors if e.code == "GUARD_OVERLAP"]
        assert len(overlap_codes) == 0, "Negated guard pair should not warn"


# ── Deadlock ────────────────────────────────────────────────────────────────

class TestDeadlock:
    """Non-final state with no outgoing transitions is a deadlock."""

    def test_deadlock_detected(self):
        source = """\
# machine Deadlock

## events
- go

## state |start> [initial]
> Start

## state |stuck>
> Dead-end — not final, no outgoing

## transitions
| Source | Event | Guard | Target | Action |
|--------|-------|-------|--------|--------|
| |start> | go   |       | |stuck> |        |
"""
        machine = _machine(source)
        result = check_structural(machine)
        assert not result.valid
        codes = [e.code for e in result.errors if e.severity == "error"]
        assert "DEADLOCK" in codes


# ── Unreachable / orphan state ────────────────────────────────────────────

class TestUnreachableState:
    """State that cannot be reached from the initial state."""

    def test_unreachable_state_detected(self):
        source = """\
# machine Unreachable

## events
- go

## state |start> [initial]
> Start

## state |orphan> [final]
> Cannot be reached

## transitions
| Source | Event | Guard | Target | Action |
|--------|-------|-------|--------|--------|
| |start> | go   |       | |start> |        |
"""
        machine = _machine(source)
        result = check_structural(machine)
        assert not result.valid
        codes = [e.code for e in result.errors if e.severity == "error"]
        assert "UNREACHABLE_STATE" in codes or "ORPHAN_STATE" in codes

    def test_orphan_event_warns(self):
        """Event declared but never used in any transition."""
        source = """\
# machine OrphanEvent

## events
- used
- unused

## state |start> [initial]
> Start

## state |end> [final]
> End

## transitions
| Source | Event | Guard | Target | Action |
|--------|-------|-------|--------|--------|
| |start> | used |       | |end>  |        |
"""
        machine = _machine(source)
        result = check_structural(machine)
        orphan_codes = [e.code for e in result.errors if e.code == "ORPHAN_EVENT"]
        assert len(orphan_codes) > 0, "Expected ORPHAN_EVENT warning"


# ── Superposition leak ────────────────────────────────────────────────────

class TestSuperpositionLeak:
    """Unguarded measurement from a superposition state leaks coherence."""

    def test_unguarded_superposition_measurement_warns(self):
        source = """\
# machine LeakSuperposition

## context
| Field  | Type        | Default |
|--------|-------------|---------|
| qubits | list<qubit> | [q0]   |

## events
- apply
- measure

## state |zero> [initial]
> Ground

## state |super> = (|0>+|1>)/sqrt2
> Superposition

## state |result> [final]
> Measured

## transitions
| Source | Event   | Guard | Target   | Action |
|--------|---------|-------|----------|--------|
| |zero>  | apply  |       | |super>  | do_H  |
| |super> | measure |       | |result> |        |

## actions
| Name  | Signature    | Effect        |
|-------|---------------|---------------|
| do_H | (qs) -> qs  | Hadamard(qs[0]) |

## verification rules
- unitarity: all gates preserve norm
"""
        machine = _machine(source)
        result = check_superposition_leaks(machine)
        codes = [e.code for e in result.errors if e.code == "SUPERPOSITION_LEAK"]
        assert len(codes) > 0, "Expected SUPERPOSITION_LEAK warning"

    def test_probability_guarded_measurement_no_leak(self):
        """Bell measurement with probability guards should NOT warn."""
        source = """\
# machine BellGuarded

## context
| Field  | Type        | Default |
|--------|-------------|---------|
| qubits | list<qubit> | [q0, q1] |

## events
- entangle
- measure

## state |00> [initial]
> Start

## state |psi> = (|00>+|11>)/sqrt2
> Bell state

## state |r00> [final]
> Collapsed 00

## state |r11> [final]
> Collapsed 11

## transitions
| Source | Event   | Guard                    | Target | Action |
|--------|---------|--------------------------|--------|--------|
| |00>   | entangle|                          | |psi>  | do_CNOT |
| |psi>  | measure | prob_collapse('00')=0.5  | |r00>  |        |
| |psi>  | measure | prob_collapse('11')=0.5  | |r11>  |        |

## guards
| Name                    | Expression                      |
|-------------------------|----------------------------------|
| prob_collapse('00')     | prob_collapse('00')=0.5         |
| prob_collapse('11')     | prob_collapse('11')=0.5         |

## actions
| Name     | Signature    | Effect             |
|----------|--------------|--------------------|
| do_CNOT | (qs) -> qs | CNOT(qs[0], qs[1]) |

## verification rules
- unitarity: all gates preserve norm
- entanglement: Bell state has Schmidt rank > 1
"""
        machine = _machine(source)
        result = check_superposition_leaks(machine)
        leak_codes = [e.code for e in result.errors if e.code == "SUPERPOSITION_LEAK"]
        assert len(leak_codes) == 0, \
            f"Unexpected SUPERPOSITION_LEAK: {[e.message for e in result.errors if e.code == 'SUPERPOSITION_LEAK']}"


# ── Incomplete event handling ──────────────────────────────────────────────

class TestIncompleteEventHandling:
    """Every state must handle every declared event (or be final)."""

    def test_unhandled_event_rejected(self):
        source = """\
# machine UnhandledEvent

## events
- alpha
- beta

## state |start> [initial]
> Start

## state |end> [final]
> End

## transitions
| Source | Event | Guard | Target | Action |
|--------|-------|-------|--------|--------|
| |start> | alpha |       | |end>  |        |
"""
        machine = _machine(source)
        result = check_completeness(machine)
        error_codes = [e.code for e in result.errors if e.severity == "error"]
        # Use substring match since code is INCOMPLETE_EVENT_HANDLING
        assert any("INCOMPLETE" in c for c in error_codes), \
            f"Expected INCOMPLETE error, got: {error_codes}"

    def test_valid_machine_has_no_completeness_errors(self, minimal_source):
        """A minimal valid machine passes completeness."""
        machine = _machine(minimal_source)
        result = check_completeness(machine)
        error_codes = [e.code for e in result.errors if e.severity == "error"]
        assert len(error_codes) == 0, f"Unexpected errors: {error_codes}"


# ── Quantum-specific checks ────────────────────────────────────────────────

class TestQuantumChecks:
    """Quantum-specific verification rules."""

    def test_qubit_index_out_of_range_rejected(self):
        source = """\
# machine BadQubitIndex

## context
| Field  | Type        | Default |
|--------|-------------|---------|
| qubits | list<qubit> | [q0]   |

## events
- go

## state |zero> [initial]
> Start

## state |one> [final]
> End

## transitions
| Source | Event | Guard | Target | Action |
|--------|-------|-------|--------|--------|
| |zero>  | go    |       | |one>  | bad_gate |

## actions
| Name      | Signature    | Effect            |
|-----------|--------------|-------------------|
| bad_gate  | (qs) -> qs | Hadamard(qs[99])  |

## verification rules
- unitarity: all gates preserve norm
"""
        machine = _machine(source)
        result = verify_quantum(machine)
        codes = [e.code for e in result.errors if e.severity == "error"]
        assert "QUBIT_INDEX_OUT_OF_RANGE" in codes, \
            f"Expected QUBIT_INDEX_OUT_OF_RANGE, got: {codes}"

    def test_entangled_state_passes_entanglement_check(self):
        """A properly entangled Bell state should pass entanglement check."""
        source = """\
# machine EntangledBell

## context
| Field  | Type        | Default |
|--------|-------------|---------|
| qubits | list<qubit> | [q0, q1] |

## events
- prepare
- entangle

## state |start> [initial]
> Start

## state |psi> = (|00>+|11>)/sqrt2
> Bell state

## transitions
| Source | Event    | Guard | Target | Action              |
|--------|----------|-------|--------|---------------------|
| |start> | prepare  |       | |psi>  | apply_H_and_CNOT   |

## actions
| Name              | Signature    | Effect               |
|-------------------|--------------|----------------------|
| apply_H_and_CNOT | (qs) -> qs | Hadamard(qs[0]); CNOT(qs[0], qs[1]) |

## verification rules
- unitarity: all gates preserve norm
- entanglement: Bell state has Schmidt rank > 1
"""
        machine = _machine(source)
        result = verify_quantum(machine)
        error_codes = [e.code for e in result.errors if e.severity == "error"]
        assert len(error_codes) == 0, f"Unexpected errors: {error_codes}"

    def test_custom_gate_without_unitarity_rule_still_passes_structural(self):
        """A custom gate with no unitarity rule should not cause structural failure."""
        source = """\
# machine CustomNoUnitarity

## context
| Field  | Type        | Default |
|--------|-------------|---------|
| qubits | list<qubit> | [q0]   |

## events
- go

## state |zero> [initial]
> Start

## state |one> [final]
> End

## transitions
| Source | Event | Guard | Target | Action    |
|--------|-------|-------|--------|-----------|
| |zero>  | go    |       | |one>  | my_custom |

## actions
| Name      | Signature    | Effect      |
|-----------|--------------|-------------|
| my_custom | (qs) -> qs | MyGate(qs[0]) |

## verification rules
# NOTE: no unitarity rule — verifier should warn but not reject
"""
        machine = _machine(source)
        result = check_structural(machine)
        assert result.valid, f"Structural should be valid, got: {[e.message for e in result.errors]}"


# ── Full pipeline ──────────────────────────────────────────────────────────

class TestFullPipelineRegression:
    """Full pipeline regression tests on actual example machines."""

    def test_all_examples_pass_without_errors(self):
        """All provided examples must pass verification with zero errors."""
        from pathlib import Path
        examples_dir = Path(__file__).parent.parent / "examples"
        for f in sorted(examples_dir.glob("*.q.orca.md")):
            source = f.read_text()
            machine = _machine(source)
            result = verify(machine)
            assert result.valid, (
                f"{f.name} failed verification:\n"
                + "\n".join(f"  [{e.severity}] {e.code}: {e.message}" for e in result.errors)
            )

    def test_bell_entangler_full_pipeline(self):
        """BellEntangler must pass all 5 stages cleanly."""
        source = (Path(__file__).parent.parent / "examples" / "bell-entangler.q.orca.md").read_text()
        machine = _machine(source)
        result = verify(machine)
        assert result.valid
        error_codes = [e.code for e in result.errors if e.severity == "error"]
        assert len(error_codes) == 0, f"BellEntangler had errors: {error_codes}"

    def test_quantum_teleportation_full_pipeline(self):
        """QuantumTeleportation must pass all 5 stages cleanly."""
        source = (Path(__file__).parent.parent / "examples" / "quantum-teleportation.q.orca.md").read_text()
        machine = _machine(source)
        result = verify(machine)
        assert result.valid
        error_codes = [e.code for e in result.errors if e.severity == "error"]
        assert len(error_codes) == 0, f"QuantumTeleportation had errors: {error_codes}"

    def test_vqe_heisenberg_full_pipeline(self):
        """VQEH must pass all 5 stages cleanly."""
        source = (Path(__file__).parent.parent / "examples" / "vqe-heisenberg.q.orca.md").read_text()
        machine = _machine(source)
        result = verify(machine)
        assert result.valid
        error_codes = [e.code for e in result.errors if e.severity == "error"]
        assert len(error_codes) == 0, f"VQEH had errors: {error_codes}"


_ROTATION_MACHINE_SOURCE = """\
# machine RotationRegression

## context
| Field  | Type        | Default |
|--------|-------------|---------|
| qubits | list<qubit> | [q0]    |

## events
- rotate

## state |0> [initial]
> Ground state

## state |theta> [final]
> Rotated state

## transitions
| Source | Event  | Guard | Target   | Action    |
|--------|--------|-------|----------|-----------|
| |0>    | rotate |       | |theta>  | rotate_q0 |

## actions
| Name      | Signature  | Effect             |
|-----------|------------|--------------------|
| rotate_q0 | (qs) -> qs | Rx(qs[0], pi/4)    |

## verification rules
- unitarity: all gates preserve norm
"""


class TestRotationGateRoundTrip:
    """Regression: rotation machine parses, compiles to QASM and Qiskit correctly."""

    def test_parse_populates_gate_parameter(self):
        result = parse_q_orca_markdown(_ROTATION_MACHINE_SOURCE)
        assert result.errors == [], f"Unexpected parse errors: {result.errors}"
        machine = result.file.machines[0]
        action = next(a for a in machine.actions if a.name == "rotate_q0")
        assert action.gate is not None
        assert action.gate.kind == "Rx"
        assert action.gate.parameter == pytest.approx(math.pi / 4)

    def test_compile_to_qasm_emits_rx(self):
        from q_orca.compiler.qasm import compile_to_qasm
        machine = _machine(_ROTATION_MACHINE_SOURCE)
        qasm = compile_to_qasm(machine)
        assert "rx(" in qasm
        # The emitted float should be approximately pi/4
        import re
        m = re.search(r"rx\(([\d.]+)\)", qasm)
        assert m, f"No rx() gate in QASM output:\n{qasm}"
        assert float(m.group(1)) == pytest.approx(math.pi / 4, rel=1e-6)

    def test_compile_to_qiskit_emits_rx(self):
        from q_orca.compiler.qiskit import compile_to_qiskit, QSimulationOptions
        machine = _machine(_ROTATION_MACHINE_SOURCE)
        qiskit_code = compile_to_qiskit(machine, QSimulationOptions())
        assert "qc.rx(" in qiskit_code
        import re
        m = re.search(r"qc\.rx\(([\d.]+),\s*\d+\)", qiskit_code)
        assert m, f"No qc.rx() in Qiskit output:\n{qiskit_code}"
        assert float(m.group(1)) == pytest.approx(math.pi / 4, rel=1e-6)


# ── Grover demo end-to-end (MCZ on 3 controls) ───────────────────────────────

class TestGroverDemoRegression:
    """End-to-end regression for `examples/larql-gate-knn-grover.q.orca.md`.

    The demo runs 3 Grover iterations on a 4-qubit index register with the
    marked state at |1010> (index 10). For N=16, M=1 the theoretical success
    probability after 3 iterations is ~96.2%; at 1024 shots the one-sigma
    band is ~0.6% so an unseeded run occasionally dips below a 95% threshold.
    We pin `seed_simulator` to remove shot-noise flake — the assertion then
    exercises compiler correctness, not the sampler's RNG draws.
    """

    REPO_ROOT = Path(__file__).resolve().parents[1]
    MACHINE_PATH = REPO_ROOT / "examples" / "larql-gate-knn-grover.q.orca.md"

    def test_grover_compiles_and_recovers_marked_state(self):
        pytest.importorskip("qiskit", reason="qiskit not installed")

        from q_orca.compiler.qiskit import compile_to_qiskit, QSimulationOptions
        from q_orca.runtime.python import run_simulation

        source = self.MACHINE_PATH.read_text()
        machine = parse_q_orca_markdown(source).file.machines[0]

        # Parse errors would indicate the multi-controlled effect grammar
        # regressed before we ever got to the Qiskit stage.
        assert machine.name == "LarqlGateKnnGrover"

        script = compile_to_qiskit(
            machine,
            QSimulationOptions(
                analytic=False,
                shots=1024,
                run=True,
                skip_qutip=True,
                seed_simulator=42,
            ),
        )

        # The generated script must transpile against a fixed basis so
        # BasicSimulator (which does not run `mcx` natively) can execute.
        assert "transpile" in script
        assert "qc.mcx(" in script

        sim = run_simulation(script)
        assert sim.success, f"simulation failed: {sim.error}\n{sim.stderr}"

        counts = sim.counts or {}
        total = sum(counts.values()) or 1
        marked = counts.get("1010", 0)
        fraction = marked / total
        assert fraction > 0.95, (
            f"Grover demo did not concentrate probability mass on |1010>: "
            f"got {marked}/{total} = {fraction:.2%}; full counts={counts}"
        )
