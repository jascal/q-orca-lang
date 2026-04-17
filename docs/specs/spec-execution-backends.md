# Q-Orca Language Specification — Execution Backends

**Version:** 0.1 (draft)
**Status:** Proposed
**Scope:** Defines supported simulation and compilation backends, mapping rules, CLI flags, configuration syntax, and fallback behaviour.

---

## 1. Overview

Q-Orca machines are backend-agnostic by default. A machine definition (`.q.orca.md`) describes *what* the quantum state machine does; the backend determines *how* it is verified, simulated, or compiled. Three tiers of backends are defined:

| Tier | Backend | Role | Required? |
|------|---------|------|-----------|
| 0 | **QuTiP** (default) | Dynamic verification (Stage 4b), simulation | Soft dependency |
| 1 | **NVIDIA cuQuantum** | GPU-accelerated dynamic verification and simulation | Optional |
| 2 | **NVIDIA CUDA-Q** | Compilation and runtime target for GPU/QPU execution | Optional |

All backends must produce semantically identical verification results. Switching backends changes performance and scalability, not correctness.

---

## 2. Default Backend: QuTiP

QuTiP is the reference backend for dynamic verification (Stage 4b). It is used when no `--backend` flag is specified and no `backend` key is set in `orca.yaml`.

**Capabilities:**
- State-vector simulation for up to ~25 qubits on typical hardware
- Von Neumann entropy and Schmidt rank computation for entanglement verification
- Lindblad master equation integration for open-system noise models

**Graceful degradation:** If QuTiP is not installed (`pip install qutip`), Stage 4b is skipped and a warning is emitted. All other verification stages run normally.

---

## 3. NVIDIA cuQuantum Backend

### 3.1 Purpose

The cuQuantum backend accelerates Stage 4b dynamic verification and simulation using NVIDIA GPU hardware via the `qutip-cuquantum` plugin and the underlying `cuDensityMat` and `cuTensorNet` libraries.

**Expected performance:** Up to 4000× speedup over CPU-only QuTiP for large composite quantum systems (benchmarks from NVIDIA cuQuantum 24.x documentation). Enables practical verification of 30–100+ qubit quantum automata via tensor network contraction.

### 3.2 CLI Flags

```bash
# Verification with cuQuantum acceleration
q-orca verify machine.q.orca.md --backend cuquantum

# Simulation with cuQuantum
q-orca simulate machine.q.orca.md --run --backend cuquantum

# Multi-GPU mode
q-orca verify machine.q.orca.md --backend cuquantum --gpu-count 4
```

The `--backend nvidia` alias is also accepted.

### 3.3 Configuration (orca.yaml)

```yaml
backend: cuquantum

cuquantum:
  gpu_ids: [0, 1]           # GPU device indices to use (default: [0])
  gpu_count: 2              # Number of GPUs (shorthand; overrides gpu_ids length)
  workstream_device: 0      # cuDensityMat WorkStream device index
  tensor_network: true      # Use cuTensorNet for contraction (default: false)
  precision: float64        # float32 | float64 (default: float64)
  seed: 42                  # RNG seed for reproducibility
```

### 3.4 Machine-level Backend Annotation

A machine may declare a preferred backend in its `## invariants` section:

```markdown
## invariants
- backend: cuquantum
- entanglement(q0,q1) = True
- schmidt_rank(q0,q1) >= 2
```

The `backend` invariant is advisory — it is used when no CLI flag is present. It does not affect verification semantics.

### 3.5 Fallback Behaviour

If the cuQuantum backend is requested but unavailable (no GPU, no `qutip-cuquantum` installed), the verifier falls back to default QuTiP and emits:

```
[WARN] BACKEND_UNAVAILABLE: cuquantum backend requested but not available.
       Falling back to default QuTiP backend.
       Install: pip install qutip-cuquantum
```

Verification proceeds normally. The `--strict` flag does **not** treat this warning as an error by default; pass `--strict --no-backend-fallback` to fail hard on backend unavailability.

### 3.6 Output Metadata

