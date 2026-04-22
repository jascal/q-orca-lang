## Context

Q-Orca's Python runtime today compiles a machine to one flat
`QuantumCircuit` — `_extract_gate_sequence` in
`q_orca/compiler/qiskit.py` does a BFS over the transition graph,
visits each state once, stops at terminal measurements, and emits a
linear gate list. That list is wrapped in a classical shots loop
(`for _ in range(shots): backend.run(qc_shots)`) and the output is a
flat counts dict. Three assumptions baked into that pipeline block
what the QPC needs:

1. **Every state is visited at most once per execution.** Back-edges
   are ignored — the `visited` set in `_extract_gate_sequence`
   silently flattens any loop.
2. **Context values are substituted at compile time.** Once the
   circuit is built, `theta[0]` is a number; no mechanism exists to
   change it and re-run without recompiling from scratch.
3. **Guards are interpreted statically** (for completeness/
   reachability checks) but never *evaluated* at runtime against
   live context.

The archived `add-classical-context-updates` change delivered the
language surface — grammar, AST, parser, verifier, and annotation
emission — for writing an action like
`if bits[0] == 1: theta[0] -= eta else: theta[0] += eta`. What is
missing is an executor that, after each measurement, reads the
measured bit, picks the branch, applies the mutation to a live
context record, rebuilds the circuit at the new parameters, and
keeps going until a guard says to stop.

The cleanest way to deliver that without disturbing the existing
hot path is a *new* runtime driver, triggered only for machines
that actually need it. Machines without context-update actions keep
the fast path verbatim; machines with them opt in automatically.

## Goals / Non-Goals

**Goals:**

- Execute `QEffectContextUpdate` effects for real against a live
  Python context record. Observable: calling `simulate_machine(...)`
  on the full QPC machine returns a trace in which `theta[0]`
  changes across iterations and the per-iteration measurement
  outcomes reflect those changes.
- Walk the machine's transition graph at runtime: evaluate guards
  against the current context, follow the first matching
  transition, execute the action, repeat until a final state is
  reached.
- Handle back-edges cleanly. A transition whose target is a
  previously-visited state SHALL re-enter that state (the `visited`
  set the compiler uses for flattening SHALL NOT exist in the
  runtime walker).
- Provide a shared guard-evaluator and a shared
  context-mutation-interpreter usable by `run-context-updates`,
  `add-runtime-state-assertions`, and `add-parameterized-invoke`.
- Keep the non-iterative fast path byte-for-byte identical. Every
  existing example and test SHALL produce the same output.

**Non-Goals:**

- **No CUDA-Q or cuQuantum iterative-runtime support in v1.** Those
  backends retain annotation-only behavior and a banner noting that
  context-update execution requires the Python/Qiskit runtime.
  Tracked as a follow-up.
- **No Qiskit `Parameter`-object reuse for per-iteration rebinding.**
  v1 rebuilds the circuit from the AST each iteration. Correctness
  first; the `Parameter`-binding optimization is tracked under
  `## Open Questions` and is a clean follow-up once the semantics
  are settled.
- **No parallel multi-shot averaging.** `inner_shots` runs the same
  parameter-bound circuit N times serially and averages the
  outcome; parallel execution is a future optimization.
- **No runtime integration with decision tables.** Out of scope.
- **No convergence-plotting or results-visualization layer.** That
  belongs in a demo harness (see `demos/predictive_coder/`, tracked
  separately), not in the runtime.
- **No cross-machine invocation.** That is explicitly
  `add-parameterized-invoke`'s scope; the runtime walker here is
  single-machine.

## Decisions

### Runtime activation is automatic on machine shape

If `any(a.context_update is not None for a in machine.actions)` is
true, `simulate_machine` dispatches to the iterative runtime.
Otherwise the existing flat-circuit path runs. Rationale: the
language surface is already gated — a machine either has
context-update actions or it doesn't, and the right runtime falls
out mechanically. No flag, no user-visible opt-in.

**Alternatives considered:**

- *Explicit `QSimulationOptions.iterative=True` flag.* Rejected —
  users would need to know the flag exists. Shape-based dispatch is
  invisible and unambiguous.
- *Make the iterative runtime the only path.* Rejected — introduces
  unnecessary per-iteration overhead for every existing machine.

### Transition selection: first-match by source + event + guard

