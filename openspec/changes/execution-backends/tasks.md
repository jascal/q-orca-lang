## 1. Backend Package Scaffolding

- [x] 1.1 Create `q_orca/backends/` package with `__init__.py` exporting `BackendRegistry`, `BackendAdapter`, `BackendResult`, `BackendUnavailableError`
- [x] 1.2 Implement `q_orca/backends/base.py` with abstract `BackendAdapter` class and `BackendResult` dataclass (fields: `name`, `version`, `errors`, `metadata`)
- [x] 1.3 Implement `q_orca/backends/registry.py` with `BackendRegistry` that maps names to adapters and resolves fallback on `BackendUnavailableError`

## 2. QuTiP Backend Adapter

- [x] 2.1 Implement `q_orca/backends/qutip_backend.py` — wraps existing `dynamic_verify()` logic, sets `AVAILABLE` based on QuTiP import, returns `BackendResult`
- [x] 2.2 Refactor `q_orca/verifier/dynamic.py` so `dynamic_verify()` is callable from the new QuTiP adapter without duplication

## 3. cuQuantum Backend Adapter

- [x] 3.1 Implement `q_orca/backends/cuquantum_backend.py` — sets `AVAILABLE = False` when `qutip_cuquantum` is missing, raises `BackendUnavailableError` from `verify()`
- [x] 3.2 Add `--gpu-count` and `--tensor-network` CLI flags to `verify` and `simulate` subparsers
- [x] 3.3 Pass `gpu_count` and `tensor_network` through `BackendRegistry` to cuQuantum adapter config

## 4. CUDA-Q Backend Adapter and Compiler

- [x] 4.1 Implement `q_orca/compiler/cudaq.py` with `compile_to_cudaq(machine) -> str` that emits a `@cudaq.kernel` Python script
- [x] 4.2 Add gate-mapping logic in `compile_to_cudaq`: H→`cudaq.h`, CNOT→`cudaq.x.ctrl`, X/Y/Z, Rx/Ry/Rz, measure→`mz`
- [x] 4.3 Implement `q_orca/backends/cudaq_backend.py` — sets `AVAILABLE` based on `cudaq` import, raises `BackendUnavailableError` when absent
- [x] 4.4 Add `cudaq` to the CLI `compile` format choices and wire to `compile_to_cudaq`

## 5. Verifier Integration

- [x] 5.1 Add `backend: str = "qutip"` field to `VerifyOptions` in `q_orca/verifier/__init__.py`
- [x] 5.2 Replace direct `dynamic_verify(machine)` call in `verify()` with `BackendRegistry.get(opts.backend).verify(machine)`, catching `BackendUnavailableError` and emitting `BACKEND_UNAVAILABLE` warning then retrying with QuTiP
- [x] 5.3 Add `--backend` flag to `verify` CLI subparser; pass it into `VerifyOptions`

## 6. Simulate Integration

- [x] 6.1 Add `--backend` flag to `simulate` CLI subparser
- [x] 6.2 Route Stage 4b in `simulate_machine()` through `BackendRegistry` using the selected backend
- [x] 6.3 Add `--cudaq-target` flag to `simulate` subparser and thread through to CUDA-Q adapter

## 7. JSON Output — Backend Metadata

- [x] 7.1 Inject `"backend": {"name": ..., "version": ...}` into `_cmd_verify` JSON output
- [x] 7.2 Inject `"backend": {"name": ..., "version": ...}` into `_cmd_simulate` JSON output

## 8. orca.yaml Config Extension

- [x] 8.1 Add `backend: str` and optional `cuquantum: dict` / `cudaq: dict` fields to `OrcaConfig` in `q_orca/config/types.py`
- [x] 8.2 Update `q_orca/config/loader.py` to parse the new fields from `orca.yaml`
- [x] 8.3 Implement `_resolve_backend(args, config)` helper in `cli.py` that merges CLI flag (priority) over config file value (fallback)

## 9. Tests

- [x] 9.1 Add `tests/test_backends.py` — unit tests for `BackendRegistry` fallback logic (mock `BackendUnavailableError`), `BACKEND_UNAVAILABLE` warning in `QVerificationResult`, and `BackendResult` metadata fields
- [x] 9.2 Add tests for `compile_to_cudaq` — Bell machine produces valid kernel string with `import cudaq`, `@cudaq.kernel`, correct gate calls
- [x] 9.3 Add CLI integration test: `q-orca verify --backend qutip --json` produces `"backend"` block; `q-orca verify --backend cuquantum --json` falls back to QuTiP with warning (mock cuquantum as unavailable)
- [x] 9.4 Run full test suite (`pytest`) and fix any regressions
