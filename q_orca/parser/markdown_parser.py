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
    VariableRef, ValueRef, QEffectMeasure, QEffectConditional,
    QContextMutation, QEffectContextUpdate,
    ActionParameter, BoundArg,
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


# Level-2 section keywords recognized by the semantic parser. A heading like
# `## context | F | T | D |` is a common user mistake where the table's header
# row got glued onto the section heading; we detect this shape to recover.
_KNOWN_SECTIONS = frozenset({
    "context", "events", "transitions", "guards", "actions", "effects",
    "verification rules", "invariants",
})


def _section_key(heading_text: str) -> str:
    """Return the canonical section keyword for matching a level-2 heading.

    Strips inline table-header content (`| ... |`) that users sometimes leave
    attached to a heading line by mistake. State headings are passed through
    untouched because ket notation legitimately uses `|`.
    """
    text = heading_text.strip().lower()
    if text.startswith("state "):
        return text
    return text.split("|", 1)[0].strip()


def parse_markdown_structure(
    source: str,
    errors: Optional[list[str]] = None,
) -> list[MdElement]:
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
            level = len(heading_match.group(1))
            raw_text = heading_match.group(2).strip()
            # Detect `## context | F | T | D |` — a level-2 section heading
            # where the table header row has been glued onto the heading line.
            # Split into a clean heading and feed the inline pipe tokens into
            # the following table as its first row.
            inline_header: Optional[str] = None
            clean_text = raw_text
            if level == 2 and "|" in raw_text:
                head, _pipe, rest = raw_text.partition("|")
                head_norm = head.strip().lower()
                if head_norm in _KNOWN_SECTIONS:
                    clean_text = head.strip()
                    inline_header = "|" + rest
                    if errors is not None:
                        errors.append(
                            f"Line {i + 1}: section heading '## {raw_text}' has "
                            f"inline table content; place the table header row "
                            f"on the next line."
                        )
            elements.append(MdHeading(level=level, text=clean_text, line=i + 1))
            i += 1
            if inline_header is not None:
                # Gather any following table lines and treat inline_header as
                # the first header row of that table.
                table_lines = [inline_header]
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
    errors: list[str] = []
    elements = parse_markdown_structure(source, errors=errors)
    machines = []

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


def _prescan_context(elements: list[MdElement]) -> list[ContextField]:
    """Locate the first `## context` table in `elements` and parse it.

    The pre-scan exists so that action effect strings can resolve
    context-field angle references regardless of section order.
    """
    for j, el in enumerate(elements):
        if (
            isinstance(el, MdHeading)
            and el.level == 2
            and _section_key(el.text) == "context"
        ):
            if j + 1 < len(elements) and isinstance(elements[j + 1], MdTable):
                return _parse_context_table(elements[j + 1])
            return []
    return []


def _build_angle_context(context_fields: list[ContextField]) -> dict[str, float]:
    """Build a {name: float} map of context fields usable as gate angles.

    Includes only fields whose declared type is `int` or `float` and whose
    default value parses as a number. Fields without defaults or with
    non-numeric defaults are skipped.
    """
    out: dict[str, float] = {}
    for f in context_fields:
        kind = getattr(f.type, "kind", "")
        if kind not in ("int", "float"):
            continue
        if not f.default_value:
            continue
        try:
            out[f.name] = float(f.default_value.strip())
        except (ValueError, AttributeError):
            continue
    return out


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

    # Pre-scan for the context table so that angle expressions in actions
    # can reference numeric context fields regardless of section order.
    context = _prescan_context(elements)
    angle_context = _build_angle_context(context)

    i = 0
    while i < len(elements):
        el = elements[i]

        if isinstance(el, MdHeading) and el.level == 1 and el.text.lower().startswith("machine "):
            name = el.text[8:].strip()
            i += 1
            continue

        if isinstance(el, MdHeading) and el.level == 2:
            section_name_lower = _section_key(el.text)  # canonical key; strips inline `| ... |`
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
                    actions = _parse_actions_table(elements[i], errors, angle_context)
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

    # Resolve transition action cells against the collected action
    # signatures. Running this after both tables are parsed lets
    # transitions reference actions declared later in the file.
    _resolve_transition_actions(transitions, actions, angle_context, errors)

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


