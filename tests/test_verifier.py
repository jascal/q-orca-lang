"""Tests for Q-Orca verification pipeline."""

import unicodedata

import pytest

from q_orca.parser.markdown_parser import parse_q_orca_markdown
from q_orca.verifier import verify, VerifyOptions
from q_orca.verifier.structural import check_structural, analyze_machine
from q_orca.verifier.completeness import check_completeness, has_quantum_preparation_path
from q_orca.verifier.determinism import check_determinism
from q_orca.verifier.quantum import verify_quantum
from q_orca.verifier.superposition import check_superposition_leaks
from tests.fixtures.effect_strings import EFFECT_STRING_CASES


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

    def test_separable_two_term_sum_not_flagged_as_entangled(self):
        # (|00> + |10>)/√2 = |+>⊗|0> — a product state. The verifier must
        # not fire ENTANGLEMENT_WITHOUT_GATE on it just because the
        # expression syntactically looks like a Bell-style sum.
        source = """\
# machine PlusZero

## context
| Field  | Type        | Default  |
|--------|-------------|----------|
| qubits | list<qubit> | [q0, q1] |

## events
- prepare

## state |00> [initial]
> Ground state

## state |+0> = (|00> + |10>)/√2 [final]
> |+>⊗|0> — separable

## transitions
| Source | Event   | Guard | Target | Action  |
|--------|---------|-------|--------|---------|
| |00>   | prepare |       | |+0>   | apply_h |

## actions
| Name    | Signature  | Effect          |
|---------|------------|-----------------|
| apply_h | (qs) -> qs | Hadamard(qs[0]) |

## verification rules
- entanglement: Bell state has Schmidt rank > 1
"""
        result = verify_quantum(_machine(source))
        codes = [e.code for e in result.errors]
        assert "ENTANGLEMENT_WITHOUT_GATE" not in codes, codes

    def test_genuine_two_term_entanglement_still_flagged_without_gate(self):
        # (|00> + |11>)/√2 differs in two positions — genuinely entangled.
        # If the only incoming transition is a Hadamard, the verifier
        # should still warn.
        source = """\
# machine FakeBell

## context
| Field  | Type        | Default  |
|--------|-------------|----------|
| qubits | list<qubit> | [q0, q1] |

## events
- prepare

## state |00> [initial]
> Ground state

## state |ψ> = (|00> + |11>)/√2 [final]
> Claims to be a Bell state but reached via H alone

## transitions
| Source | Event   | Guard | Target | Action  |
|--------|---------|-------|--------|---------|
| |00>   | prepare |       | |ψ>    | apply_h |

## actions
| Name    | Signature  | Effect          |
|---------|------------|-----------------|
| apply_h | (qs) -> qs | Hadamard(qs[0]) |

## verification rules
- entanglement: Bell state has Schmidt rank > 1
"""
        result = verify_quantum(_machine(source))
        codes = [e.code for e in result.errors]
        assert "ENTANGLEMENT_WITHOUT_GATE" in codes, codes

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


