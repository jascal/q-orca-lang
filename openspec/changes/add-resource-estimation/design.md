## Context

Q-Orca's static verifier today checks structural quantum properties
(unitarity, no-cloning, completeness, determinism) but says nothing
about the *cost* of the compiled circuit. The Qiskit compiler
(`q_orca/compiler/qiskit.py`) already builds a `QuantumCircuit`; the
ingredient missing for resource estimation is a small accounting
layer that runs `transpile()` over that circuit with carefully chosen
basis-gate sets. Five quantities cover the standard NISQ + FTQC
evaluation matrix: total gate count, parallelized depth, two-qubit
(CX) count, T-count, and logical qubit count.

The accounting itself is mechanical. The interesting design choices
are: (1) what surface syntax exposes which numbers to compute, (2)
how those numbers compose with the existing `## invariants` grammar,
and (3) where the resource-bound check lives in the verifier
pipeline.

## Goals / Non-Goals

**Goals:**

- Let users declare which resource metrics they care about per
  machine via a `## resources` table.
- Let the same five identifiers appear as bounds in `## invariants`,
  turning resource regressions into verification errors.
- Reuse Qiskit's `transpile()` as the canonical accounting backend
  so we inherit its correctness guarantees and gate-decomposition
  rules.
- Expose `estimate_resources(machine)` and
  `compile_with_resources(machine, options)` so external tools (the
  cuQuantum / CUDA-Q execution backends, future cost-aware planners)
  can read the same dict.
- Print a one-screen resource report alongside compilation when
  any resource section is present.

**Non-Goals:**

- Symbolic / parameterized resource estimates. Metrics are computed
  against the default angle values declared in `## context`. A future
  change can add worst-case-over-domain reporting once a parameter-
  sweep API exists.
- Physical-qubit accounting, FTQC overhead, code-distance
  calculation. These need a `## error_correction` section that
  doesn't exist yet.
- Symbolic-RHS invariants (`cx_count <= 4 * p + 2`). The current
  `## invariants` grammar accepts integer literals; we don't widen
  it here.
- A new transpiler pass. We use Qiskit's `optimization_level=1` as a
  fixed accounting choice — anything more would couple the metric to
  optimization tuning.

## Decisions

### Decision 1 — Use Qiskit's `transpile()` as the canonical accounting backend

The compile pipeline already constructs the same `QuantumCircuit`
that Qiskit would transpile. Calling `transpile(qc, basis_gates=...,
optimization_level=1)` and reading `count_ops()` and `depth()` is
~10 LOC per metric, deterministic given fixed inputs, and reuses
Qiskit's well-tested decomposition rules.

Alternative considered: hand-rolled gate counter walking
`QMachine.transitions`. Rejected because (a) decomposition rules
(e.g. how `CCX` decomposes into Clifford+T) belong with Qiskit, not
with us; (b) two backends counting independently invites drift
exactly like the three-site effect-parser problem this codebase just
finished cleaning up; (c) `depth()` is non-trivial to compute outside
a circuit IR and we'd be re-implementing Qiskit poorly.

The trade-off: we depend on Qiskit's optimization-level-1 pass being
stable across versions. We pin the Qiskit version in
`pyproject.toml` and add a regression test that asserts the bundled
examples' resource numbers are unchanged. A future Qiskit upgrade
that shifts the count requires updating the pinned numbers in the
examples — a normal version-bump cost.

### Decision 2 — Default to all five metrics when `## resources` is absent

The simpler alternative is to skip the report entirely when the
section is absent. That's bad UX: most users won't know to ask for
the report until they discover it exists. Defaulting to all five
metrics surfaces the numbers in every compile and lets users opt
*out* (omit the section, no resource invariants — but still get the
report) or *in* with bounds (declare invariants and gain
verification).

### Decision 3 — Resource invariants share the existing `Invariant` AST

We add `kind="resource"` and a `metric: str` field. We do *not*
introduce a separate `QResourceAssertion` AST node. Reasons: (a)
the existing `Invariant` already has `op` and `value` fields; (b) the
verifier loop already walks `machine.invariants`; (c) keeping all
invariants in one shape simplifies any future "list all invariants"
tooling. The `kind` discriminator is the existing extension point —
`entanglement` and `schmidt_rank` are already two values it takes.

Alternative considered: a top-level `QMachine.resource_assertions`
list parallel to `invariants`. Rejected because it splits "things
that must hold" into two sites the verifier has to enumerate
independently, which is the seed of the same drift class we just
consolidated for the gate parser.

