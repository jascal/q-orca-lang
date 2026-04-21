## 1. Runtime types

- [ ] 1.1 Add `QIterationTrace` dataclass in
  `q_orca/runtime/types.py` with fields `iteration: int`,
  `source_state: str`, `target_state: str`, `event: str`,
  `action: Optional[str]`, `measurement_bits: dict[int, int]`,
  `context_snapshot: dict[str, object]`.
- [ ] 1.2 Add `QIterativeSimulationOptions` dataclass extending
  `QSimulationOptions` with `inner_shots: int = 1`,
  `iteration_ceiling: int = 10_000`, `record_trace: bool = True`.
- [ ] 1.3 Add `QIterativeSimulationResult` dataclass with
  `machine: str`, `success: bool`, `final_state: str`,
  `final_context: dict`, `trace: list[QIterationTrace]`,
  `aggregate_counts: dict[str, int]`, `error: Optional[str]`.
- [ ] 1.4 Add exception type `QIterativeRuntimeError` in
  `q_orca/runtime/types.py`.

## 2. Guard evaluator

- [ ] 2.1 Create `q_orca/runtime/guards.py` with
  `evaluate_guard(expr: QGuardExpression, ctx: dict,
  bits: dict[int, int]) -> bool`. Handle the existing expression
  kinds: `ctx_field_compare` (field, op, literal), `bit_compare`
  (idx, value), boolean `and`/`or`/`not`, empty/missing guard
  (always True).
- [ ] 2.2 Reject unsupported expression kinds at runtime with
  `QIterativeRuntimeError`. Probability-based guards SHALL fall
  through to the iteration's most-recent measurement and use the
  observed bit-value, NOT analytic probability (see design
  §Guard evaluator).
- [ ] 2.3 Unit tests in `tests/test_run_context_updates.py`
  covering each expression kind, nested boolean combos, and the
  "no guard" / "missing field" / "missing bit" cases.

## 3. Context-mutation interpreter

- [ ] 3.1 Create `q_orca/runtime/context_ops.py` with
  `apply(effect: QEffectContextUpdate, ctx: dict,
  bits: dict[int, int]) -> dict` returning a *new* snapshot
  (original unchanged).
- [ ] 3.2 Evaluate the bit condition, pick then/else branch,
  apply each `QContextMutation` atomically: `=` overwrites, `+=`
  and `-=` arithmetic on `int` scalar or `list[float]` element.
  RHS is literal or context-field reference; resolve the ref
  against the incoming snapshot.
- [ ] 3.3 Raise `QIterativeRuntimeError` on type mismatch at
  runtime (belt-and-braces against a verifier miss). The
  happy path is verified to typecheck by the parser + verifier
  stages; the runtime check is a safety net, not the primary
  defense.
- [ ] 3.4 Unit tests: unconditional scalar increment, list-element
  +=/-=/= with literal RHS, list-element update with field-ref
  RHS, then-only conditional, then+else conditional, snapshot
  immutability.

## 4. Iterative runtime walker

- [ ] 4.1 Create `q_orca/runtime/iterative.py` with
  `simulate_iterative(machine: QMachineDef,
  options: QIterativeSimulationOptions) ->
  QIterativeSimulationResult`.
- [ ] 4.2 Initialize a mutable context record from
  `machine.context` defaults and an empty `bits` dict.
- [ ] 4.3 Walk transitions from the initial state: enumerate
  outgoing transitions, evaluate guards via `guards.py`, pick the
  first enabled one in declaration order. On zero matches at a
  non-final state: raise `QIterativeRuntimeError("stuck state")`.
- [ ] 4.4 Dispatch on action kind: gate/effect → build a per-segment
  Qiskit circuit at current context values via
  `build_circuit_for_iteration` (task 5.2), run it for
  `options.inner_shots`, update `bits` from measurement outcomes.
  Context-update → invoke `context_ops.apply`, update context
  snapshot. Mid-circuit measurement → treated as gate+measurement
  segment, update `bits`.
- [ ] 4.5 Record one `QIterationTrace` per transition when
  `options.record_trace` is set.
- [ ] 4.6 Terminate on reaching a `[final]` state: build
  `QIterativeSimulationResult` with the trace, final context, and
  aggregated counts across all iterations' measurement outcomes.
- [ ] 4.7 Enforce `iteration_ceiling`: raise
  `QIterativeRuntimeError("iteration ceiling exceeded")` if the
  walker hits the bound without reaching a final state.
- [ ] 4.8 Thread `options.seed_simulator` deterministically
  through each iteration's circuit run — per-iteration seeds
  SHALL be `seed + iteration_index` so a full trace is
  reproducible from a single seed.

## 5. Qiskit backend integration

- [ ] 5.1 In `q_orca/compiler/qiskit.py`, refactor the shared
  bits of `_extract_gate_sequence` so the iterative path can
  reuse them without the "each state visited once" flattening.
- [ ] 5.2 Add `build_circuit_for_iteration(machine: QMachineDef,
  ctx: dict, segment: ActionSegment) -> QuantumCircuit` that
  produces a fresh `QuantumCircuit` for the given action segment
  with angles resolved against `ctx`. No shots loop, no banner,
  no analytic stanza — just the circuit.
- [ ] 5.3 Update the file-level banner logic: if the machine has
  context-update actions, emit
  `# NOTE: context-update actions are executed by the iterative
  runtime (q_orca.runtime.iterative).` instead of the existing
  "annotations only; shot-to-shot execution not yet implemented"
  text. Existing per-action `# context_update: ...` comments are
  unchanged.
