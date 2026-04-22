## Why

`add-classical-context-updates` (archived) landed the grammar, AST,
parser, verifier, and compiler *annotations* for context-update
effects — `if bits[0] == 1: theta[0] -= eta`-style mutations on
numeric context fields. It explicitly parked the one thing that
would make those effects observable: the shot-to-shot runtime that
actually *executes* the mutation. Today the Qiskit compiler emits
the effect as a Python comment with a banner
(`# NOTE: context-update actions are annotations only; shot-to-shot
execution not yet implemented.`), and every simulator run throws
the mutation away.

This is the blocker the Quantum Predictive Coder research doc
identified. The minimal QPC example on branch
`quantum-predictive-coder-minimal` verifies VALID but stops at one
measurement — the full `gradient_step` / `reset_data_and_ancilla`
loop from the research spec cannot be demonstrated until the runtime
interprets context updates. Section 7 of the archived change's
tasks.md parks this exact follow-up:

> **Parked**: open a follow-up OpenSpec proposal `run-context-updates`
> that designs the shot-to-shot runtime execution of context updates
> (simulator loop, backend-agnostic mutation semantics). Out of
> scope for this change.

Two other currently-specced changes share the same pressure:
`add-runtime-state-assertions` wants statistical sampling across
multiple executions, and `add-parameterized-invoke` will need a
real runtime walker once child-machine dispatch lands. A concrete
runtime story unblocks all three.

## What Changes

- **Runtime — iterative executor.** Introduce a new driver in
  `q_orca/runtime/python.py` (or a new `q_orca/runtime/iterative.py`
  — design will decide) that walks the machine's transition graph
  at *execution time* rather than compile time. For each shot it
  follows transitions from the initial state, evaluates guards
  against the current context, binds parametric-gate angles from
  the current context, runs the quantum sub-circuit between context
  updates, reads measurement outcomes into `bits`, applies the
  context-update effect, and re-enters the loop — until it reaches
  a final state or hits a safety-net iteration ceiling.

- **Activation rule.** The iterative runtime SHALL be used
  automatically for any machine whose actions include at least one
  `QEffectContextUpdate`. Machines without context-update actions
  keep the existing "flat-circuit + shots" fast path unchanged. This
  is a zero-cost change for every shipped example.

- **Guard evaluator.** Add `q_orca/runtime/guards.py` that evaluates
  the existing guard expression grammar (`ctx.field <op> literal`,
  boolean combinations, `bits[i] == v`) against a mutable context
  record at runtime. The grammar is already parsed; this is the
  interpreter side. Used by the iterative runtime *and* available
  to `add-runtime-state-assertions` and `add-parameterized-invoke`
  as a shared primitive.

- **Context-mutation interpreter.** Add
  `q_orca/runtime/context_ops.py` that interprets a
  `QEffectContextUpdate` AST node against a Python context record:
  evaluates the bit condition, picks the then/else branch, applies
  each `QContextMutation`. Pure Python, no Qiskit involvement.

- **Qiskit backend — per-iteration circuit assembly.** The
  iterative runtime builds one Qiskit `QuantumCircuit` per iteration
  at the currently-resolved context values. v1 recompiles from the
  AST each iteration (simplest correct shape). `Parameter`-object
  reuse for angle rebinding is an optimization tracked as a
  follow-up in `## Open Questions` — v1 prioritizes correctness over
  throughput.

- **Shot accounting — inner vs. outer.** New
  `QIterativeSimulationOptions.inner_shots` governs how many shots
  are averaged at *each* iteration's measurement (for stochastic
  gradient-style updates that average a bit-expectation); the
  default is 1 (single-shot feedback, matches the QPC's
  binary-Kalman gradient step). Outer iteration count is bounded by
  the machine's own guards; runtime enforces a hard
  `iteration_ceiling` (default 10_000) as a safety net against
  runaway loops.

- **Result shape.** Introduce `QIterativeSimulationResult` with
  per-iteration trace entries (iteration index, source→target
  transition, measurement outcome, context snapshot). The existing
  `QSimulationResult` return shape is preserved for non-iterative
  machines. `simulate_machine(...)` dispatches on machine shape and
  returns the appropriate type.

