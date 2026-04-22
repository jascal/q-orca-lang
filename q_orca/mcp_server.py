#!/usr/bin/env python3
"""Q-Orca MCP server — exposes Q-Orca skills via Model Context Protocol (stdio).

This server speaks the MCP protocol over stdin/stdout, allowing AI clients
(Claude Code, etc.) to call Q-Orca skills as tools.

Usage:
    python -m q_orca.mcp_server
    # or via installed package:
    q-orca-mcp

Environment variables (ORCA_* prefix overrides config file):
    ORCA_PROVIDER     LLM provider: anthropic, openai, minimax, ollama, grok
    ORCA_MODEL        Model name
    ORCA_BASE_URL     API base URL (for proxies, MiniMax, etc.)
    ORCA_API_KEY      API key
    ORCA_MAX_TOKENS   Max tokens per request
    ORCA_TEMPERATURE  Sampling temperature
"""

import json
import os
import sys
import asyncio
from pathlib import Path

# Q-Orca modules
from q_orca import __version__
from q_orca.skills import (
    parse_skill,
    verify_skill,
    compile_skill,
    generate_skill,
    refine_skill,
    SkillInput,
)
from q_orca.tools import Q_ORCA_TOOLS
from q_orca.runtime.python import simulate_machine, QSimulationOptions


MCP_INSTRUCTIONS = """Q-Orca MCP Server — quantum state machine generation and verification tools.

## Workflow
generate_machine → verify_machine → refine_machine (if errors) → compile_machine → generate_actions.

## Q-Orca Syntax Overview

# machine MyQuantumMachine

## context
| Field | Type | Default |
|-------|------|---------|
| qubits | list<qubit> | |

## events
- prepare
- entangle
- measure

## state |00> [initial]
> Ground state

## state |ψ> = (|00> + |11>)/√2 [final]
> Bell state — maximally entangled

## transitions
| Source | Event | Guard | Target | Action |
|--------|-------|-------|--------|--------|
| |00> | prepare | | |00> | apply_H |

## actions
| Name | Signature | Effect |
|------|-----------|--------|
| apply_H | (qs) -> qs | Hadamard(qs[0]) |

## verification rules
- unitarity: all gates preserve norm
- entanglement: Bell state has Schmidt rank > 1
"""

TOOLS = Q_ORCA_TOOLS


