## 1. AST + parser

- [ ] 1.1 Add a per-qubit role store to `QMachineDef` (e.g. `qubit_roles: list[str]`, one per declared qubit in order); add a `QUBIT_ROLES` closed-vocabulary constant `{data, ancilla, syndrome, communication}` in `q_orca/ast.py`
- [ ] 1.2 Extend the `## context` `list<qubit>` default tokenizer in `_parse_context_table` to parse `name:role` per element (default `data`) and populate `qubit_roles`
- [ ] 1.3 Parse the `aN..aM:role` range shorthand (shared alpha prefix + inclusive integer suffixes) into the flat per-element list
- [ ] 1.4 Reject unknown / reserved (`coin`, `position`) tags with `UNKNOWN_QUBIT_ROLE` naming the element; untagged register parses identically to today

## 2. Verifier rules

- [ ] 2.1 `ancilla_reset` (`structural.py`): for each `ancilla` qubit, require `|0⟩` start + `reset` between successive mid-circuit measurements; `ANCILLA_NOT_RESET` with state + index
- [ ] 2.2 `syndrome_completeness` (`structural.py`): for each `syndrome` qubit, every cyclic SCC acting on it must contain a `measure`; `SYNDROME_NOT_MEASURED` (SCC fallback now; per-iteration once bounded-loop lands)
- [ ] 2.3 `communication_no_cloning` (`quantum.py`): escalate `check_no_cloning` to `COMMUNICATION_NO_CLONING_VIOLATION` (with `[send: …]` hint) when the duplicated qubit is `communication`; generic code unchanged otherwise
- [ ] 2.4 Wire the role rules into the verify pipeline (fire only when the machine declares any non-`data` role; no `## verification rules` opt-in needed)

## 3. Close the noise `qs[role:R]` loop

- [ ] 3.1 In `q_orca/verifier/noise_model.py`, resolve `qs[role:R]` against `qubit_roles` (matching indices); a role matching no qubit still warns `NOISE_TARGET_NO_MATCH`
- [ ] 3.2 In `q_orca/compiler/qiskit.py`, emit role-targeted noise on the resolved qubit indices (the `qubit_role` branch currently emits a "requires qubit-role-types" skip comment)

## 4. Examples + tests + docs

- [ ] 4.1 Migrate shipped ancilla-using examples to role tags: `bit-flip-syndrome` (`syndrome`), `quantum-teleportation` and `deutsch-jozsa` as applicable; confirm they verify
- [ ] 4.2 Tests: backward-compat (untagged → `data`, `bell-entangler` report unchanged); ancilla-reset pass/fail; syndrome-completeness pass/fail (SCC fallback); communication no-cloning escalation; range shorthand; `UNKNOWN_QUBIT_ROLE` for unknown + reserved; `qs[role:R]` noise selector now resolves (no `NOISE_TARGET_NO_MATCH`)
- [ ] 4.3 Docs: `docs/language/qubit-roles.md` (vocabulary, range syntax, the three rules, deferred `coin`/`position`); mark `docs/research/spec-qubit-role-types.md` delivered (scoped to rules 1–3)
