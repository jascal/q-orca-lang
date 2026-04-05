"""Q-Orca AST type definitions — dataclass equivalents of the TypeScript AST."""

from dataclasses import dataclass, field
from typing import Optional


# ============================================================
# Quantum-Specific Types
# ============================================================


GateKind = str  # 'H' | 'X' | 'Y' | 'Z' | 'CNOT' | 'CZ' | 'SWAP' | 'T' | 'S' | 'Rx' | 'Ry' | 'Rz' | 'CCNOT' | 'CSWAP' | 'custom'


@dataclass
class QuantumGate:
    kind: GateKind
    targets: list[int]
    controls: Optional[list[int]] = None
    parameter: Optional[float] = None
    custom_name: Optional[str] = None


@dataclass
class Measurement:
    qubits: list[int]
    basis: str = "computational"  # 'computational' | 'hadamard' | 'bell'


@dataclass
class CollapseOutcome:
    bitstring: str
    probability: float
    tolerance: Optional[float] = None


# ============================================================
# Core AST Types
# ============================================================


@dataclass
class QType:
    pass


@dataclass
class QTypeQubit(QType):
    kind: str = "qubit"


@dataclass
class QTypeList(QType):
    kind: str = "list"
    element_type: str = ""


@dataclass
class QTypeScalar(QType):
    kind: str = ""  # 'int' | 'float' | 'bool' | 'string' | 'complex' | 'state_vector' | 'density_matrix'


@dataclass
class QTypeOptional(QType):
    kind: str = "optional"
    inner_type: str = ""


@dataclass
class QTypeCustom(QType):
    kind: str = "custom"
    name: str = ""


@dataclass
class NoiseModel:
    """Quantum noise model specification."""
    kind: str = ""  # 'depolarizing' | 'amplitude_damping' | 'phase_damping' | 'thermal'
    parameter: float = 0.0  # noise probability or damping rate
    parameter2: float = 0.01  # secondary parameter (e.g., thermal excitation probability)
    qubits: list[int] = field(default_factory=list)  # target qubits (empty = all)


@dataclass
class ContextField:
    name: str
    type: QType
    default_value: Optional[str] = None


@dataclass
class EventDef:
    name: str
    payload: Optional[list[ContextField]] = None


@dataclass
class QStateDef:
    name: str  # raw ket notation, e.g. "|00>"
    display_name: str  # cleaned identifier, e.g. "ket_00"
    description: Optional[str] = None
    state_expression: Optional[str] = None  # e.g. "(|00> + |11>)/√2"
    is_initial: bool = False
    is_final: bool = False
    on_entry: Optional[str] = None
    on_exit: Optional[str] = None


@dataclass
class QGuardRef:
    name: str
    negated: bool = False


@dataclass
class QGuardDef:
    name: str
    expression: "QGuardExpression"


# Guard expression discriminated union
@dataclass
class QGuardTrue:
    kind: str = "true"


@dataclass
class QGuardFalse:
    kind: str = "false"


@dataclass
class QGuardNot:
    kind: str = "not"
    expr: "QGuardExpression" = None


@dataclass
class QGuardAnd:
    kind: str = "and"
    left: "QGuardExpression" = None
    right: "QGuardExpression" = None


@dataclass
class QGuardOr:
    kind: str = "or"
    left: "QGuardExpression" = None
    right: "QGuardExpression" = None


@dataclass
class QGuardCompare:
    kind: str = "compare"
    op: str = "eq"  # 'eq' | 'ne' | 'lt' | 'gt' | 'le' | 'ge' | 'approx'
    left: "VariableRef" = None
    right: "ValueRef" = None


@dataclass
class QGuardProbability:
    kind: str = "probability"
    outcome: CollapseOutcome = None


@dataclass
class QGuardFidelity:
    kind: str = "fidelity"
    state_a: str = ""
    state_b: str = ""
    op: str = "eq"
    value: float = 0.0


QGuardExpression = (
    QGuardTrue | QGuardFalse | QGuardNot | QGuardAnd | QGuardOr |
    QGuardCompare | QGuardProbability | QGuardFidelity
)


ComparisonOp = str  # 'eq' | 'ne' | 'lt' | 'gt' | 'le' | 'ge' | 'approx'


@dataclass
class VariableRef:
    kind: str = "variable"
    path: list[str] = field(default_factory=list)


@dataclass
class ValueRef:
    kind: str = "value"
    type: str = "string"  # 'string' | 'number' | 'boolean' | 'null'
    value: any = None


@dataclass
class QActionSignature:
    name: str
    parameters: list[str] = field(default_factory=list)
    return_type: str = "void"
    effect: Optional[str] = None
    has_effect: bool = False
    effect_type: Optional[str] = None
    gate: Optional[QuantumGate] = None
    measurement: Optional[Measurement] = None


@dataclass
class QEffectDef:
    name: str
    input: str
    output: str


@dataclass
class VerificationRule:
    kind: str  # 'unitarity' | 'entanglement' | 'completeness' | 'no_cloning' | 'custom'
    description: str
    target: Optional[str] = None
    custom_name: Optional[str] = None


@dataclass
class QTransition:
    source: str
    event: str
    target: str
    guard: Optional[QGuardRef] = None
    action: Optional[str] = None


@dataclass
class QMachineDef:
    name: str
    context: list[ContextField] = field(default_factory=list)
    events: list[EventDef] = field(default_factory=list)
    states: list[QStateDef] = field(default_factory=list)
    transitions: list[QTransition] = field(default_factory=list)
    guards: list[QGuardDef] = field(default_factory=list)
    actions: list[QActionSignature] = field(default_factory=list)
    effects: list[QEffectDef] = field(default_factory=list)
    verification_rules: list[VerificationRule] = field(default_factory=list)


@dataclass
class QOrcaFile:
    machines: list[QMachineDef] = field(default_factory=list)


@dataclass
class QParseResult:
    file: QOrcaFile
