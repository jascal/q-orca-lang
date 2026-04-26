# Tasks: Consolidate Gate-Effect-String Parser

## 1. Shared parser module
- [x] 1.1 Create `q_orca/effect_parser.py` with `ParsedGate` dataclass
      (`name: str, targets: tuple[int, ...], controls: tuple[int, ...],
      parameter: float | None`).
- [x] 1.2 Implement `parse_single_gate(effect_str, angle_context) ->
      ParsedGate | None` using a gate-kind-ordered regex table.
      Patterns MUST be anchored with `^` and case-insensitive; two-qubit
      parameterized gates MUST precede single-qubit rotation.
- [x] 1.3 Implement `parse_effect_string(effect_str, angle_context) ->
      list[ParsedGate]` splitting on `;` and calling
      `parse_single_gate` per part.
- [x] 1.4 Every gate kind currently recognized by any of the three
      call-site parsers MUST be covered: H, X, Y, Z, S, T, CNOT/CX, CZ,
      SWAP, CCNOT, CSWAP, Rx, Ry, Rz, RXX, RYY, RZZ, CRx, CRy, CRz.

## 2. Shared test fixture
- [x] 2.1 Create `tests/fixtures/effect_strings.py` with a list of
      `(effect_str, expected_parsed_gate, notes)` tuples covering every
      gate kind.
- [x] 2.2 Include explicit regression cases: `CRx(qs[0], qs[1], beta)`
      produces a `CRX` with `controls=(0,)`, `targets=(1,)`; `RZZ(qs[0],
      qs[1], gamma)` produces an `RZZ` with `targets=(0, 1)`.
- [x] 2.3 Include the shadowing case: `CCNOT(qs[0], qs[1], qs[2])`
      produces a `CCNOT`, not a `CNOT` from a substring match.
- [x] 2.4 Create `tests/test_effect_parser.py` parametrized over the
      fixture asserting `parse_single_gate` returns the expected
      `ParsedGate`.

## 3. Migrate the dynamic verifier (thinnest adapter first)
- [x] 3.1 Rewrite `q_orca/verifier/dynamic.py::_parse_single_gate_to_dict`
      as a thin adapter over `parse_single_gate`, translating
      `ParsedGate` into the gate-dict shape the evolver expects
      (`{"name": name, "targets": [...], "controls": [...], "params":
      {"theta": parameter} if parameter is not None else {}}`).
- [x] 3.2 Rewrite `_parse_effect_to_gate_dicts` as a thin adapter over
      `parse_effect_string`.
- [x] 3.3 Delete the verifier's regex block and the TODO comment at
      `_parse_single_gate_to_dict`.
- [x] 3.4 Extend `tests/test_verifier.py::TestContextAngleDynamicVerifier`
      with a parametrize over the shared fixture covering every gate
      kind's dict-shape output.
- [x] 3.5 Verify the suite still passes (currently 406 tests).

## 4. Migrate the Qiskit compiler
- [x] 4.1 Rewrite `q_orca/compiler/qiskit.py::_parse_single_gate` as a
      thin adapter over `parse_single_gate` building `QuantumGate`.
- [x] 4.2 Rewrite `_parse_effect_string` as a thin adapter over
      `parse_effect_string`.
- [x] 4.3 Verify `q_orca/compiler/qasm.py` still works via its current
      import path, or update it to import from `q_orca/effect_parser.py`
      directly if cleaner.
- [x] 4.4 Extend `tests/test_compiler.py` with a parametrize over the
      shared fixture covering both Qiskit and QASM emission for every
      gate kind.

## 5. Migrate the markdown parser
- [x] 5.1 Rewrite `q_orca/parser/markdown_parser.py::_parse_gate_from_effect`
      as a thin adapter over `parse_single_gate`. Preserve the existing
      error-reporting behavior (appending structured messages to
      `errors`) by translating `None` returns and malformed inputs into
      the caller's error sink.
- [x] 5.2 Remove any redundant effect-parsing regexes from the markdown
      parser.
- [x] 5.3 Extend `tests/test_parser.py` with a parametrize over the
      shared fixture asserting `QuantumGate` AST shape.

## 6. Cleanup & documentation
- [x] 6.1 Delete the now-dead effect-parsing code and any imports that
      are no longer used in the three call-site modules.
- [x] 6.2 Update `openspec/specs/compiler/spec.md` to state that the
      shared parser is the single source of truth for effect-string
      gate parsing. (Authored as MODIFIED Requirement delta in
      `specs/compiler/spec.md`; applied to main spec at archive time.)
- [x] 6.3 Update `openspec/specs/verifier/spec.md` to reference the
      shared parser. (Authored as MODIFIED Requirement delta in
      `specs/verifier/spec.md`; applied to main spec at archive time.)

## 7. Spec consistency
- [x] 7.1 `openspec validate consolidate-gate-parser --strict` is green.
- [x] 7.2 Full pytest suite green (≥ 406 passed, 4 skipped). Now 706 passed, 6 skipped.
- [x] 7.3 Ruff clean across the touched files.

## 8. Follow-up verification
- [x] 8.1 Manually run the pre-PR-#11 regression scenarios: QAOA example
      with `RZZ(qs[0], qs[1], gamma)` produces 3 RZZ gates in the
      verifier; `CRx(qs[0], qs[1], beta)` parses as `CRX` with the
      correct control qubit.
- [x] 8.2 Add `CCNOT(qs[0], qs[1], qs[2])` as a positive test case to
      confirm the CNOT-substring-match risk flagged in the design is
      also ruled out.
