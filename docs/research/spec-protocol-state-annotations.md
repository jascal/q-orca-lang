# Spec: Protocol State Annotations `[send]` / `[receive]` / `[classical]`

**Status:** Draft
**Date:** 2026-05-08
**Priority:** Medium

> Generated: 2026-05-08 — weekly feature spec session

---

## Summary

Promote the `[send: q -> Recipient]`, `[receive: q <- Sender]`,
and `[classical]` state annotations from grammar reservations
(named in the in-flight `add-runtime-state-assertions` proposal as
queued slots) to fully implemented state-header annotations with
verifier and compiler support. The annotations let a single q-orca
machine express *protocol* semantics — qubits leaving the local
register, qubits entering it, and points where all qubits have
collapsed and only classical bits remain — without leaving the
state-machine model. When two paired machines are loaded together
(via the in-flight `add-parameterized-invoke` machinery), the
verifier checks cross-machine consistency: every `[send]` on one
side must have a matching `[receive]` on the other, with compatible
qubit-role declarations. Without protocol annotations, BB84/QKD,
superdense coding, and any multi-party protocol require either
hand-written Python glue between machines or a single monolithic
machine that cannot represent the no-cloning boundary the protocol
relies on.

---

## Motivation

**The user problem.** q-orca's state-machine model assumes that
the qubit register is a closed, locally-owned object: it is
initialized, evolves under unitary actions, and is eventually
measured. This model has no vocabulary for the most common
protocol shape in quantum information theory — a qubit physically
*leaves* the local register and arrives in someone else's. The
two existing examples that come closest both pretend the protocol
is local:

1. **`quantum-teleportation.q.orca.md`** holds Alice's two qubits
   and Bob's one qubit in the same `qubits` list, and the
   "transmission" is just a contiguous gate sequence acting on
   `qs[0..2]`. There is no point in the machine where the
   verifier could enforce that, after the Bell-pair-distribution
   step, Alice cannot apply a gate to Bob's qubit. The
   no-cloning theorem is honored only because the author was
   careful — there is no structural check.

2. **A hypothetical `bb84-qkd.q.orca.md`** would have the same
   problem at higher stakes: BB84's security argument *is* that
   Eve cannot copy a qubit in transit, and that argument lives
   precisely at the `[send]` boundary. Today there is no way to
   place that boundary in the state machine.

The deeper structural issue is that q-orca has good vocabulary
for *intra-machine* boundaries (mid-circuit measurement, classical
feedforward, entanglement claims) but none for *inter-machine*
boundaries. The just-merged
`add-classical-context-updates` and the in-flight
`add-parameterized-invoke` proposals together open the door for
multi-machine composition; protocol state annotations are the
language layer that makes the composition checkable.

**The current workaround.** Authors write a single machine that
holds *all* parties' qubits, ignore the locality boundary, and
write a comment `// Eve cannot intercept here` next to the
relevant gate. This is the same pattern that made formal
distributed-system specifications obsolete in classical
computing — the comment is not enforceable.

**Why now.** Three forces converge in this release window:

- The in-flight `add-parameterized-invoke` change introduces the
  AST-level concept of a *child machine* with declared arguments
  and returns. It does not, however, provide a way to express
  *qubit transfer* between parent and child — the calling
  convention as proposed is value-passing only. Protocol state
  annotations are the missing primitive that lets one machine
  hand a qubit to another with a verifiable no-cloning step.
- The `add-runtime-state-assertions` proposal explicitly reserves
  `[send]` and `[receive]` in its grammar enumeration for state
  annotations, alongside `[initial]`, `[final]`, `[loop …]`, and
  `[assert: …]`. The grammar slot is already cut; this spec
  fills it in.
- The v0.4 coverage roadmap names the QKD-eavesdropping demo
  (`demos/qkd_protocol/`, §3.1) as the flagship multi-machine
  composition demonstration. Without `[send]` / `[receive]`,
  the demo cannot express the eavesdropping vector physics-correctly
  — Eve's *interception* of Alice's qubit *is* a `[receive]`
  followed by a `[send]` with a 25%-error-introduction step in
  between, and there is no other primitive that captures it.

