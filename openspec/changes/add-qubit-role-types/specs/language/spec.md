## ADDED Requirements

### Requirement: Qubit Role Tags

The parser SHALL accept an optional colon-delimited role tag on each element of a `## context` `list<qubit>` default, drawn from the closed vocabulary `data | ancilla | syndrome | communication`, and SHALL record a per-qubit role on the machine; an element without a tag SHALL default to role `data`.

Roles are stored as a per-qubit structure on the machine (one role per declared qubit, in declaration order) — not on the shared `QTypeQubit` type. A range shorthand `aN..aM:role` (shared alphabetic prefix, inclusive integer suffixes) SHALL expand to the flat per-element list with that role. A tag that is not in the closed vocabulary — including the reserved-but-not-yet-supported `coin` and `position` — SHALL raise `UNKNOWN_QUBIT_ROLE` naming the offending element. An untagged register SHALL parse and verify identically to today (all elements `data`).

#### Scenario: Inline role tags parse to per-qubit roles

- **WHEN** `## context` declares `| qubits | list<qubit> | [q0:data, q1:ancilla, q2:ancilla] |`
- **THEN** the machine records roles `["data", "ancilla", "ancilla"]` (one per qubit, in order)

#### Scenario: Untagged elements default to data (backward compatible)

- **WHEN** `## context` declares `| qubits | list<qubit> | [q0, q1] |`
- **THEN** both qubits have role `data` and the machine parses and verifies identically to before this change

#### Scenario: Range shorthand expands

- **WHEN** `## context` declares `| qubits | list<qubit> | [q0..q2:data, q3..q4:ancilla] |`
- **THEN** the machine records five qubits with roles `["data", "data", "data", "ancilla", "ancilla"]`

#### Scenario: Unknown or reserved role rejected

- **WHEN** an element is tagged with an unknown keyword, or with the reserved `coin` / `position` (not yet supported)
- **THEN** the parser raises `UNKNOWN_QUBIT_ROLE` naming the offending element
