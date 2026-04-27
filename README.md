# Q-Orca — Quantum Orchestrated State Machine Language

[![Tests](https://github.com/jascal/q-orca-lang/actions/workflows/test.yml/badge.svg)](https://github.com/jascal/q-orca-lang/actions/workflows/test.yml)
[![Verify Examples](https://github.com/jascal/q-orca-lang/actions/workflows/verify-examples.yml/badge.svg)](https://github.com/jascal/q-orca-lang/actions/workflows/verify-examples.yml)
[![PyPI](https://img.shields.io/pypi/v/q-orca)](https://pypi.org/project/q-orca/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://pypi.org/project/q-orca/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/jascal/q-orca-lang)

Q-Orca is a quantum-aware dialect of [Orca](https://github.com/orca-lang/orca-lang), a state machine language written in Markdown. It extends Orca with Dirac ket notation for quantum states, unitary gate actions, entanglement verification, and simulation via Qiskit.

All 15 bundled example machines — from the original Bell / GHZ / Deutsch-Jozsa / Teleportation / VQE set through QAOA, predictive-coder, and LARQL polysemantic circuits — pass the full 5-stage verification pipeline on every commit, across Python 3.10–3.13.

---

## Why Q-Orca?

Most quantum tools let you draw circuits. Q-Orca lets you **define, verify, and simulate** quantum programs as first-class state machines — with the same rigour you'd apply to a production distributed system.

- **Verification, not just simulation** — a 5-stage pipeline catches unitarity violations, entanglement declaration errors, superposition coherence leaks, and incomplete collapse branches before you run a single shot
- **Readable by humans and AI** — machines are plain Markdown; LLMs generate and refine them natively via the built-in MCP server
- **Hybrid classical-quantum control** — mid-circuit measurement + classical feedforward lets you write closed-loop quantum controllers, not just open circuits
- **Formal foundation** — directly implements quantum finite automata theory in executable, verifiable form

---

## Install

```bash
pip install q-orca[quantum]
```

Installs the CLI, verifier, compilers, and Qiskit/QuTiP simulation support.

```bash
pip install q-orca[all]      # + MCP server (pyyaml)
pip install q-orca           # CLI + verifier only, no quantum libs
```

### Verify the installation

```bash
q-orca verify examples/bell-entangler.q.orca.md --strict
```

Expected output:
```
Machine: BellEntangler
  Result: VALID
```

### Optional backends

```bash
# CUDA-Q (macOS Apple Silicon, Linux, Windows — CPU simulation, no GPU required)
# Tested: cudaq==0.14.0
pip install cudaq matplotlib
q-orca verify examples/bell-entangler.q.orca.md --backend cudaq

# cuQuantum (Linux + NVIDIA GPU only)
pip install qutip-cuquantum
q-orca verify examples/bell-entangler.q.orca.md --backend cuquantum
```

If a backend package is not installed, Q-Orca falls back to QuTiP automatically.

---

## Setup (development)

```bash
# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# Install Q-Orca in editable mode (with quantum libraries)
pip install -e ".[quantum]"

# Or install with MCP server support
pip install -e ".[all]"

# Or install without quantum deps first
pip install -e .
pip install qiskit
pip install qutip  # optional, for quantum verification
```

To exit the virtual environment: `deactivate`

---

## Running

```bash
# Check version
q-orca --version

# Verify a quantum machine
q-orca verify examples/bell-entangler.q.orca.md
q-orca verify examples/bell-entangler.q.orca.md --json
q-orca verify examples/bell-entangler.q.orca.md --strict        # warnings → errors
q-orca verify examples/bell-entangler.q.orca.md --skip-dynamic  # skip QuTiP simulation

# Compile to Mermaid diagram
q-orca compile mermaid examples/quantum-teleportation.q.orca.md

# Compile to OpenQASM 3.0
q-orca compile qasm examples/bell-entangler.q.orca.md

# Generate Qiskit simulation script
q-orca simulate examples/bell-entangler.q.orca.md

# Run simulation immediately
q-orca simulate examples/bell-entangler.q.orca.md --run

# Noisy simulation with 2048 shots
q-orca simulate examples/bell-entangler.q.orca.md --run --shots 2048

# Deterministic shots run (fixed RNG seed — useful in CI)
q-orca simulate examples/bell-entangler.q.orca.md --run --shots 1024 --seed 42

# With QuTiP verification
q-orca simulate examples/bell-entangler.q.orca.md --run --verbose

# MCP self-description (for Claude Code integration)
q-orca --tools --json

# Read source from stdin
cat examples/bell-entangler.q.orca.md | q-orca --stdin verify
```

---

## How Verification Works

Every machine passes through 5 stages in order. A failure in stage 1 stops the pipeline early; later stages are cumulative.

| Stage | Module | What it checks |
|-------|--------|----------------|
| 1 — Structural | `structural.py` | All states reachable, no deadlocks, no orphan states |
| 2 — Completeness | `completeness.py` | Every (state, event) pair has at least one outgoing transition |
| 3 — Determinism | `determinism.py` | Guards on competing transitions are mutually exclusive |
| 4 — Quantum | `quantum.py` | Unitarity of gates, no-cloning violations, entanglement declarations, collapse probability sum = 1 |
| 4b — Dynamic | `dynamic.py` | QuTiP circuit simulation: actual Schmidt rank and Von Neumann entropy for every declared entangled state |
| 4c — Resource bounds | `resources.py` | `gate_count`, `depth`, `cx_count`, `t_count`, `logical_qubits` against budgets declared in `## invariants` (skipped when no resource invariants are present) |
| 5 — Superposition | `superposition.py` | No superposition coherence leaks across unguarded transitions |

Stage 4b is a soft dependency: if QuTiP is not installed it skips gracefully and CI still passes.

### Verification Backends

Stage 4b supports three backends via `--backend`:

| Backend | Flag | Requires | Platform |
|---------|------|----------|----------|
| QuTiP (default) | `--backend qutip` | `pip install qutip` | Any |
| NVIDIA CUDA-Q | `--backend cudaq` | `pip install cudaq matplotlib` | macOS (Apple Silicon), Linux, Windows |
| NVIDIA cuQuantum | `--backend cuquantum` | `pip install qutip-cuquantum` + CUDA toolkit | Linux + NVIDIA GPU only |

All backends produce identical verification results — switching changes performance, not correctness. If a requested backend is unavailable, Q-Orca falls back to QuTiP and emits a `BACKEND_UNAVAILABLE` warning. See [Install](#install) for setup instructions.

### Stage 4 vs 4b — static vs dynamic

Stage 4 (`quantum.py`) checks your **declarations**: does the Markdown say this state is entangled? Does a CNOT gate lead to it? These are fast structural checks that catch obvious mistakes.

Stage 4b (`dynamic.py`) **simulates the circuit**: it replays every gate in the path from the initial state, then computes the actual Von Neumann entropy and Schmidt rank of the resulting state vector using QuTiP. This catches cases where the gate sequence is present but wrong — e.g. two Hadamards that cancel, a CNOT on the wrong qubits, or a rotation angle that leaves the state separable.

For a valid Bell state (`H(q0)` then `CNOT(q0, q1)`), the dynamic verifier internally computes:

```json
{
  "state": "|ψ>",
  "entropy_checks": { "q0": 1.0 },
  "schmidt_ranks": { "q0-q1": 2 },
  "passed": true,
  "details": {}
}
```

- **`entropy_checks.q0 = 1.0`** — Von Neumann entropy of qubit 0 after tracing out q1. Exactly 1.0 = maximally entangled.
- **`schmidt_ranks.q0-q1 = 2`** — Schmidt rank across the q0/q1 bipartition. Rank > 1 confirms entanglement; rank = 1 means separable.

If either value falls below threshold, stage 4b emits a `DYNAMIC_NO_ENTANGLEMENT` error (shown below).

### Example failure report

A machine with a missing CNOT gate and an incomplete collapse:

```
$ q-orca verify broken-bell.q.orca.md

  Machine: BrokenBell
  States: |00>, |ψ>, |00_collapsed>
  Events: prepare, measure_done
  Transitions: 2
  Verification rules: unitarity, entanglement

  Result: INVALID
  [WARN] ENTANGLEMENT_WITHOUT_GATE: State '|ψ>' is declared as entangled but no entangling gate (CNOT, CZ, etc.) leads to it
        -> Add a transition with a CNOT or other entangling gate action
  [ERR]  DYNAMIC_NO_ENTANGLEMENT: State '|ψ>' should be entangled but verification failed: q0-q1: Schmidt rank 1 ≤ 1
        -> Ensure the circuit creates an entangled state with CNOT or CZ gates
  [ERR]  DYNAMIC_INCOMPLETE_COLLAPSE: Measurement branches have probabilities summing to 0.5000, expected 1.0
        -> Ensure all collapse outcomes are covered with probabilities summing to 1
```

Same report as JSON (`--json`):

```json
{
  "machine": "BrokenBell",
  "valid": false,
  "errors": [
    {
      "code": "ENTANGLEMENT_WITHOUT_GATE",
      "message": "State '|ψ>' is declared as entangled but no entangling gate (CNOT, CZ, etc.) leads to it",
      "severity": "warning",
      "suggestion": "Add a transition with a CNOT or other entangling gate action"
    },
    {
      "code": "DYNAMIC_NO_ENTANGLEMENT",
      "message": "State '|ψ>' should be entangled but verification failed: q0-q1: Schmidt rank 1 ≤ 1",
      "severity": "error",
      "suggestion": "Ensure the circuit creates an entangled state with CNOT or CZ gates"
    },
    {
      "code": "DYNAMIC_INCOMPLETE_COLLAPSE",
      "message": "Measurement branches have probabilities summing to 0.5000, expected 1.0",
      "severity": "error",
      "suggestion": "Ensure all collapse outcomes are covered with probabilities summing to 1"
    }
  ]
}
```

### Declaring invariants in Markdown

For precise dynamic checks, add an `## invariants` section to your machine. This tells stage 4b exactly which qubit pairs to verify rather than using the default adjacent-pair heuristic:

```markdown
## invariants
- entanglement(q0,q1) = True
- schmidt_rank(q0,q1) >= 2
```

---

## Commands

### `q-orca verify`

Parses and verifies a quantum machine definition through all 5 stages.

```bash
q-orca verify examples/bell-entangler.q.orca.md
q-orca verify examples/bell-entangler.q.orca.md --json
q-orca verify examples/bell-entangler.q.orca.md --strict
q-orca verify examples/bell-entangler.q.orca.md --skip-dynamic
```

| Flag | Description |
|------|-------------|
| `--json` | Output as JSON |
| `--strict` | Treat warnings as errors (exit 1 on any warning) |
| `--skip-completeness` | Skip stage 2: event completeness checks |
| `--skip-quantum` | Skip stage 4: unitarity, no-cloning, entanglement |
| `--skip-dynamic` | Skip stage 4b: QuTiP circuit simulation |
| `--skip-resource-bounds` | Skip stage 4c: resource invariant checks |
| `--backend BACKEND` | Verification backend: `qutip` (default), `cuquantum`, `cudaq` |
| `--gpu-count N` | Number of GPUs to use (cuquantum backend) |
| `--tensor-network` | Use tensor-network contraction (cuquantum backend) |

All bundled examples in `examples/` pass `--strict` on every CI run (Python 3.10–3.13).

**Example: passing strict verify with dynamic entanglement confirmed**

```bash
$ q-orca verify examples/bell-entangler.q.orca.md --strict --json
```
```json
{
  "machine": "BellEntangler",
  "valid": true,
  "errors": []
}
```

When stage 4b runs (QuTiP installed), it internally verifies `entropy(q0) ≈ 1.0` and `Schmidt rank(q0,q1) = 2` for the Bell state before emitting this clean result. Any failure there produces a `DYNAMIC_NO_ENTANGLEMENT` error — see [How Verification Works](#how-verification-works) for the full failure report format.

### `q-orca compile`

Compiles a machine to a target format.

```bash
q-orca compile mermaid examples/quantum-teleportation.q.orca.md
q-orca compile qasm examples/bell-entangler.q.orca.md
```

### `q-orca simulate`

Generates and optionally runs a Qiskit Python script.

```bash
# Output the Qiskit script (no execution)
q-orca simulate examples/bell-entangler.q.orca.md

# Run the simulation immediately
q-orca simulate examples/bell-entangler.q.orca.md --run

# Noisy simulation with 2048 shots
q-orca simulate examples/bell-entangler.q.orca.md --run --shots 2048

# Deterministic shots run (fixed RNG seed — useful in CI)
q-orca simulate examples/bell-entangler.q.orca.md --run --shots 1024 --seed 42

# Skip QuTiP verification
q-orca simulate examples/bell-entangler.q.orca.md --run --skip-qutip

# JSON output
q-orca simulate examples/bell-entangler.q.orca.md --run --json
```

---

## Examples

| File | Description |
|------|-------------|
| `bell-entangler.q.orca.md` | Bell state via Hadamard + CNOT |
| `quantum-teleportation.q.orca.md` | Teleports a qubit via Bell pair |
| `deutsch-jozsa.q.orca.md` | Constant vs balanced oracle detection |
| `ghz-state.q.orca.md` | 3-qubit GHZ state preparation |
| `vqe-heisenberg.q.orca.md` | Variational quantum eigensolver for Heisenberg XXX Hamiltonian |
| `active-teleportation.q.orca.md` | Active quantum teleportation using mid-circuit measurement and classical feedforward |
| `bit-flip-syndrome.q.orca.md` | 5-qubit bit-flip error correction with syndrome extraction |
| `qaoa-maxcut.q.orca.md` | QAOA MaxCut using parameterized RZZ two-qubit gates |
| `vqe-rotation.q.orca.md` | VQE rotation circuit with parameterized Rx gate |
| `predictive-coder-minimal.q.orca.md` | Minimal 3-qubit quantum predictive coder (one parametric model qubit) |
| `predictive-coder-learning.q.orca.md` | Full predictive coder with classical learning loop (drives the iterative runtime) |
| `larql-polysemantic-2.q.orca.md` | Concept projection over 2 non-orthogonal LARQL features (minimum mechanism) |
| `larql-polysemantic-12.q.orca.md` | 12-call-site parametric concept projection with uniform-overlap dictionary |
| `larql-polysemantic-clusters.q.orca.md` | Block-structured 12-concept polysemy on a 3-qubit register (3 clusters of 4) |
| `larql-gate-knn-grover.q.orca.md` | Grover-amplified gate-KNN lookup (per-layer kernel of LARQL inference) |

### Hybrid Classical + Quantum Demo

The `demos/hybrid_quantum_controller/` demo shows a classical [Orca](https://github.com/orca-lang/orca-lang) state machine orchestrating a Q-Orca quantum circuit through design, verification, refinement, and compilation.

**Architecture:**

- **Outer loop** — A classical `QuantumExperimentController` state machine (`orca-runtime-python`) manages the experiment lifecycle: `idle -> designing -> verifying -> refining -> compiling -> analyzing -> complete`
- **Inner loop** — Q-Orca parses, verifies, and compiles quantum circuits. When verification fails (e.g. a deadlock in the Bell entangler), the refinement step fixes the machine and re-verifies.

**Running:**

```bash
# Install both runtimes (into the project venv)
pip install orca-runtime-python
pip install q-orca[quantum]

# Run the demo
python demos/hybrid_quantum_controller/demo.py
```

**What it does:**

1. Parses a classical controller machine from `controller.orca.md`
2. Loads a deliberately broken Bell entangler (missing measurement transitions)
3. Q-Orca verification catches a `DEADLOCK` error on the `|psi>` state
4. The refinement step adds collapse branches (`|00_collapsed>`, `|11_collapsed>`)
5. Re-verification passes
6. Compiles the fixed circuit to OpenQASM 3.0, Mermaid, and Qiskit

The action handlers registered on the classical machine call Q-Orca's Python API directly (`parse_q_orca_markdown`, `verify`, `compile_to_qasm`, etc.), showing how the two runtimes compose.

### Quantum Evolve — Genetic Algorithm Demo

The `demos/quantum_evolve/` demo runs a genetic algorithm whose population consists of Q-Orca quantum state machines, evolved by an LLM.

**Architecture:**

- **Outer loop** — A classical `QuantumEvolver` state machine (`orca-runtime-python`) drives the GA lifecycle: `idle -> initializing -> evaluating -> selecting -> breeding -> ... -> converged | exhausted`
- **Population** — Each individual is a Q-Orca machine generated and scored by the LLM
- **Genetic operators** — LLM-assisted crossover (combine best elements of two parents), mutation (small structural changes), and fitness evaluation (scored 0–100 against a design goal)
- **Validation** — Invalid individuals are refined using Q-Orca's `refine_skill` before being discarded. Every generation contains only valid, unique machines.

**Running:**

```bash
# Install both runtimes
pip install orca-runtime-python
pip install q-orca[quantum]

# Run with defaults (3-qubit bit-flip code, population=3, generations=3)
python demos/quantum_evolve/demo.py

# Custom parameters
python demos/quantum_evolve/demo.py --population 5 --generations 5 --fitness-target 90

# Custom design goal
python demos/quantum_evolve/demo.py --goal "Design a quantum teleportation circuit with 3 qubits"
python demos/quantum_evolve/demo.py --goal-file my_goal.txt
```

**What it does:**

1. Parses a classical GA controller from `evolve.orca.md`
2. Seeds a population of N valid Q-Orca machines via LLM generation (with refinement for invalid outputs)
3. Each generation: LLM evaluates fitness → tournament selection → LLM-assisted crossover and mutation → Q-Orca verification
4. Elite carry-over preserves the best individual across generations
5. Converges when an individual meets the fitness target, or exhausts max generations
6. Reports the best machine with compiled OpenQASM 3.0 and Mermaid output

> **Note:** This demo requires an LLM API key. Set `api_key` in `orca.yaml` or export `ORCA_API_KEY`. Runtime depends on LLM speed — expect 1–5 minutes per generation.

---

## Machine Format

The full source for every example is in [`examples/`](examples/). Here is `bell-entangler.q.orca.md`:

```markdown
# machine BellEntangler

## context
| Field      | Type          | Default          |
|------------|---------------|------------------|
| qubits     | list<qubit>   | [q0, q1]         |
| outcome    | int           | -1               |

## events
- prepare_H
- entangle
- measure_done

## state |00>
> Ground state, no entanglement yet

## state |+0> = (|0> + |1>)|00>/√2
> After Hadamard on qubit 0 — superposition

## state |ψ> = (|00> + |11>)/√2
> Bell state after Hadamard + CNOT

## state |00_collapsed> [final]
> Collapsed to |00> after measurement

## state |11_collapsed> [final]
> Collapsed to |11> after measurement

## transitions
| Source          | Event        | Guard                  | Target              | Action                  |
|-----------------|--------------|------------------------|---------------------|-------------------------|
| |00>            | prepare_H    |                        | |+0>                | apply_H_on_q0           |
| |+0>            | entangle     |                        | |ψ>                 | apply_CNOT_q0_to_q1     |
| |ψ>             | measure_done | prob_collapse('00')=0.5| |00_collapsed>       | set_outcome_0           |
| |ψ>             | measure_done | prob_collapse('11')=0.5| |11_collapsed>       | set_outcome_1           |

## guards
| Name                | Expression                          |
|---------------------|-------------------------------------|
| prob_collapse('00') | fidelity(|ψ>, |00>) ** 2 ≈ 0.5     |
| prob_collapse('11') | fidelity(|ψ>, |11>) ** 2 ≈ 0.5     |

## actions
| Name                | Signature                          | Effect                     |
|---------------------|------------------------------------|----------------------------|
| apply_H_on_q0       | (qs) -> qs                         | Hadamard(qs[0])            |
| apply_CNOT_q0_to_q1 | (qs) -> qs                         | CNOT(qs[0], qs[1])         |
| set_outcome_0       | (ctx, val) -> Context              | ctx.outcome = 0            |
| set_outcome_1       | (ctx, val) -> Context              | ctx.outcome = 1            |

## effects
| Name          | Input                  | Output            |
|---------------|------------------------|-------------------|
| collapse      | state vector           | classical bit     |

## verification rules
- unitarity: all gates preserve norm
- entanglement: final state must have Schmidt rank >1 before measure
- completeness: all possible collapses covered (no missing branches)
- no-cloning: no copy ops allowed
```

> **Full source:** [`examples/bell-entangler.q.orca.md`](examples/bell-entangler.q.orca.md) — or view all examples in [`examples/`](examples/)

---

## Supported Gates

The effect-string grammar accepts the following gate kinds. All kinds listed
below are emitted by both the OpenQASM 3.0 and Qiskit compilers and verified
as unitary by the Stage-4 static checker.

| Arity            | Syntax                                  | Example                            |
|------------------|-----------------------------------------|------------------------------------|
| Single-qubit     | `H` / `Hadamard`, `X`, `Y`, `Z`, `T`, `S` | `Hadamard(qs[0])`                |
| Rotation         | `Rx`, `Ry`, `Rz`                        | `Rx(qs[0], pi/4)`                  |
| Two-qubit        | `CNOT` / `CX`, `CZ`, `SWAP`             | `CNOT(qs[0], qs[1])`               |
| Two-qubit param. | `CRx`, `CRy`, `CRz`, `RXX`, `RYY`, `RZZ` | `RZZ(qs[0], qs[1], gamma)`        |
| Three-qubit      | `CCX` / `CCNOT` / `Toffoli`, `CCZ`, `CSWAP` | `CCNOT(qs[0], qs[1], qs[2])`   |
| Many-controlled  | `MCX(c0, c1, …, t)`, `MCZ(c0, c1, …, t)` | `MCZ(qs[0], qs[1], qs[2], qs[3])` |

`MCX` / `MCZ` accept any number of control qubits ≥ 2; the last argument is
always the target. On the Qiskit side, shots-mode simulation transpiles the
generated circuit against a fixed basis before running on `BasicSimulator`
(which does not execute `mcx` natively).

---

## Mid-Circuit Measurement & Classical Feedforward

Q-Orca supports mid-circuit measurement with classical feedforward — measure a qubit mid-circuit and use the result to condition subsequent gates.

Declare classical bits in `## context`:

| Field | Type        | Default |
|-------|-------------|---------|
| bits  | list<bit>   | [c0]    |

Use `measure(qs[N]) -> bits[M]` as an action effect, and `if bits[M] == val: Gate(qs[K])` for conditional gates:

| Name              | Signature       | Effect                              |
|-------------------|-----------------|-------------------------------------|
| measure_q0        | (qs, bits) -> bits | measure(qs[0]) -> bits[0]        |
| apply_x_if_one    | (qs, bits) -> qs   | if bits[0] == 1: X(qs[1])        |

See [`examples/active-teleportation.q.orca.md`](examples/active-teleportation.q.orca.md) and [`examples/bit-flip-syndrome.q.orca.md`](examples/bit-flip-syndrome.q.orca.md) for full working examples.

---

## Parametric actions

An action signature can declare typed positional parameters after the leading
qubit-list parameter. Supported parameter types: `int` (for `qs[...]`
subscripts) and `angle` (for rotation-gate angle slots). Call sites in the
transitions table supply literal arguments, and the compiler substitutes them
into a fresh copy of the effect string at each site — so one template replaces
N copy-pasted action rows.

```markdown
## actions
| Name           | Signature          | Effect              |
|----------------|--------------------|---------------------|
| query_concept  | (qs, c: int) -> qs | Hadamard(qs[c])     |

## transitions
| Source          | Event     | Guard | Target       | Action              |
|-----------------|-----------|-------|--------------|---------------------|
| feature_loaded  | query_c0  |       | queried_c0   | query_concept(0)    |
| feature_loaded  | query_c1  |       | queried_c1   | query_concept(1)    |
| feature_loaded  | query_c2  |       | queried_c2   | query_concept(2)    |
```

Parameters are compile-time constants — there is no runtime parameter binding.
Out-of-range subscripts and unbound identifiers produce structured parse-time
errors pointing at the offending transition, not the template. Zero-parameter
signatures like `(qs) -> qs` and `(ctx) -> ctx` continue to parse unchanged.

See [`examples/larql-polysemantic-12.q.orca.md`](examples/larql-polysemantic-12.q.orca.md) for a 12-call-site end-to-end example (parametric concept projection over a non-orthogonal dictionary).

#### Structured overlap polysemy

The 12-call-site example above uses a *uniform*-overlap dictionary — every
pair of concepts has identical cross-talk 1/2 — so the polysemy table has
exactly two flat tiers (3/4 in-feature, 1/3 out-of-feature) with no
intra-cluster signal. [`examples/larql-polysemantic-clusters.q.orca.md`](examples/larql-polysemantic-clusters.q.orca.md)
ships a richer dictionary: 12 concepts grouped into 3 clusters of 4
(`capitals`, `fruits`, `vehicles`) on a compact 3-qubit register, prepared
as product states `Ry(q0, α) Ry(q1, β) Ry(q2, γ) |000>` via a multi-angle
parametric `prepare_concept(a, b, c)` action. Intra-cluster overlap is
uniform at 0.72 and inter-cluster overlap is < 0.10 — a **block**-structured
Gram matrix, matching the empirical polysemy signature sparse-autoencoder
studies of real transformer FFNs report (Elhage et al., `2209.10652`).

The optional `q_orca.compiler.concept_gram.compute_concept_gram(machine)`
helper returns the 12×12 Gram matrix for any machine following this
convention, so tests and demos can assert the block structure directly.
See [`demos/larql_polysemantic_clusters/demo.py`](demos/larql_polysemantic_clusters/demo.py)
for an end-to-end run that prints an ASCII heatmap of the Gram blocks and
recovers the three-tier polysemy column `1.0 / 0.72 / ≲ 0.09` empirically
from 12 Qiskit circuits.

Use `larql-polysemantic-12` as the minimum-mechanism demo (single `int`
parameter, one action template); use `larql-polysemantic-clusters` when
you want the clustered-phenomenon signature on top of the same parametric
mechanism.

---

### Verify output (5-stage pipeline)

```bash
$ q-orca verify examples/bell-entangler.q.orca.md --json
```
```json
{
  "machine": "BellEntangler",
  "valid": true,
  "errors": []
}
```

All 5 stages pass silently. To see individual stage results, use the Python API:

```python
from q_orca.skills import verify_skill

result = verify_skill({"file": "examples/bell-entangler.q.orca.md"})
# result = {
#   "status": "valid",    ← all 5 stages passed
#   "machine": "BellEntangler",
#   "states": 5,
#   "events": 3,
#   "transitions": 4,
#   "errors": []
# }
```

The 5 verification stages are:

| Stage | Module | Checks |
|-------|--------|--------|
| 1 Structural | `structural.py` | Reachability, deadlocks, orphan states |
| 2 Completeness | `completeness.py` | Every (state, event) pair has a transition |
| 3 Determinism | `determinism.py` | Guards are mutually exclusive |
| 4 Quantum | `quantum.py` + `dynamic.py` | Unitarity, no-cloning, entanglement (QuTiP), collapse completeness |
| 4c Resource bounds | `resources.py` | Static gate/depth/CX/T/qubit budgets vs `## invariants` |
| 5 Superposition | `superposition.py` | No superposition coherence leaks |

---

### Compile to Mermaid diagram

```bash
$ q-orca compile mermaid examples/bell-entangler.q.orca.md
```
```mermaid
stateDiagram-v2
  direction LR

  00 : |00>
  0 : |+0> = (|0> + |1>)|00>/√2
  unnamed : |ψ> = (|00> + |11>)/√2
  00_collapsed : |00_collapsed>
  11_collapsed : |11_collapsed>

  [*] --> 00
  00_collapsed --> [*]
  11_collapsed --> [*]

  00 --> 0 : prepare_H / apply_H_on_q0
  0 --> unnamed : entangle / apply_CNOT_q0_to_q1
  unnamed --> 00_collapsed : measure_done [prob_collapse('00')] / set_outcome_0
  unnamed --> 11_collapsed : measure_done [prob_collapse('11')] / set_outcome_1

  note right of 00
    Verification Rules:
    - unitarity: all gates preserve norm
    - entanglement: final state must have Schmidt rank >1 before measure
    - completeness: all possible collapses covered (no missing branches)
    - no_cloning: no copy ops allowed
  end note
```

---

### Compile to OpenQASM 3.0

```bash
$ q-orca compile qasm examples/bell-entangler.q.orca.md
```
```qasm
// Generated by Q-Orca compiler
// Machine: BellEntangler
OPENQASM 3.0;
include "stdgates.inc";

qubit[2] q;
bit[2] c;

int outcome = -1;

// Gate sequence derived from state machine transitions
// |00> -> |+0> via prepare_H
h q[0];
// |+0> -> |ψ> via entangle
cx q[0], q[1];
// |ψ> -> |00_collapsed> via measure_done
// |ψ> -> |11_collapsed> via measure_done

// Measurement
c[0] = measure q[0];
c[1] = measure q[1];
```

---

### Simulate with Qiskit

**Analytic (statevector) — fidelity + entanglement verification:**

```bash
$ q-orca simulate examples/bell-entangler.q.orca.md --run
```
```
  Machine: BellEntangler
  Success: True
  Probabilities:
    00: 50.00%
    01: 0.00%
    10: 0.00%
    11: 50.00%
  QuTiP Verification:
    Unitarity: VERIFIED
    Entanglement: VERIFIED
    Schmidt Rank: 2
```

**Probabilistic (shots) — observed counts:**

```bash
$ q-orca simulate examples/bell-entangler.q.orca.md --run --shots 512
```
```
  Machine: BellEntangler
  Success: True
  Counts: {'11': 269, '00': 243}
```

**JSON output** (useful for tooling):

```bash
$ q-orca simulate examples/bell-entangler.q.orca.md --run --json
```
```json
{
  "machine": "BellEntangler",
  "success": true,
  "probabilities": {
    "00": 0.5,
    "01": 0.0,
    "10": 0.0,
    "11": 0.5
  },
  "counts": null,
  "qutipVerification": {
    "unitarityVerified": true,
    "entanglementVerified": true,
    "schmidtRank": 2,
    "errors": []
  }
}
```

---

### Generated Qiskit script snippet

```python
# Generated by Q-Orca compiler
# Machine: BellEntangler

from qiskit import QuantumCircuit
from qiskit.quantum_info import Statevector, Operator
from qiskit.providers.basic_provider import BasicSimulator

qubit_count = 2
qc = QuantumCircuit(2)

# Gate sequence from state machine
qc.h(0)        # |00> --prepare_H--> |+0>
qc.cx(0, 1)    # |+0> --entangle--> |ψ>

# Simulation (analytic)
sv = Statevector(qc)
probs = sv.probabilities()
# ...

# QuTiP Verification
unitary_matrix = Operator(qc).data.tolist()
U = np.array(unitary_matrix)
# Unitarity: U U† ≈ I
# Entanglement: Schmidt rank across Bell partition
```

---

## MCP Server

Q-Orca includes an MCP (Model Context Protocol) server that exposes all skills as tools for AI clients like Claude Code.

### Setup

```bash
# Install with MCP dependencies
pip install -e ".[mcp]"

# Or install with all dependencies (quantum + MCP)
pip install -e ".[all]"
```

### Running the MCP Server

```bash
# Start the MCP server (uses stdio transport)
q-orca-mcp

# Or via Python module
python -m q_orca.mcp_server
```

### Claude Code Configuration

Add to your Claude Code settings (`~/.claude/settings.json` or project `.claude.json`):

```json
{
  "mcpServers": {
    "q-orca": {
      "command": "q-orca-mcp",
      "cwd": "/path/to/your/project"
    }
  }
}
```

### Available MCP Tools

| Tool | Description |
|------|-------------|
| `parse_machine` | Parse a Q-Orca machine and return structure as JSON |
| `verify_machine` | Run 5-stage verification pipeline |
| `compile_machine` | Compile to Mermaid, QASM, or Qiskit |
| `generate_machine` | Generate quantum machine from natural language spec |
| `refine_machine` | Fix verification errors using LLM |
| `simulate_machine` | Run Qiskit simulation |
| `server_status` | Get server version and LLM config |

### Using with Claude Code

Add Q-Orca to your Claude Code project by creating `.claude.json` in your project root:

```json
{
  "mcpServers": {
    "q-orca": {
      "command": "q-orca-mcp",
      "cwd": "."
    }
  }
}
```

Claude can then generate, verify, and refine quantum machines directly from natural language. Example prompt:

> "Generate a 3-qubit GHZ state machine, verify it, and compile to QASM"

Claude calls `generate_machine` → `verify_machine` → `compile_machine` in sequence, refining automatically if verification fails.

### LLM Provider Configuration

`ORCA_API_KEY` is the universal key — it works for any provider:

```bash
# Universal API key (works for any provider)
export ORCA_API_KEY=your-api-key

# Optional overrides
export ORCA_PROVIDER=anthropic   # anthropic, openai, minimax, ollama, grok
export ORCA_MODEL=claude-sonnet-4-6
export ORCA_MAX_TOKENS=4096
export ORCA_TEMPERATURE=0.7
```

Or via a YAML config file (`orca.yaml` or `.orca.yaml` in your project):

```yaml
# Anthropic (default)
provider: anthropic
model: claude-sonnet-4-6
api_key: ${ORCA_API_KEY}
```

```yaml
# MiniMax
provider: minimax
model: MiniMax-M2.7
api_key: ${ORCA_API_KEY}
```

```yaml
# OpenAI
provider: openai
model: gpt-5.4
api_key: ${ORCA_API_KEY}
```

Provider-specific keys (`ANTHROPIC_API_KEY`, `MINIMAX_API_KEY`, `OPENAI_API_KEY`) are also supported as fallbacks.

---

## Architecture

```mermaid
flowchart TD
    subgraph Input
        MD[".q.orca.md file"]
        NL[Natural Language]
    end

    MD --> Parser

    subgraph Parser
        MP[markdown_parser.py - Two-phase parse]
    end

    Parser --> AST[AST: QMachineDef]

    subgraph "Verifier (5 stages)"
        V1[structural.py - Reachability, deadlocks, orphans]
        V2[completeness.py - state/event coverage]
        V3[determinism.py - Guard mutual exclusion]
        V4[quantum.py - Unitarity, no-cloning, entanglement]
        V4D[dynamic.py - QuTiP: Schmidt rank, entropy]
        V5[superposition.py - Superposition coherence leak]
        V1 --> V2 --> V3 --> V4 --> V4D --> V5
    end

    AST --> Verifier
    Verifier --> VResult{Valid?}

    VResult -->|Yes| Compiler
    VResult -->|No| Refine[refine_skill - LLM fix loop]

    Refine -->|Fixed source| Parser
    NL --> Generate[generate_skill - LLM generation]
    Generate -->|Raw .q.orca.md| Parser

    subgraph Compiler
        CM[Mermaid]
        CQ[QASM 3.0]
        CK[Qiskit script]
    end

    Compiler --> MermaidDiagram[Rendered state diagram]
    Compiler --> QASMCode[Quantum circuit code]
    Compiler --> QiskitScript[Python simulation]

    QiskitScript --> Runtime[Python runtime]
    Runtime --> SimResult[Counts, Probabilities, Fidelity]

    style Verifier fill:#1b4f72,color:#fff
    style Compiler fill:#27ae60,color:#fff
    style Runtime fill:#8e44ad,color:#fff
    style NL fill:#f39c12,color:#fff
```

### Directory structure

```
q_orca/
├── __init__.py            # Package exports
├── ast.py                 # AST dataclasses
├── cli.py                 # CLI entrypoint
├── skills.py              # Skill functions (parse, verify, compile, generate, refine)
├── tools.py               # MCP tool JSON schemas
├── mcp_server.py          # MCP server (stdio JSON-RPC)
├── parser/
│   └── markdown_parser.py # Two-phase markdown parser
├── verifier/
│   ├── types.py           # Verification result types
│   ├── structural.py      # Reachability, deadlocks, orphans
│   ├── completeness.py    # (state, event) coverage
│   ├── determinism.py     # Guard mutual exclusion
│   ├── quantum.py         # Unitarity, no-cloning, entanglement
│   ├── superposition.py   # Superposition coherence leak
│   └── dynamic.py         # QuTiP circuit simulation
├── backends/
│   ├── base.py            # BackendAdapter ABC
│   ├── registry.py        # BackendRegistry with fallback logic
│   ├── qutip_backend.py   # Default QuTiP adapter
│   ├── cuquantum_backend.py # NVIDIA cuQuantum adapter (optional)
│   └── cudaq_backend.py   # NVIDIA CUDA-Q adapter (optional)
├── compiler/
│   ├── mermaid.py         # Mermaid state diagram
│   ├── qasm.py            # OpenQASM 3.0
│   ├── qiskit.py          # Qiskit Python script
│   └── cudaq.py           # NVIDIA CUDA-Q kernel
├── llm/
│   ├── provider.py        # Abstract LLM provider interface
│   ├── anthropic.py       # Anthropic provider
│   ├── openai.py          # OpenAI provider
│   ├── minimax.py         # MiniMax provider
│   ├── ollama.py          # Ollama provider
│   └── grok.py            # Grok provider
├── config/
│   ├── loader.py          # YAML/env config loader
│   └── types.py           # Config types
└── runtime/
    ├── types.py           # Simulation result types
    └── python.py          # Python subprocess runner + simulation
```

---

## Benchmarks & compute requirements

The [`benchmarks/`](benchmarks/) directory contains scaling sweeps used to size
GPU compute requests in our grant applications (NVIDIA / IBM / Microsoft):

- [`benchmarks/qaoa/scaling_sweep.py`](benchmarks/qaoa/scaling_sweep.py) — QAOA MaxCut, 3–20 qubits, CPU + GPU, with `--export-qasm` for OpenQASM 2.0 dumps
- [`benchmarks/vqe/scaling_sweep.py`](benchmarks/vqe/scaling_sweep.py) — VQE Heisenberg XXX, 4–20 qubits, COBYLA optimizer
- [`benchmarks/gpu_vs_cpu.py`](benchmarks/gpu_vs_cpu.py) — combined sweep that emits a side-by-side table to `benchmarks/reports/gpu_vs_cpu_latest.md`
- [`benchmarks/llm_evolution.py`](benchmarks/llm_evolution.py) — LLM-driven QAOA parameter evolution (Claude Haiku / GPT-4o-mini), the flagship demo for the LLM × GPU-simulator pairing

```bash
pip install -e ".[quantum]"
python benchmarks/gpu_vs_cpu.py --backend cpu        # CPU baseline, no GPU needed
python benchmarks/gpu_vs_cpu.py --backend gpu        # requires CUDA-Q + cuStateVec
```

Backend honesty: each result row records both `backend_requested` (the CLI
flag) and the actual `device` that ran, so a CPU fallback never gets
mistaken for a GPU number.

The narrative grant memo lives at [`docs/compute-needs.md`](docs/compute-needs.md);
[`benchmarks/reports/resource_usage.md`](benchmarks/reports/resource_usage.md)
holds the projected GPU-hour budget.

---

## Roadmap

Feature planning goes through OpenSpec. Active proposals live in [`openspec/changes/`](openspec/changes/); archived (shipped) proposals in [`openspec/changes/archive/`](openspec/changes/archive/). Items below are marked with their spec status.

### Recently shipped

Each of these entered main with a full OpenSpec proposal → implementation → archive cycle.

- ✅ **Parameterized single-qubit gates** — `Rx(θ)`, `Ry(θ)`, `Rz(θ)` with symbolic angles *(`add-parameterized-gates`, `0.3.3`)*
- ✅ **Parameterized two-qubit gates** — `CRx`, `CRy`, `CRz`, `RXX`, `RYY`, `RZZ` *(`add-parameterized-two-qubit-gates`, [PR #5](../../pull/5))*
- ✅ **Context-resolved angles** — rotation gates accept context field references (`theta[0]`) in addition to literals *(`context-angle-references`)*
- ✅ **Mid-circuit measurement + classical feedforward** — `measure(...) -> bits[N]` + `if bits[N] == v: Gate(...)` *(`mid-circuit-measurement`, [PR #5](../../pull/5))*
- ✅ **Classical context updates** — `theta[0] -= eta` / conditional mutations on `int` and `list<float>` with static type-checking *(`add-classical-context-updates`, [PR #21](../../pull/21))*
- ✅ **Iterative runtime for context updates** — `simulate_machine` dispatches context-update machines to `q_orca.runtime.iterative`, which walks back-edges, rebuilds per-segment Qiskit circuits at the live context, and threads a deterministic per-iteration seed. Ships the QPC learning loop as `examples/predictive-coder-learning.q.orca.md`. *(`run-context-updates`)*
- ✅ **Pluggable execution backends** — cuQuantum GPU, CUDA-Q compilation target *(`execution-backends`, [PR #7](../../pull/7))*
- ✅ **Noise models** — `depolarizing`, `amplitude_damping`, `phase_damping`, `thermal(T1, T2)` in `## context`, propagated into Qiskit Aer *(`fix-noise-models`)*
- ✅ **Resource estimation (Stage 4c)** — `## resources` and `## resource invariants` sections; `gate_count`, `depth`, `cx_count`, `t_count`, `logical_qubits` checked against budgets at verify time *(`add-resource-estimation`, [PR #37](../../pull/37))*
- ✅ **Parametric actions** — one `query_concept | (qs, c: int) -> qs | Hadamard(qs[c])` action callable as `query_concept(0)`, `query_concept(1)`, ... instead of N copy-pasted rows *(`extend-gate-set-and-parametric-actions`)*
- ✅ **Gate-parser consolidation** — single shared parser for parser, Qiskit/QASM compilers, and dynamic verifier — eliminates the drift bugs that came from three independent implementations *(`consolidate-gate-parser`)*
- ✅ **CCZ / MCX / MCZ gate set** — many-controlled gates formalized and round-tripped through every backend
- ✅ **Completeness-check hardening** — measurement-bearing transitions are detected by action effect, not just event name *(`harden-completeness-detection`)*
- ✅ **Bell-pair compiler fixture** — per-backend regression tests against the canonical two-qubit circuit *(`bell-pair-example`)*
- ✅ **LARQL polysemantic clusters** — block-structured 12-concept polysemy on a 3-qubit register, matching the empirical signature reported by sparse-autoencoder studies of real transformer FFNs *(`add-polysemantic-clusters`)*

See each folder under [`openspec/changes/archive/`](openspec/changes/archive/) for the proposal, design, and scenarios that shipped.

### Near-term — specced, implementation pending

Proposals with an OpenSpec folder and agreed scope, awaiting code.

- 🧾 **Cross-machine composition** — `[invoke: Child(args) shots=N]` state-level delegation with static arg/return type-checking and a `## returns` section. Mermaid renders composed machines; QASM/Qiskit refuse until a runtime lands. *([`add-parameterized-invoke`](openspec/changes/add-parameterized-invoke/))*
- 🧾 **Per-state runtime assertions** — `[assert: classical(qs[0]); entangled(qs[0], qs[1])]` annotations backed by statistical sampling on Stage 4b, with a `## assertion policy` section for shots/confidence/on-failure. *([`add-runtime-state-assertions`](openspec/changes/add-runtime-state-assertions/))*
- 🧾 **MPS concept encoding** — hierarchical polysemantic concept registers encoded as matrix-product states, extending the LARQL polysemantic family beyond the dense-statevector regime. *([`add-mps-concept-encoding`](openspec/changes/add-mps-concept-encoding/))*

### Longer-term — research / not yet specced

Ideas we've sketched but not yet turned into an OpenSpec proposal.

- 📝 **Quantum predictive coder** — 3-register (model / data / ancilla) predictive-coding architecture with classical feedback. Research proposal at [`docs/research/spec-quantum-predictive-coder.md`](docs/research/spec-quantum-predictive-coder.md); drives several of the specced items above.
- 💡 **Composed-machine runtime** — the Python dispatcher that actually walks a composed machine, batches shots, and wires child returns back into parent context. Parked as a follow-up under `add-parameterized-invoke`.
- 💡 **QASM 3.0 import** — lift existing `.qasm` files into Q-Orca state machines.
- 💡 **VS Code extension** — syntax highlighting, inline verification on save, Mermaid preview.

### Backlog

- 🧰 [`tech-debt-backlog`](openspec/changes/tech-debt-backlog/) — rolling collection of small cleanup items (naming, error-reporting consistency) that aren't big enough to warrant their own change.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions, good first issues, and research directions. Feature specs live under [`openspec/changes/`](openspec/changes/) (active) and [`openspec/changes/archive/`](openspec/changes/archive/) (shipped).
