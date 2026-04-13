"""Q-Orca Markdown Parser — two-phase: structural markdown -> quantum-semantic AST."""

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

from q_orca.angle import evaluate_angle as _evaluate_angle

from q_orca.ast import (
    QMachineDef, QOrcaFile, QParseResult, ContextField, EventDef, QStateDef,
    QTransition, QGuardDef, QActionSignature, QEffectDef, VerificationRule, Invariant,
    QType, QTypeQubit, QTypeList, QTypeScalar, QTypeOptional, QTypeCustom,
    QGuardRef, QuantumGate, Measurement, CollapseOutcome,
    QGuardTrue, QGuardFalse, QGuardCompare, QGuardProbability, QGuardFidelity,
    VariableRef, ValueRef,
)


# ============================================================
# Phase 1: Structural Markdown Parsing
# ============================================================

@dataclass
class MdHeading:
    kind: str = "heading"
    level: int = 0
    text: str = ""
    line: int = 0


@dataclass
class MdTable:
    kind: str = "table"
    headers: list[str] = None
    rows: list[list[str]] = None
    line: int = 0


@dataclass
class MdBulletList:
    kind: str = "bullets"
    items: list[str] = None
    line: int = 0


@dataclass
class MdBlockquote:
    kind: str = "blockquote"
    text: str = ""
    line: int = 0


MdElement = MdHeading | MdTable | MdBulletList | MdBlockquote


def parse_markdown_structure(source: str) -> list[MdElement]:
    lines = source.split("\n")
    elements: list[MdElement] = []
    i = 0

    while i < len(lines):
        trimmed = lines[i].strip()

        if trimmed == "":
            i += 1
            continue

        # Skip fenced code blocks
        if trimmed.startswith("```"):
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                i += 1
            if i < len(lines):
                i += 1
            continue

        # Horizontal rule separator (--- between machines)
        if trimmed == "---":
            i += 1
            continue

        # Heading
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", trimmed)
        if heading_match:
            elements.append(MdHeading(
                level=len(heading_match.group(1)),
                text=heading_match.group(2).strip(),
                line=i + 1,
            ))
            i += 1
            continue

        # Blockquote
        if trimmed.startswith(">"):
            quote_lines = []
            start_line = i + 1
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote_lines.append(lines[i].strip().lstrip(">").strip())
                i += 1
            elements.append(MdBlockquote(text="\n".join(quote_lines), line=start_line))
            continue

        # Table
        if trimmed.startswith("|"):
            table_lines = []
            start_line = i + 1
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i].strip())
                i += 1
            if len(table_lines) >= 2:
                headers = _parse_table_row(table_lines[0])
                is_separator = re.match(r"^\|[\s\-:|]+\|$", table_lines[1]) is not None
                data_start = 2 if is_separator else 1
                rows = [_parse_table_row(line) for line in table_lines[data_start:]]
                elements.append(MdTable(headers=headers, rows=rows, line=start_line))
            continue

        # Bullet list
        if trimmed.startswith("- "):
            items = []
            start_line = i + 1
            while i < len(lines) and lines[i].strip().startswith("- "):
                items.append(lines[i].strip()[2:].strip())
                i += 1
            elements.append(MdBulletList(items=items, line=start_line))
            continue

        # Skip paragraph (not needed for our format)
        i += 1

    return elements


def _parse_table_row(line: str) -> list[str]:
    KET_OPEN = "\x01"
    KET_CLOSE = "\x02"
    processed = re.sub(r"\|([^\s|][^|]*?)>", lambda m: f"{KET_OPEN}{m.group(1)}{KET_CLOSE}", line)
    cells = [c.strip() for c in processed.split("|")]
    if cells and cells[0] == "":
        cells = cells[1:]
    if cells and cells[-1] == "":
        cells = cells[:-1]
    return [s.replace(KET_OPEN, "|").replace(KET_CLOSE, ">") for s in cells]


# ============================================================
# Phase 2: Semantic Parsing
# ============================================================

def parse_q_orca_markdown(source: str) -> QParseResult:
    elements = parse_markdown_structure(source)
    machines = []
    errors: list[str] = []

    chunks = _split_by_separator(elements)
    for chunk in chunks:
        machine = _parse_machine_chunk(chunk, errors)
        if machine:
            machines.append(machine)

    return QParseResult(file=QOrcaFile(machines=machines), errors=errors)


