# Spec: Declarative `## hamiltonian` Section

**Status:** Draft
**Date:** 2026-05-29
**Priority:** High

> Generated: 2026-05-29 — weekly feature spec session

---

## Summary

Add a declarative `## hamiltonian` section to `.q.orca.md` machines that
expresses a Hermitian observable as a weighted sum of Pauli strings. The
compiler reads this section to emit basis-rotation gates and the per-Pauli
measurement circuits required to estimate `⟨H⟩`; the runtime aggregates the
shot-batched terms into a single expectation value; the verifier confirms the
operator is Hermitian and that the qubit indices match the declared
`## context`. This eliminates today's pattern of hand-coding measurement-basis
changes inside action effects (as `examples/vqe-heisenberg.q.orca.md` does for
`⟨XX + YY + ZZ⟩/4`) and gives VQE / QAOA / time-evolution machines a
first-class declarative form for *what* they are measuring, separate from
*how* the ansatz is prepared.

## Motivation

The current VQE example carries its Hamiltonian information in three places
that the parser cannot cross-check:

1. A natural-language sentence in the `|measured>` state description
   ("Energy ⟨XX + YY + ZZ⟩/4 measured").
2. An informally-named action `set_energy` whose effect column is empty.
3. A guard `energy_ok` that reads `ctx.energy` without any binding back to a
   measurement.

There is no machine-readable definition of the observable anywhere in the
file. Practitioners writing VQE in q-orca today have to either (a) inline
basis-rotation `Sdg, H, ...` sequences inside an `apply_measurement` action,
which conflates ansatz preparation with observable measurement, or (b) drop
out of q-orca entirely and write a Python post-processing script. Both break
the principle that a `.q.orca.md` file is a complete, declarative,
verifier-checkable description of a quantum experiment.

QAOA has the same problem squared: the cost Hamiltonian `H_C` is what defines
the optimization problem, the mixer `H_M` defines the search dynamics, and
both need to be evaluated as expectations. Without a declarative form, a QAOA
machine cannot communicate to the compiler which observable terms it wants
shot-batched together (commuting Paulis can share a measurement basis;
non-commuting ones cannot — a key optimisation that Peruzzo et al. 2014
[1304.3061] introduce as the basis for quantum expectation estimation).

`add-composed-runtime` is in the same week landing the ability to actually
run these machines. The natural next move is to give the things they
measure a declarative form.

## Proposed Syntax / API

A `## hamiltonian` section lives between `## context` and `## actions`,
optionally between `## events` and `## state` blocks. It contains an
ID-typed table of Pauli terms.

```markdown
## hamiltonian H
| Coefficient    | Pauli string  | Qubits        |
|----------------|---------------|---------------|
|  1.0           | XX            | [q0, q1]      |
|  1.0           | YY            | [q0, q1]      |
|  1.0           | ZZ            | [q0, q1]      |
|  0.5           | Z             | [q0]          |
|  0.5           | Z             | [q1]          |
```

A machine may declare more than one named Hamiltonian (e.g. QAOA wants both
the cost layer `H_C` and the mixer `H_M` available). Subsequent sections use
the heading `## hamiltonian H_C`, `## hamiltonian H_M`, etc.

### Coefficient grammar

Coefficients are real numbers or symbolic angles (`pi/4`, `theta`,
`-gamma`). Symbolic coefficients must resolve via the existing
`evaluate_angle` helper (re-used unchanged) and must be real-valued; the
verifier raises `HAMILTONIAN_NON_HERMITIAN` if any coefficient evaluates to
complex.

### Pauli-string grammar

Pauli strings use the alphabet `{I, X, Y, Z}`. The string length must equal
the length of the `Qubits` list. Identities may be omitted by using a
shorter string paired with explicit qubit indices — e.g. `Z` on `[q3]`
implicitly tensors with identity on every other declared qubit.

### Effect grammar — `measure(H)`

