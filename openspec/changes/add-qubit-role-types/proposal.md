## Why

q-orca's structural verifier is its core value, but every qubit in `qubits: list<qubit>` is opaque to it — there is no way to say "this qubit is *scratch*" or "this is *the syndrome ancilla*". Two real bug classes slip through as a result: **ancilla recycling without reset** (`bit-flip-syndrome` only catches it because the author hand-added a `mid_circuit_coherence` rule — omit it and the protection is gone) and **unconverged syndromes** (a syndrome ancilla prepared but never measured in a round — exactly the silent quantum bug `extend-conditional-gate-compound-bits` / PR #62 surfaced). The verifier already has the per-qubit gate-walk machinery; it just has no way to *target* a check at the qubits that need it.

This is also the dependency that lights up the `qs[role:R]` noise-model selector shipped (stubbed) in `add-noise-model-section`: that selector parses today but is rejected with "requires qubit-role-types". Landing roles retires the stub.

## What Changes

- Add an inline **role tag** on each element of a `## context` `list<qubit>` default: `[q0:data, q1:ancilla, q2:ancilla]`, with a `a..b:role` range shorthand. Roles are a **closed vocabulary** — `data` (default), `ancilla`, `syndrome`, `communication`. Untagged elements are `data`, so every existing machine parses unchanged. Unknown keywords raise `UNKNOWN_QUBIT_ROLE`.
- Parse per-qubit roles into the AST (a real per-register structure — *not* `QTypeQubit.kind`, which is the shared type discriminator) and expose a role lookup by qubit index.
- Three structural verifier rules, applied automatically by role (no opt-in `## verification rules` line needed):
  1. **`ancilla_reset`** — an `ancilla` qubit must start in `|0⟩` and be `reset` between successive mid-circuit measurements (`ANCILLA_NOT_RESET`).
  2. **`syndrome_completeness`** — a `syndrome` qubit must be measured on every cyclic path; using the SCC fallback now, tightening to per-iteration once `bounded-loop-annotation` lands (`SYNDROME_NOT_MEASURED`).
  3. **`communication_no_cloning`** — escalates the existing no-cloning check to `COMMUNICATION_NO_CLONING_VIOLATION` (with a `[send: …]` fix hint) when the duplicated qubit is `communication`.
- **Resolve `qs[role:R]`** against declared roles wherever it appears — closing the noise-model selector loop.
- Migrate the shipped examples that use ancillas (`bit-flip-syndrome`, `quantum-teleportation`, `deutsch-jozsa`) to tag roles — the canonical "use the new feature in shipped examples" pass.
- Out of scope (deferred, named): the `coin`/`position` roles and their rules (`coin_unitary`, `position_bounded`) are gated on the unwritten walk-primitives spec; role queries in *runtime* guards (verifier-time only for v1); role propagation through `invoke:` boundaries (erased at the boundary for v1); a `borrowed-ancilla` 7th role; Mermaid role coloring.

## Capabilities

### New Capabilities
<!-- none — extends existing language + verifier capabilities -->

### Modified Capabilities
- `language`: the `## context` `list<qubit>` default may carry per-element role tags (`name:role`, `a..b:role`); closed vocabulary; default `data`; `UNKNOWN_QUBIT_ROLE`.
- `verifier`: add the three role-driven structural rules; **modify** the noise-model target-resolution rule so `qs[role:R]` resolves against declared roles instead of being rejected.

## Impact

- **Changed code**: `q_orca/parser/markdown_parser.py` (`_parse_context_table` qubit-default tokenizer — currently a raw string); `q_orca/ast.py` (per-qubit role structure on `QMachineDef`, e.g. `qubit_roles`); `q_orca/verifier/structural.py` + `q_orca/verifier/quantum.py` (3 rules); `q_orca/verifier/noise_model.py` (resolve role selectors); shipped example files.
- **New diagnostics**: `UNKNOWN_QUBIT_ROLE`, `ANCILLA_NOT_RESET`, `SYNDROME_NOT_MEASURED`, `COMMUNICATION_NO_CLONING_VIOLATION`.
- **Backward compatible**: untagged registers are all `data`; no existing machine changes behavior.
- **Dependencies**: composes with (not blocked by) `bounded-loop-annotation` (tightens rule 2 when present) and `extend-conditional-gate-compound-bits` (merged). Independent of `add-parameterized-invoke`.
