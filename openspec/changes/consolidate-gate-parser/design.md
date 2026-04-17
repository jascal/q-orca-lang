## Context

Three independent effect-string parsers grew in parallel over several
changes: the original markdown parser produced `QuantumGate` AST nodes,
the Qiskit compiler added its own parser to re-derive gates from action
effects at compile time, and the dynamic verifier added a third parser
that produces a lighter-weight dict because it never needed the full
AST node. Each site started from a copy of the others' regex block and
diverged independently as new gate kinds (CNOT/CZ/SWAP/Rx/Ry/Rz, then
RXX/RYY/RZZ/CRx/CRy/CRz) were added.

The three sites share a single angle evaluator (`q_orca.angle`) because
the context-angle-references change forced that consolidation, but the
regex block and the order in which cases are tried remained independent.

## Goals / Non-Goals

**Goals:**

- One file owning gate-effect-string parsing. Adding a new gate kind is
  a one-line regex edit in that file, not a coordinated change across
  three.
- Call-site adapters that translate the shared output into each site's
  preferred shape (`QuantumGate`, gate-dict). Each adapter is small
  enough to audit in one read.
- Regex ordering, anchoring, and case-insensitivity become
  properties of the shared parser, not per-site accidents.
- Shared test fixtures so a new gate kind is forced to exercise parser,
  compiler, and verifier with one pytest parametrize.

**Non-Goals:**

- A new parser combinator / pyparsing / Lark grammar. The current
  regex-per-gate-kind fallthrough is fine at the scale we have today.
  If we outgrow it, that is a separate change with its own proposal.
- Changing the AST or verifier gate-dict shape.
- Moving angle evaluation. `q_orca.angle.evaluate_angle` stays where it
  is; the shared parser calls it exactly like the three sites do today.
- Generalizing to non-gate effect clauses (e.g. `MEASURE(qs[N])`
  appears in the verifier's parser but is handled as a single-qubit
  fallback today — keep that).

## Decisions

### Decision 1 — New top-level module `q_orca/effect_parser.py`

Place the shared parser at `q_orca/effect_parser.py`, not inside
`q_orca/parser/` or `q_orca/compiler/`. It is consumed by parser,
compiler, and verifier, so nesting it under any one of those creates
misleading import graphs. Top-level matches the precedent set by
`q_orca/angle.py`.

Alternative considered: put it in `q_orca/ast.py` as a classmethod on
`QuantumGate`. Rejected because the verifier uses dicts, not AST
nodes, and adding AST-construction hooks inside a data class crosses a
layer boundary we currently respect.

### Decision 2 — `ParsedGate` as the shared intermediate

Return a small dataclass with fields covering every site's needs:

```python
@dataclass(frozen=True)
class ParsedGate:
    name: str                       # canonical case: "H", "CNOT", "RZZ", "CRX"
    targets: tuple[int, ...]
    controls: tuple[int, ...]
    parameter: float | None
```

Each adapter translates `ParsedGate` into its preferred shape:

- Markdown parser adapter → `QuantumGate(kind=name, targets=list(targets), controls=list(controls), parameter=parameter)`
- Qiskit compiler adapter → same as above.
- Dynamic verifier adapter → `{"name": name, "targets": list(targets), "controls": list(controls), "params": {"theta": parameter} if parameter is not None else {}}`

`ParsedGate` is immutable so the three adapters can share an instance
without copying.

Alternative considered: return `QuantumGate` directly, force the
verifier to destructure. Rejected because it pins the shared parser to
the AST module and adds an import that dictates load order.

### Decision 3 — Gate-kind table drives the regex fallthrough

Today the regex block is hand-written: one `re.search` per gate kind,
with case-insensitivity and anchoring applied inconsistently. Replace
it with a small table:

```python
_GATE_PATTERNS: list[tuple[str, re.Pattern, Callable[[re.Match], ParsedGate]]] = [
    ("Hadamard", re.compile(r"^Hadamard\(\s*\w+\[(\d+)\]\s*\)", re.IGNORECASE), _build_h),
    ("CNOT",     re.compile(r"^(?:CNOT|CX)\(...\)", re.IGNORECASE), _build_cnot),
    # ...
    ("two-qubit parameterized", re.compile(r"^(CRx|...|RZZ)\(...\)", re.IGNORECASE), _build_two_qubit_param),
    ("single-qubit rotation",   re.compile(r"^(Rx|Ry|Rz)\(...\)",     re.IGNORECASE), _build_single_qubit_rotation),
    ("pauli",                   re.compile(r"^([XYZS])\(...\)"),       _build_pauli),
    ("generic single-qubit",    re.compile(r"^([A-Za-z]+)\(...\)"),    _build_generic_single_qubit),
]
```

