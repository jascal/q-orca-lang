## Context

A `## context` `list<qubit>` field is stored today as a `ContextField` of type `QTypeList(element_type="qubit")` whose `default_value` is the **raw string** `"[q0, q1, q2]"`. There is no per-element struct, and `QTypeQubit.kind` is the type discriminator (`"qubit"`), shared across the type — not a per-element slot. So roles need a genuine new AST home; the research doc's "surface syntax over `QTypeQubit.kind`" is not how the code is shaped.

The verifier already walks the per-qubit gate sequence (`q_orca/verifier/quantum.py` no-cloning + collapse checks, `structural.py` reachability), and the `## noise_model` work already added a `qs[role:R]` selector that is parsed but currently rejected pending this capability. So the machinery to *act on* roles exists; what is missing is a way to *declare* them and a place to store them.

## Goals / Non-Goals

**Goals:**
- Declare a per-qubit role from a closed vocabulary inline in the `## context` default, backward-compatibly (untagged → `data`).
- Three role-driven structural checks that fire automatically, catching the ancilla-reset and syndrome-completeness bug classes statically.
- Make `qs[role:R]` resolvable everywhere (closing the noise-model stub).

**Non-Goals:**
- `coin` / `position` roles and their rules — gated on the unwritten walk-primitives spec; deliberately excluded so the vocabulary doesn't grow ahead of enforcement.
- Role queries in *runtime* guards — verifier-time only for v1 (Open Question 1).
- Role propagation across `invoke:` — erased at the boundary for v1 (Open Question 3).
- `borrowed-ancilla` (Q# clean-vs-borrowed) — a stronger input==output check; deferred (Open Question 2).
- Mermaid role coloring and QASM/Qiskit role annotations — pure cosmetics; out of scope for v1 (may be a tiny follow-up).

## Decisions

### D1 — Closed role vocabulary, `data` default
v1 ships `data | ancilla | syndrome | communication`. `data` is the default for any untagged element, so existing examples are unchanged. `coin`/`position` are reserved names that the parser rejects with `UNKNOWN_QUBIT_ROLE` for now (they enter the vocabulary only when their rules ship), keeping the set honest rather than accepting tags the verifier ignores.
*Alternative considered:* accept `coin`/`position` as no-op tags now — rejected; a tag the verifier silently ignores is worse than a clear "not yet supported".

### D2 — Roles live on the machine, parsed from the qubits default
Add a per-qubit role structure to `QMachineDef` (e.g. `qubit_roles: list[str]`, one entry per qubit in declaration order, or a `{name: role}` map). The parser tokenizes the `list<qubit>` default — splitting `name:role` and expanding `a..b:role` ranges — into `(name, role)` pairs, populating both the existing flat qubit list (names, unchanged) and the new roles. `QTypeQubit` is untouched.
*Alternative considered:* overload `QTypeQubit.kind` into `"qubit:ancilla"` etc. (the doc's sketch) — rejected; `kind` is a fixed discriminator and per-element roles don't belong on a shared type object.

### D3 — Range shorthand `a..bN:role`
`[q0..q5:data, q6..q9:ancilla, q10:syndrome]` expands to the flat per-element list. The range is inclusive; the numeric suffix is incremented (`q0..q5` → `q0,q1,q2,q3,q4,q5`). Purely a parse-time convenience; the AST stores per-element roles.

### D4 — Rule 1: `ancilla_reset` (structural)
For each `ancilla` qubit, walk the per-state gate sequence: it MUST have no gate before its first appearance (starts `|0⟩`) and an explicit `reset(qs[k])` between every pair of mid-circuit measurements on it. Failure → `ANCILLA_NOT_RESET` with the offending state + gate index. This makes the protection the shipped `bit-flip-syndrome` example gets by hand-adding `mid_circuit_coherence` automatic for any `ancilla`-tagged qubit.

### D5 — Rule 2: `syndrome_completeness` with SCC fallback
For each `syndrome` qubit, every cyclic path must contain a `measure(qs[k])`. Until `bounded-loop-annotation` lands there are no explicit loop bodies, so v1 uses the **strongly-connected-component fallback**: every cyclic SCC of the transition graph that the syndrome qubit participates in must contain a measure on it; otherwise `SYNDROME_NOT_MEASURED`. When `[loop …]` annotations land, the check tightens to per-iteration completeness (a one-line swap of the body-identification source).

### D6 — Rule 3: `communication_no_cloning` (escalation)
Extend the existing `check_no_cloning` (`q_orca/verifier/quantum.py`): when the duplicated qubit is tagged `communication`, emit `COMMUNICATION_NO_CLONING_VIOLATION` (error) instead of the generic `NO_CLONING_VIOLATION`, with a fix hint referencing `[send: q -> X]` protocol annotations (the queued protocol-state-annotations spec). A non-communication clone keeps emitting the generic diagnostic — no behavior change for untagged machines.

### D7 — Close the `qs[role:R]` noise selector loop
Modify the noise-model `Noise Target Resolution` rule: `qs[role:R]` now resolves against the declared roles (matching the qubit indices with role `R`) instead of being rejected with "requires qubit-role-types". A role that matches no qubit still warns `NOISE_TARGET_NO_MATCH`. This retires the stub shipped in `add-noise-model-section` and is the concrete, immediate payoff of this change.

### D8 — Verifier-time only; roles erased across `invoke:`
Role queries are a verification-time concept; they do not enter the runtime guard AST (Open Question 1 → verifier-only, the simpler contract). Roles are erased at `invoke:` boundaries for v1 — a child re-declares its own roles (Open Question 3 → stance (a)); coupling roles to the invoke signature is a named follow-up.

## Risks / Trade-offs

- **SCC fallback is coarser than per-iteration** → documented; it can over- or under-approximate vs a real loop body, so the diagnostic says "on every cyclic path" and the rule tightens when bounded-loop lands. Conservative: it only fires when *no* measure exists in the cycle, minimizing false positives.
- **Range parsing ambiguity** (`q0..q5` numeric increment) → restrict ranges to a shared alpha prefix + integer suffix; reject mixed/!numeric ranges with `UNKNOWN_QUBIT_ROLE`-adjacent parse error.
- **Reserved `coin`/`position` rejected now** → may surprise an author who read the research doc; the diagnostic message names them as reserved-but-not-yet-supported.
- **Backward compatibility** → the untagged path must produce byte-identical parse + verify output; pinned by a test on an existing untagged example (`bell-entangler`).

## Migration Plan

Additive + opt-in. New role syntax (untagged = `data`), new verifier rules (fire only on tagged qubits), one MODIFIED noise rule (role selectors now resolve — strictly more permissive). Shipped ancilla-using examples gain tags in the same change. Rollback = revert; untagged machines are the pre-change behavior.

## Open Questions

1. **Deprecation→error escalation** — should an untagged qubit *used as* an ancilla eventually be an error? v1 does nothing (you must opt in by tagging); a future warning ("used as ancilla but not tagged") then error is a possible follow-up, not in scope.
2. **`role(qs[k])` / `qs[i:role=R]` in `## invariants`** — exposing roles to invariant expressions is desirable (research test 5) but expands the invariant grammar; v1 ships the declaration + the three structural rules + selector resolution, and leaves the invariant role-query to a follow-up unless it proves trivial during implementation.