def _split_by_separator(elements: list[MdElement]) -> list[list[MdElement]]:
    chunks: list[list[MdElement]] = [[]]
    for el in elements:
        if isinstance(el, MdHeading) and el.level == 0 and el.text == "---":
            chunks.append([])
        else:
            chunks[-1].append(el)
    return [c for c in chunks if c]


def _parse_machine_chunk(elements: list[MdElement], errors: list[str] | None = None) -> Optional[QMachineDef]:
    name = ""
    context: list[ContextField] = []
    events: list[EventDef] = []
    states: list[QStateDef] = []
    transitions: list[QTransition] = []
    guards: list[QGuardDef] = []
    actions: list[QActionSignature] = []
    effects: list[QEffectDef] = []
    verification_rules: list[VerificationRule] = []
    invariants: list[Invariant] = []

    i = 0
    while i < len(elements):
        el = elements[i]

        if isinstance(el, MdHeading) and el.level == 1 and el.text.lower().startswith("machine "):
            name = el.text[8:].strip()
            i += 1
            continue

        if isinstance(el, MdHeading) and el.level == 2:
            section_name_lower = el.text.lower()  # full lowercased text for comparison
            section_full = el.text  # original text (for state headings with Greek letters)

            if section_name_lower == "context":
                i += 1
                if i < len(elements) and isinstance(elements[i], MdTable):
                    context = _parse_context_table(elements[i])
                    i += 1
                continue

            if section_name_lower == "events":
                i += 1
                if i < len(elements) and isinstance(elements[i], MdBulletList):
                    events = [_parse_event_def(item) for item in elements[i].items]
                    i += 1
                continue

            if section_name_lower.startswith("state "):
                state, next_i = _parse_state_heading(section_full, elements, i)
                states.append(state)
                i = next_i
                continue

            if section_name_lower == "transitions":
                i += 1
                if i < len(elements) and isinstance(elements[i], MdTable):
                    transitions = _parse_transitions_table(elements[i])
                    i += 1
                continue

            if section_name_lower == "guards":
                i += 1
                if i < len(elements) and isinstance(elements[i], MdTable):
                    guards = _parse_guards_table(elements[i])
                    i += 1
                continue

            if section_name_lower == "actions":
                i += 1
                if i < len(elements) and isinstance(elements[i], MdTable):
                    actions = _parse_actions_table(elements[i], errors)
                    i += 1
                continue

            if section_name_lower == "effects":
                i += 1
                if i < len(elements) and isinstance(elements[i], MdTable):
                    effects = _parse_effects_table(elements[i])
                    i += 1
                continue

            if section_name_lower == "verification rules":
                i += 1
                if i < len(elements) and isinstance(elements[i], MdBulletList):
                    verification_rules = _parse_verification_rules(elements[i])
                    i += 1
                continue

            if section_name_lower == "invariants":
                i += 1
                if i < len(elements) and isinstance(elements[i], MdBulletList):
                    invariants = _parse_invariants(elements[i])
                    i += 1
                continue

        i += 1

    if not name:
        return None

    # Mark first state as initial if none explicitly marked
    if states and not any(s.is_initial for s in states):
        states[0].is_initial = True

    return QMachineDef(
        name=name,
        context=context,
        events=events,
        states=states,
        transitions=transitions,
        guards=guards,
        actions=actions,
        effects=effects,
        verification_rules=verification_rules,
        invariants=invariants,
    )


def _parse_context_table(table: MdTable) -> list[ContextField]:
    fields: list[ContextField] = []
    field_idx = _find_column_index(table.headers, "field")
    type_idx = _find_column_index(table.headers, "type")
    default_idx = _find_column_index(table.headers, "default")

    for row in table.rows:
        name = _strip_backticks(row[field_idx] if field_idx >= 0 else "").strip()
        type_str = _strip_backticks(row[type_idx] if type_idx >= 0 else "").strip()
        default_val = row[default_idx].strip() if default_idx >= 0 and default_idx < len(row) else None

        if not name:
            continue

        fields.append(ContextField(
            name=name,
            type=_parse_q_type_string(type_str),
            default_value=default_val if default_val else None,
        ))

    return fields


def _parse_event_def(item: str) -> EventDef:
    name = item.split("#")[0].split("(")[0].strip()
    return EventDef(name=name)