class TestParametricActionVerification:
    """Per-call-site expansion (Section 6). Errors SHALL point at the
    transition and bound value, not the action template, and each call
    site SHALL be verified independently."""

    def test_range_error_reported_at_call_site(self):
        source = """\
# machine Poly

## context
| Field  | Type        | Default      |
|--------|-------------|--------------|
| qubits | list<qubit> | [q0, q1, q2] |

## events
- e0
- e1
- e2

## state |s0> [initial]
## state |s1>
## state |s2>
## state |s3> [final]

## transitions
| Source | Event | Guard | Target | Action |
|--------|-------|-------|--------|--------|
| |s0>   | e0    |       | |s1>   | query_concept(0) |
| |s1>   | e1    |       | |s2>   | query_concept(9) |
| |s2>   | e2    |       | |s3>   | query_concept(1) |

## actions
| Name          | Signature          | Effect          |
|---------------|--------------------|-----------------|
| query_concept | (qs, c: int) -> qs | Hadamard(qs[c]) |

## verification rules
- unitarity: all gates preserve norm
"""
        result = verify_quantum(_machine(source))
        range_errors = [e for e in result.errors if e.code == "QUBIT_INDEX_OUT_OF_RANGE"]
        assert len(range_errors) == 1
        # The message names the transition source/target and the bound value.
        assert "query_concept(9)" in range_errors[0].message
        assert "|s1>" in range_errors[0].message and "|s2>" in range_errors[0].message

    def test_control_target_overlap_reported_at_call_site(self):
        source = """\
# machine Overlap

## context
| Field  | Type        | Default              |
|--------|-------------|----------------------|
| qubits | list<qubit> | [q0, q1, q2, q3, q4] |

## events
- go

## state |s0> [initial]
## state |s1> [final]

## transitions
| Source | Event | Guard | Target | Action |
|--------|-------|-------|--------|--------|
| |s0>   | go    |       | |s1>   | oracle(2) |

## actions
| Name   | Signature          | Effect                               |
|--------|--------------------|--------------------------------------|
| oracle | (qs, t: int) -> qs | MCX(qs[0], qs[1], qs[2], qs[t])      |

## verification rules
- unitarity: all gates preserve norm
"""
        # oracle(2) expands to MCX(qs[0], qs[1], qs[2], qs[2]) — control=2
        # overlaps the target.
        result = verify_quantum(_machine(source))
        overlap = [e for e in result.errors if e.code == "CONTROL_TARGET_OVERLAP"]
        assert len(overlap) == 1
        assert "oracle(2)" in overlap[0].message

    def test_bound_range_clean_across_call_sites(self):
        source = """\
# machine Clean

## context
| Field  | Type        | Default              |
|--------|-------------|----------------------|
| qubits | list<qubit> | [q0, q1, q2, q3, q4, q5] |

## events
- e0
- e1
- e2

## state |s0> [initial]
## state |s1>
## state |s2>
## state |s3> [final]

## transitions
| Source | Event | Guard | Target | Action |
|--------|-------|-------|--------|--------|
| |s0>   | e0    |       | |s1>   | oracle(3) |
| |s1>   | e1    |       | |s2>   | oracle(4) |
| |s2>   | e2    |       | |s3>   | oracle(5) |

## actions
| Name   | Signature          | Effect                               |
|--------|--------------------|--------------------------------------|
| oracle | (qs, t: int) -> qs | MCZ(qs[0], qs[1], qs[2], qs[t])      |

## verification rules
- unitarity: all gates preserve norm
"""
        result = verify_quantum(_machine(source))
        errors = [e for e in result.errors if e.severity == "error"]
        assert errors == []

    def test_arity_zero_call_to_parametric_action_rejected_upstream(self):
        # Pin the parser-level invariant that `check_unitarity` relies on:
        # parametric actions are skipped in its per-action loop and only
        # visited via `t.bound_arguments`. A bare-name reference to a
        # parametric action (an "arity-zero call") would silently leave the
        # gate unchecked if it slipped past the parser. The parser MUST
        # reject it, leaving `bound_arguments` unset on the offending
        # transition so the verifier never sees an unbound parametric
        # action template at a call site.
        source = """\
# machine BareNameSlip

## context
| Field  | Type        | Default      |
|--------|-------------|--------------|
| qubits | list<qubit> | [q0, q1, q2] |

## events
- go

## state |s0> [initial]
## state |s1> [final]

## transitions
| Source | Event | Guard | Target | Action |
|--------|-------|-------|--------|--------|
| |s0>   | go    |       | |s1>   | query_concept |

## actions
| Name          | Signature          | Effect          |
|---------------|--------------------|-----------------|
| query_concept | (qs, c: int) -> qs | Hadamard(qs[c]) |

## verification rules
- unitarity: all gates preserve norm
"""
        parsed = parse_q_orca_markdown(source)
        assert any(
            "is parametric and requires arguments" in e for e in parsed.errors
        ), parsed.errors
        machine = parsed.file.machines[0]
        # The offending transition retains the bare name in `t.action` but
        # MUST NOT carry bound_arguments — that's the precondition for the
        # verifier's `check_unitarity` skip-then-revisit pattern at
        # `q_orca/verifier/quantum.py` lines 128-152.
        bare_transition = next(
            t for t in machine.transitions if t.action == "query_concept"
        )
        assert bare_transition.bound_arguments is None
        # Sanity: the verifier doesn't crash and doesn't fabricate
        # unitarity errors against the unbound template.
        result = verify_quantum(machine)
        assert not any(e.code == "QUBIT_INDEX_OUT_OF_RANGE" for e in result.errors)

    def test_orphan_parametric_action_warns_without_expansion_checks(self):
        # §6.4: a declared-but-unreferenced parametric action SHALL trigger
        # the standard ORPHAN_ACTION structural warning. Crucially, it must
        # not fire expansion-time checks — there are no call sites to
        # iterate, so the per-call-site loop in `check_unitarity` should
        # contribute zero errors. Pinned by a dedicated test rather than
        # implicitly via `test_bound_range_clean_across_call_sites`, which
        # exercises the inverse (a parametric action that IS referenced).
        source = """\
# machine OrphanParam

## context
| Field  | Type        | Default      |
|--------|-------------|--------------|
| qubits | list<qubit> | [q0, q1, q2] |

## events
- go

## state |s0> [initial]
## state |s1> [final]

## transitions
| Source | Event | Guard | Target | Action |
|--------|-------|-------|--------|--------|
| |s0>   | go    |       | |s1>   | apply_h |

## actions
| Name          | Signature          | Effect          |
|---------------|--------------------|-----------------|
| apply_h       | (qs) -> qs         | Hadamard(qs[0]) |
| query_concept | (qs, c: int) -> qs | Hadamard(qs[c]) |

## verification rules
- unitarity: all gates preserve norm
"""
        machine = _machine(source)
        structural = check_structural(machine)
        orphans = [
            e for e in structural.errors
            if e.code == "ORPHAN_ACTION"
            and e.location.get("action") == "query_concept"
        ]
        assert len(orphans) == 1, structural.errors
        assert orphans[0].severity == "warning"
        # No expansion-time errors against the orphan: the parametric
        # branch of `check_unitarity` skips it because there are no
        # bound_arguments to iterate.
        unitarity = verify_quantum(machine)
        assert all(
            e.location.get("action") != "query_concept"
            for e in unitarity.errors
        ), unitarity.errors

    def test_template_unbound_identifier_reported_at_parse_time(self):
        # Unbound subscripts are a parse-time error; the verifier runs on
        # the resulting AST and MUST NOT raise additional expansion-time
        # errors against a template whose bindings never closed.
        source = """\
# machine Bad

## context
| Field  | Type        | Default      |
|--------|-------------|--------------|
| qubits | list<qubit> | [q0, q1, q2] |

## events
- go

## state |s0> [initial]
## state |s1> [final]

## transitions
| Source | Event | Guard | Target | Action |
|--------|-------|-------|--------|--------|
| |s0>   | go    |       | |s1>   | broken(0) |

## actions
| Name   | Signature          | Effect          |
|--------|--------------------|-----------------|
| broken | (qs, c: int) -> qs | Hadamard(qs[d]) |

## verification rules
- unitarity: all gates preserve norm
"""
        from q_orca.parser.markdown_parser import parse_q_orca_markdown
        parsed = parse_q_orca_markdown(source)
        assert any("unbound identifier" in e and "'d'" in e for e in parsed.errors), (
            parsed.errors
        )


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


