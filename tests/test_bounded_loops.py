"""Tests for bounded loop annotations (add-bounded-loop-annotation).

Covers parsing (`[loop <expr>]` / `[loop until: <pred>]` + `loop_done`/
`loop_back` tags), the three loop verifier rules, the `syndrome_completeness`
per-iteration tightening, loop-aware compilation (QASM `for`/`while`, Qiskit
`ForLoopOp`, `--unroll-loops`), the resource multiplier, the shipped Grover /
Simon's examples, and backward compatibility.
"""

from q_orca.ast import Invariant
from q_orca.parser.markdown_parser import parse_q_orca_markdown
from q_orca.verifier import verify
from q_orca.verifier.loops import check_loop_rules
from q_orca.verifier.roles import check_qubit_roles
from q_orca.verifier.resources import check_resource_invariants
from q_orca.compiler.qasm import compile_to_qasm
from q_orca.compiler.qiskit import compile_to_qiskit, QSimulationOptions
from q_orca.compiler.resources import estimate_resources, clear_resource_cache
from q_orca.compiler.loops import evaluate_loop_bound, analyze_loops


def _machine(body_action="gate", loop_anno="[loop 5]", extra_states="", extra_trans="",
             ctx_extra=""):
    src = f"""# machine T
## context
| Field | Type | Default |
|-------|------|---------|
| qubits | list<qubit> | [q0] |
| N | int | 16 |
| rank | int | 0 |
| n | int | 4 |
| err | float | 1.0 |
{ctx_extra}
## events
- step
- check
## state |s0> [initial]
> start
## state |amp> {loop_anno}
> body
{extra_states}
## state |done> [final]
> done
## transitions
| Source | Event | Guard | Target | Action |
|--------|-------|-------|--------|--------|
| |s0> | step | | |amp> | gate |
| |amp> | check | go | |amp> | {body_action}, loop_back |
| |amp> | check | stop | |done> | gate, loop_done |
{extra_trans}
## actions
| Name | Signature | Effect |
|------|-----------|--------|
| gate | (qs) -> qs | H(qs[0]) |
| meas | (qs) -> qs | measure(qs[0]) -> bits[0] |
"""
    r = parse_q_orca_markdown(src)
    assert not r.errors, r.errors
    return r.file.machines[0]


def _loop_codes(machine):
    return [(e.code, e.severity) for e in check_loop_rules(machine).errors]


def _resource_invariant(metric, op, value):
    return Invariant(kind="resource", qubits=[], op=op, value=value, metric=metric)


# ── Parsing ──────────────────────────────────────────────────────────────────

class TestParsing:
    def test_fixed_bound_parsed(self):
        m = _machine(loop_anno="[loop ceil(pi/4 * sqrt(N))]")
        amp = next(s for s in m.states if s.loop is not None)
        assert amp.loop.kind == "fixed"
        assert amp.loop.bound_expr == "ceil(pi/4 * sqrt(N))"

    def test_adaptive_predicate_parsed(self):
        m = _machine(loop_anno="[loop until: rank >= n - 1]")
        amp = next(s for s in m.states if s.loop is not None)
        assert amp.loop.kind == "adaptive"
        assert amp.loop.bound_expr == "rank >= n - 1"

    def test_loop_tags_recognized(self):
        m = _machine()
        back = next(t for t in m.transitions if t.loop_back)
        done = next(t for t in m.transitions if t.loop_done)
        assert back.action == "gate" and not back.loop_done
        assert done.action == "gate" and not done.loop_back

    def test_loop_composes_with_initial(self):
        src = """# machine T
## context
| Field | Type | Default |
|-------|------|---------|
| qubits | list<qubit> | [q0] |
## state |s0> [initial, loop 3]
## state |s1> [final]
## transitions
| Source | Event | Guard | Target | Action |
| |s0> | go | | |s0> | gate, loop_back |
| |s0> | fin | | |s1> | gate, loop_done |
## actions
| Name | Signature | Effect |
| gate | (qs) -> qs | H(qs[0]) |
"""
        r = parse_q_orca_markdown(src)
        s0 = r.file.machines[0].states[0]
        assert s0.is_initial and s0.loop is not None and s0.loop.kind == "fixed"

    def test_empty_loop_errors(self):
        src = """# machine T
## context
| Field | Type | Default |
| qubits | list<qubit> | [q0] |
## state |s0> [initial, loop]
## state |s1> [final]
## transitions
| Source | Event | Guard | Target | Action |
| |s0> | go | | |s1> | gate |
## actions
| Name | Signature | Effect |
| gate | (qs) -> qs | H(qs[0]) |
"""
        r = parse_q_orca_markdown(src)
        assert any("loop_malformed" in e for e in r.errors)


