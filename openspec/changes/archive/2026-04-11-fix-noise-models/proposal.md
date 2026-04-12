## Why

The compiler spec declares `thermal(p[, q])` as a supported noise kind, but the
implementation silently falls back to `depolarizing_error` with a `# not fully
supported` comment. Additionally, there are zero tests for any of the four noise
kinds (`depolarizing`, `amplitude_damping`, `phase_damping`, `thermal`), and the
`noise_model` type has no coverage in the language spec at all.

## What Changes

1. **Fix `thermal` noise** — implement `qiskit_aer.noise.thermal_relaxation_error`
   properly using T1/T2 relaxation times derived from the two parameters, removing
   the silent fallback. Document the two-parameter semantics: `thermal(T1, T2)`.
   **BREAKING**: the first parameter changes meaning from `depol_prob` to T1 (ns).
   Anyone using `thermal(...)` in a context field gets different (correct) output.

2. **Add language spec coverage** — add a requirement in the language spec for the
   `noise_model` context field type: accepted syntax, the four kinds, and parse
   error behavior for unrecognized kinds.

3. **Add test suite** — unit and integration tests covering all four noise kinds:
   parser round-trip, `_emit_qiskit_noise_model_code` output shape, and a
   compile-level smoke test per kind.

4. **Add missing scenarios to compiler spec** — `amplitude_damping`, `phase_damping`,
   and `thermal` have no scenarios today; add one each.

## Capabilities

### New Capabilities

None. All changes refine or correct existing capabilities.

### Modified Capabilities

- `compiler`: Noise Model Compilation requirement updated — `thermal` semantics
  corrected to T1/T2 relaxation, scenarios added for `amplitude_damping`,
  `phase_damping`, and `thermal`.
- `language`: New requirement added for the `noise_model` context field type —
  syntax, accepted kinds, and parse error behavior.

## Impact

**Code:**
- `q_orca/compiler/qiskit.py` — `_emit_qiskit_noise_model_code` (thermal branch)
- `q_orca/ast.py` — `NoiseModel.parameter2` renamed/re-documented (T2, not `p_err`)

**Tests:**
- `tests/test_noise_models.py` — new file covering all four kinds

**Specs:**
- `openspec/specs/compiler/spec.md` — Noise Model Compilation requirement extended
- `openspec/specs/language/spec.md` — new `noise_model` type requirement

**Dependencies:** `qiskit_aer` already optional; no new dependencies.

**Backwards compatibility:** `thermal` parameter semantics change. No in-tree
example uses `thermal`; external users should see the CHANGELOG.
