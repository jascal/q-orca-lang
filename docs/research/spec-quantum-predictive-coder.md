# Research: Quantum Predictive Coder

> Generated: 2026-04-18 — research kickoff from user-supplied machine sketch `/tmp/QuantumPredictiveCoder.q.orca.md`

---

**Summary:** This document is a *research proposal*, not a queued feature. It sketches what a scientifically honest q-orca machine for a **quantum predictive coder** (QPC) would look like — a variational quantum circuit that (1) maintains a generative model of some target distribution on a "model" register, (2) interacts that model with a "data" register, (3) extracts a prediction-error signal via ancilla measurement, and (4) updates the model via a classical feedback loop that minimizes the extracted error. The proposal identifies why the four-state sketch the user supplied is *not* viable as written, names the q-orca features required to express a real QPC (all already on the roadmap or shipped), and grounds the design in the arXiv literature available through q-orca-kb. It also explicitly names the literature gap — no existing arXiv work bridges Friston-style predictive coding / active inference to native quantum circuits — which is what makes this a research project rather than a port of a known result.

---

**Why the user-supplied sketch is not viable as a q-orca machine:**

The `/tmp/QuantumPredictiveCoder.q.orca.md` sketch claims 2 qubits (`[q0_model, q1_data]`), four states (`|00>`, `|ψ_pred>`, `|ψ_error>`, `|posterior>`), and the gate sequence `H(q0); CNOT(q0, q1); PhaseGate(π·error) on q0; Rx(0.5) on q0`. The verifier (correctly) rejects it. The substantive scientific problems are:

- **No error extraction mechanism.** The sketch declares a context field `error: float` but never writes it. The `compute_error` transition is unguarded to anything quantum — `fidelity(|ψ_error>, Bell)` is a classical verification rule, not an observable the circuit can read. A real QPC must *measure* something to produce a classical error scalar, which requires an ancilla and mid-circuit measurement.
- **Phase kickback without a controlling qubit.** `PhaseGate(π·error) on qs[0]` is a single-qubit rotation, not phase kickback. True phase kickback requires a control register whose eigenvalue gets kicked onto a target — the sketch has neither the controls nor the eigenstructure.
- **Variational update is a single fixed `Rx(0.5)`.** No parameters, no optimizer, no gradient — so there is no "model update" happening, only a fixed rotation that makes the circuit non-unitary-overall (never re-prepares a fresh data qubit) and eventually drifts off the code subspace.
- **The predictive-coding *loop* is not a quantum loop.** Predictive coding requires: generate prediction → compare to data → extract error → update model parameters → repeat. Steps 3 and 4 are classical (measurement outcome → classical optimizer → new circuit parameters). A 4-state unitary machine with no measurement and no parameter binding cannot represent this.

In short: the sketch collapses three distinct registers (model / data / ancilla) into two, one of which (`error: float`) lives nowhere in the Hilbert space. A real QPC is ≥3 qubits, has an explicit measurement, and has an explicit classical feedback arc.

---

**Proposed architecture:**

Minimum viable QPC requires three pieces:

1. **Generative model register** (1+ qubits) — prepared by a parameterized ansatz `U_θ |0>`, where `θ` is a vector of rotation angles stored in the machine's context. This is the "prior."
2. **Data register** (1+ qubits) — prepared from a training distribution (in the demo, a fixed state encoded as a circuit; in a real use case, a state-preparation subroutine from a classical input).
3. **Error ancilla** (1 qubit, minimum) — the "predictive error unit." After a comparison operation between model and data (e.g., a SWAP-test circuit or a parity check), the ancilla holds a single bit whose expectation value is a monotone function of model/data fidelity.

The predictive-coding loop is then a **hybrid** q-orca machine: the unitary pieces are expressed as gates and mid-circuit measurement; the parameter update is expressed as a *context transition* that writes new angle values into `θ`, gated on the classical measurement bit. The existing q-orca primitives that make this expressible:

- `list<qubit>` context fields with role annotations (`[model]`, `[data]`, `[ancilla]`) — partially shipped; role annotations are on the roadmap
- Parametric gates with `angle_context` references — **shipped** (see `openspec/changes/archive/2026-04-18-context-angle-references/`)
- Mid-circuit measurement (`measure(qs[N]) -> bits[M]`) and classical-feedforward conditionals — **shipped** (archive `2026-04-17-mid-circuit-measurement`)
- Runtime state-category assertions (e.g., `[assert:separable]`, `[assert:entangled]`) — **proposed** in `openspec/changes/add-runtime-state-assertions/`; would let the verifier confirm the ancilla is disentangled after measurement
- Parameter-update actions that mutate `list<float>` context fields — **grammar, AST, verifier, and compiler annotations landed** in OpenSpec change `add-classical-context-updates`. Shot-to-shot runtime execution of the mutation is parked for a follow-up change.

Nothing in this architecture requires rewriting the q-orca execution model. What it requires is a single new action kind: a **classical context update** that reads a classical bit from the machine's bit-register and writes a new float into the angle register. Concretely: `if bits[0] == 1: θ[0] -= η · δ; else: θ[0] += η · δ` as an effect, where `δ` and `η` are further context fields. This is a strictly classical operation on the context record and does not touch the quantum state; it only runs between simulator shots.

---

**Proposed syntax (research sketch, subject to design review):**

```markdown
# machine QuantumPredictiveCoder

## context
| Field       | Type        | Default                  |
|-------------|-------------|--------------------------|
| qubits      | list<qubit> | [q_model, q_data, q_anc] |
| bits        | list<bit>   | [b_err]                  |
| theta       | list<float> | [0.0, 0.0, 0.0]          |
| eta         | float       | 0.1                      |
| iteration   | int         | 0                        |
| max_iter    | int         | 50                       |

## events
- prepare_prior
- encode_data
- compute_error
- read_error
- update_model
- done

## state |init> [initial]
## state |prior_ready>
## state |joined>
## state |error_extracted>
## state |measured>
## state |model_updated>
## state |converged> [final]

## transitions
| Source             | Event          | Guard                  | Target             | Action                    |
|--------------------|----------------|------------------------|--------------------|---------------------------|
| |init>             | prepare_prior  |                        | |prior_ready>      | apply_ansatz              |
| |prior_ready>      | encode_data    |                        | |joined>           | encode_training_datum     |
| |joined>           | compute_error  |                        | |error_extracted>  | parity_check_to_ancilla   |
| |error_extracted>  | read_error     |                        | |measured>         | measure_ancilla           |
| |measured>         | update_model   | ctx.iteration < max_iter | |model_updated>  | gradient_step             |
| |model_updated>    | prepare_prior  |                        | |prior_ready>      | reset_data_and_ancilla    |
| |measured>         | done           | ctx.iteration >= max_iter | |converged>     |                           |

## actions
| Name                    | Signature              | Effect                                                                            |
|-------------------------|------------------------|-----------------------------------------------------------------------------------|
| apply_ansatz            | (qs, theta) -> qs      | Ry(qs[0], theta[0]); Rz(qs[0], theta[1]); Rx(qs[0], theta[2])                     |
| encode_training_datum   | (qs) -> qs             | H(qs[1])                                                                          |
| parity_check_to_ancilla | (qs) -> qs             | CNOT(qs[0], qs[2]); CNOT(qs[1], qs[2])                                            |
| measure_ancilla         | (qs, bits) -> (qs, bits) | measure(qs[2]) -> bits[0]                                                       |
| gradient_step           | (ctx) -> ctx           | if bits[0] == 1: theta[0] -= eta; else: theta[0] += eta; iteration += 1           |
| reset_data_and_ancilla  | (qs) -> qs             | reset(qs[1]); reset(qs[2])                                                        |

## verification rules
- unitarity: all gates preserve norm
- entanglement: |joined> has Schmidt rank > 1 across (model, data∪ancilla) cut before measurement
- mid_circuit_coherence: measured ancilla is reset before being used as a target again
- feedforward_completeness: `theta[i]` and `bits[0]` referenced in gradient_step are assigned before use
- termination: guard `iteration < max_iter` bounds loop depth
```