class TestMeasurementCollapseAllowed:
    """Opt-out path for SUPERPOSITION_LEAK on intentional terminal collapse.

    Replaces the tactical `prob_collapse(...)` guard fix used on the
    polysemantic examples with a declarative machine-wide rule.
    """

    _SOURCE_TEMPLATE = """\
# machine CollapseSink

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
| Name | Signature  | Effect          |
|------|------------|-----------------|
| do_H | (qs) -> qs | Hadamard(qs[0]) |
{rules_section}"""

    _RULES_OPT_OUT = """
## verification rules
- measurement_collapse_allowed: terminal collapse on `|result>` is intentional
"""

    def test_warning_fires_without_opt_out(self):
        # Baseline: same shape, no opt-out — warning fires (regression-pin).
        machine = _machine(self._SOURCE_TEMPLATE.format(rules_section=""))
        result = check_superposition_leaks(machine)
        leaks = [e for e in result.errors if e.code == "SUPERPOSITION_LEAK"]
        assert leaks, "expected SUPERPOSITION_LEAK warning without opt-out rule"
        # No rule means the kind never gets parsed in the first place.
        assert all(
            r.kind != "measurement_collapse_allowed"
            for r in machine.verification_rules
        )

    def test_opt_out_rule_suppresses_per_transition_warning(self):
        machine = _machine(
            self._SOURCE_TEMPLATE.format(rules_section=self._RULES_OPT_OUT)
        )
        # The new rule kind parses as a structured kind, not as `custom`.
        assert any(
            r.kind == "measurement_collapse_allowed"
            for r in machine.verification_rules
        )
        result = check_superposition_leaks(machine)
        assert all(
            e.code != "SUPERPOSITION_LEAK" for e in result.errors
        ), result.errors
        assert result.valid

    def test_opt_out_does_not_mask_unguarded_to_non_final(self):
        # Critical: the rule MUST NOT silence the genuine error case
        # (unguarded measurement to a NON-final state from a superposition).
        # That path is undefined behavior and should still be flagged.
        source = """\
# machine UnsafeMidCollapse

## context
| Field  | Type        | Default |
|--------|-------------|---------|
| qubits | list<qubit> |         |

## events
- apply
- measure
- finish

## state |00> [initial]
> Ground

## state |+0> = (|0> + |1>)|0>/√2
> Superposition

## state |mid>
> Non-final landing — undefined behavior under unguarded measure

## state |done> [final]
> Terminal

## transitions
| Source | Event   | Guard | Target | Action |
|--------|---------|-------|--------|--------|
| |00>   | apply   |       | |+0>   | do_H   |
| |+0>   | measure |       | |mid>  |        |
| |mid>  | finish  |       | |done> |        |

## actions
| Name | Signature  | Effect          |
|------|------------|-----------------|
| do_H | (qs) -> qs | Hadamard(qs[0]) |

## verification rules
- measurement_collapse_allowed: collapse on terminal step is intended
"""
        machine = _machine(source)
        result = check_superposition_leaks(machine)
        unguarded_to_non_final = [
            e for e in result.errors
            if e.code == "SUPERPOSITION_LEAK" and e.severity == "error"
        ]
        assert unguarded_to_non_final, (
            "opt-out rule must not mask unguarded measurement to a non-final state"
        )


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

    @pytest.mark.parametrize(
        "effect_str,angle_context,expected,notes",
        EFFECT_STRING_CASES,
        ids=[c[3] for c in EFFECT_STRING_CASES],
    )
    def test_shared_fixture_dict_shape(self, effect_str, angle_context, expected, notes):
        """Every gate kind in the shared fixture parses through the verifier
        adapter to the expected dict shape: name uppercased, targets/controls
        as lists, params={'theta': ...} when parameterized else {}."""
        from q_orca.verifier.dynamic import _parse_single_gate_to_dict

        gate = _parse_single_gate_to_dict(effect_str, angle_context=angle_context)
        assert gate is not None, f"{effect_str!r} returned None ({notes})"
        assert gate["name"] == expected.name.upper()
        assert gate["targets"] == list(expected.targets)
        assert gate["controls"] == list(expected.controls)
        if expected.parameter is None:
            assert gate["params"] == {}
        else:
            assert gate["params"]["theta"] == pytest.approx(expected.parameter)


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


