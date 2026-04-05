"""Tests for example machines."""

import json
from pathlib import Path

import pytest

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"

EXAMPLE_FILES = {
    "bell-entangler": "bell-entangler.q.orca.md",
    "deutsch-jozsa": "deutsch-jozsa.q.orca.md",
    "ghz-state": "ghz-state.q.orca.md",
    "quantum-teleportation": "quantum-teleportation.q.orca.md",
    "vqe-heisenberg": "vqe-heisenberg.q.orca.md",
}


@pytest.fixture(params=list(EXAMPLE_FILES.keys()))
def example_file(request):
    """Yield (name, path) for each example."""
    name = request.param
    return name, EXAMPLES_DIR / EXAMPLE_FILES[name]


class TestExamples:
    def test_verify_all_examples(self, example_file):
        """Each example must verify successfully."""
        from q_orca.skills import verify_skill

        name, path = example_file
        result = verify_skill({"file": str(path)})
        assert result["status"] == "valid", f"{name} verification failed: {result['errors']}"

    def test_bell_entangler_ast_snapshot(self):
        """Snapshot test: BellEntangler AST must not change unexpectedly."""
        from q_orca.parser.markdown_parser import parse_q_orca_markdown

        source = (EXAMPLES_DIR / "bell-entangler.q.orca.md").read_text()
        result = parse_q_orca_markdown(source)
        machine = result.file.machines[0]

        # Build a serializable representation
        snapshot = {
            "name": machine.name,
            "num_states": len(machine.states),
            "num_events": len(machine.events),
            "num_transitions": len(machine.transitions),
            "num_actions": len(machine.actions),
            "states": sorted(s.name for s in machine.states),
            "events": sorted(e.name for e in machine.events),
            "context_fields": sorted(f.name for f in machine.context),
        }

        # Serialize to JSON for comparison
        snapshot_json = json.dumps(snapshot, sort_keys=True, indent=2)

        # The snapshot should be stable — any change is a breaking change
        expected = {
            "context_fields": ["outcome", "qubits"],
            "events": sorted(["prepare_H", "entangle", "measure_done"]),
            "name": "BellEntangler",
            "num_actions": 4,
            "num_events": 3,
            "num_states": 5,
            "num_transitions": 4,
            "states": sorted(["|00>", "|+0>", "|ψ>", "|00_collapsed>", "|11_collapsed>"]),
        }
        expected_json = json.dumps(expected, sort_keys=True, indent=2)

        assert snapshot_json == expected_json, (
            f"BellEntangler AST snapshot mismatch. "
            f"If this is intentional, update the expected dict in test_examples.py.\n"
            f"Got:\n{snapshot_json}\nExpected:\n{expected_json}"
        )