KB grounding: Communicating Quantum Processes (Gay & Nagarajan,
`quant-ph/0409119`) is the foundational work on adding
quantum-channel send/receive primitives to a process algebra,
with a type system that "guarantees that each qubit is owned by
a unique process within a system" — directly analogous to what
the verifier should enforce here. Jorrand & Lalire's QPAlg
(`quant-ph/0312067`, indexed in the q-orca-kb under
`q-orca-physics/quantum-process-algebra`) defines the operational
semantics for quantum communication via CCS-style send/receive.
The qACP axiomatization (`1311.2960`, also indexed) verifies BB84
formally using exactly these primitives. The polysemantic
research literature already drafted in
`docs/research/proposal-larql-q-orca-polysemantic-pipeline.md`
also implies multi-machine composition as a longer-term need;
protocol annotations are the smallest sufficient primitive for it.

---

## Proposed Syntax / API

### `[send: q -> Target]`

```markdown
## state |alice_transmit> [send: qs[0] -> Bob]

> Alice transmits her encoded qubit to Bob over the quantum channel.
> After this state, qs[0] is no longer in Alice's local register.
```

The annotation argument is `<qubit-slice> -> <target-machine-name>`.
The qubit slice may be a single index (`qs[0]`), a range
(`qs[0..2]`), or a context-field reference whose type is
`list<qubit>` (`alice_share`). The target name is the unqualified
identifier of another machine in the same multi-machine file or in
the same composition group.

**Effect on the local register.** After a `[send]` state, the
named qubits are removed from the local `qubits` list for the
remainder of the machine. Any subsequent action that references
them is a verifier error (`SENT_QUBIT_REFERENCED`).

### `[receive: q <- Source]`

```markdown
## state |bob_receive> [receive: qs[2] <- Alice]

> Bob's communication qubit arrives from Alice.
> qs[2] joins Bob's local register at this state.
```

Symmetric to `[send]`. The named qubit must be declared with
role `communication` in the receiving machine's `## context`
(see `spec-qubit-role-types.md`); the verifier rejects a
`[receive]` onto a `data` qubit with `RECEIVE_REQUIRES_COMMUNICATION_ROLE`.

**Effect on the local register.** The named qubit becomes
available for actions on transitions out of the `[receive]`
state. The qubit's quantum state is opaque to the receiving
machine until measured — no claim about its preparation can be
verified locally.

### `[classical]`

```markdown
## state |sift>     [classical]
## state |abort>    [final, classical]
```

Pure annotation — declares that, at this state, all qubits in the
local register have been measured, so quantum-coherence checks
trivially pass and only classical-context invariants apply. This
is mostly useful as a hint to the verifier (skip Stage 4b on this
state) and to the Mermaid renderer (color the node as classical).

`[classical]` composes with `[final]` to mean "the machine ends in
a classical-bit-only state" — common in protocols where the
deliverable is a sifted key bitstring rather than a quantum state.

### Cross-machine pairing rule

In a multi-machine source file (or a composition group passed to
`q-orca verify --compose alice.q.orca.md bob.q.orca.md`), every
`[send: q -> Bob]` annotation in machine `Alice` MUST have a
corresponding `[receive: q <- Alice]` in machine `Bob`. The
pairing is by *position in the composition execution order*, not
by qubit name — Alice's `qs[0]` need not equal Bob's `qs[2]` (and
typically does not, since the receivers re-bind the incoming
qubit into their own local register).

The verifier emits `UNPAIRED_SEND` (Alice sends but Bob does not
receive), `UNPAIRED_RECEIVE` (Bob receives but Alice does not
send), and `PROTOCOL_ORDERING_VIOLATION` (the send/receive pairs
exist but are not in a consistent global order — e.g., a deadlock
where Alice waits to receive what Bob has not yet sent).

### CLI

```bash
q-orca verify alice-bb84.q.orca.md
# Single-machine verify: [send] / [receive] checked locally
# but cross-machine pairing skipped with INFO message.

q-orca verify --compose alice-bb84.q.orca.md bob-bb84.q.orca.md
# Both machines parsed; cross-machine pairing checked.
# Reports per-pair: ✓ alice/transmit_q0 ↔ bob/receive_q0
```

---

## Implementation Sketch

**Parser** (`q_orca/parser/markdown_parser.py`,
`_parse_state_heading` at line 475, ~80 LOC).
Extend the state-header annotation grammar to recognize three new
annotation kinds. The annotation parser already exists for
`[initial]` and `[final]`; this is a third dispatch arm. Add
sub-parsers for the `qs[…] -> Name` and `qs[…] <- Name` forms.
The parser produces three new optional fields on `QStateDef`
(`q_orca/ast.py:98`):

```python
@dataclass
class QStateDef:
    ...
    send: Optional[QSendAnnotation] = None
    receive: Optional[QReceiveAnnotation] = None
    is_classical: bool = False
```