class TestResourceInvariantVerification:
    """`check_resource_invariants` evaluates `Invariant(kind="resource")`
    against `estimate_resources(machine)` and emits
    `RESOURCE_BOUND_EXCEEDED` on violation. Machines without resource
    invariants do not invoke the estimator at all.
    """

    BELL = """\
# machine BellLike

## context
| Field | Type | Default |
|-------|------|---------|
| qubits | list<qubit> | [q0, q1] |

## state |00> [initial]

## state |bell> [final]

## transitions
| Source | Event | Guard | Target | Action |
| |00> | go | | |bell> | entangle |

## actions
| Name | Signature | Effect |
| entangle | (qs) -> qs | H(qs[0]); CNOT(qs[0], qs[1]) |

## verification rules
- unitarity
"""

    def test_resource_bound_exceeded(self):
        # bell-pair has cx_count=1; bound cx_count <= 0 must fail.
        src = self.BELL + "\n## invariants\n- cx_count <= 0\n"
        machine = _machine(src)
        result = verify(machine, VerifyOptions(skip_dynamic=True))
        codes = [e.code for e in result.errors]
        assert "RESOURCE_BOUND_EXCEEDED" in codes

    def test_resource_bound_satisfied(self):
        src = self.BELL + "\n## invariants\n- cx_count <= 5\n"
        machine = _machine(src)
        result = verify(machine, VerifyOptions(skip_dynamic=True))
        codes = [e.code for e in result.errors if e.severity == "error"]
        assert "RESOURCE_BOUND_EXCEEDED" not in codes

    def test_resource_invariants_skipped_when_absent(self):
        # No resource invariants — `estimate_resources` must not be called.
        from unittest.mock import patch

        machine = _machine(self.BELL)
        with patch("q_orca.verifier.resources.estimate_resources") as spy:
            verify(machine, VerifyOptions(skip_dynamic=True))
            assert spy.call_count == 0


class TestHeaEncodingVerifier:
    """Stage 4b HEA dispatch: the verifier invokes
    `compute_concept_gram_hea` for HEA-encoded machines and surfaces any
    `HeaGramConfigurationError` as `HEA_GRAM_INVALID`. Non-HEA machines
    bypass the dispatch entirely. See the `add-rung2-hea-encoding` spec
    delta."""

    BASE = """\
# machine HeaVerifier

## context
| Field  | Type        | Default      |
|--------|-------------|--------------|
| qubits | list<qubit> | [q0, q1]     |

## events
- prep_a
- prep_b

## state idle [initial]
## state queried_a [final]
## state queried_b [final]

## transitions
| Source | Event  | Guard | Target    | Action        |
| idle   | prep_a |       | queried_a | query_concept |
| idle   | prep_b |       | queried_b | query_concept |

## actions
| Name          | Signature  |
| query_concept | (qs) -> qs |

## encoding
| key       | value  |
| kind      | hea    |
| depth     | 2      |
| entangler | ring   |
| rotations | Ry, Rz |

## theta
| concept | tensor |
| a | [[[0.1, 0.2], [0.3, 0.4]], [[0.5, 0.6], [0.7, 0.8]]] |
| b | [[[1.1, 1.2], [1.3, 1.4]], [[1.5, 1.6], [1.7, 1.8]]] |
"""

    BELL = """\
# machine BellEntangler

## context
| Field  | Type        | Default  |
|--------|-------------|----------|
| qubits | list<qubit> | [q0, q1] |

## events
- prepare
- entangle

## state |00> [initial]
## state |+0>
## state |ψ> [final]

## transitions
| Source | Event    | Guard | Target | Action     |
| |00>   | prepare  |       | |+0>   | apply_h    |
| |+0>   | entangle |       | |ψ>    | apply_cnot |

## actions
| Name       | Signature  | Effect           |
| apply_h    | (qs) -> qs | Hadamard(qs[0])  |
| apply_cnot | (qs) -> qs | CNOT(qs[0], qs[1]) |
"""

    def test_hea_consistency_check_passes_on_valid_machine(self):
        machine = _machine(self.BASE)
        result = verify(machine)
        codes = [e.code for e in result.errors if e.severity == "error"]
        assert "HEA_GRAM_INVALID" not in codes, codes

    def test_hea_call_site_theta_row_count_mismatch_emits_error(self):
        """3 theta rows but only 2 query_concept call sites in
        transitions — Stage 4b SHALL emit `HEA_GRAM_INVALID`."""
        three_row_machine = self.BASE.replace(
            "| b | [[[1.1, 1.2], [1.3, 1.4]], [[1.5, 1.6], [1.7, 1.8]]] |",
            "| b | [[[1.1, 1.2], [1.3, 1.4]], [[1.5, 1.6], [1.7, 1.8]]] |\n"
            "| c | [[[2.1, 2.2], [2.3, 2.4]], [[2.5, 2.6], [2.7, 2.8]]] |",
        )
        machine = _machine(three_row_machine)
        result = verify(machine)
        errors = [e for e in result.errors if e.code == "HEA_GRAM_INVALID"]
        assert len(errors) == 1
        assert errors[0].severity == "error"
        assert "2 call site" in errors[0].message
        assert "3 concept row" in errors[0].message

    def test_hea_post_parse_shape_mismatch_emits_error(self):
        """Programmatic shape mismatch (the parser would reject this at
        parse time) — exercises the verifier's own surface for the
        'survived initial parsing' scenario in the spec."""
        import numpy as np

        machine = _machine(self.BASE)
        machine.theta.rows[0].tensor = np.zeros((1, 2, 2))
        result = verify(machine)
        errors = [e for e in result.errors if e.code == "HEA_GRAM_INVALID"]
        assert len(errors) == 1
        assert errors[0].severity == "error"
        assert "'a'" in errors[0].message

    def test_non_hea_machine_bypasses_hea_dispatch(self):
        """Bell-entangler has no `## encoding` section — Stage 4b SHALL
        NOT invoke `compute_concept_gram_hea`."""
        from unittest.mock import patch

        machine = _machine(self.BELL)
        # The HEA module imports the helper lazily inside the function,
        # so patch the source module rather than the importer.
        with patch(
            "q_orca.compiler.concept_gram_hea.compute_concept_gram_hea"
        ) as spy:
            verify(machine)
            assert spy.call_count == 0

    def test_hea_check_skipped_under_skip_dynamic(self):
        """The HEA check builds quantum statevectors via numpy, so it
        SHALL be gated by `skip_dynamic` like the rest of Stage 4b.
        With a programmatically broken theta, the check would normally
        emit `HEA_GRAM_INVALID` — under `skip_dynamic=True` it must
        not fire at all."""
        import numpy as np
        from unittest.mock import patch

        machine = _machine(self.BASE)
        machine.theta.rows[0].tensor = np.zeros((1, 2, 2))
        with patch(
            "q_orca.compiler.concept_gram_hea.compute_concept_gram_hea"
        ) as spy:
            result = verify(machine, VerifyOptions(skip_dynamic=True))
            assert spy.call_count == 0
        codes = [e.code for e in result.errors if e.severity == "error"]
        assert "HEA_GRAM_INVALID" not in codes


