# Research Proposal: LARQL → Q-Orca Polysemantic Pipeline

A Hybrid Classical-Quantum Framework for Verifiable Mechanistic Interpretability of LLM Superposition

> Generated: 2026-05-01 — synthesis proposal contributed by Grok and forwarded into the q-orca-lang research tree.

**Principal Investigator / Proposer:** Grok (synthesis lead)
**Collaborators:** jascal/q-orca-lang team, chrishayuk/larql maintainers
**Date:** May 2026
**Target Venue:** Q-Orca repo (OpenSpec ticket + research note) + potential NeurIPS/ICML workshop on Mechanistic Interpretability & Quantum ML

---

## 1. Abstract

We propose a complete end-to-end pipeline that extracts real polysemantic feature dictionaries directly from production LLM weights using LARQL (Lazarus Query Language) and encodes them as verifiable quantum states inside Q-Orca's rung-1 MPS (χ=2) and rung-2 HEA circuits.

LARQL's vindex (vector index + graph DB) + LQL queries surface empirical hierarchical graded-tier structures and Gram matrices from any open-weight model. These are automatically compiled into Q-Orca circuits, verified with the 5-stage pipeline (structural + quantum-specific checks), and made available for hybrid quantum-classical mechanistic-interpretability experiments.

The result: the first mathematically verifiable quantum substrate for studying superposition, entanglement, and hierarchical polysemy at the scale of real frontier models. This closes the loop from "probe-and-pray" classical MI to formally checked quantum feature representations.

## 2. Background & Motivation

- **Polysemanticity & Superposition** (Anthropic 2022 "Toy Models" + 2023–2025 SAE scaling papers) is now understood to be the dominant representational strategy in LLMs. Real SAEs reveal complex graded-tier hierarchies that classical tools struggle to verify at scale.
- **LARQL** (chrishayuk/larql) already solves the upstream problem: it decompiles dense/MoE model weights into a queryable vindex and lets LQL traverse gate vectors, relation clusters, and polysemantic neighborhoods without GPU or fine-tuning.
- **Q-Orca** (jascal/q-orca-lang) provides the downstream quantum substrate: rung-1 MPS (just shipped) already supports exactly the graded two-level hierarchies seen in LARQL extractions; rung-2 HEA will enable arbitrary Gram structures.
- **Gap:** No automated bridge exists yet between real-model feature graphs and verifiable quantum encodings.

This pipeline turns that gap into a reproducible, LLM-native research platform.

## 3. Research Objectives

### Primary

1. Build an automated extraction → compilation pipeline: LARQL vindex + LQL queries → Q-Orca quantum circuit (MPS rung-1 first, HEA rung-2 as stretch goal).
2. Demonstrate faithful encoding of real hierarchical polysemy (e.g., 12–10k concept dictionaries from Llama-3.1-8B or larger) with full verifier guarantees.
3. Enable new MI experiments: quantum interference tests, entanglement-based clustering, and hybrid Orca state-machine interventions on real-model features.

### Secondary

- Quantify scaling: how many real SAE-scale dictionaries (10k–1M features) fit cleanly in 8–32 qubit registers.
- Produce public artifacts: benchmark datasets of "LARQL-derived quantum SAE dictionaries" and reproducible notebooks.

## 4. Proposed Methodology / Pipeline Architecture

### Stage 1: LARQL Extraction (Classical Front-End)

- Run `larql extract --model <hf-id> --output model.vindex`
- Use LQL scripts to:
  - Extract gate-vector neighborhoods (KNN)
  - Build hierarchical relation clusters
  - Compute empirical Gram matrix (cosine similarities)
  - Export JSON + hierarchical tier metadata (super-groups → sub-clusters → features)

### Stage 2: Feature Mapping & Gram Conditioning

- Python glue layer (`q_orca.integrations.larql`) normalizes tiers and Gram into Q-Orca's internal concept dictionary format.
- Optional lightweight classical SAE refinement step for cleaner monosemantic labels (optional but recommended for high-fidelity experiments).

### Stage 3: Quantum Compilation (Q-Orca Back-End)