### Decision 4 — Memoize `estimate_resources(machine)` per machine

Building a `QuantumCircuit` and running four `transpile()` calls
costs tens to hundreds of milliseconds for a moderate machine. The
verifier may evaluate multiple resource invariants over the same
machine, and the compiler may want the report alongside the
artifact. We memoize per `id(machine)` so the cost is paid once.

Memoization is local to a verify-or-compile invocation; we do not
attempt to cache across invocations. Cache keys would have to fold
in every input that affects the circuit (context defaults,
parametric expansion results) and the saving doesn't justify that
complexity.

### Decision 5 — Optimization level 1, fixed

`optimization_level=1` is Qiskit's default light-touch pass: it
collapses obvious redundancies (gate cancellation, single-qubit
chain merging) without aggressive resynthesis. It produces stable
counts across small input perturbations and matches what most users
mean when they say "the circuit's depth." We expose no knob.

A user who wants raw pre-optimization counts can read
`gate_count` (which we leave unoptimized; see Decision 6). A user
who wants aggressive-optimization counts is, today, expected to feed
the QASM into their preferred external tool.

### Decision 6 — `gate_count` is the un-optimized count

`gate_count` is the sum of gate effects in all reachable transition
actions, computed by a static walk of the circuit *before*
`transpile()`. The other four metrics are post-transpile. Reasoning:
`gate_count` is the user's mental model of "how many things did I
write," and applying optimization to it would surprise them. The
post-transpile counts (`depth`, `cx_count`, `t_count`) are
inherently optimization-aware because the basis decomposition is
itself an optimization-style transform.

### Decision 7 — `RESOURCE_BOUND_INDETERMINATE` for unknown loop bounds

The queued `[loop N]` annotation feature can have a runtime-unknown
`N`. When a metric depends on the unrolled body and the body's loop
count is unknown, the metric is reported as `unknown` and any
invariant referencing it emits `RESOURCE_BOUND_INDETERMINATE` as a
*warning*, not an error. The intent: a runtime-bound loop is a
deliberate user choice, and the verifier shouldn't reject it just
because we can't prove a bound.

This decision lives here in the design even though the loop feature
isn't shipped yet, so the error vocabulary is forward-compatible.
For now, `RESOURCE_BOUND_INDETERMINATE` is unreachable from any
shipped surface; we add it to the diagnostic table but no code path
emits it.

## Risks / Trade-offs

- **Risk:** Qiskit version churn changes optimization behavior and
  silently shifts counts on bundled examples.
  **Mitigation:** pin Qiskit minor version; tests assert exact
  counts on `bell-entangler` (2 gates, depth 2, 1 CX, 0 T, 2 qubits)
  and `ghz-state` (3 gates, depth 3, 2 CX, 0 T, 3 qubits). A failing
  pin upgrade surfaces the change as a test failure with the new
  numbers in the diff, which the user updates intentionally.

- **Risk:** Computing four `transpile()` passes per compile is slow.
  **Mitigation:** memoize per machine; the only time we compute is
  when the user has resource invariants or asks for the report. Bell
  pair takes ~50 ms; QAOA-3 takes ~150 ms; this is well under any
  human attention threshold and well under typical pytest test
  duration.

- **Risk:** A user expects `cx_count` to mean "count of `CNOT`
  effects in the source," not "post-decomposition CX count from a
  `u3, cx` basis transpile."
  **Mitigation:** documentation. The `Notes` column of the
  `## resources` table is the right place to surface this; the
  default text for `cx_count` says "post-decomposition CX count
  (NISQ-relevant)."

- **Risk:** The verifier emits a `RESOURCE_BOUND_EXCEEDED` for a
  rotation gate that the user expected to optimize away. Example: a
  `Ry(qs[0], 0.0)` is a no-op but still counts.
  **Mitigation:** `optimization_level=1` collapses this. If the
  user writes `Ry(qs[0], theta)` and sets `theta=0.0` in `## context`
  defaults, the transpile pass should fold it to identity. Document
  this in `docs/language/resources.md`.

- **Risk:** The `## resources` section format invites bikeshedding
  ("why three columns? why is `Notes` optional?").
  **Mitigation:** the table format mirrors `## context` — same
  columns, same parsing rules, no novel invention. The `Notes`
  column is purely informational and ignored by the parser.

## Open Questions

None for v1. The forward-compatibility hooks
(`RESOURCE_BOUND_INDETERMINATE`, optional `Notes` column) cover the
known-shape extensions (loop bounds, future metric kinds).
