"""MPS-encoded concept Gram matrix analysis.

Optional analysis utility for machines that follow the *MPS (matrix
product state) hierarchical polysemantic* concept-encoding convention
documented in ``add-mps-concept-encoding`` (and corrected in
``fix-mps-encoding-non-factorizing``). The CNOT-staircase preparation
lifts the rung-0 product-state ansatz from ``compute_concept_gram`` to
a bond-2 entangled family that admits a *four*-tier Gram structure
(self / sub-cluster / super-group / cross-group), one tier richer than
the product-state helper.

Convention assumed by this helper:

1. A single parametric concept action (preparation *or* its inverse)
   with signature ``(qs, p_0: angle, p_1: angle, ..., p_{n-1}: angle)
   -> qs`` — exactly ``n`` angle parameters where ``n`` matches the
   size of the ``qubits`` register declared in ``## context``.
2. A CNOT-staircase effect, either the preparation form
   ``Ry(qs[0], <expr_0>); CNOT(qs[0], qs[1]); Ry(qs[1], <expr_1>);
   CNOT(qs[1], qs[2]); ... Ry(qs[n-1], <expr_{n-1}>)`` or the inverse
   form (Ry order reversed, expressions negated, CNOTs self-inverse so
   they reappear in reversed position). Each ``<expr_k>`` SHALL be a
   *linear combination of the action's bound angle parameters* — i.e.,
   a sum of terms each of the form ``c · p`` where ``c`` is an
   optional numeric coefficient (defaulting to 1) and ``p`` is one of
   the action's angle parameter names. A single bound parameter
   (``Ry(qs[0], a)``) is the degenerate one-term linear combination
   ``1·a`` and is accepted. The default
   ``concept_action_label="query_concept"`` targets the inverse (query)
   form used by the canonical example.
3. ``N >= 1`` call sites to that action in the transitions table,
   each with a literal ``n``-tuple of angle arguments.

Given such a machine, ``compute_concept_gram_mps`` enumerates the
call sites in declaration order, evaluates each Ry's linear-combination
angle expression at the call site's bound argument values, builds the
statevector ``|c_i> = <staircase circuit at angles_i> |0^n>``, and
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

import ast
import re
from typing import TYPE_CHECKING

from q_orca.ast import QActionSignature, QMachineDef
from q_orca.compiler.qasm import _infer_qubit_count

if TYPE_CHECKING:
    import numpy as np


class MpsGramConfigurationError(ValueError):
    """Raised when a machine doesn't meet the MPS concept-gram convention.

    The ``kind`` attribute (when set) classifies the failure mode:

    - ``unrecognized_angle_expression``: a Ry segment's angle expression
      is not a linear combination of the action's bound angle parameters
      (e.g., ``a * b``, ``sin(a)``, ``a^2``, or a bare numeric literal).
    """

    def __init__(self, message: str, *, kind: str | None = None):
        super().__init__(message)
        self.kind = kind


# A single Ry segment, e.g. `Ry(qs[0], a)`, `Ry(qs[2], -c)`, or
# `Ry(qs[1], a + b)`. The angle expression is captured as a string and
# parsed separately as a linear combination of the action's bound
# angle parameters (see `_parse_linear_combination`).
_RY_SEGMENT_RE = re.compile(
    r"^\s*Ry\s*\(\s*qs\[\s*(?P<qubit>\d+)\s*\]\s*,\s*"
    r"(?P<expr>.+?)\s*\)\s*$"
)

# A single CNOT segment, e.g. `CNOT(qs[0], qs[1])`.
_CNOT_SEGMENT_RE = re.compile(
    r"^\s*CNOT\s*\(\s*qs\[\s*(?P<control>\d+)\s*\]\s*,\s*"
    r"qs\[\s*(?P<target>\d+)\s*\]\s*\)\s*$"
)


# Sentinel returned by `_parse_linear_combination` for non-linear
# expressions; the caller raises `MpsGramConfigurationError` with kind
# `unrecognized_angle_expression`.
class _NonLinearExpr(Exception):
    pass


def _parse_linear_combination(
    expr: str, param_names: list[str]
) -> dict[str, float]:
    """Parse ``expr`` as a linear combination of ``param_names``.

    Returns a ``{param_name: coefficient}`` mapping; parameters not
    referenced by the expression are absent from the mapping.

    Raises ``_NonLinearExpr`` if the expression is not a linear
    combination — e.g., contains products of two parameters
    (``a * b``), function calls (``sin(a)``), exponentiation (``a**2``),
    or bare numeric literals with no parameter reference. The caller
    converts this into ``MpsGramConfigurationError`` with kind
    ``unrecognized_angle_expression``.
    """
    try:
        tree = ast.parse(expr, mode="eval").body
    except SyntaxError as e:  # pragma: no cover - defensive
        raise _NonLinearExpr(f"syntax error: {e}") from e

    coeffs: dict[str, float] = {}

    def add(name: str, value: float) -> None:
        if name not in param_names:
            raise _NonLinearExpr(
                f"unknown identifier {name!r}; expected one of "
                f"{param_names}"
            )
        coeffs[name] = coeffs.get(name, 0.0) + value

    def walk(node: ast.AST, sign: float) -> None:
        if isinstance(node, ast.Name):
            add(node.id, sign)
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            walk(node.operand, -sign)
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.UAdd):
            walk(node.operand, sign)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            walk(node.left, sign)
            walk(node.right, sign)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Sub):
            walk(node.left, sign)
            walk(node.right, -sign)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
            left, right = node.left, node.right
            if (
                isinstance(left, ast.Constant)
                and isinstance(left.value, (int, float))
                and isinstance(right, ast.Name)
            ):
                add(right.id, sign * float(left.value))
            elif (
                isinstance(right, ast.Constant)
                and isinstance(right.value, (int, float))
                and isinstance(left, ast.Name)
            ):
                add(left.id, sign * float(right.value))
            else:
                raise _NonLinearExpr(
                    "product of two non-constant terms is not a "
                    "linear combination"
                )
        elif isinstance(node, ast.Constant):
            raise _NonLinearExpr(
                f"bare numeric literal {node.value!r} is not a linear "
                f"combination of bound parameters"
            )
        else:
            raise _NonLinearExpr(
                f"unsupported expression node {type(node).__name__}"
            )

    walk(tree, 1.0)
    return coeffs


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
) -> tuple[bool, list[dict[str, float]]]:
    """Parse a CNOT-staircase effect.

    Returns ``(is_inverse, ry_coeffs)`` where ``ry_coeffs[i]`` is the
    parsed linear combination (``{param_name: coefficient}``) for the
    Ry rotation acting on qubit ``i`` in *qubit-index order* (so
    ``ry_coeffs[0]`` is the Ry on qs[0] regardless of which end of the
    staircase the gate appears at).

    Accepts either the preparation form
    ``Ry(qs[0], <expr_0>); CNOT(qs[0], qs[1]); ...; Ry(qs[n-1],
    <expr_{n-1}>)`` or the inverse form ``Ry(qs[n-1], <expr_{n-1}'>);
    CNOT(qs[n-2], qs[n-1]); ...; Ry(qs[0], <expr_0'>)``. Each ``<expr>``
    SHALL be a linear combination of the action's bound angle parameters
    (see `_parse_linear_combination`); the canonical inverse form uses
    the negation of the prep form's expressions, but this helper does
    not enforce a sign convention — it evaluates whatever linear
    combination the user wrote.

    Raises ``MpsGramConfigurationError`` on any deviation from the
    staircase shape or on a non-linear angle expression.
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

    param_names = [p.name for p in action.parameters]

    # The staircase alternates Ry, CNOT, Ry, CNOT, ..., Ry. Both prep and
    # inverse forms preserve that alternation; they differ only in
    # qubit ordering. Each Ry's angle expression is parsed as a linear
    # combination of the action's bound parameters.
    parsed_ry: list[tuple[int, dict[str, float]]] = []
    parsed_cnot: list[tuple[int, int]] = []
    for idx, seg in enumerate(segments):
        if idx % 2 == 0:
            m = _RY_SEGMENT_RE.match(seg)
            if not m:
                raise MpsGramConfigurationError(
                    f"machine {machine.name!r}: action {action.name!r} "
                    f"effect segment {seg!r} (position {idx}) is not of "
                    f"the form `Ry(qs[i], <expr>)`; the CNOT staircase "
                    f"requires Ry rotations at even positions"
                )
            qubit = int(m.group("qubit"))
            expr = m.group("expr")
            try:
                coeffs = _parse_linear_combination(expr, param_names)
            except _NonLinearExpr as e:
                raise MpsGramConfigurationError(
                    f"machine {machine.name!r}: action {action.name!r} "
                    f"Ry(qs[{qubit}], {expr}): angle expression "
                    f"{expr!r} is not a linear combination of the "
                    f"action's bound angle parameters {param_names} "
                    f"({e}). mps concept-gram accepts angle expressions "
                    f"of the form `c_0·p_0 + c_1·p_1 + ...` (sums of "
                    f"terms, each an optional numeric coefficient times "
                    f"a single bound parameter name)",
                    kind="unrecognized_angle_expression",
                ) from e
            parsed_ry.append((qubit, coeffs))
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

    # Determine prep vs inverse from the qubit ordering of the Ry
    # rotations (the one structural feature the two forms differ on
    # that doesn't depend on user-chosen sign conventions).
    actual_ry_qubits = [q for q, _ in parsed_ry]
    prep_qubits = list(range(n_qubits))
    inverse_qubits = list(range(n_qubits - 1, -1, -1))
    if actual_ry_qubits == prep_qubits:
        is_inverse = False
        expected_cnots = [(k, k + 1) for k in range(n_qubits - 1)]
    elif actual_ry_qubits == inverse_qubits:
        is_inverse = True
        expected_cnots = [(k, k + 1) for k in range(n_qubits - 2, -1, -1)]
    else:
        raise MpsGramConfigurationError(
            f"machine {machine.name!r}: action {action.name!r} effect "
            f"{effect!r} applies Ry on qubits {actual_ry_qubits}; the "
            f"CNOT staircase requires Ry on qubits {prep_qubits} "
            f"(preparation form) or {inverse_qubits} (inverse form)"
        )

    if parsed_cnot != expected_cnots:
        raise MpsGramConfigurationError(
            f"machine {machine.name!r}: action {action.name!r} effect "
            f"{effect!r} has CNOTs {parsed_cnot}; the "
            f"{'inverse' if is_inverse else 'preparation'} CNOT "
            f"staircase requires adjacent CNOTs {expected_cnots}"
        )

    # Re-index the Ry coefficients by qubit so callers can look up
    # ``ry_coeffs[k]`` for the rotation on ``qs[k]`` regardless of the
    # gate-order in which it appeared.
    ry_coeffs: list[dict[str, float]] = [None] * n_qubits  # type: ignore[list-item]
    for qubit, coeffs in parsed_ry:
        ry_coeffs[qubit] = coeffs

    return is_inverse, ry_coeffs


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


def _evaluate_ry_angle(
    coeffs: dict[str, float], param_names: list[str], bound: list[float]
) -> float:
    """Substitute ``bound[i]`` for ``param_names[i]`` in the linear
    combination ``coeffs`` and return the resulting float angle."""
    angle = 0.0
    for name, c in coeffs.items():
        idx = param_names.index(name)
        angle += c * bound[idx]
    return angle


def _build_concept_state(
    np_module,
    n_qubits: int,
    bound: list[float],
    is_inverse: bool,
    param_names: list[str],
    ry_coeffs: list[dict[str, float]],
):
    """Build |c_i> for a single call site under the given bound-argument tuple.

    ``bound[k]`` is the literal value bound to the parameter at
    signature position ``k``. Each Ry's float angle is computed by
    evaluating ``ry_coeffs[k]`` (a ``{param_name: coefficient}``
    dictionary) under the ``bound`` substitution.
    """
    state = np_module.zeros((2,) * n_qubits, dtype=complex)
    state[(0,) * n_qubits] = 1.0

    if is_inverse:
        # Inverse: Ry(qs[n-1], <expr>); CNOT(n-2, n-1); ...;
        # Ry(qs[1], <expr>); CNOT(0, 1); Ry(qs[0], <expr>).
        for k in range(n_qubits - 1, -1, -1):
            theta = _evaluate_ry_angle(ry_coeffs[k], param_names, bound)
            state = _apply_1q(
                np_module, state, _ry_matrix(np_module, theta), k
            )
            if k > 0:
                state = _apply_cnot(np_module, state, k - 1, k)
    else:
        # Prep: Ry(qs[0], <expr>); CNOT(0, 1); Ry(qs[1], <expr>); ...;
        # CNOT(n-2, n-1); Ry(qs[n-1], <expr>).
        for k in range(n_qubits):
            theta = _evaluate_ry_angle(ry_coeffs[k], param_names, bound)
            state = _apply_1q(
                np_module, state, _ry_matrix(np_module, theta), k
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
    is_inverse, ry_coeffs = _parse_staircase_effect(machine, action, n_qubits)
    param_names = [p.name for p in action.parameters]

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

    for t in call_sites:
        if len(t.bound_arguments) != n_qubits:
            raise MpsGramConfigurationError(
                f"machine {machine.name!r}: call site to "
                f"{concept_action_label!r} has {len(t.bound_arguments)} "
                f"arguments; expected exactly {n_qubits} angle literals "
                f"(one per qubit in the register)"
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
        _build_concept_state(
            np, n_qubits, angles[i].tolist(), is_inverse,
            param_names, ry_coeffs,
        )
        for i in range(n_calls)
    ]
    flat_states = [s.reshape(-1) for s in states]

    gram = np.zeros((n_calls, n_calls), dtype=complex)
    for i in range(n_calls):
        for j in range(n_calls):
            gram[i, j] = np.vdot(flat_states[i], flat_states[j])
    return gram
