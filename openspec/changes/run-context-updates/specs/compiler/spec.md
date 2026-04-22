## MODIFIED Requirements

### Requirement: Context-Update Annotation Emission

Each of the three compiler backends (QASM, Qiskit, Mermaid) SHALL
recognize `QEffectContextUpdate` effects and emit them as structured
annotations in the compiled artifact.

Annotation conventions (unchanged from the original requirement):

- **QASM**: a trailing comment on its own line formatted as
  `// context_update: <original_effect_string>`.
- **Qiskit**: a Python comment formatted as
  `# context_update: <original_effect_string>`.
- **Mermaid**: the action label appears on the transition arrow as
  for any other action; no special rendering.

The file-level banner SHALL reflect whether the annotation is
merely a record or is backed by an executor:

- **QASM**: `// NOTE: context-update actions are annotations only;
  shot-to-shot execution requires the Python/Qiskit iterative
  runtime.`
- **Qiskit**: `# NOTE: context-update actions are executed by the
  iterative runtime (q_orca.runtime.iterative).`
- **Mermaid**: no banner — Mermaid output is a diagram, not an
  execution target.
- **CUDA-Q / cuQuantum**: same text as QASM, naming the
  Python/Qiskit path as the executor.

#### Scenario: Qiskit banner reflects iterative-runtime execution

- **WHEN** a machine has a context-update action compiled to Qiskit
- **THEN** the compiled Python script contains the banner
  `# NOTE: context-update actions are executed by the iterative
  runtime (q_orca.runtime.iterative).` at file scope

#### Scenario: QASM banner reflects annotation-only status

- **WHEN** a machine has a context-update action compiled to QASM
- **THEN** the compiled QASM output contains the banner
  `// NOTE: context-update actions are annotations only; shot-to-shot
  execution requires the Python/Qiskit iterative runtime.` at file
  scope

#### Scenario: CUDA-Q backend banners the gap

- **WHEN** a machine has a context-update action compiled to the
  CUDA-Q backend
- **THEN** the compiled output contains a banner noting that
  context-update actions are annotations only for this backend and
  that the Python/Qiskit iterative runtime is the executor

## ADDED Requirements

### Requirement: Iterative Runtime Execution

The Python runtime SHALL execute machines containing
`QEffectContextUpdate` actions via an iterative walker that evaluates
guards against a live context, runs per-segment Qiskit circuits at
current context values, reads measurement outcomes into classical
bits, and applies context mutations between segments.

Activation SHALL be automatic: if any action in the machine has a
non-`None` `context_update` field, `simulate_machine` dispatches to
`q_orca.runtime.iterative.simulate_iterative`. Machines with no
context-update actions SHALL continue to use the existing
flat-circuit path with byte-identical output.

The iterative runtime SHALL:

- Walk the machine's transition graph from the initial state,
  evaluating guards against the current context via
  `q_orca.runtime.guards.evaluate_guard`.
- Dispatch on action kind: gate/measurement actions produce a
  per-segment `QuantumCircuit` via
  `build_circuit_for_iteration(machine, ctx, segment)`, run for
  `options.inner_shots`; context-update actions invoke
  `q_orca.runtime.context_ops.apply` to produce a new context
  snapshot.
- Re-enter previously-visited states on back-edges (the "each
  state visited once" constraint of the flat-circuit path SHALL
  NOT apply here).
- Terminate on reaching a `[final]` state and return
  `QIterativeSimulationResult`, or raise
  `QIterativeRuntimeError` when the walker is stuck at a
  non-final state with no enabled transition, or when the
  `iteration_ceiling` (default 10_000) is exceeded.
- Thread `options.seed_simulator` deterministically as
  `seed + iteration_index` per iteration so a given seed,
  machine, and initial context reproduce the same trace.

#### Scenario: Dispatch to iterative runtime on context-update machines

- **WHEN** `simulate_machine(machine, options)` is called on a
  machine whose actions include at least one `QEffectContextUpdate`
- **THEN** the call is dispatched to
  `q_orca.runtime.iterative.simulate_iterative` and returns a
  `QIterativeSimulationResult`

#### Scenario: Flat-circuit fast path preserved for existing machines

- **WHEN** `simulate_machine(machine, options)` is called on a
  machine with no context-update actions
- **THEN** the call uses the existing flat-circuit path and
  returns a `QSimulationResult` with byte-identical output
  compared to pre-landing behavior

#### Scenario: Back-edge re-entry in the QPC learning loop

- **WHEN** a machine has a back-edge from `|model_updated>` to
  `|prior_ready>` and the guard `ctx.iteration < max_iter` is
  satisfied
- **THEN** the iterative runtime re-enters `|prior_ready>` at the
  updated `theta` values, producing a distinct per-iteration trace
  entry and a corresponding circuit execution at the new
  parameters

#### Scenario: Iteration ceiling enforced

- **WHEN** a machine's guards never reach a `[final]` state after
  `options.iteration_ceiling` steps
- **THEN** the runtime raises
  `QIterativeRuntimeError("iteration ceiling exceeded")` and
  returns a `QIterativeSimulationResult` with `success=False` and
  the error message in `error`

#### Scenario: Stuck non-final state

- **WHEN** the walker reaches a non-final state with no outgoing
  transition whose guard evaluates True under the current context
- **THEN** the runtime raises `QIterativeRuntimeError("stuck
  state: <state_name>")` and returns a
  `QIterativeSimulationResult` with `success=False`

#### Scenario: Deterministic trace under fixed seed

- **WHEN** `simulate_iterative` is invoked twice with the same
  machine, same initial context, and same `seed_simulator`
- **THEN** the two returned traces are identical — same per-iteration
  measurement outcomes, same context snapshots, same final state
