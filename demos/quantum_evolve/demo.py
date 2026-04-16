"""Quantum Evolve — Genetic Algorithm over Q-Orca Machines

A classical Orca state machine drives a genetic algorithm whose population
consists of Q-Orca quantum state machines.  Each generation:

  1. Evaluate  — an LLM scores every individual against a design goal
  2. Select    — tournament selection picks parents
  3. Breed     — LLM-assisted crossover and mutation produce offspring
  4. Verify    — Q-Orca's 5-stage pipeline filters invalid machines

The outer loop (idle -> initializing -> evaluating -> selecting ->
breeding -> evaluating -> ... -> converged | exhausted) is itself an
Orca state machine executed by orca-runtime-python.

Requirements:
  pip install orca-runtime-python q-orca[all]
  export ORCA_API_KEY=<your key>          # or set api_key in orca.yaml
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import re
import sys
import textwrap
import time
from dataclasses import dataclass, field
from pathlib import Path

from orca_runtime_python import (
    parse_orca_md,
    OrcaMachine,
    get_event_bus,
    Event,
    EventType,
)

from q_orca import (
    parse_q_orca_markdown,
    verify,
    VerifyOptions,
    compile_to_mermaid,
    compile_to_qasm,
)
from q_orca.config import load_config
from q_orca.llm import create_provider, LLMMessage, LLMRequest, LLMProviderConfig
from q_orca.skills import Q_ORCA_SYNTAX_REFERENCE, refine_skill


# ── Terminal styling (ANSI, no dependencies) ─────────────────────────────────

class C:
    """ANSI color codes."""
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    ITALIC  = "\033[3m"
    CYAN    = "\033[36m"
    GREEN   = "\033[32m"
    YELLOW  = "\033[33m"
    RED     = "\033[31m"
    MAGENTA = "\033[35m"
    BLUE    = "\033[34m"
    WHITE   = "\033[37m"
    BCYAN   = "\033[1;36m"
    BGREEN  = "\033[1;32m"
    BYELLOW = "\033[1;33m"
    BRED    = "\033[1;31m"
    BMAGENTA= "\033[1;35m"
    BBLUE   = "\033[1;34m"
    BWHITE  = "\033[1;37m"
    DIMW    = "\033[2;37m"


def _bar(value: float, max_val: float = 100.0, width: int = 20) -> str:
    """Render a Unicode bar chart."""
    ratio = min(value / max_val, 1.0) if max_val > 0 else 0
    filled = int(ratio * width)
    empty = width - filled
    if ratio >= 0.8:
        color = C.BGREEN
    elif ratio >= 0.5:
        color = C.BYELLOW
    else:
        color = C.BRED
    return f"{color}{'█' * filled}{C.DIM}{'░' * empty}{C.RESET}"


def _header(title: str, icon: str = ""):
    prefix = f"  {icon}  " if icon else "  "
    print(f"\n{C.BCYAN}{'─' * 66}")
    print(f"{prefix}{C.BWHITE}{title}{C.RESET}")
    print(f"{C.BCYAN}{'─' * 66}{C.RESET}")


def _phase(num: int, title: str, icon: str = ""):
    prefix = f"  {icon} " if icon else "  "
    print(f"\n{C.BCYAN}{'━' * 66}")
    print(f"{prefix}{C.BWHITE}PHASE {num}: {title}{C.RESET}")
    print(f"{C.BCYAN}{'━' * 66}{C.RESET}")


def _transition(from_s: str, to_s: str):
    print(f"  {C.DIM}{from_s}{C.RESET}  {C.CYAN}→{C.RESET}  {C.BCYAN}{to_s}{C.RESET}")


def _ok(msg: str):
    print(f"  {C.BGREEN}✓{C.RESET}  {msg}")


def _warn(msg: str):
    print(f"  {C.BYELLOW}⚠{C.RESET}  {msg}")


def _fail(msg: str):
    print(f"  {C.BRED}✗{C.RESET}  {msg}")


def _info(msg: str):
    print(f"  {C.DIMW}·{C.RESET}  {msg}")


def _llm_indicator(label: str, call_num: int):
    print(f"  {C.MAGENTA}⟡{C.RESET}  {C.DIM}LLM #{call_num}:{C.RESET} {label}", flush=True)


def _panel(title: str, content: str, color: str = C.BCYAN, width: int = 62):
    """Draw a box panel."""
    lines = content.splitlines()
    print(f"\n  {color}╭{'─' * width}╮{C.RESET}")
    print(f"  {color}│{C.RESET} {C.BWHITE}{title:<{width-1}}{color}│{C.RESET}")
    print(f"  {color}├{'─' * width}┤{C.RESET}")
    for line in lines:
        truncated = line[:width - 2] if len(line) > width - 2 else line
        padding = width - 1 - len(truncated)
        print(f"  {color}│{C.RESET} {truncated}{' ' * padding}{color}│{C.RESET}")
    print(f"  {color}╰{'─' * width}╯{C.RESET}")


# ── Configuration ────────────────────────────────────────────────────────────

POPULATION_SIZE = 3
MAX_GENERATIONS = 3
FITNESS_TARGET = 99.0
MUTATION_RATE = 0.5
ELITISM = 1
BACKEND = "cuquantum"  # set to "qutip" to disable GPU, or "none" to skip dynamic

DEFAULT_DESIGN_GOAL = textwrap.dedent("""\
    Design a quantum state machine that implements the 3-qubit bit-flip
    error correction code.

    Requirements:
    1. Three qubits in context: one logical data qubit (q0) and two ancillas (q1, q2)
    2. Encoding phase: spread the logical qubit across all three using CNOT gates
       so |0> -> |000> and |1> -> |111>
    3. Error phase: model a single-qubit X (bit-flip) error on one of the three qubits
    4. Syndrome measurement: measure the two parity checks (q0⊕q1 and q1⊕q2)
       using ancilla-based CNOT + measurement — each collapses to a 0 or 1 syndrome bit
    5. Correction phase: based on the 2-bit syndrome (4 branches: no error, error on
       q0, q1, or q2), apply the corrective X gate to the identified qubit
    6. Include all four syndrome collapse branches with probability guards
    7. Mark the final corrected states as [final]

    The machine should have descriptive state names for each phase, proper context
    fields, and verification rules (unitarity, no-cloning at minimum).""")

DESIGN_GOAL = DEFAULT_DESIGN_GOAL  # May be overridden by --goal / --goal-file


# ── Data types ───────────────────────────────────────────────────────────────

@dataclass
class Individual:
    id: str
    source: str
    fitness: float = 0.0
    generation: int = 0
    parents: list[str] = field(default_factory=list)
    is_valid: bool = False
    rationale: str = ""


# ── LLM helpers ──────────────────────────────────────────────────────────────

_provider = None
_call_count = 0
_start_time = 0.0


def _get_provider():
    global _provider
    if _provider is not None:
        return _provider

    config = load_config()
    api_key = (
        config.api_key
        or os.environ.get("ORCA_API_KEY")
        or os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or ""
    )
    if not api_key:
        _fail("No LLM API key found.")
        _info("Set ORCA_API_KEY or add api_key to orca.yaml")
        _info("This demo requires an LLM to generate and evolve quantum machines.")
        sys.exit(1)

    llm_config = LLMProviderConfig(
        api_key=api_key,
        base_url=config.base_url,
        model=config.model,
        max_tokens=config.max_tokens or 16384,
        temperature=config.temperature or 0.7,
    )
    _provider = create_provider(config.provider, llm_config)
    return _provider


def _get_model() -> str:
    return load_config().model


LLM_MAX_RETRIES = 3


async def _llm(system: str, user: str, temperature: float | None = None) -> str:
    config = load_config()
    provider = _get_provider()

    for attempt in range(1, LLM_MAX_RETRIES + 1):
        t0 = time.time()
        try:
            resp = await provider.complete(LLMRequest(
                messages=[
                    LLMMessage(role="system", content=system),
                    LLMMessage(role="user", content=user),
                ],
                model=config.model,
                max_tokens=config.max_tokens or 16384,
                temperature=temperature if temperature is not None else (config.temperature or 0.7),
            ))
            elapsed = time.time() - t0
            print(f"       {C.DIM}↳ {elapsed:.1f}s  ({len(resp.content)} chars){C.RESET}", flush=True)
            return resp.content
        except (TimeoutError, OSError):
            elapsed = time.time() - t0
            if attempt < LLM_MAX_RETRIES:
                wait = 5 * attempt
                _warn(f"LLM timeout after {elapsed:.0f}s — retrying in {wait}s "
                      f"(attempt {attempt}/{LLM_MAX_RETRIES})")
                time.sleep(wait)
            else:
                _fail(f"LLM failed after {LLM_MAX_RETRIES} attempts ({elapsed:.0f}s)")
                raise


def _strip_code_fence(text: str) -> str:
    return (
        text.replace("```q-orca", "")
        .replace("```orca", "")
        .replace("```markdown", "")
        .replace("```md", "")
        .replace("```", "")
        .strip()
    )


def _verify_source(source: str) -> tuple[bool, list[str]]:
    try:
        parsed = parse_q_orca_markdown(source)
        if not parsed.file.machines:
            return False, ["No machine definition found"]
        machine = parsed.file.machines[0]

        skip_dynamic = BACKEND == "none"
        opts = VerifyOptions(
            skip_completeness=True,
            skip_dynamic=skip_dynamic,
            backend=BACKEND if not skip_dynamic else "qutip",
        )

        gpu_before = 0
        if BACKEND == "cuquantum" and not skip_dynamic:
            try:
                import cupy as cp
                pool = cp.get_default_memory_pool()
                gpu_before = pool.total_bytes()
            except ImportError:
                pass

        result = verify(machine, opts)

        if BACKEND == "cuquantum" and not skip_dynamic:
            try:
                import cupy as cp
                cp.cuda.Stream.null.synchronize()
                gpu_after = cp.get_default_memory_pool().total_bytes()
                delta = gpu_after - gpu_before
                if delta > 0:
                    print(f"       {C.DIM}↳ GPU Δmem: +{delta:,} bytes{C.RESET}", flush=True)
            except ImportError:
                pass

        errors = [f"{e.code}: {e.message}" for e in result.errors if e.severity == "error"]
        return result.valid, errors
    except Exception as e:
        return False, [f"Parse error: {e}"]


async def _refine_individual(ind: Individual, max_iters: int = 2) -> Individual:
    """Attempt to fix an invalid individual using Q-Orca's refine_skill."""
    global _call_count
    _call_count += 1
    _llm_indicator(f"refine {ind.id}", _call_count)
    try:
        result = await refine_skill({"source": ind.source}, max_iterations=max_iters)
        if result.get("status") == "success" and result.get("corrected"):
            ind.source = result["corrected"]
            ind.is_valid = True
            iters = result.get("iterations", "?")
            _ok(f"{ind.id}: refined to valid ({iters} iteration(s))")
            return ind
        else:
            _warn(f"{ind.id}: refine could not fix "
                  f"(status={result.get('status', '?')})")
    except Exception as e:
        _warn(f"{ind.id}: refine error: {e}")
    return ind