At each step the runtime enumerates outgoing transitions from the
current state, filters by guard evaluation against the current
context, and picks the first matching one in declaration order.
Rationale: the verifier's existing determinism check ensures
guards are mutually exclusive on valid machines, so "first match"
and "only match" coincide on any machine that verifies. If the
verifier's check is loosened later (e.g., priority-based
dispatch), this runtime rule can be tightened along with it.

Events are implicit in v1: the runtime picks whichever transition
is enabled by the source+guard. Explicit event injection (for
external drivers, e.g., the classical orca controller in the
hybrid demo) is out of scope for this change.

**Alternatives considered:**

- *Require explicit event injection.* Rejected for v1 because all
  in-scope use cases (QPC, runtime assertions) are self-driving
  state machines where the event choice is determined by the
  state+guard.

### Guard evaluator — interpreter, not compiler

`q_orca/runtime/guards.py` operates on the already-parsed
`QGuardExpression` AST. The expression grammar (boolean combos of
`ctx.field <op> literal`, `bits[i] == v`, probability expressions)
is already parsed; the evaluator walks it against a Python dict-like
context. No re-parsing, no eval-string.

For probability-based guards (`P(|0⟩) > 0.5` style), v1 defers to
the measurement outcome actually observed at the most recent
iteration's `inner_shots` — not to analytic probability. Rationale:
the iterative runtime's whole point is measurement-driven feedback.
Analytic-probability guards are primarily a verifier concern.

**Alternatives considered:**

- *sandboxed `eval()` on the raw expression string.* Rejected —
  security-aware users reject `eval` on principle, the AST is
  already available, and the grammar is small enough to interpret
  directly.

### Context mutation — interpreter against an immutable snapshot

Each iteration starts with a *snapshot* of the previous
iteration's context (a `dict` copy). Mutations are applied to the
new snapshot and it becomes the current context for the next
iteration. Rationale: makes the per-iteration trace trivially
serializable, makes failures mid-iteration recoverable (roll back
to the last good snapshot), and matches the "functional in the
small, mutable across iterations" idiom the research doc expects.

The interpreter handles the two mutation ops in the AST:
`=`, `+=`, `-=` for both scalar `int` and `list<float>` element
LHS. No other ops are legal (the verifier already enforces this).

### Qiskit backend — per-iteration recompile, v1

Each iteration the runtime:

1. Takes the current context snapshot.
2. Determines the next single-transition segment the walker is about
   to execute (one action = gates-or-measurement-or-mutation).
3. If the action is gates/measurement: calls
   `build_circuit_for_iteration(machine, ctx, segment)` →
   `QuantumCircuit` with `theta[0]` etc. already numerically bound,
   runs it for `inner_shots`, reads the measured bit(s) into `ctx.bits`.
4. If the action is a context-update: invokes
   `context_ops.apply(action.context_update, ctx)`.

**Why per-segment rather than per-full-shot:** a machine like the
QPC has a back-edge that re-enters `|prior_ready>` with *different*
`theta` values each iteration. Building the whole circuit up front
and running shots through it cannot express that — the parameters
change *during* the shot. Per-segment execution makes the
parameter-freshness invariant free.

**Why recompile rather than `Parameter`-bind:** recompilation is
the simplest correct thing. Cost is dominated by Qiskit
circuit construction, not simulator execution, and for 3-qubit
machines it's negligible. `Parameter` reuse is an obvious
follow-up and noted in `## Open Questions`.

### Hard iteration ceiling

`QIterativeSimulationOptions.iteration_ceiling` (default 10_000)
is a safety net that raises `QIterativeRuntimeError` if the walker
has not reached a final state by that count. Rationale: protects
against buggy guards. Not a user-facing knob for the QPC (its
`max_iter` is 50 in the sketch); a research user sweeping over
longer loops can raise the ceiling explicitly.

This is complemented by the verifier's `UNBOUNDED_CONTEXT_LOOP`
warning — the verifier warns if no guard constrains loop depth;
the runtime enforces a numerical bound regardless. Two-belt
defense.

### Result shape — additive, non-breaking

`QSimulationResult` (the existing flat-counts shape) remains the
return type for non-iterative machines.
`QIterativeSimulationResult` is a new dataclass returned for
iterative machines; it carries `trace: list[QIterationTrace]`,
`final_context: dict`, `final_state: str`, plus the flat counts
aggregated across iterations (for parity with the existing shape
so simple tests still work).

CLI output (`q-orca verify --backend qiskit --run`) gains a
per-iteration summary for iterative machines (default collapsed;
`--verbose` expands it).

