"""HEA encoding consistency check (Stage 4b sub-stage).

Invoked when a machine declares an `## encoding` section with
`kind: hea`. Calls `compute_concept_gram_hea` to ensure the
encoding declaration, the `## theta` block, and the transitions
table are mutually consistent. Any `HeaGramConfigurationError`
raised by the helper is surfaced as a Stage 4b verifier error
with code `HEA_GRAM_INVALID`.

Tier-ordering enforcement against declared bands is *not* part of
this check — that requires invariant-grammar work that is
deferred to a follow-up proposal. `HEA_TIER_TOLERANCE` is exported
as a module-level constant for downstream test code and the
follow-up proposal.
"""

from __future__ import annotations

from q_orca.ast import QMachineDef
from q_orca.verifier.types import QVerificationError

HEA_TIER_TOLERANCE = 0.025


def check_hea_encoding(
    machine: QMachineDef,
    concept_action_label: str = "query_concept",
) -> list[QVerificationError]:
    """Run the HEA encoding consistency check.

    Returns an empty list if the machine does not declare an HEA
    encoding (the check is a no-op for non-HEA machines).
    """
    if machine.encoding is None or machine.encoding.kind != "hea":
        return []

    from q_orca.compiler.concept_gram_hea import (
        HeaGramConfigurationError,
        compute_concept_gram_hea,
    )

    try:
        compute_concept_gram_hea(machine, concept_action_label)
    except HeaGramConfigurationError as exc:
        return [
            QVerificationError(
                code="HEA_GRAM_INVALID",
                message=str(exc),
                severity="error",
            )
        ]
    return []
