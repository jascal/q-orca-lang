"""Q-Orca AST type definitions — dataclass equivalents of the TypeScript AST."""

from dataclasses import dataclass, field
from typing import Literal, Optional


# ============================================================
# Quantum-Specific Types
# ============================================================


GateKind = str  # 'H' | 'X' | 'Y' | 'Z' | 'CNOT' | 'CZ' | 'SWAP' | 'T' | 'S' | 'Rx' | 'Ry' | 'Rz' | 'CCNOT' | 'CSWAP' | 'CRx' | 'CRy' | 'CRz' | 'RXX' | 'RYY' | 'RZZ' | 'custom'


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
    """Legacy flat noise model (deprecated `noise:` context-field alias).

    Retained as the intermediate the deprecated context-field path parses into;
    `add-noise-model-section` wraps it in a single-row `NoiseModelSection`. New
    code uses `NoiseChannel` / `NoiseModelSection`.
    """
    kind: str = ""  # 'depolarizing' | 'amplitude_damping' | 'phase_damping' | 'thermal'
    parameter: float = 0.0  # noise probability / damping rate / T1 relaxation time (ns)
    parameter2: float = 0.0  # T2 relaxation time (ns); 0.0 means default to T1
    qubits: list[int] = field(default_factory=list)  # target qubits (empty = all)


# --- Declarative `## noise_model` section (add-noise-model-section) ----------

# Closed target-selector kinds.
NOISE_TARGET_KINDS = frozenset({
    "all_gates", "single_qubit_gates", "two_qubit_gates", "all_measurements",
    "all_qubits", "qubit_index", "qubit_role", "gate_list",
})

# Closed channel-kind enum.
NOISE_CHANNEL_KINDS = frozenset({
    "depolarizing", "amplitude_damping", "phase_damping", "thermal",
    "readout_error", "bit_flip", "phase_flip", "pauli",
})


@dataclass
class NoiseTarget:
    """Parsed target selector for a noise channel row.

    `kind` is one of `NOISE_TARGET_KINDS`; the optional fields carry the operand
    for the parameterized selectors (`qubit_index` → `index`, `qubit_role` →
    `role`, `gate_list` → `gates`). `raw` preserves the source cell text.
    """
    kind: str
    index: Optional[int] = None
    role: Optional[str] = None
    gates: list[str] = field(default_factory=list)
    raw: str = ""


@dataclass
class NoiseChannel:
    """One row of a `## noise_model` section: a channel applied to a target.

    `parameters` maps parameter name → value; time-domain values are normalized
    to nanoseconds at parse time. `raw_parameters` keeps the source text. The
    parser does not enforce per-channel schemas — the verifier does.
    """
    kind: str
    target: NoiseTarget
    parameters: dict = field(default_factory=dict)
    raw_parameters: str = ""


@dataclass
class NoiseModelSection:
    """A machine's declarative noise model: an ordered list of channel rows."""
    channels: list["NoiseChannel"] = field(default_factory=list)
    default_units: str = "ns"
    from_legacy_field: bool = False  # True when built from the deprecated `noise:` alias


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
class Span:
    """Lightweight source location for diagnostics.

    The Markdown parser tracks a `line` per structural element; `text` carries
    the original source fragment (e.g. an assertion category expression) so a
    verifier or compiler diagnostic can cite what the author actually wrote.
    """
    line: int = 0
    text: str = ""


@dataclass
class QubitSlice:
    """An inclusive qubit range `qs[start..end]`, or a single qubit `qs[start]`.

    A single qubit may be constructed as `QubitSlice(k)` (with `end=None`); it
    is normalized to `end == start` so `QubitSlice(k)` and `QubitSlice(k, k)`
    compare equal. A range `qs[a..b]` is `QubitSlice(a, b)` with `b >= a`.
    """
    start: int
    end: Optional[int] = None

    def __post_init__(self):
        if self.end is None:
            self.end = self.start

    @property
    def is_single(self) -> bool:
        return self.start == self.end

    def indices(self) -> list[int]:
        """All qubit indices covered by this slice, inclusive."""
        return list(range(self.start, self.end + 1))


AssertionCategory = Literal["classical", "superposition", "entangled", "separable"]


@dataclass
class QAssertion:
    """A runtime state-category assertion declared via `[assert: …]` on a state.

    Evaluated by the Stage-4b assertion checker against statistical samples of
    the circuit prefix reaching the annotated state. See
    `q_orca/verifier/assertions.py`.
    """
    category: AssertionCategory
    targets: list[QubitSlice]
    source_span: Span = field(default_factory=Span)


