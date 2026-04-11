# Q-Orca Language: Coverage Analysis & Roadmap Suggestions

> Generated April 2026 via cross-reference of the q-orca-lang repository and the q-orca-kb knowledge base (1,100+ indexed quantum computing papers).

---

## 1. Current Coverage

### Examples (5)

| File | Algorithm / Protocol | Gates / Concepts |
|---|---|---|
| `bell-entangler.q.orca.md` | Bell state preparation | H, CNOT, entanglement, measurement collapse |
| `ghz-state.q.orca.md` | 3-qubit GHZ state | H, CNOT chain, multi-qubit entanglement |
| `deutsch-jozsa.q.orca.md` | Deutsch–Jozsa algorithm | Oracle, balanced vs constant detection |
| `quantum-teleportation.q.orca.md` | Quantum teleportation | Bell pair, Bell measurement, classical feed-forward |
| `vqe-heisenberg.q.orca.md` | VQE on Heisenberg XXX | Variational ansatz, Hamiltonian expectation |

### Demos (2)

| Demo | Architecture |
|---|---|
| `hybrid_quantum_controller/` | Classical Orca state machine orchestrating Q-Orca circuits (design → verify → refine → compile lifecycle) |
| `quantum_evolve/` | LLM-driven genetic algorithm evolving Q-Orca machines across generations |

### Coverage Gaps

The current examples cover **entanglement, basic gate sequences, one oracle algorithm, one variational algorithm, and one quantum protocol**. Conspicuously absent:

- Iterative / looping state machines (Grover, QAOA, Simon's)
- Error correction and syndrome extraction
- Quantum communication / cryptography protocols (QKD)
- Quantum walks
- Multi-register algorithms (QPE)
- Superdense coding (complement to teleportation)

---

## 2. Suggested Examples

### 2.1 Grover's Search (`grover-search.q.orca.md`)

**Why:** Grover's algorithm has the most naturally state-machine-shaped structure of any major quantum algorithm: uniform superposition → oracle marking → amplitude amplification diffuser → loop √N times → collapse to solution. The looping structure is a direct forcing function for the `[loop N]` language enhancement (§4.3).

**States:** `|0>` → `|uniform>` → `|marked>` → `[diffuse]` → `|amplified>` → (loop) → `|solution_collapsed>`

**New verification challenge:** Loop-body unitarity must be preserved across all N iterations. The verifier needs to confirm the diffusion operator is a valid reflection about the uniform superposition.

**KB grounding:** Grover (1996) `quant-ph/9602019` — indexed in q-orca-kb.

---

### 2.2 Quantum Phase Estimation (`quantum-phase-estimation.q.orca.md`)

**Why:** QPE is the engine inside Shor's algorithm and quantum chemistry eigensolvers. It introduces a new structural pattern not in any current example: a **multi-register machine** where an ancilla register (the phase register) runs through a ladder of controlled-U gates while a data register holds the eigenstate. The inverse QFT then collapses the ancilla.

**States:** `|ancilla_0, eigenstate>` → `|H_applied>` → `|controlled_U_ladder>` → `|QFT_inv_applied>` → `|phase_measured>`

**New verification challenge:** Cross-register entanglement declarations, and verifying that the controlled-U gates are applied with the correct qubit-index doubling pattern.

**KB grounding:** Shor (1995) `quant-ph/9508027` — indexed in q-orca-kb.

---

### 2.3 QAOA MaxCut (`qaoa-maxcut.q.orca.md`)

**Why:** The Quantum Approximate Optimization Algorithm alternates parameterized cost-layer unitaries `exp(-iγC)` and mixer-layer unitaries `exp(-iβB)`. This is a parameterized looping machine — and essentially cannot be written cleanly in the current language without `Rx(θ)` / `Rz(θ)` support. It is the single strongest forcing function for the parameterized gates roadmap feature.

**States:** `|0>` → `|uniform>` → `[cost_layer(γ)]` → `[mixer_layer(β)]` → (loop p times) → `|measured>`

**New verification challenge:** Guard mutual-exclusion across parameterized transitions; verifying that the cost-layer Hamiltonian exponent is valid for the given graph.

**KB grounding:** Farhi, Goldstone & Gutmann (2014) `1411.4028` — indexed in q-orca-kb.

---

### 2.4 BB84 QKD Protocol (`bb84-qkd.q.orca.md`)

**Why:** BB84 is the foundational quantum key distribution protocol. Its execution is a multi-phase state machine with alternating quantum and classical steps, introducing a new state category not in any current example: protocol states involving a `[send]` / `[receive]` / `[classical]` boundary.

**States:** `|prepare>` → `|transmit>` → `[basis_sift]` → `[error_estimate]` → `|key_extracted>` or `|abort>`

**New verification challenge:** The `[send]` transition on the transmitter machine must trigger a no-cloning check. The `|abort>` branch must be reachable. Error rate threshold guard on `[error_estimate]`.

**KB grounding:** Quipper paper (1411.6024) references BB84 extensively — indexed in q-orca-kb.

---

### 2.5 3-Qubit Bit-Flip Error Correction (`bit-flip-correction.q.orca.md`)

**Why:** Error correction is the canonical practical use of state machines in quantum hardware — syndrome extraction automata run in real time on every quantum processor. This example demonstrates the full encode → inject error → extract syndrome → decode → correct cycle in Q-Orca syntax. Note that the `quantum_evolve` demo already targets a 3-qubit bit-flip code as its default goal, implying this is already an intended use case.

**States:** `|logical_0>` (encoded) → `|noisy>` (after error injection) → `|syndrome_extracted>` → `[error_decision: none/qubit0/qubit1/qubit2]` → `|corrected>`

**New verification challenge:** Ancilla qubit reset between syndrome rounds; syndrome measurement must not disturb the data qubit logical state (verifiable via commutativity check with the logical operators).

**KB grounding:** Fowler et al. surface codes (1208.0928), Steane (quant-ph/9605043), Calderbank-Shor (quant-ph/9508018) — all indexed in q-orca-kb.

---

### 2.6 Discrete Quantum Walk on a Line (`quantum-walk-line.q.orca.md`)

**Why:** A discrete quantum walk is arguably the closest thing to a classical finite automaton in quantum computing. The walker's position is the machine state; the coin register determines the transition direction; the shift operator moves the walker conditionally on the coin. This maps almost perfectly to Q-Orca's state+transition table model. The quadratic speedup over classical random walks (Aharonov et al.) and the exponential algorithmic speedup (Childs et al.) make this a theoretically rich example.

**States:** `|pos_−N, coin>` … `|pos_0, coin>` … `|pos_N, coin>` with parameterized N; transitions driven by `coin: Hadamard` and `shift: conditional_on_coin`.

**New verification challenge:** Walk boundary conditions (position register bounded); coin unitarity checked independently from shift unitarity; superposition coherence verified across all position states simultaneously; Schmidt rank check confirms coin and position remain entangled after each step.

**KB grounding:** Aharonov, Ambainis, Kempe & Vazirani (2001) `quant-ph/0012090`; Childs et al. (2003) `quant-ph/0209131` — both indexed in q-orca-kb.

---

### 2.7 Superdense Coding (`superdense-coding.q.orca.md`)

**Why:** The natural companion to the teleportation example. Two classical bits are transmitted using one qubit over a quantum channel, using a pre-shared Bell pair. Completes the foundational quantum communication trilogy: Bell → Teleportation → Superdense Coding, and creates a clean tutorial progression for new users. Short and tightly scoped — under 30 lines of Q-Orca Markdown.

**States:** `|Bell_pair_shared>` → `[encode_00/01/10/11]` → `|encoded>` → `[Bell_measurement]` → `|00_decoded>` / `|01_decoded>` / `|10_decoded>` / `|11_decoded>`

**KB grounding:** Categorical semantics paper (quant-ph/0402130) — indexed in q-orca-kb.

---

### 2.8 Simon's Algorithm (`simons-algorithm.q.orca.md`)

**Why:** Simon's algorithm finds the hidden period of a 2-to-1 function exponentially faster than classically, and is the historical precursor to Shor's algorithm. Its repeat-until-sufficient-constraints loop is another important test of looping state machine support, and the post-processing (Gaussian elimination over GF(2)) creates a clean classical / quantum handoff.

**States:** `|0>` → `|uniform>` → `[oracle]` → `[first_register_measured]` → `|constraint_collected>` → (loop until n−1 linearly independent constraints) → `|period_found>`

**KB grounding:** Moore & Crutchfield quantum grammars (quant-ph/9707031) — indexed in q-orca-kb.

---

## 3. Suggested Demos

### 3.1 QKD Eavesdropping Simulation (`demos/qkd_protocol/`)

**Architecture:** Three interacting state machines — Alice (sender), Bob (receiver), and Eve (eavesdropper) — each defined as separate Q-Orca or hybrid Orca machines and composed by the demo runner.

- **Alice machine:** Prepares qubits in random bases, transmits to channel.
- **Eve machine:** Intercepts, measures in a random basis, re-transmits. Introduces a detectable error rate (~25% in BB84).
- **Bob machine:** Receives, measures in a random basis, performs basis sifting with Alice via classical channel.

**What it demonstrates:** Multi-machine composition (the primary longer-term roadmap feature); the effect of eavesdropping on measured error rate; how quantum mechanics makes eavesdropping detectable by physics rather than by trust.

**Why now:** This is the most compelling possible demonstration of multi-machine composition and would make an ideal flagship demo when that roadmap feature ships. The three-machine structure also gives the `[send]` / `[receive]` protocol state annotations (§4.4) their first full workout.

---

### 3.2 Error Correction Pipeline (`demos/error_correction_pipeline/`)

**Architecture:** End-to-end fault-tolerance demonstration:

1. **Encoder** (Q-Orca machine): Takes a logical qubit and encodes it into a 3-qubit bit-flip code.
2. **Noise injector** (classical Python): Flips a random physical qubit with probability p.
3. **Syndrome extractor** (Q-Orca machine): Measures ancilla qubits to extract the 2-bit syndrome without disturbing the logical state.
4. **Classical decoder** (Orca state machine): Maps syndrome → correction operation — a classical automaton with 4 states: `no_error`, `flip_q0`, `flip_q1`, `flip_q2`.
5. **Corrector:** Applies X gate to the identified qubit.

**What it demonstrates:** The full classical-quantum boundary; the classical decoder as an explicit Orca state machine (not buried in Python logic); that error correction is fundamentally a hybrid system where a classical automaton drives quantum correction operations.

**KB grounding:** Fowler et al. (1208.0928) describes the classical decoder automaton structure — indexed in q-orca-kb.

---

### 3.3 Quantum Walk Search Demo (`demos/quantum_walk_search/`)

**Architecture:** A classical Orca controller sets up a marked graph, instantiates a Q-Orca quantum walk machine, runs it for O(√N) steps, and measures the position register. Compares walk-based search to classical random walk on the same graph, plotting convergence.

**What it demonstrates:** Quantum walks as a search primitive; the speedup argument made tangible by running both classical and quantum variants; position-register state space as a natural Q-Orca state enumeration.

---

### 3.4 Interactive Tutorial Runner (`demos/tutorial/`)

**Architecture:** A step-by-step guided demo that runs all examples in sequence, displaying the Mermaid diagram, QASM output, and simulation results side by side. Designed as onboarding for new users — the complete Q-Orca pipeline (parse → verify → compile → simulate) in a single automated invocation.

---

## 4. Language Enhancement Suggestions

### 4.1 Qubit Role Types in `## context`

**Current syntax:**
```markdown
| qubits | list<qubit> | [q0, q1, q2] |
```

**Proposed syntax:**
```markdown
| qubits | list<qubit> | [q0:data, q1:ancilla, q2:syndrome] |
```

**Available roles:** `data | ancilla | syndrome | communication | coin | position`

**Verifier implications:**
- `ancilla` qubits must be reset to `|0>` between use (detects ancilla recycling bugs)
- `syndrome` qubits must be measured in every cycle (detects unconverged syndromes)
- `communication` qubits trigger no-cloning checks on `[send]` transitions
- `coin` / `position` qubits unlock walk-specific verification rules (§4.5)

Low syntax cost, high verification payoff. Directly enables error correction and protocol examples.

---

### 4.2 Parameterized Gate Support in Actions *(on near-term roadmap)*

**Proposed syntax (extends roadmap item):**
```markdown
| apply_Rx_q0 | (qs, θ) -> qs | Rx(θ, qs[0]) |
| apply_Rz_q0 | (qs, γ) -> qs | Rz(γ, qs[0]) |
```

**Parameter binding in transitions:**
```markdown
| |uniform> | cost_layer | γ=π/4 | |cost_applied> | apply_Rz_q0(γ) |
```

**Verifier implications:** Parameter values must produce valid unitary operators. Symbolic angles (e.g. `θ = π/4`) are evaluated before the unitarity check.

Parameterized gates are required by QAOA, VQE extensions, and any hardware-efficient ansatz. This note adds a suggested syntax for parameter binding in the transition table to complement the existing roadmap item.

---

### 4.3 Loop State Annotation `[loop N]`

**Proposed syntax:**
```markdown
## state |amplified> [loop sqrt(N)]
```

Or for adaptive loops:
```markdown
## state |constraint_collected> [loop until: constraints_linearly_independent()]
```

**Back-edge in the transition table:**
```markdown
| |amplified> | check_convergence | not_converged | |marked>             | identity |
| |amplified> | check_convergence | converged     | |solution_collapsed> | measure_all |
```

**QASM / Qiskit compiler implications:** Emit a `for` loop in QASM 3.0 rather than unrolling. Qiskit compiler emits a `for _ in range(n)` block around the gate sequence.

**Verifier implications:** Loop body checked for unitarity once (applies to all iterations); termination guaranteed (convergence condition must be reachable).

Without this, Grover, QAOA, Simon's, and QPE all require manually unrolling loops, which defeats the purpose of a high-level state machine description. This is the single highest-leverage language addition relative to the algorithm coverage it unlocks.

---

### 4.4 Protocol State Annotations

**Proposed annotations:**
```markdown
## state |transmit> [send: q0 -> Bob]
## state |receive>  [receive: q1 <- Alice]
## state |sift>     [classical]
## state |abort>    [final, classical]
```

**Semantics:**
- `[send: q -> target]` — qubit `q` leaves the local register; triggers no-cloning verification; qubit removed from local context after this state
- `[receive: q <- source]` — qubit `q` enters the local register; must be declared as `role: communication`
- `[classical]` — all qubits have collapsed; superposition coherence check passes trivially
- `[final, classical]` — terminal classical state

**Cross-machine consistency:** A `[send: q -> Bob]` in Alice's machine must be paired with a `[receive: q <- Alice]` in Bob's machine when machines are composed.

Required for BB84, the QKD eavesdropping demo, and any multi-party quantum protocol.

---

### 4.5 Quantum Walk Primitives as First-Class Action Types

**Proposed action keywords:**
```markdown
| coin_flip | (qs) -> qs | coin: Hadamard(qs[coin])                                   |
| shift_pos | (qs) -> qs | shift: pos+1 if coin=|1>, pos-1 if coin=|0>                |
```

**Proposed context fields:**
```markdown
| walk_space          | int         | 11              |   # positions −5..+5
| coin_qubit          | qubit       | c               |
| position_register   | list<qubit> | [p0, p1, p2]    |
```

**Verifier implications:**
- Position register bounded: walk cannot step outside `[−walk_space/2, +walk_space/2]`
- Coin and shift unitarity checked independently
- Superposition coherence verified across all position states simultaneously
- Schmidt rank check: coin and position must remain entangled after each step (detects degenerate coins)

Quantum walks map almost perfectly to Q-Orca's existing model and are the best-grounded bridge between classical automata theory and quantum computing.

---

### 4.6 Extended `## invariants` Expressions

**Current support:**
```markdown
## invariants
- entanglement(q0,q1) = True
- schmidt_rank(q0,q1) >= 2
```

**Proposed extensions:**
```markdown
## invariants
- fidelity(|ψ>, |Φ+>) >= 0.99             # output fidelity target (stage 4b)
- gate_count <= 20                         # circuit depth budget (stage 4, static)
- T_gate_count <= 5                        # fault-tolerance T-gate budget (stage 4)
- error_rate(|solution_collapsed>) <= 0.01 # noise-model-aware (stage 4b)
- coherence_time(q0) <= T2                 # decoherence constraint (stage 4b)
```

**Implementation notes:**
- `fidelity(...)` — computed by stage 4b (QuTiP) against a target state vector
- `T_gate_count` — counted statically from the action table during stage 4; relevant for fault-tolerant resource estimation per Fowler et al.
- `error_rate(...)` — requires a `## noise_model` section; evaluated by stage 4b under the declared noise channel

The invariant section is currently underused relative to its potential. Fidelity targets, depth budgets, and T-gate counts are the primary quantities practitioners care about when benchmarking circuits.

---

### 4.7 `## noise_model` Section *(on near-term roadmap — syntax proposal)*

**Proposed syntax:**
```markdown
## noise_model
| Channel            | Target           | Parameters                        |
|--------------------|------------------|-----------------------------------|
| depolarizing       | all_gates        | p=0.001                           |
| amplitude_damping  | all_qubits       | T1=100µs                          |
| phase_damping      | all_qubits       | T2=80µs                           |
| thermal            | all_qubits       | n_bar=0.05                        |
| readout_error      | all_measurements | p0given1=0.01, p1given0=0.02      |
```

**Compiler implications:** Qiskit compiler automatically constructs a `NoiseModel` from this section and passes it to `AerSimulator`. No user-side noise model code required.

**Verifier implications:** Stage 4b runs under the declared noise model; a warning is emitted if `T1 < circuit_duration` (gate sequence too slow for the declared coherence time).

Directly motivated by the hardware characterization methodology in Kandala et al. (1704.05018) — indexed in q-orca-kb.

---

## 5. Prioritized Implementation Order

### Near-term (unlocks the most new examples)

| Priority | Enhancement | Examples unlocked |
|---|---|---|
| 1 | Parameterized gates `Rx(θ)`, `Rz(θ)` *(roadmap)* | QAOA, VQE extensions |
| 2 | Loop annotation `[loop N]` / `[loop until: ...]` | Grover, QAOA, Simon's, QPE |
| 3 | Qubit role types in `## context` | Error correction, QKD |

### Medium-term (unlocks demos)

| Priority | Enhancement | Demo unlocked |
|---|---|---|
| 4 | Protocol state annotations `[send]` / `[receive]` / `[classical]` | BB84, QKD eavesdrop demo |
| 5 | `## noise_model` section *(roadmap)* | Error correction pipeline demo |
| 6 | Extended invariant expressions | All examples (fidelity, T-gate budget) |

### Longer-term (roadmap items)

| Priority | Enhancement | Demo unlocked |
|---|---|---|
| 7 | Multi-machine composition with shared qubits *(roadmap)* | QKD eavesdropping demo |
| 8 | Quantum walk primitives | Walk example, walk search demo |
| 9 | QASM 3.0 import *(roadmap)* | — |

---

## 6. KB Sources

Papers indexed in q-orca-kb that directly ground these recommendations:

| Recommendation | Paper | arXiv ID |
|---|---|---|
| Grover example | Grover, "Fast quantum mechanical algorithm for database search" | quant-ph/9602019 |
| QPE example | Shor, "Polynomial-time algorithms for prime factorization" | quant-ph/9508027 |
| QAOA example | Farhi, Goldstone & Gutmann, "QAOA" | 1411.4028 |
| BB84 / QKD example | Quipper (BB84 protocol references) | 1411.6024 |
| Error correction example | Fowler et al., "Surface codes" | 1208.0928 |
| Error correction example | Steane, "Quantum error correction" | quant-ph/9605043 |
| Quantum walk example | Aharonov, Ambainis, Kempe & Vazirani, "Quantum walks on graphs" | quant-ph/0012090 |
| Quantum walk example | Childs et al., "Exponential speedup by quantum walk" | quant-ph/0209131 |
| Noise model syntax | Kandala et al., "Hardware-efficient VQE" | 1704.05018 |
| T-gate budgets in invariants | Fowler et al., "Surface codes" | 1208.0928 |
| Protocol state annotations | Gay & Nagarajan, "Communicating Quantum Processes" | quant-ph/0409119 |
| Multi-machine composition | Jorrand & Lalire, "Toward a Quantum Process Algebra" | quant-ph/0312067 |
| Categorical semantics / superdense coding | Abramsky & Coecke, "Categorical Semantics of Quantum Protocols" | quant-ph/0402130 |
| ZX-calculus / invariant verification | Coecke & Duncan, "Interacting Quantum Observables" | 0906.4725 |