def _machine_name(source: str) -> str:
    m = re.search(r"#\s*machine\s+(\w+)", source)
    return m.group(1) if m else "Unknown"


def _count_states(source: str) -> int:
    return len(re.findall(r"##\s+state\s+", source))


def _count_transitions(source: str) -> int:
    # Count table rows in transitions section (rough heuristic)
    in_transitions = False
    count = 0
    for line in source.splitlines():
        if re.match(r"##\s+transitions", line):
            in_transitions = True
            continue
        if in_transitions and line.startswith("##"):
            break
        if in_transitions and line.startswith("|") and not line.startswith("|-"):
            count += 1
    return max(count - 1, 0)  # subtract header row


# ── LLM prompts ─────────────────────────────────────────────────────────────

_SYSTEM_GENERATE = f"""\
You are an expert in Q-Orca, a quantum state machine language.
Generate Q-Orca machine definitions in .q.orca.md markdown format.

{Q_ORCA_SYNTAX_REFERENCE}

Key rules:
- State names MUST be safe identifiers (letters, digits, underscores).
  Do NOT use Dirac ket notation (|0>, |psi>) in state names.
- [initial] marks the start state; [final] marks terminal states.
- Gates: H, X, Y, Z, CNOT, CX, CZ, SWAP, T, S, RX, RY, RZ
- Effect syntax: H(qs[0]), CX(qs[0], qs[1]), RZ(0.5, qs[0])
- Include context, events, transitions, actions, and verification rules.

Output ONLY the machine definition wrapped in a code fence."""


