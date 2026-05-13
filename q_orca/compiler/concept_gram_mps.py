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
   with signature ``(qs, p_0: angle, p_1: angle, ..., p_{m-1}: angle)
   -> qs`` — at least one parameter, and *all* parameters of type
   ``angle``. The parameter count ``m`` need not match the qubit
   register size ``n``; it is set by the action's effect, not by the
   register.
2. A CNOT-staircase effect on ``n`` qubits, in either the preparation
   form ``Ry(qs[0], <expr_0>); CNOT(qs[0], qs[1]); Ry(qs[1], <expr_1>);
   CNOT(qs[1], qs[2]); ... Ry(qs[n-1], <expr_{n-1}>)`` or the inverse
   form (Ry order reversed, expressions negated, CNOTs self-inverse so
   they reappear in reversed position). Optional ``Rz(qs[k], <expr>)``
   phase-knob rotations may appear anywhere in the effect string —
   ``Rz`` is 1-qubit and preserves the bond-2 MPS structure (Schmidt
   rank unchanged across the middle bond). Each ``<expr>`` SHALL be a
   *linear combination of the action's bound angle parameters* — i.e.,
   a sum of terms each of the form ``c · p`` where ``c`` is an
   optional numeric coefficient (defaulting to 1) and ``p`` is one of
   the action's angle parameter names. A single bound parameter
   (``Ry(qs[0], a)``) is the degenerate one-term linear combination
   ``1·a`` and is accepted. The default
   ``concept_action_label="query_concept"`` targets the inverse (query)
   form used by ``larql-polysemantic-hierarchical.q.orca.md``; examples
   using ``Rz`` knobs SHOULD enumerate the preparation form instead,
   because the inverse-form symmetry that lets the helper compute the
   prep-form Gram from inverse-form states breaks once ``Rz`` enters
   the staircase (the inverse's ``Rz`` acts on ``|0>`` and collapses
   to a global phase). See
   ``examples/larql-animals-interference.q.orca.md`` for the
   prep-form pattern.
3. ``N >= 1`` call sites to that action in the transitions table,
   each with a literal ``m``-tuple of angle arguments matching the
   action's signature length.

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
from q_orca.compiler.util import infer_qubit_count

if TYPE_CHECKING:
    import numpy as np


