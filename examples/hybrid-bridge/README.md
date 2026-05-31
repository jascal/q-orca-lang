# Hybrid quantum-classical demo — over the cross-tool bridge

A **classical Orca** orchestrator drives a **quantum q-orca** circuit through a
variational optimization loop, with the two tools communicating *only* over the
[cross-tool bridge protocol][bridge-doc] (version `1.0`). They share no AST, no
FFI, and — as run here — not even a Python environment. Every iteration crosses
the boundary as JSON envelopes piped over a subprocess.

[bridge-doc]: https://github.com/jascal/orca-lang/blob/main/docs/cross-tool-invoke-and-returns.md
<!-- In a local side-by-side checkout the doc lives at ../../../orca-lang/docs/cross-tool-invoke-and-returns.md -->


## What it does

The orchestrator tunes the rotation angle `theta` of a single-qubit circuit so
that the **measured** probability of outcome 1 reaches a target (default `0.5`, a
"fair coin" / `|+>` state, whose ideal angle is `θ* = π/2`). It never sees a
qubit — only the classical statistic bound back from the quantum child.

```
  classical loop (Orca, runtime-python)        quantum forward pass (q-orca)
  ┌──────────────────────────┐    invocation   ┌────────────────────────────┐
  │  measuring ───────────────┼───── envelope ──▶ Ry(theta) ; measure → bit  │
  │   ▲                  │     │                 │  prob_bits_0 = sin²(θ/2)   │
  │   │ next             ▼     │ ◀──── result ────┼──────────── (shot stats)  │
  │  evaluate ◀── gradient_step                  └────────────────────────────┘
  └──────────────────────────┘  (loop until |target − measured| < tol)
```

- **`forward.q.orca.md`** — the quantum child `QForward`: `Ry(theta)` then
  `measure → bits[0]`, exposing `bits[0]` with `expectation, histogram`
  statistics. Run with `shots=N` over the bridge it returns
  `prob_bits_0 = P(measure 1)`.
- **`vqe-orchestrator.orca.md`** — the classical machine `VqeOrchestrator`. The
  whole optimization loop is expressed as Orca **states, transitions, and
  guards**: `idle → measuring →(MEASURED)→ evaluate →(next)→ measuring | done`.
  The `measuring` state's `invoke` targets `QForward` over the bridge and binds
  `prob_bits_0` back into the parent context as `prob`.
- **`run_demo.py`** — the host driver. It supplies only two things the Orca
  machine cannot express by itself: the numeric body of the `gradient_step`
  action (a proportional update that also sets the `converged` flag the guards
  branch on), and the bridge wiring (`register_foreign_runner`).

## Run it

The two packages are developed in separate repos and separate virtualenvs — the
driver runs under **orca-lang**'s venv (which has `orca_runtime_python`) and
shells out to **q-orca**'s venv console script. That separation is the point:
the bridge needs neither a shared environment nor a shared language.

```bash
Q_ORCA_BIN=/path/to/q-orca-lang/.venv/bin/q-orca \
  /path/to/orca-lang/.venv/bin/python run_demo.py
```

- `Q_ORCA_BIN` — the q-orca CLI. Defaults to `q-orca` on `PATH`; **point it at
  the repo venv** if the globally-installed console script predates the
  `run --bridge` subcommand.
- `TARGET` — override the target P(1) for a run, e.g. `TARGET=0.85` (the loop
  converges toward `θ* = 2·asin√0.85 ≈ 2.346`). The default lives in the Orca
  machine's `target` context field.

### Both halves must carry the bridge

The demo only runs against builds that include the bridge on **both** sides:

| package | needs | bridge piece |
|---------|-------|--------------|
| `q-orca` | ≥ 0.9.1 | `q-orca run … --bridge` inbound entry point |
| `orca-runtime-python` | post-PR #13 | `OrcaMachine.register_foreign_runner` outbound dispatch |

These landed without a version bump on the runtime-python side, so an installed
`orca-runtime-python 0.1.26` may or may not have the bridge depending on when it
was built. Until both are released with the bridge included, run the driver from
a checkout whose `orca-runtime-python` has `register_foreign_runner` and set
`Q_ORCA_BIN` to a `q-orca` ≥ 0.9.1.

## Sample output

```
  iter │   θ used │ measured P(1) │    error │   θ → next
  ───────────────────────────────────────────────────────
     1 │   0.3000 │        0.0188 │  +0.4812 │     1.2624
     2 │   1.2624 │        0.3457 │  +0.1543 │     1.5710
     3 │   1.5710 │        0.4993 │  +0.0007 │ (converged)

  final θ     : 1.5725   (θ* = 1.5708)
  final P(1)  : 0.4993   (target 0.5)
  quantum calls across the bridge : 3  (12288 total shots)
```

The run is reproducible: the simulator seed is fixed (`SEED = 7`), so each
`(theta, seed)` forward pass returns the same shot statistics.

## How the boundary is crossed

1. Entering `measuring`, `runtime-python` sees `QForward` is not a local sibling
   but a registered foreign runner, and builds an **invocation envelope**
   `{protocol_version, child: "QForward", args: {theta}, shots, return_bindings}`.
2. It runs `q-orca run forward.q.orca.md --bridge`, writing that envelope to the
   child's stdin.
3. q-orca's inbound bridge resolves `QForward`, runs it shot-batched, and writes
   a **result envelope** `{protocol_version, final_state, returns: {bits[0],
   prob_bits_0, hist_bits_0}}` to stdout.
4. `runtime-python` binds `prob_bits_0 → prob` into the orchestrator's context
   and fires `on_done` (`MEASURED`), advancing the Orca loop.

A protocol-version mismatch or malformed envelope on either side is a hard
`BridgeError`; a missing declared return is soft-skipped (the parent field keeps
its value). See the design doc linked above for the full contract.
