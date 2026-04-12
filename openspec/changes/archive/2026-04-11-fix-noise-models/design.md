## Context

Four noise kinds are parsed by `_parse_noise_model_string` in
`q_orca/compiler/qiskit.py` and stored as `NoiseModel` AST nodes.
`_emit_qiskit_noise_model_code` turns them into Qiskit-Aer noise model
setup code. Three of the four (`depolarizing`, `amplitude_damping`,
`phase_damping`) are implemented correctly. `thermal` is stubbed:

```python
# thermal noise not fully supported, using depolarizing
thermal_error = noise.depolarizing_error({noise_model.parameter}, 1)
```

`NoiseModel.parameter2` (default `0.01`) was intended as the thermal
excitation probability but was never wired into any output.

The `qiskit_aer.noise` API for thermal relaxation is:
```python
noise.thermal_relaxation_error(t1, t2, time)
```
where `t1` and `t2` are relaxation times in nanoseconds and `time` is
the gate time (also in ns). There is no single "thermal noise level"
parameter analogous to `depolarizing(p)` — thermal noise requires T1
and T2 times.

## Goals / Non-Goals

**Goals:**

- Replace the `thermal` stub with a real `thermal_relaxation_error` call
  using T1 and T2 parameters.
- Settle on a canonical two-parameter syntax: `thermal(T1, T2)` in ns,
  with a fixed gate time of 50 ns (a typical single-qubit gate time).
- Add `amplitude_damping`, `phase_damping`, and `thermal` scenarios to
  the compiler spec.
- Add a `noise_model` field type requirement to the language spec.
- Add `tests/test_noise_models.py` covering all four kinds.

**Non-Goals:**

- Per-gate gate times (all gates use the same fixed 50 ns default).
- Noise on two-qubit gates for `thermal` (Qiskit-Aer's
  `thermal_relaxation_error` returns a 1-qubit channel; applying it to
  `cx`/`cz`/`swap` would require a tensor product — deferred).
- Custom gate lists per noise kind.
- Noise in the QASM backend (QASM 3.0 has no standard noise pragma).

## Decisions

### `thermal(T1, T2)` — relaxation times in nanoseconds, fixed 50 ns gate time

`thermal_relaxation_error(t1, t2, time)` is the correct Qiskit-Aer API.
The two parameters are T1 and T2 relaxation times in ns. A fixed gate
time of 50 ns covers most single-qubit gates on superconducting hardware
and avoids requiring a third parameter.

The old `parameter2` field on `NoiseModel` (was `p_err`, default 0.01)
is re-purposed as T2 (ns). Since no in-tree example uses `thermal`, no
migration is needed beyond the CHANGELOG.

**Typical values**: T1 ≈ 50,000 ns, T2 ≈ 70,000 ns for transmon qubits.
A user writing `thermal(50000, 70000)` gets physically meaningful noise.

### `thermal` applied only to single-qubit gates

`thermal_relaxation_error` returns a single-qubit channel. Applying it
to two-qubit gates via `add_all_qubit_quantum_error` requires a tensor
product, which is non-trivial and outside the scope of this change.
The generated script applies `thermal_relaxation_error` to
`['h', 'x', 'y', 'z', 'rx', 'ry', 'rz', 't', 's']` only.

### `NoiseModel.parameter2` re-semanticised, not renamed

Renaming the dataclass field would break any code that accesses
`nm.parameter2` directly. The field name stays; only the docstring and
default change. The default becomes `0.0` (meaning T2 = T1, which is
the physical upper bound). `_parse_noise_model_string` already sets
`parameter2` from the optional second argument.

## Risks / Trade-offs

- **`thermal` two-qubit gate gap**: single-qubit only. Risk: users
  with CNOT-heavy circuits get partial noise. Mitigation: document
  in generated script comment.
- **Fixed 50 ns gate time**: may be wrong for non-superconducting
  hardware. Mitigation: document in spec; add optional third parameter
  in a follow-on change if needed.
- **`qiskit_aer` not always installed**: all four kinds already sit
  inside a `try/except ImportError` block. No new risk.
