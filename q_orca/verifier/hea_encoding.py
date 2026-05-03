"""HEA encoding consistency + tier-ordering checks (Stage 4b sub-stage).

Invoked when a machine declares an `## encoding` section with
`kind: hea`. Calls `compute_concept_gram_hea` to ensure the
encoding declaration, the `## theta` block, and the transitions
table are mutually consistent. Any `HeaGramConfigurationError`
raised by the helper is surfaced as a Stage 4b verifier error
with code `HEA_GRAM_INVALID`.

Additionally, when the machine declares a
`concept_gram_tier_separation` invariant in `## invariants`, this
sub-stage evaluates the declared inequality against the analytic
Gram and emits `HEA_TIER_INVARIANT_VIOLATED` /
`HEA_TIER_UNDEFINED` / `HEA_TIER_INVARIANT_NOT_APPLICABLE` as
appropriate. `HEA_TIER_TOLERANCE` is exposed as a recommended-
default tolerance constant; the verifier reads the value the
machine declares.
"""

from __future__ import annotations

from q_orca.ast import QMachineDef
from q_orca.verifier.types import QVerificationError

HEA_TIER_TOLERANCE = 0.025

_OP_FNS = {
    "ge": lambda a, b: a >= b,
    "gt": lambda a, b: a > b,
    "le": lambda a, b: a <= b,
    "lt": lambda a, b: a < b,
    "eq": lambda a, b: a == b,
}

_OP_SYMBOLS = {
    "ge": ">=", "gt": ">", "le": "<=", "lt": "<", "eq": "==",
}


def _find_tier_invariant(machine: QMachineDef):
    for inv in machine.invariants:
        if inv.kind == "resource" and inv.metric == "concept_gram_tier_separation":
            return inv
    return None


def check_hea_encoding(
    machine: QMachineDef,
    concept_action_label: str = "query_concept",
) -> list[QVerificationError]:
    """Run the HEA consistency check and the tier-separation invariant.

    Returns an empty list if the machine declares neither HEA encoding
    nor a tier-separation invariant.
    """
    tier_invariant = _find_tier_invariant(machine)
    is_hea = machine.encoding is not None and machine.encoding.kind == "hea"

    if not is_hea:
        if tier_invariant is None:
            return []
        return [
            QVerificationError(
                code="HEA_TIER_INVARIANT_NOT_APPLICABLE",
                message=(
                    f"machine {machine.name!r}: declares "
                    f"`concept_gram_tier_separation "
                    f"{_OP_SYMBOLS[tier_invariant.op]} "
                    f"{tier_invariant.value}` but has no `## encoding` "
                    f"section with `kind: hea` to evaluate it against"
                ),
                severity="warning",
            )
        ]

    from q_orca.compiler.concept_gram_hea import (
        HeaGramConfigurationError,
        compute_concept_gram_hea,
        compute_tier_separation,
    )

    errors: list[QVerificationError] = []
    try:
        gram = compute_concept_gram_hea(machine, concept_action_label)
    except HeaGramConfigurationError as exc:
        return [
            QVerificationError(
                code="HEA_GRAM_INVALID",
                message=str(exc),
                severity="error",
            )
        ]

    if tier_invariant is None:
        return errors

    theta = machine.theta
    assert theta is not None  # consistency check above guarantees this
    clusters = [row.cluster for row in theta.rows]
    separation = compute_tier_separation(gram, clusters)

    if separation is None:
        errors.append(QVerificationError(
            code="HEA_TIER_UNDEFINED",
            message=(
                f"machine {machine.name!r}: "
                f"`concept_gram_tier_separation` invariant declared, "
                f"but every `## theta` row is in its own singleton "
                f"cluster — no intra-cluster pairs to evaluate"
            ),
            severity="error",
        ))
        return errors

    op = tier_invariant.op
    bound = float(tier_invariant.value)
    if not _OP_FNS[op](separation, bound):
        violating_pair = _find_violating_pair(gram, clusters)
        errors.append(QVerificationError(
            code="HEA_TIER_INVARIANT_VIOLATED",
            message=(
                f"machine {machine.name!r}: "
                f"`concept_gram_tier_separation {_OP_SYMBOLS[op]} "
                f"{bound}` violated — actual {separation:.6f} "
                f"(driven by cluster pair {violating_pair})"
            ),
            severity="error",
        ))

    return errors


def _find_violating_pair(gram, clusters: list[str]) -> tuple[str, str]:
    """Return the cross-cluster pair (cluster_a, cluster_b) that
    realizes the maximum cross-cluster overlap. Used for
    HEA_TIER_INVARIANT_VIOLATED attribution."""
    import numpy as np

    overlap = np.abs(gram) ** 2
    n = len(clusters)
    best = (0.0, ("", ""))
    for i in range(n):
        for j in range(i + 1, n):
            if clusters[i] == clusters[j]:
                continue
            v = float(overlap[i, j])
            if v >= best[0]:
                a, b = sorted((clusters[i], clusters[j]))
                best = (v, (a, b))
    return best[1]
