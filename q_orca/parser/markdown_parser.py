"""Q-Orca Markdown Parser — two-phase: structural markdown -> quantum-semantic AST."""

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

from q_orca.angle import evaluate_angle as _evaluate_angle
from q_orca.effect_parser import parse_effect_string as _shared_parse_effect_string

from q_orca.ast import (
    QMachineDef, QOrcaFile, QParseResult, ContextField, EventDef, QStateDef,
    QTransition, QGuardDef, QActionSignature, QEffectDef, VerificationRule, Invariant,
    QType, QTypeQubit, QTypeList, QTypeScalar, QTypeOptional, QTypeCustom,
    QGuardRef, QuantumGate, Measurement, CollapseOutcome,
    QGuardTrue, QGuardFalse, QGuardCompare, QGuardProbability, QGuardFidelity,
    VariableRef, ValueRef, QEffectMeasure, QEffectConditional,
    QContextMutation, QEffectContextUpdate,
    ActionParameter, BoundArg,
    EncodingDecl, ThetaBlock, ThetaRow,
    Span, QubitSlice, QAssertion, AssertionPolicy,
    QInvoke, QReturnDef,
)
from q_orca.verifier.quantum import KNOWN_UNITARY_GATES


# Marker substring shared by every variable-arity gate-call arity error
# (MCX/MCZ/CSWAP). The "looks-like-gate" warning suppresses itself when an
# error containing this marker is already present, so a future rephrase of
# the arity messages must keep this substring (or update the marker here).
_ARITY_ERROR_MARKER = "requires at least"


def _format_known_gate_list() -> str:
    """Build the human-readable known-gate string for the typo warning.

    Sourced from `KNOWN_UNITARY_GATES` so the warning stays in sync as the
    gate set grows. Common parser-side aliases (Hadamard for H, CCX for
    CCNOT) are appended explicitly because they're accepted at parse time
    but aren't canonical kinds.
    """
    aliases = {"H": "H/Hadamard", "CCNOT": "CCNOT/CCX"}
    return ", ".join(
        aliases.get(name, name) for name in sorted(KNOWN_UNITARY_GATES)
    )


_KNOWN_GATE_LIST = _format_known_gate_list()


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
    "verification rules", "invariants", "encoding", "theta",
    "assertion policy", "returns",
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
            _validate_returns_statistics(machine, errors)
            machines.append(machine)

    return QParseResult(file=QOrcaFile(machines=machines), errors=errors)


def _machine_has_measurement(machine: QMachineDef) -> bool:
    """True if any action carries a (mid-circuit or terminal) measurement effect."""
    return any(
        a.measurement is not None or a.mid_circuit_measure is not None
        for a in machine.actions
    )


def _validate_returns_statistics(machine: QMachineDef, errors: list[str]) -> None:
    """`Statistics` cells are only valid on a measurement-bearing machine."""
    with_stats = [r.name for r in machine.returns if r.statistics]
    if with_stats and not _machine_has_measurement(machine):
        errors.append(
            f"statistics_on_non_measurement_machine: returns {with_stats} on "
            f"machine '{machine.name}' declare statistics, but the machine has "
            f"no measurement effect"
        )


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
    resource_metrics: list[str] = []
    encoding: Optional[EncodingDecl] = None
    theta: Optional[ThetaBlock] = None
    assertion_policy = AssertionPolicy()
    returns: list[QReturnDef] = []

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
                state, next_i = _parse_state_heading(section_full, elements, i, errors)
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
                    invariants = _parse_invariants(elements[i], errors)
                    i += 1
                continue

            if section_name_lower == "resources":
                i += 1
                if i < len(elements) and isinstance(elements[i], MdTable):
                    resource_metrics = _parse_resources_table(elements[i], errors)
                    i += 1
                continue

            if section_name_lower == "encoding":
                i += 1
                if i < len(elements) and isinstance(elements[i], MdTable):
                    encoding = _parse_encoding_table(elements[i], errors)
                    i += 1
                continue

            if section_name_lower == "theta":
                i += 1
                if i < len(elements) and isinstance(elements[i], MdTable):
                    theta = _parse_theta_table(
                        elements[i], encoding, context, errors
                    )
                    i += 1
                continue

            if section_name_lower == "assertion policy":
                i += 1
                if i < len(elements) and isinstance(elements[i], MdTable):
                    assertion_policy = _parse_assertion_policy_table(elements[i], errors)
                    i += 1
                continue

            if section_name_lower == "returns":
                i += 1
                if i < len(elements) and isinstance(elements[i], MdTable):
                    returns = _parse_returns_table(elements[i], errors)
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
        resource_metrics=resource_metrics,
        encoding=encoding,
        theta=theta,
        assertion_policy=assertion_policy,
        returns=returns,
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


