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
shape as the state-vector backend. It reproduces the state-vector
backend's checks without an exponential cost: unitarity holds by
construction for Clifford gates; the dynamic entanglement check (von
Neumann entropy and Schmidt rank across the declared bipartitions) is
computed from the stabilizer tableau via the GF(2) rank of its check
matrix rather than by evolving a state vector; and the collapse-
completeness check is structural and backend-independent. When the
stabilizer dependency (Stim, then `AerSimulator(method="stabilizer")`)
is unavailable, resolution SHALL fall back to the state-vector backend
with a warning rather than failing.

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

#### Scenario: Entanglement verdict agrees across backends

- **WHEN** an entangled Clifford machine (e.g. a Bell or GHZ state) is
  verified on both the stabilizer and the state-vector backend
- **THEN** both backends report the same entanglement verdict and the same
  Schmidt rank for each declared bipartition

#### Scenario: Schmidt-rank invariant is evaluated on the tableau

- **WHEN** a Clifford machine declaring `schmidt_rank(q0, q1) >= 2` is
  verified on the stabilizer backend
- **THEN** the verifier evaluates the Schmidt rank from the tableau (not a
  state vector) and reaches the same verdict as the state-vector backend

> **Deferred:** the only invariant form with no stabilizer analogue is a
> `fidelity(|ψ>, target)` against a non-stabilizer target, and the
> `## invariants` grammar does not yet express fidelity invariants (roadmap
> §4.6, unshipped). An `INVARIANT_REQUIRES_STATEVECTOR` restriction is
> therefore unreachable in v1 and is deferred to the change that adds
> fidelity invariants — every invariant the current grammar supports
> (`entanglement`, `schmidt_rank`, `resource`) is computable on the tableau.