- **Compiler banner update.** When a machine has context-update
  actions AND the Qiskit compiler target is paired with the new
  runtime (default going forward), the "not executed in v1" banner
  SHALL be replaced with an *executed-via-iterative-runtime* marker.
  The QASM and Mermaid emitters retain the annotation-only banner
  since they lack a runtime; CUDA-Q / cuQuantum are explicitly out
  of scope for v1 and keep the annotation-only banner with a
  backend-specific note.

- **Verifier — termination hint (warning).** Add a warning-severity
  check: if a machine has context-update actions but no guard on
  any path to a final state constrains loop depth (e.g., no
  `ctx.iteration < max_iter` style guard), emit
  `UNBOUNDED_CONTEXT_LOOP` warning flagging that only the runtime's
  hard `iteration_ceiling` will stop execution. Error severity is
  **warning**, not error — a user may legitimately want to lean on
  the ceiling.

- **Minimal end-to-end demo.** Extend
  `examples/predictive-coder-minimal.q.orca.md` (or add
  `examples/predictive-coder-learning.q.orca.md` — design decides)
  with the full QPC learning loop from the research doc and wire it
  into the CI `verify-examples.yml` matrix. Convergence plotting is
  a demo-level concern, tracked as an optional follow-up and not in
  this change's scope.

- **Docs.** Update the "## Roadmap → Recently shipped" section of
  `README.md` on landing. Add a back-reference in
  `docs/research/spec-quantum-predictive-coder.md` §Next concrete
  steps marking steps 4 and 6 as now unblocked.

## Capabilities

### New Capabilities
None. This is a runtime extension that lives inside the existing
`compiler` capability (which today already hosts the Python runtime
under `q_orca/runtime/`). No new top-level capability file.

### Modified Capabilities

- **`compiler`**: a new requirement covers iterative runtime
  execution for machines with context-update actions. Existing
  requirements for the three backend targets and shared gate-kind
  coverage are unchanged. The "Context-Update Annotation Emission"
  requirement (added by `add-classical-context-updates`) is
  *modified* to carve out the Qiskit target from the
  "not-executed" banner when the iterative runtime is used.
- **`verifier`**: one new requirement — iterative-machine
  termination warning. No change to existing requirements.

## Impact

- `q_orca/runtime/iterative.py` — new file, iterative executor.
  ~200 LOC.
- `q_orca/runtime/guards.py` — new file, guard evaluator. ~80 LOC.
- `q_orca/runtime/context_ops.py` — new file, context-mutation
  interpreter. ~60 LOC.
- `q_orca/runtime/types.py` — extend with
  `QIterativeSimulationOptions`, `QIterativeSimulationResult`,
  `QIterationTrace`. ~40 LOC.
- `q_orca/runtime/python.py` — `simulate_machine` dispatches to
  iterative runtime when context-update actions are present.
  ~30 LOC changed.
- `q_orca/compiler/qiskit.py` — banner text is runtime-aware;
  add an entry point `build_circuit_for_iteration(machine, ctx)`
  that returns a per-iteration `QuantumCircuit` without wrapping
  it in a shots loop. ~60 LOC.
- `q_orca/verifier/classical_context.py` — add
  `UNBOUNDED_CONTEXT_LOOP` warning check. ~30 LOC.
- `openspec/specs/compiler/spec.md`,
  `openspec/specs/verifier/spec.md` — delta specs.
- `tests/test_run_context_updates.py` — new test file covering the
  guard evaluator, context-mutation interpreter, iterative runtime
  (happy path, termination, hard-ceiling trip), and the QPC
  learning example end-to-end. ~400 LOC.
- `examples/predictive-coder-learning.q.orca.md` (or extension of
  the existing minimal example) — the demonstrable learning loop.
  ~120 LOC.
- `README.md`,
  `docs/research/spec-quantum-predictive-coder.md` — landing notes.
- **No new runtime dependencies.** No new Python packages;
  iterative runtime is built on the existing Qiskit dependency.
  CUDA-Q and cuQuantum backends explicitly skip the iterative path
  in v1 (they still emit annotations; a follow-up change can add
  backend-specific support once the shared semantics are settled).
