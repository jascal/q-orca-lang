"""Tests for qubit role types (add-qubit-role-types).

Parsing (tags / ranges / unknown / malformed), the three role-driven verifier
rules (ancilla_reset, syndrome_completeness, communication_no_cloning), backward
compatibility, and the now-resolved `qs[role:R]` noise selector.
"""

from q_orca.parser.markdown_parser import parse_q_orca_markdown
from q_orca.verifier import verify, VerifyOptions
from q_orca.verifier.quantum import check_no_cloning
from q_orca.verifier.roles import check_qubit_roles
from q_orca.verifier.noise_model import check_noise_model


def _machine(default):
    src = f"""# machine T
## context
| Field | Type | Default |
| qubits | list<qubit> | {default} |
## state |s0> [initial]
## state |s1> [final]
## transitions
| Source | Event | Guard | Target | Action |
| |s0> | go |  | |s1> |  |
"""
    return parse_q_orca_markdown(src)


# ── Parsing ─────────────────────────────────────────────────────────────────

class TestParsing:
    def test_tagged_roles(self):
        m = _machine("[q0:data, q1:ancilla, q2:ancilla]").file.machines[0]
        assert m.qubit_roles == ["data", "ancilla", "ancilla"]
        assert m.context[0].default_value == "[q0, q1, q2]"  # tags stripped

    def test_untagged_defaults_to_data(self):
        m = _machine("[q0, q1]").file.machines[0]
        assert m.qubit_roles == ["data", "data"]
        assert m.context[0].default_value == "[q0, q1]"

    def test_range_expands(self):
        m = _machine("[q0..q2:data, q3..q4:ancilla]").file.machines[0]
        assert m.qubit_roles == ["data", "data", "data", "ancilla", "ancilla"]
        assert m.context[0].default_value == "[q0, q1, q2, q3, q4]"

    def test_unknown_role_errors(self):
        errs = _machine("[q0:wizard]").errors or []
        assert any("unknown_qubit_role" in e for e in errs)

    def test_reserved_role_errors(self):
        errs = _machine("[q0:coin]").errors or []
        assert any("unknown_qubit_role" in e and "reserved" in e for e in errs)

    def test_malformed_range_errors(self):
        for bad in ("[q0..q5a:data]", "[q0..x9:data]", "[q5..q0:data]"):
            errs = _machine(bad).errors or []
            assert any("qubit_range_invalid" in e for e in errs), bad

    def test_bare_range_no_role(self):
        m = _machine("[q0..q3]").file.machines[0]
        assert m.qubit_roles == ["data", "data", "data", "data"]

    def test_mixed_tagged_untagged(self):
        m = _machine("[q0:data, q1, q2:ancilla]").file.machines[0]
        assert m.qubit_roles == ["data", "data", "ancilla"]

    def test_whitespace_in_range(self):
        m = _machine("[q0 .. q3 : ancilla]").file.machines[0]
        assert m.qubit_roles == ["ancilla"] * 4

    def test_typo_role_gets_suggestion(self):
        errs = _machine("[q0:ancillaa]").errors or []
        assert any("did you mean 'ancilla'" in e for e in errs)


# ── Verifier rules ───────────────────────────────────────────────────────────

def _roles_codes(src):
    m = parse_q_orca_markdown(src).file.machines[0]
    return [(e.code, e.severity) for e in check_qubit_roles(m).errors]


_ANCILLA = """# machine A
## context
| Field | Type | Default |
| qubits | list<qubit> | [q0:data, q1:ancilla] |
| bits | list<bit> | [b0] |
## state |s0> [initial]
## state |s1>
{mid}
## state |s2> [final]
## transitions
| Source | Event | Guard | Target | Action |
| |s0> | a |  | |s1> | meas1 |
{trans}
## actions
| Name | Signature | Effect |
| meas1 | (qs) -> qs | measure(qs[1]) -> bits[0] |
| rst | (qs) -> qs | reset(qs[1]) |
| meas2 | (qs) -> qs | measure(qs[1]) -> bits[0] |
"""


class TestAncillaReset:
    def test_double_measure_without_reset_fails(self):
        src = _ANCILLA.format(mid="", trans="| |s1> | b |  | |s2> | meas2 |")
        assert ("ANCILLA_NOT_RESET", "error") in _roles_codes(src)

    def test_reset_between_measures_passes(self):
        src = _ANCILLA.format(
            mid="## state |sr>",
            trans="| |s1> | r |  | |sr> | rst |\n| |sr> | b |  | |s2> | meas2 |")
        assert _roles_codes(src) == []


