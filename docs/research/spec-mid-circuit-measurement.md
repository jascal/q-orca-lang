# Feature: Mid-Circuit Measurement & Classical Feedforward

> Generated: 2026-04-12 — weekly feature spec session

---

**Summary:** Add the ability to measure one or more qubits mid-circuit and conditionally apply subsequent gates based on the classical measurement result, without terminating the circuit. This introduces two new language constructs: the `list<bit>` context type for storing classical measurement outcomes, and a `measure(q) -> bits[N]` effect syntax with an accompanying `if bits[N] == val: Gate(q)` conditional effect form. The feature brings q-orca in line with IBM's dynamic circuits capability (shipped in Qiskit 2025) and Quantinuum's Guppy language, and is a prerequisite for expressing quantum error correction, active teleportation, and adaptive variational algorithms in a single linear circuit rather than as multiple branching state machines.

---

**Motivation:** The algorithms and use cases this unlocks include:

- **Active quantum teleportation** — the current `quantum-teleportation.q.orca.md` uses four state branches to represent the four Bell outcomes. With mid-circuit measurement, Alice's two-qubit Bell measurement can be expressed as a single `measure → bit` step, and Bob's correction (`if bit[0]==1: Z; if bit[1]==1: X`) can be expressed as conditional effects in the same action, collapsing four branches into one linear machine.
- **Quantum error correction syndrome extraction** — a 3-qubit bit-flip code measures two syndrome qubits mid-circuit (`measure(syndrome[0]) -> bits[0]`) and uses the outcome to select the correction gate (`if bits[0]==1 && bits[1]==0: X(data[0])`). Without this feature, syndrome-based QEC is inexpressible in q-orca.
- **Adaptive VQE / ADAPT-VQE** — each iteration measures a proxy observable mid-circuit and uses the result to decide which operator to append to the ansatz next. This is the core of the ADAPT-VQE algorithm (Grimsley et al., Nature Communications 2019).
- **Reset-based qubit reuse** — measure an ancilla qubit, then conditionally reset it to |0⟩ for reuse within the same circuit, reducing qubit count for deep circuits.

---

**Proposed Syntax:**

```markdown
# machine ActiveTeleportation

## context
| Field   | Type        | Default          |
|---------|-------------|------------------|
| qubits  | list<qubit> | [q0, q1, q2]     |
| bits    | list<bit>   | [b0, b1]         |

## events
- prepare_bell
- alice_measure
- bob_correct
- done

## state |init> [initial]
> Three qubits in |000⟩

## state |bell_ready>
> Bell pair established between q1 and q2; q0 holds state to teleport

## state |alice_measured>
> Alice has measured q0 and q1 into bits[0] and bits[1]

## state |teleported> [final]
> q2 holds the teleported state; bits contain Alice's classical outcomes

## transitions
| Source           | Event          | Guard | Target           | Action           |
|------------------|----------------|-------|------------------|------------------|
| |init>           | prepare_bell   |       | |bell_ready>      | make_bell_pair   |
| |bell_ready>     | alice_measure  |       | |alice_measured>  | bell_measure      |
| |alice_measured> | bob_correct    |       | |teleported>      | apply_correction |
| |teleported>     | done           |       | |teleported>      |                  |

## actions
| Name             | Signature             | Effect                                                                    |
|------------------|-----------------------|---------------------------------------------------------------------------|
| make_bell_pair   | (qs) -> qs            | H(qs[1]); CNOT(qs[1], qs[2])                                              |
| bell_measure     | (qs, bits) -> (qs, bits) | CNOT(qs[0], qs[1]); H(qs[0]); measure(qs[0]) -> bits[0]; measure(qs[1]) -> bits[1] |
| apply_correction | (qs, bits) -> qs      | if bits[1] == 1: X(qs[2]); if bits[0] == 1: Z(qs[2])                      |

## verification rules
- unitarity: all gates preserve norm
- mid_circuit_coherence: qubits measured into bits[N] are not used unitarily after measurement
- feedforward_completeness: all bit values referenced in conditional effects are assigned before use
- no-cloning: measurement consumes qubit coherence; state is not copied
```

Key new syntax elements:
- `list<bit>` — new context field type representing a classical bit register
- `measure(qs[N]) -> bits[M]` — mid-circuit measurement effect; collapses qubit N into classical bit M
- `if bits[M] == val: Gate(qs[K])` — conditional gate effect; applies Gate only when bits[M] equals val (0 or 1)
- Multiple conditional effects may appear in one action, separated by `;`
- Action signatures that read or write bits use `(qs, bits) -> (qs, bits)` or `(qs, bits) -> qs`

---

