"""MPS-encoded concept Gram matrix analysis.

Optional analysis utility for machines that follow the *MPS (matrix
product state) hierarchical polysemantic* concept-encoding convention
documented in ``add-mps-concept-encoding``. The CNOT-staircase
preparation lifts the rung-0 product-state ansatz from
``compute_concept_gram`` to a bond-2 entangled family that admits a
*four*-tier Gram structure (self / sub-cluster / super-group /
cross-group), one tier richer than the product-state helper.

Convention assumed by this helper:

1. A single parametric concept action (preparation *or* its inverse)
   with signature ``(qs, p_0: angle, p_1: angle, ..., p_{n-1}: angle)
   -> qs`` — exactly ``n`` angle parameters where ``n`` matches the
   size of the ``qubits`` register declared in ``## context``.
2. A CNOT-staircase effect, either the preparation form
   ``Ry(qs[0], p_0); CNOT(qs[0], qs[1]); Ry(qs[1], p_1);
   CNOT(qs[1], qs[2]); ... Ry(qs[n-1], p_{n-1})`` or the inverse
   form (gate order reversed, angle signs negated, CNOTs self-
   inverse). The default ``concept_action_label="query_concept"``
   targets the inverse (query) form used by the canonical example.
3. ``N >= 1`` call sites to that action in the transitions table,
   each with a literal ``n``-tuple of angle arguments.

Given such a machine, ``compute_concept_gram_mps`` enumerates the
call sites in declaration order, builds the statevector
``|c_i> = <staircase circuit at angles_i> |0^n>`` for each, and
returns the ``N x N`` matrix with ``gram[i, j] = <c_i | c_j>``.

The helper is **not** on the main compile / verify / simulate path;
it exists for demos and tests that want to assert the four-tier
Gram signature of a hierarchical polysemantic example. It coexists
with ``compute_concept_gram`` (rung 0, product state); the caller
picks based on which preparation convention the example uses.

Implementation note: the present implementation uses an explicit
``2^n`` statevector simulation, which is fine for the shipped
``n = 3`` example. The asymptotically-correct ``O(n * chi^6)``
transfer-matrix contraction is tracked under tech-debt-backlog as a
future optimization for larger ``n``.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from q_orca.ast import QActionSignature, QMachineDef
from q_orca.compiler.qasm import _infer_qubit_count

if TYPE_CHECKING:
    import numpy as np


class MpsGramConfigurationError(ValueError):
    """Raised when a machine doesn't meet the MPS concept-gram convention."""


# A single Ry segment, e.g. `Ry(qs[0], a)` or `Ry(qs[2], -c)`.
_RY_SEGMENT_RE = re.compile(
    r"^\s*Ry\s*\(\s*qs\[\s*(?P<qubit>\d+)\s*\]\s*,\s*"
    r"(?P<sign>-?)\s*(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\)\s*$"
)

# A single CNOT segment, e.g. `CNOT(qs[0], qs[1])`.
_CNOT_SEGMENT_RE = re.compile(
    r"^\s*CNOT\s*\(\s*qs\[\s*(?P<control>\d+)\s*\]\s*,\s*"
    r"qs\[\s*(?P<target>\d+)\s*\]\s*\)\s*$"
)


def _find_concept_action(
    machine: QMachineDef, label: str
) -> QActionSignature:
    for a in machine.actions:
        if a.name == label:
            return a
    available = [a.name for a in machine.actions if a.parameters]
    raise MpsGramConfigurationError(
        f"machine {machine.name!r}: no parametric action named "
        f"{label!r}; available parametric actions: {available}"
    )


def _check_signature(
    machine: QMachineDef, action: QActionSignature, n_qubits: int
) -> None:
    params = action.parameters
    if len(params) != n_qubits or any(p.type != "angle" for p in params):
        shape = [(p.name, p.type) for p in params]
        raise MpsGramConfigurationError(
            f"machine {machine.name!r}: action {action.name!r} has "
            f"signature parameters {shape}; mps concept-gram requires "
            f"exactly {n_qubits} angle parameters (one per qubit in the "
            f"register)"
        )


