"""Entanglement entropy / Schmidt rank for stabilizer states.

For a stabilizer state the entanglement entropy of a subsystem ``A`` is
``S_A = rank_GF2(M_A) − |A|`` where ``M_A`` is the restriction of the
stabilizer generators (as a binary X|Z check matrix) to ``A``'s columns
(Fattal, Cubitt, Yamamoto, Bravyi & Chuang, quant-ph/0406168). The Schmidt
rank across the ``A | rest`` cut is ``2^{S_A}``. Both are computed in
polynomial time, replacing the `O(2^n)` state-vector evolution the QuTiP path
uses for the same entanglement check — which is what makes large Clifford QEC
circuits verifiable.

Verified by hand: Bell ⇒ S=1, rank 2; product ⇒ S=0, rank 1; GHZ (1|rest) ⇒
S=1, rank 2.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List

STIM_AVAILABLE = False
try:
    import stim  # noqa: F401
    STIM_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only without stim
    pass

_HALF_PI = math.pi / 2


def _gf2_rank(rows: List[List[int]]) -> int:
    """Rank over GF(2) of a 0/1 matrix given as a list of row lists."""
    rows = [row[:] for row in rows]
    n_rows = len(rows)
    n_cols = len(rows[0]) if rows else 0
    rank = 0
    for col in range(n_cols):
        pivot = next((r for r in range(rank, n_rows) if rows[r][col]), None)
        if pivot is None:
            continue
        rows[rank], rows[pivot] = rows[pivot], rows[rank]
        for r in range(n_rows):
            if r != rank and rows[r][col]:
                rows[r] = [a ^ b for a, b in zip(rows[r], rows[rank])]
        rank += 1
        if rank == n_rows:
            break
    return rank


def build_state_simulator(gate_dicts: Iterable[Dict[str, Any]], n_qubits: int):
    """Apply a Clifford gate path (verifier gate-dict shape) to a fresh
    ``stim.TableauSimulator`` starting from |0…0>, returning the simulator.

    Control/target extraction mirrors `dynamic._get_qutip_operator` exactly so
    the stabilizer state matches the QuTiP evolution gate-for-gate. `pi/2`
    rotations map to their Clifford equivalents (global phase is irrelevant to
    entanglement). Raises ValueError on a non-Clifford gate — callers gate this
    behind `is_clifford`.
    """
    if not STIM_AVAILABLE:
        raise RuntimeError("stim is not installed")
    sim = stim.TableauSimulator()
    sim.set_num_qubits(n_qubits)
    for g in gate_dicts:
        name = (g.get("name") or "").upper()
        targets = g.get("targets", [])
        controls = g.get("controls", [])
        params = g.get("params", {})
        if not targets:
            continue
        if name == "H":
            sim.h(targets[0])
        elif name in ("X", "NOT"):
            sim.x(targets[0])
        elif name == "Y":
            sim.y(targets[0])
        elif name == "Z":
            sim.z(targets[0])
        elif name == "S":
            sim.s(targets[0])
        elif name in ("SDG", "SDAG"):
            sim.s_dag(targets[0])
        elif name in ("CNOT", "CX"):
            ctrl = controls[0] if controls else targets[0]
            tgt = targets[1] if len(targets) > 1 else targets[0]
            sim.cnot(ctrl, tgt)
        elif name == "CZ":
            ctrl = controls[0] if controls else targets[0]
            sim.cz(ctrl, targets[0])
        elif name == "CY":
            ctrl = controls[0] if controls else targets[0]
            sim.cy(ctrl, targets[0])
        elif name == "SWAP":
            tgt2 = targets[1] if len(targets) > 1 else targets[0]
            sim.swap(targets[0], tgt2)
        elif name in ("RX", "RY", "RZ"):
            k = round(params.get("theta", 0.0) / _HALF_PI) % 4
            _apply_clifford_rotation(sim, name, targets[0], k)
        else:
            raise ValueError(f"Non-Clifford gate in stabilizer path: {name}")
    return sim


def _apply_clifford_rotation(sim, name: str, target: int, k: int) -> None:
    """Apply ``R{x,y,z}(k·π/2)`` as ``k`` repetitions of the √-gate (up to a
    global phase that does not affect entanglement)."""
    method = {"RX": sim.sqrt_x, "RY": sim.sqrt_y, "RZ": sim.s}[name]
    for _ in range(k):
        method(target)


def _stabilizer_xz_rows(sim, subsystem: List[int]) -> List[List[int]]:
    """Restriction of the canonical stabilizer generators to ``subsystem``'s
    X|Z columns, as GF(2) rows."""
    rows: List[List[int]] = []
    for pauli in sim.canonical_stabilizers():
        xs = [1 if pauli[q] in (1, 2) else 0 for q in subsystem]  # X or Y
        zs = [1 if pauli[q] in (2, 3) else 0 for q in subsystem]  # Y or Z
        rows.append(xs + zs)
    return rows


def subsystem_entropy_ebits(sim, subsystem: List[int]) -> int:
    """Entanglement entropy (in ebits / units of log2) of ``subsystem`` for the
    current stabilizer state: ``rank_GF2(M_A) − |A|``."""
    a = list(dict.fromkeys(subsystem))  # de-dup, preserve order
    rank = _gf2_rank(_stabilizer_xz_rows(sim, a))
    return rank - len(a)


def entropy_and_schmidt(sim, subsystem: List[int]) -> tuple[float, int]:
    """Return ``(entropy_bits, schmidt_rank)`` for ``subsystem`` vs. the rest:
    the von Neumann entropy (integer-valued for a stabilizer state) and Schmidt
    rank ``2^{S_A}``, matching `dynamic._entanglement_entropy` /
    `_schmidt_rank_across_bipartition` on the same state."""
    s = subsystem_entropy_ebits(sim, subsystem)
    return float(s), 2 ** s