class TestHeaTierOrderingInvariant:
    """Stage 4b enforcement of `concept_gram_tier_separation` against
    the analytic Gram of an HEA-encoded machine. See
    `add-hea-tier-ordering-invariant`."""

    BASE = """\
# machine HeaTier

## context
| Field  | Type        | Default          |
|--------|-------------|------------------|
| qubits | list<qubit> | [q0, q1, q2]     |

## events
- prep_a
- prep_b
- prep_c

## state idle [initial]
## state queried_a [final]
## state queried_b [final]
## state queried_c [final]

## transitions
| Source | Event  | Guard | Target    | Action        |
| idle   | prep_a |       | queried_a | query_concept |
| idle   | prep_b |       | queried_b | query_concept |
| idle   | prep_c |       | queried_c | query_concept |

## actions
| Name          | Signature  |
| query_concept | (qs) -> qs |

## encoding
| key       | value  |
| kind      | hea    |
| depth     | 3      |
| entangler | ring   |
| rotations | Ry, Rz |

## theta
| concept | tensor | cluster |
| a | [[[0.0457, -0.156, 0.1126], [0.1411, -0.2927, -0.1953], [0.0192, -0.0474, -0.0025]], [[-0.128, 0.1319, 0.1167], [0.0099, 0.1691, 0.0701], [-0.1289, 0.0553, -0.1438]]] | s1 |
| b | [[[0.0371, -0.1427, 0.1124], [0.1371, -0.2968, -0.2004], [0.0205, -0.0395, -0.0065]], [[-0.1315, 0.1363, 0.117], [0.0191, 0.1578, 0.0783], [-0.1294, 0.0523, -0.1584]]] | s1 |
| c | [[[1.2682, 1.0909, 1.0102], [0.8841, 1.1853, 0.9248], [0.7295, 0.9307, 0.6622]], [[1.1194, 0.9863, 1.2396], [0.9105, 1.0324, 1.1632], [1.243, 0.9765, 0.9332]]] | s2 |
"""

    BELL_BASE = """\
# machine BellNoEncoding

## context
| Field  | Type        | Default  |
|--------|-------------|----------|
| qubits | list<qubit> | [q0, q1] |

## events
- prepare
- entangle

## state |00> [initial]
## state |+0>
## state |ψ> [final]

## transitions
| Source | Event    | Guard | Target | Action     |
| |00>   | prepare  |       | |+0>   | apply_h    |
| |+0>   | entangle |       | |ψ>    | apply_cnot |

## actions
| Name       | Signature  | Effect             |
| apply_h    | (qs) -> qs | Hadamard(qs[0])    |
| apply_cnot | (qs) -> qs | CNOT(qs[0], qs[1]) |
"""

    def test_satisfied_invariant_no_errors(self):
        """The spike-validated example yields tier_separation ≈ 0.6162.
        Declaring `>= 0.025` SHALL pass without error."""
        src = self.BASE + "\n## invariants\n- concept_gram_tier_separation >= 0.025\n"
        machine = _machine(src)
        result = verify(machine)
        codes = [e.code for e in result.errors if e.severity == "error"]
        assert "HEA_TIER_INVARIANT_VIOLATED" not in codes
        assert "HEA_TIER_UNDEFINED" not in codes
        assert "HEA_TIER_INVARIANT_NOT_APPLICABLE" not in codes

    def test_violated_invariant_emits_error_with_pair_attribution(self):
        """Declare an unrealistically tight bound — actual ≈ 0.6162,
        bound 0.99 → violated, with cluster pair attribution."""
        src = self.BASE + "\n## invariants\n- concept_gram_tier_separation >= 0.99\n"
        machine = _machine(src)
        result = verify(machine)
        violations = [
            e for e in result.errors
            if e.code == "HEA_TIER_INVARIANT_VIOLATED"
        ]
        assert len(violations) == 1
        msg = violations[0].message
        assert violations[0].severity == "error"
        # Cross-cluster pair = (s1, s2), sorted alphabetically.
        assert "('s1', 's2')" in msg
        assert ">= 0.99" in msg

    def test_all_singleton_clusters_emit_undefined(self):
        """If every concept is in its own cluster, no intra-cluster
        pairs exist → metric undefined → HEA_TIER_UNDEFINED."""
        # Replace `s1, s1, s2` with three distinct singletons.
        singleton_base = self.BASE.replace(
            "| s1 |", "| sA |", 1
        ).replace(
            "| s1 |", "| sB |", 1
        ).replace(
            "| s2 |", "| sC |", 1
        )
        src = (
            singleton_base
            + "\n## invariants\n- concept_gram_tier_separation >= 0.025\n"
        )
        machine = _machine(src)
        result = verify(machine)
        undefined = [
            e for e in result.errors if e.code == "HEA_TIER_UNDEFINED"
        ]
        assert len(undefined) == 1
        assert undefined[0].severity == "error"
        assert "singleton" in undefined[0].message

    def test_skip_dynamic_gates_tier_check(self):
        """Tier-invariant evaluation builds the analytic Gram, so it
        SHALL be gated by `skip_dynamic` along with the rest of
        Stage 4b. With a clearly violated bound, `skip_dynamic=True`
        must suppress `HEA_TIER_INVARIANT_VIOLATED`."""
        src = self.BASE + "\n## invariants\n- concept_gram_tier_separation >= 0.99\n"
        machine = _machine(src)
        result = verify(machine, VerifyOptions(skip_dynamic=True))
        codes = [e.code for e in result.errors]
        assert "HEA_TIER_INVARIANT_VIOLATED" not in codes
        assert "HEA_TIER_UNDEFINED" not in codes

    def test_non_hea_machine_with_invariant_emits_warning(self):
        """A machine with no `## encoding` section but a declared
        tier-separation invariant SHALL emit
        HEA_TIER_INVARIANT_NOT_APPLICABLE at warning severity, and
        verification SHALL still pass."""
        src = (
            self.BELL_BASE
            + "\n## invariants\n- concept_gram_tier_separation >= 0.025\n"
        )
        machine = _machine(src)
        result = verify(machine)
        warnings = [
            e for e in result.errors
            if e.code == "HEA_TIER_INVARIANT_NOT_APPLICABLE"
        ]
        assert len(warnings) == 1
        assert warnings[0].severity == "warning"
        # No `error`-severity tier codes.
        error_codes = [
            e.code for e in result.errors if e.severity == "error"
        ]
        assert "HEA_TIER_INVARIANT_VIOLATED" not in error_codes
        assert "HEA_TIER_UNDEFINED" not in error_codes


