"""Tests for bug fixes from Hermes QA bug reports."""

import pytest

from q_orca.parser.markdown_parser import parse_q_orca_markdown
from q_orca.compiler.qiskit import compile_to_qiskit, QSimulationOptions, _gate_to_qiskit, _infer_qubit_count
from q_orca.ast import QuantumGate, QMachineDef, QStateDef, QActionSignature, QEffectDef, EventDef, QTransition
from q_orca.verifier.structural import analyze_machine
from q_orca.verifier.superposition import check_superposition_leaks


def _machine(source: str):
    return parse_q_orca_markdown(source).file.machines[0]


# ============================================================
# Bug 1: NameError in shots mode — sv undefined when analytic=False
# ============================================================

class TestShotsModeSvDefined:
    """The generated Qiskit script must not reference 'sv' when it was never defined."""

    def test_shots_mode_defines_sv_for_qutip(self, bell_source):
        """In shots mode with QuTiP enabled, sv must be defined before Schmidt analysis."""
        machine = _machine(bell_source)
        opts = QSimulationOptions(analytic=False, shots=1024, skip_qutip=False)
        output = compile_to_qiskit(machine, opts)
        # The script should define sv before the Schmidt block
        assert "if 'sv' not in dir():" in output
        assert "sv = Statevector(qc)" in output

    def test_shots_mode_skip_qutip_no_sv(self, bell_source):
        """In shots mode with skip_qutip=True, no sv reference should appear."""
        machine = _machine(bell_source)
        opts = QSimulationOptions(analytic=False, shots=1024, skip_qutip=True)
        output = compile_to_qiskit(machine, opts)
        # Should not have any QuTiP block at all
        assert "Schmidt" not in output or "schmidt" not in output.lower()

    def test_analytic_mode_still_works(self, bell_source):
        """Analytic mode should still define sv directly (no dir() check needed)."""
        machine = _machine(bell_source)
        opts = QSimulationOptions(analytic=True, skip_qutip=False)
        output = compile_to_qiskit(machine, opts)
        assert "sv = Statevector(qc)" in output


# ============================================================
# Bug 2: SWAP gate silent fallback to qubit 1
# ============================================================

class TestSwapGateValidation:
    """SWAP and two-qubit gates must raise errors on insufficient targets/controls."""

    def test_swap_with_two_targets(self):
        gate = QuantumGate(kind="SWAP", targets=[0, 2])
        result = _gate_to_qiskit(gate)
        assert result == "qc.swap(0, 2)"

    def test_swap_with_one_target_raises(self):
        gate = QuantumGate(kind="SWAP", targets=[0])
        with pytest.raises(ValueError, match="SWAP gate requires 2 target qubits"):
            _gate_to_qiskit(gate)

    def test_rxx_with_one_target_raises(self):
        gate = QuantumGate(kind="RXX", targets=[0], parameter=1.57)
        with pytest.raises(ValueError, match="RXX gate requires 2 target qubits"):
            _gate_to_qiskit(gate)

    def test_ryy_with_one_target_raises(self):
        gate = QuantumGate(kind="RYY", targets=[0], parameter=1.57)
        with pytest.raises(ValueError, match="RYY gate requires 2 target qubits"):
            _gate_to_qiskit(gate)

    def test_rzz_with_one_target_raises(self):
        gate = QuantumGate(kind="RZZ", targets=[0], parameter=1.57)
        with pytest.raises(ValueError, match="RZZ gate requires 2 target qubits"):
            _gate_to_qiskit(gate)

    def test_ccnot_with_insufficient_controls_raises(self):
        gate = QuantumGate(kind="CCNOT", targets=[2], controls=[0])
        with pytest.raises(ValueError, match="CCNOT gate requires 2 control qubits"):
            _gate_to_qiskit(gate)

    def test_ccnot_with_no_controls_raises(self):
        gate = QuantumGate(kind="CCNOT", targets=[2])
        with pytest.raises(ValueError, match="CCNOT gate requires 2 control qubits"):
            _gate_to_qiskit(gate)

    def test_ccnot_with_two_controls(self):
        gate = QuantumGate(kind="CCNOT", targets=[2], controls=[0, 1])
        result = _gate_to_qiskit(gate)
        assert result == "qc.ccx(0, 1, 2)"