**Implementation Sketch:**

**Parser changes (`q_orca/parser/markdown_parser.py`):**
- Add `list<bit>` as a recognized context field type, producing a new `QTypeList(element_type="bit")` AST node
- Extend the effect string parser to recognize the `measure(qs[N]) -> bits[M]` form, producing a new `QEffectMeasure(qubit_idx=N, bit_idx=M)` AST node
- Extend the effect string parser to recognize the `if bits[M] == val: Gate(args)` form, producing a new `QEffectConditional(bit_idx=M, value=val, inner_effect=QEffectGate(...))` AST node
- Both new forms must interleave with existing semicolon-separated effect chains

**Compiler changes — Qiskit (`q_orca/compiler/qiskit.py`):**
- When a machine context contains a `list<bit>` field, emit a `ClassicalRegister` of the appropriate width alongside the existing `QuantumRegister`
- `QEffectMeasure(N, M)` → `qc.measure(qreg[N], creg[M])`
- `QEffectConditional(M, val, inner)` → emit inner gate inside a `with qc.if_test((creg[M], val)):` dynamic circuit block (Qiskit's OpenQASM 3 / dynamic circuit interface)
- Add `GateKind` note: `'measure'` is not a unitary gate; omit from the shots-mode bulk measure loop for qubits that have already been measured mid-circuit

**Compiler changes — QASM (`q_orca/compiler/qasm.py`):**
- Emit `creg bits[W];` declaration when `list<bit>` context field is present (W = list length)
- `QEffectMeasure(N, M)` → `measure q[N] -> bits[M];`
- `QEffectConditional(M, val, inner)` → `if(bits[M]==val) Gate q[K];` (OpenQASM 2 conditional form; upgrade to `if (bits[M] == val) { ... }` block for QASM 3.0 output when that feature lands)

**Verifier changes (`q_orca/verifier/`):**
- New rule class `MidCircuitCoherenceRule` in `verifier/quantum.py`: walks each action's effect list; tracks which qubit indices have been measured; emits an error if any subsequent `QEffectGate` references a measured qubit index (unless preceded by a reset)
- New rule class `FeedforwardCompletenessRule` in `verifier/completeness.py`: ensures every `bits[M]` referenced in a `QEffectConditional` was written by a `QEffectMeasure` earlier in the same action chain, or is initialized in context
- Extend existing `CompletenessRule` to treat a transition with `QEffectMeasure` as a collapsing event (analogous to current `"measure"` / `"collapse"` event name heuristic, but now structural)

**New tests / examples needed:**
- `examples/active-teleportation.q.orca.md` — the syntax example above; replaces the 4-branch teleportation with a single dynamic circuit; compile + verify + simulate
- `examples/bit-flip-syndrome.q.orca.md` — 3-qubit bit-flip code with syndrome extraction: prepare logical qubit, inject a bit-flip, measure two syndrome ancillas, correct; demonstrates full QEC round-trip
- Unit tests: parser round-trips for `measure(...) -> bits[N]` and `if bits[N] == val: Gate(...)` effects
- Compiler tests: Qiskit dynamic circuit output uses `with qc.if_test(...):`; QASM output emits `if(bits[N]==val)` conditional

---

**Complexity:** Medium

**Priority:** High

**Dependencies:** None (independent of all queued backlog items). Pairs naturally with **Qubit Role Types** (queued) when those land — syndrome qubits in QEC will benefit from `[syndrome]` role annotations alongside mid-circuit measurement. Also composes with **Loop Annotations** (queued) for iterative QEC rounds.

---

**Literature:**

- Cross et al., "Open Quantum Assembly Language" (arXiv:1707.03429) — indexed in q-orca-kb (wing: `q-orca-implementations`, room: `circuits`): §3 defines the classical control flow and mid-circuit measurement semantics that became OpenQASM 2; the design of `measure q -> c` and `if(c==val)` forms is directly from this paper.
- Grimsley et al., "An adaptive variational algorithm for exact molecular simulations on a quantum computer" — referenced in q-orca-kb (room: `circuits`, source: `2407.00736.pdf`): establishes ADAPT-VQE, which requires mid-circuit measurement of gradient operators to select the next ansatz term.
- Quantinuum Guppy language (2025): quantum kernels with measurement-dependent control flow as first-class language feature — primary industry validation for this approach. See: https://www.quantinuum.com/blog/guppy-programming-the-next-generation-of-quantum-computers
- IBM Dynamic Circuits (2025): 24% accuracy improvement with dynamic circuits at 100+ qubit scale. See: https://quantum.cloud.ibm.com/announcements/en/product-updates/2025-03-03-new-version-dynamic-circuits
