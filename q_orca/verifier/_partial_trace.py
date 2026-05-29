"""Backend-agnostic partial trace for the state-assertions checker.

`reduced_density_matrix` takes a pure-state amplitude vector (whatever backend
produced it — QuTiP, cuQuantum, or a hand-built NumPy array) and returns the
reduced density matrix on a chosen subset of qubits. Keeping this independent
of QuTiP's `ptrace` lets the `entangled` / `separable` predicates run unchanged
against any backend's state vector. See `add-runtime-state-assertions` design
Decision 3.
"""

import string

import numpy as np


def reduced_density_matrix(
    state_vector: np.ndarray, n_qubits: int, keep: list[int]
) -> np.ndarray:
    """Reduce a pure state to the density matrix on the ``keep`` qubits.

    Args:
        state_vector: length-``2**n_qubits`` complex amplitude vector. Qubit 0
            is the most significant bit (big-endian), matching the convention
            used by the compiled-circuit state-vector snapshots.
        n_qubits: total number of qubits in ``state_vector``.
        keep: qubit indices to retain; all others are traced out. The returned
            matrix is ordered by ascending kept-qubit index.

    Returns:
        A ``(2**k, 2**k)`` density matrix where ``k = len(keep)``.
    """
    if not keep:
        raise ValueError("reduced_density_matrix: `keep` must be non-empty")
    keep = sorted(set(keep))
    if keep[0] < 0 or keep[-1] >= n_qubits:
        raise ValueError(
            f"reduced_density_matrix: keep={keep} out of range for "
            f"n_qubits={n_qubits}"
        )

    psi = np.asarray(state_vector, dtype=complex).reshape([2] * n_qubits)

    # A single einsum expresses the whole partial trace in one pass (clearer and
    # faster than an explicit per-amplitude loop): traced qubits share an index
    # between the ket and the (conjugated) bra so they get summed, while kept
    # qubits get a fresh bra index so they survive into the output ρ.
    letters = string.ascii_letters
    ket_idx = list(range(n_qubits))
    bra_idx = list(range(n_qubits))
    out_ket: list[int] = []
    out_bra: list[int] = []
    next_idx = n_qubits
    for q in range(n_qubits):
        if q in keep:
            bra_idx[q] = next_idx
            next_idx += 1
            out_ket.append(ket_idx[q])
            out_bra.append(bra_idx[q])

    subscripts = (
        "".join(letters[i] for i in ket_idx)
        + ","
        + "".join(letters[i] for i in bra_idx)
        + "->"
        + "".join(letters[i] for i in out_ket + out_bra)
    )
    rho = np.einsum(subscripts, psi, psi.conj())

    dim = 2 ** len(keep)
    return rho.reshape(dim, dim)


def purity(rho: np.ndarray) -> float:
    """Return ``Tr(ρ²)`` — 1 for a pure state, ``1/d`` for maximally mixed."""
    return float(np.real(np.trace(rho @ rho)))