_CALL_FORM_RE = re.compile(
    r"^([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)\s*$", re.DOTALL
)


def _resolve_transition_actions(
    transitions: list[QTransition],
    actions: list[QActionSignature],
    angle_context: Optional[dict[str, float]] = None,
    errors: Optional[list[str]] = None,
) -> None:
    """Resolve each transition's Action cell against the collected actions.

    Runs as a second pass after both the transitions and actions tables
    have been parsed, so forward references (a transition that invokes
    an action declared later in the file) parse without ordering
    constraints.

    For call-form cells (`name(args)`), verifies arity and per-argument
    type against the referenced action's signature, populates
    `QTransition.action` with the bare name, `action_label` with the
    verbatim source text, and `bound_arguments` with one `BoundArg` per
    declared parameter. For bare-name cells referencing a parametric
    action, emits a structured error — parametric actions MUST be
    invoked with their arguments.
    """
    actions_by_name = {a.name: a for a in actions}

    for t in transitions:
        if not t.action:
            continue
        raw = t.action.strip()
        transition_ref = f"transition {t.source!r} --{t.event}--> {t.target!r}"
        m = _CALL_FORM_RE.match(raw)

        if m:
            name = m.group(1)
            args_str = m.group(2).strip()
            sig = actions_by_name.get(name)
            if sig is None:
                if errors is not None:
                    errors.append(
                        f"{transition_ref}: call-form action {name!r} is not "
                        f"declared in the actions table."
                    )
                continue
            if not sig.parameters:
                if errors is not None:
                    errors.append(
                        f"{transition_ref}: action {name!r} is not parametric "
                        f"(signature takes no arguments); use the bare-name "
                        f"form."
                    )
                continue
            raw_args: list[str] = (
                [a.strip() for a in args_str.split(",")] if args_str else []
            )
            if len(raw_args) != len(sig.parameters):
                if errors is not None:
                    errors.append(
                        f"{transition_ref}: action {name!r} expects "
                        f"{len(sig.parameters)} argument(s), got {len(raw_args)}."
                    )
                continue

            bound: list[BoundArg] = []
            ok = True
            for param, arg_text in zip(sig.parameters, raw_args):
                if param.type == "int":
                    if not re.fullmatch(r"-?\d+", arg_text):
                        if errors is not None:
                            errors.append(
                                f"{transition_ref}: action {name!r} parameter "
                                f"{param.name!r} expects an int literal, got "
                                f"{arg_text!r}."
                            )
                        ok = False
                        break
                    bound.append(BoundArg(name=param.name, value=int(arg_text)))
                elif param.type == "angle":
                    try:
                        val = _evaluate_angle(arg_text, angle_context)
                    except ValueError as exc:
                        if errors is not None:
                            errors.append(
                                f"{transition_ref}: action {name!r} parameter "
                                f"{param.name!r}: {exc}"
                            )
                        ok = False
                        break
                    bound.append(BoundArg(name=param.name, value=val))
                else:
                    # Defensive — signature parser restricts types to the
                    # supported set, so this branch should be unreachable.
                    if errors is not None:
                        errors.append(
                            f"{transition_ref}: action {name!r} parameter "
                            f"{param.name!r} has unsupported type "
                            f"{param.type!r}."
                        )
                    ok = False
                    break
            if not ok:
                continue
            t.action = name
            t.action_label = raw
            t.bound_arguments = bound
        else:
            # Bare-name reference; validate only that it doesn't skip
            # required parametric arguments. Undeclared bare-name actions
            # are left alone to preserve historical parser behavior.
            sig = actions_by_name.get(raw)
            if sig is not None and sig.parameters:
                if errors is not None:
                    errors.append(
                        f"{transition_ref}: action {raw!r} is parametric and "
                        f"requires arguments (expected {len(sig.parameters)} "
                        f"argument(s))."
                    )


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


