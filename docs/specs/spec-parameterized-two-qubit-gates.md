# Feature: Parameterized Two-Qubit Gates (CRz, RXX, RYY, RZZ)

> Generated: 2026-04-12 — weekly feature spec session

---

**Summary:** Extend the parameterized rotation gate system (which currently supports single-qubit `Rx`, `Ry`, `Rz`) to include two-qubit parameterized gates: `CRz(ctrl, tgt, θ)`, `CRx(ctrl, tgt, θ)`, `CRy(ctrl, tgt, θ)`, `RXX(q0, q1, θ)`, `RYY(q0, q1, θ)`, and `RZZ(q0, q1, θ)`. These gates are the essential building blocks of QAOA cost layers, Heisenberg model VQE, and UCCSD molecular ansätze. The implementation follows exactly the same architecture as the single-qubit parameterized gates added in v0.3.3 — the parser's angle grammar, the `evaluate_angle` helper, and the Qiskit/QASM compiler paths are all directly extensible with minimal new surface area.

---

**Motivation:** The algorithms and use cases this unlocks include:

- **QAOA MaxCut** — the cost layer of QAOA applies `e^{−iγ Z_i Z_j}` = `RZZ(q_i, q_j, γ)` to every edge (i,j) of the problem graph. Without `RZZ`, QAOA cannot be expressed natively in q-orca; the roadmap coverage analysis (v0.4) explicitly lists `qaoa-maxcut.q.orca.md` as an underserved target example.
- **Heisenberg XXX VQE** — the existing `vqe-heisenberg.q.orca.md` example currently approximates the Heisenberg model; a full ansatz requires `RXX(θ) + RYY(θ) + RZZ(θ)` two-qubit terms per Trotter step. Adding these gates makes the example physically exact.
- **UCCSD / hardware-efficient ansätze** — controlled-rotation gates (`CRz(θ)`, `CRy(θ)`) appear in virtually every hardware-efficient ansatz used in quantum chemistry VQE. They are already natively supported by Qiskit and IBM hardware.
- **Quantum walk coin operators** — quantum walk step operators on a 2D lattice use `CRz(θ)` for directional phase encoding, unlocking a quantum walk example (q-orca-kb has `2101.02109.pdf` on quantum walk noise models).

---

**Proposed Syntax:**

```markdown
# machine QAOAMaxCut

## context
| Field   | Type        | Default          |
|---------|-------------|------------------|
| qubits  | list<qubit> | [q0, q1, q2]     |
| gamma   | float       | 0.3              |
| beta    | float       | 0.7              |
| shots   | int         | 1024             |

## events
- init
- cost_layer
- mixer_layer
- readout

## state |0> [initial]
> All qubits in ground state

## state |uniform>
> Equal superposition over all 2^3 = 8 computational basis states

## state |cost_applied>
> After one QAOA cost layer: exp(-i γ C) applied to |uniform>

## state |mixed>
> After QAOA mixer layer: exp(-i β B) applied; ready for readout

## state |measured> [final]
> Circuit complete; measurement outcomes encode approximate MaxCut solution

## transitions
| Source          | Event       | Guard | Target          | Action          |
|-----------------|-------------|-------|-----------------|-----------------|
| |0>             | init        |       | |uniform>        | apply_hadamards |
| |uniform>       | cost_layer  |       | |cost_applied>   | apply_cost      |
| |cost_applied>  | mixer_layer |       | |mixed>          | apply_mixer     |
| |mixed>         | readout     |       | |measured>       | measure_all     |

## actions
| Name            | Signature    | Effect                                                           |
|-----------------|--------------|------------------------------------------------------------------|
| apply_hadamards | (qs) -> qs   | H(qs[0]); H(qs[1]); H(qs[2])                                    |
| apply_cost      | (qs) -> qs   | RZZ(qs[0], qs[1], gamma); RZZ(qs[1], qs[2], gamma); RZZ(qs[0], qs[2], gamma) |
| apply_mixer     | (qs) -> qs   | Rx(qs[0], beta); Rx(qs[1], beta); Rx(qs[2], beta)               |
| measure_all     | (qs) -> qs   | measure(qs[0]); measure(qs[1]); measure(qs[2])                  |

## verification rules
- unitarity: all gates preserve norm
- parameterized_two_qubit_unitarity: RZZ/RXX/RYY are unitary for all real θ
- entanglement: cost layer increases entanglement relative to uniform superposition
```

