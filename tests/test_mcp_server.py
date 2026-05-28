"""Tests for `q_orca.mcp_server` — focused on the `tools/call` error path.

Pins task §4.3 of the tech-debt-backlog: absolute filesystem paths must
not leak verbatim through caught exceptions on the JSON-RPC response.
"""

from __future__ import annotations

import asyncio

import pytest

from q_orca.mcp_server import (
    _ABS_PATH_RE,
    _sanitize_exception_message,
    handle_request,
)


class TestSanitizeExceptionMessage:
    def test_strips_unix_absolute_path(self):
        try:
            raise FileNotFoundError(
                "[Errno 2] No such file or directory: '/Users/allans/secret/foo.md'"
            )
        except FileNotFoundError as e:
            msg = _sanitize_exception_message(e)
        assert "/Users/allans/secret/foo.md" not in msg
        assert "<path>" in msg
        assert msg.startswith("FileNotFoundError:")

    def test_strips_home_path(self):
        try:
            raise OSError("could not open /home/user/.config/q-orca/cache")
        except OSError as e:
            msg = _sanitize_exception_message(e)
        assert "/home/user/.config/q-orca/cache" not in msg
        assert "<path>" in msg
        assert msg.startswith("OSError:")

    def test_strips_windows_absolute_path(self):
        try:
            raise FileNotFoundError(
                r"[Errno 2] No such file or directory: 'C:\Users\admin\secret.md'"
            )
        except FileNotFoundError as e:
            msg = _sanitize_exception_message(e)
        assert r"C:\Users\admin\secret.md" not in msg
        assert "<path>" in msg

    def test_strips_windows_forward_slash_path(self):
        try:
            raise FileNotFoundError("missing: C:/Users/admin/file.md")
        except FileNotFoundError as e:
            msg = _sanitize_exception_message(e)
        assert "C:/Users/admin/file.md" not in msg
        assert "<path>" in msg

    def test_preserves_exception_class_name(self):
        try:
            raise ValueError("bad input")
        except ValueError as e:
            msg = _sanitize_exception_message(e)
        assert msg == "ValueError: bad input"

    def test_does_not_strip_single_slash_token(self):
        # A `/foo` (one segment) isn't an absolute filesystem path leak —
        # could be a route name, a header, etc. Keep the regex tight so
        # we don't redact meaningful content.
        try:
            raise ValueError("ratio is 1/2 not /tmp anywhere")
        except ValueError as e:
            msg = _sanitize_exception_message(e)
        assert "1/2" in msg
        # Bare `/tmp` (one segment) stays — only ≥2-segment paths redact.
        assert "/tmp" in msg

    def test_strips_two_segment_path(self):
        try:
            raise ValueError("found /tmp/scratch.md unexpectedly")
        except ValueError as e:
            msg = _sanitize_exception_message(e)
        assert "/tmp/scratch.md" not in msg
        assert "<path>" in msg

    def test_strips_multiple_paths_in_one_message(self):
        try:
            raise ValueError(
                "could not link /Users/a/in.md to /Users/b/out.md"
            )
        except ValueError as e:
            msg = _sanitize_exception_message(e)
        assert "/Users/a/in.md" not in msg
        assert "/Users/b/out.md" not in msg
        assert msg.count("<path>") == 2

    def test_debug_flag_bypasses_sanitisation(self, monkeypatch):
        monkeypatch.setenv("ORCA_MCP_DEBUG", "1")
        try:
            raise FileNotFoundError("/Users/allans/foo/bar.md")
        except FileNotFoundError as e:
            msg = _sanitize_exception_message(e)
        # Debug mode keeps the original path intact for local triage.
        assert "/Users/allans/foo/bar.md" in msg
        assert "<path>" not in msg
        assert msg.startswith("FileNotFoundError:")

    def test_debug_flag_off_by_default(self, monkeypatch):
        monkeypatch.delenv("ORCA_MCP_DEBUG", raising=False)
        try:
            raise FileNotFoundError("/Users/allans/foo/bar.md")
        except FileNotFoundError as e:
            msg = _sanitize_exception_message(e)
        assert "/Users/allans/foo/bar.md" not in msg
        assert "<path>" in msg

    def test_regex_matches_expected_shapes(self):
        # Direct regex sanity checks so a future tweak doesn't silently
        # narrow the match.
        assert _ABS_PATH_RE.search("/Users/x/y.md")
        assert _ABS_PATH_RE.search("/home/x/y")
        assert _ABS_PATH_RE.search("/var/log/foo")
        assert _ABS_PATH_RE.search(r"C:\Users\x\y.md")
        assert _ABS_PATH_RE.search("C:/Users/x/y.md")
        # One-segment paths and bare slashes don't trigger.
        assert _ABS_PATH_RE.search("/tmp") is None
        assert _ABS_PATH_RE.search("/") is None
        assert _ABS_PATH_RE.search("1/2") is None


class TestToolsCallErrorPath:
    """End-to-end: the `tools/call` JSON-RPC path must sanitise exceptions."""

    def test_unknown_tool_error_carries_no_absolute_path(self):
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "definitely_not_a_real_tool", "arguments": {}},
        }
        response = asyncio.run(handle_request(request))
        assert response["result"]["isError"] is True
        text = response["result"]["content"][0]["text"]
        # ValueError is what `call_tool` raises for an unknown tool name.
        assert text.startswith("ValueError:")
        assert "definitely_not_a_real_tool" in text  # the tool name is fine

    def test_caught_exception_path_is_sanitised(self, monkeypatch):
        """A tool that raises FileNotFoundError with an absolute path must
        have the path stripped before it lands in the JSON-RPC response."""
        from q_orca import mcp_server

        bogus_path = "/Users/nobody/definitely-missing/q-orca-test.md"

        async def boom(name, arguments):
            raise FileNotFoundError(
                f"[Errno 2] No such file or directory: '{bogus_path}'"
            )

        monkeypatch.setattr(mcp_server, "call_tool", boom)

        request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "parse_machine", "arguments": {}},
        }
        response = asyncio.run(handle_request(request))
        assert response["result"]["isError"] is True
        text = response["result"]["content"][0]["text"]
        assert text.startswith("FileNotFoundError:")
        assert bogus_path not in text
        assert "<path>" in text

    def test_debug_flag_preserves_path_in_tools_call(self, monkeypatch):
        from q_orca import mcp_server

        monkeypatch.setenv("ORCA_MCP_DEBUG", "1")
        bogus_path = "/Users/nobody/another-missing/foo.md"

        async def boom(name, arguments):
            raise FileNotFoundError(bogus_path)

        monkeypatch.setattr(mcp_server, "call_tool", boom)

        request = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "parse_machine", "arguments": {}},
        }
        response = asyncio.run(handle_request(request))
        text = response["result"]["content"][0]["text"]
        assert bogus_path in text
        assert "<path>" not in text