# ── Verifier rules ───────────────────────────────────────────────────────────

class TestVerifierRules:
    def test_fixed_unitary_body_clean(self):
        assert _loop_codes(_machine(body_action="gate", loop_anno="[loop 5]")) == []

    def test_measurement_in_fixed_body_rejected(self):
        codes = _loop_codes(_machine(body_action="meas", loop_anno="[loop 5]"))
        assert ("NON_UNITARY_ACTION", "error") in codes

    def test_measurement_in_adaptive_body_allowed(self):
        # Adaptive bodies measure to update the exit predicate — exempt.
        codes = _loop_codes(_machine(body_action="meas", loop_anno="[loop until: rank >= n - 1]"))
        assert not any(c == "NON_UNITARY_ACTION" for c, _ in codes)

    def test_adaptive_int_predicate_no_warning(self):
        assert _loop_codes(_machine(loop_anno="[loop until: rank >= n - 1]")) == []

    def test_adaptive_float_predicate_warns(self):
        codes = _loop_codes(_machine(loop_anno="[loop until: err < 0.01]"))
        assert ("LOOP_TERMINATION_UNCHECKED", "warning") in codes

    def test_two_loops_sharing_cycle_ambiguous(self):
        m = _machine(
            loop_anno="[loop 5]",
            extra_states="## state |amp2> [loop 3]\n> body2",
            extra_trans=(
                "| |amp> | check | x | |amp2> | gate |\n"
                "| |amp2> | check | y | |amp> | gate, loop_back |"
            ),
        )
        assert ("LOOP_AMBIGUOUS_BODY", "error") in _loop_codes(m)


# ── Compiler emission ────────────────────────────────────────────────────────

class TestCompiler:
    def test_fixed_emits_single_for_block_qasm(self):
        m = _machine(loop_anno="[loop 3]")
        q = compile_to_qasm(m)
        assert q.count("for k in [") == 1
        assert "for k in [0:2] {" in q

    def test_fixed_emits_for_loop_qiskit(self):
        m = _machine(loop_anno="[loop 3]")
        script = compile_to_qiskit(m, QSimulationOptions(skip_qutip=True))
        assert script.count("qc.for_loop(range(3))") == 1

    def test_adaptive_emits_while_block_qasm(self):
        m = _machine(loop_anno="[loop until: rank >= n - 1]")
        q = compile_to_qasm(m)
        # `until P` iterates while NOT P -> negated condition.
        assert "while (!(rank >= n - 1)) {" in q

    def test_unroll_loops_repeats_body_no_for_block(self):
        m = _machine(body_action="gate", loop_anno="[loop 3]")
        q = compile_to_qasm(m, unroll_loops=True)
        assert q.count("for k in [") == 0
        # body `gate` is H(q0): prefix(1) + 3 unrolled body + loop_done exit(1) = 5.
        assert q.count("h q[0];") == 5

    def test_unannotated_unchanged(self):
        # A machine with no [loop …] emits no sentinels and no loop blocks.
        m = _machine(loop_anno="")
        q = compile_to_qasm(m)
        assert "for k in [" not in q and "while (" not in q


# ── Resource estimation ──────────────────────────────────────────────────────

