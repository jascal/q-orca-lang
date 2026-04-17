# Tasks: Context-Field Angle References

## 1. Extend the angle evaluator
- [x] 1.1 Add an optional `context: Mapping[str, float] | None = None`
      parameter to `q_orca.angle.evaluate_angle`.
- [x] 1.2 After the existing literal/`pi` cases fall through, try the
      context-reference forms in order: `name*pi` / `pi*name`,
      `<int>*name` (covers `2gamma`), `name/<int>`, bare identifier.
- [x] 1.3 Refine the final `ValueError` message to include the
      identifier list when context is provided, plus the accepted
      compound forms.
- [x] 1.4 Add unit tests in `tests/test_parser.py::TestEvaluateAngle`
      covering each new form, the literal-shadowing rule, the
      "available identifiers" error, and the no-context backwards
      compatibility.

## 2. Thread context through the markdown parser
- [x] 2.1 Add helper `_build_angle_context(context_fields)` in
      `q_orca/parser/markdown_parser.py` that returns
      `{name: float(default)}` for `int`/`float` fields with numeric
      defaults.
- [x] 2.2 Update `_parse_actions_table` to take and forward
      `angle_context`.
- [x] 2.3 Update `_parse_gate_from_effect` and
      `_parse_conditional_gate_from_effect` to accept and pass
      `angle_context` into `_evaluate_angle`.
- [x] 2.4 In `_parse_machine_chunk`, pre-scan elements for the
      `## context` table so the angle map is available regardless of
      section order, then pass it into `_parse_actions_table`.
- [x] 2.5 Add tests in `tests/test_parser.py::TestContextAngleReferences`
      covering bare identifier, compound forms, two-qubit gates, error
      on missing identifier, error on non-numeric field.

## 3. Update the Qiskit compiler effect parser
- [x] 3.1 In `q_orca/compiler/qiskit.py`, mirror `_build_angle_context`
      and pass it to every `evaluate_angle` call inside
      `_parse_effect_string`.
- [x] 3.2 Update `_extract_gate_sequence` to build and forward the
      angle context to `_parse_effect_string`.
- [x] 3.3 Update `q_orca/compiler/qasm.py::_extract_gate_sequence` to
      do the same (it reuses `_parse_effect_string` from the Qiskit
      module).
- [x] 3.4 Add regression tests in
      `tests/test_compiler.py::TestContextAngleCompilation` for both
      QASM and Qiskit backends.

## 4. Update the dynamic verifier effect parser
- [x] 4.1 In `q_orca/verifier/dynamic.py`, add `_build_angle_context`
      and pass its output through `_build_gate_sequence` →
      `_parse_effect_to_gate_dicts` → `_parse_single_gate_to_dict` →
      `evaluate_angle`.
- [x] 4.2 Add a regression test in
      `tests/test_verifier.py::TestContextAngleDynamicVerifier` that
      verifies a machine using a context-field angle.

## 5. Update example files
- [x] 5.1 `examples/vqe-rotation.q.orca.md`: add a `theta` context
      field with default `0.7853981633974483` (≈π/4) and switch the
      action to `Rx(qs[0], theta)`.
- [x] 5.2 `examples/qaoa-maxcut.q.orca.md`: switch cost-layer `RZZ`
      calls to use `gamma` and mixer-layer `Rx` calls to use `beta`.
- [x] 5.3 `examples/vqe-heisenberg.q.orca.md`: already references
      `theta` in its action; with this change it now resolves correctly
      against the existing `theta` context field instead of failing.
- [x] 5.4 The existing
      `tests/test_verifier.py::TestEndToEndVerification::test_verify_all_examples`
      iterates every example and is the regression net for spec 5.

## 6. Spec consistency
- [x] 6.1 `openspec validate context-angle-references --strict` →
      "Change 'context-angle-references' is valid".
- [x] 6.2 Full pytest suite green: 404 passed, 4 skipped.
