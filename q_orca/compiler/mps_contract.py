"""MPS transfer-matrix contraction for the CNOT-staircase concept gram.

Companion to :mod:`q_orca.compiler.concept_gram_mps`. The parent module
parses an MPS-encoded machine into an ordered list of staircase
operations (``Ry``, ``Rz``, ``CNOT``) and historically simulated each
concept state explicitly as a length-``2**n`` complex vector, then took
inner products pairwise. That path is O(2^n) per state and OOMs past
~25 qubits.

This module replaces the 2^n simulation with a direct construction of
the matrix-product-state (MPS) tensors for the prepared state, plus a
transfer-matrix contraction for inner products. The shape of the
staircase guarantees Schmidt rank 2 across every adjacent cut, so the
bond dimension stays at chi=2 and the per-state storage is O(n * chi^2)
= O(n) complex numbers --- constant in n at fixed chi.

The conversion recipe
---------------------

A single-qubit operation on the staircase modifies the corresponding
per-site tensor in place::

    Ry(qubit k, theta): A^[k][L, s', R] = sum_s Ry(theta)[s', s] * A^[k][L, s, R]
    Rz(qubit k, theta): A^[k][L, s', R] = sum_s Rz(theta)[s', s] * A^[k][L, s, R]

A CNOT on adjacent qubits (control = k, target = k+1) couples the two
sites. We contract the shared bond, apply the CNOT permutation on the
physical indices, and SVD-decompose the resulting (chi_L * 2, 2 * chi_R)
matrix back into a left and a right tensor with bond dimension at most
chi=2. The staircase pattern guarantees rank <= 2 here, so the
truncation is exact.

The contraction
---------------

For two MPS lists ``A`` and ``B`` representing states ``|psi_a>`` and
``|psi_b>``, the inner product ``<psi_a | psi_b>`` is computed by
sweeping a 2x2 environment matrix ``E`` from the left edge to the right
edge::

    E_new[a', b'] = sum_{a, b, s} E[a, b] * conj(A^[k][a, s, a']) * B^[k][b, s, b']

After all n sites the environment reduces to a 1x1 scalar that is the
overlap. Per-step cost is O(chi^4 * d) = O(64) at chi=2, d=2; total cost
per overlap is O(n * chi^6) = O(64 * n). Memory is O(chi^2) = O(1) in
n.

References
----------

Schollwock, "The density-matrix renormalization group in the age of
matrix product states", Annals of Physics 326 (2011) 96-192 --- the
canonical introduction to MPS arithmetic. Section 4.5 covers the
transfer-matrix contraction we implement here; section 4.1.3 covers
the gate-by-gate construction.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np


_MAX_BOND_DIM = 2


def _ry_matrix(np_module, theta: float):
    c = np_module.cos(theta / 2.0)
    s = np_module.sin(theta / 2.0)
    return np_module.array([[c, -s], [s, c]], dtype=complex)


def _rz_matrix(np_module, theta: float):
    half = theta / 2.0
    return np_module.array(
        [
            [np_module.exp(-1j * half), 0.0],
            [0.0, np_module.exp(1j * half)],
        ],
        dtype=complex,
    )


def _evaluate_angle(
    coeffs: dict, param_names: list, bound: list
) -> float:
    angle = 0.0
    for name, c in coeffs.items():
        idx = param_names.index(name)
        angle += c * bound[idx]
    return angle


def _apply_1q(np_module, tensor, U):
    """Apply a 2x2 gate to a per-site MPS tensor's physical index.

    ``tensor`` has shape ``(chi_L, 2, chi_R)``; we contract the gate
    matrix ``U`` (shape ``(2, 2)``) against the physical index in the
    middle.
    """
    # tensor[L, s, R] -> tensor[L, s', R] = sum_s U[s', s] * tensor[L, s, R]
    return np_module.einsum("ts,Lsr->Ltr", U, tensor)


def _apply_cnot(np_module, A_c, A_t):
    """Apply CNOT(control, target) to an adjacent pair (left, right).

    ``A_c`` is the control-qubit tensor (left in the chain) and ``A_t``
    is the target-qubit tensor (right in the chain). Both have shape
    ``(chi_L, 2, chi_M)`` and ``(chi_M, 2, chi_R)``. We contract on the
    shared bond, apply the CNOT permutation on the joint physical
    indices, and SVD-decompose back into two tensors with a new middle
    bond of size at most ``_MAX_BOND_DIM``.

    CNOT acts as ``|s_c, s_t> -> |s_c, s_c XOR s_t>``. In tensor form
    that means ``T'[L, c, d, R] = T[L, c, c XOR d, R]``.
    """
    # Contract the shared bond: T[L, s_c, s_t, R].
    T = np_module.einsum("Lsm,mtr->Lstr", A_c, A_t)
    L, _, _, R = T.shape

    # Apply the CNOT permutation on (s_c, s_t).
    T2 = np_module.empty_like(T)
    T2[:, 0, 0, :] = T[:, 0, 0, :]
    T2[:, 0, 1, :] = T[:, 0, 1, :]
    T2[:, 1, 0, :] = T[:, 1, 1, :]
    T2[:, 1, 1, :] = T[:, 1, 0, :]

    # SVD-decompose back into left and right tensors. The staircase
    # guarantees rank <= _MAX_BOND_DIM at this cut, so the truncation
    # is exact (we strip only zero singular values).
    M = T2.reshape(L * 2, 2 * R)
    U, S, Vh = np_module.linalg.svd(M, full_matrices=False)
    chi = min(_MAX_BOND_DIM, len(S))
    U = U[:, :chi]
    S = S[:chi]
    Vh = Vh[:chi, :]
    A_c_new = (U * S).reshape(L, 2, chi)
    A_t_new = Vh.reshape(chi, 2, R)
    return A_c_new, A_t_new


def staircase_to_mps_tensors(
    ops: list, n_qubits: int, angle_values, param_names: list
) -> list:
    """Build per-site MPS tensors for a staircase circuit applied to |0^n>.

    Parameters
    ----------
    ops:
        Parsed staircase operations as returned by
        :func:`q_orca.compiler.concept_gram_mps._parse_staircase_effect`.
        Each entry is one of:

        - ``("ry", qubit, coeffs)`` --- single-qubit Ry rotation.
        - ``("rz", qubit, coeffs)`` --- single-qubit Rz phase rotation.
        - ``("cnot", control, target)`` --- CNOT on adjacent qubits.
    n_qubits:
        Size of the qubit register.
    angle_values:
        Numpy array (or list) of bound angle values for the call site,
        positionally aligned with ``param_names``.
    param_names:
        Action parameter names. Each ``coeffs`` dict in ``ops`` references
        a subset of these names; the angle expression is evaluated as the
        linear combination ``sum_i coeffs[name_i] * angle_values[i]``.

    Returns
    -------
    list[np.ndarray]
        ``n_qubits`` tensors. The k-th tensor has shape
        ``(chi_L, 2, chi_R)`` with ``chi_L = 1`` for ``k == 0``,
        ``chi_R = 1`` for ``k == n_qubits - 1``, and intermediate bonds
        of size ``<= _MAX_BOND_DIM`` (currently 2). Tensors are
        complex128.
    """
    import numpy as np

    bound = list(angle_values)
    tensors = []
    for _ in range(n_qubits):
        T = np.zeros((1, 2, 1), dtype=complex)
        T[0, 0, 0] = 1.0
        tensors.append(T)

    for op in ops:
        kind = op[0]
        if kind == "ry":
            _, qubit, coeffs = op
            theta = _evaluate_angle(coeffs, param_names, bound)
            tensors[qubit] = _apply_1q(np, tensors[qubit], _ry_matrix(np, theta))
        elif kind == "rz":
            _, qubit, coeffs = op
            theta = _evaluate_angle(coeffs, param_names, bound)
            tensors[qubit] = _apply_1q(np, tensors[qubit], _rz_matrix(np, theta))
        elif kind == "cnot":
            _, control, target = op
            if target != control + 1:
                raise AssertionError(
                    f"staircase_to_mps_tensors expects CNOT(k, k+1); "
                    f"got CNOT({control}, {target})"
                )
            A_c_new, A_t_new = _apply_cnot(np, tensors[control], tensors[target])
            tensors[control] = A_c_new
            tensors[target] = A_t_new
        else:  # pragma: no cover - defensive; parser filters
            raise AssertionError(f"unexpected op kind {kind!r}")

    return tensors


def mps_overlap(tensors_a: list, tensors_b: list) -> complex:
    """Compute ``<psi_a | psi_b>`` via left-to-right environment sweep.

    Both ``tensors_a`` and ``tensors_b`` are per-site MPS tensor lists of
    equal length, with matching physical dimension (2) at every site.
    Their bond dimensions need not match.

    Returns the complex inner product. For normalised MPS the magnitude
    is in ``[0, 1]``.
    """
    import numpy as np

    n = len(tensors_a)
    if len(tensors_b) != n:
        raise AssertionError(
            f"mps_overlap: tensor lists differ in length ({n} vs "
            f"{len(tensors_b)})"
        )

    # E[a, b] is the partial environment between the chains at the
    # current cut. Start with the (1, 1) left-edge environment = [[1]].
    E = np.array([[1.0 + 0j]], dtype=complex)
    for k in range(n):
        A = tensors_a[k]
        B = tensors_b[k]
        # E_new[a', b'] = sum_{a, b, s} E[a, b] * conj(A[a, s, a']) * B[b, s, b']
        E = np.einsum("ab,asA,bsB->AB", E, A.conj(), B)
    # Right edge: both chains end with chi_R = 1, so E is 1x1.
    return complex(E[0, 0])


def mps_gram(tensor_lists: list) -> "np.ndarray":
    """Compute the N x N overlap matrix from a list of MPS tensor lists.

    Exploits Hermitian symmetry: only computes the upper triangle
    (i <= j) and mirrors the conjugate to the lower triangle. Diagonal
    entries (self-overlaps) are computed directly --- they should be
    real and have unit modulus for normalised states.
    """
    import numpy as np

    N = len(tensor_lists)
    G = np.zeros((N, N), dtype=complex)
    for i in range(N):
        for j in range(i, N):
            G[i, j] = mps_overlap(tensor_lists[i], tensor_lists[j])
            if i != j:
                G[j, i] = G[i, j].conjugate()
    return G
