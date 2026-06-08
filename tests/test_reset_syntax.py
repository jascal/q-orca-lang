"""Tests for the first-class `reset(qs[i])` effect (add-reset-syntax)."""

import pytest

from q_orca.parser.markdown_parser import parse_q_orca_markdown
from q_orca.ast import QEffectReset


def _machine(src: str):
    res = parse_q_orca_markdown(src)
    assert not res.errors, res.errors
    return res.file.machines[0]


_MR = """# machine M
## context
| Field | Type | Default |
|---|---|---|
| qubits | list<qubit> | [q0, q1] |
## states
## state |s0> [initial]
## state |s1>
## state |done> [final]
## events
- a
- b
## transitions
| Source | Event | Guard | Target | Action |
|---|---|---|---|---|
| |s0> | a | | |s1> | flip |
| |s1> | b | | |done> | mr |
## actions
| Name | Signature | Effect |
|---|---|---|
| flip | (qs) -> qs | X(qs[0]) |
| mr | (qs) -> qs | measure(qs[0]) -> bits[0]; reset(qs[0]) |
"""


def _rep_machine(rounds: int, data_p: float = 0.05):
    """Distance-3 bit-flip repetition code, `rounds` syndrome rounds with ancilla
    reset between rounds (q3/q4 reused)."""
    trans, acts, ev = [], {}, [0]

    def add(s, t, a, eff):
        e = f"e{ev[0]}"
        ev[0] += 1
        trans.append((s, e, t, a))
        acts[a] = eff

    extract = "CNOT(qs[0], qs[3]); CNOT(qs[1], qs[3]); CNOT(qs[1], qs[4]); CNOT(qs[2], qs[4])"
    for r in range(rounds):
        s_in = "|enc>" if r == 0 else f"|r{r}>"
        add(s_in, f"|r{r}x>", f"ext{r}", extract)
        add(f"|r{r}x>", f"|r{r}a>", f"ms0_{r}", "measure(qs[3]) -> bits[0]; reset(qs[3])")
        nxt = f"|r{r+1}>" if r < rounds - 1 else "|rd>"
        add(f"|r{r}a>", nxt, f"ms1_{r}", "measure(qs[4]) -> bits[1]; reset(qs[4])")
    add("|rd>", "|rd0>", "md0", "measure(qs[0]) -> bits[2]")
    add("|rd0>", "|rd1>", "md1", "measure(qs[1]) -> bits[3]")
    add("|rd1>", "|done>", "md2", "measure(qs[2]) -> bits[4]")
    hdr = ("# machine Rep\n## context\n| Field | Type | Default |\n|---|---|---|\n"
           "| qubits | list<qubit> | [q0:data, q1:data, q2:data, q3:ancilla, q4:ancilla] |\n"
           "| bits | list<bit> | [b0,b1,b2,b3,b4] |\n## noise_model\n| Channel | Target | Parameters |\n|---|---|---|\n"
           f"| bit_flip | qs[role:data] | p={data_p} |\n## states\n## state |enc> [initial]\n## state |done> [final]\n## events\n")
    hdr += "".join(f"- {e}\n" for e in sorted({t[1] for t in trans}))
    hdr += "\n## transitions\n| Source | Event | Guard | Target | Action |\n|---|---|---|---|---|\n"
    for s, e, tg, a in trans:
        hdr += f"| {s} | {e} | | {tg} | {a} |\n"
    hdr += "\n## actions\n| Name | Signature | Effect |\n|---|---|---|\n"
    for a, eff in acts.items():
        hdr += f"| {a} | (qs) -> qs | {eff} |\n"
    return _machine(hdr)


class TestResetParsing:
    def test_reset_parses_to_structured_effect(self):
        m = _machine(_MR)
        mr = next(a for a in m.actions if a.name == "mr")
        assert mr.reset == QEffectReset(qubit_idx=0)
        assert mr.mid_circuit_measure is not None  # measure + reset together
        assert mr.gate is None  # not a custom 'reset' gate


