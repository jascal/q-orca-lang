"""Tests for Q-Orca verification pipeline."""

import unicodedata

from q_orca.parser.markdown_parser import parse_q_orca_markdown
from q_orca.verifier import verify, VerifyOptions
from q_orca.verifier.structural import check_structural, analyze_machine
from q_orca.verifier.completeness import check_completeness, has_quantum_preparation_path
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


class TestPreparationPathDetection:
    """Exercise `has_quantum_preparation_path`'s dual detection paths.

    The detector must treat an event as a measurement event if EITHER
    its name matches `measure|collapse|readout` OR any of its
    transition actions carries a `measurement` / `mid_circuit_measure`
    effect. See change `harden-completeness-detection`.
    """

    _LINEAR_SKELETON = """\
# machine {name}

## context
| Field | Type | Default |
|-------|------|---------|
| qubits | list<qubit> | [q0, q1, q2] |
| bits | list<bit> | [b_err] |

## events
- prepare_prior
- encode_data
- compute_error
- {measure_event}

## state |init> [initial]
> Start

## state |prior_ready>
> Prior prepared

## state |joined>
> Data encoded

## state |error_extracted>
> Parity in ancilla

## state |bit_read> [final]
> Classical bit read

## transitions
| Source | Event | Guard | Target | Action |
|--------|-------|-------|--------|--------|
| |init>             | prepare_prior  |  | |prior_ready>     | apply_ansatz      |
| |prior_ready>      | encode_data    |  | |joined>          | encode_datum      |
| |joined>           | compute_error  |  | |error_extracted> | parity_to_ancilla |
| |error_extracted>  | {measure_event}|  | |bit_read>        | measure_ancilla   |

## actions
| Name | Signature | Effect |
|------|-----------|--------|
| apply_ansatz      | (qs) -> qs | H(qs[0]) |
| encode_datum      | (qs) -> qs | H(qs[1]) |
| parity_to_ancilla | (qs) -> qs | CNOT(qs[0], qs[2]); CNOT(qs[1], qs[2]) |
| measure_ancilla   | (qs) -> qs | measure(qs[2]) -> bits[0] |
"""

    def test_action_effect_detected_without_name_match(self):
        """Event `read_error` misses the name heuristic but its action
        has a `mid_circuit_measure` effect — structural detection
        should classify this as a preparation path."""
        source = self._LINEAR_SKELETON.format(
            name="ActionOnlyDetection", measure_event="read_error"
        )
        machine = _machine(source)
        assert has_quantum_preparation_path(machine) is True
        result = check_completeness(machine)
        codes = [e.code for e in result.errors if e.severity == "error"]
        assert "INCOMPLETE_EVENT_HANDLING" not in codes, (
            f"preparation path should relax completeness, got: {result.errors}"
        )

    def test_name_match_still_works(self):
        """Keep the name-based fallback: event `measure_error` (which
        also has a measurement action) stays classified — no
        regression on the historical detection signal."""
        source = self._LINEAR_SKELETON.format(
            name="NameAndActionDetection", measure_event="measure_error"
        )
        machine = _machine(source)
        assert has_quantum_preparation_path(machine) is True
        result = check_completeness(machine)
        codes = [e.code for e in result.errors if e.severity == "error"]
        assert "INCOMPLETE_EVENT_HANDLING" not in codes

    def test_actionless_collapse_still_detected(self):
        """vqe-rotation-style: event named `collapse` with no action
        attached. Only the name heuristic can catch this, so the
        fallback must remain in place."""
        source = """\
# machine ActionlessCollapse

## events
- prepare
- evolve
- collapse

## state |0> [initial]
> Start

## state |+>
> Superposition

## state |ψ>
> Post-evolve

## state |out> [final]
> Measured

## transitions
| Source | Event    | Guard | Target | Action   |
|--------|----------|-------|--------|----------|
| |0>    | prepare  |       | |+>    | apply_h  |
| |+>    | evolve   |       | |ψ>    | apply_rx |
| |ψ>    | collapse |       | |out>  |          |

## actions
| Name     | Signature | Effect     |
|----------|-----------|------------|
| apply_h  | (qs) -> qs | H(qs[0])  |
| apply_rx | (qs) -> qs | Rx(qs[0], 0.5) |
"""
        machine = _machine(source)
        assert has_quantum_preparation_path(machine) is True

    def test_no_measurement_signal_is_not_preparation_path(self):
        """Negative case: no measurement-name events and no
        measurement actions — must NOT be classified as preparation
        path, so the standard every-state-handles-every-event rule
        still applies."""
        source = """\
# machine PureUnitary

## events
- prepare
- evolve

## state |0> [initial]
> Start

## state |+>
> Superposition

## state |done> [final]
> Done

## transitions
| Source | Event   | Guard | Target  | Action |
|--------|---------|-------|---------|--------|
| |0>    | prepare |       | |+>     | apply_h |
| |+>    | evolve  |       | |done>  | apply_rx |

## actions
| Name     | Signature | Effect     |
|----------|-----------|------------|
| apply_h  | (qs) -> qs | H(qs[0])  |
| apply_rx | (qs) -> qs | Rx(qs[0], 0.5) |
"""
        machine = _machine(source)
        assert has_quantum_preparation_path(machine) is False


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

    def test_two_qubit_parameterized_gates_are_not_dropped(self):
        """RXX/RYY/RZZ/CRx/CRy/CRz(qs[i], qs[j], <angle>) must survive the dynamic
        verifier's effect-string parser. Regression for a silent drop where two-qubit
        parameterized gates returned None and vanished from the gate sequence,
        giving `valid=True` on circuits that actually simulated nothing.
        """
        from q_orca.verifier.dynamic import _build_gate_sequence

        source = """\
# machine TwoQubitParamDynamic

## context
| Field  | Type        | Default  |
|--------|-------------|----------|
| qubits | list<qubit> | [q0, q1] |
| gamma  | float       | 0.5      |

## events
- entangle

## state |00> [initial]
## state |cost> [final]

## transitions
| Source | Event    | Guard | Target | Action       |
|--------|----------|-------|--------|--------------|
| |00>   | entangle |       | |cost> | cost_unitary |

## actions
| Name         | Signature  | Effect                   |
|--------------|------------|--------------------------|
| cost_unitary | (qs) -> qs | RZZ(qs[0], qs[1], gamma) |

## verification rules
- unitarity: all gates preserve norm
"""
        machine = _machine(source)
        err, seq = _build_gate_sequence(machine)
        assert err is None
        flat = [g for step in seq for g in step]
        rzz_gates = [g for g in flat if g["name"] == "RZZ"]
        assert len(rzz_gates) == 1, (
            f"RZZ was silently dropped from the gate sequence; got {flat}"
        )
        assert rzz_gates[0]["targets"] == [0, 1]
        assert rzz_gates[0]["params"]["theta"] == 0.5

        result = verify(machine)
        assert result.valid, [e.message for e in result.errors]

    def test_controlled_rotations_preserve_control_qubit(self):
        """CRx/CRy/CRz(qs[ctrl], qs[tgt], <angle>) must parse as a controlled
        rotation with `controls=[ctrl]` — not silently demote to a bare rotation.
        Regression for a bug where the single-qubit `Rx(...)` regex was unanchored
        and matched the substring starting after the leading `C`, returning
        `name='RX', controls=[], theta=0.0` for what should have been a CRX.
        """
        from q_orca.verifier.dynamic import _parse_single_gate_to_dict

        ctx = {"beta": 0.5, "gamma": 0.25}
        cases = [
            ("CRx(qs[0], qs[1], beta)",  "CRX", 0, 1, 0.5),
            ("CRy(qs[0], qs[1], beta)",  "CRY", 0, 1, 0.5),
            ("CRz(qs[1], qs[2], gamma)", "CRZ", 1, 2, 0.25),
        ]
        for effect_str, expected_name, ctrl, tgt, theta in cases:
            gate = _parse_single_gate_to_dict(effect_str, angle_context=ctx)
            assert gate is not None, f"{effect_str} returned None"
            assert gate["name"] == expected_name, (
                f"{effect_str} demoted to {gate['name']}; controls={gate['controls']}"
            )
            assert gate["controls"] == [ctrl], f"{effect_str}: controls={gate['controls']}"
            assert gate["targets"] == [tgt], f"{effect_str}: targets={gate['targets']}"
            assert gate["params"]["theta"] == theta, f"{effect_str}: theta={gate['params']['theta']}"


