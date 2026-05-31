## ADDED Requirements

### Requirement: Ancilla Reset Lifecycle

The verifier SHALL enforce, automatically for every qubit tagged `ancilla` (no `## verification rules` opt-in required), that the qubit starts in `|0⟩` and is explicitly `reset` between successive mid-circuit measurements, emitting `ANCILLA_NOT_RESET` at error severity otherwise.

For each `ancilla` qubit the verifier walks the per-state gate sequence and checks (a) no gate acts on it before its first appearance, and (b) some `reset(qs[k])` action occurs between every pair of mid-circuit measurements on it. The diagnostic names the offending state and the gate/measurement index.

#### Scenario: Reused ancilla without reset fails

- **WHEN** a machine tags `q1` as `ancilla` and performs two mid-circuit measurements on `q1` with no `reset(qs[1])` between them
- **THEN** the verifier emits `ANCILLA_NOT_RESET` pointing at the second measurement

#### Scenario: Reset between measurements passes

- **WHEN** the same machine inserts `reset(qs[1])` between the two measurements
- **THEN** no `ANCILLA_NOT_RESET` is emitted for `q1`

### Requirement: Syndrome Measurement Completeness

The verifier SHALL enforce, automatically for every qubit tagged `syndrome`, that the qubit is measured on every cyclic path it participates in, emitting `SYNDROME_NOT_MEASURED` at error severity for a cycle that prepares but never measures it.

Until bounded-loop annotations are available, the check uses the strongly-connected-component fallback: every cyclic SCC of the transition graph in which the syndrome qubit is acted upon SHALL contain at least one `measure(qs[k])` on it. When `[loop …]` annotations land, the check tightens to per-iteration completeness over the annotated loop body.

#### Scenario: Cycle without a syndrome measure fails

- **WHEN** a syndrome-extraction machine has a cyclic path that prepares the `syndrome` qubit but contains no measurement of it before the cycle repeats
- **THEN** the verifier emits `SYNDROME_NOT_MEASURED` at the cycle's body-end state

#### Scenario: Measured every cycle passes

- **WHEN** every cyclic SCC acting on the syndrome qubit contains a `measure` of it
- **THEN** no `SYNDROME_NOT_MEASURED` is emitted

### Requirement: Communication No-Cloning Escalation

The verifier SHALL escalate a no-cloning violation to `COMMUNICATION_NO_CLONING_VIOLATION` at error severity when the duplicated qubit is tagged `communication`, with a fix suggestion referencing `[send: q -> X]` protocol annotations; a non-`communication` qubit SHALL continue to emit the generic `NO_CLONING_VIOLATION` unchanged.

#### Scenario: Cloning a communication qubit escalates

- **WHEN** a machine clones a qubit tagged `communication` in a way that today produces `NO_CLONING_VIOLATION`
- **THEN** the verifier instead emits `COMMUNICATION_NO_CLONING_VIOLATION` with a fix hint pointing at `[send: …]` annotations

#### Scenario: Cloning a data qubit unchanged

- **WHEN** the cloned qubit is `data` (or untagged)
- **THEN** the verifier emits the generic `NO_CLONING_VIOLATION` exactly as before

## MODIFIED Requirements

### Requirement: Noise Target Resolution

The verifier SHALL resolve each row's target selector against the machine and emit `NOISE_TARGET_NO_MATCH` at warning severity when a selector matches no extant gate, qubit, or measurement (a no-op row).

A `qs[role:R]` selector SHALL resolve against the per-qubit roles declared in `## context`, matching every qubit whose role is `R`; a role that matches no declared qubit SHALL produce `NOISE_TARGET_NO_MATCH`. `gates[...]` selectors naming gates that never appear in the machine, and `qs[N]` indices beyond the declared qubit count, SHALL also produce `NOISE_TARGET_NO_MATCH`.

#### Scenario: Role selector resolves to matching qubits

- **GIVEN** `## context` declares qubits with roles `[q0:data, q1:ancilla, q2:ancilla]`
- **WHEN** a row targets `qs[role:ancilla]`
- **THEN** the selector resolves to qubit indices `[1, 2]` and no `NOISE_TARGET_NO_MATCH` is emitted

#### Scenario: Non-matching selector warns

- **WHEN** a row targets `qs[role:nonexistent]` (or `gates[TOFFOLI]` in a machine with no Toffoli gate)
- **THEN** the verifier emits `NOISE_TARGET_NO_MATCH` at warning severity
