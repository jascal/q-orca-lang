## Why

Two related limitations have been blocking realistic LARQL-flavored demos:

1. **Multi-controlled gates were missing.** The 4-qubit Grover gate-KNN demo
   (`examples/larql-gate-knn-grover.q.orca.md`) needs a 3-control `MCZ` for
   both the phase oracle and the diffusion operator. Q-Orca's effect-string
   parser only knew `CNOT`, `CZ`, and a single 3-qubit `CCNOT`, so the
   smallest interesting Grover instance (N=16, M=1, 3 iterations, P > 96%)
   wouldn't compile. CCZ was also missing as a peer of `CCNOT`. This was
   patched in-place during the demo work; this proposal documents the patch
   as a spec-level commitment instead of a fix that lives only in code.

2. **Action definitions are not parameterizable.** The natural follow-on demo
   (a polysemantic-feature concept-projection machine for d=3 qubits over 12
   non-orthogonal LARQL concepts) wants to write one
   `query_concept | (qs, c: int) -> qs | Hadamard(qs[c])` action and call
   it as `query_concept(0)`, `query_concept(1)`, ..., `query_concept(11)` in
   12 transitions. Today that requires twelve nearly-identical action rows,
   one per concept. The state-machine markdown bloats from O(states + concepts)
   to O(states × concepts), pushing realistic polysemy demos past the
   "one screen of YAML" affordance the language is otherwise designed for.

The two halves go together because the parametric-action expansion needs the
multi-controlled gate set to stay closed under expansion: once a single
`oracle(c: int)` action can stamp out 12 copies of an MCX-bearing effect
string, the spec and the implementation need to agree that MCX is in the
recognized gate set.

## What Changes

**Multi-controlled gate set (already implemented; this proposal documents it):**

- The effect grammar SHALL recognize three- and many-controlled gates:
  `CCX(c0, c1, t)` / `CCNOT` / `Toffoli` / `CCZ` (3-arg, two controls + one
  target) and `MCX(c0, c1, ..., t)` / `MCZ(c0, c1, ..., t)` (variable arity,
  ≥ 3 args, last argument is the target).
- The Qiskit and QASM compilers SHALL emit these gates: QASM via
  `ccx`/`ctrl(N) @ x` (with H-sandwich for the Z variants), Qiskit via
  `qc.ccx` / `qc.mcx` (with H-sandwich for the Z variants).
- The Qiskit script SHALL transpile the generated circuit to a fixed basis
  before running on `BasicSimulator`, because that backend does not
  natively execute `mcx`.
- The verifier SHALL accept `CCZ`, `MCX`, `MCZ` as known unitary gate kinds
  for the Stage-4 unitarity check.

**Parametric action signatures (new design; this proposal proposes them):**

- An action signature SHALL accept zero or more typed parameters in addition
  to the leading qubit-list parameter. Initial supported types: `int` (used
  in qubit-list subscripts) and `angle` (used in rotation-gate angle slots).
- The transitions table's `Action` cell SHALL accept the call form
  `action_name(arg1, arg2, ...)` with literal integer or angle arguments, in
  addition to the existing bare-name form.
- The compiler SHALL substitute bound parameter values into the action's
  effect string at the *point of use* (one expansion per call site) and
  parse the resolved effect with the existing gate-effect parser. There is
  no runtime parameter binding; parameters are compile-time constants.
- The static and dynamic verifiers SHALL run their existing checks on the
  *expanded* gate sequences, not on the action template. An unbound
  parameter or an out-of-range subscript SHALL produce a structured
  parse-time error.

This change does **not**:

- Add runtime / context-bound action parameters (would require true
  conditional execution of gate sequences mid-circuit, out of scope).
- Add default parameter values, variadic parameters, or named-argument
  call syntax. Initial scope is positional, fully-bound calls only.
- Generalize the `qs[c]` subscript grammar beyond a single bound integer
  parameter per slot (no `qs[c+1]`, no `qs[2*c]`).
- Change the existing `parameter` field on `QuantumGate` (the rotation
  angle stored on the AST). "Action parameter" is a distinct, new concept.