**AST** (`q_orca/ast.py`, ~30 LOC).
New dataclasses `QSendAnnotation(qubits: list[int], target: str)`
and `QReceiveAnnotation(qubits: list[int], source: str)`. The
qubit-slice resolver reuses the existing helper
`_split_top_level_commas` and the qubit-index parser already used
for transition arguments. New `QMachineDef.protocol_endpoints`
that pre-aggregates send and receive states for fast cross-machine
lookup.

**Verifier — local checks**
(`q_orca/verifier/structural.py`, ~120 LOC):

1. **`sent_qubit_not_referenced`** — after a `[send]` state, walk
   every transition path forward; any action that references the
   sent qubit is a `SENT_QUBIT_REFERENCED` error. Implemented as
   a forward dataflow on the state graph.

2. **`receive_role_match`** — every `[receive]` annotation MUST
   target a context qubit whose declared role is `communication`
   (per `spec-qubit-role-types.md`). If role tags are not yet
   present in the codebase, this check soft-fails with
   `RECEIVE_ROLE_NOT_DECLARED` warning.

3. **`classical_means_no_quantum`** — at any `[classical]`
   state, the verifier must be able to prove (via the existing
   coherence dataflow) that every qubit has been measured on
   every transition path leading to it. If not, raise
   `CLASSICAL_STATE_HAS_LIVE_QUBITS`.

**Verifier — cross-machine composition checker**
(`q_orca/verifier/composition.py` — new file, ~150 LOC).
A dedicated module invoked only when `--compose` is passed (or
when `add-parameterized-invoke` resolves a multi-machine load).
Builds a global send/receive graph keyed by `(machine_name,
endpoint_name)`, then:

1. Collect all `[send]` annotations across all loaded machines.
2. Collect all `[receive]` annotations.
3. For each `[send: q -> Bob]` in `Alice`, find the unique
   `[receive: r <- Alice]` in `Bob` whose declared qubit slice
   width matches the sent slice width; pair them.
4. Report unpaired sends/receives.
5. Build a global send/receive ordering graph; report cycles
   (deadlock) as `PROTOCOL_ORDERING_VIOLATION`.

**Compiler** (`q_orca/compiler/qasm.py`,
`q_orca/compiler/qiskit.py`, ~40 LOC each).
QASM emits `[send]` as a comment `// transmit qs[0] -> Bob` (no
QASM 3.0 primitive captures cross-process qubit transfer; OpenQASM
extensions in DistributedQASM-style work are still draft). Qiskit
emits a custom `Instruction` subclass `Transmit(target_machine)`
that the runtime can intercept for distributed execution. For a
single-machine compose-target (the common case where multiple
logical machines compile to one physical circuit running in
shared memory), `[send]` / `[receive]` collapse to identity gates
with metadata.

**Mermaid renderer** (`q_orca/compiler/mermaid.py`, ~30 LOC).
Color `[send]` states in red with an outgoing arrow labeled with
the target machine; color `[receive]` states in green with an
incoming arrow; color `[classical]` states in gray. In compose
mode, draw cross-machine arrows linking paired endpoints.

**CLI** (`q_orca/cli.py`, ~25 LOC).
Add `--compose` flag to `q-orca verify` and `q-orca compile`,
accepting a list of `.q.orca.md` paths. The flag triggers the
composition checker and, on success, the multi-machine code
emission. (For v1, code emission compiles each machine
independently and emits a glue Python harness; the
distributed-execution backend is parked for a future change.)

**Total LOC budget:** ~475 LOC across 7 files, plus tests and
two new examples (`bb84-qkd-alice.q.orca.md` and
`bb84-qkd-bob.q.orca.md`).

---

## Test Cases

1. **Local `[send]` lifecycle.**
   A single-machine test with `[send: qs[0] -> Bob]` followed by
   any action referencing `qs[0]` MUST fail with
   `SENT_QUBIT_REFERENCED`. Removing the offending action MUST
   make it pass.

2. **`[receive]` on a `data` qubit fails.**
   A test machine that declares `[q0:data]` and annotates a
   state with `[receive: qs[0] <- Alice]` MUST fail with
   `RECEIVE_REQUIRES_COMMUNICATION_ROLE`. Re-declaring `q0` as
   `[q0:communication]` MUST make it pass.

