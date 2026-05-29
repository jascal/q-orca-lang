# Spec: Qubit Role Types in `## context`

**Status:** Draft
**Date:** 2026-05-08
**Priority:** High

> Generated: 2026-05-08 — weekly feature spec session

---

## Summary

Promote the `qubits` register from an opaque `list<qubit>` into a
typed list whose elements carry a *role* tag drawn from a closed
vocabulary: `data`, `ancilla`, `syndrome`, `communication`, `coin`,
`position`. The role is declared inline in the `## context` default
list and feeds five new structural-verifier checks that today have
no expressible form: ancillas must be reset to `|0⟩` between
distinct mid-circuit measurements; syndromes must be measured in
every observed loop iteration; communication qubits trigger
no-cloning checks at protocol boundaries; coin and position qubits
unlock walk-specific invariants. The annotation is opt-in — a
register without role tags continues to verify under today's rules
unchanged. Role tags are surface syntax over an existing AST field
(`QTypeQubit.kind`) and slot directly into the verifier's existing
per-register dispatch, so the implementation surface area is small
relative to the bug classes it catches.

---

## Motivation

**The user problem.** q-orca's structural verifier is its core
selling point — it catches non-unitarity, no-cloning violations,
and feedforward completeness errors before the user ever runs a
shot. But today every qubit in `qubits: list<qubit>` is the same
thing to the verifier. There is no way to say "this qubit is
*scratch*" or "this qubit is *the syndrome ancilla*", which means
two important bug classes go uncaught:

1. **Ancilla recycling without reset.** The shipped
   `bit-flip-syndrome.q.orca.md` example uses qubits `q3` and `q4`
   as syndrome ancillas. The verifier's mid-circuit-coherence rule
   currently catches *one* form of misuse — measuring an ancilla
   then re-using it without a reset — but only when the user
   manually adds a `mid_circuit_coherence` rule under
   `## verification rules`. There is no way to say "q3 and q4 are
   *categorically* ancilla, so the check is mandatory and applies
   automatically." The shipped example does include the rule by
   hand, but every author who omits the rule loses the protection.