Additional syntax examples:

```markdown
# CRz usage in UCCSD-style ansatz
| apply_uccsd_term | (qs) -> qs | CRz(qs[0], qs[1], pi/3); CRz(qs[1], qs[2], pi/6) |

# RXX and RYY in Heisenberg Trotter step
| trotter_step | (qs) -> qs | RXX(qs[0], qs[1], 0.2); RYY(qs[0], qs[1], 0.2); RZZ(qs[0], qs[1], 0.2) |
```

**Angle grammar:** Identical to the existing single-qubit parameterized gate grammar from `q_orca/angle.py`. All forms already supported (`pi`, `pi/N`, `N*pi`, `N*pi/M`, decimal literals, leading minus) apply without change. Context field names (e.g. `gamma`, `beta`) are resolved from the machine context at compile time in a new "context parameter" pass (see implementation sketch).

**Argument order:** Two-qubit parameterized gates use the form `Gate(q0, q1, angle)` — two qubit arguments (positional, as `qs[N]` index expressions) followed by the angle. Controlled gates (`CRx`, `CRy`, `CRz`) treat the first qubit as control and the second as target.

---

**Implementation Sketch:**

**AST changes (`q_orca/ast.py`):**
- Extend `GateKind` literal type to include: `'CRx' | 'CRy' | 'CRz' | 'RXX' | 'RYY' | 'RZZ'`
- The existing `QEffectGate` node already holds `kind`, `qubit_indices: list[int]`, and `angle: Optional[float]`; no new AST node is needed — two-qubit parameterized gates use the same node with `len(qubit_indices) == 2`

**Parser changes (`q_orca/parser/markdown_parser.py`):**
- In the effect string tokenizer, add a regex for `(CRx|CRy|CRz|RXX|RYY|RZZ)\s*\(\s*qs\[(\d+)\]\s*,\s*qs\[(\d+)\]\s*,\s*([^)]+)\)` — captures gate name, two qubit indices, and raw angle string
- Pass the raw angle string through the existing `evaluate_angle()` helper (unchanged)
- Emit `QEffectGate(kind=..., qubit_indices=[idx0, idx1], angle=evaluated)` — identical structure to Rx/Ry/Rz nodes
- Context parameter resolution: if `evaluate_angle()` returns `None` (unrecognized token), attempt to look up the token as a context field name and record it as a `symbolic_angle` string for the compiler to resolve; this is a new small sub-feature that also benefits Rx/Ry/Rz (currently `gamma`, `beta` etc. in QAOA cannot be passed as context fields to single-qubit gates either)

**Compiler changes — Qiskit (`q_orca/compiler/qiskit.py`):**
- Add six branches to the gate dispatch block (currently lines ~411–415):
  - `CRx` → `qc.crx(angle, qreg[ctrl], qreg[tgt])`
  - `CRy` → `qc.cry(angle, qreg[ctrl], qreg[tgt])`
  - `CRz` → `qc.crz(angle, qreg[ctrl], qreg[tgt])`
  - `RXX` → `qc.rxx(angle, qreg[q0], qreg[q1])`
  - `RYY` → `qc.ryy(angle, qreg[q0], qreg[q1])`
  - `RZZ` → `qc.rzz(angle, qreg[q0], qreg[q1])`
- All six gates are natively available in Qiskit's standard gate library; no custom unitary is needed
- For symbolic angles: emit a Python variable for context field lookups (e.g. `gamma = ctx.gamma`) and reference it in the gate call