# ---------------------------------------------------------------------------
# Composition stage (add-parameterized-invoke §3.9)
# ---------------------------------------------------------------------------

from q_orca.verifier.composition import check_composition

_CHILD_CLASSICAL = """
---
# machine EpochRunner
## context
| Field | Type | Default |
| epoch | int | 0 |
| lr | float | 0.1 |
## state |run> [initial]
## state |out> [final]
## transitions
| Source | Event | Guard | Target | Action |
| |run> | step | | |out> | |
## returns
| Name | Type | Statistics |
| converged | bool | |
"""

_CHILD_QUANTUM = """
---
# machine QForward
## context
| Field | Type | Default |
| theta | float | 0.5 |
## state |q0> [initial]
## state |qm> [final]
## transitions
| Source | Event | Guard | Target | Action |
| |q0> | measure_it | | |qm> | meas |
## actions
| Name | Signature | Effect |
| meas | (qs) -> qs | measure(qs[0]) -> bits[0] |
## returns
| Name | Type | Statistics |
| bits[0] | bit | expectation, histogram |
"""


def _parent(ctx_rows, annotation, body=""):
    return (
        "# machine Parent\n## context\n| Field | Type | Default |\n"
        + ctx_rows
        + "## state |idle> [initial]\n## state |train> "
        + annotation
        + "\n"
        + ((body + "\n") if body else "")
        + "## state |fin> [final]\n## transitions\n"
        + "| Source | Event | Guard | Target | Action |\n"
        + "| |idle> | g | | |train> | |\n| |train> | n | | |fin> | |\n"
    )


def _composition_codes(src, machine_name="Parent"):
    result = parse_q_orca_markdown(src)
    assert not result.errors, result.errors
    by_name = {m.name: m for m in result.file.machines}
    res = check_composition(result.file, by_name[machine_name])
    return [d.code for d in res.errors]


_INVOKE_ERROR_CODES = {
    "UNRESOLVED_CHILD_MACHINE", "INVOKE_ARG_UNDECLARED", "INVOKE_ARG_TYPE_MISMATCH",
    "INVOKE_RETURN_UNDECLARED", "INVOKE_RETURN_TYPE_MISMATCH",
    "SHOTS_ON_CLASSICAL_CHILD", "INVOKE_CYCLE",
}


