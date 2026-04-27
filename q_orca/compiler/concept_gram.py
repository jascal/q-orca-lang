"""Concept Gram matrix analysis for product-state polysemantic machines.

Optional analysis utility for machines that follow the *structured
polysemantic* concept-encoding convention. The helper is fixed at the
3-qubit / 3-angle product-state shape used by the canonical example
(``examples/larql-polysemantic-clusters.q.orca.md``); a generalized
``n``-angle variant lives under ``add-mps-concept-encoding`` and is
not exposed here.

1. A single parametric concept action (preparation *or* its inverse)
   with signature ``(qs, a: angle, b: angle, c: angle) -> qs`` —
   exactly three angle parameters, no more, no less.
2. A product-state effect, either a preparation of the form
   ``Ry(qs[0], a); Ry(qs[1], b); Ry(qs[2], c)`` or its inverse
   ``Ry(qs[2], -c); Ry(qs[1], -b); Ry(qs[0], -a)`` (reversed gate
   order, negated angle signs). Either form enumerates the same
   concept vectors ``|c_i> = Ry(q0, a_i) Ry(q1, b_i) Ry(q2, c_i)
   |000>``; the helper's default ``concept_action_label="query_concept"``
   targets the inverse (query) form used by the canonical example.
3. ``N ≥ 1`` call sites to that action in the transitions table,
   each with a literal angle triple.

Given such a machine, ``compute_concept_gram`` returns the ``N × N``
inner-product matrix of the concept vectors the call sites enumerate.
The helper is **not** on the main compile / verify / simulate path;
it exists for demo code and for tests that want to assert the
block-structured Gram signature of a clustered polysemantic example.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from q_orca.ast import QActionSignature, QMachineDef

if TYPE_CHECKING:
    import numpy as np


class ConceptGramConfigurationError(ValueError):
    """Raised when a machine doesn't meet the concept-gram convention."""


# A single product-state Ry segment, e.g. `Ry(qs[0], a)` or `Ry(qs[2], -c)`.
# Tolerates whitespace around tokens; the angle slot is `name` or `-name`.
_RY_SEGMENT_RE = re.compile(
    r"^\s*Ry\s*\(\s*qs\[\s*(?P<qubit>\d+)\s*\]\s*,\s*"
    r"(?P<sign>-?)\s*(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\)\s*$"
)


def _find_concept_action(
    machine: QMachineDef, label: str
) -> QActionSignature:
    for a in machine.actions:
        if a.name == label:
            return a
    available = [a.name for a in machine.actions if a.parameters]
    raise ConceptGramConfigurationError(
        f"machine {machine.name!r}: no parametric action named "
        f"{label!r}; available parametric actions: {available}"
    )


def _check_signature(machine: QMachineDef, action: QActionSignature) -> None:
    params = action.parameters
    if len(params) != 3 or any(p.type != "angle" for p in params):
        shape = [(p.name, p.type) for p in params]
        raise ConceptGramConfigurationError(
            f"machine {machine.name!r}: action {action.name!r} has "
            f"signature parameters {shape}; concept-gram requires "
            f"exactly three angle parameters (a: angle, b: angle, "
            f"c: angle)"
        )