def _parse_state_heading(heading_text: str, elements: list[MdElement], current_index: int) -> tuple[QStateDef, int]:
    # heading_text is like "state |00>" or "state |ψ> = (|00> + |11>)/√2"
    rest = heading_text[6:].strip()  # remove "state "

    is_initial = False
    is_final = False

    # Check for [initial] / [final] annotations
    if re.search(r"\[initial\]", rest, re.IGNORECASE):
        is_initial = True
        rest = re.sub(r"\[initial\]", "", rest, flags=re.IGNORECASE).strip()
    if re.search(r"\[final\]", rest, re.IGNORECASE):
        is_final = True
        rest = re.sub(r"\[final\]", "", rest, flags=re.IGNORECASE).strip()

    # Parse name and optional expression
    ket_close = rest.find(">")
    eq_index = rest.find("=")

    if eq_index > 0 and ket_close > 0 and eq_index > ket_close:
        state_name = _normalize_state_name(rest[:eq_index])
        state_expression = rest[eq_index + 1:].strip()
    else:
        state_name = _normalize_state_name(rest)
        state_expression = None

    # Look for blockquote description
    description = None
    next_index = current_index + 1

    if next_index < len(elements) and isinstance(elements[next_index], MdBlockquote):
        description = elements[next_index].text
        next_index += 1

    return (
        QStateDef(
            name=state_name,
            display_name=ket_to_identifier(state_name),
            description=description,
            state_expression=state_expression,
            is_initial=is_initial,
            is_final=is_final,
        ),
        next_index,
    )


def _parse_transitions_table(table: MdTable) -> list[QTransition]:
    transitions: list[QTransition] = []
    source_idx = _find_column_index(table.headers, "source")
    event_idx = _find_column_index(table.headers, "event")
    guard_idx = _find_column_index(table.headers, "guard")
    target_idx = _find_column_index(table.headers, "target")
    action_idx = _find_column_index(table.headers, "action")

    for row in table.rows:
        source = _normalize_state_name(row[source_idx]) if source_idx >= 0 else ""
        event = row[event_idx].strip() if event_idx >= 0 else ""
        guard_str = row[guard_idx].strip() if guard_idx >= 0 else ""
        target = _normalize_state_name(row[target_idx]) if target_idx >= 0 else ""
        action = row[action_idx].strip() if action_idx >= 0 else ""

        if not source or not event or not target:
            continue

        transition = QTransition(source=source, event=event, target=target)

        if guard_str:
            transition.guard = _parse_guard_ref(guard_str)
        if action:
            transition.action = action

        transitions.append(transition)

    return transitions


def _parse_guards_table(table: MdTable) -> list[QGuardDef]:
    guards: list[QGuardDef] = []
    name_idx = _find_column_index(table.headers, "name")
    expr_idx = _find_column_index(table.headers, "expression")

    for row in table.rows:
        name = row[name_idx].strip() if name_idx >= 0 else ""
        expr_str = row[expr_idx].strip() if expr_idx >= 0 else ""

        if not name:
            continue

        guards.append(QGuardDef(name=name, expression=_parse_q_guard_expression(expr_str)))

    return guards


def _parse_actions_table(table: MdTable, errors: list[str] | None = None) -> list[QActionSignature]:
    actions: list[QActionSignature] = []
    name_idx = _find_column_index(table.headers, "name")
    sig_idx = _find_column_index(table.headers, "signature")
    effect_idx = _find_column_index(table.headers, "effect")

    for row in table.rows:
        name = row[name_idx].strip() if name_idx >= 0 else ""
        sig_str = row[sig_idx].strip() if sig_idx >= 0 else ""
        effect_str = row[effect_idx].strip() if effect_idx >= 0 else ""

        if not name:
            continue

        params, return_type = _parse_signature(sig_str)
        gate = _parse_gate_from_effect(effect_str, errors, action_name=name)
        measurement = _parse_measurement_from_effect(effect_str)

        actions.append(QActionSignature(
            name=name,
            parameters=params,
            return_type=return_type,
            effect=effect_str if effect_str else None,
            has_effect=bool(effect_str),
            gate=gate,
            measurement=measurement,
        ))

    return actions