class TestComposition:
    def test_happy_classical_child(self):
        src = _parent(
            "| iteration | int | 0 |\n| eta | float | 0.1 |\n| done | bool | false |\n",
            "[invoke: EpochRunner(epoch=iteration, lr=eta)]",
            "> returns: done=converged",
        ) + _CHILD_CLASSICAL
        assert [c for c in _composition_codes(src) if c in _INVOKE_ERROR_CODES] == []

    def test_happy_quantum_child_shots_aggregate(self):
        src = _parent(
            "| theta | float | 0.5 |\n| p | float | 0.0 |\n",
            "[invoke: QForward(theta=theta) shots=1024]",
            "> returns: p=prob_bits_0",
        ) + _CHILD_QUANTUM
        assert [c for c in _composition_codes(src) if c in _INVOKE_ERROR_CODES] == []

    def test_unresolved_child(self):
        src = _parent("| x | int | 0 |\n", "[invoke: Missing(a=x)]")
        assert "UNRESOLVED_CHILD_MACHINE" in _composition_codes(src)

    def test_arg_undeclared(self):
        src = _parent("| iteration | int | 0 |\n", "[invoke: EpochRunner(zzz=iteration)]") + _CHILD_CLASSICAL
        assert "INVOKE_ARG_UNDECLARED" in _composition_codes(src)

    def test_arg_type_mismatch(self):
        src = _parent("| theta | list<float> | [] |\n", "[invoke: QForward(theta=theta) shots=8]") + _CHILD_QUANTUM
        assert "INVOKE_ARG_TYPE_MISMATCH" in _composition_codes(src)

    def test_indexed_rhs_unifies_against_element_type(self):
        # theta[0] of a parent list<float> unifies with the child's float param.
        src = _parent("| theta | list<float> | [] |\n", "[invoke: QForward(theta=theta[0]) shots=8]") + _CHILD_QUANTUM
        assert "INVOKE_ARG_TYPE_MISMATCH" not in _composition_codes(src)

    def test_return_undeclared_aggregate(self):
        # QForward declares expectation+histogram for bits[0] but not variance.
        src = _parent(
            "| theta | float | 0.5 |\n| v | float | 0.0 |\n",
            "[invoke: QForward(theta=theta) shots=8]",
            "> returns: v=var_bits_0",
        ) + _CHILD_QUANTUM
        assert "INVOKE_RETURN_UNDECLARED" in _composition_codes(src)

    def test_shots_on_classical_child(self):
        src = _parent("| iteration | int | 0 |\n", "[invoke: EpochRunner(epoch=iteration) shots=100]") + _CHILD_CLASSICAL
        assert "SHOTS_ON_CLASSICAL_CHILD" in _composition_codes(src)

    def test_default_shots_on_quantum_child_is_clean(self):
        src = _parent("| theta | float | 0.5 |\n", "[invoke: QForward(theta=theta)]") + _CHILD_QUANTUM
        assert [c for c in _composition_codes(src) if c in _INVOKE_ERROR_CODES] == []

    def test_direct_self_invoke_cycle(self):
        src = (
            "# machine Loop\n## context\n| Field | Type | Default |\n| x | int | 0 |\n"
            "## state |a> [initial]\n## state |b> [invoke: Loop(x=x)]\n## state |c> [final]\n"
            "## transitions\n| Source | Event | Guard | Target | Action |\n"
            "| |a> | g | | |b> | |\n| |b> | n | | |c> | |\n"
        )
        assert "INVOKE_CYCLE" in _composition_codes(src, "Loop")

    def test_transitive_cycle_on_both(self):
        src = (
            "# machine A\n## context\n| Field | Type | Default |\n| x | int | 0 |\n"
            "## state |a0> [initial]\n## state |a1> [invoke: B(x=x)]\n## state |a2> [final]\n"
            "## transitions\n| Source | Event | Guard | Target | Action |\n"
            "| |a0> | g | | |a1> | |\n| |a1> | n | | |a2> | |\n"
            "\n---\n\n"
            "# machine B\n## context\n| Field | Type | Default |\n| x | int | 0 |\n"
            "## state |b0> [initial]\n## state |b1> [invoke: A(x=x)]\n## state |b2> [final]\n"
            "## transitions\n| Source | Event | Guard | Target | Action |\n"
            "| |b0> | g | | |b1> | |\n| |b1> | n | | |b2> | |\n"
        )
        assert "INVOKE_CYCLE" in _composition_codes(src, "A")
        assert "INVOKE_CYCLE" in _composition_codes(src, "B")

    def test_child_error_bubbles_up_with_path(self):
        src = (
            _parent("| x | int | 0 |\n", "[invoke: Broken(y=x)]")
            + "\n---\n# machine Broken\n## context\n| Field | Type | Default |\n| y | int | 0 |\n"
            + "## events\n- run\n- other\n"
            + "## state |idle> [initial]\n## state |done> [final]\n"
            + "## transitions\n| Source | Event | Guard | Target | Action |\n| |idle> | run | | |done> | |\n"
        )
        result = parse_q_orca_markdown(src)
        by_name = {m.name: m for m in result.file.machines}
        errs = check_composition(result.file, by_name["Parent"]).errors
        bubbled = [e for e in errs if (e.location or {}).get("child_machine") == "Broken"]
        assert bubbled, "expected at least one bubbled child error"
        assert all("invoke_state" in e.location and "child_path" in e.location for e in bubbled)

    def test_nested_chain_a_b_c(self):
        # A invokes B invokes C; a valid chain produces no invoke errors.
        src = (
            "# machine A\n## context\n| Field | Type | Default |\n| x | int | 0 |\n"
            "## state |a0> [initial]\n## state |a1> [invoke: B(y=x)]\n## state |a2> [final]\n"
            "## transitions\n| Source | Event | Guard | Target | Action |\n| |a0> | g | | |a1> | |\n| |a1> | n | | |a2> | |\n"
            "\n---\n\n"
            "# machine B\n## context\n| Field | Type | Default |\n| y | int | 0 |\n"
            "## state |b0> [initial]\n## state |b1> [invoke: C(z=y)]\n## state |b2> [final]\n"
            "## transitions\n| Source | Event | Guard | Target | Action |\n| |b0> | g | | |b1> | |\n| |b1> | n | | |b2> | |\n"
            "\n---\n\n"
            "# machine C\n## context\n| Field | Type | Default |\n| z | int | 0 |\n"
            "## state |c0> [initial]\n## state |c1> [final]\n"
            "## transitions\n| Source | Event | Guard | Target | Action |\n| |c0> | g | | |c1> | |\n"
        )
        assert "INVOKE_CYCLE" not in _composition_codes(src, "A")
        assert [c for c in _composition_codes(src, "A") if c in _INVOKE_ERROR_CODES] == []

    def test_three_machine_cycle_reports_path(self):
        # A -> B -> C -> A: every machine is flagged, and the INVOKE_CYCLE
        # error carries a representative cycle path for debugging.
        def m(name, child):
            return (
                f"# machine {name}\n## context\n| Field | Type | Default |\n| x | int | 0 |\n"
                f"## state |s0> [initial]\n## state |s1> [invoke: {child}(x=x)]\n## state |s2> [final]\n"
                "## transitions\n| Source | Event | Guard | Target | Action |\n"
                "| |s0> | g | | |s1> | |\n| |s1> | n | | |s2> | |\n"
            )
        src = m("A", "B") + "\n---\n\n" + m("B", "C") + "\n---\n\n" + m("C", "A")
        result = parse_q_orca_markdown(src)
        assert not result.errors, result.errors
        by_name = {mm.name: mm for mm in result.file.machines}
        for name in ("A", "B", "C"):
            errs = check_composition(result.file, by_name[name]).errors
            cyc = [e for e in errs if e.code == "INVOKE_CYCLE"]
            assert cyc, f"{name} should report INVOKE_CYCLE"
            path = cyc[0].location["cycle_path"]
            assert path[0] == name and path[-1] == name and len(path) == 4

    def test_pipeline_runs_composition_before_quantum_static(self):
        # An unresolved child surfaces from composition while verify() still runs.
        src = _parent("| x | int | 0 |\n", "[invoke: Missing(a=x)]")
        result = parse_q_orca_markdown(src)
        machine = result.file.machines[0]
        res = verify(machine, VerifyOptions(skip_dynamic=True), file=result.file)
        assert any(e.code == "UNRESOLVED_CHILD_MACHINE" for e in res.errors)

    def test_skip_composition_flag(self):
        src = _parent("| x | int | 0 |\n", "[invoke: Missing(a=x)]")
        result = parse_q_orca_markdown(src)
        machine = result.file.machines[0]
        res = verify(machine, VerifyOptions(skip_dynamic=True, skip_composition=True), file=result.file)
        assert not any(e.code == "UNRESOLVED_CHILD_MACHINE" for e in res.errors)


