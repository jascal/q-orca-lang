## MODIFIED Requirements

### Requirement: Loop Compilation

The compiler SHALL emit a real control-flow loop for a `[loop …]`-annotated body instead of unrolling it. For a fixed bound `N`: QASM 3 `for k in [0:N-1] { … }` and Qiskit `ForLoopOp`. For an adaptive predicate `P`: QASM 3 emits `while (!(P)) { … }` — a `[loop until: P]` iterates *while `P` is not yet satisfied*, so the QASM `while` condition is the negation of the predicate. A `--unroll-loops` flag SHALL retain the previous N-times-unrolled emission.

Adaptive predicates are host-computed (e.g. Simon's `rank` over GF(2)) and are not expressible over QASM classical registers, so the Qiskit backend emits the adaptive body **once** under a structured host-driven marker rather than a literal `WhileLoopOp`; faithful adaptive iteration is host-driven.

The fixed bound `N` is the compile-time evaluation of the `[loop <expr>]` expression against the machine's context defaults. Under `--qasm-version=2` (no native loops) the loop is unrolled with a `QASM2_DOWNGRADE_LOOP` warning. Under a stabilizer/Stim backend (no `for`) the loop is silently unrolled with an info-level `LOOP_UNROLLED_FOR_BACKEND` diagnostic. The Mermaid renderer SHALL render a loop-annotated state with a back-edge label — `×N` for fixed, a condensed predicate (≤ 30 chars) for adaptive — rather than an unrolled linear chain.

#### Scenario: Fixed loop emits a single for block

- **WHEN** a machine with `## context | N | int | 16 |` has `## state |amplified> [loop ceil(pi/4 * sqrt(N))]` and is compiled to QASM 3
- **THEN** the output contains exactly one `for k in [0:2]` block wrapping the body (not the body repeated three times)

#### Scenario: Adaptive loop emits a negated while block

- **WHEN** a `[loop until: P]` machine is compiled to QASM 3
- **THEN** the output contains a `while (!(P)) { … }` block over the body (iterate while the predicate is not yet satisfied)

#### Scenario: --unroll-loops reproduces prior emission

- **WHEN** the same fixed-loop machine is compiled with `--unroll-loops`
- **THEN** the body is emitted N times with no `for` block (the pre-change shape)