def _parse_effects_table(table: MdTable) -> list[QEffectDef]:
    effects: list[QEffectDef] = []
    name_idx = _find_column_index(table.headers, "name")
    input_idx = _find_column_index(table.headers, "input")
    output_idx = _find_column_index(table.headers, "output")

    for row in table.rows:
        name = row[name_idx].strip() if name_idx >= 0 else ""
        inp = row[input_idx].strip() if input_idx >= 0 else ""
        out = row[output_idx].strip() if output_idx >= 0 else ""

        if not name:
            continue

        effects.append(QEffectDef(name=name, input=inp, output=out))

    return effects


def _parse_verification_rules(list_el: MdBulletList) -> list[VerificationRule]:
    rules: list[VerificationRule] = []
    known_kinds = ["unitarity", "entanglement", "completeness", "no_cloning"]

    for item in list_el.items:
        colon_index = item.find(":")
        if colon_index < 0:
            rules.append(VerificationRule(kind="custom", description=item, custom_name=item))
            continue

        kind_str = item[:colon_index].strip().lower().replace("-", "_")
        description = item[colon_index + 1:].strip()
        kind = kind_str if kind_str in known_kinds else "custom"

        rules.append(VerificationRule(
            kind=kind,
            description=description,
            custom_name=kind_str if kind == "custom" else None,
        ))

    return rules


def _parse_invariants(list_el: MdBulletList) -> list[Invariant]:
    invariants: list[Invariant] = []
    for item in list_el.items:
        # entanglement(q0,q1) = True
        m = re.match(r"entanglement\(\s*(q\d+)\s*,\s*(q\d+)\s*\)\s*=\s*True", item, re.IGNORECASE)
        if m:
            q1 = int(re.search(r'\d+', m.group(1)).group())
            q2 = int(re.search(r'\d+', m.group(2)).group())
            invariants.append(Invariant(kind="entanglement", qubits=[q1, q2]))
            continue
        # schmidt_rank(q0,q1) >= 2
        m = re.match(r"schmidt_rank\(\s*(q\d+)\s*,\s*(q\d+)\s*\)\s*(>=|>|<=|<|==)\s*(\d+)", item, re.IGNORECASE)
        if m:
            q1 = int(re.search(r'\d+', m.group(1)).group())
            q2 = int(re.search(r'\d+', m.group(2)).group())
            op = _parse_comparison_op(m.group(3))
            value = float(m.group(4))
            invariants.append(Invariant(kind="schmidt_rank", qubits=[q1, q2], op=op, value=value))
    return invariants


# ============================================================
# Micro-Parsers
# ============================================================

def _strip_backticks(text: str) -> str:
    if text.startswith("`") and text.endswith("`"):
        return text[1:-1]
    return text


def _normalize_state_name(name: str) -> str:
    """NFC-normalize and strip a state name so heading and table lookups always agree.

    Applies Unicode NFC normalization (e.g. é as U+00E9 vs e + combining acute)
    and strips surrounding whitespace. Unicode characters are preserved — this
    function must never ASCII-ify or transliterate the content.
    """
    return unicodedata.normalize("NFC", name.strip())


def _find_column_index(headers: list[str], name: str) -> int:
    for i, h in enumerate(headers):
        if h.lower().strip() == name.lower():
            return i
    return -1


def ket_to_identifier(name: str) -> str:
    """Convert ket notation to a safe identifier: |00> -> "ket_00", |ψ> -> "ket_psi"."""
    greek_map = {
        "ψ": "psi", "φ": "phi", "Φ": "Phi", "χ": "chi",
        "α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta",
        "ε": "epsilon", "θ": "theta", "λ": "lambda", "μ": "mu",
        "π": "pi", "σ": "sigma", "τ": "tau", "ω": "omega",
        "√": "sqrt", "∞": "inf", "±": "pm",
    }
    id_ = name.replace("|", "").replace(">", "").replace("<", "")
    for greek, latin in greek_map.items():
        id_ = id_.replace(greek, latin)
    id_ = re.sub(r"[^a-zA-Z0-9_]", "_", id_)
    id_ = re.sub(r"_+", "_", id_).strip("_")
    return f"ket_{id_ or 'unnamed'}"


