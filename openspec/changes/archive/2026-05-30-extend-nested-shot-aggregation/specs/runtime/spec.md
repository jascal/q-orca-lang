## MODIFIED Requirements

### Requirement: Shot-Batched Quantum Child Aggregation

The runtime SHALL aggregate a shot-batched quantum child's measured bits into
synthesized statistic fields, regardless of whether that child is a leaf machine
or is itself composed. For a measurement-bearing child invoked with `shots=N`
where `N>1`, the runtime SHALL run N shots and, for each declared returns-section
row carrying statistics, materialize the synthesized aggregate fields using the
same names the composition verifier synthesizes (`prob_<r>`, `hist_<r>`,
`var_<r>` where `<r>` is the sanitized return name). The aggregates SHALL be
computed from the child's per-measured-bit shot counts: `prob_<r>` is the
relative frequency of outcome 1, `hist_<r>` is `{0: n0, 1: n1}`, and `var_<r>`
is `p(1−p)`. A return binding whose RHS is one of these aggregate names SHALL
receive the computed value. Under `shots=1` (or omitted) the runtime SHALL bind
the raw return value instead, with no aggregation.

A composed (non-leaf) child SHALL surface its measured-bit shot-count
distribution on its run result, accumulated across its own measurement segments
and its invoked children's runs, so the aggregation computes identically whether
the child is a leaf or composed. The shot count SHALL propagate into the composed
child's run so its measurement segments are sampled at the requested count.

#### Scenario: Expectation aggregate is the relative frequency of 1

- **WHEN** a child return `bits[0]` declares `expectation`, is invoked with
  `shots=1000`, and measures outcome 1 in 730 shots
- **THEN** the synthesized `prob_bits_0` is ≈ `0.73` and is bound to the parent
  field named on the matching return binding

#### Scenario: Histogram aggregate carries both outcome counts

- **WHEN** a child return `bits[0]` declares `histogram` and is invoked with
  `shots=N`
- **THEN** the synthesized `hist_bits_0` is a dict `{0: n0, 1: n1}` with
  `n0 + n1 == N`

#### Scenario: Single-shot binds the raw return

- **WHEN** a quantum child is invoked with `shots=1` (or no shots) and a return
  binding references the raw return name
- **THEN** the parent field receives the raw measured value, not an aggregate

#### Scenario: Composed child surfaces aggregates upward

- **WHEN** a parent shot-batches (`shots=N>1`) a composed child that itself
  invokes a leaf grandchild which measures a bit, and binds `p=prob_bits_0`
- **THEN** the parent's `p` receives a non-empty expectation computed from the
  N-shot distribution the composed child surfaced (not an empty aggregate)