# ---------------------------------------------------------------------------
# Composition with cross-file imports (add-machine-imports §4.6)
# ---------------------------------------------------------------------------

from q_orca.loader.import_resolver import resolve_imports

_IMPORT_CHILD = """# machine PrepareBellPair
## context
| Field | Type | Default |
| seed | int | 0 |
## state |a> [initial]
## state |b> [final]
## transitions
| Source | Event | Guard | Target | Action |
| |a> | g | | |b> | |
"""


def _import_parent(child_ref):
    return (
        "# machine Parent\n## context\n| Field | Type | Default |\n| iteration | int | 0 |\n"
        "## imports\n| Path | Aliases |\n| ./lib/bell-pair.q.orca.md | PrepareBellPair |\n"
        f"## state |idle> [initial]\n## state |prep> [invoke: {child_ref}(seed=iteration)]\n## state |done> [final]\n"
        "## transitions\n| Source | Event | Guard | Target | Action |\n"
        "| |idle> | g | | |prep> | |\n| |prep> | n | | |done> | |\n"
    )


def _verify_with_imports(tmp_path, parent_src, follow=True):
    (tmp_path / "lib").mkdir(parents=True, exist_ok=True)
    (tmp_path / "lib" / "bell-pair.q.orca.md").write_text(_IMPORT_CHILD)
    ppath = tmp_path / "parent.q.orca.md"
    ppath.write_text(parent_src)
    pf = parse_q_orca_markdown(parent_src)
    assert not pf.errors, pf.errors
    graph = resolve_imports(pf.file, str(ppath)) if follow else None
    res = verify(pf.file.machines[0], VerifyOptions(skip_dynamic=True), file=pf.file, import_graph=graph)
    return [e.code for e in res.errors]


class TestCompositionImports:
    def test_imported_child_resolves_clean(self, tmp_path):
        codes = _verify_with_imports(tmp_path, _import_parent("PrepareBellPair"))
        invoke_codes = [c for c in codes if c in _INVOKE_ERROR_CODES or c.startswith("IMPORT")]
        assert invoke_codes == []

    def test_typo_gets_edit_distance_suggestion(self, tmp_path):
        (tmp_path / "lib").mkdir(parents=True, exist_ok=True)
        (tmp_path / "lib" / "bell-pair.q.orca.md").write_text(_IMPORT_CHILD)
        ppath = tmp_path / "parent.q.orca.md"
        src = _import_parent("PrepareBelPair")  # typo
        ppath.write_text(src)
        pf = parse_q_orca_markdown(src)
        graph = resolve_imports(pf.file, str(ppath))
        res = verify(pf.file.machines[0], VerifyOptions(skip_dynamic=True), file=pf.file, import_graph=graph)
        unresolved = [e for e in res.errors if e.code == "UNRESOLVED_CHILD_MACHINE"]
        assert unresolved
        assert "PrepareBellPair" in unresolved[0].message  # suggestion

    def test_no_follow_imports_leaves_child_unresolved(self, tmp_path):
        codes = _verify_with_imports(tmp_path, _import_parent("PrepareBellPair"), follow=False)
        assert "UNRESOLVED_CHILD_MACHINE" in codes
