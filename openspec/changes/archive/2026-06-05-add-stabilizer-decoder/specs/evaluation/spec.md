## ADDED Requirements

### Requirement: Logical Error Rate Benchmark

The evaluation layer SHALL provide `logical_error_rate(machine, shots, seed)`
that compiles a noisy Clifford QEC machine to its detector circuit
(`compile_to_stim_with_detectors`), builds the detector error model, decodes each
shot's sampled syndrome with a minimum-weight-perfect-matching decoder
(PyMatching, from the detector error model), and returns the logical error rate —
the fraction of shots whose decoded logical-flip prediction disagrees with the
sampled logical observable. The run SHALL be reproducible under a fixed seed.
When PyMatching is unavailable, the benchmark SHALL raise a clear "decoder
unavailable" error rather than crash.

#### Scenario: Logical error rate is reproducible under a fixed seed

- **WHEN** `logical_error_rate` is run twice with the same `(machine, shots, seed)`
- **THEN** it returns the same rate

#### Scenario: Logical error rate falls with code distance

- **WHEN** a code family is benchmarked at a fixed sub-threshold physical error
  rate across increasing distance
- **THEN** the logical error rate decreases as distance grows

#### Scenario: Logical error rate rises with the physical error rate

- **WHEN** a fixed code is benchmarked at increasing physical error rates
- **THEN** the logical error rate increases

#### Scenario: Decoder unavailable is reported, not crashed

- **WHEN** `logical_error_rate` is invoked without PyMatching installed
- **THEN** it raises a structured "decoder unavailable" error naming the extra to install
