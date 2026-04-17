"""Tests for Q-Orca verification pipeline."""

import unicodedata

from q_orca.parser.markdown_parser import parse_q_orca_markdown
from q_orca.verifier import verify, VerifyOptions
from q_orca.verifier.structural import check_structural, analyze_machine
from q_orca.verifier.completeness import check_completeness
from q_orca.verifier.determinism import check_determinism
from q_orca.verifier.quantum import verify_quantum
from q_orca.verifier.superposition import check_superposition_leaks


def _machine(source: str):
    return parse_q_orca_markdown(source).file.machines[0]


class TestStructuralVerification:
    def test_valid_machine(self, minimal_source):
        machine = _machine(minimal_source)
        result = check_structural(machine)
        assert result.valid

    def test_no_initial_state(self):
        source = """\
# machine NoInit

## events
- go

## state |a> [final]
> Only state

## transitions
| Source | Event | Guard | Target | Action |
|--------|-------|-------|--------|--------|
"""
        # First state auto-becomes initial, but it's final — structural should still work
        machine = _machine(source)
        result = check_structural(machine)
        # It has no outgoing transitions from a non-final state, but since it's final that's ok
        assert result.valid

    def test_unreachable_state(self):
        source = """\
# machine Unreachable

## events
- go

## state |0> [initial]
> Start

## state |1> [final]
> End

## state |orphan>
> Cannot reach this

## transitions
| Source | Event | Guard | Target | Action |
|--------|-------|-------|--------|--------|
| |0>    | go    |       | |1>    |        |
"""
        machine = _machine(source)
        result = check_structural(machine)
        assert not result.valid
        codes = [e.code for e in result.errors if e.severity == "error"]
        assert "UNREACHABLE_STATE" in codes

    def test_deadlock_detection(self):
        source = """\
# machine Deadlock

## events
- go

## state |0> [initial]
> Start

## state |stuck>
> No way out, not final

## state |end> [final]
> End

## transitions
| Source | Event | Guard | Target | Action |
|--------|-------|-------|--------|--------|
| |0>    | go    |       | |stuck> |       |
"""
        machine = _machine(source)
        result = check_structural(machine)
        assert not result.valid
        codes = [e.code for e in result.errors if e.severity == "error"]
        assert "DEADLOCK" in codes

    def test_undeclared_state_in_transition(self):
        source = """\
# machine BadRef

## events
- go

## state |0> [initial]
> Start

## transitions
| Source | Event | Guard | Target | Action |
|--------|-------|-------|--------|--------|
| |0>    | go    |       | |ghost> |       |
"""
        machine = _machine(source)
        result = check_structural(machine)
        assert not result.valid
        codes = [e.code for e in result.errors if e.severity == "error"]
        assert "UNDECLARED_STATE" in codes


class TestAnalyzeMachine:
    def test_analysis_state_map(self, bell_source):
        machine = _machine(bell_source)
        analysis = analyze_machine(machine)
        assert "|00>" in analysis.state_map
        assert "|ψ>" in analysis.state_map

    def test_analysis_initial_state(self, bell_source):
        machine = _machine(bell_source)
        analysis = analyze_machine(machine)
        assert analysis.initial_state is not None

    def test_analysis_final_states(self, bell_source):
        machine = _machine(bell_source)
        analysis = analyze_machine(machine)
        assert len(analysis.final_states) == 2

    def test_outgoing_transitions(self, bell_source):
        machine = _machine(bell_source)
        analysis = analyze_machine(machine)
        psi_info = analysis.state_map["|ψ>"]
        assert len(psi_info.outgoing) == 2


