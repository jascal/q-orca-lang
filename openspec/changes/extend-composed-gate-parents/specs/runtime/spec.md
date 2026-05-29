## MODIFIED Requirements

### Requirement: Composed Machine Execution

The runtime SHALL provide `run_composed(file, machine, options, base_path=None)`
that executes a parent machine and every machine it invokes, returning the
parent's final context. It SHALL reuse the single-machine iterative walk for
each machine and intercept invoke states to dispatch their children. A machine
with no invoke states SHALL execute identically to the existing single-machine
runtime. The runtime SHALL assume the machine has already passed verification
and SHALL NOT re-verify.

An invoke-bearing parent MAY carry its own gate- and measurement-bearing
transitions interleaved with invoke states. The runtime SHALL accumulate the
parent's gate-bearing transitions into circuit segments and flush them (building
and running the circuit, updating the parent's measured bits) on three
boundaries: before a context-update action, before an invoke, and on reaching a
final state. The parent's quantum register and a child's are independent; only
the child's declared returns cross the invoke boundary, as classical values. An
invoke SHALL NOT perturb the parent's accumulated quantum state.

When the walk reaches an invoke state, the runtime SHALL: (0) flush any pending
parent gate segment so its measured bits are observable to the invoke's
bindings and to subsequent guards; (1) resolve the child (a same-file machine,
or via the import graph when `base_path` is supplied); (2) build the child's
initial context by seeding each child field named on an argument binding's LHS
from the bound parent expression's value; (3) execute the child; (4) write each
return binding's parent field from the child's corresponding return value;
(5) resume the parent walk from the invoke state's outgoing transitions.

Recursion depth SHALL be bounded by a configurable ceiling (default 32); a run
exceeding it SHALL raise a structured runtime error. Invoke cycles are rejected
statically and SHALL NOT be re-detected at run time.

#### Scenario: Single machine runs unchanged

- **WHEN** `run_composed` is given a machine with no invoke states
- **THEN** its final context equals the result of the existing single-machine
  iterative runtime

#### Scenario: Classical child returns flow into the parent

- **WHEN** a parent invokes a classical (no-measurement) child and binds
  `done=converged`, and the child reaches a final state with `converged=true`
- **THEN** after the invoke the parent context has `done == true`

#### Scenario: Argument bindings seed the child context

- **WHEN** a parent with `iteration=3` invokes `Child(seed=iteration)`
- **THEN** the child executes with its `seed` context field initialized to `3`

#### Scenario: Depth ceiling guards runaway recursion

- **WHEN** composition nesting exceeds the configured depth ceiling
- **THEN** `run_composed` raises a structured runtime error naming the ceiling

#### Scenario: Parent gates execute around an invoke

- **WHEN** an invoke-bearing parent applies its own `H(qs[0]); CNOT(qs[0], qs[1])`
  before an invoke state and a further gate after it
- **THEN** `run_composed` executes the parent's gate segments (rather than
  raising an unsupported-action error) and the parent's measured bits reflect
  its own circuit, independent of the child's register

#### Scenario: Parent measurement before an invoke feeds a later guard

- **WHEN** a parent measures a qubit into a bit, then invokes a child, then has
  two guarded outgoing transitions selecting on that bit
- **THEN** the bit measured before the invoke is observable to the guard
  evaluated after the invoke completes
