## Context

q-orca already has a single-machine runtime: `q_orca/runtime/iterative.py::simulate_iterative`
walks a machine's states, evaluates guards (`runtime/guards.py`), accumulates
gate-bearing transitions into a "segment" that flushes as a simulated circuit,
applies classical context updates (`runtime/context_ops.py`), and returns a
`QIterativeSimulationResult` with `final_state`, `final_context`, and
`aggregate_counts` (per-measured-bit shot counts). What it does **not** do is
handle `invoke:` states — it has no notion of running a child machine.

The static layer is complete: `QInvoke` (arg/return bindings, shots), `## returns`,
the composition verifier (resolution, typing, shots rules, cycles), and the
cross-file import resolver all shipped. The compilers refuse composed machines
(`COMPILE_COMPOSED_MACHINE`) precisely because this runtime did not exist. This
change adds the dispatcher.

## Goals / Non-Goals

**Goals:**

- Execute a composed parent machine end-to-end on the simulator, dispatching
  each invoked child and threading its returns back into the parent context.
- One dispatch path that handles both classical (run-to-completion) and quantum
  (single-shot or shot-batched) children, keyed off whether the child is
  measurement-bearing — mirroring the verifier's `shots`-flag rule.
- Compute the declared `## returns` statistics into the synthesized aggregate
  fields (`prob_*`, `hist_*`, `var_*`) using the **same names** the composition
  verifier checks, so a machine that verifies also runs.
- Reuse `simulate_iterative` for the per-machine walk; do not fork it.

**Non-Goals:**

- Real-hardware execution — simulator only (a real-device run is a later change).
- Concurrent / parallel invokes, and coroutine/yield-on-measure execution.
- New statistic kinds beyond `expectation` / `histogram` / `variance`.
- Re-verifying at run time — `run_composed` assumes the machine has already
  passed `verify()`; it is an executor, not a checker.

## Decisions

### Decision 1: A thin dispatcher around `simulate_iterative`, not a rewrite

`run_composed` walks the parent exactly as `simulate_iterative` does, with one
addition: when the walk reaches an invoke state, it pauses, executes the child,
binds returns into the parent context, and resumes. Rather than duplicate the
walk, `composed.py` drives `simulate_iterative` on each individual machine and
intercepts invoke states. A machine with no invoke states runs through the
existing path unchanged.

**Alternative considered:** a brand-new unified walker. Rejected — it would
duplicate guard evaluation, segment flushing, and context-update logic that
already works and is tested.

### Decision 2: Child execution keyed off measurement-bearing, matching the verifier

The dispatcher classifies the resolved child the same way the verifier does
(any action with a `measurement` / `mid_circuit_measure` effect → quantum):

- **Classical child**: `simulate_iterative` to a final state; the returns are
  read from the child's `final_context` by the names in its `## returns`.
- **Quantum child, `shots=1`**: run once; raw return values from `final_context`
  / measured bits.
- **Quantum child, `shots=N>1`**: run the child with the shot count threaded
  into its simulation options; collect per-measured-bit counts from the child's
  `aggregate_counts` and compute, for each declared return + statistic, the
  synthesized aggregate (`prob_r = count1/N`, `hist_r = {0: n0, 1: n1}`,
  `var_r = p(1−p)`).

This guarantees the field a parent binds (`prob_bits_0`, …) is exactly what the
runtime materializes.

**Alternative considered:** always shot-batch quantum children. Rejected — the
verifier already distinguishes `shots=1` (raw) from `shots>1` (aggregates), and
the runtime must honour that contract.

### Decision 3: Arg/return binding is by name against context, not positional

Argument bindings (`child_param=parent_expr`) build the child's initial context:
each child context field named on a binding LHS is seeded from the parent
expression's value (a parent context field, or an indexed element `theta[0]`).
Return bindings (`parent_field=child_return`) write back: the parent context
field is set to the child's raw return (shots=1) or synthesized aggregate
(shots>1). Fields not mentioned in bindings keep their declared defaults. This
mirrors the verifier's typing checks one-to-one.

### Decision 4: Child resolution reuses the import resolver

Same-file children resolve against `file.machines`; cross-file children resolve
through the `add-machine-imports` `ResolvedImportGraph` when `base_path` is
supplied. The runtime accepts an optional pre-built graph (built by the CLI from
the file path) so it does no path discovery itself beyond delegating to the
resolver — symmetric with how the verifier consumes the graph.

### Decision 5: Depth ceiling, not cycle detection, at run time

Invoke cycles are rejected statically by the verifier (`INVOKE_CYCLE`) and the
import resolver (`IMPORT_CYCLE`), so the runtime does not re-detect them. It
carries a recursion-depth ceiling (default 32) purely as a runaway guard,
raising a structured runtime error if exceeded.

## Risks / Trade-offs

- **[Risk] Divergence between verifier-synthesized aggregate names and
  runtime-materialized ones.** → Mitigation: both derive names from the same
  `_sanitize` rule; a shared helper (or a test asserting parity) keeps them in
  lockstep.
- **[Risk] Quantum child simulation is the dominant cost; shot-batched nested
  composition multiplies it.** → Mitigation: shots are per-invoke and
  author-controlled; the depth ceiling bounds nesting; this is debug/simulation
  tooling, not a production hot path.
- **[Trade-off] Assumes a pre-verified machine.** `run_composed` does not
  re-run `verify()`. A malformed binding that somehow reaches the runtime
  surfaces as a Python-level error rather than a structured diagnostic. The CLI
  `run` command verifies first and refuses to run an invalid machine.

## Open Questions

1. **Return snapshot at multiple `[final]` states.** A child with several final
   states may exit with different contexts; v1 takes the context at whichever
   final state the run reaches (deterministic given the guards). A union/typed
   exit is deferred.
2. **Seeding shot-batched runs.** For reproducibility the CLI may expose a
   `--seed`; v1 threads the existing simulation seed option if present.