def _multi_controlled_machine(effect: str, qubits: str = "[q0, q1, q2, q3]") -> str:
    return f"""\
# machine MultiCtrlVerify

## context
| Field  | Type        | Default |
|--------|-------------|---------|
| qubits | list<qubit> | {qubits} |

## events
- run

## state |s0> [initial]
> Start

## state |s1> [final]
> End

## transitions
| Source | Event | Guard | Target | Action |
|--------|-------|-------|--------|--------|
| |s0>   | run   |       | |s1>   | apply  |

## actions
| Name  | Signature  | Effect   |
|-------|------------|----------|
| apply | (qs) -> qs | {effect} |

## verification rules
- unitarity: all gates preserve norm
"""


class TestMultiControlledUnitarity:
    """check_unitarity must accept CCZ/MCX/MCZ as known unitaries and still
    enforce QUBIT_INDEX_OUT_OF_RANGE and CONTROL_TARGET_OVERLAP on them."""

    def test_ccz_unitarity_clean(self):
        machine = _machine(_multi_controlled_machine("CCZ(qs[0], qs[1], qs[2])", "[q0, q1, q2]"))
        result = verify_quantum(machine)
        assert result.valid, [e.message for e in result.errors]
        # CCZ is recognized as a unitary kind — no UNVERIFIED_UNITARITY warning
        codes = [e.code for e in result.errors]
        assert "UNVERIFIED_UNITARITY" not in codes

    def test_mcx_unitarity_clean(self):
        machine = _machine(_multi_controlled_machine("MCX(qs[0], qs[1], qs[2], qs[3])"))
        result = verify_quantum(machine)
        assert result.valid, [e.message for e in result.errors]
        codes = [e.code for e in result.errors]
        assert "UNVERIFIED_UNITARITY" not in codes

    def test_mcz_unitarity_clean(self):
        machine = _machine(_multi_controlled_machine("MCZ(qs[0], qs[1], qs[2], qs[3])"))
        result = verify_quantum(machine)
        assert result.valid, [e.message for e in result.errors]
        codes = [e.code for e in result.errors]
        assert "UNVERIFIED_UNITARITY" not in codes

    def test_mcx_control_target_overlap_detected(self):
        """An MCX whose last control repeats the target qubit (e.g.
        `MCX(qs[0], qs[1], qs[2], qs[2])`) must raise CONTROL_TARGET_OVERLAP —
        a 3-control Toffoli can't share a wire between a control and its target."""
        machine = _machine(_multi_controlled_machine("MCX(qs[0], qs[1], qs[2], qs[2])"))
        result = verify_quantum(machine)
        codes = [e.code for e in result.errors if e.severity == "error"]
        assert "CONTROL_TARGET_OVERLAP" in codes

    def test_ccz_control_target_overlap_detected(self):
        machine = _machine(_multi_controlled_machine("CCZ(qs[0], qs[1], qs[1])", "[q0, q1, q2]"))
        result = verify_quantum(machine)
        codes = [e.code for e in result.errors if e.severity == "error"]
        assert "CONTROL_TARGET_OVERLAP" in codes

    def test_cswap_unitarity_clean(self):
        machine = _machine(_multi_controlled_machine("CSWAP(qs[0], qs[1], qs[2])", "[q0, q1, q2]"))
        result = verify_quantum(machine)
        assert result.valid, [e.message for e in result.errors]
        codes = [e.code for e in result.errors]
        assert "UNVERIFIED_UNITARITY" not in codes

    def test_cswap_control_target_overlap_detected(self):
        """CSWAP(ctrl, t1, t2) where ctrl == t1 must flag CONTROL_TARGET_OVERLAP —
        the control qubit cannot simultaneously participate in the swap."""
        machine = _machine(_multi_controlled_machine("CSWAP(qs[0], qs[0], qs[1])", "[q0, q1, q2]"))
        result = verify_quantum(machine)
        codes = [e.code for e in result.errors if e.severity == "error"]
        assert "CONTROL_TARGET_OVERLAP" in codes
