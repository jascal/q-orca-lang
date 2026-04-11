## Why

Parameterized single-qubit rotation gates (`Rx(θ)`, `Ry(θ)`, `Rz(θ)`) are
on the README's near-term roadmap and are called out in
`openspec/roadmap/coverage-analysis-v0.4.md` §4.2 as the enabling
prerequisite for QAOA, VQE extensions, hardware-efficient ansätze, and
quantum phase estimation. Reading the current code shows that rotation
gate support is already **half-plumbed**:

- `QuantumGate.parameter: Optional[float]` exists on the AST
  (`q_orca/ast.py:20`)
- The static verifier already lists `Rx/Ry/Rz` in
  `KNOWN_UNITARY_GATES` (`quantum.py:10`) and `SUPERPOSITION_GATES`
  (`superposition.py:19`)
- The QASM backend emits `rx(θ) q[i];` (`qasm.py:116`)
- The Qiskit backend emits `qc.rx(θ, i)` (`qiskit.py:406`)
- The dynamic verifier evolves the circuit through QuTiP (`dynamic.py:143`)

What's missing is at the seams:

1. The **markdown parser's** `_parse_gate_from_effect` does not recognize
   `Rx/Ry/Rz`, so `action.gate` on the AST is always `None` for rotation
   gates. Any pass that reads the gate off the action (rather than
   re-parsing the effect string) silently drops them.
2. The two effect-string parsers **disagree on argument order**. The
   dynamic verifier expects `Rx(qs[N], theta)` (qubit first).
   The Qiskit compiler expects `Rx(theta, qs[N])` (angle first). No
   example currently uses rotation gates, so this latent bug has never
   fired.
3. **Symbolic angles** (`pi/4`, `theta`, named context references)
   silently fall through to `0.0` in both parsers, producing wrong
   circuits with no error.
4. **Zero tests** touch rotation gates.

This change reconciles the seams, fixes the argument-order bug, supports
a small set of symbolic angles, and ships a VQE-rotation example to
exercise the path end-to-end.

## What Changes

1. **Canonical syntax**: pick and document
   `Rx(qs[N], theta)` — qubit first, angle second — to match the
   convention for CNOT/CZ/SWAP and the signature column in the actions
   table. Update the Qiskit compiler's parser to accept this order.
2. **Parser**: extend `_parse_gate_from_effect` in
   `q_orca/parser/markdown_parser.py` to recognize the canonical form
   and populate `QuantumGate(kind="Rx"|"Ry"|"Rz", targets=[N], parameter=theta)`.
3. **Symbolic angles**: support a small bounded grammar for angle
   expressions — bare numbers, `pi`, `pi/k`, `k*pi`, `pi/k * n` — in
   both the parser and the compiler's effect parser. Non-recognized
   symbolic expressions SHALL produce a parse error (fail loud, not
   silently coerce to `0.0`).
4. **Tests**: add unit coverage for the new parser paths and at least
   one end-to-end test that compiles a rotation-gate machine to Qiskit
   and confirms the resulting circuit matches a QuTiP-computed state
   vector.
5. **Example**: add `examples/vqe-rotation.q.orca.md`, a minimal
   single-qubit variational example that rotates `|0>` by a declared
   angle and measures. Intentionally narrower than the full
   `vqe-heisenberg.q.orca.md` to keep scope focused on exercising
   rotation gates.

This change does **not**:

- Add loop annotations (separate change, the natural follow-up)
- Add QAOA or Grover examples (blocked on loops)
- Add a parameter-binding syntax in the transitions table (deferred
  until there is a real use case beyond VQE rotation)
- Extend the context-field grammar with an angle-reference shorthand

## Capabilities

### Modified Capabilities

- `language`: the gate effect grammar MODIFIES to recognize rotation
  gates with symbolic or numeric angles. File-level requirement around
  "Rotation gates not yet recognized by AST parser (known limitation)"
  is retired.
- `compiler`: the shared gate kind coverage requirement MODIFIES to
  document the canonical rotation-gate argument order and the
  symbolic-angle grammar. The "Parameterized Gate Handling (Current
  Gap)" requirement is retired.

### New Capabilities

None. All changes refine existing capabilities.

## Impact

**Code**:

- `q_orca/parser/markdown_parser.py` — `_parse_gate_from_effect`
- `q_orca/compiler/qiskit.py` — `_parse_single_gate` (argument order)
- `q_orca/verifier/dynamic.py` — `_parse_single_gate_to_dict` (already
  matches the canonical order; update any stale regex)
- Symbolic angle evaluator — new small module or inline helper in the
  parser

**Tests**:

- `tests/test_parser.py` — rotation gate parsing
- `tests/test_compiler.py` — rotation gate QASM/Qiskit emission
- `tests/test_regression.py` — symbolic angle round-trip
- New: `tests/test_vqe_rotation.py`

**Examples**:

- New: `examples/vqe-rotation.q.orca.md`

**Dependencies**: none added. The existing QuTiP fallback path
remains.

**Backwards compatibility**: no existing example uses rotation gates,
so the argument-order reconciliation cannot break in-tree code. External
users who wrote machines against the Qiskit-compiler's angle-first
parser will see their machines fail to parse — an acceptable break
given the latent inconsistency.