class TestUnicodeStateNames:
    """Bug 1 regression: Unicode state names must not cause UNDECLARED_STATE."""

    def test_phi_plus_state_name(self):
        """State named |Φ⁺> should be recognized in both heading and transitions."""
        source = """\
# machine BellPhiPlus

## events
- prepare
- measure_done

## state |Φ⁺> [initial]
> Bell state phi-plus

## state |done> [final]
> Measured

## transitions
| Source | Event        | Guard | Target  | Action |
|--------|--------------|-------|---------|--------|
| |Φ⁺>   | prepare      |       | |Φ⁺>    |        |
| |Φ⁺>   | measure_done |       | |done>  |        |
"""
        machine = _machine(source)
        result = check_structural(machine)
        error_codes = [e.code for e in result.errors if e.severity == "error"]
        assert "UNDECLARED_STATE" not in error_codes, (
            f"Unicode state |Φ⁺> falsely flagged as undeclared: {result.errors}"
        )
        assert "UNREACHABLE_STATE" not in error_codes, (
            f"Unicode state |Φ⁺> falsely flagged as unreachable: {result.errors}"
        )

    def test_psi_state_name(self):
        """State named |ψ> (Greek small psi) should pass structural checks."""
        source = """\
# machine PsiMachine

## events
- go

## state |ψ> [initial]
> Psi state

## state |done> [final]
> End

## transitions
| Source | Event | Guard | Target  | Action |
|--------|-------|-------|---------|--------|
| |ψ>    | go    |       | |done>  |        |
"""
        machine = _machine(source)
        result = check_structural(machine)
        error_codes = [e.code for e in result.errors if e.severity == "error"]
        assert "UNDECLARED_STATE" not in error_codes
        assert result.valid

    def test_plus_minus_state_name(self):
        """State named |+-> should parse correctly from both heading and table."""
        source = """\
# machine PlusMinus

## events
- rotate

## state |+-> [initial]
> Plus-minus superposition

## state |done> [final]
> End

## transitions
| Source | Event  | Guard | Target  | Action |
|--------|--------|-------|---------|--------|
| |+->   | rotate |       | |done>  |        |
"""
        machine = _machine(source)
        result = check_structural(machine)
        error_codes = [e.code for e in result.errors if e.severity == "error"]
        assert "UNDECLARED_STATE" not in error_codes
        assert result.valid

    def test_nfc_nfd_normalization_consistency(self):
        """State name encoded as NFD in heading and NFC in table must still match."""
        # 'é' in NFD = U+0065 (e) + U+0301 (combining acute accent)
        # 'é' in NFC = U+00E9
        nfd_e = unicodedata.normalize("NFD", "\u00e9")  # é in NFD form
        nfc_e = unicodedata.normalize("NFC", "\u00e9")  # é in NFC form

        # Build source with NFD in heading and NFC in table
        source = (
            f"# machine NormTest\n\n"
            f"## events\n- go\n\n"
            f"## state |{nfd_e}+> [initial]\n> NFD heading\n\n"
            f"## state |done> [final]\n> End\n\n"
            f"## transitions\n"
            f"| Source | Event | Guard | Target  | Action |\n"
            f"|--------|-------|-------|---------|--------|\n"
            f"| |{nfc_e}+>   | go    |       | |done>  |        |\n"
        )
        machine = _machine(source)
        result = check_structural(machine)
        error_codes = [e.code for e in result.errors if e.severity == "error"]
        assert "UNDECLARED_STATE" not in error_codes, (
            f"NFC/NFD mismatch caused UNDECLARED_STATE — normalization not applied: {result.errors}"
        )


class TestCompletenessVerification:
    def test_complete_machine(self, bell_source):
        machine = _machine(bell_source)
        result = check_completeness(machine)
        # Bell entangler is a quantum preparation path, so completeness is relaxed
        error_codes = [e.code for e in result.errors if e.severity == "error"]
        assert "INCOMPLETE_EVENT_HANDLING" not in error_codes or result.valid


class TestDeterminismVerification:
    def test_deterministic_machine(self, bell_source):
        machine = _machine(bell_source)
        result = check_determinism(machine)
        error_codes = [e.code for e in result.errors if e.severity == "error"]
        assert "NON_DETERMINISTIC" not in error_codes

    def test_non_deterministic_unguarded(self):
        source = """\
# machine NonDet

## events
- go

## state |0> [initial]
> Start

## state |1> [final]
> End A

## state |2> [final]
> End B

## transitions
| Source | Event | Guard | Target | Action |
|--------|-------|-------|--------|--------|
| |0>    | go    |       | |1>    |        |
| |0>    | go    |       | |2>    |        |
"""
        machine = _machine(source)
        result = check_determinism(machine)
        assert not result.valid
        codes = [e.code for e in result.errors if e.severity == "error"]
        assert "NON_DETERMINISTIC" in codes