def _parse_state_heading(
    heading_text: str,
    elements: list[MdElement],
    current_index: int,
    errors: Optional[list[str]] = None,
) -> tuple[QStateDef, int]:
    # heading_text is like "state |00>" or "state |ψ> = (|00> + |11>)/√2"
    rest = heading_text[6:].strip()  # remove "state "
    heading_line = getattr(elements[current_index], "line", 0)

    is_initial = False
    is_final = False
    assertions: list[QAssertion] = []
    invoke: Optional[QInvoke] = None

    # Extract all bracketed annotation groups, e.g. `[initial]`,
    # `[final, assert: entangled(qs[0], qs[1])]`,
    # `[invoke: Child(a=b) shots=N]`. Bracket scanning is nesting-aware because
    # assertion/invoke payloads carry `qs[...]` / `(...)` subexpressions.
    # Multiple groups and multiple comma-separated tokens within a group are
    # conjunctive and order-independent (per the language spec).
    groups, rest = _extract_bracket_groups(rest)
    for group in groups:
        for token in _split_top_level_commas(group):
            tok = token.strip()
            low = tok.lower()
            if low == "initial":
                is_initial = True
            elif low == "final":
                is_final = True
            elif low.startswith("assert:"):
                payload = tok[tok.find(":") + 1:]
                assertions.extend(
                    _parse_assertion_payload(payload, heading_line, errors)
                )
            elif low.startswith("invoke:"):
                payload = tok[tok.find(":") + 1:]
                parsed = _parse_invoke_annotation(payload, heading_line, errors)
                if parsed is not None:
                    if invoke is not None:
                        if errors is not None:
                            errors.append(
                                f"invoke_duplicate: state at line {heading_line} "
                                f"declares more than one invoke: annotation"
                            )
                    else:
                        invoke = parsed
            # Other bracket tokens (queued `[loop …]`, `[send]`, `[receive]`)
            # are not yet recognized and are left untouched, not errored.

    if invoke is not None and (is_initial or is_final) and errors is not None:
        errors.append(
            f"invoke_with_initial_or_final: the invoke state at line "
            f"{heading_line} cannot also be [initial] or [final]"
        )

    # Parse name and optional expression from the de-annotated remainder
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

    # A `returns:` body line binds the child's returns into parent fields; it
    # only has meaning on an invoke state.
    if description and invoke is not None:
        invoke.return_bindings = _parse_return_bindings(description, heading_line, errors)

    return (
        QStateDef(
            name=state_name,
            display_name=ket_to_identifier(state_name),
            description=description,
            state_expression=state_expression,
            is_initial=is_initial,
            is_final=is_final,
            assertions=assertions,
            invoke=invoke,
        ),
        next_index,
    )


_RETURN_STATISTICS_VOCAB = frozenset({"expectation", "histogram", "variance"})

# `Child(arg=expr, ...)` with an optional trailing `shots=N`.
_INVOKE_RE = re.compile(
    r"^\s*([A-Za-z_]\w*)\s*\(([^)]*)\)\s*(?:shots\s*=\s*(-?\d+)\s*)?$"
)


def _parse_invoke_annotation(
    payload: str, heading_line: int, errors: Optional[list[str]]
) -> Optional[QInvoke]:
    """Parse `Child(param=expr, …) [shots=N]` (the text after `invoke:`).

    Returns a `QInvoke` (return bindings filled in later from the state body),
    or `None` on a malformed annotation or an out-of-range `shots`.
    """
    m = _INVOKE_RE.match(payload)
    if not m:
        if errors is not None:
            errors.append(
                f"invoke_malformed: '{payload.strip()}' at line {heading_line} "
                f"is not of the form Child(param=expr, …) [shots=N]"
            )
        return None

    child = m.group(1)
    shots: Optional[int] = None
    if m.group(3) is not None:
        shots = int(m.group(3))
        if shots < 1:
            if errors is not None:
                errors.append(
                    f"invoke_shots_invalid: shots must be at least 1 (got "
                    f"{shots}) at line {heading_line}"
                )
            return None

    arg_bindings: dict[str, str] = {}
    args_str = m.group(2).strip()
    if args_str:
        for binding in _split_top_level_commas(args_str):
            if "=" not in binding:
                if errors is not None:
                    errors.append(
                        f"invoke_arg_malformed: '{binding}' in {child}(…) at line "
                        f"{heading_line} must be of the form param=expr"
                    )
                continue
            param, expr = binding.split("=", 1)
            arg_bindings[param.strip()] = expr.strip()

    return QInvoke(child_name=child, arg_bindings=arg_bindings, shots=shots)


