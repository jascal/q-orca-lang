## Context

Rotation gate support is already partially implemented across the
Q-Orca stack. The AST has the field, the verifier has the gate kinds,
both compilers emit the right code. The problem is exclusively at the
parsing seams and in the lack of tests.

Two concrete bugs exist in the current code:

1. **Parser gap**: `q_orca/parser/markdown_parser.py::_parse_gate_from_effect`
   only matches `Hadamard`, `CNOT`, and a single-letter `[A-Z][a-z]*`
   gate pattern that covers `X/Y/Z/H/T/S` but not `Rx/Ry/Rz`. The
   rotation gates fall through and the action's `gate` field is `None`.

2. **Argument order divergence**:

   ```python
   # q_orca/verifier/dynamic.py:144
   re.search(r"(Rx|Ry|Rz)\((\w+)\[(\d+)\]\s*,\s*([\w.]+)\s*\)", effect_str)
   # Accepts: Rx(qs[0], 1.5708)

   # q_orca/compiler/qiskit.py:58
   re.search(r"R([XYZ])\(\s*([\w./\-]+)\s*,\s*\w+\[(\d+)\]\s*\)", effect_str)
   # Accepts: Rx(1.5708, qs[0])
   ```

Neither parser handles symbolic angles — both call `float(param_str)`
and fall through to `0.0` on failure.

## Goals / Non-Goals

**Goals:**

- Single canonical syntax for rotation gates across parser, both
  compilers, and the dynamic verifier.
- Parser populates `action.gate` for rotation gates so downstream
  analysis works off the AST, not the raw effect string.
- A small, well-defined symbolic angle grammar that fails loudly on
  anything it cannot evaluate.
- At least one executable example (`examples/vqe-rotation.q.orca.md`)
  exercising the full path: parse → verify → compile → simulate.

**Non-Goals:**

- No parameter binding in the transitions table (e.g. `γ=π/4` columns).
  Parameters remain literal angle values in the action effect.
- No general-purpose expression evaluator. Only the bounded angle
  forms listed below are supported.
- No new `angle` type in the context-field grammar. If a user wants
  to share an angle, they copy it across effect strings — we'll
  revisit this when QAOA forces the issue.
- No controlled rotation gates (`CRx`, `CRy`, `CRz`). Separate change
  if and when needed.

## Decisions

### Canonical syntax: qubit first, angle second

```
Rx(qs[0], pi/4)
```

Rationale: matches `CNOT(qs[0], qs[1])` and `SWAP(qs[0], qs[1])` where
the qubit arguments come first, matches the `(qs) -> qs` signature
convention in the actions table (qubit register is the receiver),
matches the dynamic verifier's existing regex (one fewer file to
change), and reads left-to-right as "rotate this qubit by this angle".

The Qiskit compiler's current angle-first parser is wrong. It will be
updated.

### Symbolic angle grammar

The accepted forms, in order of parser precedence:

1. A decimal literal: `1.5708`, `-0.5`, `3.14159`
2. The bare symbol `pi`, representing π
3. `pi/<integer>`: `pi/2`, `pi/4`, `pi/8`
4. `<integer>*pi` or `<integer>pi`: `2*pi`, `2pi`
5. `<integer>*pi/<integer>`: `3*pi/4`
6. A leading minus sign on any of the above

An `_evaluate_angle(text: str) -> float` helper returns a Python float
or raises `ValueError` on anything else. The parser wraps this into a
`QuantumGate.parameter` value. The Qiskit and QASM backends emit the
evaluated float — there is no need to propagate the symbolic form
since the downstream artifacts don't need to round-trip back to
Q-Orca markdown.

**Future extension**: when the context-field angle-reference feature
lands, the grammar will add a form `<identifier>` resolved against
the context. For now that path raises `ValueError`.

### Error behavior

Any rotation-gate effect that doesn't match the canonical grammar —
wrong argument order, unrecognized symbolic form, missing
parentheses — SHALL produce a parser error surfaced through
`QParseResult.errors` (or equivalent). Silent `0.0` fallback is gone.

Rationale: the current silent-fallback behavior is exactly how the
argument-order bug hid for this long. An explicit error on an
unrecognized angle protects future users from the same class of bug.

### Test strategy

- **Unit**: `tests/test_parser.py` gets a parametrized block covering
  each grammar form (decimal, `pi`, `pi/4`, `2*pi`, `3*pi/4`, negative
  variants) and one known-bad case (bare identifier) that asserts the
  error.
- **Regression**: `tests/test_regression.py` gets one test that parses
  a rotation machine, compiles to both QASM and Qiskit, and asserts
  the text contains the expected emitted gate strings.
- **End-to-end**: new `tests/test_vqe_rotation.py` runs the
  `vqe-rotation.q.orca.md` example through parse → verify → compile →
  QuTiP simulate and asserts the final state vector matches
  `Rx(θ)|0>` to 1e-6 for θ = π/4.

## Risks / Trade-offs

- **External breakage**: any external user who wrote machines against
  the Qiskit-compiler's angle-first parser will see those machines
  break. We don't have an authoritative user base to survey, and the
  behavior was never documented. The CHANGELOG notes the break.
- **Symbolic grammar scope creep**: the narrow grammar here will look
  too restrictive the first time someone writes QAOA. The proposal
  intentionally pushes the broader context-reference form to a later
  change, because QAOA also needs loops, and the two should be
  designed together.
- **Qubit-first vs angle-first taste**: the canonical order is a
  taste call. If industry convention (e.g. Qiskit's `qc.rx(theta, q)`)
  argues for angle-first, we override in favor of Q-Orca's own
  internal consistency. Worth noting in the CHANGELOG so people
  coming from Qiskit know what to expect.
- **Float precision**: `pi/4` evaluates to `0.7853981633974483` in
  Python. Round-trip tests that compare emitted QASM strings
  byte-for-byte will need to assert against the exact float literal
  or normalize. The regression test in `tests/test_regression.py`
  will normalize.