# ============================================================
# Bug 3: Orphan effect detection — wrong field comparison
# ============================================================

class TestOrphanEffectDetection:
    """Orphan effect detection must compare effect names, not effect_type tags."""

    def test_used_effect_not_flagged_as_orphan(self):
        """An effect referenced in an action's effect string should not be orphaned."""
        machine = QMachineDef(
            name="TestMachine",
            states=[
                QStateDef(name="|0>", display_name="ket_0", is_initial=True),
                QStateDef(name="|1>", display_name="ket_1", is_final=True),
            ],
            events=[EventDef(name="go")],
            transitions=[QTransition(source="|0>", event="go", target="|1>", action="do_it")],
            actions=[
                QActionSignature(
                    name="do_it",
                    effect="ApplyH",
                    has_effect=True,
                    effect_type="quantum",  # This is a tag, not an effect name
                ),
            ],
            effects=[
                QEffectDef(name="ApplyH", input="qs", output="qs"),
            ],
        )
        analysis = analyze_machine(machine)
        assert "ApplyH" not in analysis.orphan_effects

    def test_truly_orphan_effect_is_flagged(self):
        """An effect not referenced anywhere should be flagged as orphaned."""
        machine = QMachineDef(
            name="TestMachine",
            states=[
                QStateDef(name="|0>", display_name="ket_0", is_initial=True),
                QStateDef(name="|1>", display_name="ket_1", is_final=True),
            ],
            events=[EventDef(name="go")],
            transitions=[QTransition(source="|0>", event="go", target="|1>", action="do_it")],
            actions=[
                QActionSignature(
                    name="do_it",
                    effect="H(qs[0])",
                    has_effect=True,
                    effect_type="quantum",
                ),
            ],
            effects=[
                QEffectDef(name="UnusedEffect", input="qs", output="qs"),
            ],
        )
        analysis = analyze_machine(machine)
        assert "UnusedEffect" in analysis.orphan_effects

    def test_old_bug_effect_type_vs_name_mismatch(self):
        """Regression: effect_type='quantum' must NOT match effect.name='quantum'."""
        machine = QMachineDef(
            name="TestMachine",
            states=[
                QStateDef(name="|0>", display_name="ket_0", is_initial=True),
                QStateDef(name="|1>", display_name="ket_1", is_final=True),
            ],
            events=[EventDef(name="go")],
            transitions=[QTransition(source="|0>", event="go", target="|1>", action="do_it")],
            actions=[
                QActionSignature(
                    name="do_it",
                    effect="H(qs[0])",
                    has_effect=True,
                    effect_type="quantum",
                ),
            ],
            effects=[
                # Effect named "quantum" — old bug would match this against effect_type="quantum"
                QEffectDef(name="quantum", input="qs", output="qs"),
            ],
        )
        analysis = analyze_machine(machine)
        # "quantum" is NOT referenced in the effect string "H(qs[0])" — but wait,
        # substring "quantum" is not in "H(qs[0])". So it should be orphaned.
        assert "quantum" in analysis.orphan_effects


# ============================================================
# Bug 4: Superposition leaks always valid=True
# ============================================================

