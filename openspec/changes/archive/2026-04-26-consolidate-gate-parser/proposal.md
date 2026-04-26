## Why

Gate-effect-string parsing is implemented three times across the
codebase:

- `q_orca/parser/markdown_parser.py::_parse_gate_from_effect` — produces
  `QuantumGate` AST nodes.
- `q_orca/compiler/qiskit.py::_parse_single_gate` — produces
  `QuantumGate` for the Qiskit and QASM compilers.
- `q_orca/verifier/dynamic.py::_parse_single_gate_to_dict` — produces
  `{name, targets, controls, params}` dicts for the dynamic verifier.

The three implementations were kept in sync by hand. PR #11
(context-angle-references) shipped two bugs from that drift in the span
of one review:

1. **RZZ silently dropped** (commit `d0d274c`): the dynamic verifier's
   parser had no branch for `RXX/RYY/RZZ` or `CRx/CRy/CRz`, so every
   two-qubit parameterized gate returned `None` and disappeared from the
   gate sequence. `verify()` returned `valid=True` on circuits that
   simulated nothing.
2. **CRx/CRy/CRz demoted to bare rotations** (commit `f279d3e`): the
   single-qubit `Rx|Ry|Rz` regex was unanchored and evaluated before the
   two-qubit branch, so `CRx(qs[0], qs[1], beta)` matched the embedded
   substring `Rx(qs[0], qs[1], beta)` and silently lost its control
   qubit and context-resolved angle.

Both bugs were invisible to tests because the three sites were tested
independently — the verifier's parser had no coverage for two-qubit
parameterized gates at all. Neither site reused the others' test
fixtures, so regression tests for one never exercised the others.

The TODO left at
`q_orca/verifier/dynamic.py::_parse_single_gate_to_dict` captures this
problem in-source. This change consolidates the three implementations
into one shared parser so the next gate type added (or the next regex
reordering) can't introduce this class of bug.

## What Changes

- Introduce `q_orca/effect_parser.py` containing:
  - `parse_effect_string(effect_str, angle_context) -> list[ParsedGate]`
  - `parse_single_gate(effect_str, angle_context) -> ParsedGate | None`
  - A typed `ParsedGate` dataclass with `name`, `targets`, `controls`,
    `parameter` fields — enough information for every caller.
- Migrate all three call sites to the shared parser:
  - `markdown_parser.py::_parse_gate_from_effect` becomes a thin
    adapter producing `QuantumGate` from `ParsedGate`.
  - `compiler/qiskit.py::_parse_single_gate` becomes a thin adapter
    producing `QuantumGate`.
  - `verifier/dynamic.py::_parse_single_gate_to_dict` becomes a thin
    adapter producing the gate-dict shape the evolver expects.
- Centralize the regex ordering (two-qubit parameterized before
  single-qubit rotation, anchored patterns) so adding a new gate kind
  means editing one file, not three.
- Share a canonical test fixture of effect strings exercising every gate
  kind in every syntactic slot. Every call-site adapter's test suite
  includes it via parametrize.
- Remove the TODO comment at
  `q_orca/verifier/dynamic.py::_parse_single_gate_to_dict`.

## Capabilities

### New Capabilities
None. This is a refactor of existing capability.

### Modified Capabilities
- `compiler`: the canonical rotation/parametric gate syntax SHALL be
  parsed by a single shared function; the existing guarantee that
  parser, Qiskit compiler, and dynamic verifier agree on gate shape is
  strengthened from "by convention" to "by construction."
- `verifier`: the dynamic verifier's effect-string parser SHALL delegate
  to the shared implementation; new gate kinds added to the shared
  parser become verifiable without a per-site edit.

## Impact

- `q_orca/effect_parser.py` — new file, ~150 lines.
- `q_orca/parser/markdown_parser.py` — `_parse_gate_from_effect` reduces
  to a ~20-line adapter; effect-parsing regexes removed.
- `q_orca/compiler/qiskit.py` — `_parse_single_gate` and
  `_parse_effect_string` reduce to adapters; regex block removed.
- `q_orca/compiler/qasm.py` — already delegates to the Qiskit module;
  no change beyond inheriting the consolidated behavior.
- `q_orca/verifier/dynamic.py` — `_parse_single_gate_to_dict` and
  `_parse_effect_to_gate_dicts` reduce to adapters; the TODO block is
  removed.
- `tests/` — a shared fixture `tests/fixtures/effect_strings.py` feeds
  parametrized tests in `test_parser.py`, `test_compiler.py`,
  `test_verifier.py`, and a dedicated `test_effect_parser.py`.
- No runtime dependency changes. No user-visible behavior changes
  beyond the two bugs already fixed on PR #11 remaining fixed.

## Non-Goals

- Changing the accepted gate syntax. Anything that parses today still
  parses. Anything that errors today still errors with the same
  structured message.
- Changing `QuantumGate` AST shape, or the verifier gate-dict shape.
  The adapters preserve both.
- Expanding the supported gate set. That is a separate change and a
  prime example of *why* we want this consolidation in place first.
