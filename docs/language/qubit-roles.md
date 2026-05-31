# Qubit role types

Tag each qubit in a `## context` register with a *role* so the structural
verifier knows what it is for. Roles drive three checks **automatically** — no
`## verification rules` opt-in. Shipped by `add-qubit-role-types`.

```markdown
## context

| Field  | Type        | Default                                              |
|--------|-------------|------------------------------------------------------|
| qubits | list<qubit> | [q0:data, q1:data, q2:data, q3:ancilla, q4:ancilla]  |
```

Untagged elements are `data`, so every existing machine parses and verifies
unchanged.

## Role taxonomy

| Role | Meaning | Triggers |
|---|---|---|
| `data` | computational payload (default) | — |
| `ancilla` | scratch / reusable workspace | **ancilla_reset** |
| `syndrome` | error information captured by measurement | **syndrome_completeness** |
| `communication` | qubit transferred between modules/parties | **communication_no_cloning** |

`coin` and `position` (quantum-walk registers) are **reserved but not yet
supported** — the parser rejects them with `UNKNOWN_QUBIT_ROLE` until their rules
ship with the walk-primitives spec, rather than accepting a tag the verifier
would ignore.

## Range shorthand

```markdown
| qubits | list<qubit> | [q0..q5:data, q6..q9:ancilla, q10:syndrome] |
```

Inclusive on both ends; the range must be a shared alphabetic prefix with
ascending integer suffixes (`q0..q5`). Malformed ranges (`q0..q5a`, `q0..x9`,
descending) are rejected. The AST stores per-element roles; the stored default is
the expanded clean list.

## The three rules

- **`ancilla_reset`** (`ANCILLA_NOT_RESET`) — an `ancilla` qubit measured
  mid-circuit must be `reset` before it is measured again. This makes the
  protection the `bit-flip-syndrome` example used to get by hand-adding a
  `mid_circuit_coherence` rule automatic for any `ancilla` qubit; an explicit
  `mid_circuit_coherence` rule still works and does not conflict.
- **`syndrome_completeness`** (`SYNDROME_NOT_MEASURED`) — a `syndrome` qubit must
  be measured on every cyclic path. **Limitation:** until `[loop …]` annotations
  land, this uses a strongly-connected-component fallback that can mis-judge in
  both directions (it fires only when *no* measure exists anywhere in the
  cyclic component — the most conservative choice); it tightens to exact
  per-iteration completeness once `bounded-loop-annotation` ships.
- **`communication_no_cloning`** (`COMMUNICATION_NO_CLONING_VIOLATION`) —
  escalates the existing no-cloning check when the copied qubit is
  `communication`, with a fix hint (and a pointer to the eventual `[send: …]`
  protocol idiom).

## Interaction with `## noise_model`

A `qs[role:R]` noise target now resolves against declared roles — e.g.
`thermal | qs[role:ancilla] | T1=60us, T2=40us` applies the channel to exactly
the ancilla qubits. (This selector parsed but was rejected before this change.)

## Scope (v1)

Roles are a **verification-time** concept — they are not queryable in runtime
guards. Roles are **erased at `invoke:` boundaries**: a child machine declares
its own roles and a parent's roles are not checked against it. A `role(qs[k])` /
`qs[i:role=R]` query in `## invariants`, per-iteration syndrome tightening, and
invoke-boundary role propagation are recorded follow-ups.