def _parse_staircase_effect(
    machine: QMachineDef, action: QActionSignature, n_qubits: int
) -> tuple[bool, list[tuple[int, str]]]:
    """Parse a CNOT-staircase effect.

    Returns ``(is_inverse, [(qubit, param_name), ...])`` where the list
    has length ``n_qubits`` in *signature-positional order* (so entry
    ``k`` is the param bound to ``qs[k]``).

    Accepts either the preparation form
    ``Ry(qs[0], p_0); CNOT(qs[0], qs[1]); ...; Ry(qs[n-1], p_{n-1})``
    or the inverse form
    ``Ry(qs[n-1], -p_{n-1}); CNOT(qs[n-2], qs[n-1]); ...;
    Ry(qs[0], -p_0)``.

    Raises ``MpsGramConfigurationError`` on any deviation.
    """
    effect = (action.effect or "").strip()
    segments = [s.strip() for s in effect.split(";") if s.strip()]
    expected_len = 2 * n_qubits - 1
    if len(segments) != expected_len:
        raise MpsGramConfigurationError(
            f"machine {machine.name!r}: action {action.name!r} effect "
            f"{effect!r} has {len(segments)} gate segment(s); the CNOT "
            f"staircase on {n_qubits} qubits requires exactly "
            f"{expected_len} segments ({n_qubits} Ry rotations and "
            f"{n_qubits - 1} adjacent CNOTs, alternating)"
        )

    # The staircase alternates Ry, CNOT, Ry, CNOT, ..., Ry. Both prep and
    # inverse forms preserve that alternation; they differ only in
    # qubit/angle ordering and angle sign.
    parsed_ry: list[tuple[int, str, str]] = []  # (qubit, sign, name)
    parsed_cnot: list[tuple[int, int]] = []  # (control, target)
    for idx, seg in enumerate(segments):
        if idx % 2 == 0:
            m = _RY_SEGMENT_RE.match(seg)
            if not m:
                raise MpsGramConfigurationError(
                    f"machine {machine.name!r}: action {action.name!r} "
                    f"effect segment {seg!r} (position {idx}) is not of "
                    f"the form `Ry(qs[i], [-]name)`; the CNOT staircase "
                    f"requires Ry rotations at even positions"
                )
            parsed_ry.append(
                (int(m.group("qubit")), m.group("sign"), m.group("name"))
            )
        else:
            m = _CNOT_SEGMENT_RE.match(seg)
            if not m:
                raise MpsGramConfigurationError(
                    f"machine {machine.name!r}: action {action.name!r} "
                    f"effect segment {seg!r} (position {idx}) is not of "
                    f"the form `CNOT(qs[i], qs[j])`; the CNOT staircase "
                    f"requires CNOTs at odd positions"
                )
            parsed_cnot.append((int(m.group("control")), int(m.group("target"))))

    # Sign uniformity (all positive = prep, all negative = inverse).
    signs = {sign for _, sign, _ in parsed_ry}
    if len(signs) > 1:
        raise MpsGramConfigurationError(
            f"machine {machine.name!r}: action {action.name!r} effect "
            f"{effect!r} mixes positive and negated angle signs across "
            f"the {n_qubits} Ry gates; mps concept-gram accepts the "
            f"all-positive preparation form or the all-negated inverse "
            f"form, not a mix"
        )
    is_inverse = signs == {"-"}

    # Validate the qubit / CNOT pattern.
    if is_inverse:
        # Inverse form: Ry order is qs[n-1], qs[n-2], ..., qs[0];
        # CNOTs are (n-2, n-1), (n-3, n-2), ..., (0, 1).
        expected_ry_qubits = list(range(n_qubits - 1, -1, -1))
        expected_cnots = [(k, k + 1) for k in range(n_qubits - 2, -1, -1)]
    else:
        # Preparation form: Ry order is qs[0], qs[1], ..., qs[n-1];
        # CNOTs are (0, 1), (1, 2), ..., (n-2, n-1).
        expected_ry_qubits = list(range(n_qubits))
        expected_cnots = [(k, k + 1) for k in range(n_qubits - 1)]

    actual_ry_qubits = [q for q, _, _ in parsed_ry]
    if actual_ry_qubits != expected_ry_qubits:
        raise MpsGramConfigurationError(
            f"machine {machine.name!r}: action {action.name!r} effect "
            f"{effect!r} applies Ry on qubits {actual_ry_qubits}; the "
            f"{'inverse' if is_inverse else 'preparation'} CNOT "
            f"staircase requires Ry on qubits {expected_ry_qubits}"
        )

    if parsed_cnot != expected_cnots:
        raise MpsGramConfigurationError(
            f"machine {machine.name!r}: action {action.name!r} effect "
            f"{effect!r} has CNOTs {parsed_cnot}; the "
            f"{'inverse' if is_inverse else 'preparation'} CNOT "
            f"staircase requires adjacent CNOTs {expected_cnots}"
        )

    # Map each Ry's angle param-name back to its signature position
    # (= the qubit index it acts on, since both forms enumerate qubits
    # 0..n-1). Validate name matches the declared parameter at that
    # signature position.
    param_names = [p.name for p in action.parameters]
    by_qubit: list[tuple[int, str]] = [(0, "")] * n_qubits
    for qubit, _sign, name in parsed_ry:
        if name != param_names[qubit]:
            raise MpsGramConfigurationError(
                f"machine {machine.name!r}: action {action.name!r} effect "
                f"applies Ry on qs[{qubit}] with angle {name!r}, but "
                f"signature position {qubit} declares parameter "
                f"{param_names[qubit]!r}; mps concept-gram requires "
                f"positional alignment between angle parameters and "
                f"qubit indices"
            )
        by_qubit[qubit] = (qubit, name)

    return is_inverse, by_qubit