class TestResetClassifierVerifier:
    def test_resetting_machine_is_clifford(self):
        from q_orca.compiler.stabilizer import is_clifford
        ok, offenders = is_clifford(_machine(_MR))
        assert ok, offenders

    def test_reset_no_unverified_unitarity(self):
        from q_orca.verifier import verify, VerifyOptions
        result = verify(_machine(_MR), VerifyOptions())
        assert not any(e.code == "UNVERIFIED_UNITARITY" for e in result.errors)


class TestResetCompileToStim:
    def setup_method(self):
        pytest.importorskip("stim")

    def test_measure_reset_coalesces_to_mr(self):
        from q_orca.compiler.stabilizer import compile_to_stim
        circ = str(compile_to_stim(_machine(_MR)))
        assert "MR 0" in circ
        assert "\nM 0" not in circ  # not emitted as separate M

    def test_standalone_reset_emits_R(self):
        from q_orca.compiler.stabilizer import compile_to_stim
        src = _MR.replace("| mr | (qs) -> qs | measure(qs[0]) -> bits[0]; reset(qs[0]) |",
                          "| mr | (qs) -> qs | reset(qs[0]) |")
        circ = str(compile_to_stim(_machine(src)))
        assert "R 0" in circ and "MR" not in circ


class TestMultiRoundDetectors:
    def setup_method(self):
        pytest.importorskip("stim")

    def test_cross_round_detector_strings(self):
        from q_orca.compiler.stabilizer import compile_to_stim_with_detectors
        circ = str(compile_to_stim_with_detectors(_rep_machine(2)))
        assert "MR 3" in circ and "MR 4" in circ  # ancilla measured-and-reset
        # round 2's two stabilizer detectors each pair this round with the previous
        assert circ.count("DETECTOR rec[-1] rec[-3]") == 2

    def test_multiround_decodes(self):
        pytest.importorskip("pymatching")
        from q_orca.compiler.stabilizer import compile_to_stim_with_detectors
        from q_orca.evaluation.qec import decode_logical_error_rate
        # A 3-round code decodes to a sane logical error rate (cross-round
        # detectors well-formed; the DEM builds without error).
        ler = decode_logical_error_rate(compile_to_stim_with_detectors(_rep_machine(3)), shots=20000, seed=3)
        assert 0.0 <= ler < 0.05


_FLIP_RESET_MEASURE = """# machine M
## context
| Field | Type | Default |
|---|---|---|
| qubits | list<qubit> | [q0] |
| bits   | list<bit>   | [b0] |
## states
## state |s0> [initial]
## state |s1>
## state |s2>
## state |done> [final]
## events
- a
- b
- c
## transitions
| Source | Event | Guard | Target | Action |
|---|---|---|---|---|
| |s0> | a | | |s1> | flip |
| |s1> | b | | |s2> | rst |
| |s2> | c | | |done> | meas |
## actions
| Name | Signature | Effect |
|---|---|---|
| flip | (qs) -> qs | X(qs[0]) |
| rst  | (qs) -> qs | reset(qs[0]) |
| meas | (qs) -> qs | measure(qs[0]) -> bits[0] |
"""


class TestResetRuntime:
    def test_reset_clears_a_flipped_qubit(self):
        pytest.importorskip("qiskit")
        pytest.importorskip("qiskit_aer")
        from qiskit_aer import AerSimulator
        from q_orca.compiler.qiskit import build_circuit_for_iteration
        m = _machine(_FLIP_RESET_MEASURE)
        # X(q0); reset(q0); measure(q0) — the reset between the flip and the
        # measurement clears q0, so every shot measures 0.
        qc = build_circuit_for_iteration(m, {}, list(m.actions))
        assert any(instr.operation.name == "reset" for instr in qc.data)
        counts = AerSimulator().run(qc, shots=1000, seed_simulator=1).result().get_counts()
        assert set(counts) == {"0"}, f"reset should clear q0 → all-0, got {counts}"