class TestResources:
    def _body12_machine(self, loop_anno):
        gates12 = "; ".join(["H(qs[0])"] * 12)
        src = f"""# machine R
## context
| Field | Type | Default |
|-------|------|---------|
| qubits | list<qubit> | [q0] |
| n | int | 4 |
| rank | int | 0 |
## events
- e
- c
## state |s0> [initial]
## state |body> {loop_anno}
## state |done> [final]
## transitions
| Source | Event | Guard | Target | Action |
| |s0> | e | | |body> | noop |
| |body> | c | go | |body> | work12, loop_back |
| |body> | c | stop | |done> | noop, loop_done |
## actions
| Name | Signature | Effect |
| noop | (qs) -> qs | |
| work12 | (qs) -> qs | {gates12} |
"""
        r = parse_q_orca_markdown(src)
        assert not r.errors, r.errors
        return r.file.machines[0]

    def test_fixed_loop_multiplies_body_cost(self):
        clear_resource_cache()
        m = self._body12_machine("[loop 100]")
        res = estimate_resources(m)
        # base body once (12) + 99 extra iterations × 12 = 1200.
        assert res["gate_count"] == 1200

    def test_adaptive_loop_reports_diagnostic(self):
        clear_resource_cache()
        m = self._body12_machine("[loop until: rank >= n - 1]")
        res = estimate_resources(m)
        assert res.get("adaptive_loops")

    def test_adaptive_loop_emits_resource_warning(self):
        clear_resource_cache()
        m = self._body12_machine("[loop until: rank >= n - 1]")
        # The resource-bound check emits the range warning when a resource
        # invariant is declared on a machine with an adaptive loop.
        m.invariants.append(_resource_invariant("gate_count", "le", 10_000))
        codes = [e.code for e in check_resource_invariants(m)]
        assert "RESOURCE_ESTIMATE_LOOP_ADAPTIVE" in codes


# ── Syndrome completeness tightening (D7) ────────────────────────────────────

class TestSyndromeTightening:
    def _syndrome_loop(self, measures_each_iter: bool):
        # q1 is a syndrome qubit acted on inside an annotated loop body.
        back_action = "measure_s, loop_back" if measures_each_iter else "act_s, loop_back"
        src = f"""# machine S
## context
| Field | Type | Default |
|-------|------|---------|
| qubits | list<qubit> | [q0:data, q1:syndrome] |
## events
- prep
- round
- fin
## state |s0> [initial]
## state |cycling> [loop 3]
## state |done> [final]
## transitions
| Source | Event | Guard | Target | Action |
| |s0> | prep | | |cycling> | entangle |
| |cycling> | round | go | |cycling> | {back_action} |
| |cycling> | fin | stop | |done> | noop, loop_done |
## actions
| Name | Signature | Effect |
| entangle | (qs) -> qs | CNOT(qs[0], qs[1]) |
| act_s | (qs) -> qs | CNOT(qs[0], qs[1]) |
| measure_s | (qs) -> qs | measure(qs[1]) -> bits[0] |
| noop | (qs) -> qs | |
"""
        r = parse_q_orca_markdown(src)
        assert not r.errors, r.errors
        return r.file.machines[0]

    def test_loop_body_without_per_iteration_measure_fails(self):
        codes = [e.code for e in check_qubit_roles(self._syndrome_loop(False)).errors]
        assert "SYNDROME_NOT_MEASURED" in codes

    def test_loop_body_with_per_iteration_measure_ok(self):
        codes = [e.code for e in check_qubit_roles(self._syndrome_loop(True)).errors]
        assert "SYNDROME_NOT_MEASURED" not in codes


# ── Bound evaluation ─────────────────────────────────────────────────────────

class TestBoundEvaluation:
    def test_ceil_pi_sqrt(self):
        m = _machine(loop_anno="[loop ceil(pi/4 * sqrt(N))]")  # N=16 -> ceil(pi) = 4
        info = analyze_loops(m)["|amp>"]
        assert info.bound == 4

    def test_literal_and_field(self):
        assert evaluate_loop_bound(_machine(), "5") == 5
        assert evaluate_loop_bound(_machine(), "N") == 16  # N default 16


# ── Shipped examples ─────────────────────────────────────────────────────────

class TestExamples:
    def test_grover_verifies_and_has_one_for_block(self):
        r = parse_q_orca_markdown(open("examples/grover-search.q.orca.md").read())
        assert not r.errors, r.errors
        m = r.file.machines[0]
        res = verify(m, file=r.file)
        assert res.valid, [e.code for e in res.errors if e.severity == "error"]
        assert compile_to_qasm(m).count("for k in [") == 1

    def test_simons_verifies_and_has_while_block(self):
        r = parse_q_orca_markdown(open("examples/simons-algorithm.q.orca.md").read())
        assert not r.errors, r.errors
        m = r.file.machines[0]
        res = verify(m, file=r.file)
        assert res.valid, [e.code for e in res.errors if e.severity == "error"]
        assert compile_to_qasm(m).count("while (") == 1