3. **Paired send/receive across two machines.**
   `alice.q.orca.md` declares `[send: qs[0] -> Bob]`;
   `bob.q.orca.md` declares `[receive: qs[2] <- Alice]`. Running
   `q-orca verify --compose alice.q.orca.md bob.q.orca.md` MUST
   report `✓ alice/transmit ↔ bob/receive` and no errors.

4. **Unpaired send caught.**
   Same as (3) but with Bob's `[receive]` removed. Compose verify
   MUST fail with `UNPAIRED_SEND` naming Alice's transmit state.

5. **Deadlock detection.**
   Alice's machine has `[receive: qs[0] <- Bob]` before any
   `[send]`; Bob's machine has `[receive: qs[0] <- Alice]`
   before any `[send]`. Compose verify MUST fail with
   `PROTOCOL_ORDERING_VIOLATION` and report the cycle in the
   send/receive graph.

6. **`[classical]` final state.**
   A BB84-shaped machine ending in `## state |key_extracted>
   [final, classical]` after all qubits have been measured MUST
   pass. The same machine with one un-measured qubit at the
   final state MUST fail with `CLASSICAL_STATE_HAS_LIVE_QUBITS`.

---

## Dependencies

- Sequences cleanly *after* `add-parameterized-invoke` lands.
  Single-machine `[send]` / `[receive]` checks are independent
  and can ship anytime; cross-machine composition checks need
  the multi-machine loader that `add-parameterized-invoke`
  introduces. v1 of this spec ships with the local checks
  active and the cross-machine checks gated behind `--compose`,
  which can be a no-op until the loader is ready.
- Pairs with `spec-qubit-role-types.md` (this same release
  cycle): the `[receive]` check is sharper if `communication`
  role tags are available, but degrades to a warning if they
  are not.
- Unblocks examples §2.4 (BB84) and the flagship multi-machine
  demo §3.1 (QKD eavesdropping) from the v0.4 coverage roadmap.
- Pairs naturally with the future `add-composed-runtime` change
  (parked in `add-parameterized-invoke`'s out-of-scope list);
  that change is what makes the compiled multi-machine output
  actually executable.

---

## Open Questions

1. **Should `[send]` qubits be erased or just frozen?** Today the
   spec proposes erasure: the sent qubit is removed from the
   local `qubits` list. An alternative is freezing — the qubit
   stays in the list but any action on it is a verifier error.
   Erasure is cleaner semantically (matches the physical
   reality) but breaks the invariant that `qubits` is constant
   across a machine's lifetime, which several existing
   verifier passes assume. Recommend erasure with an explicit
   "qubit count after this state" field on `QStateDef`.

2. **Qubit naming after `[receive]`: re-bind or extend?** When
   Bob receives a qubit from Alice, does it occupy a new index
   in Bob's `qubits` list (extend), or replace one of Bob's
   declared placeholders (re-bind)? The current proposal goes
   with re-bind for simplicity (Bob declares `[q0:data,
   q1:communication]`, the receive lands in `q1`), but extend
   is more flexible for protocols where the number of received
   qubits is dynamic (e.g., a quantum repeater). Recommend
   re-bind for v1, extend in a follow-up if needed.

3. **What is the right Mermaid representation for cross-machine
   arrows?** Mermaid's flowchart syntax does not natively
   support links between subdiagrams. Three candidates:
   (a) emit a single combined diagram with both machines as
   nested subgraphs; (b) emit two separate diagrams plus a
   third "protocol" diagram showing only the send/receive
   pairing; (c) emit Mermaid `sequenceDiagram` syntax for the
   protocol view. Leaning toward (b)+(c) — a structural diagram
   per machine plus a protocol sequence diagram — to give users
   the right picture for the question they're asking.

4. **Should `[send]` carry a basis annotation?** BB84's security
   argument depends critically on which basis the sender used.
   A future enhancement could allow `[send: qs[0] -> Bob, basis:
   {0|1}]` — a uniform random basis annotation — that the
   verifier could use to prove the sift-rate bound. This is
   explicitly out of scope for v1; flagged here so the grammar
   reservation leaves room.

5. **Do `[send]` and `[receive]` interact with `[loop …]`?**
   A repeated send/receive pair (e.g., BB84 sends N qubits in
   a loop) needs to commute with loop annotations. The current
   proposal allows `[loop N]` and `[send: …]` on the same
   state; the verifier must then check that the loop iterates
   over fresh qubits (extends the `qubits` list per iteration)
   rather than reusing — which would be a no-cloning violation.
   This is mostly a parser combination question and probably
   resolves naturally; flagging to confirm during
   implementation.
