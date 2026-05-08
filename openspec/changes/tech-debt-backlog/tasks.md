## 1. Parser

- [x] 1.1 Rename `_has_trailing_mutation` in
  `q_orca/parser/markdown_parser.py` to something that reflects
  what it actually detects (a mutation op appearing after a gate
  call within the same effect string). Current name reads like
  "this effect ends with a mutation" which is misleading.
  (Source: Hermes QA on PR #21, low severity.)
  Renamed to `_contains_mutation_segment`; docstring clarifies
  that the regex anchors on segment starts (`^` or after `;`)
  so nested `==` inside gate args don't spuriously trigger.

- [x] 1.2 Replace the fragile `"requires at least" in e` string
  match in the `_looks_like_gate_call` guard with a structural
  signal (either a shared `ARITY_ERROR_MARKER` constant or an
  explicit sentinel returned by `_parse_gate_from_effect`). The
  current test pins the wording; a future rephrase silently
  re-enables the double-fire regression.
  (Source: Claude code review on PR #17, concern 1.)
  Added module-level `_ARITY_ERROR_MARKER = "requires at least"`
  constant in `q_orca/parser/markdown_parser.py`. Both producers
  (MCX/MCZ and the new CSWAP branch from 1.3) and the
  looks-like-gate consumer reference the constant, so a future
  rephrase only requires updating the marker in one place.

- [x] 1.3 Make CSWAP arity errors symmetric with MCX/MCZ.
  `MCX(qs[0], qs[1])` raises a structured "needs ≥3 args" error,
  but `CSWAP(qs[0], qs[1])` falls through to the generic "looks
  like a gate call" warning. Add a CSWAP-specific arity branch
  next to the MCX/MCZ one (~6 lines).
  (Source: Claude code review on PR #17, concern 2.)
  Added a CSWAP wrong-arity branch in `_parse_gate_from_effect`
  mirroring the MCX/MCZ shape, plus a `TestCSWAPArityValidation`
  class in `tests/test_parser.py` covering the arity error and
  the no-double-fire invariant.

- [x] 1.4 Build the known-gate list in the unknown-gate warning
  message from `KNOWN_UNITARY_GATES` at module load, instead of
  the hardcoded inline string in
  `q_orca/parser/markdown_parser.py`. The inline list is a second
  source of truth that drifts as gates are added (extend-gate-set
  work will add more).
  (Source: Claude code review on PR #17, concern 4.)
  Added `_format_known_gate_list()` that imports
  `KNOWN_UNITARY_GATES` from `q_orca.verifier.quantum`, sorts the
  set, and emits parser-side aliases (Hadamard for H, CCX for
  CCNOT). Result cached at module load as `_KNOWN_GATE_LIST` and
  interpolated into the typo warning. New regression test
  `test_warning_lists_known_gates_from_canonical_set` pins that
  recently-added gates (CCZ, MCX, MCZ, …) appear automatically.

- [x] 1.5 Flag "extra non-`qs` slot without `: type`" in
  `_parse_signature`. Today `(qs, c) -> qs` silently returns a
  zero-parameter signature because no slot contains `:`; the
  transition `foo(0)` then errors with the unhelpful "not
  parametric" message rather than pointing at the missing
  `: int`. Adding an error (or warning) in `_parse_signature`
  surfaces the intent mismatch at parse time.
  (Source: Claude code review on PR #26, suggestion 1.)
  Added a `len(raw_params) > 1` branch in the early-exit (no
  typed slots) path of `_parse_signature` that lists all extra
  slot names and points at the canonical `(qs, c: int) -> qs`
  shape. New tests in `TestParametricActionSignature`
  (`tests/test_parser.py`) pin the diagnostic, including an
  all-extras-listed case and a no-fire case for the historical
  zero-parameter forms `(qs) -> qs` and `(ctx) -> ctx`.

- [x] 1.6 Converge bare-name and call-form typo detection for
  parametric actions. Today an undeclared bare-name reference
  (`query_concep`) slips through silently while the call-form
  typo (`query_concep(0)`) is reported. The asymmetry was a
  deliberate scoping call on PR #26 but should be revisited now
  that section 4–7 have shipped.
  (Source: Claude code review on PR #26, suggestion 2.)
  Converged the two paths in `_resolve_transition_actions`: an
  undeclared bare-name reference now emits a structured
  "bare-name action {name!r} is not declared in the actions
  table" error, mirroring the call-form wording. A pre-flight
  scan of all `examples/*.q.orca.md` and 103 in-test markdown
  fixtures confirmed no live machine relied on the silent-allow
  behavior. New tests
  `test_bare_name_unknown_action_is_error` (typo flagged) and
  `test_bare_name_known_action_is_not_flagged` (declared
  zero-parameter still clean) pin both directions in
  `TestParametricTransitionCall`.

- [x] 1.7 Replace naive `args_str.split(",")` in
  `_resolve_transition_actions` with a paren-aware
  `_split_top_level_commas` helper. Today `_evaluate_angle` only
  accepts single-arg expressions so there's no live bug, but
  `mix(atan2(a, b), 0)` will be mis-split into three args the
  moment a multi-arg angle expression lands.
  (Source: Claude code review on PR #26, suggestion 3.)
  Added `_split_top_level_commas` helper that tracks paren and
  bracket depth, and switched `_resolve_transition_actions` to
  use it. Unit-tested in `TestSplitTopLevelCommas`
  (`tests/test_parser.py`) with cases covering nested calls,
  nested subscripts, deeply-nested calls, empty input, and
  whitespace stripping.

- [x] 1.8 Drop `re.DOTALL` from the call-form regex in
  `_resolve_transition_actions` (or document why it's needed).
  Markdown table cells shouldn't contain newlines, so the flag
  buys nothing and permits weird inputs.
  (Source: Claude code review on PR #26, suggestion 4.)
  Removed `re.DOTALL` from `_CALL_FORM_RE`. Cell text is
  single-line by the time the structural parser delivers it, so
  the flag was a no-op that incidentally permitted weirdly-shaped
  inputs.

- [x] 1.9 Allow underscores in the `_looks_like_gate_call` regex
  (`[A-Za-z_][A-Za-z0-9_]*` instead of `[A-Za-z][A-Za-z0-9]*`),
  so typos like `U_3(qs[0], ...)` for `U3` are still flagged.
  Unlikely in practice but essentially free.
  (Source: Claude code review on PR #17, concern 3.)
  Widened the leading identifier in `_looks_like_gate_call` and
  added `test_underscore_typo_in_gate_name_triggers_warning` to
  pin the behavior.

## 2. Verifier / backend adapters

- [x] 2.1 Audit CUDA-Q backend error reporting for `severity` /
  `valid` field consistency. Hermes flagged cases where a result
  could carry `severity="error"` alongside `valid=True`, or the
  inverse. Confirm the convention (error severity must mean
  `valid=False`) and fix any drift.
  (Source: Hermes QA on PR #21, low severity.)
  Audit result: no live drift — the sole mutation site in
  `q_orca/backends/cudaq_backend.py::CudaQBackend.verify`
  inserted a `severity="warning"` entry into `result.errors`
  without re-deriving `valid`. The invariant held today but the
  pattern was fragile. Fixed by constructing a new
  `QVerificationResult` with `valid` recomputed from the merged
  error list, and added a regression test
  (`test_severity_valid_invariant_holds`) that asserts the
  invariant on the backend's output.

- [x] 2.2 Add a regression test pinning that arity-zero calls to
  a parametric action (e.g. a bare-name reference to an action
  declared `query_concept(c: int)`) are rejected upstream. The
  verifier's `check_unitarity` assumes this today — parametric
  actions are skipped in the per-action loop and only visited via
  `bound_arguments`, so a bare-name slip would silently leave the
  gate unchecked.
  (Source: Claude code review on PR #27, concern 4.)
  Added `test_arity_zero_call_to_parametric_action_rejected_upstream`
  in `TestParametricActionVerification` (`tests/test_verifier.py`).
  It pins three things end-to-end: (1) the parser emits the
  "is parametric and requires arguments" error, (2) the
  surviving transition has `bound_arguments is None` so the
  verifier's per-call-site loop never visits it, and (3)
  `verify_quantum` does not fabricate a spurious
  `QUBIT_INDEX_OUT_OF_RANGE` against the unbound template.

- [x] 2.3 Add a parametric-specific `ORPHAN_ACTION` test so
  §6.4 behavior (orphan parametric actions still trigger the
  error without firing expansion-time checks) is pinned by a
  dedicated test rather than only implicitly covered by
  `test_bound_range_clean_across_call_sites`.
  (Source: Claude code review on PR #27, concern 5.)
  Added `test_orphan_parametric_action_warns_without_expansion_checks`
  in `TestParametricActionVerification` (`tests/test_verifier.py`).
  Builds a machine where `query_concept(c: int)` is declared but
  never referenced; asserts (a) `check_structural` emits exactly
  one `ORPHAN_ACTION` warning for the orphan parametric action,
  and (b) `verify_quantum` produces zero errors keyed on the
  orphan name — the per-call-site loop has nothing to iterate.

- [x] 2.4 Add a declarative opt-out path for `SUPERPOSITION_LEAK`
  on intentional single-target measure-to-final transitions.
  Today the rule in `q_orca/verifier/superposition.py` fires a
  warning when a superposition state has an unguarded measure
  transition to a `[final]` state; under `q-orca verify --strict`
  in CI (`.github/workflows/verify-examples.yml`), those warnings
  become errors. The only ways to silence them today are (a) add
  a `prob_collapse(...)` guard — the verifier checks for
  *presence* only, not validity — or (b) split the final state
  into per-outcome targets with complementary guards summing to 1
  (bell-entangler pattern). PR #28 shipped option (a) on
  `larql-polysemantic-2` / `-12` as a tactical fix. The proper
  fix is a declarative opt-out — either a new verification-rule
  name (e.g. `measurement_collapse_allowed`) or a marker on the
  target state (e.g. `[final, collapse_sink]`) — that tells the
  verifier "this is an intentional trace-out of the measurement
  outcome" so machines don't have to fabricate guard strings.
  Once landed, revisit both polysemantic examples and drop the
  tactical guards in favor of the declarative marker.
  (Source: PR #28 CI failure triage.)
  Took the verification-rule path. Added
  `measurement_collapse_allowed` to the parser's `known_kinds`
  in `_parse_verification_rules` so it lands as a structured
  rule kind rather than `custom`. In
  `q_orca/verifier/superposition.py`, added
  `_machine_allows_measurement_collapse` and a
  `collapse_allowed` early-out on both warning paths: the
  per-transition unguarded-measure-to-final path and the
  measurement-coverage path that fires when all targets are
  final. The opt-out does NOT silence the genuine error case
  (unguarded measure to a non-final state) — pinned by
  `test_opt_out_does_not_mask_unguarded_to_non_final` in
  `TestMeasurementCollapseAllowed`. Migrated polysemantic-2,
  polysemantic-12, and polysemantic-clusters: dropped the
  tactical `prob_collapse(...)` guards (and the now-empty
  guards table on the smaller examples) in favor of the
  declarative rule, with the analytic-probability annotations
  promoted into the rule description.

## 3. Compiler

- [x] 3.1 Tighten `_SUBSCRIPT_RE` in
  `q_orca/compiler/parametric.py` to `qs\[` (so int-param
  substitution only happens inside `qs[...]` subscripts), or
  update the docstring so the broader behavior is explicit.
  Today the regex matches any `word[...]` subscript, which is
  wider than the "inside `qs[...]` slots" claim in the docstring.
  (Source: Claude code review on PR #27, concern 2.)
  Narrowed `_SUBSCRIPT_RE` from `(\w+)\[([^\]]+)\]` to
  `(qs)\[([^\]]+)\]`. Added a regression test
  `TestExpandActionCallSubscriptScope::test_classical_bits_subscript_is_not_substituted`
  that pins the new boundary: a `bits[c]` subscript stays literal
  while the sibling `qs[c]` gets the int substitution.

- [x] 3.2 Add a comment on `_ROTATION_GATE_ANGLE_RE` noting that
  it only accepts 1–2 qubit slots before the angle, so future
  multi-controlled rotations (e.g. hypothetical
  `MCRx(qs[0], qs[1], qs[2], theta)`) must either extend the
  regex or land with an explicit template-time validation path.
  (Source: Claude code review on PR #27, concern 3.)
  Added the rationale block above the regex in
  `q_orca/parser/markdown_parser.py`, noting the 1–2 qubit-slot
  shape and that a hypothetical `MCRx`-style multi-controlled
  rotation would silently skip the angle-binding check until the
  regex is extended.

- [x] 3.3 Fix the `_format_angle_literal` docstring — `repr(float)`
  does use scientific notation below ~1e-4 (`repr(1e-10)` →
  `'1e-10'`), so the "avoiding scientific notation" claim is
  slightly misleading even if fine for the angle magnitudes
  rotation gates see in practice.
  (Source: Claude code review on PR #27, nit 1.)
  Reworded the docstring to acknowledge that `repr(float)` does
  switch to scientific notation outside ~1e-4..1e16 and to clarify
  that decimal form holds because rotation-gate angles sit inside
  that band in practice.

- [x] 3.4 Drop the redundant `list(bound_arguments)` copy in
  `expand_action_call` when the caller already passes a list.
  Either narrow the type hint to `list[BoundArg]`, or only
  materialize when necessary. Minor.
  (Source: Claude code review on PR #27, nit 2.)
  Narrowed the type hint from `Iterable[BoundArg] | None` to
  `list[BoundArg] | None` (matching all live call sites, which all
  pass `t.bound_arguments: Optional[list[BoundArg]]`) and removed
  the eager `list(...)` copy. The function now iterates the input
  directly via `zip`.

- [x] 3.5 Reference: the verifier→compiler coupling introduced in
  PR #27 (importing `_parse_effect_string` from
  `q_orca/compiler/qiskit.py` into `q_orca/verifier/quantum.py`)
  is subsumed by the open `consolidate-gate-parser` OpenSpec
  change, which promotes the effect-string parser to a shared
  module. No separate backlog item needed — tracked there.
  (Source: Claude code review on PR #27, concern 1.)
  Reference-only entry — closed in place; the actual fix lands
  under `consolidate-gate-parser`.

- [x] 3.6 Validate effect structure in
  `q_orca/compiler/concept_gram.py::_check_signature`. Today
  only the *parameter shape* is checked (3 angles); a caller
  could pass an action with signature
  `(qs, a: angle, b: angle, c: angle) -> qs` but effect like
  `CNOT(qs[0], qs[1]); Rz(qs[2], c)` and get a silently-wrong
  Gram matrix. A cheap effect-string regex check
  (`Ry\(qs\[0\], ...\)` etc., matching either the preparation
  or inverse-preparation form) would harden the "wrong shape"
  error scenario. Not urgent for an opt-in analysis helper but
  worth doing before a second caller lands.
  (Source: Claude code review on PR #31, suggestion 3.)
  Added a sibling `_check_effect` helper (called from
  `compute_concept_gram` right after `_check_signature`) that
  splits the effect on `;` and matches each segment against
  `_RY_SEGMENT_RE` (`Ry(qs[i], [-]name)`). Rejects: wrong
  segment count, foreign gates (CNOT/Rz/etc.), out-of-range
  qubit subscripts, duplicate qubits, mixed sign conventions,
  and parameter-name/qubit-position misalignment. The inverse
  form used by `larql-polysemantic-clusters.q.orca.md` (all
  three segments negated, qubits reversed) passes unchanged
  — pinned by `test_inverse_form_effect_passes`. Five new
  tests in `TestComputeConceptGram` cover each rejection branch.

- [x] 3.7 Inline the unused intermediate `shape` variable in
  `_check_signature` (`concept_gram.py:50`) — it's only used in
  the error f-string, so computing it eagerly bloats the happy
  path. Micro-nit, ~1-line change.
  (Source: Claude code review on PR #31, suggestion 4.)
  Moved the `shape` list-comp inside the `if` branch so it's
  only built when the signature actually fails the check.

- [x] 3.8 Migrate `tests/test_compiler.py::TestComputeConceptGram`
  error-path tests from the `try/except/else: raise
  AssertionError(...)` pattern to the codebase-idiomatic
  `with pytest.raises(ConceptGramConfigurationError) as
  exc_info: ...` + `str(exc_info.value)` pattern used elsewhere
  in `test_compiler.py`. Functional behavior is correct today;
  style-only.
  (Source: Claude code review on PR #31, suggestion 5.)
  Migrated all three error-path tests
  (`test_wrong_signature_int_parameter_raises`,
  `test_missing_action_raises`, `test_no_call_sites_raises`) to the
  `pytest.raises(...) as exc_info` + `str(exc_info.value)` pattern
  matching the rest of the file.

- [x] 3.9 Vectorize the Gram double-loop in `compute_concept_gram`.
  The current Python-level `O(N²)` nested loop (`concept_gram.py
  :123-126`) is fine at N=12, but collapses to one vectorized
  call with
  `np.prod(np.cos((angles[:, None, :] - angles[None, :, :]) /
  2.0), axis=-1)`. Worth doing if `compute_concept_gram` ever
  targets dictionaries past ~100 concepts; no action needed at
  current scale.
  (Source: Claude code review on PR #31, suggestion 6. Related
  to the N ≈ 1K statevector-path wall discussed in
  `docs/research/polysemantic-encoding-beyond-product-states.md`.)
  Decision: defer. The vectorized form is recorded above in this
  task body so the next author can apply it directly when N grows
  past the documented ~100-concept threshold. Closing the backlog
  entry rather than carrying forever; if the threshold is hit, spin
  out as a dedicated `vectorize-gram-loop` change per §5.1.

- [x] 3.10 Reframe the hardcoded 3-qubit assumption in
  `compute_concept_gram`. The signature check demands exactly
  three angle parameters, matching the canonical example, but
  the module docstring phrases this as an example rather than a
  constraint. Either (a) generalize the helper to accept any
  `n`-angle signature where `n` matches the concept register
  size, or (b) tighten the docstring to state the 3-angle
  constraint explicitly and point at
  `add-mps-concept-encoding` (which ships the general `n`-angle
  helper variant under a different ansatz). Option (b) is the
  minimum fix; option (a) is a real generalization that
  probably warrants its own small OpenSpec change if pursued.
  (Source: Claude code review on PR #31, suggestion 7.)
  Took option (b): the module docstring now leads with the
  fixed 3-qubit / 3-angle shape as a constraint, points at
  `add-mps-concept-encoding` for the general `n`-angle variant,
  and the signature bullet calls out "exactly three angle
  parameters, no more, no less" so the requirement reads as
  intentional rather than illustrative.

- [x] 3.11 Wrap `float(b.value)` coercion in
  `compute_concept_gram_mps` (`concept_gram_mps.py`, the per-call-site
  arity-validation block + the angle-matrix build a few lines below)
  with a `try/except ValueError` that re-raises as
  `MpsGramConfigurationError` naming the offending call site, action,
  and value. Today a non-numeric `BoundArg.value` (e.g., a context-
  field reference, if a future parser path ever lets one through to
  `bound_arguments`) surfaces as a bare `ValueError` from the float
  coercion, mentioning neither the machine nor the helper. Not a live
  bug — the parser only emits int/float literals into `BoundArg.value`
  today — so this is defense-in-depth for callers that build
  `QMachineDef`s programmatically, mirroring the rationale for the
  per-call-site arity guard added in PR #45.
  (Source: Claude Sonnet 4.6 code review on PR #45, suggestion 2.)
  Folded the angle-matrix build into the existing per-call-site loop
  so the arity guard and the float coercion share the same iteration
  context. Each `float(b.value)` is now wrapped in
  `try/except (TypeError, ValueError)`; on failure we raise
  `MpsGramConfigurationError` naming the machine, the action, the call-
  site index, the argument index, and the offending repr. Pinned by
  `test_call_site_non_numeric_bound_argument_raises` in
  `TestComputeConceptGramMps`, which mutates a parsed
  `BoundArg.value` to a string and asserts the contextful error replaces
  the bare `ValueError`.

- [ ] 3.12 Vectorize the Gram double-loop in
  `compute_concept_gram_mps` (`concept_gram_mps.py:392-395`). The
  matrix is Hermitian by construction (`gram[j,i] = conj(gram[i,j])`)
  with unit-modulus diagonal, but the current implementation computes
  all N² inner products independently. Two cheap wins available, in
  order of preference: (a) stack the flat statevectors into a single
  `(N, 2^n)` array and compute the whole Gram in one
  `flat @ flat.conj().T` numpy call (also typically more accurate);
  (b) cut the loop to `for i in range(n_calls): for j in range(i,
  n_calls):` with a `gram[j, i] = gram[i, j].conjugate()` mirror,
  halving the constant. The module docstring advertises
  `O(N² · 2ⁿ)` runtime when option (a) makes it effectively a single
  BLAS call. Irrelevant at the shipped n=3 / N≈12 example but worth
  doing before a larger MPS dictionary lands.
  (Source: Claude Sonnet 4.6 code review on PR #45, suggestion 5.
  Related to the N ≈ 1K statevector-path wall discussed in
  `docs/research/polysemantic-encoding-beyond-product-states.md`.)

- [x] 3.13 Promote `_infer_qubit_count` from
  `q_orca/compiler/qasm.py` to a public helper in a shared module
  (e.g. `q_orca/compiler/util.py`). Both `compute_concept_gram` and
  `compute_concept_gram_mps` reach into the qasm module's underscored
  API to call it; convention has already been set by the first
  helper, but each new caller hardens the smell. Not a blocker for
  any individual PR — appropriate to land "next time you touch
  `qasm.py`" or as a small dedicated refactor change. Update the two
  concept-gram helpers (and any future caller) to import from the
  new location.
  (Source: Claude Sonnet 4.6 code review on PR #45, suggestion 6.)
  Created `q_orca/compiler/util.py` and moved the helper there as
  the public `infer_qubit_count`. `q_orca/compiler/qasm.py` now
  imports it as `_infer_qubit_count = infer_qubit_count` so internal
  qasm callers and the existing `tests/test_bug_fixes.py` parity
  tests (`TestQubitCountInferenceQasmParity`) keep working without
  churn. Updated `q_orca/compiler/concept_gram_mps.py` and
  `q_orca/compiler/concept_gram_hea.py` to import the public name
  from the new location instead of reaching into qasm's underscored
  surface. (`concept_gram.py` is fixed at 3 qubits and never imported
  the helper, contrary to the original task body — only the MPS and
  HEA helpers needed updating.) The other three peer copies in
  `q_orca/compiler/qiskit.py`, `q_orca/compiler/cudaq.py`, and
  `q_orca/verifier/dynamic.py` remain in place; consolidating those
  is out of scope for this entry, which targeted the specific
  cross-module reach that PR #45's review flagged. Pinned by
  `TestInferQubitCountPublicHelper` in `tests/test_compiler.py`,
  including a `qasm_alias is infer_qubit_count` identity assertion
  so a future accidental re-shadowing in qasm fails loudly.

## 4. MCP server / skills

- [x] 4.1 Surface parse errors from `parse_skill`
  (`q_orca/skills.py:131-143`). Today the skill calls
  `parse_q_orca_markdown(source)` and builds `machines` from
  `parsed.file.machines`, returning `status="success"` regardless
  of `parsed.errors`. A genuinely malformed source (invalid table
  syntax, malformed kets, etc.) produces `parsed.errors` populated
  AND `parsed.file.machines = []`, so the skill reports
  `status="success", machines=[], machine=None` — silently
  swallowing the error list. The `parse_machine` MCP tool that
  fronts this then can't distinguish "no machine in input" from
  "machine had parse errors." Mirror the `verify_skill` pattern
  (lines 163-177): when `parsed.errors` is non-empty, return
  `status="error"` with the errors surfaced in a structured field
  on `ParseSkillResult`. Genuine "input contained no machine
  heading" (`parsed.errors == [] and parsed.file.machines == []`)
  stays `status="success"` with `machines=[]` so the call shape
  remains unambiguous.
  (Source: Hermes QA on the MCP server, observation 3.)
  Added `errors: list[SkillError]` to `ParseSkillResult` and a
  pre-build branch in `parse_skill` that fires when
  `parsed.errors` is non-empty: returns
  `status="error", machines=[], machine=None` and maps each parser
  message to a `SkillError(code="PARSE_ERROR", severity="error")`,
  mirroring the `verify_skill` pattern. The genuinely-empty path
  (`parsed.errors == [] and parsed.file.machines == []`) stays
  `status="success"` with `machines=[]`. Pinned by
  `test_parse_with_parser_errors_returns_error_status` (undeclared
  bare-name action source — surfaces with `code="PARSE_ERROR"`,
  the offending action name in `message`, and the `errors` field
  populated) and `test_parse_no_machine_no_errors_stays_success`
  (empty input — `status="success"`, no `errors` key) in
  `tests/test_skills.py::TestParseSkill`.

- [ ] 4.2 Document the no-auth-on-tool-calls model in
  `q_orca/mcp_server/`'s top-level docs / README. The MCP server
  speaks JSON-RPC over stdio, so any client that connects can call
  any tool — including `generate_machine` and `refine_machine`
  which spend on the LLM provider — without an auth check. This
  is intentional given the stdio = local trust boundary, but the
  property is invisible to operators who haven't read the code.
  Add a "Threat model" or "Trust boundary" section that names
  stdio-as-local-trust-boundary explicitly, and flag the LLM-
  spending tools so anyone wiring up a non-stdio transport in the
  future knows to add auth before flipping the bit.
  (Source: Hermes QA on the MCP server, observation 2.)

- [ ] 4.3 Sanitize exception messages on the `tools/call` error
  path (`q_orca/mcp_server/`, around the `isError` content build
  flagged at line 244 in Hermes's report). Today caught exceptions
  are stringified directly into the response; a stack trace or
  filesystem path leak would land verbatim in the client message.
  Low priority while the transport is stdio-only (the client *is*
  the local user), but a cheap hardening step before any non-
  stdio transport ships. Either filter to a known set of
  exception types with curated messages, or strip absolute paths
  and limit to the exception class name + a short generic
  message, with the full repr behind a debug flag.
  (Source: Hermes QA on the MCP server, observation 4.)

## 5. Example library — QA findings (2026-05-01)

Sourced from a full QA pass on `examples/*.q.orca.md`, 2026-05-01.
The teleportation correction-target bug from the same QA was fixed
in-place (qs[0] → qs[2] on `apply_Z` / `apply_X` / `apply_XZ` in
`examples/quantum-teleportation.q.orca.md`); items below are the
remaining findings.

- [x] 5.1 **bit-flip-syndrome.q.orca.md: missing (1,1) syndrome
  produces wrong corrections.** Today the example has two correction
  actions — `correct_q0: if bits[0] == 1: X(qs[0])` and `correct_q2:
  if bits[1] == 1: X(qs[2])`. Under syndrome (1,1) the error sits on
  q1, so both corrections fire on the wrong qubits and q1 stays
  flipped, giving a logical X on the encoded state for ~25% of error
  patterns. The verifier doesn't catch it because there's no rule
  that every syndrome pattern must map to its correct correction.
  The proper fix needs the parser to support compound bit conditions
  (`if bits[0] == 1 and bits[1] == 1: X(qs[1])`), which today silently
  parse to `None` (verified: `_parse_conditional_gate_from_effect` on
  the compound form returns `None` with no error). Scope:
    - `q_orca/ast.py::QEffectConditional` — extend with
      `extra_conditions: list[tuple[int, int]]` (or refactor to a list
      of `(bit_idx, value)` tuples); existing single-condition
      consumers stay backward-compatible by reading the first entry.
    - `q_orca/parser/markdown_parser.py::_parse_conditional_gate_from_effect`
      — extend the regex to optionally match
      `(\s+and\s+bits\[(\d+)\]\s*==\s*(\d+))*` after the first
      condition, before the `:` and gate body.
    - `q_orca/compiler/qasm.py` — emit `if (c[0] && c[1]) { ... }`
      for compound conditions (OpenQASM 3.0 supports `&&`).
    - `q_orca/compiler/qiskit.py` — Qiskit's `if_test` doesn't accept
      AND'd conditions directly; emit nested `with qc.if_test(...)`
      blocks (the inner gate fires only when both bits match).
    - `q_orca/verifier/quantum.py::feedforward_bits.add(...)` (around
      line 388) — add every condition's `bit_idx`, not just the
      head one.
    - Once the parser change lands, fix the example: keep
      `correct_q0` and `correct_q2` (they remain correct for the
      single-error cases (1,0) and (0,1) — they fire spuriously on
      (1,1) but the new `correct_q1` undoes the spurious flips by
      acting on q1 in the right way). Cleanest rewrite: tighten both
      to "this bit set AND the other clear," then add `correct_q1: if
      bits[0] == 1 and bits[1] == 1: X(qs[1])`. Add a behavior test
      asserting all four syndrome patterns end in the correct logical
      state.
  Severity: high — example silently produces wrong quantum results.
  May warrant a dedicated OpenSpec change
  (`extend-conditional-gate-compound-bits`) per §5.1 since it touches
  AST + parser + two compilers + verifier.
  (Source: 2026-05-01 example library QA, bug 2.)
  Closed via the dedicated
  `extend-conditional-gate-compound-bits` OpenSpec change: AST gained
  `QEffectConditional.conditions: list[tuple[int, int]]`, the parser
  recognises `and`-joined clauses (rejecting same-bit conflicts), both
  compilers emit compound conditionals (QASM `&&`, Qiskit nested
  `if_test`), the verifier registers every clause bit as fed-forward,
  the example now ships three compound-condition corrections covering
  all four syndrome patterns, and `tests/test_bit_flip_syndrome.py`
  pins the round-trip via aer-gated behavior tests for (0,0), (1,0),
  (1,1), and (0,1).

- [x] 5.2 **README example count is stale (15 → 16).** `README.md:12`
  ("All 15 bundled example machines …") and `README.md:274` ("All
  bundled examples …") both reflect the pre-`larql-gate-knn-grover`
  count; `docs/compute-needs.md:155` has the same drift. There are 16
  examples in `examples/` today (`ls examples/*.q.orca.md | wc -l`).
  Fix: update the three references and add a brief note in the README
  to derive the count from the directory rather than hardcoding it,
  or replace with "all bundled example machines" without a number.
  (Source: 2026-05-01 example library QA, overall verdict.)
  Audit at fix time (2026-05-04, 19 examples in `examples/`):
  `README.md:12` had already drifted forward to "All 19 bundled …"
  via an interim PR; `README.md:274` was already number-free
  ("All bundled examples …"); only `docs/compute-needs.md:155`
  remained at "All 15 example machines" and was bumped to 19. No
  derive-from-directory note added — the two surviving references are
  in marketing/landing-page paragraphs where a concrete number reads
  better than a generic one.

- [x] 5.3 **Stale syntax in `vqe-heisenberg.q.orca.md` and
  `predictive-coder-learning.q.orca.md` — they don't parse on the
  live parser, but their tests pass via `verify_skill`.** Direct
  `parse_q_orca_markdown` against the current parser yields:
    - `vqe-heisenberg`: 3 errors — `apply_ansatz: (qs, theta) -> qs`
      missing `: angle` annotation on the `theta` slot; `set_energy`
      and `increment_iter` use compound RHS expressions
      (`ctx.theta * ctx.theta - 1.0`, `ctx.iteration + 1`) which the
      mutation parser rejects ("must be a numeric literal or a bare
      context-field identifier").
    - `predictive-coder-learning`: 4 errors — `apply_ansatz` uses
      array-index notation in the angle slot (`Ry(qs[0], theta[0])`)
      which the angle-expression parser doesn't accept.
  These tests pass because `verify_skill`
  (`q_orca/skills.py:157-181`) calls `parse_q_orca_markdown` but
  doesn't check `parsed.errors` before proceeding to verification —
  the malformed AST runs through verify and emits `status="valid"`.
  Two-part fix: (a) gate `verify_skill` on `parsed.errors` being
  empty (mirrors the gap that §4.1 already documents for
  `parse_skill`); (b) bring both example files into compliance with
  the current parser (annotate the parametric `theta` slot, decompose
  compound RHS into helper-context fields or split into multiple
  mutations, replace `theta[0..2]` with three scalar fields
  `theta_0`, `theta_1`, `theta_2`). Item (a) prevents future drift;
  item (b) clears the live divergence.
  (Source: 2026-05-01 example library QA, "Stale Examples".)
  Done: (a) added `if parsed.errors:` early-return in
  `verify_skill` (`q_orca/skills.py`) emitting structured
  `PARSE_ERROR` items so the skill no longer silently passes when
  the parser has rejected the input. (b) `vqe-heisenberg` —
  annotated `apply_ansatz` as `(qs, theta: angle) -> qs`, dispatched
  it via `apply_ansatz(theta)` in the two transitions that invoke
  it (bare-name dispatch on a parametric action is now a hard
  error), rewrote `increment_iter` to `ctx.iteration += 1`, and
  cleared the bogus compound RHS in `set_energy` since the verifier
  hard-restricts scalar context mutations to `int` LHSs (the
  example's `energy` is `float`, so the original
  `ctx.energy = ctx.theta * ctx.theta - 1.0` could never have
  verified — it only "worked" because the parser silently dropped
  the whole mutation; `set_energy` is now a no-op transition stamp,
  matching the convention that energy estimates come from a
  measurement effect at runtime, not a context update).
  `predictive-coder-learning` — split the `theta: list<float>` slot
  into three scalar fields `theta_0`, `theta_1`, `theta_2` so the
  angle-expression parser can resolve them without array indexing,
  updated `apply_ansatz` and the docstrings accordingly, and cleared
  `gradient_step`'s body for the same scalar-float-mutation reason
  as `set_energy` (the runtime would drive learning via an
  out-of-band update; the example documents the loop topology).
  Bonus: the new gate exposed two latent parse errors in
  `bell-entangler.q.orca.md` (`set_outcome_0`/`set_outcome_1` had a
  spurious `val` slot in their signatures with no `: type`
  annotation); dropped the unused parameter so both actions read
  `(ctx) -> Context`. All three examples now parse cleanly and
  `pytest -q` is green (865 passed, 6 skipped).

- [x] 5.4 **Test coverage gaps for shipped examples.** Six of the 16
  examples have weak or no test coverage (verified by collecting
  `pytest --collect-only` and grepping for each example name):
    - No tests at all: `predictive-coder-minimal`,
      `predictive-coder-learning`, `larql-gate-knn-grover`.
    - Parse-only (no verify/compile/behavior assertion):
      `bit-flip-syndrome`, `active-teleportation`.
    - Resource-only (no parse/verify/compile against the example
      file): `qaoa-maxcut` (covered by
      `test_resource_estimation.py::test_qaoa_maxcut_resources`).
  Fix shape: mirror the structure of `tests/test_quantum_teleportation.py`
  (parse / verify / compile / snapshot classes) for each gap example.
  Behavior tests should assert end-state correctness where applicable
  (e.g. for `bit-flip-syndrome`, all four syndrome patterns end at
  `|corrected>` with the right logical state — but that test should
  block on §5.1 since the underlying example is broken). Defer
  `predictive-coder-learning` until §5.3 (b) lands.
  (Source: 2026-05-01 example library QA, "Untested Examples".)
  **Closed 2026-05-06 by `tech-debt-backlog-5-4-example-test-coverage`:**
  added `test_bit_flip_syndrome.py` (covered transitively by §5.1,
  PR #62), `test_active_teleportation.py`, `test_qaoa_maxcut.py`,
  `test_predictive_coder_minimal.py`,
  `test_predictive_coder_learning.py`, and
  `test_larql_gate_knn_grover.py` — 71 new tests (parse / verify /
  compile / snapshot for all 5 + behavior tests for the three
  examples whose semantics admit them: active-teleportation
  round-trip, qaoa-maxcut Z₂-symmetry, predictive-coder parity
  truth table). predictive-coder-learning gets structural-only
  coverage (its iterative runtime is exercised by
  `test_run_context_updates*.py`); larql-gate-knn-grover behavior
  is already covered by
  `test_regression.py::test_grover_compiles_and_recovers_marked_state`.
  Full suite: 956 passed, 18 skipped (aer-gated + `if_else`
  simulator gap from §5.17).

- [ ] 5.5 **Verifier blind spot — gate targets aren't checked
  against state-description intent.** The teleportation correction
  bug (Z/X/XZ targeting qs[0] instead of qs[2]) was a copy-paste
  error that survived the full 5-stage pipeline because the verifier
  only checks unitarity / branch-completeness / Bell-pair Schmidt
  rank — not which qubit holds Bob's state. The state markdown bodies
  are explicit about qubit ownership ("Bob holds q2"), but the
  verifier doesn't read prose. A cheap heuristic: in
  `q_orca/verifier/quantum.py`, when a transition is annotated with
  Bell-correction semantics (or more generally, when the source
  state's body mentions a specific qubit by index), warn if the
  paired action's gate targets a *different* qubit. Likely false-
  positive-prone — better is to spec out a `target_qubit` annotation
  on Bell-correction states (or an explicit `corrects: q2` field on
  the transition) and check it structurally. Not urgent — the
  teleportation example is now correct — but worth designing before
  another correction-style example lands.
  (Source: 2026-05-01 example library QA, bug 1 root cause.)

- [ ] 5.6 **Verifier blind spot — exhaustive syndrome coverage.**
  Companion to §5.5 and the precondition for §5.1's behavior test.
  Today `feedforward_completeness` checks that every measured bit
  drives *some* correction; it doesn't check that every `2^N`-pattern
  of `N` measured bits has a defined correction path. For the
  bit-flip code with 2 syndrome bits there are 4 patterns and 4
  correction targets (none, q0, q1, q2); the missing (1,1) → q1 case
  was invisible to the verifier. Spec sketch: add a rule
  `syndrome_exhaustiveness` (or extend `feedforward_completeness`
  under a new option) that — when a `list<bit>` field of width N is
  fully populated by mid-circuit measurements — enforces that the
  combined conditional-gate effects cover all `2^N` patterns or are
  explicitly partial (annotated by the user). Pairs naturally with
  the compound-condition parser work in §5.1.
  (Source: 2026-05-01 example library QA, bug 2 root cause.)
  See §5.7 for an analogous "structural property the verifier
  cannot see" gap on the quantum-encoding side.

- [ ] 5.7 **Verifier blind spot — Gram factorization vs. encoding
  entanglement.** A future verifier rule should flag any
  hierarchical-polysemantic encoding whose Gram matches the same-
  angle product-state Gram
  (`gram[i,j] == ∏_k cos((θ_{i,k} − θ_{j,k})/2)`), so the class of
  bug behind `fix-mps-encoding-non-factorizing` (a CNOT-staircase
  encoding with Schmidt rank 2 but a Gram identical to rung 0's
  product-state Gram) is caught at verify time rather than at
  example-library QA time. Spec sketch: add a rule
  `gram_factorization_distinct_from_product_state` (gated on a
  machine declaring an `mps_bond_2_*_encoding` verification rule
  or a sibling marker) that builds the per-call-site product-state
  Gram and asserts at least one off-diagonal entry differs by ≥ 0.05
  in `|gram|²`. Companion to §5.6: both are cases where a structural
  property the user cares about isn't directly observable in the
  AST and has to be derived from running the encoding's contraction
  side-by-side with a reference. Motivating incident:
  `add-mps-concept-encoding` shipped a four-tier example whose
  Gram silently factorized as the rung-0 product-state map; the
  fix is in `openspec/changes/fix-mps-encoding-non-factorizing/`
  (and that change's `design.md` post-mortem section). Gated behind
  a separate proposal once a second concrete example exists where
  the factorization status is non-obvious — out of scope for the
  immediate fix.
  (Source: 2026-05-01 `fix-mps-encoding-non-factorizing` post-mortem.)

The §5.8–§5.15 entries below come from a post-merge self-review of
PR #48 (`fix-mps-encoding-non-factorizing` implementation). They are
not example-library QA findings but the numbering continues §5 to
keep the 2026-05-01 cluster contiguous.

- [x] 5.8 **`evaluate_angle` regression on scientific-notation
  literals.** Severity: HIGH. `q_orca/angle.py:127-164`. The new
  top-level `+`/`-` splitter (`_split_linear_combination`) walks
  character-by-character and treats any non-operator preceding char
  as a license to split. The `e` in `1e-5` is non-operator, so the
  splitter splits `1e-5` into `[1e, -5]` and `evaluate_angle("1e-5")`
  raises `Unrecognized angle expression '1e'` where it returned
  `1e-5` before this commit. Reproducer:
  `evaluate_angle("1e-5*a", {"a": 0.1})` and
  `evaluate_angle("1e-5 + a", ...)` both fail. Fix: in the look-back
  at `angle.py:154`, also exclude `+`/`-` that follow `e`/`E`
  preceded by a digit (treat as exponent sign). No example in the
  repo uses scientific notation today, so this is latent but real;
  add a regression test alongside the fix.
  (Source: 2026-05-01 PR #48 self-review.)
  Added `_is_exponent_marker(text, j)` in `q_orca/angle.py` that
  walks back through digits and at most one `.` to confirm `e`/`E`
  sits on a numeric mantissa, and gated the splitter's split
  decision on it. `1e-5` and `1e-5 + a` now evaluate cleanly;
  `1e5-a` still splits correctly (the `5` before `-` is not an
  exponent marker). Tests in
  `tests/test_parser.py::TestEvaluateAngle::test_scientific_notation_literals`
  (7 cases incl. `1E-5`, `1.5e-5`, `-1e-5`),
  `test_scientific_notation_in_linear_combination` (4 cases),
  and `test_non_exponent_e_still_splits` (a context field literally
  named `e` does not suppress the split). Note: the
  `evaluate_angle("1e-5*a", ...)` reproducer in the original task
  body remains unsupported because `<float>*name` was never a
  recognized form in `evaluate_angle` (only `<int>*name`); that is
  a pre-existing limitation, not the regression — out of scope here.

- [x] 5.9 **Inverse-form `Ry(qs[k], -(a + b))` does not parse end-
  to-end.** Severity: HIGH. The language spec at
  `openspec/changes/fix-mps-encoding-non-factorizing/specs/language/spec.md:64-66`
  explicitly says `Ry(qs[k], -(a + b))` is "equivalently" valid
  alongside `-a - b`. Two parser-side defects block it:
    1. `_ROTATION_GATE_ANGLE_RE` in
       `q_orca/parser/markdown_parser.py:1170-1175` uses `[^)]+` to
       capture the angle, which truncates `-(a+b)` to `-(a+b` at
       the inner `)`.
    2. Even if captured, `_split_linear_combination` does not recurse
       into parens, so `evaluate_angle("-(a + b)", ctx)` raises.
  Reproducer: parsing an effect with `Ry(qs[2], -(b + c))` gives
  parser error `unrecognized angle expression '-(b + c'`. The
  helper's own AST walk handles `-(a+b)` fine, so the asymmetry is
  purely on the parser. Fix: balance parens in the angle regex, and
  have the splitter return `None` (delegate to a paren-stripping
  retry) when the whole text is a parenthesized expression. The
  shipped example sidesteps this by writing `-a - b`/`-b - c` — but
  the spec promises both forms.
  (Source: 2026-05-01 PR #48 self-review.)
  Widened the angle capture in `_ROTATION_GATE_ANGLE_RE` to
  `(?:[^()]|\([^()]*\))+` so a single level of nested parens is
  matched whole rather than truncated at the inner `)`. Added a
  `_strip_matched_outer_parens` helper in `q_orca/angle.py` and
  called it from `evaluate_angle` immediately after sign extraction,
  so `-(a + b)` becomes `sign * evaluate_angle("a + b", ctx)` and
  the existing top-level `+`/`-` splitter handles the inner
  combination. Tests in
  `TestEvaluateAngle::test_parenthesized_expression` (8 cases incl.
  `-(a + b)`, `(a) + (b)`, `(a + b) + c`, `-(pi/4)`) and
  `TestEvaluateAngle::test_unbalanced_or_empty_parens_rejected`
  (3 cases: `(a + b`, `a + b)`, `()`); end-to-end parse pinned by
  `TestParametricTemplateBinding::test_inverse_form_paren_negation_parses_clean`
  and `…_full_inverse_staircase`. Deeper nesting (e.g.
  `-((a + b))`) is still unsupported — no shipped example needs it.

- [x] 5.10 **Test gap — bare-literal sad path uncovered.**
  Severity: MEDIUM. The compiler spec scenario at
  `openspec/changes/fix-mps-encoding-non-factorizing/specs/compiler/spec.md:90-101`
  enumerates four trigger forms for `unrecognized_angle_expression`:
  `a * b`, `sin(a)`, `a^2`, and **`Ry(qs[1], 2.5)`** (bare numeric
  literal with no parameter reference). `tests/test_compiler.py`
  (`TestComputeConceptGramMps`) covers `a * b` and `sin(a)` only —
  bare-literal and `a^2` have no test. Manually verified that
  `Ry(qs[1], 2.5)` does in fact raise with kind
  `unrecognized_angle_expression`, but this is an untested behavior
  the spec explicitly calls out. Fix: add
  `test_unrecognized_angle_expression_bare_literal_raises` and
  `test_unrecognized_angle_expression_power_raises` to
  `TestComputeConceptGramMps`.
  (Source: 2026-05-01 PR #48 self-review.)
  Added both tests in `TestComputeConceptGramMps`. The power test uses
  `a**2` rather than `a^2` because the helper parses angle expressions
  as Python AST and `a^2` becomes `BitXor(Name(a), Constant(2))` while
  `a**2` becomes `BinOp(Pow, …)`; either trips the unsupported-node
  branch with the same `unrecognized_angle_expression` kind, but the
  test pins the more user-likely shape (`**` is exponentiation).

- [x] 5.11 **Test gap — inverse-form linear combination uncovered
  by focused unit test.** Severity: MEDIUM. All happy-path tests
  for cross-coupled angles in `tests/test_compiler.py` use the prep
  form (`prepare_concept`, `Ry(qs[0], a); ...; Ry(qs[2], b + c)`).
  No unit test exercises the inverse form (`Ry(qs[2], -b - c); ...;
  Ry(qs[0], -a)`) with a linear-combination angle. The helper's
  `is_inverse=True` branch with cross-coupled angles is only
  covered transitively via
  `test_examples.py::test_larql_polysemantic_hierarchical_pipeline`.
  Fix: add a focused unit test in `TestComputeConceptGramMps` that
  constructs an inverse-form effect with `-a - b` and asserts the
  Gram matches the inverse of a prep-form Gram on the same angles.
  (Source: 2026-05-01 PR #48 self-review.)
  Added `test_inverse_form_linear_combination_matches_prep_form` in
  `TestComputeConceptGramMps`. It builds two machines on the same three
  angle triples — preparation form `Ry(qs[0], a); …; Ry(qs[1], a + b);
  …; Ry(qs[2], b + c)` versus inverse form `Ry(qs[2], -b - c); …;
  Ry(qs[1], -a - b); …; Ry(qs[0], -a)` — and asserts
  `|gram_inverse| == |gram_prep|` to 1e-12. Pins the helper's
  cross-coupled inverse-form path against silent regressions in
  `_parse_linear_combination` and the contraction path.

- [x] 5.12 **`_parse_linear_combination` rejects `2*-a`.**
  Severity: LOW. `q_orca/compiler/concept_gram_mps.py:147-165` only
  matches `Constant * Name` and `Name * Constant` for `Mult`; the
  AST shape `Constant * UnaryOp(USub, Name)` (i.e., `2*-a`) is
  rejected as "product of two non-constant terms". This is a
  syntactically valid linear combination. Unlikely in practice —
  users would write `-2*a` — but the matching is incomplete. Fix:
  when one operand is `Constant` and the other is a `UnaryOp` over
  a `Name`, multiply the constant into the sign and recurse, or
  permit `walk(other_operand, sign * float(const))`.
  (Source: 2026-05-01 PR #48 self-review.)
  Refactored the Mult branch to extract a `_as_numeric_const` helper
  that recognizes both bare `Constant` and `UnaryOp(USub|UAdd,
  Constant)` shapes — so on top of `2*-a`, the canonical `-2*a` form
  (which is `BinOp(Mult, UnaryOp(USub, Constant(2)), Name)` at the
  AST level and was previously also rejected by the same fall-through)
  now parses cleanly. Either side may carry the constant; if the
  constant lives on the right (`a*-2`) the recursion lands on the
  Name with the negated coefficient. Pinned by
  `test_constant_times_negated_param_accepted`, which feeds both
  shapes via the parser-bypass pattern (the user-facing template
  validator still rejects either form upstream — this is a defense-in-
  depth fix for programmatically-built machines and post-parse
  effect mutation).

- [x] 5.13 **Misleading `_parse_linear_combination` error message
  for all-constant products.** Severity: LOW. Same site as §5.12:
  `2*3` is rejected with `"product of two non-constant terms"` even
  though both terms *are* constants. The intent is to reject
  expressions with no parameter reference, and a separate branch
  already handles bare `Constant`. Fix: tighten the `Mult` fall-
  through message to say "no parameter reference" when both sides
  are constants, or short-circuit the case earlier with a clearer
  diagnostic.
  (Source: 2026-05-01 PR #48 self-review.)
  Folded into the same Mult-branch refactor as §5.12. When both
  operands resolve via `_as_numeric_const`, the helper now raises
  `_NonLinearExpr("product of two numeric constants has no parameter
  reference")` before falling through to the "two non-constant terms"
  case (which only fires when at least one operand is genuinely non-
  numeric). Pinned by
  `test_constant_times_constant_error_mentions_no_parameter`, which
  asserts the new wording lands and the misleading "non-constant"
  phrase no longer appears for the all-constants case.

- [ ] 5.14 **Polysemy column tabulates `0.000` for entries that
  compute as ~`1e-4`.** Severity: LOW.
  `examples/larql-polysemantic-hierarchical.q.orca.md:138-139`
  claims `mango (6) → 0.000` and `papaya (7) → 0.000`. Actual
  computed values are `~0.00012` (rounding to `0.000` at 3-decimal
  display; ASCII heatmap correctly shows blank). Not numerically
  wrong, but a reader running `compute_concept_gram_mps` and seeing
  `9.5e-5` may read the rounded display as misleadingly "exactly
  zero". Fix optional — add a "≈" prefix on near-zero rows or
  document the rounding convention in the surrounding paragraph.
  (Source: 2026-05-01 PR #48 self-review.)

- [x] 5.15 **Documentation/contract polish on
  `MpsGramConfigurationError` and the compiler spec example.**
  Severity: NIT. Two minor doc-vs-code mismatches:
    - `q_orca/compiler/concept_gram_mps.py:66-78`: the
      `MpsGramConfigurationError` class docstring lists only
      `unrecognized_angle_expression` as a possible `kind`. All
      other configuration errors in the module raise without a
      `kind` (correct), but the docstring could note that
      explicitly so callers know to fall through to message
      inspection for non-angle errors.
    - `openspec/changes/fix-mps-encoding-non-factorizing/specs/compiler/spec.md:107-109`
      says "the second and third `qc.ry(` calls receiving the
      *evaluated* linear combination (e.g., `qc.ry(a_value +
      b_value, 1)` rather than a single bound parameter)". The
      actual Qiskit compiler emits a *fully-evaluated* float
      (e.g., `qc.ry(-1.594, 1)`), not the symbolic
      `a_value + b_value` form. Both satisfy the contract, but
      the spec example is misleading.
  (Source: 2026-05-01 PR #48 self-review.)
  Bullet 1 was already addressed by an interim PR
  (`extend-mps-matcher-rz-phases`): the docstring now lists both
  `unrecognized_angle_expression` and `rz_in_inverse_form` and
  explicitly notes that other configuration errors raise without a
  `kind` and require message inspection. Bullet 2: updated the live
  spec at `openspec/specs/language/spec.md:676-682` (the canonical
  copy; the spec was promoted from the change directory into
  `openspec/specs/` when `fix-mps-encoding-non-factorizing` was
  archived). The spec now says the linear combination is "fully
  evaluated to a numeric float at compile time" and uses
  `qc.ry(-0.85, 2)` (verified against the live qiskit compiler output
  for the canonical example) instead of the misleading symbolic
  `qc.ry(a_value + b_value, 1)` form.

- [ ] 5.16 **Inverse-form symmetry breaks when `Rz` enters the
  staircase, requiring the prep form for phase-knob examples.**
  Severity: LOW. The matcher extension shipped on
  `extend-mps-matcher-rz-phases` accepts optional `Rz(qs[k], <expr>)`
  rotations anywhere in the staircase, but the inverse-form
  evaluation pattern used by `larql-polysemantic-hierarchical.q.orca.md`
  (and `larql-animals-hierarchy.q.orca.md`) computes the right
  preparation-form Gram only because the pure-`Ry` staircase keeps
  ``|<0|U_prep U_prep'^†|0>|`` magnitude-equal to
  ``|<0|U_prep^† U_prep'|0>|``. Once `Rz` enters the staircase that
  invariance breaks: the inverse's `Rz` falls before the qubit
  rotation that gives it bite, and the helper would return a
  spuriously-trivial Gram on the phi axis. Examples using `Rz` knobs
  must therefore enumerate `prepare_concept` call sites directly,
  as `examples/larql-animals-interference.q.orca.md` does.

  **Partial fix shipped (`extend-mps-matcher-rz-phases`):** the
  matcher now detects this configuration and raises
  ``MpsGramConfigurationError(kind="rz_in_inverse_form")`` rather
  than silently producing a wrong Gram, so the failure mode is
  loud. The deeper fix — generalize the helper to construct the
  prep-form Gram by symbolically inverting the inverse-form effect
  before contraction — remains open and is module-level scope (~1
  day). Justified mostly if a hand-written `Rz` example needs the
  inverse-form ergonomics; codegen will emit prep form anyway, so
  the loud-error guard is likely sufficient.
  (Source: 2026-05-01 `extend-mps-matcher-rz-phases` PR.)

- [ ] 5.17 **`estimate_resources` raises `TranspilerError` on circuits
  with `if_else` blocks under qiskit ≥ 2.4.** Severity: MEDIUM. Surface:
  `q_orca/compiler/resources.py:42-46` calls `transpile(qc,
  basis_gates=['u3', 'cx'], optimization_level=1)` and a sibling call
  with the Clifford+T basis. Qiskit 2.4.1's `BasisTranslator` rejects
  control-flow ops because no equivalence rule decomposes `if_else`
  into `u3 + cx`. Repro: `estimate_resources` on
  `examples/bit-flip-syndrome.q.orca.md` (or any machine with a
  conditional gate). The bug is silent on qiskit 2.3.x (the local dev
  baseline at the time of `extend-conditional-gate-compound-bits`) but
  surfaces on 2.4.x (CI). Fix shape: catch `TranspilerError` and fall
  back to manual op-walking that descends into each `if_else` block's
  inner `QuantumCircuit` and accumulates `cx` / `t` / `tdg` counts
  there too — the conjunction is classical control flow and the inner
  gate is what the spec wants counted. `gate_count` should keep
  collapsing nested compound conditionals to a single top-level
  `if_else` op (per `extend-conditional-gate-compound-bits`); only
  `cx_count` / `t_count` need the descent. Add regression coverage in
  `tests/test_resource_estimation.py` against a single-cond and a
  compound-cond machine.
  (Source: 2026-05-06 `extend-conditional-gate-compound-bits` PR #62 CI
  fail, https://github.com/jascal/q-orca-lang/actions/runs/25450682232.
  Worked around in PR #62 by switching the new compound-conditional
  resource tests to `count_ops()` directly so they don't pay the
  transpile cost.)

## 6. How to use this file

- [x] 6.1 **Meta**: when an item is fixed, leave the task checked
  rather than deleting it — the archived copy of this change is
  our record. If an item grows beyond "small," spin it out into
  a dedicated OpenSpec change and replace the task body with a
  pointer (e.g. "→ spun out as `add-xyz`").
  Convention-only entry; closed because every implemented item in
  this change followed it (note left alongside each `[x]`, no items
  deleted on completion). Originally numbered §5.1; renumbered to
  §6.1 when the example-library QA findings were added as §5.