_SYSTEM_FITNESS = """\
You are a quantum computing expert evaluating quantum state machine designs.
Score each machine 0-100 against the design goal.  Return valid JSON only.

Scoring rubric:
- 0-20:  Barely a quantum machine; missing fundamental structure
- 20-40: Has basic structure but wrong gate sequence or missing key phases
- 40-60: Correct overall approach but incomplete (missing branches, wrong qubit count)
- 60-80: Mostly correct with minor issues (missing guards, incomplete collapse)
- 80-100: Fully correct, complete, and well-structured

Return exactly: {"score": <int>, "rationale": "<one sentence>"}"""


_SYSTEM_CROSSOVER = f"""\
You are performing genetic crossover on two Q-Orca quantum state machines.
Combine the best structural elements from both parents into a single child.

Strategy:
- Take the stronger gate sequence / state preparation from the higher-fitness parent.
- Take measurement structure from whichever parent has more complete collapse branches.
- Merge context fields, events, and verification rules from both.
- Ensure the child is a valid, self-consistent Q-Orca machine.

{Q_ORCA_SYNTAX_REFERENCE}

Key rules:
- State names MUST be safe identifiers (letters, digits, underscores only).
- The child must have [initial] and [final] states.
- Include verification rules (at minimum: unitarity).

Output ONLY the child machine definition wrapped in a code fence."""