def _parse_return_bindings(
    description: str, heading_line: int, errors: Optional[list[str]]
) -> dict[str, str]:
    """Extract `returns: parent=child, …` from an invoke state's body."""
    m = re.search(r"returns:\s*([^\n]*)", description)
    if not m:
        return {}
    bindings: dict[str, str] = {}
    for binding in _split_top_level_commas(m.group(1).strip()):
        if not binding:
            continue
        if "=" not in binding:
            if errors is not None:
                errors.append(
                    f"invoke_return_malformed: '{binding}' in the returns: line "
                    f"at line {heading_line} must be of the form parent=child"
                )
            continue
        parent, child = binding.split("=", 1)
        bindings[parent.strip()] = child.strip()
    return bindings


# Recognized `[assert: …]` category names → expected qubit-target arity.
_ASSERTION_CATEGORIES = {
    "classical": "slice",       # one slice (single qubit or range)
    "superposition": "slice",   # one slice
    "entangled": "pair",        # two single qubits
    "separable": "pair",        # two single qubits
}


def _extract_bracket_groups(text: str) -> tuple[list[str], str]:
    """Split off top-level `[…]` annotation groups from a state heading.

    Returns `(groups, remainder)` where `groups` are the contents of each
    top-level bracket pair (brackets stripped) and `remainder` is the heading
    text with those groups removed (the state name / expression). Scanning is
    nesting-aware so an assertion payload's inner `qs[a..b]` subscripts do not
    terminate the enclosing annotation group. Unbalanced `]` are treated as
    literal remainder characters.
    """
    groups: list[str] = []
    remainder: list[str] = []
    buf: list[str] = []
    depth = 0
    for ch in text:
        if ch == "[":
            if depth == 0:
                buf = []
            else:
                buf.append(ch)
            depth += 1
        elif ch == "]":
            if depth == 0:
                remainder.append(ch)  # stray ] — keep as literal
            else:
                depth -= 1
                if depth == 0:
                    groups.append("".join(buf))
                else:
                    buf.append(ch)
        else:
            (buf if depth > 0 else remainder).append(ch)
    return groups, "".join(remainder).strip()


def _parse_qubit_slice(text: str) -> Optional[QubitSlice]:
    """Parse `qs[k]` → `QubitSlice(k)` or `qs[a..b]` → `QubitSlice(a, b)`.

    Returns `None` for any malformed form (missing `qs[…]` shape, non-integer
    index, or a descending range `b < a`).
    """
    m = re.match(r"^qs\[\s*(\d+)\s*(?:\.\.\s*(\d+)\s*)?\]$", text.strip())
    if not m:
        return None
    start = int(m.group(1))
    end = int(m.group(2)) if m.group(2) is not None else None
    if end is not None and end < start:
        return None
    return QubitSlice(start=start, end=end)


def _parse_assertion_payload(
    payload: str,
    heading_line: int = 0,
    errors: Optional[list[str]] = None,
) -> list[QAssertion]:
    """Parse the text after `assert:` into a list of `QAssertion`.

    Multiple category expressions are separated by `;` and returned in
    declaration order. Unrecognized categories and malformed targets append
    structured parser errors and are skipped.
    """
    assertions: list[QAssertion] = []
    for expr in payload.split(";"):
        expr = expr.strip()
        if not expr:
            continue
        parsed = _parse_assertion_expression(expr, heading_line, errors)
        if parsed is not None:
            assertions.append(parsed)
    return assertions


def _parse_assertion_expression(
    expr: str,
    heading_line: int,
    errors: Optional[list[str]],
) -> Optional[QAssertion]:
    m = re.match(r"^([A-Za-z_]\w*)\s*\((.*)\)$", expr)
    if not m:
        if errors is not None:
            errors.append(
                f"malformed_assertion: '{expr}' is not of the form "
                f"category(qs[…]) at line {heading_line}"
            )
        return None
    category = m.group(1).lower()
    arity = _ASSERTION_CATEGORIES.get(category)
    if arity is None:
        if errors is not None:
            errors.append(
                f"unknown_assertion_category: '{m.group(1)}' at line "
                f"{heading_line} is not one of "
                f"{', '.join(sorted(_ASSERTION_CATEGORIES))}"
            )
        return None

    arg_strs = [a for a in _split_top_level_commas(m.group(2)) if a]
    targets: list[QubitSlice] = []
    for arg in arg_strs:
        sl = _parse_qubit_slice(arg)
        if sl is None:
            if errors is not None:
                errors.append(
                    f"invalid_assertion_target: '{arg}' in {category}(…) at "
                    f"line {heading_line} is not a valid qs[k] or qs[a..b] slice"
                )
            return None
        targets.append(sl)

    if arity == "slice" and len(targets) != 1:
        if errors is not None:
            errors.append(
                f"invalid_assertion_target: {category}(…) at line "
                f"{heading_line} takes exactly one qubit slice, got {len(targets)}"
            )
        return None
    if arity == "pair":
        if len(targets) != 2 or not all(t.is_single for t in targets):
            if errors is not None:
                errors.append(
                    f"invalid_assertion_target: {category}(…) at line "
                    f"{heading_line} takes exactly two single qubits "
                    f"qs[i], qs[j]"
                )
            return None

    return QAssertion(
        category=category,
        targets=targets,
        source_span=Span(line=heading_line, text=expr),
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
    r"^([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)\s*$"
)


