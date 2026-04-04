"""Q-Orca skills — LLM-friendly skill functions for quantum state machines.

This module provides skill functions similar to orca-lang's skills.ts but
adapted for Q-Orca's quantum domain. Skills accept either a source string
or a file path and return structured JSON results.
"""

import re
from pathlib import Path
from typing import TypedDict

from q_orca.parser.markdown_parser import parse_q_orca_markdown
from q_orca.verifier import verify, VerifyOptions
from q_orca.compiler.mermaid import compile_to_mermaid
from q_orca.compiler.qasm import compile_to_qasm
from q_orca.compiler.qiskit import compile_to_qiskit, QSimulationOptions
from q_orca.ast import QMachineDef, QStateDef
from q_orca.config import load_config
from q_orca.llm import create_provider, LLMMessage, LLMRequest, LLMProviderConfig


# ── Skill Input ─────────────────────────────────────────────────────────────────

class SkillInput(TypedDict, total=False):
    source: str
    file: str


def _resolve_source(input: SkillInput) -> str:
    if "source" in input and input["source"] is not None:
        return input["source"]
    if "file" in input and input["file"] is not None:
        return Path(input["file"]).read_text()
    raise ValueError("SkillInput requires either source or file")


def _resolve_label(input: SkillInput) -> str:
    return input.get("file", "<source>")


# ── Skill Error ─────────────────────────────────────────────────────────────────

class SkillError(TypedDict):
    code: str
    message: str
    severity: str  # "error" | "warning"
    location: dict | None
    suggestion: str | None


# ── Parse Skill ─────────────────────────────────────────────────────────────────

class ParsedTransition(TypedDict):
    source: str
    event: str
    guard: str | None
    target: str
    action: str | None


class ParsedMachine(TypedDict):
    name: str
    states: list[str]
    events: list[str]
    transitions: list[ParsedTransition]
    guards: list[dict]
    actions: list[dict]
    effects: list[dict]
    context: list[dict]


class ParseSkillResult(TypedDict, total=False):
    status: str  # "success" | "error"
    machines: list[ParsedMachine]
    machine: ParsedMachine | None
    error: str | None


def _collect_state_names(states: list[QStateDef]) -> list[str]:
    names = []
    for s in states:
        names.append(s.name)
    return names


def _machine_to_parsed(machine: QMachineDef) -> ParsedMachine:
    return ParsedMachine(
        name=machine.name,
        states=_collect_state_names(machine.states),
        events=[e.name for e in machine.events],
        transitions=[
            ParsedTransition(
                source=t.source,
                event=t.event,
                guard=(f"!{t.guard.name}" if t.guard and t.guard.negated else t.guard.name if t.guard else None),
                target=t.target,
                action=t.action,
            )
            for t in machine.transitions
        ],
        guards=[
            {"name": g.name, "expression": str(g.expression)}
            for g in machine.guards
        ],
        actions=[
            {"name": a.name, "hasEffect": a.has_effect, "effectType": a.effect_type}
            for a in machine.actions
        ],
        effects=[
            {"name": e.name, "input": e.input, "output": e.output}
            for e in machine.effects
        ],
        context=[
            {"name": f.name, "type": f.type.kind, "default": f.default_value}
            for f in machine.context
        ],
    )


def parse_skill(input: SkillInput) -> ParseSkillResult:
    """Parse a Q-Orca machine definition and return structured result."""
    try:
        source = _resolve_source(input)
        parsed = parse_q_orca_markdown(source)
        machines = [_machine_to_parsed(m) for m in parsed.file.machines]
        return ParseSkillResult(
            status="success",
            machines=machines,
            machine=machines[0] if machines else None,
        )
    except Exception as e:
        return ParseSkillResult(status="error", error=str(e))


# ── Verify Skill ───────────────────────────────────────────────────────────────

class VerifySkillResult(TypedDict, total=False):
    status: str  # "valid" | "invalid"
    machine: str
    states: int
    events: int
    transitions: int
    errors: list[SkillError]