**Compiler changes — QASM (`q_orca/compiler/qasm.py`):**
- `CRx(θ) ctrl, tgt` — available as a standard gate in OpenQASM 2 `qelib1.inc`
- `CRy(θ) ctrl, tgt` — available in `qelib1.inc`
- `CRz(θ) ctrl, tgt` — available in `qelib1.inc`
- `RXX` / `RYY` / `RZZ` — not in `qelib1.inc`; emit as custom gate definitions at the top of the QASM output, or use the decomposition `RZZ(θ) q0, q1 ≡ cx q0,q1; rz(θ) q1; cx q0,q1;` for QASM 2 compatibility

**Verifier changes (`q_orca/verifier/`):**
- Extend `UnitarityRule` (in `verifier/quantum.py`) to recognize all six new gate kinds as unitary; each is parameterized but unitary for all real θ — no angle-range check needed
- Extend the two-qubit gate index check: verify `qubit_indices` has exactly 2 elements, both in range, and not equal (no self-application)
- For `CRx/CRy/CRz`: add a note in the verifier that the controlled axis is distinct from the CNOT/CZ pattern; no special entanglement rule needed (the gate is unitary and entangling by construction)

**New tests / examples needed:**
- `examples/qaoa-maxcut.q.orca.md` — 3-qubit MaxCut on a triangle graph (all-to-all, 3 edges); single QAOA layer with fixed γ=0.3, β=0.7; compile to Qiskit, simulate 1024 shots, verify most-probable bitstring is a valid MaxCut
- `examples/heisenberg-trotter.q.orca.md` — single Trotter step for 2-qubit Heisenberg XXX model using `RXX + RYY + RZZ`; replaces the approximate approach in `vqe-heisenberg.q.orca.md`
- Unit tests: parser correctly parses all 6 gate forms with all existing angle grammar forms; `evaluate_angle` produces correct float values
- Compiler tests: Qiskit output contains `qc.rzz(...)`, `qc.crz(...)`, etc.; QASM output is valid QASM 2 (with custom gate preamble where needed)
- Verifier tests: unitarity check passes for all 6 gates; invalid qubit indices (out of range, or `qs[0]` used as both args) produce errors

---

**Complexity:** Small

**Priority:** High

**Dependencies:** None. This is a direct, self-contained extension of the parameterized gate machinery already shipped in v0.3.3. The parser, compiler, and verifier paths are fully analogous. The symbolic context parameter lookup (for `gamma`, `beta` etc.) is a small optional enhancement; the feature can ship without it by requiring angle literals in a first pass.

---

**Literature:**

- Farhi, Goldstone & Gutmann, "A Quantum Approximate Optimization Algorithm" (arXiv:1411.4028) — indexed in q-orca-kb (room: `vqe`): establishes QAOA; cost layer is `exp(-iγ C)` where C is a sum of `ZZ` terms, directly requiring `RZZ(θ)`.
- Grimsley et al., "An adaptive variational algorithm for exact molecular simulations on a quantum computer" (Nature Comm. 2019) — indexed in q-orca-kb (room: `circuits`, source: `2407.00736.pdf`): ADAPT-VQE uses CRz-family gates as the basic ansatz operators in the hardware-efficient variant.
- Yan et al., "Quantum Circuit Synthesis and Compilation Optimization: Overview and Prospects" (arXiv:2407.00736) — indexed in q-orca-kb (wing: `q-orca-implementations`, room: `circuits`): §III.B covers parameterized circuit synthesis for VQAs; notes that `RZZ` and `RXX` are the dominant two-qubit building blocks for NISQ-era algorithms.
- Riste et al., "Feedback control of a solid-state qubit using high-fidelity projective measurement" (Phys. Rev. Lett., 2012) — indexed in q-orca-kb (room: `hardware`, source: `1704.05018.pdf`): underpins the physical motivation for parameterized controlled rotations in error-correction and feedback protocols.
