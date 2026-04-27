"""
LLM-driven quantum circuit evolution demo for Q-Orca.

Demonstrates using an LLM (Claude or GPT-4) to iteratively refine a Q-Orca
machine definition — starting from a seed circuit, proposing parameter changes,
and accepting improvements via a VQE-style energy criterion.

This is a key demo for NVIDIA / Microsoft grant applications: it shows the
intersection of LLM inference and GPU-accelerated quantum simulation.

Usage:
    export ANTHROPIC_API_KEY=sk-...   # or OPENAI_API_KEY
    python benchmarks/llm_evolution.py --algorithm qaoa --qubits 8 --rounds 5

Output:
    - Per-round energy trace (printed + JSON)
    - Final best Q-Orca machine definition (Markdown)
"""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path


# ── Seed machine templates ────────────────────────────────────────────────

QAOA_SEED = """\
# machine QAOAMaxCut_{n}q

## context
| Field  | Type        | Default                          |
|--------|-------------|----------------------------------|
| qubits | list<qubit> | [{qubit_list}]                   |
| gamma  | float       | 0.5                              |
| beta   | float       | 0.25                             |
| depth  | int         | 1                                |

## events
- init
- apply_cost
- apply_mixer
- readout

## state |0...0> [initial]
> All qubits in |0⟩ — ground state

## state |+...+>
> Equal superposition after Hadamard layer

## state |cost_applied>
> After QAOA cost unitary (RZZ on all edges)

## state |mixed>
> After mixer unitary (Rx on each qubit)

## state |measured> [final]
> Measurement outcome encodes MaxCut bitstring

## transitions
| Source          | Event        | Guard | Target          | Action          |
|-----------------|--------------|-------|-----------------|-----------------|
| |0...0>         | init         |       | |+...+>         | hadamard_layer  |
| |+...+>         | apply_cost   |       | |cost_applied>  | cost_unitary    |
| |cost_applied>  | apply_mixer  |       | |mixed>         | mixer_unitary   |
| |mixed>         | readout      |       | |measured>      |                 |

## verification rules
- unitarity: all gates preserve norm
"""


def seed_machine(n_qubits: int) -> str:
    return QAOA_SEED.format(
        n=n_qubits,
        qubit_list=", ".join(f"q{i}" for i in range(n_qubits)),
    )


# ── LLM client (minimal, no heavy deps) ──────────────────────────────────

def call_llm(prompt: str) -> str:
    """Call Claude or GPT-4 to suggest parameter improvements."""
    api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        # Demo mode: return a canned mutation
        import random
        gamma = round(random.uniform(0.1, 1.5), 3)
        beta = round(random.uniform(0.1, 1.0), 3)
        return json.dumps({"gamma": gamma, "beta": beta, "rationale": "random search (no API key)"})

    if os.environ.get("ANTHROPIC_API_KEY"):
        return _call_claude(prompt, api_key)
    return _call_openai(prompt, api_key)


