"""HEA-encoded concept Gram matrix analysis.

Optional analysis utility for machines that follow the rung-2
*hardware-efficient ansatz* (HEA) concept-encoding convention
documented in ``add-rung2-hea-encoding``. The HEA preparation lifts
the rung-1 CNOT-staircase MPS ansatz from ``compute_concept_gram_mps``
to a depth-``L`` block of single-qubit rotations followed by an
entangler (CNOT ring or chain), repeated ``L`` times — the standard
expressivity workhorse from VQE / QAOA.

Convention assumed by this helper:

1. The machine declares an ``## encoding`` section with
   ``kind: hea`` (parsed into ``machine.encoding`` as an
   ``EncodingDecl``).
2. The machine declares a ``## theta`` block (parsed into
   ``machine.theta`` as a ``ThetaBlock``) with one ``ThetaRow`` per
   concept. Each row's tensor has shape
   ``(|rotations|, depth, n)`` where ``n`` is the size of the
   resolved qubits register.
3. The transitions table contains call sites to the named concept
   action. The helper enumerates call sites in transition-
   declaration order and pairs them positionally with theta rows in
   declaration order: call site ``i`` is built from
   ``machine.theta.rows[i]``. The number of call sites SHALL equal
   the number of theta rows.

Given such a machine, ``compute_concept_gram_hea`` builds each
concept state ``|c_i>`` by simulating the HEA circuit on
``|0^n>`` and returns the ``N x N`` matrix with
``gram[i, j] = <c_i | c_j>``.

The helper is **not** on the main compile / verify / simulate path;
it exists for analysis and the verifier's Stage 4b dispatch on HEA
machines.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from q_orca.ast import EncodingDecl, QMachineDef
from q_orca.compiler.concept_gram_mps import (
    _apply_1q,
    _apply_cnot,
    _ry_matrix,
    _rz_matrix,
)
from q_orca.compiler.util import infer_qubit_count

if TYPE_CHECKING:
    import numpy as np


class HeaGramConfigurationError(ValueError):
    """Raised when a machine doesn't meet the HEA concept-gram convention."""


def _rx_matrix(np_module, theta: float):
    c = np_module.cos(theta / 2.0)
    s = np_module.sin(theta / 2.0)
    return np_module.array([[c, -1j * s], [-1j * s, c]], dtype=complex)


def _rotation_matrix(np_module, kind: str, theta: float):
    if kind == "Rx":
        return _rx_matrix(np_module, theta)
    if kind == "Ry":
        return _ry_matrix(np_module, theta)
    if kind == "Rz":
        return _rz_matrix(np_module, theta)
    raise AssertionError(f"unexpected rotation kind {kind!r}")  # pragma: no cover


def _entangler_pairs(entangler: str, n_qubits: int) -> list[tuple[int, int]]:
    """Return the list of CNOT (control, target) pairs for the entangler."""
    if n_qubits < 2:
        return []
    chain = [(q, q + 1) for q in range(n_qubits - 1)]
    if entangler == "chain":
        return chain
    if entangler == "ring":
        return chain + [(n_qubits - 1, 0)]
    raise AssertionError(f"unexpected entangler {entangler!r}")  # pragma: no cover


def _build_hea_state(
    np_module,
    theta_tensor,
    encoding: EncodingDecl,
    n_qubits: int,
):
    """Build |c_i> for a single concept under its theta tensor.

    ``theta_tensor`` has shape ``(|rotations|, depth, n_qubits)``.
    For each layer the helper applies the rotations in declared order
    (one rotation kind per element of ``encoding.rotations``) on
    every qubit, then applies the entangler block.
    """
    state = np_module.zeros((2,) * n_qubits, dtype=complex)
    state[(0,) * n_qubits] = 1.0

    pairs = _entangler_pairs(encoding.entangler, n_qubits)
    for layer in range(encoding.depth):
        for r_idx, kind in enumerate(encoding.rotations):
            for q in range(n_qubits):
                angle = float(theta_tensor[r_idx, layer, q])
                U = _rotation_matrix(np_module, kind, angle)
                state = _apply_1q(np_module, state, U, q)
        for control, target in pairs:
            state = _apply_cnot(np_module, state, control, target)
    return state


