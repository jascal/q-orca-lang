## Why

Q-Orca's static verifier is strong on structural checks (unitarity, no-cloning,
reachability) but silent on the question every quantum-program author actually
asks while debugging: *"is the quantum state at this midpoint what I think it
is?"* Today the only answers are eyeballing a printed state vector or running
the full circuit on hardware. The current `## invariants` table already speaks
the right vocabulary (`entanglement(q0, q1) = True`, `schmidt_rank(q0, q1) >= 2`)
but only at the *machine* level — there is no way to localize a claim to a
specific named state. This change promotes the same vocabulary to a per-state
annotation backed by statistical sampling on the Stage 4b simulator, which is
the Huang–Martonosi (ISCA 2019) "coarse-grained" approach recommended by the
formal-methods survey `2109.06493` §8.4 as the right tool when destructive
measurement and non-determinism rule out QHL-style projection assertions.

## What Changes

- Extend the `## state` heading grammar to recognize a new `[assert: …]`
  annotation alongside `[initial]`, `[final]`, and the queued `[loop …]` /
  `[send]` / `[receive]` annotations. The payload is one or more
  semicolon-separated category expressions over qubit slices.
- Recognized assertion categories: `classical(qs[…])`,
  `superposition(qs[…])`, `entangled(qs[i], qs[j])`,
  `separable(qs[i], qs[j])`. Each accepts either a single qubit `qs[k]` or a
  range slice `qs[a..b]`.
- Add a new `## assertion policy` section parsed into an `AssertionPolicy`
  with fields `shots_per_assert: int = 512`, `confidence: float = 0.99`,
  `on_failure: 'error' | 'warn' = 'error'`, and `backend: 'auto' | <name> =
  'auto'`. Section is optional; absence yields the defaults.
- Add a new verifier module `q_orca/verifier/assertions.py` implementing
  `check_state_assertions(machine, backend)` which builds the circuit prefix
  to each annotated state, runs `shots_per_assert` samples on the Stage 4b
  backend, and evaluates each category predicate (Z-basis sampling for
  `classical` / `superposition`; reduced-density-matrix purity for
  `entangled` / `separable`).
- Add a new verification rule name `state_assertions` to `## verification
  rules`, plus three new diagnostic codes: `ASSERTION_FAILED`,
  `ASSERTION_INCONCLUSIVE`, `ASSERTION_BACKEND_MISSING`. A fourth
  informational diagnostic `ASSERTIONS_SKIPPED_NO_SIMULATOR` fires when the
  compile target is a real device.
- Carry the per-state assertion list through the Qiskit and QASM compilers
  as out-of-band metadata. The Qiskit compiler attaches an
  `assertion_probe: list[QAssertion]` field to its existing state-label
  metadata. The QASM compiler emits `// assert: …` comment lines but no
  instructions, preserving compatibility with external tools.

## Capabilities

### New Capabilities

None. This change extends the existing language, compiler, and verifier
capabilities.

### Modified Capabilities

- `language`: state-header grammar gains the `[assert: …]` annotation kind;
  new `## assertion policy` section; `QState.assertions` and
  `QMachine.assertion_policy` AST fields.
- `verifier`: new `state_assertions` rule, new `check_state_assertions`
  module, four new diagnostic codes, statistical-sampling semantics for the
  four assertion categories.
- `compiler`: Qiskit emission attaches `assertion_probe` metadata to the
  state-label snapshot; QASM emission produces `// assert:` comment lines;
  neither compiler emits any new instructions.

## Impact

- **Code**: new `q_orca/verifier/assertions.py` (~300 LOC including
  reduced-density-matrix partial trace); parser extension in
  `q_orca/parser/markdown_parser.py` (~100 LOC); new AST nodes `QAssertion`
  and `AssertionPolicy` in `q_orca/ast.py`; small additions to
  `q_orca/compiler/qiskit.py` and `q_orca/compiler/qasm.py` to carry the
  metadata.
- **Tests**: new `tests/test_state_assertions.py` covering one passing case
  per category, a failing case, an inconclusive case (`shots=16`), and the
  backend-missing path. Parser tests added to `tests/test_parser.py`.
- **Examples**: new `examples/bell-entangler-asserts.q.orca.md`; updated
  `examples/bit-flip-syndrome.q.orca.md` to demonstrate real debugging
  value.
- **Docs**: new `docs/language/assertions.md` covering the vocabulary,
  statistical semantics, and the destructive-measurement caveat (assertions
  re-run the circuit prefix, so they are a debug-time cost, not a runtime
  cost on real hardware).
- **Dependencies**: no new hard dependencies. Reuses QuTiP from Stage 4b
  and NumPy / SciPy (already in the tree) for binomial / Wilson-score
  bounds.
- **Composes with**: execution-backends (already shipped in 0.4.0),
  mid-circuit measurement (already shipped), the queued extended-invariants
  and qubit-role-types proposals.
