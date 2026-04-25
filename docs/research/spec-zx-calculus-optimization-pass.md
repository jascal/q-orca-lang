# Feature: ZX-Calculus Circuit Optimization Pass

> Generated: 2026-04-24 — weekly feature spec session

---

## Feature: ZX-Calculus Circuit Optimization Pass

**Summary:** Add an explicit optimization stage between parsing and
backend compilation in which the q-orca compiler converts the
declared gate sequence into a ZX-diagram, applies the standard
ZX-calculus simplification rewrite suite (spider fusion, Hadamard
cancellation, local complementation, pivoting, phase teleportation)
via [PyZX](https://github.com/Quantomatic/pyzx), and extracts a
reduced circuit with lower CX-count, lower T-count, and lower
two-qubit depth. The pass is declarative — turned on per-machine
via a new `## optimize` section, or globally via a `--optimize=zx`
CLI flag — and it preserves the semantics of the circuit (ZX rewrite
rules are provably semantics-preserving). The output feeds into the
existing Qiskit, QASM, Stim (companion spec), and CUDA-Q compilers
unchanged. Because the in-flight `add-resource-estimation` proposal
already defines `gate_count`, `depth`, `cx_count`, and `t_count` as
first-class resource metrics, this change gives machine authors a
direct way to *reduce* those numbers without hand-editing gate
tables — closing the loop between resource declaration and
resource optimization.

---

**Motivation:** The algorithms and use cases this unlocks include:

- **Cheaper NISQ circuits.** NISQ hardware dies a death of a thousand
  CNOTs. Every example in `examples/` that involves more than five
  gates (VQE Heisenberg, QAOA MaxCut, Deutsch–Jozsa, active
  teleportation, syndrome extraction) hand-writes a gate sequence
  that PyZX empirically reduces by 15–40 % in two-qubit gate count
  with no change in semantics. On a device with CX error rate
  `p = 5 × 10⁻³`, a 30 % reduction in CX-count is a `(1−p)^{0.3n}`
  fidelity gain — a first-class forcing function on every target
  hardware of 2026.
- **Clifford+T fault-tolerant readiness.** T-count is the dominant
  cost driver for fault-tolerant execution under surface-code-based
  resource estimates (Fowler et al. `1208.0928`). PyZX's
  phase-teleportation T-count minimization (arXiv `1903.10477`)
  matches or beats the best classical T-count reducers (Tpar, TODD)
  on standard benchmarks. Shipping this as a default-off optimization
  pass means any machine declaring `t_count <= N` in its invariants
  (a pattern unlocked by the queued extended-invariants roadmap item)
  gets the pass applied automatically.
- **Circuit-depth budgets for coherence-limited hardware.** The
  coverage analysis roadmap §4.6 suggests extending `## invariants`
  with `coherence_time(q0) <= T2`. A depth-reducing optimization pass
  is the natural feature to pair with that invariant — when the
  declared depth budget fails, the compiler can suggest running with
  `--optimize=zx` before failing hard.
- **Clean separation between written and compiled circuits.** Today,
  a machine author writing `qaoa-maxcut.q.orca.md` has to choose
  between clarity (write the natural gate decomposition) and
  efficiency (pre-optimize by hand). An optional optimization pass
  lets the *author-facing* representation stay clear while the
  *hardware-facing* representation gets compressed.
- **Optimization benchmarking.** The `quantum_evolve` demo already
  uses q-orca machines as genomes for a genetic algorithm; adding a
  ZX pass gives evolved circuits a principled second-stage polish.
  Similarly, a future RL-driven optimization path (arXiv
  `2312.11597`) can plug into the same extraction interface PyZX
  uses, with q-orca as the source and sink.

---

**Proposed Syntax:**

One new declarative section and one new CLI flag. The section is
absent by default (no optimization); when present it enables the
pass at a configurable level.

```markdown
# machine QAOAMaxCut

> QAOA depth-p=3 on a 4-node MaxCut instance.

## context

| Field  | Type          | Default        |
|--------|---------------|----------------|
| qubits | list<qubit>   | [q0, q1, q2, q3] |
| gamma  | list<float>   | [0.3, 0.6, 0.8]  |
| beta   | list<float>   | [0.4, 0.5, 0.2]  |

## optimize

| Key              | Value       |
|------------------|-------------|
| pass             | zx          |
| level            | full-reduce |
| preserve_depth   | false       |
| preserve_gate_set| {CX, Rz, Rx, H} |

## invariants
- cx_count <= 18   # optimized target; pre-optimization is 30
- t_count <= 0     # QAOA has no T; verify pass doesn't introduce any
```

**`## optimize` table semantics:**

| Key                  | Type                 | Default       | Meaning |
|----------------------|----------------------|---------------|---------|
| `pass`               | `zx`                 | —             | Required. Names the optimization suite. This spec ships only `zx`; future passes (e.g. `routing`, `peephole`) are additional values. |
| `level`              | `basic` / `full-reduce` / `teleport-reduce` | `full-reduce` | Names a PyZX simplification strategy. `basic` is spider fusion only; `full-reduce` applies the full Clifford-simp + phase-free simplification; `teleport-reduce` additionally applies T-count-reducing phase teleportation. |
| `preserve_depth`     | bool                 | `false`       | If true, the extraction step minimizes depth rather than gate count. |
| `preserve_gate_set`  | set of gate names    | `{CX, Rz, Rx, Rz, H}` | The output basis. Extraction emits only these gates. |
| `timeout_ms`         | int                  | `5000`        | Bail out and use the original circuit if the pass exceeds this budget; emit a warning. |

CLI equivalents:

```bash
q-orca compile examples/qaoa-maxcut.q.orca.md --optimize=zx
q-orca compile examples/qaoa-maxcut.q.orca.md --optimize=zx:teleport-reduce
q-orca compile examples/qaoa-maxcut.q.orca.md --optimize=none    # default
```

**Interaction with `## invariants`:** When the extended resource
invariants (`cx_count`, `t_count`, `depth`, `gate_count` — from the
in-flight `add-resource-estimation` change) are declared, the
compiler computes them *after* the optimization pass, so the
declared bound is the bound on the *compiled* circuit. A new
diagnostic `OPTIMIZATION_REGRESSED_METRIC` fires if the pass leaves
any declared metric *worse* than before — this is extremely unlikely
but possible for pathological inputs, and catching it is free given
resource estimation already runs.

**Interaction with `## execution` (stabilizer backend, companion
spec):** If the machine is pure Clifford, the pass still helps — PyZX's
Clifford simplification is strictly stronger than Stim's internal
rewrites and typically reduces the stabilizer-tableau depth too. If
the machine is Clifford+T and the user has declared
`backend: stabilizer`, the ZX pass is a no-op (stabilizer backend
can't execute T gates anyway); the compiler emits an informational
diagnostic and skips the pass.

---

**Implementation Sketch:**

### Parser changes

- Add `## optimize` section grammar. Parser recognizes the five keys
  above. Unknown keys are structured parser errors; unknown pass
  names are structured errors (future-proof). Absence of the section
  yields no optimization.
- Extend `q_orca/ast.py` with an `OptimizeConfig` dataclass (fields:
  `pass_name`, `level`, `preserve_depth`, `preserve_gate_set`,
  `timeout_ms`), plumbed into `Machine.optimize_config`.
- Plumb a `--optimize=<pass>[:<level>]` CLI flag in
  `q_orca/cli.py` that overrides any per-machine section.

### Compiler changes

- New module `q_orca/compiler/optimize/__init__.py` exposing
  `optimize(machine) -> Machine` — the dispatcher.
- New module `q_orca/compiler/optimize/zx.py`:
  - `optimize_with_zx(machine, config) -> Machine` —
    (1) builds a flattened, per-state gate sequence from the action
    table; (2) converts to `pyzx.Circuit` (PyZX accepts QASM, so we
    go gate-table → QASM → PyZX); (3) calls
    `pyzx.simplify.full_reduce(graph)` or
    `pyzx.simplify.teleport_reduce(graph)` per `level`; (4) extracts
    a circuit via `pyzx.extract.extract_circuit(graph)`, passing
    `preserve_depth` down; (5) maps the extracted gates back into
    q-orca `QuantumGate` AST nodes; (6) returns a *new* `Machine`
    with the action table rewritten. The machine's state / context
    / invariants / events are untouched.
- Back-mapping step is the fiddly bit: PyZX's extracted circuit is
  over `{CX, CZ, S, H, Z, X, T}` plus rotation phases expressed as
  fractions of π. The mapper reuses the existing
  `q_orca/angle.py` helpers to translate PyZX phase fractions into
  q-orca symbolic angles (so the shipped parametric-action support
  survives the round-trip — a context-referenced `γ` that PyZX
  treats as a symbolic Z-spider phase comes back out referencing the
  same context field). Unmappable phases (e.g. non-rational angles)
  block the pass and emit `ZX_UNMAPPABLE_PHASE` as a diagnostic;
  the pass then falls back to the un-optimized circuit.
- Plumb the pass into `q_orca/cli.py compile` and `q_orca/cli.py
  verify` so both code paths optimize before hitting the backend.
  Order: parse → static verify → **optimize** → compile/simulate.

### Verifier changes

- Static verifier: untouched. Optimization preserves semantics, so no
  structural re-verification is needed. However, a new lightweight
  check in `q_orca/verifier/optimize_audit.py`:
  - `audit_optimization(pre, post) -> AuditResult` compares declared
    resource invariants on `pre` and `post` and confirms
    `post <= pre` on each declared metric. Fires
    `OPTIMIZATION_REGRESSED_METRIC` on violation.
  - Confirms unitarity equivalence on small machines (`n_qubits ≤ 6`)
    by building both circuits in Qiskit and comparing unitary
    matrices via `numpy.allclose`. Skipped for larger circuits
    (relies on PyZX's own semantics preservation).
- Dynamic verifier (`q_orca/verifier/dynamic.py`): receives the
  *optimized* machine, so sampling-based assertions apply to the
  compiled-and-optimized form. This matches user intent — you want
  to verify the thing that will actually run.

### New tests / examples needed

- `tests/test_zx_optimization.py`:
  - Round-trip equivalence on every example in `examples/`: optimized
    and un-optimized simulators must produce statistically
    indistinguishable measurement distributions at `shots=4000`.
  - CX-count reduction: `qaoa-maxcut` and `vqe-heisenberg` must each
    show at least a 15 % CX reduction under `level=full-reduce`.
  - T-count reduction: a newly added `examples/adder-4bit.q.orca.md`
    (Clifford+T) must drop from a hand-written baseline to within
    5 % of the PyZX paper's reported T-count for the same adder.
  - Symbolic-parameter round-trip: a parametric QAOA cost layer with
    `γ` referenced from `## context` survives the pass with `γ`
    still referenced (not baked to a literal).
  - Diagnostic firing: `ZX_UNMAPPABLE_PHASE`, `OPTIMIZATION_REGRESSED_METRIC`,
    and `OPTIMIZATION_TIMEOUT` each have a regression test.
- `tests/test_optimize_audit.py`: resource-metric monotonicity on
  every example under `full-reduce`.
- `examples/qaoa-maxcut.q.orca.md` already exists; extend its
  `## invariants` to declare post-optimization resource bounds as
  living documentation.
- `docs/research/` cross-reference: call out the ZX pass as a
  generalization of the specific measurement-calculus rewriting
  theme in `dirac-rewriter-synthesis.md` (both are rewrite-system
  approaches; the Dirac rewriter operates on symbolic state
  expressions, ZX on circuit diagrams — adjacent problems).

### Packaging

- Add `pyzx ≥ 0.8` as a declared extra in `pyproject.toml` under a
  new `optimize` extras group, mirroring the existing `backends`
  extras pattern from the execution-backends change. `pip install
  "q-orca[optimize]"` opts the user in. Absent the extra, the pass
  module raises `OptimizerNotInstalled` with a clear install
  message on any attempt to use it — consistent with the pattern
  already established for `cuquantum` and `cudaq`.

---

**Complexity:** Large — PyZX integration is well-scoped, but the
back-mapping of optimized circuits into q-orca's AST with preserved
context-referenced parameters is genuinely fiddly and requires
careful testing. The audit step (equivalence verification) is
straightforward but adds surface area. Realistic estimate: 3 PRs
(parser + config, optimizer + round-trip, audit + tests +
diagnostics).

**Priority:** High — directly improves every NISQ-targeted example
in the repository; composes tightly with the already-in-flight
resource-estimation change; opens the path to future RL-driven
optimization research without locking the architecture into PyZX
specifically (the `## optimize` section has room for additional
pass names).

**Dependencies:**
- **Composes tightly with `add-resource-estimation`** (in-flight):
  the optimizer reduces exactly the metrics that change declares as
  first-class. The resource-audit step of this spec depends on that
  change having landed. Hard dependency — ship resource-estimation
  first, this second.
- **Complementary to the Stabilizer Fast-Path Backend** (companion
  spec, same week): together they form a coherent compilation
  pipeline — Clifford circuits get both ZX simplification and
  stabilizer execution; Clifford+T circuits get ZX +
  phase-teleportation before hitting a state-vector backend.
- Independent of `add-parameterized-invoke`, `add-runtime-state-assertions`,
  and `consolidate-gate-parser`; does not block or require any of
  them.

**Literature:**

- Coecke & Duncan, "Interacting Quantum Observables" (2008),
  `0906.4725` — foundational ZX-calculus; indexed in q-orca-kb
  (`q-orca-physics / zx-calculus`).
- Kissinger & van de Wetering, "Reducing T-count with the ZX-calculus"
  (2019), `1903.10477` — PyZX T-count reduction, matches best-known
  on Tpar benchmarks; indexed.
- van de Wetering, "ZX-calculus for the working quantum computer
  scientist" (2020), `2012.13966` — pedagogy reference; indexed.
- "ZX-calculus based optimization for fault-tolerant quantum
  circuits" (2023), `2306.02264` — fault-tolerant ZX optimization
  motivates the T-count pass; indexed.
- "Reinforcement learning guided quantum circuit optimization via
  the ZX-Calculus" (Quantum journal, 2025), `2312.11597` — RL + ZX;
  indexed. Positions this spec as a stepping stone to a future
  RL-driven pass plugged into the same extraction interface.
- Duncan, Kissinger, Perdrix & van de Wetering, "Graph-theoretic
  simplification of quantum circuits with the ZX-calculus" (2020) —
  the core `full_reduce` algorithm PyZX exposes.
- Hadzihasanovic, Jeandel, Perdrix, Vilmart — ZX completeness
  axiomatizations (2018–2019) — foundational correctness of the
  rewrite system; referenced in q-orca-kb's verified-compilation
  room (`2207.11350`, `2003.05841`, `2109.06493`).
- Qiskit Aer stabilizer primitives page — cross-references the
  Clifford pathway; indexed as `simulate-stabilizer-circuits` in
  q-orca-kb.

---