_SYSTEM_MUTATE = f"""\
You are performing a random mutation on a Q-Orca quantum state machine.
Apply exactly ONE small structural change.  Pick one at random:

- Swap a gate type (H <-> X, CNOT <-> CZ, etc.)
- Add or remove an intermediate state and reconnect transitions
- Change a qubit index in an action effect
- Add a missing collapse branch or guard
- Add or remove a verification rule
- Rename a state to something more descriptive

Keep the machine structurally valid.  Do not rewrite from scratch.

{Q_ORCA_SYNTAX_REFERENCE}

Key rules:
- State names MUST be safe identifiers (letters, digits, underscores only).
- Maintain [initial] and [final] markers.

Output ONLY the mutated machine definition wrapped in a code fence."""


# ── Genetic operations ───────────────────────────────────────────────────────

async def generate_individual(goal: str, gen: int, idx: int) -> Individual:
    global _call_count
    _call_count += 1
    _llm_indicator(f"generate individual {idx}", _call_count)
    text = await _llm(
        _SYSTEM_GENERATE,
        f"Generate a Q-Orca machine for the following goal.  "
        f"Be creative — this is individual #{idx} in a diverse population, "
        f"so try a different structural approach than a textbook solution.\n\n"
        f"Goal:\n{goal}",
        temperature=0.9,
    )
    source = _strip_code_fence(text)
    is_valid, errors = _verify_source(source)
    name = _machine_name(source)
    states = _count_states(source)
    transitions = _count_transitions(source)

    tag = f"{C.BGREEN}valid{C.RESET}" if is_valid else f"{C.BRED}invalid{C.RESET}"
    _info(f"g{gen}-{idx}: {C.WHITE}{name}{C.RESET}  "
          f"{states} states  {transitions} transitions  [{tag}]")
    if not is_valid and errors:
        for e in errors[:2]:
            print(f"       {C.DIM}{e[:70]}{C.RESET}")

    ind = Individual(
        id=f"g{gen}-{idx}", source=source, generation=gen,
        is_valid=is_valid,
    )

    # Attempt to refine invalid individuals before giving up
    if not ind.is_valid:
        ind = await _refine_individual(ind)

    return ind


async def evaluate_individual(ind: Individual, goal: str) -> Individual:
    global _call_count
    _call_count += 1
    _llm_indicator(f"evaluate {ind.id}", _call_count)
    prompt = (
        f"Design goal:\n{goal}\n\n"
        f"Machine (id={ind.id}, valid={ind.is_valid}):\n```\n{ind.source}\n```\n\n"
        f"Score this machine 0-100.  Return JSON only."
    )
    raw = await _llm(_SYSTEM_FITNESS, prompt, temperature=0.2)
    cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        data = json.loads(cleaned)
        ind.fitness = float(data.get("score", 0))
        ind.rationale = data.get("rationale", "")
    except (json.JSONDecodeError, TypeError, ValueError):
        m = re.search(r'"score"\s*:\s*(\d+)', raw)
        ind.fitness = float(m.group(1)) if m else 0.0
        ind.rationale = "Could not parse LLM response"

    if not ind.is_valid:
        ind.fitness = min(ind.fitness, 30.0)

    return ind


async def crossover(parent_a: Individual, parent_b: Individual, gen: int, idx: int) -> Individual:
    global _call_count
    _call_count += 1
    _llm_indicator(f"crossover {parent_a.id} × {parent_b.id}", _call_count)
    prompt = (
        f"Parent A (fitness={parent_a.fitness:.0f}):\n```\n{parent_a.source}\n```\n\n"
        f"Parent B (fitness={parent_b.fitness:.0f}):\n```\n{parent_b.source}\n```\n\n"
        f"Design goal:\n{DESIGN_GOAL}\n\n"
        f"Create a child that combines the best elements of both parents."
    )
    text = await _llm(_SYSTEM_CROSSOVER, prompt, temperature=0.6)
    source = _strip_code_fence(text)
    is_valid, errors = _verify_source(source)
    name = _machine_name(source)
    tag = f"{C.BGREEN}valid{C.RESET}" if is_valid else f"{C.BRED}invalid{C.RESET}"
    _info(f"child g{gen}-{idx}: {C.WHITE}{name}{C.RESET}  [{tag}]")
    ind = Individual(
        id=f"g{gen}-{idx}", source=source, generation=gen,
        parents=[parent_a.id, parent_b.id], is_valid=is_valid,
    )
    if not ind.is_valid:
        ind = await _refine_individual(ind)
    return ind


