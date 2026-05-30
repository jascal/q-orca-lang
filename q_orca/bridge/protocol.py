"""Bridge protocol envelopes for cross-tool composition (`add-cross-tool-bridge-protocol`).

Three versioned JSON shapes let classical-orca and q-orca compose across the tool
boundary without sharing an AST:

- **machine descriptor**: `{protocol_version, name, params, returns,
  measurement_bearing}`
- **invocation envelope**: `{protocol_version, child, args, shots, return_bindings}`
- **result envelope**: `{protocol_version, final_state, returns, error?}`

Only JSON scalars/arrays cross the boundary. A `BridgeError` is the transport
(bridge-category) failure; a child error rides in the result envelope's `error`
field. See the change's `specs/bridge-protocol/spec.md`.
"""

from __future__ import annotations

from typing import Optional, Union

from q_orca.ast import (
    QMachineDef,
    QReturnDef,
    QType,
    QTypeCustom,
    QTypeList,
    QTypeOptional,
    QTypeQubit,
    QTypeScalar,
)

BRIDGE_PROTOCOL_VERSION = "1.0"


class BridgeError(Exception):
    """A bridge/transport failure (distinct from a child error in the envelope).

    Raised for: unlaunchable runner, timeout, non-JSON output, or an
    unsupported `protocol_version`.
    """

    code = "BRIDGE_ERROR"


def wire_type(qtype: QType) -> str:
    """Map a q-orca `QType` to a tool-agnostic wire type string.

    Unmappable types raise `BridgeError` so an incompatible boundary is caught
    before any dispatch.
    """
    if isinstance(qtype, QTypeScalar):
        return qtype.kind
    if isinstance(qtype, QTypeQubit):
        return "qubit"
    if isinstance(qtype, QTypeList):
        return f"list<{qtype.element_type}>"
    if isinstance(qtype, QTypeOptional):
        return f"optional<{qtype.inner_type}>"
    if isinstance(qtype, QTypeCustom):
        return qtype.name
    raise BridgeError(f"cannot map q-orca type {qtype!r} to a wire type")


def _machine_is_measurement_bearing(machine: QMachineDef) -> bool:
    # A child property derived from the machine's definition — NOT from shots.
    return any(
        a.measurement is not None or a.mid_circuit_measure is not None
        for a in machine.actions
    )


def _return_descriptor(r: QReturnDef) -> dict:
    return {"name": r.name, "type": wire_type(r.type), "statistics": list(r.statistics)}


def descriptor_for(machine: QMachineDef) -> dict:
    """Emit a machine descriptor: params from context, returns + statistics, kind."""
    return {
        "protocol_version": BRIDGE_PROTOCOL_VERSION,
        "name": machine.name,
        "params": [{"name": f.name, "type": wire_type(f.type)} for f in machine.context],
        "returns": [_return_descriptor(r) for r in machine.returns],
        "measurement_bearing": _machine_is_measurement_bearing(machine),
    }


def build_invocation(
    child: str,
    args: dict,
    shots: Optional[int],
    return_bindings: dict,
) -> dict:
    """Build an invocation envelope (caller has already evaluated args to values)."""
    return {
        "protocol_version": BRIDGE_PROTOCOL_VERSION,
        "child": child,
        "args": dict(args),
        "shots": shots,
        "return_bindings": dict(return_bindings),
    }


def make_result(final_state: str, returns: dict, error: Optional[dict] = None) -> dict:
    """Build a result envelope. `error` is a `{code, message}` dict on child error."""
    envelope = {
        "protocol_version": BRIDGE_PROTOCOL_VERSION,
        "final_state": final_state,
        "returns": dict(returns),
    }
    if error is not None:
        envelope["error"] = error
    return envelope


def _check_version(envelope: dict, kind: str) -> None:
    version = envelope.get("protocol_version")
    if version != BRIDGE_PROTOCOL_VERSION:
        raise BridgeError(
            f"unsupported bridge {kind} protocol_version {version!r} "
            f"(this tool speaks {BRIDGE_PROTOCOL_VERSION!r})"
        )


def parse_result(data: Union[str, bytes, dict]) -> dict:
    """Validate + normalize a result envelope. Raises `BridgeError` on bad shape."""
    if isinstance(data, (str, bytes)):
        import json

        try:
            data = json.loads(data)
        except (ValueError, TypeError) as exc:
            raise BridgeError(f"result envelope is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise BridgeError("result envelope must be a JSON object")
    _check_version(data, "result")
    return {
        "final_state": data.get("final_state", ""),
        "returns": data.get("returns", {}) or {},
        "error": data.get("error"),
    }


def parse_invocation(data: Union[str, bytes, dict]) -> dict:
    """Validate + normalize an invocation envelope (inbound side)."""
    if isinstance(data, (str, bytes)):
        import json

        try:
            data = json.loads(data)
        except (ValueError, TypeError) as exc:
            raise BridgeError(f"invocation envelope is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise BridgeError("invocation envelope must be a JSON object")
    _check_version(data, "invocation")
    if "child" not in data:
        raise BridgeError("invocation envelope is missing 'child'")
    return {
        "child": data["child"],
        "args": data.get("args", {}) or {},
        "shots": data.get("shots"),
        "return_bindings": data.get("return_bindings", {}) or {},
    }
