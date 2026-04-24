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

- [ ] 1.2 Replace the fragile `"requires at least" in e` string
  match in the `_looks_like_gate_call` guard with a structural
  signal (either a shared `ARITY_ERROR_MARKER` constant or an
  explicit sentinel returned by `_parse_gate_from_effect`). The
  current test pins the wording; a future rephrase silently
  re-enables the double-fire regression.
  (Source: Claude code review on PR #17, concern 1.)

- [ ] 1.3 Make CSWAP arity errors symmetric with MCX/MCZ.
  `MCX(qs[0], qs[1])` raises a structured "needs ≥3 args" error,
  but `CSWAP(qs[0], qs[1])` falls through to the generic "looks
  like a gate call" warning. Add a CSWAP-specific arity branch
  next to the MCX/MCZ one (~6 lines).
  (Source: Claude code review on PR #17, concern 2.)

- [ ] 1.4 Build the known-gate list in the unknown-gate warning
  message from `KNOWN_UNITARY_GATES` at module load, instead of
  the hardcoded inline string in
  `q_orca/parser/markdown_parser.py`. The inline list is a second
  source of truth that drifts as gates are added (extend-gate-set
  work will add more).
  (Source: Claude code review on PR #17, concern 4.)

- [ ] 1.5 Flag "extra non-`qs` slot without `: type`" in
  `_parse_signature`. Today `(qs, c) -> qs` silently returns a
  zero-parameter signature because no slot contains `:`; the
  transition `foo(0)` then errors with the unhelpful "not
  parametric" message rather than pointing at the missing
  `: int`. Adding an error (or warning) in `_parse_signature`
  surfaces the intent mismatch at parse time.
  (Source: Claude code review on PR #26, suggestion 1.)

- [ ] 1.6 Converge bare-name and call-form typo detection for
  parametric actions. Today an undeclared bare-name reference
  (`query_concep`) slips through silently while the call-form
  typo (`query_concep(0)`) is reported. The asymmetry was a
  deliberate scoping call on PR #26 but should be revisited now
  that section 4–7 have shipped.
  (Source: Claude code review on PR #26, suggestion 2.)

- [ ] 1.7 Replace naive `args_str.split(",")` in
  `_resolve_transition_actions` with a paren-aware
  `_split_top_level_commas` helper. Today `_evaluate_angle` only
  accepts single-arg expressions so there's no live bug, but
  `mix(atan2(a, b), 0)` will be mis-split into three args the
  moment a multi-arg angle expression lands.
  (Source: Claude code review on PR #26, suggestion 3.)

- [ ] 1.8 Drop `re.DOTALL` from the call-form regex in
  `_resolve_transition_actions` (or document why it's needed).
  Markdown table cells shouldn't contain newlines, so the flag
  buys nothing and permits weird inputs.
  (Source: Claude code review on PR #26, suggestion 4.)

- [ ] 1.9 Allow underscores in the `_looks_like_gate_call` regex
  (`[A-Za-z_][A-Za-z0-9_]*` instead of `[A-Za-z][A-Za-z0-9]*`),
  so typos like `U_3(qs[0], ...)` for `U3` are still flagged.
  Unlikely in practice but essentially free.
  (Source: Claude code review on PR #17, concern 3.)

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

- [ ] 2.2 Add a regression test pinning that arity-zero calls to
  a parametric action (e.g. a bare-name reference to an action
  declared `query_concept(c: int)`) are rejected upstream. The
  verifier's `check_unitarity` assumes this today — parametric
  actions are skipped in the per-action loop and only visited via
  `bound_arguments`, so a bare-name slip would silently leave the
  gate unchecked.
  (Source: Claude code review on PR #27, concern 4.)

- [ ] 2.3 Add a parametric-specific `ORPHAN_ACTION` test so
  §6.4 behavior (orphan parametric actions still trigger the
  error without firing expansion-time checks) is pinned by a
  dedicated test rather than only implicitly covered by
  `test_bound_range_clean_across_call_sites`.
  (Source: Claude code review on PR #27, concern 5.)

- [ ] 2.4 Add a declarative opt-out path for `SUPERPOSITION_LEAK`
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

## 3. Compiler

- [ ] 3.1 Tighten `_SUBSCRIPT_RE` in
  `q_orca/compiler/parametric.py` to `qs\[` (so int-param
  substitution only happens inside `qs[...]` subscripts), or
  update the docstring so the broader behavior is explicit.
  Today the regex matches any `word[...]` subscript, which is
  wider than the "inside `qs[...]` slots" claim in the docstring.
  (Source: Claude code review on PR #27, concern 2.)

- [ ] 3.2 Add a comment on `_ROTATION_GATE_ANGLE_RE` noting that
  it only accepts 1–2 qubit slots before the angle, so future
  multi-controlled rotations (e.g. hypothetical
  `MCRx(qs[0], qs[1], qs[2], theta)`) must either extend the
  regex or land with an explicit template-time validation path.
  (Source: Claude code review on PR #27, concern 3.)

- [ ] 3.3 Fix the `_format_angle_literal` docstring — `repr(float)`
  does use scientific notation below ~1e-4 (`repr(1e-10)` →
  `'1e-10'`), so the "avoiding scientific notation" claim is
  slightly misleading even if fine for the angle magnitudes
  rotation gates see in practice.
  (Source: Claude code review on PR #27, nit 1.)

- [ ] 3.4 Drop the redundant `list(bound_arguments)` copy in
  `expand_action_call` when the caller already passes a list.
  Either narrow the type hint to `list[BoundArg]`, or only
  materialize when necessary. Minor.
  (Source: Claude code review on PR #27, nit 2.)

- [ ] 3.5 Reference: the verifier→compiler coupling introduced in
  PR #27 (importing `_parse_effect_string` from
  `q_orca/compiler/qiskit.py` into `q_orca/verifier/quantum.py`)
  is subsumed by the open `consolidate-gate-parser` OpenSpec
  change, which promotes the effect-string parser to a shared
  module. No separate backlog item needed — tracked there.
  (Source: Claude code review on PR #27, concern 1.)

## 4. How to use this file

- [ ] 4.1 **Meta**: when an item is fixed, leave the task checked
  rather than deleting it — the archived copy of this change is
  our record. If an item grows beyond "small," spin it out into
  a dedicated OpenSpec change and replace the task body with a
  pointer (e.g. "→ spun out as `add-xyz`").