async def mutate(parent: Individual, gen: int, idx: int) -> Individual:
    global _call_count
    _call_count += 1
    _llm_indicator(f"mutate {parent.id}", _call_count)
    prompt = (
        f"Machine to mutate (fitness={parent.fitness:.0f}):\n```\n{parent.source}\n```\n\n"
        f"Design goal:\n{DESIGN_GOAL}\n\n"
        f"Apply one small mutation that might improve fitness."
    )
    text = await _llm(_SYSTEM_MUTATE, prompt, temperature=0.8)
    source = _strip_code_fence(text)
    is_valid, errors = _verify_source(source)
    name = _machine_name(source)
    tag = f"{C.BGREEN}valid{C.RESET}" if is_valid else f"{C.BRED}invalid{C.RESET}"
    _info(f"mutant g{gen}-{idx}: {C.WHITE}{name}{C.RESET}  [{tag}]")
    ind = Individual(
        id=f"g{gen}-{idx}", source=source, generation=gen,
        parents=[parent.id], is_valid=is_valid,
    )
    if not ind.is_valid:
        ind = await _refine_individual(ind)
    return ind


def tournament_select(population: list[Individual], k: int = 2) -> Individual:
    contestants = random.sample(population, min(k, len(population)))
    return max(contestants, key=lambda ind: ind.fitness)


# ── Workspace ────────────────────────────────────────────────────────────────

@dataclass
class EvolutionState:
    population: list[Individual] = field(default_factory=list)
    selected_parents: list[Individual] = field(default_factory=list)
    all_generations: list[list[Individual]] = field(default_factory=list)
    best_ever: Individual | None = None


evo = EvolutionState()


# ── Action handlers ──────────────────────────────────────────────────────────

def _print_population(pop: list[Individual], gen: int):
    sorted_pop = sorted(pop, key=lambda i: -i.fitness)
    print()
    print(f"  {C.DIMW}{'ID':<8} {'Fitness':>9}  {'':>22} {'V':>1}  "
          f"{'Parents':<16} Rationale{C.RESET}")
    print(f"  {C.DIM}{'─' * 8} {'─' * 9}  {'─' * 22} {'─'}  "
          f"{'─' * 16} {'─' * 25}{C.RESET}")
    for ind in sorted_pop:
        v = f"{C.BGREEN}✓{C.RESET}" if ind.is_valid else f"{C.BRED}✗{C.RESET}"
        parents = ", ".join(ind.parents) if ind.parents else f"{C.DIM}seed{C.RESET}"
        bar = _bar(ind.fitness)
        rat = (ind.rationale[:28] + "..") if len(ind.rationale) > 28 else ind.rationale
        print(f"  {C.WHITE}{ind.id:<8}{C.RESET} {ind.fitness:>6.1f}/100  "
              f"{bar} {v}  {parents:<16} {C.DIM}{rat}{C.RESET}")


def _normalize_source(source: str) -> str:
    """Normalize whitespace for duplicate detection."""
    return re.sub(r"\s+", " ", source.strip()).lower()


async def _init_population(ctx, payload=None):
    goal = (payload or {}).get("goal", DESIGN_GOAL)
    max_attempts = POPULATION_SIZE * 4  # hard cap to avoid infinite loops

    _header("Seeding initial population", "🧬")
    _info(f"Generating {POPULATION_SIZE} valid, unique quantum machines via LLM...")
    print()

    evo.population = []
    seen: set[str] = set()
    attempt = 0

    while len(evo.population) < POPULATION_SIZE and attempt < max_attempts:
        ind = await generate_individual(goal, gen=0, idx=attempt)
        attempt += 1

        if not ind.is_valid:
            _warn(f"{ind.id}: invalid — retrying ({len(evo.population)}/{POPULATION_SIZE} accepted)")
            continue

        norm = _normalize_source(ind.source)
        if norm in seen:
            _warn(f"{ind.id}: duplicate — retrying ({len(evo.population)}/{POPULATION_SIZE} accepted)")
            continue

        seen.add(norm)
        # Re-label with sequential accepted index
        ind.id = f"g0-{len(evo.population)}"
        evo.population.append(ind)
        _ok(f"{ind.id}: accepted ({len(evo.population)}/{POPULATION_SIZE})")

    evo.all_generations.append(list(evo.population))

    if len(evo.population) < POPULATION_SIZE:
        _warn(f"Only {len(evo.population)}/{POPULATION_SIZE} valid individuals "
              f"after {attempt} attempts — proceeding anyway")
    else:
        print()
        _ok(f"Population seeded: {len(evo.population)} valid, unique individuals "
            f"({attempt} attempts)")

    return {"population_size": len(evo.population), "generation": 0, "status": "initialized"}


