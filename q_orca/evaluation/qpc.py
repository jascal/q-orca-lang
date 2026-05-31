"""QPC convergence benchmark (`add-qpc-convergence-benchmark`).

Runs the quantum predictive coder's learning loop through the iterative runtime,
measures the per-iteration error trajectory, compares it against an exact
classical baseline, and certifies convergence.

What is and is not claimed
--------------------------
This is a *correctness and measurability* demonstration, **not** a quantum
advantage. For this single-parameter toy the exact classical baseline is at
least as good — it is shown alongside precisely so the comparison is honest.

How the loop converges
----------------------
The benchmark machine (`examples/predictive-coder-converging.q.orca.md`) prepares
the model qubit with `Ry(theta_0)`, leaves the data qubit in `|0>`, and measures
the parity ancilla, so the forward measurement is
``p(theta_0) = P(bits[0]=1) = sin^2(theta_0/2)``.
The binary update ``theta_0 -= eta`` (measured 1) / ``+= eta`` (measured 0) has
zero expected drift exactly where ``p = 1/2``, i.e. at ``theta_0* = pi/2``. With
a constant step `eta` the loop does not converge to a point — it enters and then
dithers within an ``O(eta)`` band around `theta_0*`, which the verdict accounts
for (band criterion + first-half-vs-second-half improvement, never strict
per-iteration monotonicity).

The theta trajectory is produced by the real quantum runtime (`simulate_iterative`
runs the full 3-qubit machine; the measured ancilla bit drives each update). The
per-iteration error metric re-measures the forward pass at each recorded
`theta_0` by building and running its circuit (so the no-signal guard works for
any machine, not just this one).
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from q_orca.ast import QMachineDef
from q_orca.parser.markdown_parser import parse_q_orca_markdown
from q_orca.runtime.iterative import simulate_iterative
from q_orca.runtime.types import QIterativeSimulationOptions

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_EXAMPLE = _REPO_ROOT / "examples" / "predictive-coder-converging.q.orca.md"

TARGET_PROB = 0.5            # the binary update's zero-drift fixed point
THETA_STAR = math.pi / 2     # the angle where p(theta_0) = 1/2


def p_exact(theta_0: float) -> float:
    """Exact forward-measurement probability for the benchmark task.

    For `Ry(theta_0)|0>` measured in Z (with the data qubit fixed at |0>), the
    parity ancilla reads 1 with probability ``sin^2(theta_0/2)``. This is the
    classical baseline's objective — no simulator required.
    """
    return math.sin(theta_0 / 2.0) ** 2


@dataclass
class QpcBenchmarkConfig:
    theta_0_init: float = 0.5
    eta: float = 0.15
    max_iter: int = 60
    loop_shots: int = 256        # shots per loop iteration (drives the majority-vote bit)
    metric_shots: int = 2048     # shots for the per-theta forward error estimate
    seed: int = 7
    band_factor: float = 1.0     # convergence band width = band_factor * eta
    window_frac: float = 1.0 / 3.0
    signal_threshold: float = 0.2  # min |p(lo) - p(hi)| to count as a learning signal
    theta_field: str = "theta_0"
    example_path: str = str(_DEFAULT_EXAMPLE)


@dataclass
class QpcBenchmarkResult:
    config: dict
    theta_star: float
    # per-iteration trajectories (length = iterations actually run)
    thetas: list = field(default_factory=list)             # theta_0 in effect each iteration
    quantum_prob: list = field(default_factory=list)        # p_hat(theta_t) measured forward prob
    quantum_error: list = field(default_factory=list)       # |p_hat(theta_t) - 1/2| (measured)
    classical_theta: list = field(default_factory=list)     # exact-baseline theta trajectory
    classical_error: list = field(default_factory=list)     # |p_exact(theta_t) - 1/2| (exact)
    # summary
    final_theta: float = 0.0
    band_width: float = 0.0
    first_half_mean: float = 0.0
    second_half_mean: float = 0.0
    final_window_mean: float = 0.0
    max_gap: float = 0.0
    mean_gap: float = 0.0
    has_signal: bool = True
    signal_lo: float = 0.0
    signal_hi: float = 0.0
    converged: bool = False
    verdict_reason: str = ""
    plot_written: bool = False
    plot_skipped_reason: Optional[str] = None


def _load_machine(path: str) -> QMachineDef:
    return parse_q_orca_markdown(Path(path).read_text()).file.machines[0]


def _forward_actions(machine: QMachineDef) -> list:
    """Collect the gate-bearing actions of one forward pass.

    Walks the machine from its initial state taking the first enabled transition
    (matching the iterative runtime's auto-walk), collecting gate/measurement
    actions until the first classical context-update action (the gradient step) —
    that prefix is exactly the circuit measured each iteration.
    """
    action_map = {a.name: a for a in machine.actions}
    transitions = machine.transitions
    initial = next((s.name for s in machine.states if s.is_initial), None)

    fwd: list = []
    current = initial
    seen: set = set()
    while current is not None and current not in seen:
        seen.add(current)
        outgoing = [t for t in transitions if t.source == current]
        if not outgoing:
            break
        t = outgoing[0]
        action = action_map.get(t.action) if t.action else None
        if action is not None:
            if getattr(action, "context_update", None) is not None:
                break  # reached the classical update — forward prefix complete
            fwd.append(action)
        current = t.target
    return fwd


def _forward_prob_measured(
    machine: QMachineDef, fwd_actions: list, theta_field: str,
    theta_value: float, shots: int, seed: int,
) -> float:
    """Measured P(bits[0]=1) of the forward pass at a given theta (real circuit)."""
    from q_orca.compiler.qiskit import build_circuit_for_iteration

    ctx = {f.name: f.default_value for f in machine.context}
    ctx[theta_field] = theta_value
    qc = build_circuit_for_iteration(machine, ctx, fwd_actions)

    from qiskit.providers.basic_provider import BasicSimulator
    from qiskit import transpile

    sim = BasicSimulator()
    try:
        compiled = transpile(qc, sim)
    except Exception:
        compiled = qc
    counts = sim.run(compiled, shots=shots, seed_simulator=seed).result().get_counts()
    total = sum(counts.values()) or 1
    ones = sum(c for k, c in counts.items() if k.replace(" ", "")[::-1][0] == "1")
    return ones / total


def _run_loop(machine: QMachineDef, cfg: QpcBenchmarkConfig) -> list:
    """Run the QPC loop on the real runtime; return theta_0 in effect each iteration."""
    opts = QIterativeSimulationOptions(
        inner_shots=cfg.loop_shots, seed_simulator=cfg.seed, record_trace=True,
    )
    res = simulate_iterative(machine, opts, initial_context={
        cfg.theta_field: cfg.theta_0_init, "eta": cfg.eta, "max_iter": cfg.max_iter,
    })
    post = [t.context_snapshot.get(cfg.theta_field)
            for t in res.trace if t.action == "gradient_step"]
    # theta in effect during iteration t's measurement = value before that
    # iteration's update: init for t=0, else the previous post-update value.
    thetas = [cfg.theta_0_init] + post[:-1] if post else []
    return thetas


def _classical_baseline(cfg: QpcBenchmarkConfig, n_iter: int) -> tuple:
    """Exact deterministic baseline: same binary-drift dynamics on p_exact."""
    thetas, errors = [], []
    theta = cfg.theta_0_init
    for _ in range(n_iter):
        thetas.append(theta)
        p = p_exact(theta)
        errors.append(abs(p - TARGET_PROB))
        # deterministic majority bit: 1 iff p > 1/2
        if p > TARGET_PROB:
            theta -= cfg.eta
        else:
            theta += cfg.eta
    return thetas, errors


def _mean(xs: list) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def run_benchmark(cfg: Optional[QpcBenchmarkConfig] = None) -> QpcBenchmarkResult:
    """Run the QPC convergence benchmark and return a structured result."""
    cfg = cfg or QpcBenchmarkConfig()
    machine = _load_machine(cfg.example_path)
    fwd = _forward_actions(machine)

    result = QpcBenchmarkResult(config=asdict(cfg), theta_star=THETA_STAR)

    # --- no-signal guard: does the forward error actually depend on theta? -----
    lo = _forward_prob_measured(machine, fwd, cfg.theta_field, 0.3, cfg.metric_shots, cfg.seed)
    hi = _forward_prob_measured(machine, fwd, cfg.theta_field, 2.8, cfg.metric_shots, cfg.seed + 1)
    result.signal_lo, result.signal_hi = lo, hi
    result.has_signal = abs(hi - lo) > cfg.signal_threshold

    # --- quantum trajectory (real runtime) + measured error metric ------------
    thetas = _run_loop(machine, cfg)
    result.thetas = thetas
    result.quantum_prob = [
        _forward_prob_measured(
            machine, fwd, cfg.theta_field, th, cfg.metric_shots, cfg.seed + i,
        )
        for i, th in enumerate(thetas)
    ]
    result.quantum_error = [abs(p - TARGET_PROB) for p in result.quantum_prob]
    result.final_theta = thetas[-1] if thetas else cfg.theta_0_init

    # --- exact classical baseline (for the convergence comparison/plot) -------
    c_theta, c_err = _classical_baseline(cfg, len(thetas))
    result.classical_theta, result.classical_error = c_theta, c_err

    # --- shot-noise gap: measured forward prob vs the exact objective at the
    #     SAME theta. This isolates measurement noise (O(1/sqrt(shots))) from the
    #     stochastic-vs-deterministic trajectory divergence (which is O(eta)).
    gaps = [abs(p - p_exact(th)) for p, th in zip(result.quantum_prob, thetas)]
    result.max_gap = max(gaps) if gaps else 0.0
    result.mean_gap = _mean(gaps)

    # --- convergence verdict (band + monotone-improvement) --------------------
    n = len(result.quantum_error)
    result.band_width = cfg.band_factor * cfg.eta
    if n == 0:
        result.verdict_reason = "no iterations run"
        return result
    window = max(1, math.ceil(cfg.window_frac * n))
    result.final_window_mean = _mean(result.quantum_error[-window:])
    half = max(1, n // 2)
    result.first_half_mean = _mean(result.quantum_error[:half])
    result.second_half_mean = _mean(result.quantum_error[half:])

    if not result.has_signal:
        result.converged = False
        result.verdict_reason = (
            f"no learning signal: forward error is ~constant in {cfg.theta_field} "
            f"(p(0.3)={lo:.3f} vs p(2.8)={hi:.3f}); refusing to certify convergence"
        )
        return result

    in_band = result.final_window_mean < result.band_width
    improved = result.second_half_mean < result.first_half_mean
    result.converged = in_band and improved
    if result.converged:
        result.verdict_reason = (
            f"converged: final-window mean error {result.final_window_mean:.3f} "
            f"< band {result.band_width:.3f}, and second-half mean "
            f"{result.second_half_mean:.3f} < first-half {result.first_half_mean:.3f}"
        )
    else:
        why = []
        if not in_band:
            why.append(f"final-window mean {result.final_window_mean:.3f} >= band {result.band_width:.3f}")
        if not improved:
            why.append(f"second-half mean {result.second_half_mean:.3f} >= first-half {result.first_half_mean:.3f}")
        result.verdict_reason = "not converged: " + "; ".join(why)
    return result


def write_artifacts(result: QpcBenchmarkResult, out_dir: str | Path) -> dict:
    """Write results.csv + results.json (always) and a plot (only if matplotlib).

    Returns a dict of the paths written.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written: dict = {}

    csv_path = out / "results.csv"
    with csv_path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["iteration", "theta_quantum", "prob_quantum", "error_quantum",
                    "theta_classical", "error_classical"])
        for i in range(len(result.thetas)):
            w.writerow([
                i,
                result.thetas[i],
                result.quantum_prob[i] if i < len(result.quantum_prob) else "",
                result.quantum_error[i],
                result.classical_theta[i] if i < len(result.classical_theta) else "",
                result.classical_error[i] if i < len(result.classical_error) else "",
            ])
    written["csv"] = str(csv_path)

    json_path = out / "results.json"
    json_path.write_text(json.dumps(asdict(result), indent=2, default=str))
    written["json"] = str(json_path)

    # Plot is best-effort: emit only if matplotlib is importable.
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(7, 4))
        xs = list(range(len(result.quantum_error)))
        ax.plot(xs, result.quantum_error, label="quantum (measured)", marker="o", ms=3)
        ax.plot(xs, result.classical_error, label="classical (exact)", ls="--")
        ax.axhline(result.band_width, color="grey", ls=":", label=f"band = {result.band_width:.3f}")
        ax.set_xlabel("iteration")
        ax.set_ylabel("error  |P(1) - 1/2|")
        ax.set_title("QPC convergence — quantum vs exact classical baseline\n(no quantum advantage claimed)")
        ax.legend()
        fig.tight_layout()
        plot_path = out / "convergence.png"
        fig.savefig(plot_path, dpi=110)
        plt.close(fig)
        written["plot"] = str(plot_path)
        result.plot_written = True
    except Exception as exc:  # matplotlib absent or headless failure
        result.plot_skipped_reason = f"{type(exc).__name__}: {exc}"
        result.plot_written = False

    return written