2. **Unconverged syndromes.** A bit-flip code with three rounds of
   syndrome extraction must measure the syndrome ancilla in every
   round. Today there is no rule that catches a third-round
   ancilla that is *prepared but never measured* before the round
   ends — the user only finds out by inspecting QASM output or by
   getting wrong corrections. The just-merged
   `extend-conditional-gate-compound-bits` (PR #62) found a
   silent quantum-physics bug that involved exactly this kind of
   misuse going undetected.

The deeper issue is that the verifier already has the *machinery*
to check these things — `q_orca/verifier/quantum.py:check_no_cloning`
and `quantum.py:307+` walk the gate sequence per qubit — but no
way to *target* the check at the qubits where it matters. The
present spec gives the verifier a way to know, structurally, what
each qubit is for.

**The current workaround.** Authors either (a) hand-write a
verification rule per machine, which the v0.4 coverage roadmap
notes is fragile; or (b) accept that some bug classes are caught
only by the example library QA pass that landed as
`tech-debt-backlog §5` after the fact. Shipping QA-after-the-fact
as a substitute for static checking is exactly the failure mode
the verifier exists to prevent.

**Why now.** Three forces converge:

- The just-merged `add-hea-tier-ordering-invariant` (PR #57)
  established the precedent that *some* invariants are mandatory
  and structural rather than user-declared. Role tags follow the
  same shape: declared once in `## context`, enforced everywhere.
- The in-flight `extend-conditional-gate-compound-bits` proposal
  promotes the bit-flip syndrome example to a first-class
  verification target. Its motivation explicitly cites the silent
  bug that role tags would have caught.
- The coverage roadmap §4.1 names role tags as the lowest-cost
  enabler of the next wave of canonical-algorithm coverage —
  error correction (#2.5), QKD (#2.4), and quantum walks (#2.6)
  all need at least one role beyond `data`.

KB grounding: Q# (Svore et al., arXiv `1803.00652`) was an early
language to formally distinguish *clean ancilla* (initialized to
`|0⟩` and reset on release) from *borrowed ancilla* (returned in an
arbitrary state); Communicating Quantum Processes (Gay & Nagarajan,
`quant-ph/0409119`, indexed in the q-orca-kb under
`q-orca-physics/quantum-process-algebra`) defines a type system in
which "each qubit is owned by a unique process within a system" —
the natural quantum analogue of role-tagged registers. Tannu &
Qureshi's *Not All Qubits Are Created Equal* (ASPLOS 2019, cited in
arXiv `2003.05841`, also indexed) makes the case at the
NISQ-architecture level that distinguishing qubit kinds is a
correctness *and* performance win.

---

## Proposed Syntax / API

### Inline role tag in the default list

```markdown
## context

| Field  | Type                | Default                                          |
|--------|---------------------|--------------------------------------------------|
| qubits | list<qubit>         | [q0:data, q1:data, q2:data, q3:ancilla, q4:ancilla] |
| bits   | list<bit>           | [b0, b1]                                         |
```

The role tag is a colon-delimited suffix on each element of the
default list. Elements without a tag inherit the default role
`data` (so existing examples parse unchanged). The tag is a
single keyword from the closed vocabulary:

| Role            | Semantics                                                                |
|-----------------|--------------------------------------------------------------------------|
| `data`          | Algorithmic payload. No special invariants. Default.                     |
| `ancilla`       | Scratch space; must be `|0⟩` at first use and reset before each reuse.   |
| `syndrome`      | Measured every cycle of any `[loop …]` it lives inside (§4.3 spec).      |
| `communication` | Subject to no-cloning at `[send: q -> X]` boundaries (§4.4 spec).        |
| `coin`          | Quantum-walk coin register; unitary coin operator required (§4.5 spec).  |
| `position`      | Quantum-walk position register; bounded-walk-space invariant.            |

### Multi-register shorthand

Authors with many qubits of the same role can group them with a
range syntax:

```markdown
| qubits | list<qubit> | [q0..q5:data, q6..q9:ancilla, q10:syndrome] |
```

The range is inclusive on both ends and parses to the same flat
list as the single-element form. This is a pure surface
convenience; the AST stores per-element roles.

### Role queries in guards and invariants

The role of a register element is queryable from guard predicates
and `## invariants` expressions:

```markdown
## invariants
- role(qs[3]) == ancilla
- entanglement(qs[i:role=data], qs[j:role=ancilla]) = False
```

The slice form `qs[i:role=R]` is a filtered iterator over indices
whose role is `R`, useful in invariants that quantify over a
role-class.

### CLI reporting

```bash
q-orca verify examples/bit-flip-syndrome.q.orca.md
# emits, alongside the existing checks:
# ✓ ancilla_reset[q3]: q3 reset to |0⟩ before each mid-circuit measurement
# ✓ ancilla_reset[q4]: q4 reset to |0⟩ before each mid-circuit measurement
# ✓ syndrome_completeness[q3]: q3 measured on every observed transition path
# ✓ syndrome_completeness[q4]: q4 measured on every observed transition path
```

---

## Implementation Sketch

**Parser** (`q_orca/parser/markdown_parser.py`,
`_parse_context_table` at line 447, ~60 LOC).
Extend the default-list tokenizer for `list<qubit>` types to
recognize the `name:role` and `nameA..nameZ:role` patterns. Reject
unknown role keywords with a new diagnostic
`UNKNOWN_QUBIT_ROLE`. The output is the existing
`ContextField.payload: list[ContextField]` already defined in
`q_orca/ast.py:85`, with each child `ContextField.kind` extended
from `"qubit"` to a tagged union (`"qubit:data"`,
`"qubit:ancilla"`, …). The change is backward-compatible because
`"qubit"` continues to mean `"qubit:data"`.

**AST** (`q_orca/ast.py`, ~20 LOC).
Add a literal type alias `QubitRole = Literal["data", "ancilla",
"syndrome", "communication", "coin", "position"]` and a `role:
QubitRole = "data"` field on whichever dataclass currently holds
per-element default information (the parser already builds this
list; the field is added to the per-element struct rather than to
`ContextField` itself). No breaking AST change for existing
machines.

**Verifier — five new rules**
(`q_orca/verifier/structural.py` for ancilla / syndrome lifecycle,
`q_orca/verifier/quantum.py` for no-cloning extension, ~250 LOC
total):

1. **`ancilla_reset`** — for every qubit tagged `ancilla`, walk
   the per-state gate sequence; the qubit MUST be (a) initially
   `|0⟩` (no gate before its first appearance), and (b) preceded
   by an explicit `reset(qs[k])` between every pair of
   mid-circuit measurements on it. Failure raises
   `ANCILLA_NOT_RESET` with the offending state and gate index.

2. **`syndrome_completeness`** — for every qubit tagged
   `syndrome`, every transition path that enters a `[loop …]`
   body must contain at least one `measure(qs[k])` action. The
   check piggybacks on the loop-annotation work in the queued
   `spec-bounded-loop-annotation.md`; if loop annotations are not
   yet in the parse, the check degrades gracefully to
   "every cyclic SCC must contain a measure on the syndrome".

3. **`communication_no_cloning`** — extends the existing
   `check_no_cloning` (`q_orca/verifier/quantum.py:171`) to flag
   a *stronger* error when the duplicated qubit is tagged
   `communication`: the diagnostic becomes
   `COMMUNICATION_NO_CLONING_VIOLATION` and the suggested fix
   message references the protocol-state-annotation spec.

4. **`coin_unitary`** — for every qubit tagged `coin`, the
   coin-flip action applied to it must be a 2×2 unitary on the
   coin space alone (no entanglement with `position` qubits in
   the coin step). Implemented as a dimensionality check on the
   gate sequence between consecutive `shift` actions.

5. **`position_bounded`** — for every qubit-list tagged
   `position`, the declared `walk_space` context field (added by
   §4.5 of the coverage roadmap) bounds the reachable walker
   positions. If the position register has fewer qubits than
   `ceil(log2(walk_space))`, raise `POSITION_REGISTER_TOO_SMALL`.

   (Rules 4 and 5 are gated on the §4.5 walk-primitives spec
   landing; they are listed here to fix the role-tag vocabulary
   in one place rather than letting it grow piecemeal.)

**Resource estimator**
(`q_orca/verifier/resources.py`, ~30 LOC).
Break out per-role gate counts so the existing `gate_count`,
`cx_count`, `t_count` outputs can be reported as
`gate_count(role=ancilla)` etc. when invariants reference a
role. The compiler-side resource pass already groups by qubit;
this is a re-bucket, not a re-walk.

**Compiler** (`q_orca/compiler/qasm.py`, `q_orca/compiler/qiskit.py`,
~20 LOC each).
Emit role tags as QASM 3.0 stretch annotations
(`@role data` / `@role ancilla`) on the qubit declaration. Qiskit
backend stores roles in `QuantumRegister.metadata` so downstream
optimization passes (resource-estimation, transpiler) can use
them. No semantic change to compiled programs — pure
documentation flow.

**Mermaid renderer** (`q_orca/compiler/mermaid.py`, ~15 LOC).
Color qubit nodes by role in the per-state register diagram:
`data` neutral, `ancilla` dashed, `syndrome` highlighted. Pure
visual.

**Total LOC budget:** ~415 LOC across 6 files, plus tests.

**Migration:** the four existing examples that use ancilla qubits
(`bit-flip-syndrome.q.orca.md`,
`quantum-teleportation.q.orca.md`, `deutsch-jozsa.q.orca.md`,
plus the `vqe-heisenberg.q.orca.md` parameter qubits) gain
explicit role tags as part of the same change. This is the
canonical "use the new feature in shipped examples" pass.

---

## Test Cases

1. **Backward compatibility — untagged register parses unchanged.**
   `bell-entangler.q.orca.md` declares `[q0, q1]` with no role
   tags; the verifier MUST emit the same passing report it does
   today, with all qubits inferred as `role=data`.

2. **Ancilla reset enforcement.**
   A test machine with `[q0:data, q1:ancilla]`, two consecutive
   mid-circuit measurements on `q1`, and *no* reset between them
   MUST fail with `ANCILLA_NOT_RESET` pointing at the second
   measure. Adding a `reset(qs[1])` between the measures MUST
   make it pass.

3. **Syndrome completeness across a loop body.**
   A two-iteration syndrome-extraction state machine where the
   second iteration prepares but never measures the syndrome
   ancilla MUST fail with `SYNDROME_NOT_MEASURED` at the
   loop-body-end state. (Requires the bounded-loop annotation;
   if absent, the check uses the SCC fallback and produces the
   same error.)

4. **No-cloning escalation for communication qubits.**
   The cloning attempt that today produces a generic
   `NO_CLONING_VIOLATION` MUST instead produce
   `COMMUNICATION_NO_CLONING_VIOLATION` when the duplicated qubit
   is tagged `communication`, with a fix suggestion pointing at
   `[send: q -> X]` annotations.

5. **Role-filtered invariant.**
   An invariant `entanglement(qs[i:role=data], qs[j:role=ancilla])
   = False` MUST evaluate over every `(i, j)` pair where the
   role filter holds and pass only if entanglement is absent for
   every such pair at every named state.

---

## Dependencies

- Sequences cleanly with the in-flight
  `extend-conditional-gate-compound-bits` change — that change
  fixes the *syndrome → correction* dispatch for compound bits;
  this change makes "is this qubit really a syndrome?" a
  declarable fact. The two compose: with both landed, a future
  bit-flip-syndrome regression like the one that motivated PR #62
  fails verification rather than producing wrong quantum results.
- Pairs with the queued `spec-bounded-loop-annotation.md`. The
  `syndrome_completeness` rule degrades gracefully if loops are
  not yet annotated; once `[loop N]` lands, the check tightens
  to per-iteration completeness.
- Unblocks examples §2.5 (3-qubit bit-flip code as a first-class
  example with verified ancilla lifecycle) and §2.6 (quantum walk
  on a line with declared `coin` and `position` roles) from the
  v0.4 coverage roadmap.
- Independent of `add-parameterized-invoke` and
  `add-runtime-state-assertions` — can ship in any order
  relative to those.

---

## Open Questions

1. **Should `role` be queryable in *runtime* guards or only at
   verification time?** Today guards run in the Python runtime,
   and a guard like `if role(qs[k]) == ancilla:` would force
   role information to survive into the runtime AST. The
   alternative is to evaluate role queries entirely at
   verification time and forbid them in runtime guards. Leaning
   toward the verifier-only stance — it's the simpler
   contract — but a few candidate guards in QKD-style protocols
   (`if role(qs[k]) == communication: send_qubit_to(Bob)`) would
   be cleaner with runtime support.

2. **Is `borrowed-ancilla` worth a seventh role?** Q# distinguishes
   *clean* and *borrowed* ancillas. The clean version is what
   `ancilla` here means. Borrowed ancillas (returned in an
   arbitrary state) require an "input state matches output state"
   check that is much stronger than the reset rule and probably
   needs its own follow-up spec. Recommend deferring; the role
   vocabulary is closed in this version and a future spec can
   extend it.

3. **Do role tags carry through `invoke:` boundaries?** Once
   `add-parameterized-invoke` lands, a parent passing a list of
   qubits into a child needs a story for what happens to the
   roles. Two stances: (a) roles are erased at the boundary and
   the child re-declares them; (b) roles are part of the
   child's argument signature and the parent's roles must
   match. The latter is stronger but couples this spec to
   `add-parameterized-invoke`. Recommend (a) for v1, with a
   follow-up `tech-debt-backlog` item to revisit once invoke
   lands.

4. **Should the verifier upgrade *deprecation warnings* into
   errors after one release?** Today `bit-flip-syndrome.q.orca.md`
   passes without role tags. Once this lands, the example file
   will be migrated, but third-party machines on the public
   examples wiki will lag. Proposal: emit a deprecation warning
   for one minor release ("`q3` is used as ancilla but not
   tagged — will be required in v0.10") then escalate to error.