async def _evaluate_fitness(ctx, payload=None):
    gen = ctx.get("generation", 0)
    _header(f"Fitness evaluation  ·  Generation {gen}", "📊")
    # Skip re-evaluation for elite carry-overs (already scored)
    to_eval = [ind for ind in evo.population if ind.fitness == 0.0]
    skipped = len(evo.population) - len(to_eval)
    if skipped:
        _info(f"LLM scoring {len(to_eval)} individuals "
              f"({skipped} elite carry-over(s) keep prior score)...")
    else:
        _info(f"LLM scoring {len(evo.population)} individuals against design goal...")
    print()

    # Run sequentially — blocking LLM provider can't parallelize
    for j, ind in enumerate(evo.population):
        if ind.fitness > 0.0:
            continue  # elite carry-over, already scored
        evo.population[j] = await evaluate_individual(ind, DESIGN_GOAL)

    best = max(evo.population, key=lambda i: i.fitness)
    if evo.best_ever is None or best.fitness > evo.best_ever.fitness:
        evo.best_ever = best

    _print_population(evo.population, gen)
    print()

    best_color = C.BGREEN if best.fitness >= FITNESS_TARGET else C.BYELLOW
    _info(f"Best this gen:  {best_color}{best.id}  "
          f"fitness={best.fitness:.1f}{C.RESET}")
    _info(f"Best overall:   {C.BWHITE}{evo.best_ever.id}  "
          f"fitness={evo.best_ever.fitness:.1f}{C.RESET}")

    return {"best_fitness": evo.best_ever.fitness, "status": "evaluated"}


def _select_parents(ctx, payload=None):
    _header("Tournament selection", "🎯")

    parent_a = tournament_select(evo.population)
    remaining = [ind for ind in evo.population if ind.id != parent_a.id]
    parent_b = tournament_select(remaining) if remaining else parent_a
    evo.selected_parents = [parent_a, parent_b]

    _ok(f"Parent A: {C.BBLUE}{parent_a.id}{C.RESET}  "
        f"fitness={parent_a.fitness:.1f}")
    _ok(f"Parent B: {C.BMAGENTA}{parent_b.id}{C.RESET}  "
        f"fitness={parent_b.fitness:.1f}")

    return {"status": "selected"}


async def _breed_next_gen(ctx, payload=None):
    gen = ctx.get("generation", 0) + 1
    parent_a, parent_b = evo.selected_parents
    max_attempts = POPULATION_SIZE * 4

    _header(f"Breeding generation {gen}", "🧪")

    # Elitism — carry over the best individual unchanged
    elite = max(evo.population, key=lambda i: i.fitness)
    elite_copy = Individual(
        id=f"g{gen}-0", source=elite.source, fitness=elite.fitness,
        generation=gen, parents=[elite.id], is_valid=elite.is_valid,
        rationale=f"Elite carry-over from {elite.id}",
    )
    _ok(f"Elite: {C.WHITE}{elite.id}{C.RESET}  →  "
        f"{C.BWHITE}{elite_copy.id}{C.RESET}  "
        f"(fitness={elite.fitness:.1f}, carried unchanged)")

    children: list[Individual] = [elite_copy]
    seen: set[str] = {_normalize_source(elite.source)}
    attempt = 0


    print()
    while len(children) < POPULATION_SIZE and attempt < max_attempts:
        attempt += 1
        child_idx = len(children)

        # Alternate crossover and mutation
        if random.random() > MUTATION_RATE:
            print(f"  {C.BBLUE}⤨{C.RESET}  {C.WHITE}Crossover:{C.RESET} "
                  f"{C.BBLUE}{parent_a.id}{C.RESET} × "
                  f"{C.BMAGENTA}{parent_b.id}{C.RESET}")
            child = await crossover(parent_a, parent_b, gen, child_idx)
        else:
            parent = random.choice([parent_a, parent_b])
            print(f"  {C.BYELLOW}⚡{C.RESET} {C.WHITE}Mutation:{C.RESET}  "
                  f"{C.WHITE}{parent.id}{C.RESET}")
            child = await mutate(parent, gen, child_idx)

        if not child.is_valid:
            _warn(f"{child.id}: invalid — retrying "
                  f"({len(children)}/{POPULATION_SIZE} accepted)")
            print()
            continue

        norm = _normalize_source(child.source)
        if norm in seen:
            _warn(f"{child.id}: duplicate — retrying "
                  f"({len(children)}/{POPULATION_SIZE} accepted)")
            print()
            continue

        seen.add(norm)
        child.id = f"g{gen}-{len(children)}"
        children.append(child)
        _ok(f"{child.id}: accepted ({len(children)}/{POPULATION_SIZE})")
        print()

    # If we still need more individuals and at least one breed worked,
    # fill remaining slots with copies of valid parents (diverse by fitness rank)
    if len(children) < POPULATION_SIZE:
        valid_pool = sorted(
            [ind for ind in evo.population if ind.is_valid],
            key=lambda i: -i.fitness,
        )
        fill_idx = 0
        while len(children) < POPULATION_SIZE and valid_pool:
            donor = valid_pool[fill_idx % len(valid_pool)]
            norm = _normalize_source(donor.source)
            if norm not in seen:
                seen.add(norm)
                copy = Individual(
                    id=f"g{gen}-{len(children)}", source=donor.source,
                    generation=gen, parents=[donor.id], is_valid=True,
                    rationale=f"Cloned from {donor.id} (fill)",
                )
                children.append(copy)
                _warn(f"{copy.id}: cloned from {donor.id} to fill population")
            fill_idx += 1
            if fill_idx >= len(valid_pool) * 2:
                break  # avoid infinite loop if all are duplicates

    evo.population = children
    evo.all_generations.append(list(children))

    valid = sum(1 for c in children if c.is_valid)
    _ok(f"Generation {gen} bred: {valid}/{len(children)} valid "
        f"({attempt} attempts)")

    return {"generation": gen, "status": "bred"}


