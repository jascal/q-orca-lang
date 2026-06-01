## ADDED Requirements

### Requirement: Loop Compilation

The compiler SHALL emit a real control-flow loop for a `[loop …]`-annotated body instead of unrolling it: QASM 3 `for k in [0:N-1] { … }` and Qiskit `ForLoopOp` for a fixed bound `N`, and QASM 3 `while (P) { … }` and Qiskit `WhileLoopOp` for an adaptive predicate `P`. A `--unroll-loops` flag SHALL retain the previous N-times-unrolled emission.

The fixed bound `N` is the compile-time evaluation of the `[loop <expr>]` expression against the machine's context defaults. Under `--qasm-version=2` (no native loops) the loop is unrolled with a `QASM2_DOWNGRADE_LOOP` warning. Under a stabilizer/Stim backend (no `for`) the loop is silently unrolled with an info-level `LOOP_UNROLLED_FOR_BACKEND` diagnostic. The Mermaid renderer SHALL render a loop-annotated state with a back-edge label — `×N` for fixed, a condensed predicate (≤ 30 chars) for adaptive — rather than an unrolled linear chain.

#### Scenario: Fixed loop emits a single for block

- **WHEN** a machine with `## context | N | int | 16 |` has `## state |amplified> [loop ceil(pi/4 * sqrt(N))]` and is compiled to QASM 3
- **THEN** the output contains exactly one `for k in [0:2]` block wrapping the body (not the body repeated three times)

#### Scenario: Adaptive loop emits a while block

- **WHEN** a `[loop until: P]` machine is compiled to QASM 3
- **THEN** the output contains a `while (...)` block over the body

#### Scenario: --unroll-loops reproduces prior emission

- **WHEN** the same fixed-loop machine is compiled with `--unroll-loops`
- **THEN** the body is emitted N times with no `for` block (the pre-change shape)

### Requirement: Loop-Aware Resource Estimation

The compiler's resource estimation SHALL multiply a fixed `[loop N]` body's per-action cost contributions by `N` once (so `gate_count`/`cx_count`/`depth` are faithful rather than the body's single-iteration cost), and SHALL report an adaptive loop's cost as the range `[body_cost, body_cost × MAX_LOOP_BOUND]` (default `MAX_LOOP_BOUND = 1000`) with a `RESOURCE_ESTIMATE_LOOP_ADAPTIVE` diagnostic.

#### Scenario: Fixed loop multiplies the body cost

- **WHEN** a 4-state body annotated `[loop 100]` has a per-iteration `gate_count` of 12
- **THEN** the reported `gate_count` is 1200 (and the emitted code is a single `ForLoopOp`, so estimate and emission agree)

#### Scenario: Adaptive loop reports a range

- **WHEN** a `[loop until: P]` body has per-iteration `gate_count` 12
- **THEN** the resource report gives a range up to `12 × MAX_LOOP_BOUND` and emits `RESOURCE_ESTIMATE_LOOP_ADAPTIVE`