class TestSuperpositionLeakSeverity:
    """Superposition leak errors must use severity='error' for non-trivial cases."""

    def test_unguarded_measure_to_nonfinal_is_error(self):
        """Unguarded measurement from superposition to non-final state should be error."""
        source = """\
# machine LeakyNonFinal

## context
| Field  | Type        | Default |
|--------|-------------|---------|
| qubits | list<qubit> |         |

## events
- apply
- measure

## state |00> [initial]
> Ground

## state |+0> = (|0> + |1>)|0>/\u221a2
> Superposition

## state |mid>
> Not final, not guarded

## state |done> [final]
> Final

## transitions
| Source | Event   | Guard | Target | Action  |
|--------|---------|-------|--------|---------|
| |00>   | apply   |       | |+0>   | do_H    |
| |+0>   | measure |       | |mid>  |         |
| |mid>  | apply   |       | |done> |         |

## actions
| Name | Signature  | Effect        |
|------|------------|---------------|
| do_H | (qs) -> qs | Hadamard(qs[0]) |
"""
        machine = _machine(source)
        result = check_superposition_leaks(machine)
        error_severity_codes = [e for e in result.errors if e.severity == "error"]
        assert len(error_severity_codes) > 0, "Unguarded measurement to non-final state should produce error-level issues"
        assert not result.valid

    def test_guarded_measure_to_final_is_warning(self, bell_source):
        """Bell entangler with guarded measurement to final is ok (valid=True)."""
        machine = _machine(bell_source)
        result = check_superposition_leaks(machine)
        assert result.valid

    def test_unguarded_measure_to_final_is_warning(self):
        """Unguarded measurement to final state should be warning, not error."""
        source = """\
# machine CollapseFinal

## context
| Field  | Type        | Default |
|--------|-------------|---------|
| qubits | list<qubit> |         |

## events
- apply
- measure

## state |00> [initial]
> Ground

## state |+0> = (|0> + |1>)|0>/\u221a2
> Superposition

## state |result> [final]
> Measured and done

## transitions
| Source | Event   | Guard | Target   | Action  |
|--------|---------|-------|----------|---------|
| |00>   | apply   |       | |+0>     | do_H    |
| |+0>   | measure |       | |result> |         |

## actions
| Name | Signature  | Effect        |
|------|------------|---------------|
| do_H | (qs) -> qs | Hadamard(qs[0]) |
"""
        machine = _machine(source)
        result = check_superposition_leaks(machine)
        # Should only produce warnings (intentional collapse to final)
        for e in result.errors:
            if e.code == "SUPERPOSITION_LEAK":
                assert e.severity == "warning", f"Collapse to final state should be warning, got: {e.severity}"
        assert result.valid


# ============================================================
# Bug 5: Qubit count fallback to 1
# ============================================================

class TestQubitCountInference:
    """Qubit count inference must scan gate targets and raise on total failure."""

    def test_infers_from_gate_targets_in_effect(self):
        """Machine with qs[2] in an effect string should infer at least 3 qubits."""
        source = """\
# machine GateTargetInference

## events
- go

## state |psi> [initial]
> Start

## state |done> [final]
> End

## transitions
| Source | Event | Guard | Target | Action  |
|--------|-------|-------|--------|---------|
| |psi>  | go    |       | |done> | do_gate |

## actions
| Name    | Signature  | Effect          |
|---------|------------|-----------------|
| do_gate | (qs) -> qs | Hadamard(qs[2]) |
"""
        machine = _machine(source)
        count = _infer_qubit_count(machine)
        assert count >= 3

    def test_infers_from_gate_object(self):
        """Machine with a gate targeting qubit 4 should infer at least 5 qubits."""
        machine = QMachineDef(
            name="TestMachine",
            states=[
                QStateDef(name="|0>", display_name="ket_0", is_initial=True),
                QStateDef(name="|1>", display_name="ket_1", is_final=True),
            ],
            events=[EventDef(name="go")],
            transitions=[QTransition(source="|0>", event="go", target="|1>", action="do_it")],
            actions=[
                QActionSignature(
                    name="do_it",
                    gate=QuantumGate(kind="H", targets=[4]),
                ),
            ],
        )
        count = _infer_qubit_count(machine)
        assert count >= 5

    def test_defaults_to_one_when_no_qubit_info(self):
        """Machine with no qubit information should default to 1 qubit."""
        machine = QMachineDef(
            name="NoQubits",
            states=[
                QStateDef(name="|start>", display_name="start", is_initial=True),
                QStateDef(name="|end>", display_name="end", is_final=True),
            ],
            events=[EventDef(name="go")],
            transitions=[QTransition(source="|start>", event="go", target="|end>")],
            actions=[],
        )
        assert _infer_qubit_count(machine) == 1

    def test_bitstring_states_still_work(self):
        """Machine with |0000> states should still infer 4 qubits."""
        source = """\
# machine BitstringMachine

## events
- init

## state |0000> [initial]
> Initial

## state |1111> [final]
> Final

## transitions
| Source | Event | Guard | Target |
|--------|-------|-------|--------|
| |0000> | init |       | |1111> |
"""
        machine = _machine(source)
        count = _infer_qubit_count(machine)
        assert count == 4
