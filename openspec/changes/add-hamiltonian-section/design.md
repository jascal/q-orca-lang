## Context

The shipped VQE example encodes its observable in three parser-opaque places (a
prose `|measured>` description, an empty `set_energy` action, an `energy_ok`
guard reading `ctx.energy`). `add-composed-runtime` now executes machines with
shot-batched leaf children and threads `prob_/hist_/var_` aggregates back into
the parent; `add-runtime-state-assertions` established the pattern of a
declarative section the verifier and compiler agree on. This change gives the
*measured observable* the same declarative footing. Research draft:
`docs/research/spec-hamiltonian-section.md`.

## Goals / Non-Goals

**Goals**
- A declarative `## hamiltonian <name>` section as the single source of truth
  for an observable, verifier-checked for Hermiticity and index validity.
- `measure(H) -> ctx.field` that estimates `⟨H⟩` via qubit-wise-commuting
  measurement groups and aggregates to a scalar.
- Multiple named Hamiltonians per machine (QAOA `H_C` + `H_M`).

**Non-Goals (v1)**
- Variance-weighted shot allocation across groups (uniform per group for v1;
  `## measurement_strategy` is a follow-on). Open Question 3.
- General (non-qubit-wise) commuting-group optimisation. Qubit-wise
  commutativity only.
- Fermionic / second-quantised operators (Jordan-Wigner is out of scope).

## Decisions

### D1 — Section placement and grammar
`## hamiltonian <name>` lives between `## context` and `## actions`. Its body is
a table `| Coefficient | Pauli string | Qubits |`. `<name>` defaults to `H`.
AST: `HamiltonianTerm(coefficient: float|str, pauli: str, qubits: list[int])`,
`HamiltonianDecl(name: str, terms: list[HamiltonianTerm])`, and
`QMachineDef.hamiltonians: list[HamiltonianDecl]`.

### D2 — Coefficient grammar (real-valued)
Coefficients are real literals or symbolic angle expressions resolved by the
existing `evaluate_angle` helper (re-used unchanged). A coefficient that
evaluates complex raises `HAMILTONIAN_NON_HERMITIAN` at the offending row. (A
Hermitian operator with a weighted-Pauli decomposition has real coefficients,
since each Pauli string is Hermitian.)

### D3 — Pauli-string convention
Pauli strings use the alphabet `{I, X, Y, Z}`. `Pauli[i]` pairs with
`Qubits[i]` (explicit, position-paired — no Qiskit big-endian ambiguity). The
string length MUST equal the `Qubits` list length, else
`HAMILTONIAN_PAULI_OUT_OF_RANGE`. The docs state this convention explicitly.

### D4 — `measure(H_name) -> ctx.field` effect
A new effect form parsed by `effect_parser`. The runtime decomposes `H_name`
into qubit-wise-commuting groups, emits one shot-batched measurement circuit per
group, estimates each Pauli term's expectation from that group's counts, and
writes `Σ coeff · ⟨P⟩` to `ctx.field` as a `float`.

### D5 — Qubit-wise commutativity grouping
`q_orca/compiler/measurement_grouping.py` groups terms whose non-identity Pauli
factors never disagree on any shared qubit (qubit-wise commuting), so each group
shares a single measurement basis (Peruzzo et al. 2014). This is the v1
optimisation; general commuting groups are out of scope.

### D6 — Expectation in the shot-batched leaf path
`measure(H)` is implemented in `run_composed`'s leaf path (depends on
`add-composed-runtime`). With `extend-nested-shot-aggregation` it also works
inside a composed child; the spec ships leaf-only and gains nesting for free.

## Risks / Trade-offs
- **Grouping correctness** is the only piece without a codebase analogue; pinned
  by an end-to-end `⟨Φ+|XX+YY+ZZ|Φ+⟩ = 3` regression.
- **Noise interaction** — under a `## noise_model`, `--report-hamiltonians` can
  print noise-free and noisy side by side; the default single number is the
  noisy simulated value when a noise model is present. Open Question 4.

## Migration Plan
Additive. Absent section = unchanged. `measure(H)` is a new effect form; the
VQE/QAOA examples are refactored to use it. Rollback = revert.

## Open Questions
1. Per-group shot allocation: uniform (v1) vs variance-weighted (follow-on).
2. Multi-qubit identity shorthand (shorter string + explicit qubits) vs
   full identity-padded strings. v1 requires `len(string) == len(qubits)`.
3. Noise-free vs noisy default expectation under `## noise_model`.