The new effect forms are: `theta[i] -= eta` / `theta[i] += eta` (classical context arithmetic), and `iteration += 1` (classical counter). These are the one genuinely new primitive — a *classical update effect* on `list<float>` and `int` context fields.

---

**What this is *not* (scope guardrails):**

- **It is not Friston active inference on a quantum substrate.** A curated literature review (see §Literature Grounding below) surfaced no arXiv work bridging the free-energy principle / active inference to native quantum circuits. There *is* prior work on "quantum predictive coding" — notably Fanizza et al. (arXiv:2202.01230) which uses quantum autoencoders for state compression, and the quantum Kalman/Wiener filtering corpus (arXiv:1809.01191, arXiv:2601.04812) which is structurally predictive-coding-shaped — but no paper currently claims a full Friston-style variational free-energy implementation in a quantum circuit. Calling this work "predictive coding" positions it alongside the autoencoder and Kalman-filter families, not as a Friston claim.
- **It is not a scalable advantage over classical.** For anything short of problem-specific structure (Hamiltonian learning, state reconstruction), a classical generative model is cheaper than a VQA. The scientific question this machine *can* meaningfully ask is: *given a target state that a classical model struggles with (e.g. a highly-entangled ground state), does a variational quantum predictor converge faster or to a lower error floor than a classical one?* Fanizza et al. (2202.01230) report compression ratios on sequential quantum data that no classical compressor can replicate — that is the kind of concrete comparison target this work should aim at.
- **It does not resolve barren plateaus.** The three-rotation ansatz above is a toy — on any non-trivial problem it will inherit all the known trainability problems of hardware-efficient ansätze (see `2405.00781.pdf` in q-orca-kb for the current survey). A real QPC would use a problem-structured ansatz (HVA, qubit-ADAPT-VQE); choice of ansatz is the main open research question.

---

**Mathematical form (quantum Kalman / Wiener grounding):**

The cleanest existing mathematical formalism the proposed architecture maps onto is the **quantum Kalman filter** (arXiv:1809.01191, arXiv:2601.04812). Under continuous weak measurement of an open quantum system with density operator `ρ_m(t)`, the observable expectations `π_t(ẑ) := Tr(ρ_m(t)·ẑ)` evolve under the SDE:

```
dπ_t(ẑ)   = A·π_t(ẑ) dt + L·u(t) dt + G_t · dν_q(t)      [state update]
dy_qm(t) = C·π_t(ẑ) dt + D·u(t) dt + (DD^⊤) · dν_q(t)   [measurement]
V̇_t      = A·V_t + V_t·A^⊤ + L·Q·L^⊤ − G_t·(DD^⊤)^{-1}·G_t^⊤   [Riccati]
```

where `ν_q(t)` is the **innovation process** — a classical standard Wiener process (quoting 2601.04812 verbatim). The innovation is precisely the "prediction error" that classical predictive coding computes as `observation − predicted_observation`: it is the part of the measurement that the model did not anticipate. The Kalman gain `G_t` is the frequency with which that error drives the model update. A discrete-time approximation of this SDE, specialized to the three-register (model/data/ancilla) setup, is exactly what `gradient_step` should implement — the current sketch's `theta[0] ± eta` is a crude binary Kalman update; a scalar-innovation update proportional to `(bits[0] − expected)` would be the principled version.

This correspondence is the reason the three-register structure is minimum-viable: the Kalman SDE cannot be reduced below (state, measurement, innovation).

---

**Open research questions:**

