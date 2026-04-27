"""Q-Orca — Quantum Orchestrated State Machine Language"""

from q_orca.parser.markdown_parser import parse_q_orca_markdown
from q_orca.verifier import verify, VerifyOptions
from q_orca.compiler.mermaid import compile_to_mermaid
from q_orca.compiler.qasm import compile_to_qasm
from q_orca.compiler.qiskit import compile_to_qiskit, QSimulationOptions
from q_orca.compiler.resources import (
    estimate_resources,
    compile_with_resources,
    format_resource_report,
)
from q_orca.compiler.concept_gram import (
    compute_concept_gram,
    ConceptGramConfigurationError,
)
from q_orca.skills import (
    parse_skill,
    verify_skill,
    compile_skill,
    generate_skill,
    refine_skill,
)
from q_orca.config import load_config, QOrcaConfig
from q_orca.llm import create_provider, LLMProvider

__version__ = "0.6.0"

__all__ = [
    # Parser
    "parse_q_orca_markdown",
    # Verifier
    "verify",
    "VerifyOptions",
    # Compilers
    "compile_to_mermaid",
    "compile_to_qasm",
    "compile_to_qiskit",
    "QSimulationOptions",
    "estimate_resources",
    "compile_with_resources",
    "format_resource_report",
    # Concept-gram analysis (optional, for polysemantic examples)
    "compute_concept_gram",
    "ConceptGramConfigurationError",
    # Skills
    "parse_skill",
    "verify_skill",
    "compile_skill",
    "generate_skill",
    "refine_skill",
    "generate_actions_skill",
    # Config
    "load_config",
    "QOrcaConfig",
    # LLM
    "create_provider",
    "LLMProvider",
]