def _report_best(ctx, payload=None):
    best = evo.best_ever
    if not best:
        _fail("No individuals found.")
        return {"status": "reported"}

    # Build summary
    lines = [
        f"Individual:  {best.id}",
        f"Fitness:     {best.fitness:.1f} / 100",
        f"Valid:       {'Yes' if best.is_valid else 'No'}",
        f"Generation:  {best.generation}",
        "",
    ]

    # Word-wrap rationale
    if best.rationale:
        wrapped = textwrap.wrap(best.rationale, width=58)
        lines.append("Rationale:")
        for w in wrapped:
            lines.append(f"  {w}")

    color = C.BGREEN if best.fitness >= FITNESS_TARGET else C.BYELLOW
    _panel("Best Individual", "\n".join(lines), color=color)

    # Compile
    try:
        parsed = parse_q_orca_markdown(best.source)
        if parsed.file.machines:
            machine = parsed.file.machines[0]
            mermaid = compile_to_mermaid(machine)
            qasm = compile_to_qasm(machine)

            print(f"\n  {C.BCYAN}── Best Machine Source ──{C.RESET}")
            for line in best.source.strip().splitlines()[:40]:
                print(f"  {C.DIM}│{C.RESET} {line}")
            total = len(best.source.strip().splitlines())
            if total > 40:
                print(f"  {C.DIM}│ ... ({total - 40} more lines){C.RESET}")

            print(f"\n  {C.BCYAN}── Mermaid State Diagram ──{C.RESET}")
            for line in mermaid.strip().splitlines():
                print(f"  {C.DIM}│{C.RESET} {line}")

            print(f"\n  {C.BCYAN}── OpenQASM 3.0 ──{C.RESET}")
            for line in qasm.strip().splitlines():
                print(f"  {C.DIM}│{C.RESET} {line}")
    except Exception as e:
        _fail(f"Compile error: {e}")

    return {"status": "reported"}


# ── Main ─────────────────────────────────────────────────────────────────────