def compute_concept_gram_hea(
    machine: QMachineDef,
    concept_action_label: str = "query_concept",
) -> "np.ndarray":
    """Compute the N x N concept-overlap matrix for an HEA-encoded machine.

    Parameters
    ----------
    machine:
        A parsed ``QMachineDef`` with an ``## encoding`` section
        declaring ``kind: hea`` and a matching ``## theta`` block.
    concept_action_label:
        Name of the parametric concept action whose call sites
        enumerate the dictionary. Default ``"query_concept"``.

    Returns
    -------
    numpy.ndarray
        Complex-valued ``(N, N)`` matrix with
        ``gram[i, j] = <c_i | c_j>``.

    Raises
    ------
    HeaGramConfigurationError
        On any of: missing ``## encoding`` section, wrong
        ``encoding.kind``, missing ``## theta`` section, theta-row
        shape mismatch with ``(|rotations|, depth, n)``, a call site
        whose concept name has no matching theta row, or zero call
        sites.
    """
    import numpy as np

    encoding = machine.encoding
    if encoding is None:
        raise HeaGramConfigurationError(
            f"machine {machine.name!r}: no `## encoding` section; "
            f"compute_concept_gram_hea requires an encoding "
            f"declaration with `kind: hea`"
        )
    if encoding.kind != "hea":
        raise HeaGramConfigurationError(
            f"machine {machine.name!r}: encoding kind is "
            f"{encoding.kind!r}; this helper handles `kind: hea` only"
        )

    theta = machine.theta
    if theta is None:
        raise HeaGramConfigurationError(
            f"machine {machine.name!r}: no `## theta` block; "
            f"compute_concept_gram_hea requires a theta block "
            f"declaring per-concept tensors"
        )

    n_qubits = infer_qubit_count(machine)
    if n_qubits <= 0:
        raise HeaGramConfigurationError(
            f"machine {machine.name!r}: could not infer a qubit "
            f"register size; HEA concept-gram requires a non-empty "
            f"`qubits` list in `## context`"
        )

    expected_shape = (len(encoding.rotations), encoding.depth, n_qubits)
    tensors: list = []
    for row in theta.rows:
        tensor = np.asarray(row.tensor, dtype=float)
        if tensor.shape != expected_shape:
            raise HeaGramConfigurationError(
                f"machine {machine.name!r}: theta row for concept "
                f"{row.concept!r} has shape {tensor.shape}, expected "
                f"{expected_shape}"
            )
        tensors.append(tensor)

    call_sites = [
        t for t in machine.transitions
        if t.action == concept_action_label
    ]
    if not call_sites:
        raise HeaGramConfigurationError(
            f"machine {machine.name!r}: action "
            f"{concept_action_label!r} has no call sites in the "
            f"transitions table; HEA concept-gram needs at least one"
        )

    if len(call_sites) != len(tensors):
        concept_names = [r.concept for r in theta.rows]
        raise HeaGramConfigurationError(
            f"machine {machine.name!r}: action "
            f"{concept_action_label!r} has {len(call_sites)} call "
            f"site(s) but `## theta` declares {len(tensors)} concept "
            f"row(s) ({concept_names!r}); the two SHALL match"
        )

    states = np.stack([
        _build_hea_state(np, tensors[i], encoding, n_qubits).reshape(-1)
        for i in range(len(call_sites))
    ])
    return states.conj() @ states.T


def compute_tier_separation(
    gram: "np.ndarray",
    clusters: list[str],
) -> float | None:
    """Tier-ordering metric for an HEA-encoded dictionary.

    ``gram`` is the ``N x N`` complex Gram matrix returned by
    ``compute_concept_gram_hea`` (or any compatible helper).
    ``clusters[i]`` is the cluster label for concept ``i``.

    Returns ``min_intra_cluster_mean − max_cross_cluster_overlap``,
    where intra-cluster mean is taken over the squared off-diagonal
    overlaps within each cluster of size ≥ 2. Singleton clusters are
    ignored. Returns ``None`` when no cluster has at least two
    members (the metric is undefined — there is no intra-cluster
    overlap to compare against).

    Sensitivity caveat
    ------------------
    Both reductions are min/max over a small number of pairs, so the
    metric is sensitive to outliers when clusters are small. A
    2-concept cluster has only one intra-cluster pair, so its "mean"
    is just that single overlap; ``min`` over cluster means then
    penalizes the worst-cohesion cluster regardless of cluster size.
    Symmetrically, ``max_cross_cluster_overlap`` is dominated by a
    single outlier pair. For noisy θ tensors or dictionaries with
    many small clusters, prefer larger clusters (size ≥ 4) before
    treating the metric as tight; if a more robust alternative is
    needed (e.g. quantile-trimmed reductions or weighted means), that
    belongs in a follow-up rather than as a silent change here.
    """
    import numpy as np

    n = len(clusters)
    if gram.shape != (n, n):
        raise ValueError(
            f"compute_tier_separation: gram.shape {gram.shape} does "
            f"not match cluster count {n}"
        )

    overlap = np.abs(gram) ** 2

    intra_means: list[float] = []
    cross_max = 0.0
    for i in range(n):
        for j in range(i + 1, n):
            v = float(overlap[i, j])
            if clusters[i] == clusters[j]:
                pass  # collected below
            else:
                if v > cross_max:
                    cross_max = v

    by_cluster: dict[str, list[float]] = {}
    for i in range(n):
        for j in range(i + 1, n):
            if clusters[i] == clusters[j]:
                by_cluster.setdefault(clusters[i], []).append(
                    float(overlap[i, j])
                )

    for cluster, vals in by_cluster.items():
        if vals:
            intra_means.append(sum(vals) / len(vals))

    if not intra_means:
        return None

    return min(intra_means) - cross_max