1. **Ansatz choice and trainability.** Hardware-efficient ansätze exhibit barren plateaus at modest qubit counts (`2405.00781.pdf`). Hamiltonian variational ansätze (HVA) have provable gradient lower bounds under parameter constraints (`2403.04844.pdf`) but require problem structure. Which ansatz family best matches the QPC's generative-model role?
2. **Gradient estimator.** Parameter-shift rule requires re-preparing the full state for each θ-component. Quantum natural gradient using QFIM / Fubini-Study metric (`2406.14285.pdf`) converges in fewer iterations but costs more per iteration. Is the per-iteration-cost trade-off favorable given the ancilla-measurement cost of the error-extraction step?
3. **Error-extraction circuit.** The sketch uses a parity check; a SWAP test produces a real-valued fidelity but costs more gates and a second ancilla. Destructive-SWAP / SWAP-free comparison schemes (see dynamic-circuits room: `2504.21250.pdf` for QSDC-style swap-test feedback) may be cheaper per shot.
4. **Mid-circuit reset cost.** Currently expressed as `reset(qs[1]); reset(qs[2])` — real hardware reset fidelities on 2026-era devices are ~0.99 per qubit (not perfect). At what iteration depth does accumulated reset infidelity overwhelm the gradient signal? This is the empirical question that decides whether the machine is ever useful on real hardware vs. only in simulation.
5. **Verifier support for classical context mutation.** `gradient_step` mutates `theta` — the existing verifier's completeness/coherence rules don't track classical-field state flow. The runtime-assertions change (`add-runtime-state-assertions`) is a step in this direction but was scoped to qubit-state categories, not context-field invariants. A separate proposal for a `ClassicalContextRule` verifier pass may be warranted.

---

**Literature grounding (q-orca-kb):**

*Directly-on-topic quantum predictive coding / filtering (indexed 2026-04-19):*
- **`2202.01230.pdf`** (room: `circuits`) — "Quantum Predictive Coding via Quantum Autoencoders." The closest prior art to this proposal: uses a quantum autoencoder to compress sequential quantum data into a latent register, then predicts the next element of the sequence from the latent. The autoencoder's latent subspace plays the role of the "model register" in the QPC architecture above. Read this before anything else.
- **`1809.01191.pdf`** (room: `formal-methods`) — "Quantum Kalman Filter." Foundational paper formalizing the classical → quantum Kalman transition. Establishes the innovation-process formalism used in §Mathematical Form above.
- **`2601.04812.pdf`** (room: `circuits`) — "Quantum Wiener Architecture for Quantum Reservoir Computing" (Jan 2026). Provides the explicit SDE for the quantum Kalman filter reproduced verbatim above, and defines a Wiener architecture (`u → h_1,...,h_d → f → o`) that is the continuous-time analogue of the discrete three-register QPC. The load-bearing reference for the mathematical grounding.
- **`2209.02325.pdf`** (room: `formal-methods`) — "Predictive State Representations for Quantum Systems." Observable-based representations for predicting quantum-system futures; an alternative formalism to the SDE approach that may be more natural for discrete-time q-orca machines.
- **`2107.08359.pdf`** (room: `circuits`) — "Best Subset Selection: Statistical Computing Meets Quantum Computing." Quantum Linear Prediction via quantum PCA + compact SVD, avoiding matrix inversion. Offers an O((n+n_t) log²d) predictor vs. classical O((n+n_t)d). The linear-prediction building block that the three-rotation ansatz is a crude stand-in for.
- **`2512.04909.pdf`** (room: `circuits`) — "PVLS: Learning-Based Parameter Prediction for VQLS" (late 2025). Uses a Graph Neural Network to meta-learn good initial parameters for Variational Quantum Linear Solvers. Relevant as an alternative to gradient-based `gradient_step`: rather than iteratively refining `theta`, a meta-learner could propose a warm-start `theta` from features of the target state.
- **`2401.11351.pdf`** (room: `circuits`) — "Comprehensive Review of Quantum Machine Learning: from NISQ to Fault Tolerance" (2024). Broad QML survey covering shadow tomography, Born machines, and the input/output problem. General orientation reference.
- **`2504.09909.pdf`** (room: `circuits`) — "Quantum Natural Language Processing: Comprehensive Review" (April 2025). Maps grammatical structures onto parameterized quantum circuits; relevant as a parallel case where *sequence structure* drives the ansatz design, analogous to how *dynamical structure* should drive the QPC ansatz.