A new effect form `measure(H_name)` is introduced. It signals that the
machine completes by estimating `⟨H_name⟩` over the current state. The
runtime decomposes the named Hamiltonian into commuting groups (using
qubit-wise commutativity, the algorithm cited in Peruzzo et al. 2014), emits
one shot-batched measurement circuit per group, and aggregates the result
into a single `float` written to a designated context field.

```markdown
| measure_energy | (qs, ctx) -> ctx | measure(H) -> ctx.energy |
```

### CLI integration

`q-orca run` already exists (shipped under `add-composed-runtime`). A new
flag `--report-hamiltonians` prints, for each declared Hamiltonian, the
estimated expectation, the per-Pauli-group breakdown, and the number of
measurement shots spent per group. This is the same diagnostic surface
`run_composed` exposes for aggregates today.

## Implementation Sketch

Changed / new modules (approximate diff sizes):

| File / module                                   | Change                                                          | LoC     |
|-------------------------------------------------|-----------------------------------------------------------------|---------|
| `q_orca/ast.py`                                  | New `HamiltonianTerm`, `HamiltonianDecl` AST nodes; field on `QMachineDef`. | +60     |
| `q_orca/parser/markdown_parser.py`              | New `_parse_hamiltonian_block`; integrate into the section-dispatch loop.  | +120    |
| `q_orca/verifier/quantum.py`                    | New `_check_hamiltonian_hermitian`; new `_check_pauli_qubit_indices` pass.  | +90     |
| `q_orca/verifier/types.py`                      | Two new error codes: `HAMILTONIAN_NON_HERMITIAN`, `HAMILTONIAN_PAULI_OUT_OF_RANGE`. | +10     |
| `q_orca/compiler/measurement_grouping.py` (new) | Qubit-wise commutativity grouping (Peruzzo et al.).                         | +180    |
| `q_orca/compiler/qiskit.py`                      | New `build_measurement_circuits_for(hamiltonian)`; emits one circuit per group. | +120    |
| `q_orca/compiler/qasm.py`                        | Mirror of the Qiskit path: emit one QASM file per measurement group.        | +90     |
| `q_orca/runtime/composed.py`                    | New `_run_hamiltonian_measurement`; aggregate term expectations into scalar. | +110    |
| `q_orca/effect_parser.py`                       | Parse `measure(H_name) -> ctx.field` form.                                   | +50     |
| `docs/language/hamiltonian.md` (new)            | User-facing docs.                                                            | +150    |
| `examples/vqe-heisenberg.q.orca.md`             | Refactored to use `## hamiltonian H` instead of in-action energy logic.      | edit    |
| `examples/qaoa-maxcut.q.orca.md`                | Same: `## hamiltonian H_C`, `## hamiltonian H_M`.                            | edit    |
| Tests                                            | Parser, verifier, compiler, runtime, end-to-end VQE expectation regression. | +400    |

Estimated total new LoC: ~1,250 across implementation + ~400 in tests.

The measurement-grouping module is the only piece without a clear analogue
in the existing codebase; the rest is incremental work on patterns already
established by the `## noise_model` spec draft and the
`add-runtime-state-assertions` change.

## Test Cases

1. **Single-Pauli Hamiltonian** — `H = Z @ q0`. Verifier accepts; compiler
   emits one measurement circuit; expectation matches analytic value
   `±1` for `|0>` / `|1>` initial states.

2. **Commuting-group batching** — `H = XX + YY + ZZ` on `[q0, q1]`. Verifier
   accepts; compiler emits three measurement circuits (different bases,
   shots batched per group); end-to-end expectation matches the Bell-state
   energy `⟨Φ+ | XX+YY+ZZ | Φ+⟩ = 1 + 1 + 1 = 3` to within statistical
   precision.

3. **Non-Hermitian rejection** — A term with coefficient `1.0 + 0.1j`. Verifier
   raises `HAMILTONIAN_NON_HERMITIAN` with a location pointing at the
   offending row.