## Capabilities

### New Capabilities

None. Both halves refine existing capabilities.

### Modified Capabilities

- `language`: the gate effect grammar gains CCX/CCZ/MCX/MCZ as recognized
  syntactic forms. The action-section grammar gains typed positional
  parameters in the signature; the transitions-table grammar gains the
  `action_name(args)` call form.
- `compiler`: the shared gate-kind coverage requirement extends to
  CCZ/MCX/MCZ across QASM and Qiskit emission. A new requirement governs
  parameter binding and expansion at compile time. The Qiskit-script
  emission requirement adds a transpile-to-basis step before the shots run.
- `verifier`: the static (`quantum`) stage's known-unitary set extends to
  CCZ/MCX/MCZ. A new requirement governs verification of expanded action
  call sites — checks run on the per-call-site expanded gate sequence, not
  the template.

## Impact

**Code already shipped (multi-controlled gates):**

- `q_orca/compiler/qiskit.py` — `_parse_single_gate` recognizes CCX/CCNOT/
  Toffoli/CCZ (3-arg) and MCX/MCZ (variable arity); `_gate_to_qiskit`
  emits each; the script emission adds a `transpile` pass keyed to
  `BasicSimulator`'s basis gates.
- `q_orca/compiler/qasm.py` — `_gate_to_qasm` emits CCZ, MCX, MCZ via
  `ccx` / `ctrl(N) @ x` with H-sandwich for the Z variants.
- `q_orca/verifier/quantum.py` — `KNOWN_UNITARY_GATES` includes CCZ, MCX,
  MCZ.
- `examples/larql-gate-knn-grover.q.orca.md` — exercises the path
  end-to-end.
- `demos/larql_gate_knn/demo.py` — runs the full pipeline.

**Code to be written (parametric actions):**

- `q_orca/parser/markdown_parser.py` — signature parser accepts
  `(qs, name: type, ...)`; transition Action column accepts `name(args)`.
- `q_orca/effect_parser.py` (post `consolidate-gate-parser`) or
  `q_orca/compiler/qiskit.py` — accept identifier subscripts (`qs[c]`)
  alongside literal subscripts (`qs[0]`); add a parameter-binding pass
  that substitutes literals into a copied effect string before gate
  parsing.
- `q_orca/ast.py` — `QActionSignature` gains a list of typed parameters;
  `QTransition.action` gains a list of bound argument values.
- `q_orca/verifier/*` — verification stages iterate expanded call sites
  instead of action definitions when collecting gate sequences.

**Tests:**

- `tests/test_parser.py` — multi-controlled effect parsing; parametric
  signature/call parsing; out-of-range and unbound-parameter errors.
- `tests/test_compiler.py` — QASM and Qiskit emission for CCZ/MCX/MCZ
  and for parameterized action call sites.
- `tests/test_verifier.py` — unitarity check passes for expanded MCX/MCZ
  sequences and for multiple expansions of the same parametric action.
- `tests/test_examples.py` — the existing Grover example and a new
  polysemantic-12 example are pulled in.

**Examples:**

- Already present: `examples/larql-gate-knn-grover.q.orca.md`.
- Sketched as
  `openspec/changes/extend-gate-set-and-parametric-actions/sketches/larql-polysemantic-concept.q.orca.md`
  (the 2-qubit / 2-concept sketch produced during this work; lives under
  the change rather than `examples/` because it is illustrative of the
  proposed parametric-action shape and not yet a verification-clean
  example).
- Proposed follow-on: `examples/larql-polysemantic-12.q.orca.md` — the
  3-qubit / 12-concept polysemy machine that motivates the parametric
  action work, blocked on this change.

**Dependencies**: none added. The Qiskit transpile call is already part of
the existing Qiskit dependency.

**Backwards compatibility**: the multi-controlled gate set is purely
additive. The parametric-action signature parser must accept the existing
zero-parameter `(qs) -> qs` form unchanged — every example in tree today
uses that form. Bare-name action references in the transitions table
remain valid; the `name(args)` call form is opt-in per row.