*Supporting references on trainability / ansatz choice / error extraction:*
- **`2405.00781.pdf`** (room: `circuits`) — Cerezo / Larocca et al. review on barren plateaus and trainability. Covers explicit vs. implicit generative models and adaptive ansätze (qubit-ADAPT-VQE). Load-bearing for the "why this is hard" section.
- **`2403.04844.pdf`** (room: `circuits`) — Gradient lower bounds for the Hamiltonian variational ansatz.
- **`2406.14285.pdf`** (room: `circuits`) — Parameter-update schemes for PQCs including QFIM-based quantum natural gradient.
- **`2309.09342.pdf`** (room: `circuits`) — Lie-algebraic analysis of parametrized circuit expressibility; relevant to choosing an ansatz whose Dynamical Lie Algebra covers the target state space.
- **`2504.21250.pdf`** (room: `dynamic-circuits`) — Quantum secure direct communication via state reconstruction with swap-test fidelity feedback. Closest architectural analogue for the classical-feedback loop in the palace.
- **`2406.07611.pdf`** (room: `dynamic-circuits`) — GHZ preparation with mid-circuit measurement error characterization. Relevant for the reset / ancilla-measurement error model.
- **`2211.01925.pdf`** (room: `dynamic-circuits`) — Qubit reuse via mid-circuit measurement and classical-controlled NOT. Validates the `reset_data_and_ancilla` step.

**Remaining gap (after the 2026-04-19 index round):** quantum predictive coding is now well-covered (autoencoder formulation at 2202.01230; Kalman/Wiener at 1809.01191, 2601.04812; PSR at 2209.02325). What remains *un*-covered in the palace is the **Friston free-energy / active-inference** corpus itself — neither the classical foundations nor any quantum extensions were returned by the semantic search. This is either a genuinely open research direction or a palace-indexing gap. Candidates to index if a future iteration wants to make a Friston claim:

- Friston, "The free-energy principle: a unified brain theory?" (2010, Nature Reviews Neuroscience) — classical foundational reference (not on arXiv; would need local-PDF indexing).
- Parr & Friston, "Generalised free energy and active inference" (2019, Biological Cybernetics).
- Any arXiv preprints from the "quantum cognition" / "quantum active inference" intersection.

---

**Next concrete steps (in order):**

1. Read arXiv:2202.01230 in full to confirm the autoencoder-based QPC architecture and identify what it does *not* cover (the paper focuses on compression; this proposal adds the online-learning feedback loop).
2. Read arXiv:2601.04812 §II–III to map the continuous-time quantum Kalman SDE onto a discrete-time q-orca state machine. The mapping `innovation process → classical feedback bit` is the key bridge.
3. Write a one-qubit-model / one-qubit-data / one-ancilla worked example as `examples/predictive-coder-minimal.q.orca.md`, using only currently-shipped q-orca features — skip the `gradient_step` classical-update action until the new primitive is scoped. The example should at minimum generate-and-measure without the learning loop, proving the unitary skeleton verifies.
4. ✅ **Landed** — `add-classical-context-updates` (parser/verifier/compile-time annotations) shipped in v0.5.0, and `run-context-updates` wired the iterative Python runtime (`q_orca.runtime.iterative`) that actually executes those effects shot-to-shot. The full learning loop is now representable in q-orca syntax and executable end-to-end on the Qiskit backend.
5. Optional: index the Friston free-energy corpus (2010 Nature Reviews Neuroscience paper, 2019 Parr & Friston active-inference paper) into q-orca-kb if a future iteration wants to make a Friston-style claim. Not needed to make the Kalman/autoencoder version work.
6. **Unblocked** — extend `examples/predictive-coder-learning.q.orca.md` (already shipped as the minimal loop under `run-context-updates`) into a convergence benchmark: sweep the QPC learning loop and plot error-vs-iteration against a classical baseline (e.g. a small NN trained to match the same target state distribution), and against the 2202.01230 autoencoder compression baseline on sequential quantum data.

---

**Complexity:** High (research, not implementation). The only near-term implementation work is **classical context update effects** — a contained language feature.

**Priority:** Research / exploratory. Not on the feature roadmap; parked here for future kickoff.

**Dependencies:** Composes with every recently-landed feature — mid-circuit measurement, context-angle references, runtime state assertions, role annotations. The QPC is effectively the capstone use case for all of them.
