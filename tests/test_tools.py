"""Tests for Q-Orca MCP tool definitions."""

from q_orca.tools import Q_ORCA_TOOLS


class TestToolDefinitions:
    def test_tool_count(self):
        assert len(Q_ORCA_TOOLS) == 7

    def test_all_tools_have_required_fields(self):
        for tool in Q_ORCA_TOOLS:
            assert "name" in tool, f"Tool missing 'name': {tool}"
            assert "description" in tool, f"Tool {tool['name']} missing 'description'"
            assert "inputSchema" in tool, f"Tool {tool['name']} missing 'inputSchema'"

    def test_tool_names(self):
        names = {t["name"] for t in Q_ORCA_TOOLS}
        expected = {
            "parse_machine",
            "verify_machine",
            "compile_machine",
            "generate_machine",
            "refine_machine",
            "simulate_machine",
            "server_status",
        }
        assert names == expected

    def test_schemas_are_valid_objects(self):
        for tool in Q_ORCA_TOOLS:
            schema = tool["inputSchema"]
            assert schema["type"] == "object"
            assert "properties" in schema