def _call_claude(prompt: str, api_key: str) -> str:
    import urllib.request

    body = json.dumps({
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 256,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    return data["content"][0]["text"]


def _call_openai(prompt: str, api_key: str) -> str:
    import urllib.request

    body = json.dumps({
        "model": "gpt-4o-mini",
        "max_tokens": 256,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()

    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    return data["choices"][0]["message"]["content"]


# ── Energy evaluator ──────────────────────────────────────────────────────

def evaluate_energy(n_qubits: int, gamma: float, beta: float) -> float:
    """Compute QAOA expectation value for MaxCut on a ring graph.

    Raises ImportError if qiskit/qiskit-aer aren't installed — install with
    `pip install -e .[quantum]` to run real evolution.
    """
    from qiskit import QuantumCircuit, transpile
    from qiskit_aer import AerSimulator

    qc = QuantumCircuit(n_qubits)
    for i in range(n_qubits):
        qc.h(i)
    edges = [(i, (i + 1) % n_qubits) for i in range(n_qubits)]
    for u, v in edges:
        qc.rzz(2 * gamma, u, v)
    for i in range(n_qubits):
        qc.rx(2 * beta, i)
    qc.measure_all()

    sim = AerSimulator()
    t_qc = transpile(qc, sim)
    result = sim.run(t_qc, shots=2048).result()
    counts = result.get_counts()

    # MaxCut energy = fraction of edges cut, averaged over shots
    total_shots = sum(counts.values())
    total_cut = 0
    for bitstring, count in counts.items():
        bits = [int(b) for b in bitstring.replace(" ", "")]
        cut = sum(bits[u] != bits[v] for u, v in edges)
        total_cut += cut * count
    return total_cut / total_shots


# ── LLM response parser ───────────────────────────────────────────────────

def _extract_json_object(raw: str) -> dict | None:
    """Pull the first flat {...} object out of an LLM response.

    LLMs frequently wrap JSON in ```json ... ``` fences or add preamble text;
    json.loads on the raw response is almost guaranteed to fail. This pulls
    the first balanced flat JSON object out and tolerates surrounding noise.
    """
    cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", raw)
    match = re.search(r"\{[^{}]*\}", cleaned, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return None


# ── Evolution loop ────────────────────────────────────────────────────────

def evolve(n_qubits: int, rounds: int, output_dir: Path) -> None:
    print(f"\nLLM-driven QAOA evolution  |  {n_qubits} qubits  |  {rounds} rounds")
    print("=" * 60)

    best_gamma, best_beta = 0.5, 0.25
    best_energy = evaluate_energy(n_qubits, best_gamma, best_beta)
    history = [{"round": 0, "gamma": best_gamma, "beta": best_beta,
                "energy": round(best_energy, 4), "accepted": True, "rationale": "seed"}]

    print(f"  Round 0 (seed): γ={best_gamma} β={best_beta}  E={best_energy:.4f}")

    for round_idx in range(1, rounds + 1):
        prompt = (
            f"You are tuning a QAOA MaxCut circuit on a {n_qubits}-qubit ring graph.\n"
            f"Current best: gamma={best_gamma}, beta={best_beta}, energy={best_energy:.4f}\n"
            f"Suggest new values of gamma (0.1–2.0) and beta (0.1–1.5) to increase MaxCut energy.\n"
            f"Output ONE JSON object on a single line, no markdown fences, no preamble:\n"
            f'{{"gamma": <float>, "beta": <float>, "rationale": "<short string>"}}'
        )

        raw = call_llm(prompt)
        suggestion = _extract_json_object(raw)
        if suggestion is None:
            print(f"  Round {round_idx}: LLM parse failure — raw: {raw[:120]!r}")
            continue
        try:
            new_gamma = float(suggestion["gamma"])
            new_beta  = float(suggestion["beta"])
            rationale = str(suggestion.get("rationale", ""))
        except (KeyError, TypeError, ValueError) as exc:
            print(f"  Round {round_idx}: invalid suggestion {suggestion!r} ({exc})")
            continue

        new_energy = evaluate_energy(n_qubits, new_gamma, new_beta)
        accepted = new_energy > best_energy
        if accepted:
            best_gamma, best_beta, best_energy = new_gamma, new_beta, new_energy

        status = "✓ accepted" if accepted else "✗ rejected"
        print(f"  Round {round_idx}: γ={new_gamma} β={new_beta}  E={new_energy:.4f}  {status}")
        print(f"           [{rationale[:80]}]")

        history.append({
            "round": round_idx,
            "gamma": new_gamma, "beta": new_beta,
            "energy": round(new_energy, 4),
            "accepted": accepted,
            "rationale": rationale,
        })

    print(f"\nBest result: γ={best_gamma} β={best_beta}  E={best_energy:.4f}")

    # Write outputs
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_out = output_dir / f"llm_evolution_{n_qubits}q_{ts}.json"
    md_out   = output_dir / f"llm_evolution_{n_qubits}q_{ts}_best_machine.md"

    json_out.write_text(json.dumps({"history": history, "best": {
        "gamma": best_gamma, "beta": best_beta, "energy": best_energy,
    }}, indent=2))

    best_machine = seed_machine(n_qubits).replace("| gamma  | float       | 0.5    ", f"| gamma  | float       | {best_gamma}")
    best_machine = best_machine.replace("| beta   | float       | 0.25   ", f"| beta   | float       | {best_beta}")
    md_out.write_text(best_machine)

    print(f"\nHistory → {json_out}")
    print(f"Best machine → {md_out}")


# ── CLI ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="LLM-driven Q-Orca circuit evolution demo")
    parser.add_argument("--algorithm", choices=["qaoa"], default="qaoa")
    parser.add_argument("--qubits", type=int, default=8)
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--output-dir", default="benchmarks/reports", type=Path)
    args = parser.parse_args()

    evolve(args.qubits, args.rounds, args.output_dir)


if __name__ == "__main__":
    main()