def _parse_q_type_string(text: str) -> QType:
    text = text.strip()
    if text.endswith("?"):
        return QTypeOptional(inner_type=text[:-1])
    list_match = re.match(r"^list<\s*(.+)\s*>$", text)
    if list_match:
        return QTypeList(element_type=list_match.group(1))
    if text == "qubit":
        return QTypeQubit()
    scalar_map = {"int": "int", "float": "float", "decimal": "float",
                  "bool": "bool", "string": "string", "complex": "complex",
                  "state_vector": "state_vector", "density_matrix": "density_matrix",
                  "noise_model": "noise_model"}
    if text in scalar_map:
        return QTypeScalar(kind=text)
    return QTypeCustom(name=text)


def _parse_guard_ref(text: str) -> QGuardRef:
    text = text.strip()
    negated = False
    if text.startswith("!"):
        negated = True
        text = text[1:].strip()
    # Strip probability comparison suffix
    text = re.sub(r"\s*[≈=!<>]+[\d.]+\s*$", "", text).strip()
    return QGuardRef(name=text, negated=negated)


def _parse_q_guard_expression(text: str):
    text = text.strip()
    if text == "true":
        return QGuardTrue()
    if text == "false":
        return QGuardFalse()

    # Fidelity expression
    m = re.match(r"fidelity\(\s*(\|[^>]+>)\s*,\s*(\|[^>]+>)\s*\)\s*\*\*\s*2\s*(≈|==|!=|<=|>=|<|>)\s*([\d.]+)", text)
    if m:
        return QGuardFidelity(
            state_a=m.group(1).strip(),
            state_b=m.group(2).strip(),
            op=_parse_comparison_op(m.group(3)),
            value=float(m.group(4)),
        )

    # Probability expression
    m = re.match(r"prob(?:_collapse)?\(\s*'([^']+)'\s*\)\s*(≈|==|=|!=|<=|>=|<|>)\s*([\d.]+)", text)
    if m:
        return QGuardProbability(outcome=CollapseOutcome(
            bitstring=m.group(1),
            probability=float(m.group(3)),
        ))

    # Comparison
    m = re.match(r"^([a-zA-Z_][\w.]*)\s*(==|!=|<=|>=|<|>|≈)\s*(.+)$", text)
    if m:
        return QGuardCompare(
            op=_parse_comparison_op(m.group(2)),
            left=VariableRef(path=m.group(1).split(".")),
            right=_parse_value_ref(m.group(3).strip()),
        )

    return QGuardTrue()


def _parse_comparison_op(op: str) -> str:
    return {"==": "eq", "=": "eq", "!=": "ne", "<": "lt", ">": "gt", "<=": "le", ">=": "ge", "≈": "approx"}.get(op, "eq")


def _parse_value_ref(text: str):
    text = text.strip()
    if (text.startswith("'") and text.endswith("'")) or (text.startswith('"') and text.endswith('"')):
        return ValueRef(type="string", value=text[1:-1])
    if text == "true":
        return ValueRef(type="boolean", value=True)
    if text == "false":
        return ValueRef(type="boolean", value=False)
    if text == "null":
        return ValueRef(type="null", value=None)
    try:
        return ValueRef(type="number", value=float(text))
    except ValueError:
        return ValueRef(type="string", value=text)


def _parse_signature(text: str) -> tuple[list[str], str]:
    if not text:
        return [], "void"
    m = re.match(r"^\(([^)]*)\)\s*->\s*(.+)$", text)
    if m:
        params = [p.strip() for p in m.group(1).split(",") if p.strip()]
        return params, m.group(2).strip()
    return [], "void"


