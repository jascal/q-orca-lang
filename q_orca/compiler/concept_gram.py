"""Concept Gram matrix analysis for product-state polysemantic machines.

Optional analysis utility for machines that follow the *structured
polysemantic* preparation convention:

1. A single parametric preparation action with signature
   ``(qs, a: angle, b: angle, c: angle) -> qs``.
2. A product-state effect of the form
   ``Ry(qs[0], a); Ry(qs[1], b); Ry(qs[2], c)``.
3. ``N ≥ 1`` call sites to that action in the transitions table,
   each with a literal angle triple.

Given such a machine, ``compute_concept_gram`` returns the ``N × N``
inner-product matrix of the product-state "concept" vectors the call
sites prepare. The helper is **not** on the main compile / verify /
simulate path; it exists for demo code and for tests that want to
assert the block-structured Gram signature of a clustered
polysemantic example.
"""

from __future__ import annotations

import numpy as np

from q_orca.ast import QActionSignature, QMachineDef


class ConceptGramConfigurationError(ValueError):
    """Raised when a machine doesn't meet the concept-gram convention."""


def _find_prepare_action(
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
    shape = [(p.name, p.type) for p in params]
    if len(params) != 3 or any(p.type != "angle" for p in params):
        raise ConceptGramConfigurationError(
            f"machine {machine.name!r}: action {action.name!r} has "
            f"signature parameters {shape}; concept-gram requires "
            f"exactly three angle parameters (a: angle, b: angle, "
            f"c: angle)"
        )


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
    action = _find_prepare_action(machine, concept_action_label)
    _check_signature(machine, action)

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
