## 1. Multi-controlled gate set (already shipped — record as done)

- [x] 1.1 `q_orca/compiler/qiskit.py::_parse_single_gate` recognizes
      `CCX`/`CCNOT`/`Toffoli`/`CCZ` (3-arg form) and `MCX`/`MCZ`
      (≥3-arg form).
- [x] 1.2 `q_orca/compiler/qiskit.py::_gate_to_qiskit` emits `qc.ccx`
      for `CCNOT`, `qc.h(t); qc.ccx(...); qc.h(t)` for `CCZ`,
      `qc.mcx([controls], target)` for `MCX`, and the H-sandwich
      around `qc.mcx` for `MCZ`.
- [x] 1.3 `q_orca/compiler/qasm.py::_gate_to_qasm` emits `ccx` /
      `h … ccx … h` for the 3-control variants and `ctrl(N) @ x` /
      `h … ctrl(N) @ x … h` for `MCX` / `MCZ`.
- [x] 1.4 `q_orca/verifier/quantum.py::KNOWN_UNITARY_GATES` includes
      `CCZ`, `MCX`, `MCZ`.
- [x] 1.5 The Qiskit script's shots branch imports `transpile` and
      runs it over the measurement-augmented circuit with a fixed
      basis-gate list before invoking `BasicSimulator`.
- [x] 1.6 `examples/larql-gate-knn-grover.q.orca.md` exercises the
      new gate set end-to-end (4-qubit, 3-iteration Grover with
      `MCZ` on 3 controls).
- [x] 1.7 `demos/larql_gate_knn/demo.py` runs parse → verify →
      compile → simulate → decode and confirms ~96% probability
      mass on the marked state.

## 2. Multi-controlled gate set — formalize as spec

- [ ] 2.1 Land this proposal so the spec deltas in
      `specs/language/spec.md`, `specs/compiler/spec.md`, and
      `specs/verifier/spec.md` are reviewable in isolation from
      future changes.
- [x] 2.2 Add `tests/test_compiler.py` cases for CCZ/MCX/MCZ QASM and
      Qiskit emission, mirroring the existing CNOT / CCNOT cases.
      Include the H-sandwich line ordering as an explicit assertion.
- [x] 2.3 Add `tests/test_verifier.py` cases that confirm
      `unitarity` rules pass for CCZ/MCX/MCZ and that an
      `MCX(qs[c0], qs[c1], qs[c2], qs[c2])` (control = target) raises
      `CONTROL_TARGET_OVERLAP`.
- [x] 2.4 Add a regression test that runs the Grover demo machine
      through `compile_to_qiskit` + `BasicSimulator` shots and
      asserts a > 95% count on `|1010>` for 1024 shots — the same
      check the demo performs end-to-end.
- [x] 2.5 Add `MCX` / `MCZ` to the README / docs gate-set table.

## 3. Parametric actions — parser

- [ ] 3.1 Extend `q_orca/ast.py` with `ActionParameter(name: str,
      type: Literal["int", "angle"])` and add
      `parameters: list[ActionParameter] = []` to
      `QActionSignature`. Add `bound_arguments: list[BoundArg] | None
      = None` and `action_label: str | None = None` to
      `QTransition`.
- [ ] 3.2 Extend `q_orca/parser/markdown_parser.py`'s signature
      parser to accept `(qs, name1: type1, name2: type2, ...) -> qs`.
      Reject duplicate names and unknown types with structured
      errors. Preserve the zero-parameter form as a no-op change.
- [ ] 3.3 Extend the same module's transitions-table parser to
      accept `name(arg1, arg2, ...)` in the Action column. Validate
      arity and per-argument type against the referenced action's
      signature. Populate `QTransition.bound_arguments` and
      `QTransition.action_label`.
- [ ] 3.4 Bare-name references to a parameterized action and
      call-form references to a non-parameterized action SHALL raise
      structured errors with both the action name and the source
      line of the offending transition.
- [ ] 3.5 Resolve action references in a two-pass approach: collect
      all action definitions first, then walk transitions resolving
      against the collected set, so forward references parse without
      ordering constraints.

## 4. Parametric actions — effect-string subscripts

- [ ] 4.1 Extend the shared effect parser (post
      `consolidate-gate-parser`) to accept either a literal int or
      a bare identifier inside `qs[...]` subscripts. Identifier
      subscripts SHALL be valid only when a `signature_context` is
      provided that lists the parameter names in scope.
- [ ] 4.2 Same change for angle slots: identifier-form angles inside
      a parametric action's effect SHALL resolve against the
      signature's `angle`-typed parameters when an
      `signature_context` is provided.