@dataclass
class AssertionPolicy:
    """Per-machine policy for the state-assertions stage (`## assertion policy`)."""
    shots_per_assert: int = 512
    confidence: float = 0.99
    on_failure: Literal["error", "warn"] = "error"
    backend: str = "auto"
    # Governs forcing `backend: stabilizer`/`stim` on a non-Clifford machine:
    # 'error' (default) is fatal; 'state-vector' downgrades to a warning and
    # uses the state-vector path.
    stabilizer_fallback: Literal["error", "state-vector"] = "error"


@dataclass
class QInvoke:
    """A state's delegation to another machine (`[invoke: Child(args)]`).

    `arg_bindings` maps each child context-field name to the parent-side
    expression bound to it (a bare field or an indexed reference like
    `theta[0]`), as written. `return_bindings` maps each parent context-field
    name to the child-side return it receives. `shots` is the shot-batched
    execution count (None → single-shot run-to-completion; forbidden for
    classical children — enforced by the composition verifier).
    """
    child_name: str
    arg_bindings: dict[str, str] = field(default_factory=dict)
    return_bindings: dict[str, str] = field(default_factory=dict)
    shots: Optional[int] = None


@dataclass
class QReturnDef:
    """One value a machine exposes to a caller via its `## returns` section.

    `name` is a context-field identifier or an indexed reference (`bits[0]`).
    `statistics` is a subset of {expectation, histogram, variance} and is only
    valid on measurement-bearing machines.
    """
    name: str
    type: QType
    statistics: list[str] = field(default_factory=list)


LoopKind = Literal["fixed", "adaptive"]


@dataclass
class QLoopAnnotation:
    """A bounded-loop annotation on a `## state` heading.

    `[loop <expr>]` (kind="fixed") iterates the loop body a fixed number of
    times; `bound_expr` is the raw bound expression (a numeric literal, a
    context-field reference, or a closed-form expression over context fields
    and the standard math functions `sqrt`/`ceil`/`floor`/`pi`), evaluated
    once at compile time to an integer.

    `[loop until: <predicate>]` (kind="adaptive") iterates until the classical
    `bound_expr` predicate (raw source text) holds; the predicate is re-checked
    after each body iteration. See `docs/language/bounded-loops.md`.
    """
    kind: LoopKind
    bound_expr: str
    source_span: Span = field(default_factory=Span)


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
    assertions: list[QAssertion] = field(default_factory=list)
    invoke: Optional["QInvoke"] = None
    loop: Optional["QLoopAnnotation"] = None


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
class QEffectMeasure:
    """Mid-circuit measurement: measure qubit N into classical bit M."""
    qubit_idx: int
    bit_idx: int


@dataclass
class QEffectReset:
    """Reset: re-initialise qubit N to |0⟩ (e.g. an ancilla between syndrome rounds)."""
    qubit_idx: int


