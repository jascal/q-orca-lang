"""Shared parametrize fixture for gate-effect-string parsing.

Each entry is ``(effect_str, expected_parsed_gate, notes)``. The same
list feeds ``test_effect_parser.py`` (the shared parser directly) and
the per-call-site test files (parser, compiler, verifier) so a new
gate kind is forced to exercise every backend in a single PR.
"""

from __future__ import annotations

import math

from q_orca.effect_parser import ParsedGate


# (effect_str, angle_context, expected, notes)
EFFECT_STRING_CASES: list[tuple[str, dict | None, ParsedGate, str]] = [
    # ---- single-qubit Pauli / Clifford ---------------------------------
    ("Hadamard(qs[0])", None, ParsedGate("H", (0,)), "Hadamard form"),
    ("X(qs[1])", None, ParsedGate("X", (1,)), "Pauli-X"),
    ("Y(qs[2])", None, ParsedGate("Y", (2,)), "Pauli-Y"),
    ("Z(qs[3])", None, ParsedGate("Z", (3,)), "Pauli-Z"),
    ("S(qs[0])", None, ParsedGate("S", (0,)), "S phase"),
    ("T(qs[0])", None, ParsedGate("T", (0,)), "T phase"),
    ("I(qs[0])", None, ParsedGate("I", (0,)), "Identity"),
    # ---- two-qubit non-parametric --------------------------------------
    ("CNOT(qs[0], qs[1])", None, ParsedGate("CNOT", (1,), (0,)), "CNOT canonical"),
    ("CX(qs[0], qs[1])", None, ParsedGate("CNOT", (1,), (0,)), "CX alias"),
    ("CZ(qs[0], qs[1])", None, ParsedGate("CZ", (1,), (0,)), "CZ"),
    ("SWAP(qs[2], qs[3])", None, ParsedGate("SWAP", (2, 3)), "SWAP symmetric"),
    # ---- multi-controlled gates ----------------------------------------
    (
        "CCNOT(qs[0], qs[1], qs[2])",
        None,
        ParsedGate("CCNOT", (2,), (0, 1)),
        "CCNOT — must NOT match as CNOT via substring",
    ),
    ("CCX(qs[0], qs[1], qs[2])", None, ParsedGate("CCNOT", (2,), (0, 1)), "CCX alias"),
    (
        "Toffoli(qs[0], qs[1], qs[2])",
        None,
        ParsedGate("CCNOT", (2,), (0, 1)),
        "Toffoli alias",
    ),
    ("CCZ(qs[0], qs[1], qs[2])", None, ParsedGate("CCZ", (2,), (0, 1)), "CCZ"),
    (
        "MCX(qs[0], qs[1], qs[2], qs[3])",
        None,
        ParsedGate("MCX", (3,), (0, 1, 2)),
        "MCX 3-control",
    ),
    (
        "MCZ(qs[0], qs[1], qs[2], qs[3])",
        None,
        ParsedGate("MCZ", (3,), (0, 1, 2)),
        "MCZ 3-control",
    ),
    (
        "CSWAP(qs[0], qs[1], qs[2])",
        None,
        ParsedGate("CSWAP", (1, 2), (0,)),
        "CSWAP / Fredkin",
    ),
    # ---- single-qubit rotations (literal angle) ------------------------
    (
        "Rx(qs[0], pi/4)",
        None,
        ParsedGate("Rx", (0,), parameter=math.pi / 4),
        "Rx literal angle",
    ),
    ("Ry(qs[1], 0.5)", None, ParsedGate("Ry", (1,), parameter=0.5), "Ry decimal"),
    ("Rz(qs[2], pi)", None, ParsedGate("Rz", (2,), parameter=math.pi), "Rz pi"),
    # ---- single-qubit rotations (context-resolved angle) ---------------
    (
        "Rx(qs[0], gamma)",
        {"gamma": 0.7},
        ParsedGate("Rx", (0,), parameter=0.7),
        "Rx context-ref angle",
    ),
    # ---- two-qubit parameterized: Pauli-product ------------------------
    (
        "RXX(qs[0], qs[1], pi/2)",
        None,
        ParsedGate("RXX", (0, 1), parameter=math.pi / 2),
        "RXX",
    ),
    (
        "RYY(qs[0], qs[1], pi/2)",
        None,
        ParsedGate("RYY", (0, 1), parameter=math.pi / 2),
        "RYY",
    ),
    (
        "RZZ(qs[0], qs[1], gamma)",
        {"gamma": 0.5},
        ParsedGate("RZZ", (0, 1), parameter=0.5),
        "PR #11 regression: RZZ silently dropped before consolidation",
    ),
    # ---- two-qubit parameterized: controlled rotations -----------------
    (
        "CRx(qs[0], qs[1], beta)",
        {"beta": 0.5},
        ParsedGate("CRx", (1,), (0,), parameter=0.5),
        "PR #11 regression: CRx demoted to Rx via substring match",
    ),
    (
        "CRy(qs[0], qs[1], 0.25)",
        None,
        ParsedGate("CRy", (1,), (0,), parameter=0.25),
        "CRy literal",
    ),
    (
        "CRz(qs[0], qs[1], pi/8)",
        None,
        ParsedGate("CRz", (1,), (0,), parameter=math.pi / 8),
        "CRz pi-fraction",
    ),
    # ---- whitespace tolerance ------------------------------------------
    (
        "  H(qs[5])  ",
        None,
        ParsedGate("H", (5,)),
        "leading/trailing whitespace",
    ),
]


# Cases that MUST parse to None (no match) — distinct from the
# malformed-with-error cases below.
NON_MATCHING_CASES: list[tuple[str, str]] = [
    ("", "empty string"),
    ("totally unrelated text", "non-gate text"),
]


# Cases where the input is recognized as a gate keyword but malformed,
# producing a structured error in the `errors` sink. ``error_substr``
# is asserted to appear in the message.
MALFORMED_CASES: list[tuple[str, dict | None, str, str]] = [
    (
        "MCX(qs[0], qs[1])",
        None,
        "MCX requires at least",
        "MCX with only 2 args (needs ≥3)",
    ),
    (
        "MCZ(qs[0])",
        None,
        "MCZ requires at least",
        "MCZ with only 1 arg",
    ),
    (
        "CSWAP(qs[0], qs[1])",
        None,
        "CSWAP requires at least",
        "CSWAP with 2 args (needs 3)",
    ),
    (
        "Rx(0.5, qs[0])",
        None,
        "angle-first argument order",
        "Rx in legacy angle-first order",
    ),
    (
        "Ry(qs[0], blah)",
        None,
        "unrecognized angle",
        "unknown angle identifier",
    ),
    (
        "CRx(qs[0], qs[1], blah)",
        None,
        "unrecognized angle",
        "two-qubit unknown angle identifier",
    ),
]
