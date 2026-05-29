# Runtime State-Category Assertions

Q-Orca's static verifier checks structure (unitarity, no-cloning, reachability)
but cannot answer the question every quantum-program author asks while
debugging: *is the state at this midpoint what I think it is?* Runtime
state-category assertions close that gap. You annotate a named `## state` with
an expected category of quantum-register configuration, and the Stage-4b
verifier mechanically checks the claim by simulating the circuit prefix that
reaches that state.

This is the Huang–Martonosi (ISCA 2019) *statistical assertion* approach: claims
are checked by sampling, not by symbolic projection, so they survive
destructive measurement and quantum non-determinism.

## Syntax

Add an `[assert: …]` annotation to a state heading, alongside `[initial]` /
`[final]`:

```
## state |bell> [assert: entangled(qs[0], qs[1])]
## state |measured> [final, assert: classical(qs[3..4])]
```

Multiple category expressions on one state are separated by `;` and are
conjunctive — all must hold:

```
## state |encoded> [assert: superposition(qs[0..2]); entangled(qs[0], qs[1])]
```

Assertions are evaluated **only** when the machine opts in with a
`state_assertions` verification rule:

```
## verification rules
- state_assertions: check the mid-circuit state categories
```

Without that rule the annotations are parsed and carried through the compilers
as metadata, but no checking runs.

## Categories

| Category | Target form | Holds when |
|---|---|---|
| `classical(qs[k])`, `classical(qs[a..b])` | one qubit or a range | the qubits sit in a single, definite computational-basis outcome |
| `superposition(qs[k])`, `superposition(qs[a..b])` | one qubit or a range | **at least one** qubit in the slice shows both Z-basis outcomes |
| `entangled(qs[i], qs[j])` | exactly two single qubits | qubits `i` and `j` are entangled with each other |
| `separable(qs[i], qs[j])` | exactly two single qubits | the joint state of `i` and `j` factorizes |

### The `superposition` "some qubit" rule

`superposition(qs[a..b])` means *some* qubit in the slice is in superposition,
**not every** qubit. This matters for GHZ-style states: in
`(|000⟩ + |111⟩)/√2` every individual qubit has a maximally mixed marginal, so
the "some qubit" reading is the one that matches the debug intent ("did my
superposition propagate at least this far?"). To require every qubit, write the
conjunction explicitly: `superposition(qs[0]); superposition(qs[1]); …`.

### How `entangled` / `separable` are decided

These use the **Peres–Horodecki (PPT / negativity) criterion** on the reduced
two-qubit density matrix, which is *exact* for two qubits: the pair is entangled
iff the partial transpose of its reduced density matrix has a negative
eigenvalue. This correctly reports a Bell pair as entangled and a GHZ pairwise
reduction as separable (GHZ pairs are classically correlated but not entangled).

> Note: this differs from the original design sketch, which proposed checking
> `Tr(ρ²) < 1−ε` on the pair. That recipe is wrong for a 2-qubit Bell state
> (its pair purity is exactly 1) and false-positives on GHZ pairs. The shipped
> implementation uses PPT/negativity instead.

## Statistical semantics & policy

`classical` / `superposition` are decided by drawing `shots_per_assert` Z-basis
samples and applying a Wilson score interval at the `confidence` level against a
fixed *definiteness* threshold (0.90). Each assertion resolves to exactly one
diagnostic:

- `ASSERTION_PASSED` (info) — the claim holds.
- `ASSERTION_FAILED` — the claim is contradicted. Severity is `error` by
  default, `warning` under `on_failure: warn`.
- `ASSERTION_INCONCLUSIVE` (warning) — the sample interval straddles the
  threshold. Raise `shots_per_assert` rather than treating it as a failure.

Tune behaviour with an optional `## assertion policy` section (absent → these
defaults):

```
## assertion policy
| Setting          | Value | Notes                         |
|------------------|-------|-------------------------------|
| shots_per_assert | 512   | samples per assertion         |
| confidence       | 0.99  | Wilson-interval level         |
| on_failure       | error | 'error' or 'warn'             |
| backend          | auto  | 'auto' (QuTiP) or a name      |
```

Sampling uses a fixed seed, so a verify run is reproducible — the same machine
and policy always produce the same PASS/FAIL/INCONCLUSIVE result.

## Caveats

- **Debug-time cost, not runtime cost.** Assertions re-simulate the circuit
  prefix to each annotated state; they emit **no gates** into the compiled
  artifact. The Qiskit script carries them as `# assertion_probe` comments and
  QASM as `// assert:` comments — real-hardware execution is unaffected.
- **Default parameter values only.** A parameterized machine is asserted against
  its declared default angles; sweeping assertion parameters is not yet
  supported.
- **Real-device targets are skipped.** Compiling to a real device emits a single
  `ASSERTIONS_SKIPPED_NO_SIMULATOR` info diagnostic — there is no replay-and-
  sample on hardware. Re-run the simulator path before a hardware run.
- **Mid-circuit measurement** is handled by collapsing to the dominant outcome
  at each measurement and firing feedforward gates on the recorded bits, so an
  assertion downstream of a `measure(…)` is checked against the post-measurement
  state along the first declaration-order path.
- **Missing backend.** If the simulator (QuTiP) is unavailable, the stage emits
  a single `ASSERTION_BACKEND_MISSING` warning and evaluates nothing.

## Example

See `examples/bell-entangler-asserts.q.orca.md` (superposition after the
Hadamard, entanglement after the CNOT) and `examples/bit-flip-syndrome.q.orca.md`
(classical data codeword and classical syndrome ancilla).