When cuQuantum is used, verification and simulation JSON output includes a `backend` metadata block:

```json
{
  "machine": "BellEntangler",
  "valid": true,
  "errors": [],
  "backend": {
    "name": "cuquantum",
    "version": "24.03.0",
    "gpu_ids": [0],
    "precision": "float64",
    "seed": 42
  }
}
```

---

## 4. NVIDIA CUDA-Q Backend

### 4.1 Purpose

CUDA-Q is a compilation and runtime target that maps Q-Orca quantum state machines to CUDA-Q kernel functions. It supports:

- GPU-accelerated state-vector and tensor network simulation
- Hardware execution via CUDA-Q's QPU-agnostic layer (~75% of public QPUs)
- Tight classical-quantum interleaving for hybrid control loops
- Future: `cudaq-realtime` and NVQLink for microsecond-latency GPU ↔ QPU callbacks

### 4.2 Mapping Rules

#### 4.2.1 States → Kernel Boundaries

Each distinct quantum state in the machine maps to a named section in the CUDA-Q kernel. Terminal states (marked `[final]`) map to classical post-processing blocks.

#### 4.2.2 Transitions → Gate Sequences

| Q-Orca action effect | CUDA-Q primitive |
|----------------------|-----------------|
| `Hadamard(qs[N])` | `cudaq::h(q[N])` |
| `CNOT(qs[N], qs[M])` | `cudaq::x<cudaq::ctrl>(q[N], q[M])` |
| `Rx(qs[N], theta)` | `cudaq::rx(theta, q[N])` |
| `Ry(qs[N], theta)` | `cudaq::ry(theta, q[N])` |
| `Rz(qs[N], theta)` | `cudaq::rz(theta, q[N])` |
| `CRz(qs[N], qs[M], theta)` | `cudaq::rz<cudaq::ctrl>(theta, q[N], q[M])` |
| `RZZ(qs[N], qs[M], theta)` | `cudaq::rzz(theta, q[N], q[M])` |

Custom gate matrices (declared via `## gates`) are emitted as `cudaq::unitary` calls.

#### 4.2.3 Mid-Circuit Measurement + Feedforward

Mid-circuit `measure(qs[N]) -> bits[M]` effects and `if bits[M] == val: Gate(...)` conditionals map to CUDA-Q's hybrid programming model:

```python
# Generated by Q-Orca CUDA-Q compiler
import cudaq

@cudaq.kernel
def active_teleportation():
    q = cudaq.qvector(3)
    # ... gate sequence ...
    c0 = mz(q[0])           # mid-circuit measurement
    if c0:                  # classical feedforward
        x(q[2])
```

This leverages CUDA-Q's native support for classical control flow interleaved with quantum gates — the defining feature of its hybrid model.

#### 4.2.4 Noise Context → cudaq noise_model

`## context` noise declarations map to CUDA-Q noise models:

| Q-Orca context field | CUDA-Q equivalent |
|---------------------|-------------------|
| `noise: depolarizing(p)` | `cudaq.DepolarizationChannel(p)` |
| `noise: amplitude_damping(gamma)` | `cudaq.AmplitudeDampingChannel(gamma)` |
| `noise: thermal(T1, T2)` | `cudaq.ThermalRelaxationChannel(T1, T2)` |

### 4.3 CLI Flags

```bash
# Compile to CUDA-Q Python kernel
q-orca compile cudaq machine.q.orca.md

# Simulate using CUDA-Q state-vector simulator
q-orca simulate machine.q.orca.md --run --backend cudaq

# Simulate using CUDA-Q tensor network simulator
q-orca simulate machine.q.orca.md --run --backend cudaq --cudaq-target tensornet

# Target real hardware via CUDA-Q QPU layer
q-orca simulate machine.q.orca.md --run --backend cudaq --cudaq-target <qpu-name>
```

### 4.4 Configuration (orca.yaml)

```yaml
backend: cudaq

cudaq:
  target: nvidia          # nvidia | tensornet | qpp-cpu | <qpu-name>
  shots: 1024             # Number of shots for sampling (default: 1024)
  seed: 42                # RNG seed
  precision: float64      # float32 | float64
```

