## Why

`add-parameterized-invoke` and `add-machine-imports` gave q-orca the *static*
story for machine composition — `invoke: Child(...)`, typed `## returns`,
shot-batched aggregates, cross-file resolution, and a verifier that checks it
all. But there is still **no way to actually run a composed machine**: the
QASM/Qiskit backends refuse invoke states with `COMPILE_COMPOSED_MACHINE`, and
the existing `simulate_iterative` runtime walks a single machine only. The
Quantum Predictive Coder — a classical training loop that repeatedly dispatches
a quantum forward pass and reads back measured-bit expectations — is fully
expressible and verifiable today but cannot execute. This change closes that
loop: a Python dispatcher that walks a parent machine, executes each invoked
child (classical run-to-completion or quantum shot-batched), and threads the
declared returns / synthesized aggregates back into the parent's context.

## What Changes

- **Runtime**: a new `q_orca/runtime/composed.py` exposing
  `run_composed(file, machine, options, base_path=None) -> ComposedRunResult`.
  It reuses the existing single-machine walk (`simulate_iterative`) for each
  machine and adds invoke handling:
  - At an invoke state it resolves the child (same-file machine, or via the
    `add-machine-imports` resolver when `base_path` is given), builds the
    child's initial context from the parent's via the invoke's `arg_bindings`,
    runs the child, and binds the child's returns back into the parent context
    via `return_bindings`.
  - **Classical child** (no measurement): run to a final state; returns are a
    snapshot of the child's declared `## returns` fields at exit.
  - **Quantum child** (measurement-bearing): under `shots=1`, run once and
    return raw values; under `shots=N>1`, run N shots and compute the declared
    statistics into the synthesized aggregate fields (`prob_<r>: float`,
    `hist_<r>: dict[int,int]`, `var_<r>: float`) matching the names the
    composition verifier already synthesizes.
  - Recursion is bounded by a depth ceiling; invoke cycles are already rejected
    statically by the verifier.
- **CLI**: `q-orca run <file>` executes a composed (or single) machine and
  prints the final parent context (and per-invoke child summaries); `--json`
  for machine-readable output.
- **Out of scope (v1)**: real-hardware execution (simulator only), concurrent
  invokes, coroutine/yield-on-measure execution, and aggregate kinds beyond
  `expectation` / `histogram` / `variance`.

## Capabilities

### New Capabilities

- `runtime`: execution semantics for composed machines — the dispatcher that
  walks a parent, runs invoked children (classical/quantum, single/shot-batched),
  computes aggregates, and threads returns back into the parent context.

### Modified Capabilities

None. The language, verifier, and compiler contracts are unchanged; this change
adds an execution layer on top of them.

## Impact

- **Code**: new `q_orca/runtime/composed.py` (~250 LOC) reusing
  `simulate_iterative`, `context_ops`, and the `import_resolver`; a `run`
  subcommand in `q_orca/cli.py` (~40 LOC); a small `ComposedRunResult` type.
- **Tests**: classical-child run-to-completion, quantum single-shot, quantum
  shot-batched aggregate computation, return binding into parent context,
  nested composition, depth-ceiling guard. New `tests/test_composed_runtime.py`.
- **Dependencies**: none new — reuses the QuTiP/Qiskit simulation already wired
  into the iterative runtime.
- **Composes with**: `add-parameterized-invoke` (invoke/returns AST + verifier),
  `add-machine-imports` (cross-file child resolution). Unblocks the
  `composed_predictive_coder` fixture from running, not just verifying.