@dataclass
class QEffectConditional:
    """Classical feedforward: if every (bits[i] == v) holds, apply gate.

    `conditions` is the ordered list of `(bit_idx, value)` clauses joined
    by short-circuit AND. The legacy single-condition form parses to a
    length-1 list. `bit_idx` and `value` mirror `conditions[0]` for
    read-only consumers that haven't migrated yet.
    """
    bit_idx: int
    value: int  # 0 or 1
    gate: QuantumGate
    conditions: list[tuple[int, int]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.conditions:
            self.conditions = [(self.bit_idx, self.value)]
        else:
            head_bit, head_val = self.conditions[0]
            self.bit_idx = head_bit
            self.value = head_val


@dataclass
class QContextMutation:
    """A single classical-context mutation: <lhs> <op> <rhs>."""
    target_field: str
    target_idx: Optional[int] = None  # None for scalar, int for list element
    op: str = "="                      # "=", "+=", "-="
    # Literal RHS. `int` when the source literal has no decimal point or
    # exponent (e.g., `iteration += 1`); `float` otherwise. Storing the
    # narrower type preserves `int` through `int += 1` so runtime
    # mutations don't silently promote an `int` field to `float`.
    rhs_literal: Optional[float] = None
    rhs_field: Optional[str] = None    # mutually exclusive with rhs_literal


@dataclass
class QEffectContextUpdate:
    """Optionally-bit-gated mutation of classical context fields."""
    then_mutations: list["QContextMutation"] = field(default_factory=list)
    else_mutations: list["QContextMutation"] = field(default_factory=list)
    bit_idx: Optional[int] = None
    bit_value: Optional[int] = None   # 0 or 1; None iff bit_idx is None
    raw: Optional[str] = None          # original effect string for round-trip emission


@dataclass
class ActionParameter:
    """A typed positional parameter on a parametric action signature."""
    name: str
    type: str  # "int" or "angle"


@dataclass
class BoundArg:
    """A literal argument bound at a parametric action call site."""
    name: str
    value: int | float  # int for "int" params, float for "angle" params


@dataclass
class QActionSignature:
    name: str
    parameters: list[ActionParameter] = field(default_factory=list)
    return_type: str = "void"
    effect: Optional[str] = None
    has_effect: bool = False
    effect_type: Optional[str] = None
    gate: Optional[QuantumGate] = None
    measurement: Optional[Measurement] = None
    mid_circuit_measure: Optional[QEffectMeasure] = None
    conditional_gate: Optional[QEffectConditional] = None
    context_update: Optional[QEffectContextUpdate] = None
    reset: Optional["QEffectReset"] = None


@dataclass
class QEffectDef:
    name: str
    input: str
    output: str


@dataclass
class VerificationRule:
    kind: str  # 'unitarity' | 'entanglement' | 'completeness' | 'no_cloning' | 'measurement_collapse_allowed' | 'custom'
    description: str
    target: Optional[str] = None
    custom_name: Optional[str] = None


@dataclass
class Invariant:
    kind: str          # 'entanglement' | 'schmidt_rank' | 'resource'
    qubits: list[int]  # e.g. [0, 1]; empty for kind='resource'
    op: str = "eq"     # 'eq' | 'ge' | 'gt' | 'le' | 'lt'
    value: Optional[float] = None  # e.g. 2 for schmidt_rank >= 2
    metric: Optional[str] = None  # 'gate_count' | 'depth' | 'cx_count' | 't_count' | 'logical_qubits' (kind='resource' only)


@dataclass
class QTransition:
    source: str
    event: str
    target: str
    guard: Optional[QGuardRef] = None
    action: Optional[str] = None
    # Populated for call-form references (`query_concept(3)`); `None` for bare-name refs.
    bound_arguments: Optional[list[BoundArg]] = None
    # Source-form text of the Action cell, preserved for display (e.g. Mermaid labels).
    # `None` for bare-name refs; set to the verbatim cell text for call-form refs.
    action_label: Optional[str] = None
    # Bounded-loop transition tags (recognized comma-separated alongside a real
    # action in the Action cell): `loop_done` marks the loop-exit edge,
    # `loop_back` marks the back-edge that re-enters the loop body.
    loop_done: bool = False
    loop_back: bool = False


@dataclass
class EncodingDecl:
    """Explicit ansatz declaration from a `## encoding` section.

    `kind == "hea"` is the only kind supported as of `add-rung2-hea-encoding`;
    `rotations` preserves declaration order (e.g. ("Ry", "Rz")).
    """
    kind: str
    depth: int
    entangler: str          # "ring" | "chain"
    rotations: tuple[str, ...]
    qubits: Optional[str] = None  # name of the context register; None → "qubits"


@dataclass
class ThetaRow:
    """One concept's HEA parameter tensor, shape (|rotations|, depth, n)."""
    concept: str
    tensor: object  # numpy.ndarray; not type-imported here to keep ast.py numpy-free
    cluster: str = "_default"  # tier label; `_default` when no cluster column is declared


@dataclass
class ThetaBlock:
    rows: list[ThetaRow] = field(default_factory=list)


# Qubit role vocabulary (add-qubit-role-types). `data` is the default for any
# untagged qubit. `coin`/`position` are reserved-but-not-yet-supported: the
# parser rejects them (their rules ship with the walk-primitives spec).
QUBIT_ROLES = frozenset({"data", "ancilla", "syndrome", "communication"})
RESERVED_QUBIT_ROLES = frozenset({"coin", "position"})
DEFAULT_QUBIT_ROLE = "data"


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
    invariants: list[Invariant] = field(default_factory=list)
    resource_metrics: list[str] = field(default_factory=list)
    encoding: Optional[EncodingDecl] = None
    theta: Optional[ThetaBlock] = None
    assertion_policy: AssertionPolicy = field(default_factory=AssertionPolicy)
    returns: list[QReturnDef] = field(default_factory=list)
    noise_model: Optional[NoiseModelSection] = None
    # Per-qubit role, index-aligned with the `qubits` register (declaration
    # order). Empty when no `qubits` list is declared; all `data` when untagged.
    qubit_roles: list[str] = field(default_factory=list)


@dataclass
class QImport:
    """A cross-file import row (`## imports`): bind machines from another file.

    `path` is relative (`./`, `../`) or project-relative (`q_orca:…`) — absolute
    paths are rejected at parse time. `aliases` are the names by which machines
    from the imported file may be referenced in `invoke:`.
    """
    path: str
    aliases: list[str] = field(default_factory=list)


@dataclass
class QReexport:
    """A re-export row (`## reexports`): republish an (imported) machine alias."""
    alias: str
    source: str


@dataclass
class QOrcaFile:
    machines: list[QMachineDef] = field(default_factory=list)
    imports: list[QImport] = field(default_factory=list)
    reexports: list[QReexport] = field(default_factory=list)


@dataclass
class QParseResult:
    file: QOrcaFile
    errors: list[str] = field(default_factory=list)