### 4.5 Example: Bell Entangler compiled to CUDA-Q

Given `examples/bell-entangler.q.orca.md`, `q-orca compile cudaq` produces:

```python
# Generated by Q-Orca CUDA-Q compiler v0.1
# Machine: BellEntangler

import cudaq

@cudaq.kernel
def bell_entangler():
    q = cudaq.qvector(2)
    # |00> --prepare_H--> |+0>
    h(q[0])
    # |+0> --entangle--> |ψ>
    x.ctrl(q[0], q[1])
    # Measurement
    mz(q)

counts = cudaq.sample(bell_entangler, shots_count=1024)
print(counts)
```

### 4.6 Future: cudaq-realtime and NVQLink

A future extension (`--backend cudaq-realtime`) will target the `cudaq-realtime` runtime with NVQLink for microsecond-latency GPU ↔ QPU callbacks. This is the target execution model for real-time hybrid applications such as:

- Quantum error correction with adaptive syndrome feedback
- Closed-loop variational quantum algorithms (ADAPT-VQE)
- Real-time quantum state tomography

This extension is not yet implemented. The spec reserves the `cudaq-realtime` backend identifier.

---

## 5. Tensor Network Mode (cuTensorNet)

For quantum automata with 30–100+ qubits, state-vector simulation is intractable. Both the cuQuantum and CUDA-Q backends support tensor network contraction via cuTensorNet.

```bash
# cuQuantum tensor network mode
q-orca verify large-machine.q.orca.md --backend cuquantum --tensor-network

# CUDA-Q tensor network simulator
q-orca simulate large-machine.q.orca.md --run --backend cudaq --cudaq-target tensornet
```

Tensor network mode is automatically selected when qubit count exceeds the threshold defined in `orca.yaml` (`tensornet_qubit_threshold`, default: 30). It can also be forced explicitly.

**Limitations:** Tensor network contraction is efficient for low-entanglement circuits. Highly entangled states (e.g. GHZ at large N) may still require exponential contraction time. The verifier emits a `WARN: HIGH_ENTANGLEMENT_TENSOR_NETWORK` advisory in these cases.

---

## 6. Backend Selection Summary

| Flag / Config | Effect |
|---------------|--------|
| *(none)* | QuTiP (CPU) for Stage 4b; Qiskit for simulation |
| `--backend cuquantum` | GPU-accelerated QuTiP via cuDensityMat |
| `--backend cudaq` | CUDA-Q state-vector simulator |
| `--backend cudaq --cudaq-target tensornet` | CUDA-Q tensor network simulator |
| `--backend cudaq --cudaq-target <qpu>` | Real QPU hardware via CUDA-Q |
| `--tensor-network` | Force tensor network mode on cuQuantum |
| `--gpu-count N` | Multi-GPU mode (cuQuantum only) |

---

## 7. Reproducibility

All backend outputs include a `backend` metadata block in JSON mode (see §3.6). For reproducible research:

- Always set `seed` in `orca.yaml` or pass `--seed N`
- Pin backend versions in CI (`cuquantum==24.x`, `cuda-quantum==0.x`)
- Use `--json` output and archive the `backend` metadata alongside results

---

## 8. Error Codes

| Code | Severity | Description |
|------|----------|-------------|
| `BACKEND_UNAVAILABLE` | Warning | Requested backend not installed; fell back to default |
| `BACKEND_GPU_NOT_FOUND` | Warning | No CUDA-capable GPU detected |
| `BACKEND_VERSION_MISMATCH` | Warning | Installed backend version differs from pinned version |
| `BACKEND_TENSORNET_HIGH_ENTANGLEMENT` | Warning | Tensor network mode may be slow due to high entanglement |
| `BACKEND_UNSUPPORTED_GATE` | Error | Gate has no mapping in the target backend |
| `BACKEND_REALTIME_NOT_AVAILABLE` | Error | `cudaq-realtime` target requested but not yet implemented |