- [ ] 4.3 Add an `unbound_identifier` structured error path; the
      action-definition parser uses it when a subscript or angle
      identifier is not in the signature.

## 5. Parametric actions — compiler expansion

- [ ] 5.1 Add `q_orca/compiler/parametric.py::expand_action_call(action,
      bound_arguments) -> str` that returns the literal effect string
      with all parameter slots substituted. Out-of-range subscripts
      and unparseable angle substitutions SHALL raise structured
      errors carrying the bound-argument values.
- [ ] 5.2 Update `q_orca/compiler/qiskit.py::_extract_gate_sequence`
      (and the parallel paths in QASM and Mermaid) to detect a
      transition with `bound_arguments is not None` and route through
      `expand_action_call` before parsing the gate sequence.
- [ ] 5.3 Mermaid label generation SHALL use
      `t.action_label` when present, falling back to `t.action` for
      bare-name transitions.
- [ ] 5.4 Confirm Qiskit emission for an N-call-site machine
      produces N independent gate sequences in the script (BFS visit
      order preserved) and that the basis transpile pass still runs
      correctly.

## 6. Parametric actions — verifier

- [ ] 6.1 Update `q_orca/verifier/quantum.py` and
      `q_orca/verifier/dynamic.py` to enumerate transitions (not
      action definitions) when collecting gate sequences for
      checking. For each transition with bound arguments, expand and
      verify the resulting sequence; for bare-name transitions, fall
      through to the existing path.
- [ ] 6.2 Add a template-only check pass that runs once per
      parametric action: signature shape, effect-string parseability,
      identifier-binding closure. Errors raised here SHALL point at
      the action's source location.
- [ ] 6.3 Per-call-site errors (range, overlap) SHALL report the
      transition's source location and the bound argument values, not
      the action's location.
- [ ] 6.4 Confirm `ORPHAN_ACTION` warning still fires for
      parametric actions that no transition invokes, and that no
      expansion-time check runs against the orphaned template.

## 7. Tests

- [ ] 7.1 `tests/test_parser.py`: zero-parameter signature still
      parses identically; new typed-parameter cases (int-only,
      angle-only, mixed); duplicate-name and unknown-type error
      cases; call-form arity and type checks.
- [ ] 7.2 `tests/test_compiler.py`: per-call-site expansion produces
      N distinct gate-sequence entries; angle-typed parameter
      expands through the rotation-gate emitter; Mermaid label uses
      the source-form call text.
- [ ] 7.3 `tests/test_verifier.py`: per-call-site range error
      (12-call-site machine with one bad bound value produces one
      error pointing at that transition); template-only unbound-
      identifier error; orphan parametric action.
- [ ] 7.4 `tests/test_examples.py`: pull the new
      `examples/larql-polysemantic-12.q.orca.md` through the
      pipeline end-to-end (parse → verify → compile → optional
      simulate → decode).

## 8. Example & demo

- [ ] 8.1 Author `examples/larql-polysemantic-12.q.orca.md`: 3-qubit
      concept register, 12 non-orthogonal concept vectors, single
      parametric `query_concept(c: int)` action, 12 query
      transitions. Document the chosen overlap matrix in the leading
      paragraph.
- [ ] 8.2 Author `demos/larql_polysemantic_12/demo.py` mirroring
      the structure of `demos/larql_gate_knn/demo.py`: parse +
      verify → compile (Mermaid + QASM) → run Qiskit simulation →
      decode the polysemy score per concept and assert the cross-talk
      floor matches the analytic prediction.
- [ ] 8.3 Promote the 2-qubit / 2-concept sketch from
      `openspec/changes/extend-gate-set-and-parametric-actions/sketches/`
      to `examples/` once the parametric-action grammar lands —
      either by adding the missing dead-letter transitions to satisfy
      completeness, or by rewriting it as a parametric variant that
      exercises the same geometry.

## 9. Documentation

- [ ] 9.1 Update the README's gate-set table with `CCZ`, `MCX`,
      `MCZ`.
- [ ] 9.2 Update the README's "actions" syntax section with a brief
      example of a parametric action plus a call-site usage.
- [ ] 9.3 CHANGELOG entry under the next release: multi-controlled
      gate set is additive (no break); parametric actions are
      additive (no break for existing zero-parameter signatures).
- [ ] 9.4 Run `openspec archive extend-gate-set-and-parametric-actions`
      after merge so the deltas land in
      `openspec/specs/{language,compiler,verifier}/spec.md`.

## 10. Spec consistency

- [ ] 10.1 `openspec validate extend-gate-set-and-parametric-actions
      --strict` passes.
- [ ] 10.2 Full pytest suite green.
- [ ] 10.3 Ruff clean across the touched files.