def verify_skill(input: SkillInput, skip_completeness: bool = False, skip_quantum: bool = False) -> VerifySkillResult:
    """Verify a Q-Orca machine definition (5-stage pipeline)."""
    try:
        source = _resolve_source(input)
        parsed = parse_q_orca_markdown(source)

        if not parsed.file.machines:
            return VerifySkillResult(
                status="invalid",
                machine="unknown",
                states=0,
                events=0,
                transitions=0,
                errors=[SkillError(
                    code="PARSE_ERROR",
                    message="No machine definition found",
                    severity="error",
                    location=None,
                    suggestion="Ensure the file contains a valid Q-Orca machine definition",
                )],
            )

        machine = parsed.file.machines[0]
        opts = VerifyOptions(skip_completeness=skip_completeness, skip_quantum=skip_quantum)
        result = verify(machine, opts)

        def map_error(e) -> SkillError:
            return SkillError(
                code=e.code,
                message=e.message,
                severity=e.severity,
                location=e.location,
                suggestion=e.suggestion,
            )

        return VerifySkillResult(
            status="valid" if result.valid else "invalid",
            machine=machine.name,
            states=len(machine.states),
            events=len(machine.events),
            transitions=len(machine.transitions),
            errors=[map_error(e) for e in result.errors],
        )
    except Exception as e:
        return VerifySkillResult(
            status="invalid",
            machine="unknown",
            states=0,
            events=0,
            transitions=0,
            errors=[SkillError(
                code="PARSE_ERROR",
                message=str(e),
                severity="error",
                location=None,
                suggestion="Check Q-Orca syntax",
            )],
        )


# ── Compile Skill ───────────────────────────────────────────────────────────────

class CompileSkillResult(TypedDict, total=False):
    status: str  # "success" | "error"
    target: str  # "mermaid" | "qasm" | "qiskit"
    output: str
    warnings: list[SkillError]


def compile_skill(input: SkillInput, target: str) -> CompileSkillResult:
    """Compile a Q-Orca machine to Mermaid, QASM, or Qiskit format."""
    try:
        source = _resolve_source(input)
        parsed = parse_q_orca_markdown(source)

        if not parsed.file.machines:
            return CompileSkillResult(
                status="error",
                target=target,
                output="",
                warnings=[],
            )

        machine = parsed.file.machines[0]

        if target == "mermaid":
            output = compile_to_mermaid(machine)
        elif target == "qasm":
            output = compile_to_qasm(machine)
        elif target == "qiskit":
            opts = QSimulationOptions(analytic=True, run=False)
            output = compile_to_qiskit(machine, opts)
        else:
            return CompileSkillResult(
                status="error",
                target=target,
                output="",
                warnings=[{"code": "UNKNOWN_TARGET", "message": f"Unknown target: {target}", "severity": "error", "location": None, "suggestion": "Use mermaid, qasm, or qiskit"}],
            )

        # Run verification for warnings
        warnings: list[SkillError] = []
        opts = VerifyOptions()
        result = verify(machine, opts)
        for e in result.errors:
            if e.severity == "warning":
                warnings.append({"code": e.code, "message": e.message, "severity": "warning", "location": e.location, "suggestion": e.suggestion})

        return CompileSkillResult(status="success", target=target, output=output, warnings=warnings)
    except Exception as e:
        return CompileSkillResult(
            status="error",
            target=target,
            output="",
            warnings=[],
        )


# ── Generate Skill ─────────────────────────────────────────────────────────────

Q_ORCA_SYNTAX_REFERENCE = """Q-Orca Quantum State Machine Markdown Syntax Reference (.q.orca.md):

# machine MyQuantumMachine

## context
| Field       | Type          | Default |
|-------------|---------------|---------|
| qubits      | list<qubit>   |         |

## events
- prepare
- entangle
- measure

## state |00> [initial]
> Ground state

## state |ψ> = (|00> + |11>)/√2 [final]
> Bell state — maximally entangled

## transitions
| Source | Event    | Guard | Target | Action           |
|--------|----------|-------|--------|------------------|
| |00>   | prepare  |       | |00>   | apply_H          |
| |00>   | entangle |       | |ψ>    | apply_CNOT        |

## actions
| Name       | Signature     | Effect           |
|------------|---------------|------------------|
| apply_H    | (qs) -> qs   | Hadamard(qs[0]) |
| apply_CNOT | (qs) -> qs   | CNOT(qs[0], qs[1]) |

## verification rules
- unitarity: all gates preserve norm
- entanglement: Bell state has Schmidt rank > 1
- completeness: all collapse branches covered
- no-cloning: no copy operations
"""