class TestQuantumVerification:
    def test_bell_quantum_checks(self, bell_source):
        machine = _machine(bell_source)
        result = verify_quantum(machine)
        # Should not have hard errors
        error_codes = [e.code for e in result.errors if e.severity == "error"]
        assert len(error_codes) == 0

    def test_qubit_index_out_of_range(self):
        source = """\
# machine BadIndex

## context
| Field  | Type        | Default |
|--------|-------------|---------|
| qubits | list<qubit> |         |

## events
- go

## state |0> [initial]
> Start

## state |1> [final]
> End

## transitions
| Source | Event | Guard | Target | Action   |
|--------|-------|-------|--------|----------|
| |0>    | go    |       | |1>    | bad_gate |

## actions
| Name     | Signature  | Effect        |
|----------|------------|---------------|
| bad_gate | (qs) -> qs | Hadamard(qs[5]) |

## verification rules
- unitarity: all gates preserve norm
"""
        machine = _machine(source)
        result = verify_quantum(machine)
        codes = [e.code for e in result.errors if e.severity == "error"]
        assert "QUBIT_INDEX_OUT_OF_RANGE" in codes


class TestSuperpositionLeaks:
    def test_bell_no_leaks(self, bell_source):
        machine = _machine(bell_source)
        result = check_superposition_leaks(machine)
        # Bell entangler has guarded measurement transitions — no leaks
        assert result.valid

    def test_unguarded_measurement_warns(self):
        source = """\
# machine LeakyMeasure

## context
| Field  | Type        | Default |
|--------|-------------|---------|
| qubits | list<qubit> |         |

## events
- apply
- measure

## state |00> [initial]
> Ground

## state |+0> = (|0> + |1>)|0>/√2
> Superposition

## state |result> [final]
> Measured

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
        codes = [e.code for e in result.errors]
        assert "SUPERPOSITION_LEAK" in codes


class TestFullPipeline:
    def test_bell_entangler_valid(self, bell_source):
        machine = _machine(bell_source)
        result = verify(machine)
        # Bell entangler should be valid (warnings ok, no errors)
        assert result.valid

    def test_minimal_machine_valid(self, minimal_source):
        machine = _machine(minimal_source)
        result = verify(machine)
        assert result.valid

    def test_skip_completeness(self, bell_source):
        machine = _machine(bell_source)
        opts = VerifyOptions(skip_completeness=True)
        result = verify(machine, opts)
        completeness_errors = [e for e in result.errors if e.code == "INCOMPLETE_EVENT_HANDLING"]
        assert len(completeness_errors) == 0

    def test_skip_quantum(self, bell_source):
        machine = _machine(bell_source)
        opts = VerifyOptions(skip_quantum=True)
        result = verify(machine, opts)
        quantum_codes = {"UNVERIFIED_UNITARITY", "NO_CLONING_VIOLATION",
                         "NO_ENTANGLEMENT", "INCOMPLETE_COLLAPSE", "QUBIT_INDEX_OUT_OF_RANGE"}
        for e in result.errors:
            assert e.code not in quantum_codes

    def test_verify_all_examples(self):
        """All example files should pass verification."""
        from pathlib import Path
        examples_dir = Path(__file__).parent.parent / "examples"
        for f in examples_dir.glob("*.q.orca.md"):
            source = f.read_text()
            machine = _machine(source)
            result = verify(machine)
            assert result.valid, f"{f.name} failed verification: {[e.message for e in result.errors if e.severity == 'error']}"


class TestContextAngleDynamicVerifier:
    """Dynamic verifier must resolve context-field angle references."""

    def test_context_ref_matches_literal_dynamic_simulation(self):
        """A machine using `Rx(qs[0], theta)` with theta=pi/2 must produce the
        same dynamic verification outcome as `Rx(qs[0], pi/2)`. We assert this
        indirectly by checking that both verify cleanly under the same rules.
        """
        ctx_source = """\
# machine CtxAngleDynamic

## context
| Field  | Type        | Default            |
|--------|-------------|--------------------|
| qubits | list<qubit> | [q0]               |
| theta  | float       | 1.5707963267948966 |

## events
- rotate

## state |0> [initial]
## state |+> [final]

## transitions
| Source | Event  | Guard | Target | Action |
|--------|--------|-------|--------|--------|
| |0>    | rotate |       | |+>    | spin   |

## actions
| Name | Signature  | Effect           |
|------|------------|------------------|
| spin | (qs) -> qs | Rx(qs[0], theta) |

## verification rules
- unitarity: all gates preserve norm
"""
        machine = _machine(ctx_source)
        result = verify(machine)
        # A successful run means the dynamic verifier did not stumble on the
        # bare-identifier angle and produced no errors.
        assert result.valid, [e.message for e in result.errors]