async def main():
    global _start_time
    _start_time = time.time()

    print(f"""
{C.BCYAN}╔══════════════════════════════════════════════════════════════════╗
║{C.RESET}  {C.BWHITE}🧬  QUANTUM EVOLVE{C.RESET}                                             {C.BCYAN}║
║{C.RESET}  {C.DIM}Genetic Algorithm over Q-Orca Quantum State Machines{C.RESET}          {C.BCYAN}║
║{C.RESET}                                                                {C.BCYAN}║
║{C.RESET}  {C.DIM}Outer loop:{C.RESET}  Classical Orca GA controller (orca-runtime-python) {C.BCYAN}║
║{C.RESET}  {C.DIM}Population:{C.RESET}  Q-Orca quantum state machines (q-orca)            {C.BCYAN}║
║{C.RESET}  {C.DIM}Evolution:{C.RESET}   LLM-assisted fitness, crossover, and mutation     {C.BCYAN}║
╚══════════════════════════════════════════════════════════════════╝{C.RESET}
""")

    # Check LLM
    _get_provider()
    config = load_config()
    _info(f"LLM provider:    {C.WHITE}{config.provider} / {config.model}{C.RESET}")
    _info(f"Verify backend:  {C.WHITE}{BACKEND}{C.RESET}")
    _info(f"Population:      {C.WHITE}{POPULATION_SIZE}{C.RESET}   "
          f"Max generations: {C.WHITE}{MAX_GENERATIONS}{C.RESET}")
    _info(f"Fitness target:  {C.WHITE}{FITNESS_TARGET}{C.RESET}")
    _info(f"Design goal:     {C.ITALIC}{DESIGN_GOAL.splitlines()[0]}{C.RESET}")

    # ── Phase 1 ──────────────────────────────────────────────────────────
    _phase(1, "Load classical GA controller", "🔧")

    controller_path = Path(__file__).parent / "evolve.orca.md"
    controller_def = parse_orca_md(controller_path.read_text())

    _ok(f"Machine: {C.WHITE}{controller_def.name}{C.RESET}")
    _info(f"States:      {[s.name for s in controller_def.states]}")
    _info(f"Transitions: {len(controller_def.transitions)}")

    # ── Phase 2 ──────────────────────────────────────────────────────────
    _phase(2, "Start controller + register genetic operators", "⚙️")

    bus = get_event_bus()

    async def on_transition(event: Event):
        p = event.payload
        _transition(p.get("from", "?"), p.get("to", "?"))

    bus.subscribe(EventType.TRANSITION_COMPLETED, on_transition)

    controller = OrcaMachine(
        definition=controller_def,
        context={
            "generation": 0,
            "max_generations": MAX_GENERATIONS,
            "best_fitness": 0.0,
            "fitness_target": FITNESS_TARGET,
            "population_size": 0,
            "status": "idle",
        },
    )

    controller.register_action("init_population", _init_population)
    controller.register_action("evaluate_fitness", _evaluate_fitness)
    controller.register_action("select_parents", _select_parents)
    controller.register_action("breed_next_gen", _breed_next_gen)
    controller.register_action("report_best", _report_best)

    await controller.start()
    _ok(f"Controller ready  ·  state: {C.BCYAN}{controller.state}{C.RESET}")

    # ── Phase 3 ──────────────────────────────────────────────────────────
    _phase(3, "Evolution", "🧬")

    await controller.send("START", {"goal": DESIGN_GOAL})
    await controller.send("POPULATION_READY")

    for _ in range(MAX_GENERATIONS + 1):
        leaf = controller.state.leaf()
        if leaf in ("converged", "exhausted"):
            break

        await controller.send("EVALUATION_DONE")
        leaf = controller.state.leaf()
        if leaf in ("converged", "exhausted"):
            break

        if leaf == "selecting":
            await controller.send("SELECTION_DONE")
        if controller.state.leaf() == "breeding":
            await controller.send("BREEDING_DONE")

    # ── Summary ──────────────────────────────────────────────────────────
    await controller.stop()
    elapsed = time.time() - _start_time

    ctx = controller.context
    final_state = controller.state.leaf()
    is_success = final_state == "converged"

    color = C.BGREEN if is_success else C.BYELLOW
    icon = "✅" if is_success else "⏱️"

    summary_lines = [
        f"Final state:    {final_state}",
        f"Generations:    {ctx.get('generation', 0)}",
        f"Best fitness:   {ctx.get('best_fitness', 0):.1f} / 100",
        f"LLM calls:      {_call_count}",
        f"Elapsed:        {elapsed:.1f}s",
        "",
        "Fitness progression:",
    ]
    for gi, gen_pop in enumerate(evo.all_generations):
        scored = [ind for ind in gen_pop if ind.fitness > 0]
        if scored:
            best_f = max(ind.fitness for ind in scored)
            avg_f = sum(ind.fitness for ind in scored) / len(scored)
            valid = sum(1 for i in gen_pop if i.is_valid)
            summary_lines.append(
                f"  Gen {gi}:  best={best_f:5.1f}  avg={avg_f:5.1f}  "
                f"valid={valid}/{len(gen_pop)}"
            )

    _panel(f"{icon}  Evolution {'Converged' if is_success else 'Exhausted'}",
           "\n".join(summary_lines), color=color)
    print()


def _parse_args():
    parser = argparse.ArgumentParser(
        description="Quantum Evolve — genetic algorithm over Q-Orca machines",
    )
    parser.add_argument(
        "--goal", type=str, default=None,
        help="Design goal prompt (inline text)",
    )
    parser.add_argument(
        "--goal-file", type=str, default=None,
        help="Read design goal from a text file",
    )
    parser.add_argument(
        "--population", type=int, default=None,
        help=f"Population size (default: {POPULATION_SIZE})",
    )
    parser.add_argument(
        "--generations", type=int, default=None,
        help=f"Max generations (default: {MAX_GENERATIONS})",
    )
    parser.add_argument(
        "--fitness-target", type=float, default=None,
        help=f"Fitness target to converge (default: {FITNESS_TARGET})",
    )
    parser.add_argument(
        "--backend", type=str, default=None,
        help="Verification backend: cuquantum (GPU), qutip (CPU), none (skip dynamic). "
             f"Default: {BACKEND}",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    if args.goal:
        DESIGN_GOAL = args.goal  # noqa: F841 — module-level reassignment
    elif args.goal_file:
        DESIGN_GOAL = Path(args.goal_file).read_text().strip()

    if args.population is not None:
        POPULATION_SIZE = args.population
    if args.generations is not None:
        MAX_GENERATIONS = args.generations
    if args.fitness_target is not None:
        FITNESS_TARGET = args.fitness_target
    if args.backend is not None:
        BACKEND = args.backend

    asyncio.run(main())
