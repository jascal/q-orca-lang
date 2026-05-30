"""Tests for the cross-tool bridge protocol (add-cross-tool-bridge-protocol).

Exercises the q-orca side end-to-end by using q-orca on *both* ends of the
bridge: a parent dispatches a child it treats as foreign via
`q-orca run --bridge` over a real process boundary.
"""

import sys

import pytest

from q_orca.bridge.protocol import (
    BRIDGE_PROTOCOL_VERSION,
    BridgeError,
    build_invocation,
    descriptor_for,
    make_result,
    parse_invocation,
    parse_result,
)
from q_orca.bridge.dispatch import run_inbound
from q_orca.parser.markdown_parser import parse_q_orca_markdown
from q_orca.runtime.composed import run_composed
from q_orca.runtime.types import QIterativeRuntimeError, QIterativeSimulationOptions

_QFORWARD = """# machine QForward
## context
| Field | Type | Default |
| theta | float | 0.5 |
## state |q0> [initial]
## state |prepared>
## state |measured> [final]
## transitions
| Source | Event | Guard | Target | Action |
| |q0> | prepare | | |prepared> | rotate |
| |prepared> | m | | |measured> | meas |
## actions
| Name | Signature | Effect |
| rotate | (qs) -> qs | Ry(qs[0], 0.5) |
| meas | (qs) -> qs | measure(qs[0]) -> bits[0] |
## returns
| Name | Type | Statistics |
| bits[0] | bit | expectation, histogram |
"""

_CLASSICAL = """# machine Counter
## context
| Field | Type | Default |
| n | int | 0 |
## state |a> [initial]
## state |b> [final]
## transitions
| Source | Event | Guard | Target | Action |
| |a> | g | | |b> | |
## returns
| Name | Type | Statistics |
| n | int | |
"""

_PARENT = """# machine Trainer
## context
| Field | Type | Default |
| theta | float | 0.5 |
| prob | float | 0.0 |
## state |idle> [initial]
## state |step> [invoke: QForward(theta=theta) shots=1024]
> returns: prob=prob_bits_0
## state |done> [final]
## transitions
| Source | Event | Guard | Target | Action |
| |idle> | advance | | |step> | |
| |step> | advance | | |done> | |
"""


def _file(src):
    r = parse_q_orca_markdown(src)
    assert not r.errors, r.errors
    return r.file


class TestProtocolEnvelopes:
    def test_descriptor_measurement_bearing(self):
        d = descriptor_for(_file(_QFORWARD).machines[0])
        assert d["measurement_bearing"] is True
        assert d["protocol_version"] == BRIDGE_PROTOCOL_VERSION
        ret = d["returns"][0]
        assert ret["name"] == "bits[0]" and ret["statistics"] == ["expectation", "histogram"]

    def test_descriptor_classical(self):
        d = descriptor_for(_file(_CLASSICAL).machines[0])
        assert d["measurement_bearing"] is False
        assert [p["name"] for p in d["params"]] == ["n"]

    def test_envelope_round_trip(self):
        import json

        inv = build_invocation("QForward", {"theta": 0.5}, 1024, {"prob": "prob_bits_0"})
        assert parse_invocation(json.dumps(inv))["child"] == "QForward"
        res = make_result("|measured>", {"prob_bits_0": 0.73})
        parsed = parse_result(json.dumps(res))
        assert parsed["final_state"] == "|measured>" and parsed["returns"]["prob_bits_0"] == 0.73

    def test_version_mismatch_raises(self):
        bad = {"protocol_version": "0.0", "final_state": "x", "returns": {}}
        with pytest.raises(BridgeError):
            parse_result(bad)

    def test_non_json_result_raises(self):
        with pytest.raises(BridgeError):
            parse_result("not json {")


class TestInbound:
    def test_run_inbound_quantum_aggregate(self):
        env = build_invocation("QForward", {"theta": 0.5}, 1024, {"prob": "prob_bits_0"})
        res = run_inbound(_file(_QFORWARD), env, seed=42)
        assert res["final_state"] == "|measured>"
        assert 0.0 <= res["returns"]["prob_bits_0"] <= 1.0
        assert res["returns"]["hist_bits_0"][0] + res["returns"]["hist_bits_0"][1] == 1024
        assert "error" not in res

    def test_run_inbound_unresolved_child_is_child_error(self):
        env = build_invocation("Missing", {}, None, {})
        res = run_inbound(_file(_QFORWARD), env)
        assert res["error"]["code"] == "UNRESOLVED_CHILD"


def _qorca_bridge_runner(child_file):
    return [sys.executable, "-m", "q_orca.cli", "run", str(child_file), "--bridge"]


class TestOutboundOverBridge:
    def test_foreign_child_dispatched_end_to_end(self, tmp_path):
        child = tmp_path / "forward.q.orca.md"
        child.write_text(_QFORWARD)
        pf = _file(_PARENT)
        result = run_composed(
            pf, pf.machines[0],
            QIterativeSimulationOptions(seed_simulator=42),
            foreign_runners={"QForward": _qorca_bridge_runner(child)},
        )
        assert result.final_context["prob"] >= 0.0
        assert result.child_runs[0]["foreign"] is True

    def test_bridge_error_on_unlaunchable_runner(self):
        pf = _file(_PARENT)
        with pytest.raises(BridgeError):
            run_composed(
                pf, pf.machines[0],
                QIterativeSimulationOptions(seed_simulator=42),
                foreign_runners={"QForward": ["q-orca-no-such-binary-xyz"]},
            )

    def test_child_error_surfaces_as_runtime_error(self, tmp_path):
        # The foreign runner is q-orca --bridge on a file WITHOUT QForward → the
        # result envelope carries an UNRESOLVED_CHILD error → run_composed raises.
        empty = tmp_path / "other.q.orca.md"
        empty.write_text(_CLASSICAL)  # has Counter, not QForward
        pf = _file(_PARENT)
        with pytest.raises(QIterativeRuntimeError):
            run_composed(
                pf, pf.machines[0],
                QIterativeSimulationOptions(seed_simulator=42),
                foreign_runners={"QForward": _qorca_bridge_runner(empty)},
            )