def _split_top_level_commas(s: str) -> list[str]:
    """Split a comma-separated argument list, ignoring commas inside parens.

    `_evaluate_angle` only accepts single-arg expressions today, but a
    multi-arg angle expression like `mix(atan2(a, b), 0)` would be
    mis-split by a naive `s.split(",")`. This helper tracks parenthesis
    depth so commas inside nested calls don't count as argument
    separators. Square brackets are tracked too for `qs[i, j]`-style
    subscripts.
    """
    args: list[str] = []
    depth = 0
    start = 0
    for i, ch in enumerate(s):
        if ch in "([":
            depth += 1
        elif ch in ")]":
            if depth > 0:
                depth -= 1
        elif ch == "," and depth == 0:
            args.append(s[start:i].strip())
            start = i + 1
    tail = s[start:].strip()
    if args or tail:
        args.append(tail)
    return args


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
                _split_top_level_commas(args_str) if args_str else []
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
            # Bare-name reference; verify the name resolves to a declared
            # action and doesn't skip required parametric arguments.
            sig = actions_by_name.get(raw)
            if sig is None:
                if errors is not None:
                    errors.append(
                        f"{transition_ref}: bare-name action {raw!r} is not "
                        f"declared in the actions table."
                    )
            elif sig.parameters:
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
            and not any(_ARITY_ERROR_MARKER in e for e in errors)
        ):
            errors.append(
                f"action {name!r}: effect {effect_str!r} looks like a gate call "
                "but does not match any known gate. Check the gate name for typos "
                f"(known gates: {_KNOWN_GATE_LIST})."
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
    known_kinds = [
        "unitarity",
        "entanglement",
        "completeness",
        "no_cloning",
        "measurement_collapse_allowed",
        "state_assertions",
    ]

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


def _parse_assertion_policy_table(
    table: MdTable, errors: Optional[list[str]] = None
) -> AssertionPolicy:
    """Parse a `## assertion policy` table into an `AssertionPolicy`.

    Accepts a 2- or 3-column table (`Setting | Value | Notes?`); the optional
    notes column is read and discarded. Recognized settings are
    `shots_per_assert`, `confidence`, `on_failure`, and `backend`; unknown
    settings and out-of-range values append structured parser errors and are
    skipped, leaving that setting at its default.
    """
    policy = AssertionPolicy()
    setting_idx = _find_column_index(table.headers, "setting")
    value_idx = _find_column_index(table.headers, "value")
    if setting_idx < 0 or value_idx < 0:
        if errors is not None:
            errors.append(
                "assertion_policy_value_error: `## assertion policy` table must "
                "have `Setting` and `Value` columns"
            )
        return policy

    for row in table.rows:
        if setting_idx >= len(row) or value_idx >= len(row):
            continue
        setting = _strip_backticks(row[setting_idx].strip()).strip().lower()
        value = _strip_backticks(row[value_idx].strip()).strip()
        if not setting:
            continue

        if setting == "shots_per_assert":
            try:
                shots = int(value)
            except ValueError:
                _policy_value_error(errors, setting, value, "an integer >= 1")
                continue
            if shots <= 0:
                _policy_value_error(errors, setting, value, "an integer >= 1")
                continue
            policy.shots_per_assert = shots
        elif setting == "confidence":
            try:
                conf = float(value)
            except ValueError:
                _policy_value_error(errors, setting, value, "a float in [0, 1]")
                continue
            if conf < 0.0 or conf > 1.0:
                _policy_value_error(errors, setting, value, "a float in [0, 1]")
                continue
            policy.confidence = conf
        elif setting == "on_failure":
            if value.lower() not in ("error", "warn"):
                _policy_value_error(errors, setting, value, "'error' or 'warn'")
                continue
            policy.on_failure = value.lower()
        elif setting == "backend":
            policy.backend = value
        else:
            if errors is not None:
                errors.append(
                    f"unknown_assertion_policy_setting: '{setting}' is not a "
                    f"recognized assertion-policy setting (expected one of "
                    f"shots_per_assert, confidence, on_failure, backend)"
                )

    return policy


def _policy_value_error(
    errors: Optional[list[str]], setting: str, value: str, expected: str
) -> None:
    if errors is not None:
        errors.append(
            f"assertion_policy_value_error: setting '{setting}' got '{value}'; "
            f"expected {expected}"
        )


def _parse_returns_table(
    table: MdTable, errors: Optional[list[str]] = None
) -> list[QReturnDef]:
    """Parse a `## returns` table into `QReturnDef`s.

    Columns: `Name`, `Type`, and optional `Statistics` (comma-separated from
    {expectation, histogram, variance}). Unknown statistic values append a
    structured error and are dropped.
    """
    returns: list[QReturnDef] = []
    name_idx = _find_column_index(table.headers, "name")
    type_idx = _find_column_index(table.headers, "type")
    stats_idx = _find_column_index(table.headers, "statistics")

    for row in table.rows:
        name = _strip_backticks(row[name_idx].strip()).strip() if 0 <= name_idx < len(row) else ""
        if not name:
            continue
        type_str = _strip_backticks(row[type_idx].strip()).strip() if 0 <= type_idx < len(row) else ""

        statistics: list[str] = []
        if 0 <= stats_idx < len(row):
            for raw in row[stats_idx].split(","):
                stat = _strip_backticks(raw.strip()).strip().lower()
                if not stat:
                    continue
                if stat not in _RETURN_STATISTICS_VOCAB:
                    if errors is not None:
                        errors.append(
                            f"invalid_return_statistic: '{stat}' for return "
                            f"'{name}' is not one of "
                            f"{', '.join(sorted(_RETURN_STATISTICS_VOCAB))}"
                        )
                    continue
                statistics.append(stat)

        returns.append(QReturnDef(
            name=name,
            type=_parse_q_type_string(type_str),
            statistics=statistics,
        ))

    return returns


_RESOURCE_METRIC_NAMES = ("gate_count", "depth", "cx_count", "t_count", "logical_qubits")


def _parse_invariants(list_el: MdBulletList, errors: list[str] | None = None) -> list[Invariant]:
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
            continue
        # resource invariants: gate_count|depth|cx_count|t_count|logical_qubits <op> <int>
        m = re.match(
            r"(gate_count|depth|cx_count|t_count|logical_qubits)\s*(>=|<=|==|=|<|>)\s*(\d+)\s*$",
            item,
        )
        if m:
            metric = m.group(1)
            op = _parse_comparison_op(m.group(2))
            value = float(m.group(3))
            invariants.append(Invariant(kind="resource", qubits=[], op=op, value=value, metric=metric))
            continue
        # decimal-valued resource invariants: concept_gram_tier_separation <op> <decimal in [0, 1]>
        m = re.match(
            r"concept_gram_tier_separation\s*(>=|<=|==|=|<|>)\s*([0-9]*\.?[0-9]+)\s*$",
            item,
        )
        if m:
            op = _parse_comparison_op(m.group(1))
            value = float(m.group(2))
            if value < 0.0 or value > 1.0:
                if errors is not None:
                    errors.append(
                        f"invariant_value_out_of_range: "
                        f"concept_gram_tier_separation value {value} "
                        f"is outside [0, 1]"
                    )
                continue
            invariants.append(Invariant(
                kind="resource", qubits=[], op=op,
                value=value, metric="concept_gram_tier_separation",
            ))
    return invariants


def _parse_resources_table(table: MdTable, errors: list[str] | None = None) -> list[str]:
    """Parse a `## resources` table into a list of metric names.

    Accepts a 2- or 3-column table whose first column is `Metric`.
    Unknown metric names append a structured `unknown_resource_metric`
    error referencing the offending row.
    """
    metric_idx = _find_column_index(table.headers, "metric")
    if metric_idx < 0:
        return []
    metrics: list[str] = []
    for row in table.rows:
        if metric_idx >= len(row):
            continue
        name = _strip_backticks(row[metric_idx]).strip()
        if not name:
            continue
        if name not in _RESOURCE_METRIC_NAMES:
            if errors is not None:
                errors.append(
                    f"unknown_resource_metric: '{name}' (expected one of "
                    f"{', '.join(_RESOURCE_METRIC_NAMES)})"
                )
            continue
        metrics.append(name)
    return metrics


_HEA_VALID_ROTATIONS = ("Rx", "Ry", "Rz")
_HEA_VALID_ENTANGLERS = ("ring", "chain")
_HEA_REQUIRED_KEYS = ("kind", "depth", "entangler", "rotations")
_HEA_OPTIONAL_KEYS = ("qubits",)
_HEA_KNOWN_KEYS = frozenset(_HEA_REQUIRED_KEYS + _HEA_OPTIONAL_KEYS)


def _parse_encoding_table(
    table: MdTable, errors: list[str] | None = None
) -> Optional[EncodingDecl]:
    """Parse a `## encoding` key/value table into an EncodingDecl.

    Errors are appended via the structured `encoding_*` prefix. On any
    error the function returns `None` so the machine's `encoding` field
    stays unset.
    """
    key_idx = _find_column_index(table.headers, "key")
    val_idx = _find_column_index(table.headers, "value")
    if key_idx < 0 or val_idx < 0:
        if errors is not None:
            errors.append(
                "encoding_table_columns: `## encoding` requires columns "
                "`key` and `value`"
            )
        return None

    raw: dict[str, str] = {}
    for row in table.rows:
        if key_idx >= len(row) or val_idx >= len(row):
            continue
        k = _strip_backticks(row[key_idx]).strip().lower()
        v = _strip_backticks(row[val_idx]).strip()
        if not k:
            continue
        if k not in _HEA_KNOWN_KEYS:
            if errors is not None:
                errors.append(
                    f"encoding_unknown_key: '{k}' (expected one of "
                    f"{', '.join(_HEA_KNOWN_KEYS)})"
                )
            return None
        raw[k] = v

    missing = [k for k in _HEA_REQUIRED_KEYS if k not in raw]
    if missing:
        if errors is not None:
            errors.append(
                f"encoding_missing_keys: {missing} (required: "
                f"{list(_HEA_REQUIRED_KEYS)})"
            )
        return None

    kind = raw["kind"].lower()
    if kind != "hea":
        if errors is not None:
            errors.append(
                f"encoding_unsupported_kind: '{raw['kind']}' "
                f"(only 'hea' is supported)"
            )
        return None

    try:
        depth = int(raw["depth"])
    except ValueError:
        if errors is not None:
            errors.append(
                f"encoding_bad_depth: '{raw['depth']}' is not an integer"
            )
        return None
    if depth < 1:
        if errors is not None:
            errors.append(
                f"encoding_bad_depth: depth must be a positive integer, "
                f"got {depth}"
            )
        return None

    entangler = raw["entangler"].lower()
    if entangler not in _HEA_VALID_ENTANGLERS:
        if errors is not None:
            errors.append(
                f"encoding_bad_entangler: '{raw['entangler']}' "
                f"(expected one of {list(_HEA_VALID_ENTANGLERS)})"
            )
        return None

    rotation_tokens = [
        tok.strip() for tok in raw["rotations"].split(",") if tok.strip()
    ]
    if not rotation_tokens:
        if errors is not None:
            errors.append(
                "encoding_bad_rotations: `rotations` must list at least "
                "one of Rx, Ry, Rz"
            )
        return None
    rotations: list[str] = []
    for tok in rotation_tokens:
        if tok not in _HEA_VALID_ROTATIONS:
            if errors is not None:
                errors.append(
                    f"encoding_bad_rotations: unsupported rotation "
                    f"'{tok}' (expected one of "
                    f"{list(_HEA_VALID_ROTATIONS)})"
                )
            return None
        if tok in rotations:
            if errors is not None:
                errors.append(
                    f"encoding_bad_rotations: duplicate rotation '{tok}'"
                )
            return None
        rotations.append(tok)

    qubits_field = raw.get("qubits") or None
    return EncodingDecl(
        kind="hea",
        depth=depth,
        entangler=entangler,
        rotations=tuple(rotations),
        qubits=qubits_field,
    )


def _resolve_register_size(
    encoding: EncodingDecl, context: list[ContextField]
) -> Optional[int]:
    """Find the size of the qubits register declared by `encoding`.

    The default value is a list literal like ``[q0, q1, q2]``; the
    register size is the count of comma-separated items inside the
    brackets after stripping whitespace. Qubit names are not
    constrained to the ``q\\d+`` shape — any non-empty identifier
    counts as one qubit, so registers like ``[qubit_a, qubit_b]``
    resolve correctly.

    Returns None if the field is absent or the default value isn't a
    bracketed list with at least one non-empty entry.
    """
    target = encoding.qubits or "qubits"
    for f in context:
        if f.name != target or not isinstance(f.type, QTypeList):
            continue
        if not f.default_value:
            continue
        body = f.default_value.strip()
        if body.startswith("[") and body.endswith("]"):
            body = body[1:-1]
        items = [tok.strip() for tok in body.split(",") if tok.strip()]
        if items:
            return len(items)
    return None


def _parse_theta_table(
    table: MdTable,
    encoding: Optional[EncodingDecl],
    context: list[ContextField],
    errors: list[str] | None = None,
) -> Optional[ThetaBlock]:
    """Parse a `## theta` table into a `ThetaBlock`.

    Each row maps a concept name to a rank-3 numpy tensor of shape
    `(|rotations|, depth, n)`. Errors are appended with `theta_*`
    prefix; on any structural failure the function returns `None`.
    """
    import ast as _py_ast

    import numpy as _np

    if encoding is None:
        if errors is not None:
            errors.append(
                "theta_no_encoding: `## theta` requires a preceding "
                "`## encoding` section"
            )
        return None

    n = _resolve_register_size(encoding, context)
    if n is None:
        if errors is not None:
            errors.append(
                f"theta_no_register: cannot resolve register "
                f"'{encoding.qubits or 'qubits'}' size from context"
            )
        return None

    expected_shape = (len(encoding.rotations), encoding.depth, n)

    concept_idx = _find_column_index(table.headers, "concept")
    tensor_idx = _find_column_index(table.headers, "tensor")
    cluster_idx = _find_column_index(table.headers, "cluster")
    if concept_idx < 0 or tensor_idx < 0:
        if errors is not None:
            errors.append(
                "theta_table_columns: `## theta` requires columns "
                "`concept` and `tensor`"
            )
        return None

    seen: dict[str, int] = {}
    rows: list[ThetaRow] = []
    for row_pos, row in enumerate(table.rows, start=1):
        if concept_idx >= len(row) or tensor_idx >= len(row):
            continue
        concept = _strip_backticks(row[concept_idx]).strip()
        tensor_src = row[tensor_idx].strip()
        if not concept:
            continue
        if concept in seen:
            if errors is not None:
                errors.append(
                    f"theta_duplicate_concept: '{concept}' "
                    f"(rows {seen[concept]} and {row_pos})"
                )
            return None
        seen[concept] = row_pos

        if cluster_idx >= 0:
            if cluster_idx >= len(row):
                if errors is not None:
                    errors.append(
                        f"theta_missing_cluster: concept '{concept}' "
                        f"row {row_pos} has no cluster cell"
                    )
                return None
            cluster = _strip_backticks(row[cluster_idx]).strip()
            if not cluster:
                if errors is not None:
                    errors.append(
                        f"theta_empty_cluster: concept '{concept}' "
                        f"row {row_pos} has an empty cluster value"
                    )
                return None
        else:
            cluster = "_default"

        try:
            literal = _py_ast.literal_eval(tensor_src)
        except (ValueError, SyntaxError) as exc:
            if errors is not None:
                errors.append(
                    f"theta_malformed_literal: concept '{concept}' "
                    f"row {row_pos}: {exc}"
                )
            return None
        try:
            tensor = _np.asarray(literal, dtype=float)
        except (TypeError, ValueError) as exc:
            if errors is not None:
                errors.append(
                    f"theta_non_numeric: concept '{concept}' row "
                    f"{row_pos}: {exc}"
                )
            return None
        if tensor.shape != expected_shape:
            if errors is not None:
                errors.append(
                    f"theta_shape_mismatch: concept '{concept}' has "
                    f"shape {tensor.shape}, expected {expected_shape}"
                )
            return None
        rows.append(ThetaRow(concept=concept, tensor=tensor, cluster=cluster))

    return ThetaBlock(rows=rows)


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
        # Extra slots without any `: type` annotation likely mean the user
        # intended parametric form but forgot the annotation. Surface the
        # mismatch here rather than letting downstream "action is not
        # parametric" errors confuse the diagnosis when a transition tries
        # to call e.g. `foo(0)`.
        if len(raw_params) > 1 and errors is not None:
            extras = ", ".join(repr(s) for s in raw_params[1:])
            errors.append(
                f"action {action_name!r}: extra parameter slot(s) {extras} "
                f"missing `: type` annotation (e.g. `(qs, c: int) -> qs` "
                f"for int-parametric actions; supported types: int, angle)."
            )
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

    Underscores are accepted in the leading identifier so typos like
    `U_3(qs[0], ...)` (for `U3`) still trigger the warning.
    """
    return bool(re.match(r"^\s*[A-Za-z_][A-Za-z0-9_]*\s*\(\s*\w+\[", effect_str.strip()))


# Rotation-gate shapes that accept a symbolic angle in the last argument
# slot. Used by the parametric-template validator to route angle checks.
# The shape is fixed at 1–2 qubit slots before the angle (one for Rx/Ry/Rz,
# two for CRx/CRy/CRz/RXX/RYY/RZZ). A future hypothetical multi-controlled
# rotation (e.g. `MCRx(qs[0], qs[1], qs[2], theta)`) would not match here and
# must either extend this regex or land with its own template-time validation
# path; missing the match silently skips the angle-binding check.
#
# The angle slot accepts one level of nested parens so inverse-form linear
# combinations like ``Ry(qs[k], -(a + b))`` (spec'd in
# ``fix-mps-encoding-non-factorizing``) capture the full ``-(a + b)``
# expression rather than truncating at the inner ``)``. Deeper nesting is
# not currently required by any shipped example.
_ROTATION_GATE_ANGLE_RE = re.compile(
    r"(?P<name>CRx|CRy|CRz|RXX|RYY|RZZ|Rx|Ry|Rz)"
    r"\(\s*\w+\[[^\]]+\]\s*"
    r"(?:,\s*\w+\[[^\]]+\]\s*)?"
    r",\s*(?P<angle>(?:[^()]|\([^()]*\))+)\)",
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
    """Extract the *primary* gate of an action's effect for the AST.

    The AST stores one ``QuantumGate`` per action; the compiler re-parses
    the full effect string to get the complete gate sequence at compile
    time. For multi-gate effects (``H(qs[0]); CNOT(qs[0], qs[1])``),
    we surface the first parsable gate as the primary annotation.
    """
    if not effect_str:
        return None
    gates = _shared_parse_effect_string(
        effect_str,
        angle_context=angle_context,
        errors=errors,
        action_name=action_name,
    )
    if not gates:
        return None
    parsed = gates[0]
    # Measurement effects (`measure(qs[i])`, `M(qs[i])`) are stored on
    # `action.measurement`, not `action.gate`. The shared parser exposes
    # them as a custom-gate fallback; the adapter drops that here so the
    # static unitarity check doesn't see them as unverified custom gates.
    if parsed.name == "custom" and (parsed.custom_name or "").upper() in {"MEASURE", "M"}:
        return None
    return QuantumGate(
        kind=parsed.name,
        targets=list(parsed.targets),
        controls=list(parsed.controls) if parsed.controls else None,
        parameter=parsed.parameter,
        custom_name=parsed.custom_name,
    )


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


_CONDITIONAL_HEAD_RE = re.compile(
    r"if\s+bits\[(\d+)\]\s*==\s*(\d+)", re.IGNORECASE,
)
_CONDITIONAL_AND_RE = re.compile(
    r"\s+and\s+bits\[(\d+)\]\s*==\s*(\d+)", re.IGNORECASE,
)


def _parse_conditional_gate_from_effect(
    effect_str: str,
    errors: list[str] | None = None,
    action_name: str = "",
    angle_context: dict[str, float] | None = None,
) -> Optional[QEffectConditional]:
    """Parse 'if bits[M] == val [and bits[N] == val ...]: Gate(...)'.

    The condition list is short-circuit AND across `(bit_idx, value)`
    clauses; the gate fires only when every clause holds.
    """
    if not effect_str:
        return None
    text = effect_str.strip()
    head = _CONDITIONAL_HEAD_RE.match(text)
    if not head:
        return None
    conditions: list[tuple[int, int]] = [(int(head.group(1)), int(head.group(2)))]
    pos = head.end()
    while True:
        tail = _CONDITIONAL_AND_RE.match(text, pos)
        if not tail:
            break
        conditions.append((int(tail.group(1)), int(tail.group(2))))
        pos = tail.end()
    rest = text[pos:].lstrip()
    if not rest.startswith(":"):
        return None
    gate_str = rest[1:].strip()

    seen: dict[int, int] = {}
    for bit_idx, value in conditions:
        if bit_idx in seen and seen[bit_idx] != value:
            if errors is not None:
                errors.append(
                    f"action {action_name!r}: conditional gate has conflicting "
                    f"clauses for bits[{bit_idx}] (declared both =={seen[bit_idx]} "
                    f"and =={value}); the gate would never fire."
                )
            return None
        seen[bit_idx] = value

    gate = _parse_gate_from_effect(gate_str, errors=errors, action_name=action_name, angle_context=angle_context)
    if gate is None:
        return None
    head_bit, head_val = conditions[0]
    return QEffectConditional(
        bit_idx=head_bit, value=head_val, gate=gate, conditions=conditions
    )


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