async def call_tool(name: str, arguments: dict) -> dict:
    """Dispatch an MCP tool call to the appropriate skill function."""
    match name:
        case "parse_machine":
            inp = SkillInput(source=arguments.get("source"), file=arguments.get("file"))
            return parse_skill(inp)

        case "verify_machine":
            inp = SkillInput(source=arguments.get("source"), file=arguments.get("file"))
            return verify_skill(
                inp,
                skip_completeness=arguments.get("skip_completeness", False),
                skip_quantum=arguments.get("skip_quantum", False),
            )

        case "compile_machine":
            inp = SkillInput(source=arguments.get("source"), file=arguments.get("file"))
            return compile_skill(inp, arguments.get("target", "qasm"))

        case "generate_machine":
            spec = arguments.get("spec", "")
            return await generate_skill(spec)

        case "refine_machine":
            inp = SkillInput(source=arguments.get("source"), file=arguments.get("file"))
            errors = arguments.get("errors")
            max_iterations = arguments.get("max_iterations", 3)
            return await refine_skill(inp, errors, max_iterations)

        case "simulate_machine":
            inp = SkillInput(source=arguments.get("source"), file=arguments.get("file"))
            from q_orca.parser.markdown_parser import parse_q_orca_markdown
            parsed = parse_q_orca_markdown(inp["source"] if "source" in inp else Path(inp["file"]).read_text())
            if not parsed.file.machines:
                return {"success": False, "error": "No machine found"}
            machine = parsed.file.machines[0]
            opts = QSimulationOptions(
                analytic=arguments.get("analytic", True),
                shots=arguments.get("shots", 1024),
                run=arguments.get("run", False),
                skip_qutip=arguments.get("skip_qutip", False),
            )
            if opts.run:
                result = simulate_machine(machine, opts)
                from q_orca.runtime.types import QIterativeSimulationResult

                if isinstance(result, QIterativeSimulationResult):
                    verbose = bool(arguments.get("verbose", False))
                    trace_entries = [
                        {
                            "iteration": t.iteration,
                            "source": t.source_state,
                            "target": t.target_state,
                            "event": t.event,
                            "action": t.action,
                            "bits": t.measurement_bits,
                            "context": t.context_snapshot,
                        }
                        for t in (result.trace if verbose else [])
                    ]
                    return {
                        "success": result.success,
                        "machine": machine.name,
                        "runtime": "iterative",
                        "finalState": result.final_state,
                        "finalContext": result.final_context,
                        "aggregateCounts": result.aggregate_counts,
                        "iterations": len(result.trace),
                        "trace": trace_entries,
                        "error": result.error,
                    }

                # QuTiPVerificationResult is a dataclass — convert to dict for JSON
                import dataclasses
                qutip_dict = (
                    dataclasses.asdict(result.qutip_verification)
                    if result.qutip_verification is not None
                    else None
                )
                return {
                    "success": result.success,
                    "machine": machine.name,
                    "probabilities": result.probabilities,
                    "counts": result.counts,
                    "qutipVerification": qutip_dict,
                    "error": result.error,
                }
            else:
                from q_orca.compiler.qiskit import compile_to_qiskit
                script = compile_to_qiskit(machine, opts)
                return {"success": True, "machine": machine.name, "script": script}

        case "server_status":
            api_key_configured = bool(
                os.environ.get("ORCA_API_KEY")
                or os.environ.get("ANTHROPIC_API_KEY")
                or os.environ.get("OPENAI_API_KEY")
                or os.environ.get("MINIMAX_API_KEY")
                or os.environ.get("GROK_API_KEY")
            )
            return {
                "version": __version__,
                "python_version": sys.version,
                "provider": os.environ.get("ORCA_PROVIDER", "anthropic"),
                "model": os.environ.get("ORCA_MODEL", "claude-sonnet-4-6"),
                "base_url": os.environ.get("ORCA_BASE_URL") or None,
                "max_tokens": int(os.environ["ORCA_MAX_TOKENS"]) if "ORCA_MAX_TOKENS" in os.environ else 4096,
                "temperature": float(os.environ["ORCA_TEMPERATURE"]) if "ORCA_TEMPERATURE" in os.environ else 0.7,
                "api_key_configured": api_key_configured,
            }

        case _:
            raise ValueError(f"Unknown tool: {name}")


def format_result(result: dict) -> list[dict]:
    """Format a skill result as MCP content array."""
    return [{"type": "text", "text": json.dumps(result, indent=2)}]


def format_error(error: str) -> list[dict]:
    """Format an error as MCP error content."""
    return [{"type": "text", "text": error}]


async def handle_request(request: dict) -> dict:
    """Handle a single MCP JSON-RPC request."""
    method = request.get("method", "")
    params = request.get("params", {})
    req_id = request.get("id")

    # JSON-RPC response base
    def resp(result: dict, is_error: bool = False):
        r = {"jsonrpc": "2.0", "id": req_id}
        if is_error:
            r["error"] = result
        else:
            r["result"] = result
        return r

    try:
        match method:
            case "initialize":
                return resp({
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "q-orca", "version": __version__},
                    "instructions": MCP_INSTRUCTIONS,
                })

            case "tools/list":
                return resp({"tools": TOOLS})

            case "tools/call":
                tool_name = params.get("name", "")
                arguments = params.get("arguments", {})
                try:
                    result = await call_tool(tool_name, arguments)
                    return resp({"content": format_result(result), "isError": False})
                except Exception as e:
                    return resp({"content": format_error(str(e)), "isError": True})

            case "ping":
                return resp({"pong": True})

            case _:
                # Notification (no id) — ok to ignore
                if req_id is None:
                    return None
                return resp({"error": f"Method not found: {method}"}, is_error=True)

    except Exception as e:
        if req_id is None:
            return None
        return resp({"code": -32603, "message": str(e)}, is_error=True)


async def main():
    """Read newline-delimited JSON-RPC requests from stdin, write responses to stdout."""
    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader()
    await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), sys.stdin)

    while True:
        line = await reader.readline()
        if not line:
            break  # EOF

        line = line.strip()
        if not line:
            continue

        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            err = json.dumps({
                "jsonrpc": "2.0",
                "error": {"code": -32700, "message": "Invalid JSON"},
                "id": None,
            })
            sys.stdout.write(err + "\n")
            sys.stdout.flush()
            continue

        result = await handle_request(parsed)
        if result is not None:
            sys.stdout.write(json.dumps(result) + "\n")
            sys.stdout.flush()


def run():
    """Synchronous entry point for console_scripts."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