class MpsGramConfigurationError(ValueError):
    """Raised when a machine doesn't meet the MPS concept-gram convention.

    The ``kind`` attribute (when set) classifies the failure mode:

    - ``unrecognized_angle_expression``: a Ry/Rz segment's angle
      expression is not a linear combination of the action's bound angle
      parameters (e.g., ``a * b``, ``sin(a)``, ``a^2``, or a bare
      numeric literal).
    - ``rz_in_inverse_form``: the action effect is in inverse (query)
      form and contains a non-trivial ``Rz`` segment. The helper builds
      states by applying the effect to ``|0^n>``; in the inverse form
      the ``Rz`` lands on ``|0>`` and degrades to a global phase, so the
      analytic Gram would silently lose the phase axis. Examples using
      ``Rz`` knobs SHALL enumerate the preparation form.

    Other configuration errors (signature shape, staircase skeleton,
    out-of-range qubits, unknown gate kinds, etc.) are raised without a
    ``kind`` attribute — callers fall through to message inspection.
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

# A single Rz segment, e.g. `Rz(qs[0], phi_dog)`, `Rz(qs[1], -phi_dog)`,
# or `Rz(qs[0], phi_a + phi_b)`. Same linear-combination angle parser as
# Ry. Rz gates are 1-qubit phase rotations and are accepted anywhere in
# the staircase as an "interference knob" — they preserve the bond-2
# MPS structure (Schmidt rank unchanged across the middle bond) but
# perturb the Gram amplitudes.
_RZ_SEGMENT_RE = re.compile(
    r"^\s*Rz\s*\(\s*qs\[\s*(?P<qubit>\d+)\s*\]\s*,\s*"
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

    def _as_numeric_const(n: ast.AST) -> float | None:
        """Return the numeric value of a Constant, or of a unary
        ``+``/``-`` wrapping a numeric constant (so both ``2`` and
        ``-2`` register as numeric coefficients in a Mult node). Returns
        ``None`` otherwise."""
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return float(n.value)
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.USub):
            inner = _as_numeric_const(n.operand)
            return None if inner is None else -inner
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.UAdd):
            return _as_numeric_const(n.operand)
        return None

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
            left_val = _as_numeric_const(node.left)
            right_val = _as_numeric_const(node.right)
            if left_val is not None and right_val is not None:
                raise _NonLinearExpr(
                    "product of two numeric constants has no parameter "
                    "reference"
                )
            if left_val is not None:
                walk(node.right, sign * left_val)
            elif right_val is not None:
                walk(node.left, sign * right_val)
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
    if not params or any(p.type != "angle" for p in params):
        shape = [(p.name, p.type) for p in params]
        raise MpsGramConfigurationError(
            f"machine {machine.name!r}: action {action.name!r} has "
            f"signature parameters {shape}; mps concept-gram requires "
            f"at least one parameter and all parameters of type `angle`"
        )


def _parse_staircase_effect(
    machine: QMachineDef, action: QActionSignature, n_qubits: int
) -> list[tuple]:
    """Parse a CNOT-staircase effect into an ordered list of operations.

    Returns a list of ``(kind, *args)`` tuples in the order they appear
    in the effect string:

    - ``("ry", qubit, coeffs_dict)`` — a Ry rotation on the staircase
      skeleton; appears exactly ``n_qubits`` times, on qubits in
      ``range(n_qubits)`` (preparation form) or ``range(n_qubits - 1,
      -1, -1)`` (inverse form).
    - ``("rz", qubit, coeffs_dict)`` — an optional Rz phase rotation
      ("interference knob"); may appear zero or more times, on any
      qubit, anywhere in the effect string. Rz gates are 1-qubit and
      do not change the bond-2 MPS structure.
    - ``("cnot", control, target)`` — a CNOT on adjacent qubits;
      appears exactly ``n_qubits - 1`` times, on pairs ``(k, k+1)``
      with ``k`` running ``0..n-2`` (prep) or ``n-2..0`` (inverse).

    The Ry/CNOT skeleton must alternate ``Ry, CNOT, Ry, CNOT, ..., Ry``
    when Rz gates are removed from the sequence. Each angle expression
    (Ry or Rz) SHALL be a linear combination of the action's bound
    angle parameters — see `_parse_linear_combination`.

    Raises ``MpsGramConfigurationError`` on any deviation from the
    staircase shape or on a non-linear angle expression.
    """
    effect = (action.effect or "").strip()
    segments = [s.strip() for s in effect.split(";") if s.strip()]
    param_names = [p.name for p in action.parameters]

    ops: list[tuple] = []
    skeleton: list[tuple] = []  # Ry/CNOT subsequence used for shape validation.

    def _parse_angle_expr(gate_label: str, qubit: int, expr: str) -> dict[str, float]:
        try:
            return _parse_linear_combination(expr, param_names)
        except _NonLinearExpr as e:
            raise MpsGramConfigurationError(
                f"machine {machine.name!r}: action {action.name!r} "
                f"{gate_label}(qs[{qubit}], {expr}): angle expression "
                f"{expr!r} is not a linear combination of the "
                f"action's bound angle parameters {param_names} "
                f"({e}). mps concept-gram accepts angle expressions "
                f"of the form `c_0·p_0 + c_1·p_1 + ...` (sums of "
                f"terms, each an optional numeric coefficient times "
                f"a single bound parameter name)",
                kind="unrecognized_angle_expression",
            ) from e

    for seg in segments:
        m = _RY_SEGMENT_RE.match(seg)
        if m:
            qubit = int(m.group("qubit"))
            coeffs = _parse_angle_expr("Ry", qubit, m.group("expr"))
            ops.append(("ry", qubit, coeffs))
            skeleton.append(("ry", qubit))
            continue

        m = _RZ_SEGMENT_RE.match(seg)
        if m:
            qubit = int(m.group("qubit"))
            if qubit < 0 or qubit >= n_qubits:
                raise MpsGramConfigurationError(
                    f"machine {machine.name!r}: action {action.name!r} "
                    f"effect segment {seg!r} targets qs[{qubit}], which "
                    f"is out of range for the {n_qubits}-qubit register"
                )
            coeffs = _parse_angle_expr("Rz", qubit, m.group("expr"))
            ops.append(("rz", qubit, coeffs))
            continue

        m = _CNOT_SEGMENT_RE.match(seg)
        if m:
            control = int(m.group("control"))
            target = int(m.group("target"))
            ops.append(("cnot", control, target))
            skeleton.append(("cnot", control, target))
            continue

        raise MpsGramConfigurationError(
            f"machine {machine.name!r}: action {action.name!r} effect "
            f"segment {seg!r} is not of the form `Ry(qs[i], <expr>)`, "
            f"`Rz(qs[i], <expr>)`, or `CNOT(qs[i], qs[j])`; mps concept-"
            f"gram accepts only those gate shapes in the staircase"
        )

    # Validate the Ry/CNOT skeleton (Rz gates have already been
    # accumulated into `ops` and contribute nothing to the staircase
    # shape check).
    expected_len = 2 * n_qubits - 1
    if len(skeleton) != expected_len:
        ry_count = sum(1 for s in skeleton if s[0] == "ry")
        cnot_count = sum(1 for s in skeleton if s[0] == "cnot")
        raise MpsGramConfigurationError(
            f"machine {machine.name!r}: action {action.name!r} effect "
            f"{effect!r} has {ry_count} Ry segment(s) and {cnot_count} "
            f"CNOT segment(s) on the staircase skeleton; the CNOT "
            f"staircase on {n_qubits} qubits requires exactly "
            f"{n_qubits} Ry rotations and {n_qubits - 1} adjacent CNOTs"
        )

    parsed_ry: list[int] = [s[1] for s in skeleton if s[0] == "ry"]
    parsed_cnot: list[tuple[int, int]] = [
        (s[1], s[2]) for s in skeleton if s[0] == "cnot"
    ]

    # The Ry/CNOT skeleton must alternate Ry, CNOT, Ry, CNOT, ..., Ry.
    for idx, entry in enumerate(skeleton):
        expected_kind = "ry" if idx % 2 == 0 else "cnot"
        if entry[0] != expected_kind:
            raise MpsGramConfigurationError(
                f"machine {machine.name!r}: action {action.name!r} effect "
                f"{effect!r}: the Ry/CNOT skeleton (Rz gates ignored) "
                f"must alternate Ry, CNOT, Ry, CNOT, ..., Ry; got "
                f"{entry[0]!r} at skeleton position {idx}"
            )

    # Determine prep vs inverse from the qubit ordering of the Ry
    # rotations on the skeleton (the one structural feature the two
    # forms differ on that doesn't depend on user-chosen sign conventions).
    prep_qubits = list(range(n_qubits))
    inverse_qubits = list(range(n_qubits - 1, -1, -1))
    if parsed_ry == prep_qubits:
        expected_cnots = [(k, k + 1) for k in range(n_qubits - 1)]
        form = "preparation"
    elif parsed_ry == inverse_qubits:
        expected_cnots = [(k, k + 1) for k in range(n_qubits - 2, -1, -1)]
        form = "inverse"
    else:
        raise MpsGramConfigurationError(
            f"machine {machine.name!r}: action {action.name!r} effect "
            f"{effect!r} applies Ry on qubits {parsed_ry}; the "
            f"CNOT staircase requires Ry on qubits {prep_qubits} "
            f"(preparation form) or {inverse_qubits} (inverse form)"
        )

    if parsed_cnot != expected_cnots:
        raise MpsGramConfigurationError(
            f"machine {machine.name!r}: action {action.name!r} effect "
            f"{effect!r} has CNOTs {parsed_cnot}; the {form} CNOT "
            f"staircase requires adjacent CNOTs {expected_cnots}"
        )

    # Guardrail: the helper builds concept states by applying the effect
    # string to `|0^n>`. In the inverse form, an `Rz` segment runs
    # *before* the corresponding `Ry` rotates its target qubit off `|0>`
    # (because gate order is reversed); since `Rz(theta)|0> =
    # exp(-i*theta/2)|0>`, the phase collapses to a global factor and the
    # helper would silently return a Gram that is invariant on the phase
    # axis. The preparation form does not have this issue (`Rz` runs
    # *after* its qubit has been rotated). Reject the configuration with
    # a contextful error rather than producing a misleading result.
    # Tracked in `tech-debt-backlog/tasks.md` §5.16; symbolic inversion
    # of the inverse-form effect is the deeper fix and remains open.
    if form == "inverse":
        nontrivial_rz = [
            op for op in ops
            if op[0] == "rz" and any(c != 0.0 for c in op[2].values())
        ]
        if nontrivial_rz:
            _, qubit, coeffs = nontrivial_rz[0]
            raise MpsGramConfigurationError(
                f"machine {machine.name!r}: action {action.name!r} effect "
                f"{effect!r} is in inverse (query) form and contains a "
                f"non-trivial `Rz(qs[{qubit}], <expr>)` segment with "
                f"coefficients {coeffs}. Applied to `|0^n>`, the inverse-"
                f"form `Rz` runs before its target qubit has been rotated "
                f"and collapses to a global phase, so the analytic Gram "
                f"would silently lose the phase-knob axis. Examples that "
                f"use `Rz` interference knobs SHALL enumerate the "
                f"preparation form (one parametric call site per "
                f"concept) — see "
                f"`examples/larql-animals-interference.q.orca.md`",
                kind="rz_in_inverse_form",
            )

    return ops


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


def _rz_matrix(np_module, theta: float):
    half = theta / 2.0
    return np_module.array(
        [
            [np_module.exp(-1j * half), 0.0],
            [0.0, np_module.exp(1j * half)],
        ],
        dtype=complex,
    )


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


def _evaluate_angle(
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
    param_names: list[str],
    ops: list[tuple],
):
    """Build |c_i> for a single call site under the given bound-argument tuple.

    ``ops`` is the ordered list of operations returned by
    ``_parse_staircase_effect``. Each Ry/Rz angle expression is
    evaluated against ``bound`` (positional substitution into
    ``param_names``) and applied in declaration order; CNOTs apply
    directly. The starting state is ``|0^n>``.
    """
    state = np_module.zeros((2,) * n_qubits, dtype=complex)
    state[(0,) * n_qubits] = 1.0

    for op in ops:
        kind = op[0]
        if kind == "ry":
            _, qubit, coeffs = op
            theta = _evaluate_angle(coeffs, param_names, bound)
            state = _apply_1q(
                np_module, state, _ry_matrix(np_module, theta), qubit
            )
        elif kind == "rz":
            _, qubit, coeffs = op
            theta = _evaluate_angle(coeffs, param_names, bound)
            state = _apply_1q(
                np_module, state, _rz_matrix(np_module, theta), qubit
            )
        elif kind == "cnot":
            _, control, target = op
            state = _apply_cnot(np_module, state, control, target)
        else:  # pragma: no cover - defensive; _parse_staircase_effect filters
            raise AssertionError(f"unexpected op kind {kind!r}")

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

    n_qubits = infer_qubit_count(machine)
    if n_qubits <= 0:
        raise MpsGramConfigurationError(
            f"machine {machine.name!r}: could not infer a qubit register "
            f"size; mps concept-gram requires a non-empty `qubits` list "
            f"in `## context`"
        )

    action = _find_concept_action(machine, concept_action_label)
    _check_signature(machine, action, n_qubits)
    ops = _parse_staircase_effect(machine, action, n_qubits)
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

    n_params = len(action.parameters)
    angle_rows: list[list[float]] = []
    for site_idx, t in enumerate(call_sites):
        if len(t.bound_arguments) != n_params:
            raise MpsGramConfigurationError(
                f"machine {machine.name!r}: call site to "
                f"{concept_action_label!r} has {len(t.bound_arguments)} "
                f"arguments; expected exactly {n_params} angle literals "
                f"(one per parameter of the action's signature)"
            )
        row: list[float] = []
        for arg_idx, b in enumerate(t.bound_arguments):
            try:
                row.append(float(b.value))
            except (TypeError, ValueError) as e:
                raise MpsGramConfigurationError(
                    f"machine {machine.name!r}: call site #{site_idx} to "
                    f"{concept_action_label!r}: argument #{arg_idx} value "
                    f"{b.value!r} cannot be coerced to float ({e}); mps "
                    f"concept-gram requires every bound argument to be a "
                    f"numeric angle literal"
                ) from e
        angle_rows.append(row)

    angles = np.array(angle_rows, dtype=float)
    n_calls = len(angles)

    # TODO(deferred): replace this 2^n statevector simulation with an
    # MPS transfer-matrix contraction in O(n * chi^6) per call site.
    # The current path is fine for the shipped n=3 hierarchical example;
    # the asymptotic statevector cost only bites once n grows past ~8.
    # Sketch of the contraction: build a per-site `T_k = sum_b A_k^b
    # \otimes A_k^b\dagger` rank-4 transfer matrix from the staircase
    # MPS tensors `A_k`, then contract along the chain to obtain
    # `gram[i, j]` without ever materializing the 2^n statevector. See
    # the research note `docs/research/polysemantic-encoding-beyond-
    # product-states.md` for the closed-form derivation.
    flat_states = np.stack(
        [
            _build_concept_state(
                np, n_qubits, angles[i].tolist(), param_names, ops,
            ).reshape(-1)
            for i in range(n_calls)
        ]
    )
    # gram[i, j] = <c_i | c_j> = sum_k flat_states[i, k].conj() *
    # flat_states[j, k] = (flat_states.conj() @ flat_states.T)[i, j].
    # Single BLAS call replaces the previous O(N^2) Python loop over
    # np.vdot, and is typically more numerically accurate.
    return flat_states.conj() @ flat_states.T
