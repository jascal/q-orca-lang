"""Shared fixtures for Q-Orca tests."""

import pytest
from pathlib import Path

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"

BELL_ENTANGLER_SOURCE = (EXAMPLES_DIR / "bell-entangler.q.orca.md").read_text()


MINIMAL_MACHINE = """\
# machine Minimal

## events
- go

## state |0> [initial]
> Start

## state |1> [final]
> End

## transitions
| Source | Event | Guard | Target | Action |
|--------|-------|-------|--------|--------|
| |0>    | go    |       | |1>    |        |
"""


@pytest.fixture
def bell_source():
    return BELL_ENTANGLER_SOURCE


@pytest.fixture
def minimal_source():
    return MINIMAL_MACHINE