class GenerateSkillResult(TypedDict, total=False):
    status: str  # "success" | "error" | "requires_refinement"
    machine: str | None
    orca: str | None
    verification: VerifySkillResult | None
    error: str | None


async def generate_skill(spec: str, max_iterations: int = 3) -> GenerateSkillResult:
    """Generate a Q-Orca quantum machine from natural language spec using LLM."""
    import os

    config = load_config()

    # Check API key availability
    anthropic_key = config.api_key or os.environ.get("ORCA_API_KEY") or os.environ.get("MINIMAX_API_KEY") or os.environ.get("ANTHROPIC_API_KEY", "")
    openai_key = config.api_key or os.environ.get("ORCA_API_KEY") or os.environ.get("OPENAI_API_KEY", "")

    has_key = (
        (config.provider == "openai" and openai_key) or
        (config.provider == "ollama") or
        (bool(anthropic_key) if config.provider == "anthropic" else False)
    )

    if not has_key:
        key_name = "OPENAI_API_KEY" if config.provider == "openai" else "ANTHROPIC_API_KEY"
        return GenerateSkillResult(
            status="error",
            error=f"No API key available. Set {key_name} in your environment.",
        )

    llm_config = LLMProviderConfig(
        api_key=config.api_key,
        base_url=config.base_url,
        model=config.model,
        max_tokens=config.max_tokens,
        temperature=config.temperature,
    )
    provider = create_provider(config.provider, llm_config)

    system_prompt = f"""You are an expert in Q-Orca — a quantum-aware state machine language.
Generate Q-Orca machine definitions in markdown (.q.orca.md) format from natural language descriptions.

{Q_ORCA_SYNTAX_REFERENCE}

Key rules:
- States use Dirac ket notation: |00>, |01>, |ψ>, etc.
- [initial] marks the initial state, [final] marks terminal states
- Gates are quantum operations: H (Hadamard), X, Y, Z, CNOT, CZ, SWAP, T, S, Rx, Ry, Rz
- Actions represent gate applications on qubits
- Every (state, event) pair must have a transition or explicit ignore
- Context should contain qubit registers and quantum state

Output ONLY the Q-Orca machine definition in .q.orca.md markdown format, wrapped in a code fence, with no additional text."""

    current_orca = ""
    last_errors: list[SkillError] = []
    iteration = 0

    while iteration < max_iterations:
        user_prompt = (
            f"Generate a Q-Orca state machine for:\n{spec}"
            if iteration == 0
            else f"""Previous Q-Orca had verification errors. Fix them:

Previous Q-Orca:
{current_orca}

Verification errors:
{_format_errors(last_errors)}

Provide the corrected Q-Orca machine definition:"""
        )

        try:
            response = await provider.complete(LLMRequest(
                messages=[LLMMessage(role="system", content=system_prompt), LLMMessage(role="user", content=user_prompt)],
                model=config.model,
                max_tokens=config.max_tokens,
                temperature=config.temperature,
            ))

            current_orca = _strip_code_fence(response.content)
            verify_result = verify_skill({"source": current_orca})

            if verify_result["status"] == "valid":
                return GenerateSkillResult(
                    status="success",
                    machine=verify_result["machine"],
                    orca=current_orca,
                    verification=verify_result,
                )

            last_errors = verify_result["errors"]
            iteration += 1
        except Exception as e:
            return GenerateSkillResult(status="error", error=str(e))

    return GenerateSkillResult(
        status="requires_refinement",
        machine=_extract_machine_name(current_orca),
        orca=current_orca,
        verification=verify_skill({"source": current_orca}),
    )


# ── Refine Skill ───────────────────────────────────────────────────────────────

class RefineSkillResult(TypedDict, total=False):
    status: str  # "success" | "requires_refinement" | "error"
    corrected: str | None
    verification: VerifySkillResult | None
    iterations: int
    changes: list[str]
    error: str | None