### File layout — new module for runtime internals

```
q_orca/runtime/
  python.py          # existing; gains dispatch logic
  types.py           # existing; gains iterative types
  iterative.py       # NEW — the walker
  guards.py          # NEW — guard evaluator
  context_ops.py     # NEW — mutation interpreter
```

Rationale: keeps the runtime primitives separate and testable.
`guards.py` and `context_ops.py` are both ~60-80 LOC pure functions
that other OpenSpec changes (assertions, invoke) can import.

## Risks / Trade-offs

- **[Risk]** Per-iteration recompile is slow on large machines. →
  **Mitigation:** explicitly named as a v1 trade-off; 3-qubit QPC
  and any shipped example is dominated by measurement overhead
  anyway. `Parameter`-reuse is a known optimization path. If
  someone hits the limit on a larger machine before the follow-up
  lands, they can still use the non-iterative path by removing
  context-update actions.

- **[Risk]** The "first matching guard" rule silently diverges
  from the verifier if the verifier ever permits overlapping
  guards. → **Mitigation:** the runtime calls the verifier's
  existing determinism analyzer at simulator start and raises
  `QIterativeRuntimeError` if any state has multiple enabled
  transitions for the current context. Two-level defense.

- **[Risk]** `UNBOUNDED_CONTEXT_LOOP` generates false-positive
  warnings on machines that legitimately want to rely on the
  iteration ceiling. → **Mitigation:** it's a warning, not an
  error, and is suppressible with
  `VerifyOptions.skip_classical_context`. Also add a machine-level
  `## context` hint `iteration_ceiling: <N>` that, if present,
  silences the warning. (Optional polish; decide during
  implementation.)

- **[Trade-off]** New files `guards.py` and `context_ops.py` add
  two modules to the runtime directory. Worth it: both are reused
  by other roadmap changes and the alternative (inlining them in
  `iterative.py`) makes `iterative.py` hard to test. The boundary
  pays for itself.

- **[Trade-off]** CUDA-Q and cuQuantum staying annotation-only in
  v1 means the execution-backends matrix has a visible gap for
  context-update machines. → **Mitigation:** compiler banner for
  those backends names the gap explicitly and points to the
  Python/Qiskit path. A follow-up change can port the iterative
  semantics to the native backends once v1 settles.

## Migration Plan

Machines without context-update actions see zero behavioral change.

Machines with context-update actions change behavior observably:
the previously ignored `# context_update:` comment now executes,
and results (counts, final state) may differ from the pre-landing
run. This is the *intended* change, but it is observable, so:

- The Qiskit compiler's file-level banner swaps from
  "annotations only; not executed" to "executed via iterative
  runtime".
- The release note and CHANGELOG entry SHALL call this out
  explicitly as a behavioral change, not just a new feature.
- Any user with a machine that was relying on context-updates
  being silently ignored (none known; the grammar is three months
  old and the archived change's test suite is the only other
  caller) would need to remove the action or re-verify behavior.

Rollback: revert this change's commits. The existing
annotation-only emission path is preserved, so rollback restores
pre-landing behavior exactly.

## Open Questions

1. **Qiskit `Parameter` reuse.** How much speedup does it
   actually buy on the QPC and on a hypothetical 50-iteration,
   10-parameter ansatz? Worth prototyping after v1 correctness
   is locked. Not a v1 blocker.

2. **Machine-level `iteration_ceiling` hint.** Whether to surface
   the ceiling as a `## context` field rather than (or in addition
   to) a runtime option. Leaning "in addition to" — context gives
   machines self-describing bounds; runtime gives sweep harnesses
   a knob. Decide during implementation.

3. **Event injection for externally-driven machines.** The QPC's
   inner loop is self-driving (guards determine the path). Future
   machines (a replicated hybrid controller, a tutorial walker)
   may want to inject events from outside. Leaning "park until
   `add-parameterized-invoke` lands" since the composition story
   is the natural place for explicit events.

4. **Seeded reproducibility.** The non-iterative path already
   supports `seed_simulator`. v1 of the iterative runtime SHALL
   thread the seed through per-iteration circuits deterministically
   so that a given seed + machine + initial context reproduces the
   same trace. Treat this as non-negotiable for regression tests.

5. **Trace persistence.** Writing the iteration trace to disk as
   JSON (for plotting in a notebook) is worth building in from v1
   if it's a 20-line add. Probably yes. Decide during
   implementation.
