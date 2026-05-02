# Tasks: Fix MPS Encoding Factorization

## 1. Re-derive the encoding and tier bands

- [x] 1.1 Pin the new encoding shape to **Alternative A**
      (cross-coupled-by-sum), as recommended in design.md:

          prepare_concept(a, b, c):
              Ry(qs[0], a)
              ; CNOT(qs[0], qs[1])
              ; Ry(qs[1], a + b)
              ; CNOT(qs[1], qs[2])
              ; Ry(qs[2], b + c)

      Numerically verify the non-factorization criterion before
      committing the angle-design pass: `max | |gram_new[i,j]|² −
      |gram_prod[i,j]|² | ≥ 0.05` over 1000 random angle triples
      per concept (12 concepts), with `gram_prod` the product-state
      `Ry(q0,a)·Ry(q1,b)·Ry(q2,c)·|000⟩` Gram. Expected diff ≈ 0.32.

- [x] 1.2 Run an angle-design pass for 12 concepts under the new
      encoding, targeting four ordered tiers with strict inter-tier
      separation. Starting point: the archived design's α ∈ {0,
      2π/3, 4π/3}, β ∈ {-0.75, +0.75}, γ ∈ {-0.35, +0.35}; sweep
      ±20% on β and γ if needed to land bands cleanly. Acceptance
      criterion: self = 1.0; sub-mate band, super-sib band, and
      cross-group band are all non-overlapping with ≥ 0.05 gap
      between adjacent bands.

- [x] 1.3 Record the achieved per-tier bands (exact numerical
      values from the angle-design pass) here, so downstream tasks
      can re-pin against them.

- [x] 1.4 Re-derive the polysemy column for `|f⟩ = |c_0⟩` (the
      "dog" loaded feature) under the new encoding. Verify that
      all four tiers still appear in the single column.

## 2. Compiler helper update (option 2a)

- [x] 2.1 In `q_orca/compiler/concept_gram_mps.py`, generalize the
      Ry-segment matcher from a single-bound-param shape to a
      linear-combination shape. Capture the angle expression as a
      string and parse it into a list of `(coefficient,
      parameter_name)` pairs. Whitespace-tolerant `+`, `-`,
      identifier tokens, optional integer/float coefficients.

- [x] 2.2 At call-site evaluation, substitute the bound argument
      values into the parsed linear combination to produce the
      float angle that the staircase walker passes to `_apply_1q`.

- [x] 2.3 Add a new error kind to `MpsGramConfigurationError`:
      `unrecognized_angle_expression`, raised when the angle
      expression is neither a bound parameter nor a linear
      combination of them. Message names the offending expression,
      the action, the machine, and lists the supported shapes.

- [x] 2.4 Verify that the strict single-bound-param staircase
      (the archived rung-1 shape) still parses successfully under
      the generalized matcher. The single-bound-param case is just
      the linear combination `1·α` with one term — the generalized
      parser must reduce to it.

## 3. Update the example file

- [x] 3.1 Rewrite the `prepare_concept` and `query_concept` effect
      strings in `examples/larql-polysemantic-hierarchical.q.orca.md`
      to match the new encoding. The query effect remains the exact
      inverse of the prepare effect (gate order reversed, angle
      signs negated, CNOTs self-inverse — so the `b + c` of prep
      becomes `−(b + c) = −b − c` on the q2 segment, etc.).

- [x] 3.2 Re-pin the leading paragraph: drop the false claim that
      the rung-1 staircase produces non-factorized overlap "by
      virtue of being entangled". Replace with the corrected
      framing: the staircase is *necessary* (gives bond-2 MPS
      structure) but *not sufficient* — the cross-coupled angle
      structure is what produces the non-factorized Gram. Keep
      the four-tier hierarchy framing; only the *mechanism*
      explanation changes.

- [x] 3.3 Re-pin the analytic per-tier band table to the bands
      from task 1.3.

- [x] 3.4 Re-pin the ASCII Gram heatmap to the new bands. The
      heatmap's four-tier visual structure is preserved; only the
      cell values shift slightly.

- [x] 3.5 Re-pin the polysemy column table for `|f⟩ = |dog⟩`
      from task 1.4.

- [x] 3.6 Adjust the 12 concept (α, β, γ) triples if task 1.2's
      angle pass selected a tweaked design. Otherwise leave them
      as the archived values.