_SYNDROME = """# machine S
## context
| Field | Type | Default |
| qubits | list<qubit> | [q0:data, q1:syndrome] |
| bits | list<bit> | [b0] |
## state |s0> [initial]
## state |loop>
## state |done> [final]
## transitions
| Source | Event | Guard | Target | Action |
| |s0> | a |  | |loop> | prep |
| |loop> | b |  | |loop> | {loopaction} |
| |loop> | c |  | |done> |  |
## actions
| Name | Signature | Effect |
| prep | (qs) -> qs | CNOT(qs[0], qs[1]) |
| meas | (qs) -> qs | measure(qs[1]) -> bits[0] |
"""


class TestSyndromeCompleteness:
    def test_cycle_without_measure_fails(self):
        assert ("SYNDROME_NOT_MEASURED", "error") in _roles_codes(_SYNDROME.format(loopaction="prep"))

    def test_cycle_with_measure_passes(self):
        assert _roles_codes(_SYNDROME.format(loopaction="meas")) == []


_COMM = """# machine C
## context
| Field | Type | Default |
| qubits | list<qubit> | [q0:communication, q1:data] |
## state |s0> [initial]
## state |s1> [final]
## transitions
| Source | Event | Guard | Target | Action |
| |s0> | go |  | |s1> | dup |
## actions
| Name | Signature | Effect |
| dup | (qs) -> qs | clone(qs[0], qs[1]) |
## verification rules
- no_cloning
"""


class TestCommunicationNoCloning:
    def test_communication_clone_escalates(self):
        m = parse_q_orca_markdown(_COMM).file.machines[0]
        codes = [e.code for e in check_no_cloning(m).errors]
        assert "COMMUNICATION_NO_CLONING_VIOLATION" in codes
        assert "NO_CLONING_VIOLATION" not in codes

    def test_data_clone_stays_generic(self):
        m = parse_q_orca_markdown(_COMM.replace("q0:communication", "q0:data")).file.machines[0]
        codes = [e.code for e in check_no_cloning(m).errors]
        assert "NO_CLONING_VIOLATION" in codes
        assert "COMMUNICATION_NO_CLONING_VIOLATION" not in codes


# ── Backward compatibility ──────────────────────────────────────────────────

def test_untagged_machine_verifies_unchanged():
    # An untagged register triggers no role rules.
    m = _machine("[q0, q1]").file.machines[0]
    assert check_qubit_roles(m).errors == []


# ── Noise qs[role:R] now resolves ───────────────────────────────────────────

def test_noise_role_selector_resolves():
    src = """# machine N
## context
| Field | Type | Default |
| qubits | list<qubit> | [q0:data, q1:ancilla, q2:ancilla] |
## noise_model
| Channel | Target | Parameters |
| thermal | qs[role:ancilla] | T1=1us, T2=1us |
## state |s0> [initial]
## state |s1> [final]
## transitions
| Source | Event | Guard | Target | Action |
| |s0> | go |  | |s1> | mk |
## actions
| Name | Signature | Effect |
| mk | (qs) -> qs | H(qs[0]) |
"""
    m = parse_q_orca_markdown(src).file.machines[0]
    codes = [e.code for e in check_noise_model(m).errors]
    assert "NOISE_TARGET_NO_MATCH" not in codes

def test_noise_role_selector_unmatched_warns():
    src = """# machine N
## context
| Field | Type | Default |
| qubits | list<qubit> | [q0:data, q1:data] |
## noise_model
| Channel | Target | Parameters |
| thermal | qs[role:ancilla] | T1=1us, T2=1us |
## state |s0> [initial]
## state |s1> [final]
## transitions
| Source | Event | Guard | Target | Action |
| |s0> | go |  | |s1> | mk |
## actions
| Name | Signature | Effect |
| mk | (qs) -> qs | H(qs[0]) |
"""
    m = parse_q_orca_markdown(src).file.machines[0]
    codes = [e.code for e in check_noise_model(m).errors]
    assert "NOISE_TARGET_NO_MATCH" in codes


# ── Migrated example ────────────────────────────────────────────────────────

def test_bit_flip_syndrome_example_verifies_with_roles():
    m = parse_q_orca_markdown(open("examples/bit-flip-syndrome.q.orca.md").read()).file.machines[0]
    assert m.qubit_roles == ["data", "data", "data", "ancilla", "ancilla"]
    result = verify(m, VerifyOptions(skip_dynamic=True, skip_qutip=True))
    assert not any(e.code in ("ANCILLA_NOT_RESET", "SYNDROME_NOT_MEASURED") for e in result.errors)
