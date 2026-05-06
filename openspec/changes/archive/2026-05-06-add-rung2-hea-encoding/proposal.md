## Why

The shipped `larql-polysemantic-hierarchical` example
(`add-mps-concept-encoding`, PR #46) is rung 1 of the polysemantic
encoding ladder — a CNOT-staircase MPS with bond dimension 2. It
ships four-tier hierarchical Gram structure on a 3-qubit register,
extending the rung-0 product-state demo. The research note
`docs/research/polysemantic-encoding-beyond-product-states.md` lays
out the full ladder and identifies **rung 2 — the hardware-efficient
ansatz (HEA)** — as the next non-trivial step:

- a depth-`L` block of single-qubit `Rx`/`Ry`/`Rz` rotations
  followed by an entangler (CNOT ring or chain), repeated `L` times;
- parameter tensor `θ ∈ ℝ^{3 × L × n}` (three Pauli rotations per
  layer per qubit), training to richer concept geometries than the
  rung-1 staircase can express;
- the standard expressivity-vs-entanglement workhorse in the VQE /
  QAOA literature (Cerezo et al., `2012.09265`; Kandala et al.
  `1704.05018`).

The rung-1 helper (`compute_concept_gram_mps`) handles a fixed
staircase pattern by sniffing the action's effect string. That
sniff worked because the staircase is rigid — three `Ry`s and two
`CNOT`s in a unique order — but it doesn't scale to HEA's
`3 × L × n`-knob structure. A Polygram researcher specifying
"depth=3, ring entangler" should not need to hand-write a
3-rotation × 3-layer × 4-qubit = 36-segment effect string and trust
that a regex finds it. They should declare the ansatz shape, drop
in the parameter tensor, and let the compiler instantiate the
circuit.

The companion **Polygram rung-2 verifier spike**
(`spikes/rung2-verifier-spike.md`, deferred-and-stashed) confirmed
two things this proposal depends on:

1. **Verification cost is a non-issue.** Numpy-only HEA simulation
   plus tier-ordering verification at `n=8, L=5` runs in ~50 ms per
   call. The verifier's Stage 4b can extend to HEA without any
   performance work.
2. **The structural floor generalizes for free.** Pure-φ search on
   a single Pauli rotation has eigenvalues `±1`, so the squared
   overlap remains a single sinusoid `M + V·cos(δ)`. Polygram's
   `Cancellation.structural_floor()` (the `M − |V|` analytic
   minimum) carries straight across — the rung-2 work doesn't
   invalidate any structural-floor commitments to Polygram's
   Phase 0 triage layer.

This proposal lands an **explicit grammar** for HEA ansätze (an
`## encoding` section + a `## theta` parameter block), the matching
AST extensions, a compiler helper `compute_concept_gram_hea`, an
extension to the verifier's Stage 4b for HEA tier-ordering checks,
and a minimal 3-qubit depth=3 example. The implicit
pattern-detection alternative — sniff a gigantic effect string and
hope the regex matches — was rejected: HEA has too many tunable
shape knobs (depth, entangler topology, rotation set) to encode in
effect-string conventions.

## What Changes

**New language grammar — `## encoding` section:**

- A new optional top-level section in a `.q.orca.md` machine,
  parallel to `## context` / `## events` / `## actions`.
- Declares ansatz shape via key/value rows. Required keys:
  `kind: hea`, `depth: <int>`, `entangler: <ring|chain>`, and
  `rotations: <subset of {Rx, Ry, Rz}>`. Optional `qubits:
  <register-name>` defaults to the machine's `qubits` register.
- The presence of an `## encoding` section makes a machine
  *encoding-aware*: the compiler and verifier treat that machine as
  using the declared ansatz, rather than relying on effect-string
  pattern detection.
- Rejects unknown keys with a structured parser error pointing at
  the row.

**New language grammar — `## theta` block:**

- A second new top-level section, only valid when an `## encoding`
  section is present.
- Declares the parameter tensor shape and call-site values. Format:
  one row per call site, `| concept | theta_3xLxn |` where the
  second column is a literal nested-list expression (rank-3 tensor
  flattened in `(rotation, layer, qubit)` order).
- Each row's tensor SHALL have shape `(|rotations|, depth, n)`. The
  parser produces structured errors on shape mismatch, malformed
  literals, or duplicate concept names.
- The `## transitions` table references concepts by name from the
  `theta` block; the compiler instantiates the HEA circuit per call
  site by interpolating the row's tensor into the rotation gates.

**AST extensions:**

- Two new dataclasses in `q_orca/parser/ast.py`:
  - `EncodingDecl(kind: str, depth: int, entangler: str,
    rotations: tuple[str, ...], qubits: str | None)`.
  - `ThetaBlock(rows: list[ThetaRow])` where
    `ThetaRow(concept: str, tensor: numpy.ndarray)`.
- `QMachineDef` grows two optional fields: `encoding:
  EncodingDecl | None` and `theta: ThetaBlock | None`.
- Parser dispatcher in `q_orca/parser/markdown_parser.py` adds
  `encoding` and `theta` to `_KNOWN_SECTIONS` and routes them to
  the new section parsers.

**New compiler helper — `compute_concept_gram_hea`:**

- New module `q_orca/compiler/concept_gram_hea.py`. Function
  signature: `compute_concept_gram_hea(machine, concept_action_label:
  str = "query_concept") -> numpy.ndarray[complex]`.
- Reads `machine.encoding` (must be `kind="hea"`) and
  `machine.theta` to recover per-concept `θ` tensors. Builds each
  concept state by simulating the HEA circuit on `|0^n⟩` (numpy-
  only, no Qiskit dep), then returns `gram[i, j] = ⟨c_i | c_j⟩`.
- Raises `HeaGramConfigurationError` on: missing `## encoding`,
  wrong `kind`, missing `## theta`, theta-row shape mismatch with
  the declared `(|rotations|, depth, n)`, missing concept rows for
  declared call sites, or zero call sites.
- Re-exported from `q_orca/__init__.py` next to
  `compute_concept_gram` and `compute_concept_gram_mps`.

**Verifier Stage 4b extension:**

- When `machine.encoding.kind == "hea"`, Stage 4b SHALL use the new
  `compute_concept_gram_hea` helper to evaluate the empirical Gram
  and SHALL check tier-ordering invariants declared via
  `verification rules` and `invariants` sections at tolerance
  `0.025` (the spike-validated value).
- Existing rung-0 / rung-1 dispatch is unchanged.

**New example — minimal 3-qubit depth-3 HEA:**

- New file `examples/larql-hea-minimal.q.orca.md`. Three concepts on
  a 3-qubit register, depth-3 ring-entangler HEA with rotation set
  `{Ry, Rz}`. Hand-picked θ tensors produce a three-tier Gram
  signature (self / sub-cluster / cross). The leading paragraph
  documents the analytic Gram and the encoding declaration.
- Mirrors the size and shape of `larql-polysemantic-hierarchical` so
  reviewers can compare rung 1 → rung 2 side-by-side.

**Tests:**

- `tests/test_parser.py`: parser tests for `## encoding` and
  `## theta` happy paths plus the structured-error scenarios listed
  in the language spec delta.
- `tests/test_compiler.py::TestComputeConceptGramHea`: happy path
  on the new example, missing-section, wrong-kind, theta-shape
  mismatch, missing-concept, and zero-call-sites errors.
- `tests/test_verifier.py`: Stage 4b on the new example —
  tier-ordering pass when bands are well-separated, error when
  bands collide above the 0.025 tolerance.
- `tests/test_examples.py`: `larql-hea-minimal` added to
  `EXAMPLE_FILES` fixture.

## Capabilities

### Modified Capabilities

- `language`: gains the `## encoding` and `## theta` sections.
  Existing machines remain valid (both sections are optional). The
  spec delta codifies the ansatz declaration grammar and the
  tensor-row shape invariant.
- `compiler`: gains `compute_concept_gram_hea` and the matching
  `HeaGramConfigurationError`. Pipeline behavior on machines
  without an `## encoding` section is unchanged.
- `verifier`: Stage 4b dispatches HEA-encoded machines to the new
  helper. Pipeline ordering and error codes are unchanged for non-
  HEA machines.

### Not Modified

- Effect-string grammar. HEA does not use effect-string sniffing.
- Rung-0 (`compute_concept_gram`) and rung-1
  (`compute_concept_gram_mps`) helpers. Both remain in place; HEA
  is additive.
- QASM / Qiskit emit for HEA is **out of scope** (see Non-Goals).

## Impact

- `q_orca/parser/ast.py` — add `EncodingDecl`, `ThetaBlock`,
  `ThetaRow`; extend `QMachineDef` with two optional fields.
- `q_orca/parser/markdown_parser.py` — add `encoding` / `theta` to
  `_KNOWN_SECTIONS`; add the two section parsers (~120 LOC total).
- `q_orca/compiler/concept_gram_hea.py` — new file, ~180 LOC. Pure
  numpy circuit simulator (1q rotation via `tensordot` + `moveaxis`,
  CNOT via cached 4×4 reshape) reused from `concept_gram_mps.py`.
- `q_orca/__init__.py` — re-export `compute_concept_gram_hea` and
  `HeaGramConfigurationError`.
- `q_orca/verifier/dynamic.py` (or equivalent Stage 4b dispatcher)
  — branch on `machine.encoding.kind` to select the HEA Gram
  helper.
- `examples/larql-hea-minimal.q.orca.md` — new file, ~120 lines.
- `tests/test_parser.py`, `tests/test_compiler.py`,
  `tests/test_verifier.py`, `tests/test_examples.py` — new tests
  per the language/compiler/verifier deltas (~250 LOC).
- `README.md` "Parametric actions" section grows a "HEA encoding"
  sub-heading; `CHANGELOG.md` `## Unreleased` grows an **Added**
  bullet.
- No new runtime dependency — numpy is already a transitive Qiskit
  dep.

## Non-Goals

- **No QASM / Qiskit emit for HEA.** The compiler helper builds the
  state directly via numpy. Compiling HEA to QASM/Qiskit is a
  follow-up (would require expanding the parameter tensor into a
  flat gate sequence at compile time; deferred until a Polygram
  experiment needs to run on real hardware).
- **No automatic ansatz selection.** A machine declares
  `kind: hea` explicitly. The compiler does not inspect existing
  machines and decide they "look like" HEA.
- **No ansatz kinds beyond `hea`.** `kind:` is forward-compatible —
  `kind: alternating-layered`, `kind: brick-wall`, etc. are
  reserved for future proposals. This change ships only `kind: hea`
  with `entangler: ring | chain` and `rotations: ⊆ {Rx, Ry, Rz}`.
- **No θ-from-data import.** The `## theta` block expects literal
  nested-list values. A future proposal may add a `theta_source:`
  field referencing a `.npy` / `.npz` file; out of scope here.
- **No general bond-dim / entangler-pattern grammar for rung 1.**
  This proposal is HEA-only; the existing
  `compute_concept_gram_mps` continues to handle the staircase
  pattern via effect-string sniffing.
- **No verifier rules beyond Stage 4b dispatch.** Stage 4b uses the
  same tier-ordering invariant grammar that already exists; HEA
  doesn't introduce new invariant kinds.
- **Does not retire any rung-0 / rung-1 example or test.** All
  existing examples remain valid and tested.
