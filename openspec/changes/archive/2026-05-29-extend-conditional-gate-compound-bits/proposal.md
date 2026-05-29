## Why

`examples/bit-flip-syndrome.q.orca.md` silently produces wrong
quantum results. The 3-qubit bit-flip code maps the four syndrome
patterns to four corrections — `(0,0)` → no error, `(1,0)` → q0,
`(1,1)` → q1, `(0,1)` → q2. The example only ships two correction
actions (`correct_q0: if bits[0] == 1: X(qs[0])` and
`correct_q2: if bits[1] == 1: X(qs[2])`), so under syndrome `(1,1)`
both actions fire on the wrong qubits and q1 stays flipped — a
logical X applied for ~25% of single-qubit error patterns. The
example "verifies valid" because today's parser cannot express the
correct fix (`if bits[0] == 1 and bits[1] == 1: X(qs[1])`) and the
verifier's `feedforward_completeness` rule only checks that every
*measured bit* drives some correction, not that every `2^N` syndrome
pattern is handled.

The proper fix is structural: extend `QEffectConditional` to carry a
list of `(bit_idx, value)` conditions joined by AND, teach the parser
to recognize the `if bits[i] == v and bits[j] == w: …` shape, teach
both compilers (OpenQASM and Qiskit) to emit the conjoined branch,
and update the example so all four syndrome patterns map to the
correct correction. The example is the most-cited educational use of
mid-circuit measurement and feedforward in the repo; shipping a
silent bug there is embarrassing and erodes trust in every other
example downstream.

This change is bounded to the AND-of-equalities case actually needed
by syndrome decoding. Disjunction, inequality, and arithmetic on
classical bits are out of scope — they would require a real classical
expression sub-language and are not motivated by any current
example.

## What Changes

- **MODIFIED** `language` capability:
  - `QEffectConditional`'s grammar SHALL accept zero or more
    additional `and bits[<int>] == <0|1>` clauses after the head
    condition, before the `:` and gate body. The conjunction is
    short-circuit AND: the gate fires only when *every* listed bit
    equals its declared value.
  - The AST SHALL carry the full list of `(bit_idx, value)` pairs
    in declaration order. The legacy single-condition form SHALL
    parse identically to a length-1 list.
  - Whitespace SHALL be flexible (`bits[0]==1 and bits[1] == 1`,
    `bits[0] == 1  and  bits[1]==1`, etc.).
  - Duplicate `bits[i]` clauses with conflicting values SHALL be
    rejected as a parse error (the gate would never fire).

- **MODIFIED** `compiler` capability:
  - The OpenQASM 3.0 emitter SHALL emit `if (c[i] == v && c[j] == w)
    { gate; }` for compound conditions (OpenQASM 3.0 supports `&&`).
  - The Qiskit emitter SHALL emit nested `with qc.if_test((c[i], v)):`
    blocks — one for each clause, innermost wrapping the gate. This
    produces the same short-circuit semantics as a single conjoined
    test without depending on Qiskit AST features that vary across
    versions.
  - Resource estimation SHALL count a compound conditional gate as a
    single gate (the conjunction is classical control flow, not extra
    quantum operations).

- **MODIFIED** `verifier` capability:
  - `feedforward_completeness` SHALL register *every* bit referenced
    by a compound condition, not just the head. Today
    `q_orca/verifier/quantum.py:388-389` only adds
    `conditional_gate.bit_idx`; it SHALL iterate the full list.
  - Existing per-bit "every measured bit drives a correction"
    semantics are preserved.

## Capabilities

### Modified Capabilities

- `language` — `QEffectConditional` accepts AND-conjoined bit
  conditions
- `compiler` — OpenQASM and Qiskit emit compound conditions
- `verifier` — feedforward completeness registers every conjoined
  bit

## Impact

- `q_orca/ast.py` — `QEffectConditional` gains
  `conditions: list[tuple[int, int]]`. The legacy `bit_idx`/`value`
  fields are derived from `conditions[0]` for backward compatibility
  with read-only consumers; new code SHALL prefer `conditions`.
- `q_orca/parser/markdown_parser.py::_parse_conditional_gate_from_effect`
  — extended regex / parsing to recognize the `and` chain; emits a
  parse error on conflicting clauses.
- `q_orca/compiler/qasm.py` — `_emit_conditional_gate` joins the
  clause list with `&&`.
- `q_orca/compiler/qiskit.py` — emits nested `if_test` blocks.
- `q_orca/compiler/resources.py` — confirm conditional gates count as
  one gate regardless of clause count (no change expected; pin with
  test).
- `q_orca/verifier/quantum.py` — feedforward iterates the full
  clause list.
- `examples/bit-flip-syndrome.q.orca.md` — tighten existing
  conditions to "this bit set AND the other clear," add
  `correct_q1: if bits[0] == 1 and bits[1] == 1: X(qs[1])`, add a
  fourth correction transition to chain it in. The example now
  produces a genuine logical-X-corrected state under all four
  syndrome patterns.
- `tests/test_bit_flip_syndrome.py` — new behavior test asserting
  all four `(b0, b1)` syndrome patterns end with the data register
  in the correct logical state via the Qiskit backend.
- `tests/test_parser.py`, `tests/test_compiler.py`, `tests/test_verifier.py`
  — unit coverage for the new shapes.

No breaking changes for examples that use only the legacy
single-condition form — they continue to parse, verify, and compile
unchanged.