- [ ] 5.4 CUDA-Q and cuQuantum banner additions: when a machine
  has context-update actions, emit a banner noting that only the
  Python/Qiskit runtime executes context updates; these backends
  emit annotations only. (Touches `q_orca/compiler/cudaq.py` and
  wherever cuquantum is generated.)

## 6. Runtime dispatch

- [ ] 6.1 In `q_orca/runtime/python.py::simulate_machine`, detect
  `any(a.context_update is not None for a in machine.actions)`
  and dispatch to `simulate_iterative` instead of the existing
  flat-circuit path when true.
- [ ] 6.2 Keep the existing flat-circuit path unchanged for every
  other machine. Add a regression test that every shipped example
  produces byte-identical output before and after this change.
- [ ] 6.3 Wire `simulate_iterative` into `q-orca verify --run`
  and the MCP `simulate_machine` tool so iterative results are
  returned through the same user-facing surface. Default output
  collapses the trace; `--verbose` expands it.

## 7. Verifier — termination warning

- [ ] 7.1 In `q_orca/verifier/classical_context.py`, add
  `check_iterative_termination(machine) -> list[QVerifyError]`:
  if `any(a.context_update is not None for a in machine.actions)`
  AND no guard on any path from a context-update-bearing state
  to a `[final]` state references an `int` context field with
  a bounding comparison (e.g., `ctx.iteration < <literal>`),
  emit `UNBOUNDED_CONTEXT_LOOP` at **warning** severity.
- [ ] 7.2 Respect the existing `VerifyOptions.skip_classical_context`
  skip flag.
- [ ] 7.3 Unit tests: QPC learning example (no warning — has
  `ctx.iteration < max_iter` guard), a synthetic machine that
  mutates context but has no bounding guard (warning emitted), a
  machine with guards on `list<float>` element values (still
  warned — element mutations are not a termination bound under
  v1's conservative analysis).

## 8. Spec + docs sync

- [ ] 8.1 Delta `openspec/changes/run-context-updates/specs/
  compiler/spec.md` — modify "Context-Update Annotation Emission"
  to carve out the Qiskit target under the iterative runtime;
  add a new requirement "Iterative Runtime Execution" covering
  activation, per-segment execution, result shape, and seeding.
- [ ] 8.2 Delta `openspec/changes/run-context-updates/specs/
  verifier/spec.md` — add "Iterative-Machine Termination Warning"
  requirement covering `UNBOUNDED_CONTEXT_LOOP`.
- [ ] 8.3 Update
  `docs/research/spec-quantum-predictive-coder.md` §Next concrete
  steps to mark step 4 (this change) as landed and step 6
  (learning-loop + benchmark) as unblocked.
- [ ] 8.4 Update `README.md` roadmap: move the line for
  `add-classical-context-updates` to reflect full shipment,
  and add this change under Recently shipped on landing.
- [ ] 8.5 Update `CHANGELOG.md` with the behavioral-change note
  from design §Migration Plan.
- [ ] 8.6 Run `openspec validate run-context-updates --strict`
  before opening the PR.

## 9. End-to-end verification

- [ ] 9.1 Extend `examples/predictive-coder-minimal.q.orca.md`
  (or add `examples/predictive-coder-learning.q.orca.md`) with
  the full learning loop from the research doc:
  `|measured>` → `|model_updated>` → `|prior_ready>` back-edge,
  `|converged>` final state on `ctx.iteration >= max_iter`,
  `gradient_step` + `reset_data_and_ancilla` actions.
- [ ] 9.2 Confirm `q-orca verify --strict` returns VALID on the
  example with no `UNBOUNDED_CONTEXT_LOOP` warning.
- [ ] 9.3 Confirm `q-orca verify --backend qiskit --run` drives
  the iterative runtime and returns a trace in which `theta[0]`
  changes across iterations and the machine reaches
  `|converged>` within `max_iter` iterations.
- [ ] 9.4 Wire the example into `.github/workflows/
  verify-examples.yml` (confirm existing glob already picks it
  up; add explicitly if not).
- [ ] 9.5 Run the full suite
  `.venv/bin/python -m pytest tests/ -q
  --ignore=tests/test_cuquantum_backend.py
  --ignore=tests/test_cudaq_backend.py` — baseline + all new tests.
- [ ] 9.6 Regression-check every other example in `examples/`
  remains VALID under `q-orca verify --strict`.

## 10. Follow-ups parked (NOT this change)

- [ ] 10.1 **Parked**: CUDA-Q iterative runtime. Open once v1
  semantics are settled and the cudaq compile-run loop can be
  adapted.
- [ ] 10.2 **Parked**: cuQuantum iterative runtime. Same as
  10.1 for cuquantum.
- [ ] 10.3 **Parked**: Qiskit `Parameter`-object reuse for
  per-iteration rebinding (performance optimization). Bench
  against v1's per-iteration recompile on a 10-parameter,
  50-iteration ansatz before opening.
- [ ] 10.4 **Parked**: convergence-plotting demo under
  `demos/predictive_coder/` — Python harness that sweeps the
  QPC learning loop and plots error-vs-iteration against a
  classical NN baseline (research-spec step 6).
- [ ] 10.5 **Parked**: explicit-event injection API for
  externally-driven machines (likely part of
  `add-parameterized-invoke`).
