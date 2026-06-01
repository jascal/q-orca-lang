## ADDED Requirements

### Requirement: Hamiltonian Expectation Aggregation

When an action's effect is `measure(H_name) -> ctx.field`, the runtime SHALL estimate `⟨H_name⟩` over the current state and write the scalar result to the named context field. It SHALL run each qubit-wise-commuting group's measurement circuit (shot-batched in `run_composed`'s leaf path), estimate each Pauli term's expectation from that group's measurement counts, and aggregate as `Σ coefficient · ⟨P⟩` into a single `float`.

A machine MAY declare and measure more than one Hamiltonian (e.g. `H_C` and `H_M`); the runtime SHALL track each expectation independently.

#### Scenario: Bell-state energy aggregates across groups

- **WHEN** a machine prepares `|Φ+>` and runs `measure(H) -> ctx.energy` for `H = XX + YY + ZZ` on `[q0, q1]`
- **THEN** `ctx.energy` equals `⟨Φ+|XX+YY+ZZ|Φ+⟩ = 3` to within statistical precision

#### Scenario: Multiple Hamiltonians tracked independently

- **WHEN** a machine measures both `H_C` and `H_M` in different transitions
- **THEN** the runtime writes each expectation to its own context field without cross-contamination

### Requirement: Hamiltonian Report Diagnostic

`q-orca run --report-hamiltonians` SHALL print, for each declared Hamiltonian, the estimated expectation, the per-commuting-group breakdown, and the number of measurement shots spent per group.

#### Scenario: Report prints per-group breakdown

- **WHEN** `q-orca run --report-hamiltonians` is invoked on a machine that measures `H`
- **THEN** the output lists `H`'s estimated expectation, each commuting group's contribution, and the shots spent per group
