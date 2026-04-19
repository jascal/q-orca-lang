## ADDED Requirements

### Requirement: Context-Update Annotation Emission

Each of the three compiler backends (QASM, Qiskit, Mermaid) SHALL
recognize `QEffectContextUpdate` effects and emit them as structured
annotations rather than executable circuit elements. The shot-to-shot
execution of the mutation is out of scope for this change — the
annotation preserves the information in the compiled artifact for
downstream tooling.

Annotation conventions:

- **QASM**: a trailing comment on its own line where the action's
  circuit element would otherwise appear, formatted as
  `// context_update: <original_effect_string>`.
- **Qiskit**: a Python comment at the corresponding location,
  formatted as `# context_update: <original_effect_string>`.
- **Mermaid**: the action label appears on the transition arrow as
  for any other action; no special rendering.

Compilers SHALL also emit a single file-level banner when at least
one context-update action is present, indicating that the compiled
artifact contains context-update annotations that are not executed
in v1:

- QASM: `// NOTE: context-update actions are annotations only; shot-to-shot execution not yet implemented.`
- Qiskit: Python comment with the same text.

#### Scenario: QASM emission of a context-update action

- **WHEN** a machine has an action with effect
  `if bits[0] == 1: theta[0] -= eta else: theta[0] += eta` compiled to QASM
- **THEN** the output includes a line
  `// context_update: if bits[0] == 1: theta[0] -= eta else: theta[0] += eta`
  at the position where the action's gates would otherwise be
  emitted, AND the output includes the file-level banner noting
  non-execution

#### Scenario: Qiskit script with no context-update actions

- **WHEN** a machine has only gate and measurement actions (no
  context-update)
- **THEN** the compiled Qiskit script SHALL NOT contain the
  file-level non-execution banner

#### Scenario: Mermaid diagram with context-update actions

- **WHEN** a machine has a transition whose action is
  `gradient_step` (a context-update)
- **THEN** the Mermaid diagram shows a transition arrow labeled
  `gradient_step`, identical to how any other named action is
  rendered
