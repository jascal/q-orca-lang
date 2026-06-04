## ADDED Requirements

### Requirement: Backend-Dispatched Dynamic Verification

Stage 4b dynamic verification SHALL be parameterized by the selected
backend, resolved from (in priority order) the `--backend` CLI flag, the
config-file backend, and the `## assertion policy` `backend` field. Under
`backend: auto`, the verifier SHALL classify the machine and route a
Clifford machine to the stabilizer backend and any other machine to the
state-vector backend. A stabilizer backend SHALL implement the shipped
`BackendAdapter.verify(machine, options) -> (QVerificationResult,
BackendResult)` contract and produce a `QVerificationResult` of the same
shape as the state-vector backend, so that reachability-by-simulation,
sampling-based state assertions, and backend-agnostic invariants are
evaluated identically regardless of backend. When the stabilizer
dependency (Stim, then `AerSimulator(method="stabilizer")`) is
unavailable, resolution SHALL fall back to the state-vector backend with
a warning rather than failing.

#### Scenario: Clifford machine auto-routes to the stabilizer backend

- **WHEN** a Clifford machine is verified with `backend: auto` and a
  stabilizer simulator is available
- **THEN** Stage 4b runs on the stabilizer backend and the
  `BackendResult` names the stabilizer backend

#### Scenario: Non-Clifford machine auto-routes to state-vector

- **WHEN** a machine containing `Rz(theta)` at an arbitrary angle is
  verified with `backend: auto`
- **THEN** Stage 4b runs on the state-vector backend

#### Scenario: Stabilizer unavailable falls back to state-vector

- **WHEN** a Clifford machine is verified with `backend: auto` and neither
  Stim nor the Aer stabilizer method is installed
- **THEN** Stage 4b runs on the state-vector backend with a warning and
  verification still completes

#### Scenario: Sampling-based assertions agree across backends

- **WHEN** a Clifford machine with `[assert: entangled]` /
  `[assert: separable]` annotations is verified on both the stabilizer
  and the state-vector backend
- **THEN** both backends reach the same assertion verdicts

### Requirement: Stabilizer Invariant Restriction

The verifier SHALL emit `INVARIANT_REQUIRES_STATEVECTOR`, naming the
invariant, for any invariant form that requires a full state vector —
`fidelity(...)` and `schmidt_rank(...)` — when Stage 4b runs on the
stabilizer backend, rather than silently skipping it. These forms have no
stabilizer-tableau analogue. Sampling-based state-category invariants
MUST remain evaluable on the stabilizer backend.

#### Scenario: Fidelity invariant under stabilizer backend is rejected

- **WHEN** a machine declaring `fidelity(|ψ>, |Φ+>) >= 0.99` is verified
  on the stabilizer backend
- **THEN** the verifier emits `INVARIANT_REQUIRES_STATEVECTOR` naming the
  `fidelity` invariant

#### Scenario: Schmidt-rank invariant under stabilizer backend is rejected

- **WHEN** a machine declaring `schmidt_rank(q0, q1) >= 2` is verified on
  the stabilizer backend
- **THEN** the verifier emits `INVARIANT_REQUIRES_STATEVECTOR` naming the
  `schmidt_rank` invariant
