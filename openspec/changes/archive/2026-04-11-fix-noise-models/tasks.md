## 1. Fix thermal noise implementation

- [x] 1.1 Update `NoiseModel.parameter2` default from `0.01` to `0.0` in
      `q_orca/ast.py` and update the docstring: parameter = T1 (ns),
      parameter2 = T2 (ns); `0.0` means "default T2 to T1".
- [x] 1.2 Update `_parse_noise_model_string` in `q_orca/compiler/qiskit.py`
      so `thermal(T1)` sets `parameter2=0.0` (sentinel for T2=T1) and
      `thermal(T1, T2)` sets `parameter2=T2` directly.
- [x] 1.3 Replace the `thermal` stub in `_emit_qiskit_noise_model_code` with
      a real `noise.thermal_relaxation_error(t1, t2, 50)` call where
      `t2 = parameter2 if parameter2 > 0 else parameter` (T2 defaults to T1).
      Apply to single-qubit gate list only:
      `['h', 'x', 'y', 'z', 'rx', 'ry', 'rz', 't', 's']`.

## 2. Tests

- [x] 2.1 Create `tests/test_noise_models.py` with a `TestNoiseModelParsing`
      class covering `_parse_noise_model_string` for all four kinds:
      decimal parameters, case-insensitive matching, and unrecognized kind
      returning `None`.
- [x] 2.2 Add a `TestNoiseModelEmission` class testing
      `_emit_qiskit_noise_model_code` output for each kind: assert the
      emitted lines contain the correct `qiskit_aer.noise` function name
      and the correct parameter values.
- [x] 2.3 Add a `TestThermalDefaults` class asserting that `thermal(50000)`
      (one parameter) produces a T2 equal to T1 in the emitted code, and
      `thermal(50000, 70000)` (two parameters) uses the distinct T2 value.
- [x] 2.4 Add a `TestNoiseModelCompileSmoke` class that calls
      `compile_to_qiskit(machine, QSimulationOptions(..., skip_noise=False))`
      on a minimal one-qubit machine with each noise kind in context and
      asserts the output contains the expected `thermal_relaxation_error`
      (or `depolarizing_error`, etc.) substring.

## 3. Documentation

- [x] 3.1 Add a CHANGELOG entry under `0.3.3` (or next version) noting the
      `thermal` parameter semantics change as a breaking change: T1/T2 in ns
      replaces the old depolarizing-probability fallback.