def _check_effect(machine: QMachineDef, action: QActionSignature) -> None:
    """Validate the effect string is a 3-qubit Ry product-state template.

    The signature shape check (`_check_signature`) only constrains parameter
    *count* and type; it would silently accept a malformed effect like
    ``CNOT(qs[0], qs[1]); Rz(qs[2], c)``, producing a numerically wrong Gram
    matrix. Pin the template to either the preparation form
    (``Ry(qs[0], a); Ry(qs[1], b); Ry(qs[2], c)``) or its inverse
    (``Ry(qs[2], -c); Ry(qs[1], -b); Ry(qs[0], -a)``) so the formula in
    ``compute_concept_gram`` matches the actual circuit.
    """
    effect = (action.effect or "").strip()
    segments = [s.strip() for s in effect.split(";") if s.strip()]
    if len(segments) != 3:
        raise ConceptGramConfigurationError(
            f"machine {machine.name!r}: action {action.name!r} effect "
            f"{effect!r} has {len(segments)} gate segment(s); concept-gram "
            f"requires exactly three Ry gates of the form "
            f"`Ry(qs[0], a); Ry(qs[1], b); Ry(qs[2], c)` (or its inverse)."
        )

    parsed: list[tuple[int, str, str]] = []
    for seg in segments:
        m = _RY_SEGMENT_RE.match(seg)
        if not m:
            raise ConceptGramConfigurationError(
                f"machine {machine.name!r}: action {action.name!r} effect "
                f"segment {seg!r} is not of the form `Ry(qs[i], [-]name)`; "
                f"concept-gram requires a product of single-qubit Ry "
                f"rotations driven by the declared angle parameters."
            )
        parsed.append((int(m.group("qubit")), m.group("sign"), m.group("name")))

    signs = {sign for _, sign, _ in parsed}
    if len(signs) > 1:
        raise ConceptGramConfigurationError(
            f"machine {machine.name!r}: action {action.name!r} effect "
            f"{effect!r} mixes positive and negated angle signs across the "
            f"three Ry gates; concept-gram accepts the all-positive "
            f"preparation form or the all-negated inverse form, not a mix."
        )

    expected = {k: action.parameters[k].name for k in range(3)}
    seen_qubits: set[int] = set()
    for qubit, _, name in parsed:
        if qubit not in expected:
            raise ConceptGramConfigurationError(
                f"machine {machine.name!r}: action {action.name!r} effect "
                f"references qs[{qubit}]; concept-gram requires qubit "
                f"subscripts 0, 1, 2 only."
            )
        if qubit in seen_qubits:
            raise ConceptGramConfigurationError(
                f"machine {machine.name!r}: action {action.name!r} effect "
                f"applies Ry to qs[{qubit}] more than once; concept-gram "
                f"requires one Ry per qubit."
            )
        if name != expected[qubit]:
            raise ConceptGramConfigurationError(
                f"machine {machine.name!r}: action {action.name!r} effect "
                f"applies Ry on qs[{qubit}] with angle {name!r}, but "
                f"signature position {qubit} declares parameter "
                f"{expected[qubit]!r}; concept-gram requires positional "
                f"alignment between angle parameters and qubit indices."
            )
        seen_qubits.add(qubit)


def compute_concept_gram(
    machine: QMachineDef,
    concept_action_label: str = "query_concept",
) -> np.ndarray:
    """Compute the N×N concept-overlap matrix for a product-state machine.

    Parameters
    ----------
    machine:
        A parsed ``QMachineDef`` following the structured-polysemantic
        preparation convention (see module docstring).
    concept_action_label:
        Name of the parametric action whose call sites enumerate the
        N-concept dictionary. The default ``"query_concept"`` matches
        the canonical ``examples/larql-polysemantic-clusters.q.orca.md``
        example, where ``query_concept`` is called 12 times (once per
        concept). Pass ``"prepare_concept"`` (or any other label) when
        the enumerating action has a different name.

    Returns
    -------
    numpy.ndarray
        A complex-valued ``(N, N)`` matrix where ``N`` is the number
        of call sites to the preparation action in the transitions
        table. ``gram[i, j] = <c_i | c_j>`` with the concept vectors
        ``|c_i> = Ry(q0, a_i) Ry(q1, b_i) Ry(q2, c_i) |000>``. The
        return dtype is complex for forward compatibility with
        non-Ry encodings, but values are real for the canonical Ry
        convention.

    Raises
    ------
    ConceptGramConfigurationError
        If the named action is missing, has the wrong signature, or
        has no call sites in the transitions table.
    """
    # Lazy numpy import: this module is re-exported from the top-level
    # `q_orca` package, and numpy isn't part of the base install (it comes
    # in via the optional `quantum` extras). Importing numpy at module
    # load would break `python -m q_orca.cli` on minimal installs (e.g.,
    # the mcp-check job).
    import numpy as np

    action = _find_concept_action(machine, concept_action_label)
    _check_signature(machine, action)
    _check_effect(machine, action)

    call_sites = [
        t for t in machine.transitions
        if t.action == concept_action_label and t.bound_arguments
    ]
    if not call_sites:
        raise ConceptGramConfigurationError(
            f"machine {machine.name!r}: action {concept_action_label!r} "
            f"has no call sites in the transitions table; concept-gram "
            f"needs at least one parametric call site to enumerate"
        )

    angles = np.array(
        [[float(b.value) for b in t.bound_arguments] for t in call_sites],
        dtype=float,
    )
    n = len(angles)
    gram = np.zeros((n, n), dtype=complex)
    for i in range(n):
        for j in range(n):
            diff = angles[i] - angles[j]
            gram[i, j] = complex(np.prod(np.cos(diff / 2.0)))
    return gram
