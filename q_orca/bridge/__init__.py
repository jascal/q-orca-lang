"""Cross-tool composition bridge (classical-orca <-> q-orca)."""

from q_orca.bridge.protocol import (
    BRIDGE_PROTOCOL_VERSION,
    BridgeError,
    build_invocation,
    descriptor_for,
    make_result,
    parse_result,
)

__all__ = [
    "BRIDGE_PROTOCOL_VERSION",
    "BridgeError",
    "build_invocation",
    "descriptor_for",
    "make_result",
    "parse_result",
]