async def refine_skill(input: SkillInput, errors: list[SkillError] | None = None, max_iterations: int = 3) -> RefineSkillResult:
    """Refine a Q-Orca machine based on verification errors."""
    import os

    config = load_config()

    # Check API key
    anthropic_key = config.api_key or os.environ.get("ORCA_API_KEY") or os.environ.get("MINIMAX_API_KEY") or os.environ.get("ANTHROPIC_API_KEY", "")
    openai_key = config.api_key or os.environ.get("ORCA_API_KEY") or os.environ.get("OPENAI_API_KEY", "")

    has_key = (
        (config.provider == "openai" and openai_key) or
        (config.provider == "ollama") or
        (bool(anthropic_key) if config.provider == "anthropic" else False)
    )

    if not has_key:
        key_name = "OPENAI_API_KEY" if config.provider == "openai" else "ANTHROPIC_API_KEY"
        return RefineSkillResult(status="error", iterations=0, changes=[], error=f"No API key available. Set {key_name}.")

    if errors is None:
        verify_result = verify_skill(input)
        if verify_result["status"] == "valid":
            return RefineSkillResult(
                status="success",
                corrected=_resolve_source(input),
                iterations=0,
                changes=["Machine already valid — no refinement needed"],
            )
        errors = [e for e in verify_result["errors"] if e["severity"] == "error"]

    llm_config = LLMProviderConfig(
        api_key=config.api_key,
        base_url=config.base_url,
        model=config.model,
        max_tokens=config.max_tokens,
        temperature=config.temperature,
    )
    provider = create_provider(config.provider, llm_config)

    initial_source = _resolve_source(input)
    parsed = parse_q_orca_markdown(initial_source)
    machine = parsed.file.machines[0] if parsed.file.machines else None

    system_prompt = f"""You are an expert in Q-Orca — a quantum-aware state machine language.
Given verification errors, fix the machine definition.

{Q_ORCA_SYNTAX_REFERENCE}

Output ONLY the corrected Q-Orca machine definition in .q.orca.md format, wrapped in a code fence, with no explanations."""

    current_source = initial_source

    for i in range(max_iterations):
        error_list = "\n".join(f"[{e['severity'].upper()}] {e['code']}: {e['message']}" for e in errors)

        user_prompt = f"""Machine: {machine.name if machine else 'unknown'}
States: {', '.join(s.name for s in machine.states) if machine else 'unknown'}
Events: {', '.join(e.name for e in machine.events) if machine else 'unknown'}

Verification Errors:
{error_list}

Machine Definition:
{current_source}

Provide the corrected machine definition:"""

        try:
            response = await provider.complete(LLMRequest(
                messages=[LLMMessage(role="system", content=system_prompt), LLMMessage(role="user", content=user_prompt)],
                model=config.model,
                max_tokens=config.max_tokens,
                temperature=0.3,
            ))

            current_source = _strip_code_fence(response.content)
            verify_result = verify_skill({"source": current_source})

            if verify_result["status"] == "valid":
                return RefineSkillResult(
                    status="success",
                    corrected=current_source,
                    verification=verify_result,
                    iterations=i + 1,
                    changes=[f"Corrected after {i + 1} iteration(s)"],
                )

            errors = [e for e in verify_result["errors"] if e["severity"] == "error"]

            try:
                m = parse_q_orca_markdown(current_source).file.machines[0]
                machine = m
            except Exception:
                pass
        except Exception as e:
            return RefineSkillResult(status="error", iterations=i, changes=[], error=str(e))

    final_verification = verify_skill({"source": current_source})
    return RefineSkillResult(
        status="requires_refinement",
        corrected=current_source,
        verification=final_verification,
        iterations=max_iterations,
        changes=[f"{max_iterations} iteration(s) attempted but errors remain"],
    )


# ── Helpers ──────────────────────────────────────────────────────────────────────

def _strip_code_fence(code: str) -> str:
    """Remove markdown code fence from LLM output."""
    return (
        code.replace("```q-orca", "")
            .replace("```orca", "")
            .replace("```markdown", "")
            .replace("```", "")
            .strip()
    )


def _extract_machine_name(orca: str) -> str:
    """Extract machine name from Q-Orca source."""
    match = re.search(r"(?:#\s+)?machine\s+(\w+)", orca)
    return match.group(1) if match else "Unknown"


def _format_errors(errors: list[SkillError]) -> str:
    return "\n".join(f"[{e['severity'].upper()}] {e['code']}: {e['message']}" for e in errors)
