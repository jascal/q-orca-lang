"""Direct tests for the shared gate-effect-string parser."""

from __future__ import annotations

import pytest

from q_orca.effect_parser import (
    ParsedGate,
    parse_effect_string,
    parse_single_gate,
)
from tests.fixtures.effect_strings import (
    EFFECT_STRING_CASES,
    MALFORMED_CASES,
    NON_MATCHING_CASES,
)


@pytest.mark.parametrize(
    "effect_str,angle_context,expected,notes",
    EFFECT_STRING_CASES,
    ids=[c[3] for c in EFFECT_STRING_CASES],
)
def test_parse_single_gate_happy_path(
    effect_str: str,
    angle_context: dict | None,
    expected: ParsedGate,
    notes: str,
) -> None:
    actual = parse_single_gate(effect_str, angle_context=angle_context)
    assert actual is not None, f"expected match for {effect_str!r} ({notes})"
    assert actual.name == expected.name
    assert actual.targets == expected.targets
    assert actual.controls == expected.controls
    if expected.parameter is None:
        assert actual.parameter is None
    else:
        assert actual.parameter == pytest.approx(expected.parameter)
    if expected.custom_name is not None:
        assert actual.custom_name == expected.custom_name


@pytest.mark.parametrize(
    "effect_str,notes",
    NON_MATCHING_CASES,
    ids=[c[1] for c in NON_MATCHING_CASES],
)
def test_parse_single_gate_returns_none_for_non_matches(
    effect_str: str, notes: str
) -> None:
    assert parse_single_gate(effect_str) is None


@pytest.mark.parametrize(
    "effect_str,angle_context,error_substr,notes",
    MALFORMED_CASES,
    ids=[c[3] for c in MALFORMED_CASES],
)
def test_parse_single_gate_emits_structured_error(
    effect_str: str,
    angle_context: dict | None,
    error_substr: str,
    notes: str,
) -> None:
    errors: list[str] = []
    result = parse_single_gate(
        effect_str,
        angle_context=angle_context,
        errors=errors,
        action_name="myaction",
    )
    assert result is None, f"expected None for malformed {effect_str!r} ({notes})"
    assert errors, f"expected an error message for {effect_str!r} ({notes})"
    assert any(error_substr in e for e in errors), (
        f"expected {error_substr!r} in errors for {effect_str!r}, got {errors!r}"
    )
    assert all("'myaction'" in e for e in errors), (
        f"expected action_name prefix in errors for {effect_str!r}, got {errors!r}"
    )


def test_parse_single_gate_silent_on_malformed_when_errors_none() -> None:
    """Qiskit and verifier adapters pass errors=None to silently drop."""
    assert parse_single_gate("MCX(qs[0])") is None
    assert parse_single_gate("Rx(qs[0], blah)") is None


def test_parse_effect_string_splits_on_semicolon() -> None:
    gates = parse_effect_string("H(qs[0]); CNOT(qs[0], qs[1]); Z(qs[1])")
    assert [g.name for g in gates] == ["H", "CNOT", "Z"]
    assert gates[1].controls == (0,) and gates[1].targets == (1,)


def test_parse_effect_string_drops_unmatched_parts() -> None:
    """Unrecognized parts are dropped — preserves existing call-site behavior."""
    gates = parse_effect_string("H(qs[0]); not_a_gate; CNOT(qs[0], qs[1])")
    assert [g.name for g in gates] == ["H", "CNOT"]


def test_parse_effect_string_skips_empty_parts() -> None:
    """Trailing semicolons should not produce empty gates."""
    gates = parse_effect_string("H(qs[0]);")
    assert len(gates) == 1


def test_parse_effect_string_returns_empty_for_empty_input() -> None:
    assert parse_effect_string("") == []
    assert parse_effect_string(None) == []  # type: ignore[arg-type]


def test_pr11_regression_crx_not_demoted_to_rx() -> None:
    """Direct guard against the PR #11 substring-match bug."""
    g = parse_single_gate("CRx(qs[0], qs[1], 0.5)")
    assert g is not None and g.name == "CRx"
    assert g.controls == (0,) and g.targets == (1,)


def test_pr11_regression_rzz_not_silently_dropped() -> None:
    """Direct guard against the other PR #11 bug."""
    g = parse_single_gate("RZZ(qs[0], qs[1], 0.5)")
    assert g is not None and g.name == "RZZ"
    assert g.targets == (0, 1) and g.parameter == pytest.approx(0.5)


def test_ccnot_substring_does_not_match_cnot() -> None:
    """CCNOT must not silently degrade to CNOT via substring match."""
    g = parse_single_gate("CCNOT(qs[0], qs[1], qs[2])")
    assert g is not None and g.name == "CCNOT"
    assert g.controls == (0, 1) and g.targets == (2,)


def test_hadamard_multi_index_supported() -> None:
    """Markdown-parser-flavored multi-index Hadamard form."""
    g = parse_single_gate("Hadamard(qs[0 1 2])")
    assert g is not None and g.name == "H" and g.targets == (0, 1, 2)
