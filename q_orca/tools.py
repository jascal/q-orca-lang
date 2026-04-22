"""Q-Orca MCP tools — JSON schemas for MCP tool exposure."""

# Q-Orca tools for MCP server exposure.
# Each tool has a name, description, and input schema.

Q_ORCA_TOOLS = [
    {
        "name": "parse_machine",
        "description": "Parse a Q-Orca quantum machine definition and return its structure as JSON.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "Raw Q-Orca source content (.q.orca.md format). Provide either source or file.",
                },
                "file": {
                    "type": "string",
                    "description": "Path to a .q.orca.md file. Provide either source or file.",
                },
            },
        },
    },
    {
        "name": "verify_machine",
        "description": "Verify a Q-Orca quantum machine definition using the 5-stage verification pipeline: structural, completeness, determinism, quantum-specific, and superposition leak checks.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "Raw Q-Orca source content. Provide either source or file.",
                },
                "file": {
                    "type": "string",
                    "description": "Path to a .q.orca.md file. Provide either source or file.",
                },
                "skip_completeness": {
                    "type": "boolean",
                    "description": "Skip event completeness checks",
                    "default": False,
                },
                "skip_quantum": {
                    "type": "boolean",
                    "description": "Skip quantum-specific checks (unitarity, entanglement, no-cloning)",
                    "default": False,
                },
            },
        },
    },
    {
        "name": "compile_machine",
        "description": "Compile a Q-Orca machine to Mermaid state diagram, OpenQASM 3.0, or Qiskit Python script.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "Raw Q-Orca source content",
                },
                "file": {
                    "type": "string",
                    "description": "Path to a .q.orca.md file",
                },
                "target": {
                    "type": "string",
                    "enum": ["mermaid", "qasm", "qiskit"],
                    "description": "Compilation target format",
                    "default": "qasm",
                },
            },
        },
    },
    {
        "name": "generate_machine",
        "description": "Generate a Q-Orca quantum machine from a natural language specification using an LLM. The machine will be verified and iteratively refined if errors are found.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "spec": {
                    "type": "string",
                    "description": "Natural language description of the quantum state machine to generate",
                },
            },
            "required": ["spec"],
        },
    },
    {
        "name": "refine_machine",
        "description": "Refine a Q-Orca machine by fixing verification errors using an LLM. If errors are not provided, the machine will be auto-verified first.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "Raw Q-Orca source content",
                },
                "file": {
                    "type": "string",
                    "description": "Path to a .q.orca.md file",
                },
                "errors": {
                    "type": "array",
                    "description": "List of verification errors to fix",
                },
                "max_iterations": {
                    "type": "integer",
                    "description": "Maximum refinement iterations",
                    "default": 3,
                },
            },
        },
    },
    {
        "name": "simulate_machine",
        "description": "Simulate a Q-Orca quantum machine using Qiskit. Generates or runs a Qiskit Python script.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "Raw Q-Orca source content. Provide either source or file.",
                },
                "file": {
                    "type": "string",
                    "description": "Path to a .q.orca.md file. Provide either source or file.",
                },
                "run": {
                    "type": "boolean",
                    "description": "Run the simulation immediately",
                    "default": False,
                },
                "shots": {
                    "type": "integer",
                    "description": "Number of shots for noisy simulation",
                    "default": 1024,
                },
                "analytic": {
                    "type": "boolean",
                    "description": "Use exact statevector simulation",
                    "default": True,
                },
                "skip_qutip": {
                    "type": "boolean",
                    "description": "Skip QuTiP verification",
                    "default": False,
                },
                "verbose": {
                    "type": "boolean",
                    "description": "When running a machine under the iterative runtime, include the full per-iteration trace in the response.",
                    "default": False,
                },
            },
        },
    },
    {
        "name": "server_status",
        "description": "Get Q-Orca MCP server status including version, configured LLM provider, and API key status.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
]


__all__ = ["Q_ORCA_TOOLS"]
