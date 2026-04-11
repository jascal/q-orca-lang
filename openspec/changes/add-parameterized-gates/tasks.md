## 1. Parser: recognize rotation gates

- [ ] 1.1 Add an `_evaluate_angle(text: str) -> float` helper in
      `q_orca/parser/markdown_parser.py` supporting: decimal literal,
      `pi`, `pi/<int>`, `<int>*pi`, `<int>*pi/<int>`, and a leading
      minus sign on any of the above. Raise `ValueError` on anything else.
- [ ] 1.2 Extend `_parse_gate_from_effect` to match
      `R([XYZ])\(\s*\w+\[(\d+)\]\s*,\s*([^)]+)\s*\)` and construct
      `QuantumGate(kind="R{X|Y|Z}", targets=[N], parameter=<angle>)`.
- [ ] 1.3 Surface parser errors on malformed rotation-gate effects
      through the existing `QParseResult.errors` path (add the field if
      missing, and plumb the message through).

## 2. Compiler: canonical argument order

- [ ] 2.1 Update `q_orca/compiler/qiskit.py::_parse_single_gate` to
      accept `Rx(qs[N], theta)` (qubit first). Remove the old
      angle-first regex.
- [ ] 2.2 Reuse the parser's `_evaluate_angle` in the Qiskit effect
      parser so symbolic angles work identically. Extract to a shared
      helper module if duplication becomes a smell.
- [ ] 2.3 Confirm the verifier's
      `q_orca/verifier/dynamic.py::_parse_single_gate_to_dict` already
      uses the canonical order; swap to the shared angle evaluator.
- [ ] 2.4 Update `q_orca/compiler/qasm.py::_gate_to_qasm` to continue
      emitting `rx(<float>) q[i];`. No behavior change expected; just
      confirm the `gate.parameter` value is populated correctly once
      the parser fix lands.

## 3. Tests

- [ ] 3.1 Add parametrized parser tests in `tests/test_parser.py`
      covering each angle grammar form plus a bare-identifier
      error case.
- [ ] 3.2 Add a regression test in `tests/test_regression.py` that
      parses a minimal rotation machine, compiles to QASM and Qiskit,
      and asserts the presence of the expected emitted gate substrings.
- [ ] 3.3 Create `tests/test_vqe_rotation.py` that runs the new example
      through the full pipeline, simulates via QuTiP (skip if not
      installed), and asserts `|<psi|psi_expected>|^2 > 0.999999` for
      θ = π/4.

## 4. Example

- [ ] 4.1 Create `examples/vqe-rotation.q.orca.md`: a single-qubit
      machine with states `|0>` → `|θ>` → `|measured>`, one action
      `rotate_q0` with effect `Rx(qs[0], pi/4)`, a measurement, and a
      `## verification rules` list opting into `unitarity`.
- [ ] 4.2 Wire the new example into `tests/test_examples.py` so it
      runs under the standard example harness.

## 5. Documentation

- [ ] 5.1 Update the README roadmap to mark parameterized gates as
      shipped, cross-linked to the CHANGELOG entry.
- [ ] 5.2 Update `openspec/specs/language/spec.md` and
      `openspec/specs/compiler/spec.md` by running
      `openspec archive add-parameterized-gates` after merge — the
      archive command applies the change deltas to the seed specs.
- [ ] 5.3 Add a CHANGELOG entry under the next version bump (0.3.3 or
      0.4.0 per release discipline) noting the canonical argument
      order change as a potential compatibility break.