def _parse_gate_from_effect(
    effect_str: str,
    errors: list[str] | None = None,
    action_name: str = "",
) -> Optional[QuantumGate]:
    if not effect_str:
        return None

    # Hadamard(qs[N])
    m = re.search(r"Hadamard\(\s*\w+\[(\d+(?:\s+\d+\s+\d+)?)\]\s*\)", effect_str, re.IGNORECASE)
    if m:
        indices = [int(x) for x in m.group(1).split()]
        return QuantumGate(kind="H", targets=indices)

    # CNOT(qs[control], qs[target])
    m = re.search(r"CNOT\(\s*\w+\[(\d+)\]\s*,\s*\w+\[(\d+)\]\s*\)", effect_str, re.IGNORECASE)
    if m:
        return QuantumGate(kind="CNOT", targets=[int(m.group(2))], controls=[int(m.group(1))])

    # Two-qubit parameterized gates: CRx/CRy/CRz/RXX/RYY/RZZ(qs[i], qs[j], angle)
    m = re.search(r"(CRx|CRy|CRz|RXX|RYY|RZZ)\(\s*\w+\[(\d+)\]\s*,\s*\w+\[(\d+)\]\s*,\s*([^)]+)\s*\)", effect_str, re.IGNORECASE)
    if m:
        raw_kind = m.group(1).upper()
        # Normalize to canonical forms: CRx/CRy/CRz (capital C+R, lowercase axis)
        canonical_map = {"CRX": "CRx", "CRY": "CRy", "CRZ": "CRz", "RXX": "RXX", "RYY": "RYY", "RZZ": "RZZ"}
        kind = canonical_map.get(raw_kind, raw_kind)
        ctrl_or_i = int(m.group(2))
        tgt_or_j = int(m.group(3))
        angle_str = m.group(4).strip()
        try:
            theta = _evaluate_angle(angle_str)
        except ValueError as exc:
            if errors is not None:
                prefix = f"action {action_name!r}: " if action_name else ""
                errors.append(f"{prefix}two-qubit gate {kind} has unrecognized angle {angle_str!r}. {exc}")
            return None
        # Controlled forms use controls=[ctrl], targets=[tgt]; symmetric forms use targets=[i,j]
        if kind in ("CRx", "CRy", "CRz"):
            return QuantumGate(kind=kind, targets=[tgt_or_j], controls=[ctrl_or_i], parameter=theta)
        else:
            return QuantumGate(kind=kind, targets=[ctrl_or_i, tgt_or_j], parameter=theta)

    # Rotation gates canonical form: Rx(qs[N], <angle>), Ry(qs[N], <angle>), Rz(qs[N], <angle>)
    m = re.search(r"R([XYZ])\(\s*\w+\[(\d+)\]\s*,\s*([^)]+)\s*\)", effect_str, re.IGNORECASE)
    if m:
        axis = m.group(1).upper()  # 'X', 'Y', or 'Z'
        # Canonical GateKind is 'Rx'/'Ry'/'Rz' (capital R, lowercase axis)
        axis = axis.lower()
        idx = int(m.group(2))
        angle_str = m.group(3).strip()
        try:
            theta = _evaluate_angle(angle_str)
        except ValueError as exc:
            if errors is not None:
                prefix = f"action {action_name!r}: " if action_name else ""
                errors.append(f"{prefix}rotation gate R{axis} has unrecognized angle {angle_str!r}. {exc}")
            return None
        return QuantumGate(kind=f"R{axis}", targets=[idx], parameter=theta)

    # Detect angle-first rotation syntax (wrong order) and produce an error
    m_wrong = re.search(r"R([XYZ])\(\s*([^,)]+)\s*,\s*\w+\[\d+\]\s*\)", effect_str, re.IGNORECASE)
    if m_wrong:
        axis = m_wrong.group(1).upper()
        if errors is not None:
            prefix = f"action {action_name!r}: " if action_name else ""
            errors.append(
                f"{prefix}rotation gate R{axis} uses angle-first argument order. "
                "The canonical form is qubit-first: R{axis}(qs[N], <angle>)."
            )
        return None

    # Generic gate: X(qs[N]), Z(qs[N]), etc.
    m = re.search(r"^([A-Z][a-z]*)\(\s*\w+\[(\d+)\]\s*\)", effect_str)
    if m:
        gate_kinds = {"X": "X", "Y": "Y", "Z": "Z", "H": "H", "T": "T", "S": "S"}
        kind = gate_kinds.get(m.group(1), "custom")
        return QuantumGate(kind=kind, targets=[int(m.group(2))], custom_name=kind if kind == "custom" else None)

    return None


def _parse_measurement_from_effect(effect_str: str) -> Optional[Measurement]:
    if not effect_str:
        return None
    # Match 'measure(q[i])' (standard) OR 'M(q[i])' (custom quantum notation).
    # 'M' is the conventional single-letter symbol for measurement in quantum circuits.
    m = re.search(r"(?:measure|M)\(\s*\w+\[([^\]]+)\]\s*\)", effect_str, re.IGNORECASE)
    if m:
        indices = [int(x.strip()) for x in m.group(1).split(",")]
        return Measurement(qubits=indices, basis="computational")
    return None