- `q-orca compile --from-larql model.vindex --ansatz mps-rung1` (or `hea-rung2 --depth L`)
- Generates Dirac-ket circuit + effect strings with cross-coupled angles (rung-1) or full parameterized HEA layers (rung-2).
- Automatic resource estimation and capacity warnings.

### Stage 4: Verification & Hybrid Execution

- Run full 5-stage verifier (structural + Schmidt-rank/entropy checks).
- Export OpenQASM + QuTiP/CUDA-Q simulation scripts + Orca state-machine orchestration for closed-loop experiments.
- Optional: MCP server integration for agentic querying (e.g., "perturb concept X while keeping Y entangled").

### Stage 5: Evaluation

- Compare quantum-encoded Gram vs. original LARQL Gram (overlap fidelity, hierarchical tier preservation).
- Run proof-of-concept MI experiments (e.g., quantum phase cancellation of polysemantic interference).

## 5. Expected Outcomes & Impact

- **Immediate:** Working open-source pipeline + demo notebooks (Llama-3 → quantum-encoded LARQL dictionary).
- **Scientific:** First verifiable quantum representations of real-model polysemy → new class of MI experiments impossible with classical SAEs alone.
- **Community:** Reproducible "quantum SAE dictionary" benchmark suite; integration ticket in both repos; potential for LARQL + Q-Orca joint workshop paper.
- **Longer-term:** Path to 32+ qubit experiments on neutral-atom hardware (Atom Computing / QuEra) for frontier-scale superposition studies.

## 6. Timeline (3–4 months)

- **Month 1:** Glue layer + rung-1 MPS integration; basic LQL → MPS demo.
- **Month 2:** Rung-2 HEA support + verifier extensions; scaling benchmarks (8–16 qubits).
- **Month 3:** Hybrid Orca loop experiments + public release + research note.
- **Month 4 (stretch):** Paper draft + hardware access pilot.

## 7. Resources Needed

- **Compute:** Standard laptop + optional GPU for large-model extraction (LARQL is lightweight).
- **Access:** Public HF models + Q-Orca simulator (no hardware required initially).
- **Team:** 1–2 contributors familiar with LARQL + Q-Orca (or AI-assisted).

## 8. Risks & Mitigations

- LARQL output schema changes → version-pinned integration tests.
- Large Gram matrices exceed classical simulator limits → tensor-network backends (already planned in Q-Orca).
- Fidelity loss in encoding → tolerance-based compiler + verification flags.

## 9. Why This Matters

This pipeline turns two powerful but separate projects into a single, verifiable research engine for the superposition hypothesis that underlies modern LLMs. It moves mechanistic interpretability from statistical observation to formal, quantum-native engineering.

---

## Status & next steps

This document is a **research proposal**, not a queued feature. It has not yet been promoted to an OpenSpec change. Concrete next steps if/when the proposal is adopted:

1. Open an OpenSpec change `add-larql-integration` under `openspec/changes/` with proposal + design + tasks covering Stages 1–3 of §4 (the glue layer + compiler entry point); Stage 4 (verifier extensions) and Stage 5 (evaluation) can split into follow-on changes.
2. Coordinate with the LARQL maintainers on a stable export schema for the vindex → JSON handoff (§4 Stage 1) so the integration tests can pin a contract.
3. Cross-reference with the (pending) `mps-rung-1-validation` change — that change validates the rung-1 substrate's utility on synthetic SAE-pattern data; this proposal validates it on real-model dictionaries. The two are complementary: validation first on synthetic patterns (sweep n=3–8 qubits, controlled angle choices), then on extracted dictionaries.

## Connection to existing work

- **`add-mps-concept-encoding`** (shipped, [PR #46](../../pull/46)) + **`fix-mps-encoding-non-factorizing`** (shipped, [PR #48](../../pull/48)) — provide the rung-1 MPS substrate this proposal targets in §4 Stage 3.
- **`docs/research/polysemantic-encoding-beyond-product-states.md`** — the rung-0 / rung-1 / rung-2 ladder this proposal sits on top of; rung-2 HEA is the §4 stretch goal.
- **`docs/research/concept-encoding-efficiency.md`** — language-extension question A (compile-time MPS verification) becomes load-bearing for the §4 Stage 4 verifier checks at rung-2.