4. **Pauli-string / qubit-list length mismatch** — Pauli string `XX` on a
   single-qubit `[q0]`. Verifier raises `HAMILTONIAN_PAULI_OUT_OF_RANGE`.

5. **Multi-Hamiltonian QAOA** — Declared `H_C` and `H_M`; two separate
   `measure(H_C)` and `measure(H_M)` effects in different transitions.
   Runtime tracks both expectations independently and reports them in the
   composed-run output. Regression test against the analytic ground-state
   energy of the 4-vertex ring MaxCut graph.

## Dependencies

- **`add-composed-runtime`** (just landed): `measure(H)` is implemented inside
  `run_composed`'s shot-batched leaf path, so this spec sequences strictly
  after composed-runtime is on `main`.
- **`extend-nested-shot-aggregation`** (in flight): if landed first, the new
  Hamiltonian expectation works inside a *composed* child as well, not just
  a leaf. Not strictly required — the spec can ship with a "leaf-only"
  caveat and have nested support added when `extend-nested-shot-aggregation`
  archives.
- **`spec-test-cases-section`** (draft): regression tests for Hamiltonian
  expectation values are an obvious fit for the planned `## test_cases`
  block. Specs can be authored independently, but the example files will be
  cleaner if `## test_cases` ships first.

## Open Questions

1. **Pauli-string convention** — left-to-right or right-to-left for the
   qubit ordering inside the string? Qiskit uses big-endian
   (`Pauli("XYZ")` puts `Z` on qubit 0). The proposal above implicitly
   pairs `Pauli[i]` with `Qubits[i]`, which is unambiguous, but the docs
   need to state this explicitly to avoid Qiskit-convention drift.

2. **Real-coefficient grammar** — should the coefficient column accept
   the full angle grammar (`pi/4`, `2*pi`, etc.) or only real literals?
   Re-using `evaluate_angle` is the lowest-effort option but forces a
   real-result check.

3. **Per-group shot allocation** — uniform shots per commuting group, or
   variance-weighted? Variance-weighted shot allocation (Wecker et al.
   2015 strategy) gives lower-variance expectations but adds a feedback
   loop into the runtime that doesn't exist today. Suggest uniform for
   v1, with a `## measurement_strategy` extension as a follow-on.

4. **Interaction with `## noise_model`** — should the expectation be the
   noise-free analytical value, the noisy simulated value, or both? Likely
   both: a single number is what users want by default, but
   `--report-hamiltonians` could print both side by side under a noise
   model.

5. **Multi-qubit identity shorthand** — is the "shorter string + explicit
   qubits" convention readable enough, or should the syntax require the
   full identity-padded form (`IIZI` on the full register)? The shorthand
   matches Pennylane / OpenFermion conventions, but contradicts the
   "everything is explicit" Q-Orca house style.

---

**KB grounding:**

- Peruzzo, McClean, Shadbolt et al. (2014) *A variational eigenvalue solver
  on a photonic quantum processor.* `arXiv:1304.3061`. Indexed in q-orca-kb
  (wing `q-orca-physics`, room `vqe`). Source of the qubit-wise commutativity
  grouping algorithm and the "Hamiltonian as weighted sum of Pauli strings"
  abstraction this spec encodes.
- Farhi, Goldstone & Gutmann (2014) *A Quantum Approximate Optimization
  Algorithm.* `arXiv:1411.4028`. Indexed in q-orca-kb (wing
  `q-orca-implementations`, room `circuits`). Motivates the multi-Hamiltonian
  case (`H_C` + `H_M`).
- Larocca, Cerezo et al. (2024) *A Review of Barren Plateaus.*
  `arXiv:2405.00781`. Indexed in q-orca-kb (`circuits`). Cites the
  Hamiltonian-variational-ansatz generalisation; relevant for future
  invariant checks on Hamiltonian structure.