_RY = None  # type: ignore[var-annotated]
_CNOT = None  # type: ignore[var-annotated]


def _get_gates(np_module):
    """Return cached (CNOT_4x4) matrix; Ry is parameterized so built per call."""
    global _CNOT
    if _CNOT is None:
        _CNOT = np_module.array(
            [
                [1, 0, 0, 0],
                [0, 1, 0, 0],
                [0, 0, 0, 1],
                [0, 0, 1, 0],
            ],
            dtype=complex,
        )
    return _CNOT


def _ry_matrix(np_module, theta: float):
    c = np_module.cos(theta / 2.0)
    s = np_module.sin(theta / 2.0)
    return np_module.array([[c, -s], [s, c]], dtype=complex)


def _apply_1q(np_module, state, U, qubit: int):
    """Apply 2x2 gate ``U`` on ``qubit`` of statevector tensor ``state``."""
    state = np_module.moveaxis(state, qubit, 0)
    state = np_module.tensordot(U, state, axes=1)
    state = np_module.moveaxis(state, 0, qubit)
    return state


def _apply_cnot(np_module, state, control: int, target: int):
    """Apply CNOT(control, target) on statevector tensor ``state``."""
    cnot4 = _get_gates(np_module)
    U_t = cnot4.reshape(2, 2, 2, 2)
    state = np_module.moveaxis(state, [control, target], [0, 1])
    state = np_module.tensordot(U_t, state, axes=([2, 3], [0, 1]))
    state = np_module.moveaxis(state, [0, 1], [control, target])
    return state


def _build_concept_state(np_module, n_qubits: int, angles: list[float], is_inverse: bool):
    """Build |c_i> for a single call site under the given angle tuple.

    ``angles[k]`` is the literal value bound to the parameter at
    signature position ``k`` (i.e., the angle on ``qs[k]`` under the
    preparation form). The same tuple drives both forms — the inverse
    form negates each angle on the way to the matrix.
    """
    state = np_module.zeros((2,) * n_qubits, dtype=complex)
    state[(0,) * n_qubits] = 1.0

    if is_inverse:
        # Inverse: Ry(qs[n-1], -p_{n-1}); CNOT(n-2, n-1); ...;
        # Ry(qs[1], -p_1); CNOT(0, 1); Ry(qs[0], -p_0).
        for k in range(n_qubits - 1, -1, -1):
            state = _apply_1q(
                np_module, state, _ry_matrix(np_module, -angles[k]), k
            )
            if k > 0:
                state = _apply_cnot(np_module, state, k - 1, k)
    else:
        # Prep: Ry(qs[0], p_0); CNOT(0, 1); Ry(qs[1], p_1); ...;
        # CNOT(n-2, n-1); Ry(qs[n-1], p_{n-1}).
        for k in range(n_qubits):
            state = _apply_1q(
                np_module, state, _ry_matrix(np_module, angles[k]), k
            )
            if k < n_qubits - 1:
                state = _apply_cnot(np_module, state, k, k + 1)

    return state