## 4. Update the demo

- [x] 4.1 In `demos/larql_polysemantic_hierarchical/demo.py`,
      re-pin the §3 analytic Gram heatmap to the new bands.

- [x] 4.2 In §6 (rung-0 vs. rung-1 recap), reword the narrative.
      Drop "the CNOT staircase entangles adjacent qubits, lifting
      the block diagonal of rung-0 into a graded two-level
      hierarchy" — this was true of the new encoding but false of
      the old one. New wording: ground the hierarchy in the
      cross-coupled angle structure, with the bond-2 register as
      a *prerequisite* for the structure but not its sole cause.

- [x] 4.3 If the demo prints the analytic vs. simulated Gram
      side-by-side, verify the simulated values match the new
      analytic values within shot-noise tolerance (default 1024
      shots).

## 5. Update documentation

- [x] 5.1 In `README.md`, find the "Hierarchical polysemy" section
      (~lines 591-606) and reword to accurately describe the new
      encoding. Explicitly note that the particular
      Ry-CNOT-Ry-CNOT-Ry-on-vacuum staircase factorizes — this is
      the surprising mathematical fact this change documents.

- [x] 5.2 Append a short post-mortem section (~10 lines) at the
      end of `openspec/changes/add-mps-concept-encoding/design.md`
      pointing forward to this change. Do **not** rewrite the
      archived design — the post-mortem is the only edit to
      archived content. Exact text in this change's design.md
      §"Post-mortem entry in archived design".

- [x] 5.3 In `docs/research/polysemantic-encoding-beyond-product-
      states.md`, insert a "Caveat: Schmidt rank > 1 ≠ non-
      factorized overlap" box near the factorization formula
      (lines 124-128). Cite the bare Ry-CNOT staircase as the
      canonical counter-example.

- [x] 5.4 Update the rung-1 entry in the same research note to
      reflect that *some* bond-2 encodings still factorize, and
      that the rung-1 example uses a cross-coupled variant.

## 6. Tests

- [x] 6.1 Re-pin
      `tests/test_examples.py::test_larql_polysemantic_hierarchical_pipeline`
      tier-band assertions to the bands from task 1.3.

- [x] 6.2 Add a non-factorization assertion to the same test:
      compute the same-angle product-state Gram and assert that
      `max | |gram_mps|² − |gram_prod|² | ≥ 0.05` on at least one
      off-diagonal entry. This catches a future encoding regression
      that silently re-introduces factorization.

- [x] 6.3 Extend `tests/test_compiler.py::TestComputeConceptGramMps`
      with happy-path tests for the generalized angle-expression
      input: a cross-coupled effect string, a brick-pattern-ish
      effect string (if option 2a is general enough — otherwise
      skip), and a degenerate single-bound-param effect string
      (parses as a 1-term linear combination, must produce the
      same Gram as before).

- [x] 6.4 Add a sad-path test for the new
      `unrecognized_angle_expression` error: an effect with a
      non-linear angle expression like `Ry(qs[1], a * b)` or
      `Ry(qs[1], sin(a))` — must raise `MpsGramConfigurationError`
      with the new error kind, naming the offending expression.

- [x] 6.5 Run the full test suite — `tests/test_examples.py`,
      `tests/test_compiler.py`, and the CLI integration tests —
      and verify everything passes.

## 7. Tech-debt cross-reference

- [x] 7.1 In `openspec/changes/tech-debt-backlog/tasks.md`, mark
      §5.6 (verifier blind spot: exhaustive syndrome coverage)
      with a cross-link to a new entry §5.7 added by this change:

          §5.7 Verifier blind spot — Gram factorization vs.
          encoding entanglement

      The new entry describes a future verifier rule that would
      flag any encoding whose Gram matches the same-angle product-
      state Gram, surfacing this class of bug at verify time.
      Includes the post-mortem reference to this change as the
      motivating incident.

## 8. OpenSpec validation

- [x] 8.1 Run `openspec validate fix-mps-encoding-non-factorizing
      --strict` and resolve any issues. The change set has two
      MODIFIED capability deltas (`language` and `compiler`) and
      no ADDED or REMOVED requirements.

- [x] 8.2 Run `openspec list` and verify the change appears as
      pending. After the change ships and is archived (post-
      merge), it moves to `openspec/changes/archive/`.