def _parse_actions_table(
    table: MdTable,
    errors: list[str] | None = None,
    angle_context: dict[str, float] | None = None,
) -> list[QActionSignature]:
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

        params, return_type = _parse_signature(sig_str, errors=errors, action_name=name)
        context_update = _parse_context_update_from_effect(effect_str, errors, action_name=name)
        if params and effect_str:
            _validate_parametric_template(effect_str, params, errors, action_name=name)
        # Merge parametric angle-typed parameter names into the angle context so
        # gate-effect parsing of a parametric template (e.g. `Ry(qs[0], a)` with
        # `a: angle`) does not re-emit "unrecognized angle" errors that
        # _validate_parametric_template already surfaced as structured
        # unbound-identifier diagnostics. Per-call-site expansion substitutes
        # real values at compile time; the template's angle_context entry is a
        # 0.0 placeholder for template-level gate parsing only.
        effect_angle_context = angle_context
        if params:
            effect_angle_context = dict(angle_context)
            for p in params:
                if p.type == "angle":
                    effect_angle_context.setdefault(p.name, 0.0)
        gate = _parse_gate_from_effect(effect_str, errors, action_name=name, angle_context=effect_angle_context)
        measurement = _parse_measurement_from_effect(effect_str)
        mid_circuit_measure = _parse_mid_circuit_measure_from_effect(effect_str)
        conditional_gate = _parse_conditional_gate_from_effect(effect_str, errors, action_name=name, angle_context=effect_angle_context)

        has_other_effect = (
            gate is not None
            or measurement is not None
            or mid_circuit_measure is not None
            or conditional_gate is not None
        )

        # If the parser recognized a context-update AND any other effect,
        # that's a mixed-kind effect — rejected in v1.
        if context_update is not None and has_other_effect:
            if errors is not None:
                errors.append(
                    f"action {name!r}: context-update effect cannot be combined with "
                    f"gate, measurement, mid-circuit measurement, or conditional-gate "
                    f"effects in a single action (v1)."
                )
            context_update = None
        # Otherwise, a gate+something string may still hide an unparsed
        # mutation tail (e.g. `H(qs[0]); iteration += 1`). Detect the
        # mutation-operator pattern in any `;`-delimited segment that isn't
        # the first and isn't a parsed gate.
        elif has_other_effect and effect_str and _contains_mutation_segment(effect_str):
            if errors is not None:
                errors.append(
                    f"action {name!r}: context-update effect cannot be combined with "
                    f"gate, measurement, mid-circuit measurement, or conditional-gate "
                    f"effects in a single action (v1)."
                )

        # Skip the "looks-like-gate" warning when the effect parsed as a
        # context-update; otherwise we'd spuriously flag `iteration += 1`
        # as a gate typo. Also skip for parametric actions, whose effect
        # strings legitimately use identifier subscripts (`qs[c]`) that the
        # current gate-effect parser cannot resolve — per-call-site
        # expansion handles them at compile time.
        if (
            effect_str
            and gate is None
            and measurement is None
            and mid_circuit_measure is None
            and conditional_gate is None
            and context_update is None
            and not params
            and errors is not None
            and _looks_like_gate_call(effect_str)
            # Don't double-fire if _parse_gate_from_effect already surfaced a
            # specific error for this effect (e.g. MCX with wrong arity).
            and not any("requires at least" in e for e in errors)
        ):
            errors.append(
                f"action {name!r}: effect {effect_str!r} looks like a gate call "
                "but does not match any known gate. Check the gate name for typos "
                "(known gates: H, X, Y, Z, T, S, CNOT, CZ, SWAP, CSWAP, CCNOT/CCX, "
                "CCZ, MCX, MCZ, Rx, Ry, Rz, CRx, CRy, CRz, RXX, RYY, RZZ)."
            )

        actions.append(QActionSignature(
            name=name,
            parameters=params,
            return_type=return_type,
            effect=effect_str if effect_str else None,
            has_effect=bool(effect_str),
            gate=gate,
            measurement=measurement,
            mid_circuit_measure=mid_circuit_measure,
            conditional_gate=conditional_gate,
            context_update=context_update,
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
        element = list_match.group(1).strip()
        return QTypeList(element_type=element)
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


_SUPPORTED_PARAM_TYPES = frozenset({"int", "angle"})


def _parse_signature(
    text: str,
    errors: list[str] | None = None,
    action_name: str = "",
) -> tuple[list[ActionParameter], str]:
    """Parse an action signature string into typed parameters + return type.

    Accepted forms:
      - `(qs) -> qs` → empty parameter list
      - `(qs, name: type, ...) -> qs` → one typed parameter per extra slot
    Supported parameter types are `int` and `angle`. Duplicate parameter
    names and unsupported types are reported through ``errors`` and the
    offending parameter is dropped.
    """
    if not text:
        return [], "void"
    m = re.match(r"^\(([^)]*)\)\s*->\s*(.+)$", text)
    if not m:
        return [], "void"
    raw_params = [p.strip() for p in m.group(1).split(",") if p.strip()]
    return_type = m.group(2).strip()

    # Typed-parameter grammar is opt-in: only triggered when a slot contains
    # a `: type` annotation. Signatures with no typed slots (the historical
    # form for quantum and classical actions alike — `(qs) -> qs`,
    # `(ctx) -> ctx`) parse with an empty `parameters` list.
    if not any(":" in slot for slot in raw_params):
        return [], return_type

    # Typed form: leading slot must be the bare qubit-list binder `qs`.
    head, *tail = raw_params
    if head != "qs":
        if errors is not None:
            errors.append(
                f"action {action_name!r}: parametric signature must begin "
                f"with `qs` (got {head!r})."
            )
        return [], return_type

    parameters: list[ActionParameter] = []
    seen: set[str] = set()
    for slot in tail:
        # Each typed parameter is `name: type`.
        if ":" not in slot:
            if errors is not None:
                errors.append(
                    f"action {action_name!r}: parameter slot {slot!r} must have "
                    f"the form `name: type` (supported types: int, angle)."
                )
            continue
        name_part, type_part = slot.split(":", 1)
        name = name_part.strip()
        type_name = type_part.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            if errors is not None:
                errors.append(
                    f"action {action_name!r}: invalid parameter name {name!r}."
                )
            continue
        if type_name not in _SUPPORTED_PARAM_TYPES:
            if errors is not None:
                errors.append(
                    f"action {action_name!r}: unsupported parameter type "
                    f"{type_name!r} for parameter {name!r} "
                    f"(supported: int, angle)."
                )
            continue
        if name in seen:
            if errors is not None:
                errors.append(
                    f"action {action_name!r}: duplicate parameter name {name!r}."
                )
            continue
        seen.add(name)
        parameters.append(ActionParameter(name=name, type=type_name))
    return parameters, return_type


def _looks_like_gate_call(effect_str: str) -> bool:
    """Return True if effect_str appears to be a gate-call expression.

    Used by `_parse_actions_table` to surface typos in gate names: e.g.
    `MCXY(qs[0], qs[1], qs[2])` doesn't match any known gate and would
    otherwise be silently dropped. A literal `Name(qs[...]...)` shape is
    sufficient to warn; non-gate effects (bare text, measurements,
    conditionals) are already handled by their respective parsers.
    """
    return bool(re.match(r"^\s*[A-Za-z][A-Za-z0-9]*\s*\(\s*\w+\[", effect_str.strip()))


# Rotation-gate shapes that accept a symbolic angle in the last argument
# slot. Used by the parametric-template validator to route angle checks.
_ROTATION_GATE_ANGLE_RE = re.compile(
    r"(?P<name>CRx|CRy|CRz|RXX|RYY|RZZ|Rx|Ry|Rz)"
    r"\(\s*\w+\[[^\]]+\]\s*"
    r"(?:,\s*\w+\[[^\]]+\]\s*)?"
    r",\s*(?P<angle>[^)]+)\)",
    re.IGNORECASE,
)


def _validate_parametric_template(
    effect_str: str,
    parameters: list[ActionParameter],
    errors: list[str] | None,
    action_name: str,
) -> None:
    """Check identifier bindings in a parametric action's effect template.

    For each `qs[<token>]` subscript, a non-integer token must name an `int`
    parameter. For each rotation-gate angle slot, a non-literal angle must
    name an `angle` parameter (or parse as one of the symbolic forms the
    evaluator already accepts). Unbound names emit structured
    ``unbound identifier`` errors. Called only for actions whose signature
    declared at least one typed parameter; zero-parameter actions continue
    to flow through the existing gate-effect parser unchanged.
    """
    if not parameters or not effect_str or errors is None:
        return

    int_param_names = {p.name for p in parameters if p.type == "int"}
    angle_param_names = {p.name for p in parameters if p.type == "angle"}

    # Subscripts — `qs[c]` or `qs[0]` or `qs[0 1 2]` / `qs[c, d]`
    for m in re.finditer(r"\w+\[([^\]]+)\]", effect_str):
        inner = m.group(1).strip()
        for sub in re.split(r"[\s,]+", inner):
            sub = sub.strip()
            if not sub or re.fullmatch(r"-?\d+", sub):
                continue
            if re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", sub):
                if sub not in int_param_names:
                    declared = ", ".join(sorted(int_param_names)) or "(none)"
                    errors.append(
                        f"action {action_name!r}: unbound identifier {sub!r} in "
                        f"qubit-list subscript (declared int parameters: "
                        f"{declared})."
                    )
            else:
                errors.append(
                    f"action {action_name!r}: invalid subscript {sub!r} "
                    f"(bare integer literal or parameter name required; "
                    f"arithmetic expressions are not supported)."
                )

    # Rotation-gate angle slots — accept literal angle expressions or a bare
    # angle parameter. The evaluator resolves context-field angles; seed it
    # with the signature's angle parameters so identifier-form angles bound
    # to the template's own parameters parse without error.
    template_angle_ctx = {name: 0.0 for name in angle_param_names}
    for m in _ROTATION_GATE_ANGLE_RE.finditer(effect_str):
        angle_str = m.group("angle").strip()
        try:
            _evaluate_angle(angle_str, template_angle_ctx)
        except ValueError:
            if re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", angle_str):
                declared = ", ".join(sorted(angle_param_names)) or "(none)"
                errors.append(
                    f"action {action_name!r}: unbound identifier {angle_str!r} "
                    f"in angle slot (declared angle parameters: {declared})."
                )
            else:
                errors.append(
                    f"action {action_name!r}: unrecognized angle expression "
                    f"{angle_str!r} in parametric template."
                )


def _parse_gate_from_effect(
    effect_str: str,
    errors: list[str] | None = None,
    action_name: str = "",
    angle_context: dict[str, float] | None = None,
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

    # CCX / CCNOT / Toffoli / CCZ — two controls + one target (last argument)
    m = re.search(
        r"(CCX|CCNOT|Toffoli|CCZ)\(\s*\w+\[(\d+)\]\s*,\s*\w+\[(\d+)\]\s*,\s*\w+\[(\d+)\]\s*\)",
        effect_str,
        re.IGNORECASE,
    )
    if m:
        name = m.group(1).upper()
        c0, c1, tgt = int(m.group(2)), int(m.group(3)), int(m.group(4))
        kind = "CCZ" if name == "CCZ" else "CCNOT"
        return QuantumGate(kind=kind, targets=[tgt], controls=[c0, c1])

    # MCX / MCZ — variable arity (≥3 args), last argument is the target.
    m = re.search(
        r"(MCX|MCZ)\(\s*((?:\w+\[\d+\]\s*,\s*){2,}\w+\[\d+\])\s*\)",
        effect_str,
        re.IGNORECASE,
    )
    if m:
        kind = m.group(1).upper()
        indices = [int(x) for x in re.findall(r"\d+", m.group(2))]
        return QuantumGate(kind=kind, targets=[indices[-1]], controls=indices[:-1])

    # MCX/MCZ with too few args — promote to a structured parser error.
    # The happy-path regex above requires ≥3 qubit args; if we see the
    # keyword but don't match, the user almost certainly typed the wrong
    # arity (e.g. `MCX(qs[0], qs[1])`) rather than a completely unrelated
    # effect that happens to contain "MCX(".
    m_bad_mc = re.match(
        r"^(MCX|MCZ)\(\s*((?:\w+\[\d+\](?:\s*,\s*)?)*)\s*\)\s*$",
        effect_str,
        re.IGNORECASE,
    )
    if m_bad_mc:
        kind = m_bad_mc.group(1).upper()
        n_args = len(re.findall(r"\w+\[\d+\]", m_bad_mc.group(2)))
        if errors is not None:
            prefix = f"action {action_name!r}: " if action_name else ""
            alt = "CCX" if kind == "MCX" else "CCZ"
            errors.append(
                f"{prefix}{kind} requires at least 3 qubit arguments "
                f"(≥2 controls + 1 target), got {n_args}. Use {alt} for the 2-control case."
            )
        return None

    # CSWAP / Fredkin — 1 control + 2 swap targets.
    m = re.search(
        r"CSWAP\(\s*\w+\[(\d+)\]\s*,\s*\w+\[(\d+)\]\s*,\s*\w+\[(\d+)\]\s*\)",
        effect_str,
        re.IGNORECASE,
    )
    if m:
        ctrl, t1, t2 = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return QuantumGate(kind="CSWAP", targets=[t1, t2], controls=[ctrl])

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
            theta = _evaluate_angle(angle_str, angle_context)
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
            theta = _evaluate_angle(angle_str, angle_context)
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
    # Skip mid-circuit form 'measure(qs[N]) -> bits[M]' — that is handled separately.
    if re.search(r"measure\s*\(.*\)\s*->", effect_str, re.IGNORECASE):
        return None
    # 'M' is the conventional single-letter symbol for measurement in quantum circuits.
    m = re.search(r"(?:measure|M)\(\s*\w+\[([^\]]+)\]\s*\)", effect_str, re.IGNORECASE)
    if m:
        indices = [int(x.strip()) for x in m.group(1).split(",")]
        return Measurement(qubits=indices, basis="computational")
    return None


def _parse_mid_circuit_measure_from_effect(effect_str: str) -> Optional[QEffectMeasure]:
    """Parse 'measure(qs[N]) -> bits[M]' into QEffectMeasure(qubit_idx=N, bit_idx=M)."""
    if not effect_str:
        return None
    m = re.search(
        r"measure\s*\(\s*\w+\[(\d+)\]\s*\)\s*->\s*bits\[(\d+)\]",
        effect_str, re.IGNORECASE,
    )
    if m:
        return QEffectMeasure(qubit_idx=int(m.group(1)), bit_idx=int(m.group(2)))
    return None


def _parse_conditional_gate_from_effect(
    effect_str: str,
    errors: list[str] | None = None,
    action_name: str = "",
    angle_context: dict[str, float] | None = None,
) -> Optional[QEffectConditional]:
    """Parse 'if bits[M] == val: Gate(qs[K])' into QEffectConditional."""
    if not effect_str:
        return None
    m = re.match(
        r"if\s+bits\[(\d+)\]\s*==\s*(\d+)\s*:\s*(.+)$",
        effect_str.strip(), re.IGNORECASE,
    )
    if not m:
        return None
    bit_idx = int(m.group(1))
    value = int(m.group(2))
    gate_str = m.group(3).strip()
    gate = _parse_gate_from_effect(gate_str, errors=errors, action_name=action_name, angle_context=angle_context)
    if gate is None:
        return None
    return QEffectConditional(bit_idx=bit_idx, value=value, gate=gate)


# ============================================================
# Context-update parsing
# ============================================================

# A single mutation like:   iteration += 1   |   theta[0] -= eta
# Accepts an optional `ctx.` prefix for consistency with guard expressions
# (e.g., `ctx.iteration += 1`); the prefix is stripped before the name is
# stored on the AST.
_MUTATION_RE = re.compile(
    r"""
    ^\s*
    (?:ctx\.)?                                # optional `ctx.` prefix
    (?P<lhs>[A-Za-z_][A-Za-z0-9_]*)          # field name
    (?:\[\s*(?P<idx>-?\d+)\s*\])?             # optional [int] index
    \s*(?P<op>=|\+=|-=)\s*
    (?P<rhs>[^\s].*?)
    \s*$
    """,
    re.VERBOSE,
)

_INT_LITERAL_RE = re.compile(r"^-?\d+$")
_FLOAT_LITERAL_RE = re.compile(r"^-?\d+(\.\d+)?([eE][+-]?\d+)?$")


def _parse_single_mutation(
    mut_str: str,
    errors: list[str] | None,
    action_name: str,
) -> Optional[QContextMutation]:
    """Parse one `<lhs> <op> <rhs>` atom into a QContextMutation."""
    m = _MUTATION_RE.match(mut_str)
    if not m:
        if errors is not None:
            errors.append(
                f"action {action_name!r}: malformed context-update mutation {mut_str!r} "
                f"(expected `<field> = | += | -= <literal | field>`)."
            )
        return None

    target_field = m.group("lhs")
    idx_str = m.group("idx")
    target_idx: Optional[int] = None
    if idx_str is not None:
        try:
            target_idx = int(idx_str)
        except ValueError:
            if errors is not None:
                errors.append(
                    f"action {action_name!r}: non-integer list index in mutation {mut_str!r}."
                )
            return None
        if target_idx < 0:
            if errors is not None:
                errors.append(
                    f"action {action_name!r}: negative list index in mutation {mut_str!r}."
                )
            return None

    op = m.group("op")
    rhs = m.group("rhs").strip()

    rhs_literal: Optional[float] = None
    rhs_field: Optional[str] = None
    if _INT_LITERAL_RE.match(rhs):
        try:
            rhs_literal = int(rhs)
        except ValueError:
            if errors is not None:
                errors.append(
                    f"action {action_name!r}: unrecognized integer RHS {rhs!r} in mutation {mut_str!r}."
                )
            return None
    elif _FLOAT_LITERAL_RE.match(rhs):
        try:
            rhs_literal = float(rhs)
        except ValueError:
            if errors is not None:
                errors.append(
                    f"action {action_name!r}: unrecognized numeric RHS {rhs!r} in mutation {mut_str!r}."
                )
            return None
    elif re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", rhs):
        rhs_field = rhs
    else:
        if errors is not None:
            errors.append(
                f"action {action_name!r}: RHS {rhs!r} in mutation {mut_str!r} must be a "
                f"numeric literal or a bare context-field identifier."
            )
        return None

    return QContextMutation(
        target_field=target_field,
        target_idx=target_idx,
        op=op,
        rhs_literal=rhs_literal,
        rhs_field=rhs_field,
    )


def _parse_mutation_sequence(
    seq_str: str,
    errors: list[str] | None,
    action_name: str,
) -> list[QContextMutation]:
    """Parse `mut (; mut)*` into a list of QContextMutation."""
    mutations: list[QContextMutation] = []
    for piece in seq_str.split(";"):
        piece = piece.strip()
        if not piece:
            continue
        mut = _parse_single_mutation(piece, errors, action_name)
        if mut is not None:
            mutations.append(mut)
    return mutations


def _parse_context_update_from_effect(
    effect_str: str,
    errors: list[str] | None = None,
    action_name: str = "",
) -> Optional[QEffectContextUpdate]:
    """Parse a context-update effect string into a QEffectContextUpdate.

    Returns None if the effect does not match the context-update grammar,
    so the other effect parsers still get a chance. Emits structured
    errors only for forms that are clearly context-update intent but
    malformed.
    """
    if not effect_str:
        return None

    stripped = effect_str.strip()

    # Ignore the conditional-gate form: it starts with `if bits[...` but the
    # body is a gate call, not a mutation. We detect "context-update intent"
    # by the presence of `;` or a mutation operator (= / += / -=) somewhere
    # after the colon.
    cond_match = re.match(
        r"^if\s+bits\[(\d+)\]\s*==\s*([01])\s*:\s*(.*)$",
        stripped,
        re.IGNORECASE,
    )
    if cond_match:
        bit_idx = int(cond_match.group(1))
        bit_value = int(cond_match.group(2))
        body = cond_match.group(3).strip()
        then_part, else_part = _split_then_else(body)

        has_nested_if = bool(
            re.search(r"\bif\s+bits\[", then_part, re.IGNORECASE)
            or (else_part is not None and re.search(r"\bif\s+bits\[", else_part, re.IGNORECASE))
        )

        # If the body contains nested `if bits[...]`, decide whether the
        # innermost form is mutation-intent (context-update) or gate-intent
        # (nested conditional gates — also not supported, but handled
        # elsewhere). Look anywhere in the body for a mutation operator
        # (`=` / `+=` / `-=`, not `==`) on a field-like LHS; if present,
        # the user is writing a nested context-update.
        if has_nested_if:
            if re.search(r"[A-Za-z_]\w*(?:\[\s*-?\d+\s*\])?\s*(\+=|-=|(?<!=)=(?!=))", body):
                if errors is not None:
                    errors.append(
                        f"action {action_name!r}: nested `if bits[...]` conditions "
                        f"are not allowed in context-update effects (v1)."
                    )
                return None
            # Non-mutation nested case: let the conditional-gate parser try.
            return None

        # Only treat as context-update if the then branch looks like a
        # mutation (has an assignment op). Otherwise let the conditional-gate
        # parser handle it.
        if not _looks_like_mutation_sequence(then_part):
            return None

        then_muts = _parse_mutation_sequence(then_part, errors, action_name)
        else_muts: list[QContextMutation] = []
        if else_part is not None:
            else_muts = _parse_mutation_sequence(else_part, errors, action_name)

        if not then_muts:
            return None

        return QEffectContextUpdate(
            bit_idx=bit_idx,
            bit_value=bit_value,
            then_mutations=then_muts,
            else_mutations=else_muts,
            raw=stripped,
        )

    # Unconditional single-or-sequence form.
    if _looks_like_mutation_sequence(stripped):
        muts = _parse_mutation_sequence(stripped, errors, action_name)
        if not muts:
            return None
        return QEffectContextUpdate(
            bit_idx=None,
            bit_value=None,
            then_mutations=muts,
            else_mutations=[],
            raw=stripped,
        )

    return None


def _looks_like_mutation_sequence(text: str) -> bool:
    """Heuristic: text begins with `<ident>([<int>])? <op>` where op is =/+=/-=.

    The op must not be `==` (that's a comparison, used in bit conditions).
    """
    if not text:
        return False
    m = re.match(
        r"^\s*(?:ctx\.)?[A-Za-z_][A-Za-z0-9_]*(?:\[\s*-?\d+\s*\])?\s*(=(?!=)|\+=|-=)",
        text,
    )
    return m is not None


# Any `<ident>([<int>])? (= | += | -=)` occurring at the start of a
# segment (beginning of the string or after a `;`) — used to detect
# mixed gate/context-update effects like `H(qs[0]); iteration += 1`.
_MUTATION_OP_PAT = re.compile(
    r"(?:^|;)\s*(?:ctx\.)?[A-Za-z_][A-Za-z0-9_]*(?:\[\s*-?\d+\s*\])?\s*(=(?!=)|\+=|-=)"
)


def _contains_mutation_segment(effect_str: str) -> bool:
    """True if any `;`-separated segment of `effect_str` starts with a
    mutation op (`=`, `+=`, `-=`).

    Used to catch `gate; mutation` combinations that the context-update
    parser rejected as a whole but that still indicate mixed intent.
    The match is anchored at segment boundaries, so substrings like
    `==` inside a gate-call argument don't trigger.
    """
    return _MUTATION_OP_PAT.search(effect_str) is not None


def _split_then_else(body: str) -> tuple[str, Optional[str]]:
    """Split a context-update body on a top-level `else:` keyword.

    Only splits on `else:` that appears between semicolon-separated
    mutations — otherwise we'd mis-split on an `else` inside some other
    construct. For v1 (no nesting), a simple `else:` token search is
    sufficient.
    """
    # Look for `else:` with word boundaries; take the first match.
    m = re.search(r"\belse\s*:\s*", body)
    if not m:
        return body.strip(), None
    then_part = body[:m.start()].strip().rstrip(";").strip()
    else_part = body[m.end():].strip()
    return then_part, else_part