def compute_concept_gram_mps(
    machine: QMachineDef,
    concept_action_label: str = "query_concept",
    bond_dim: int = 2,
) -> "np.ndarray":
    """Compute the N x N concept-overlap matrix for an MPS-encoded machine.

    Parameters
    ----------
    machine:
        A parsed ``QMachineDef`` whose ``concept_action_label`` action
        follows the CNOT-staircase MPS preparation convention (see
        module docstring).
    concept_action_label:
        Name of the parametric action whose call sites enumerate the
        N-concept dictionary. Default ``"query_concept"`` matches the
        canonical inverse-form action used by
        ``examples/larql-polysemantic-hierarchical.q.orca.md``.
    bond_dim:
        Reserved for future generalization. Currently fixed at ``2`` —
        any other value raises ``MpsGramConfigurationError``.

    Returns
    -------
    numpy.ndarray
        Complex-valued ``(N, N)`` matrix with
        ``gram[i, j] = <c_i | c_j>``. Real-valued in practice for the
        Ry+CNOT staircase encoding; the dtype is complex for forward
        compatibility.

    Raises
    ------
    MpsGramConfigurationError
        If the named action is missing, has the wrong signature, has
        an effect that isn't a CNOT-staircase, has zero call sites,
        or ``bond_dim != 2``.
    """
    # Lazy numpy import: this module is re-exported from the top-level
    # ``q_orca`` package, and numpy isn't part of the base install.
    import numpy as np

    if bond_dim != 2:
        raise MpsGramConfigurationError(
            f"compute_concept_gram_mps: bond_dim={bond_dim} is not yet "
            f"implemented; only bond_dim=2 is currently supported "
            f"(higher bond dimensions require multi-CNOT staircase "
            f"steps and a more general transfer-matrix contraction)"
        )

    n_qubits = _infer_qubit_count(machine)
    if n_qubits <= 0:
        raise MpsGramConfigurationError(
            f"machine {machine.name!r}: could not infer a qubit register "
            f"size; mps concept-gram requires a non-empty `qubits` list "
            f"in `## context`"
        )

    action = _find_concept_action(machine, concept_action_label)
    _check_signature(machine, action, n_qubits)
    is_inverse, _by_qubit = _parse_staircase_effect(machine, action, n_qubits)

    call_sites = [
        t for t in machine.transitions
        if t.action == concept_action_label and t.bound_arguments
    ]
    if not call_sites:
        raise MpsGramConfigurationError(
            f"machine {machine.name!r}: action {concept_action_label!r} "
            f"has no call sites in the transitions table; mps concept-"
            f"gram needs at least one parametric call site to enumerate"
        )

    angles = np.array(
        [[float(b.value) for b in t.bound_arguments] for t in call_sites],
        dtype=float,
    )
    n_calls = len(angles)

    # TODO(deferred): replace this 2^n statevector simulation with an
    # MPS transfer-matrix contraction in O(n * chi^6) per call site.
    # The current path is fine for the shipped n=3 hierarchical example
    # and is dominated by the O(N^2) Gram double-loop below; the
    # asymptotic statevector cost only bites once n grows past ~8.
    # Sketch of the contraction: build a per-site `T_k = sum_b A_k^b
    # \otimes A_k^b\dagger` rank-4 transfer matrix from the staircase
    # MPS tensors `A_k`, then contract along the chain to obtain
    # `gram[i, j]` without ever materializing the 2^n statevector. See
    # the research note `docs/research/polysemantic-encoding-beyond-
    # product-states.md` for the closed-form derivation.
    states = [
        _build_concept_state(np, n_qubits, angles[i].tolist(), is_inverse)
        for i in range(n_calls)
    ]
    flat_states = [s.reshape(-1) for s in states]

    gram = np.zeros((n_calls, n_calls), dtype=complex)
    for i in range(n_calls):
        for j in range(n_calls):
            gram[i, j] = np.vdot(flat_states[i], flat_states[j])
    return gram