The parser walks the table in order and returns the first match. Order
is the *only* place regex ordering lives — the bug that shipped on PR
#11 (CRx matching Rx via substring) is impossible because all patterns
are anchored with `^` by construction.

Alternative considered: a single union regex with named groups.
Rejected because disambiguating the match branch from the group that
fired is awkward and obscures the fallthrough order.

### Decision 4 — Migrate in layers, not all at once

The three call sites are independent: each adapter can be introduced
without touching the other two. Sequence the migration:

1. Ship `q_orca/effect_parser.py` + its own tests. No call-site
   changes yet; behavior is unchanged.
2. Migrate the dynamic verifier first (thinnest adapter, most recent
   bug source).
3. Migrate the Qiskit compiler.
4. Migrate the markdown parser.
5. Delete the original regex blocks and the TODO comment.

Each step is its own commit, each step leaves the test suite green,
and bisect remains useful if a downstream consumer breaks.

Alternative considered: a single big commit replacing all three. This
is what we'd normally do for a refactor of this size, but we have
burned evidence that this exact refactor is subtle. Stepping it lets
us catch regressions mid-migration with smaller blast radius.

### Decision 5 — Shared test fixture

Add `tests/fixtures/effect_strings.py` with a list of
`(effect_str, expected_ParsedGate)` pairs exercising every gate kind
and every syntactic slot (qubit-only, with-angle, with-controls,
literal-angle, context-ref-angle). The shared fixture is imported by:

- `tests/test_effect_parser.py` — tests the shared parser directly.
- `tests/test_parser.py` — parametrized over the fixture, tests
  `_parse_gate_from_effect` produces the expected `QuantumGate`.
- `tests/test_compiler.py` — parametrized, tests the Qiskit compiler's
  adapter produces the expected `QuantumGate`.
- `tests/test_verifier.py` — parametrized, tests the dynamic verifier's
  adapter produces the expected gate-dict.

Adding a new gate kind then means appending one fixture entry and
watching four test files light up simultaneously.

## Risks / Trade-offs

- **Risk:** The three adapters produce subtly different shapes today
  (case of `name`, order of `targets`/`controls`, whether `params` is
  empty dict vs `{"theta": 0.0}` when angle is absent).
  **Mitigation:** characterize current behavior with parametrized
  tests *before* the refactor. Each adapter's tests become the
  contract the adapter must satisfy.

- **Risk:** The markdown parser's current `_parse_gate_from_effect` has
  error-reporting side effects (appends to `errors` list). The shared
  parser needs a way to surface parse failures without coupling to the
  caller's error sink.
  **Mitigation:** the shared parser returns `None` on no-match; the
  adapter converts `None` into the caller's error shape. Parse errors
  that the shared parser can detect (invalid int, angle out of
  context) are returned as a structured error in the adapter's call.

- **Risk:** `q_orca/compiler/qasm.py` imports from
  `q_orca/compiler/qiskit.py` today. After the refactor, it can import
  from `q_orca/effect_parser.py` directly instead.
  **Mitigation:** handle as part of step 3. Both approaches keep the
  public surface stable.

- **Risk:** A user of the library imports `_parse_single_gate_to_dict`
  directly. This is a private symbol but the underscore is not
  enforced.
  **Mitigation:** keep the private symbols as thin wrappers around the
  adapter for one release, flagged with a deprecation comment. Remove
  in the next change.

## Open Questions

- Should `ParsedGate.name` be normalized to a canonical case (always
  uppercase, always `"CRX"` not `"CRx"`), or should it preserve source
  case like the markdown parser does today? The AST uses mixed case
  (`"Rx"`, `"CRx"`) and the dict shape uses uppercase (`"RX"`, `"CRX"`).
  The adapters can normalize differently — proposing lowercase-in,
  canonical-out on the shared layer and letting each adapter map to
  its site's convention. Revisit in implementation if the mapping gets
  ugly.
