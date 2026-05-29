## 1. Result type + entry point

- [x] 1.1 Add a `ComposedRunResult` dataclass to `q_orca/runtime/types.py`
  (final parent context, final state, per-invoke child summaries, depth used).
- [x] 1.2 Create `q_orca/runtime/composed.py` with
  `run_composed(file, machine, options, base_path=None, import_graph=None)`.

## 2. Dispatcher

- [x] 2.1 Walk the parent reusing the iterative-runtime machinery; detect when
  the walk reaches an invoke state (do not duplicate guard/segment logic).
- [x] 2.2 Resolve the invoke child: same-file `file.machines` first, then the
  import graph (built from `base_path` when given).
- [x] 2.3 Build the child's initial context from the parent via `arg_bindings`
  (bare field and indexed `theta[0]` RHS); unbound child fields keep defaults.
- [x] 2.4 Classify the child (measurement-bearing → quantum, else classical)
  and execute: classical/`shots=1` run-to-completion; `shots>1` shot-batched.
- [x] 2.5 Bind returns back into the parent context via `return_bindings`
  (raw return for `shots<=1`, synthesized aggregate for `shots>1`).
- [x] 2.6 Depth-ceiling guard (default 32) raising a structured runtime error.

## 3. Aggregate computation

- [x] 3.1 From the child's per-measured-bit shot counts, compute
  `prob_<r>` / `hist_<r>` / `var_<r>` using the same sanitized names the
  composition verifier synthesizes (share or mirror the `_sanitize` rule;
  pin parity with a test).

## 4. CLI

- [x] 4.1 Add a `q-orca run <file>` subcommand that verifies, then executes via
  `run_composed`, printing the final parent context (+ per-invoke summaries);
  `--json` for machine-readable output. Refuse to run an invalid machine.

## 5. Tests

- [x] 5.1 `tests/test_composed_runtime.py`: single machine runs unchanged;
  classical child returns flow into parent; arg bindings seed child context;
  quantum `shots=1` raw return; quantum `shots>1` aggregate (prob/hist/var);
  nested composition; depth-ceiling guard.
- [x] 5.2 Run the `composed_predictive_coder` fixture end-to-end through
  `run_composed` and assert the parent's `prob` field is populated from the
  child's `prob_bits_0` aggregate.

## 6. End-to-end + docs

- [x] 6.1 Full suite green + all examples still `verify --strict`.
- [x] 6.2 Update `docs/research/spec-quantum-predictive-coder.md` to note the
  composed QPC now executes (not just verifies) via `run_composed`.

## 7. Spec sync

- [ ] 7.1 At archive time, sync the `runtime` delta spec into
  `openspec/specs/runtime/spec.md`.
