## ADDED Requirements

### Requirement: Bounded Loop Annotation

The parser SHALL recognize a `[loop <expr>]` or `[loop until: <predicate>]` annotation on a `## state` heading, filling the reserved `[loop …]` grammar slot, and SHALL attach a `QLoopAnnotation` (kind `fixed` or `adaptive`) to that state.

For `[loop <expr>]` (fixed), `<expr>` is a numeric literal, a context-field reference, or a closed-form expression over context fields and the standard math functions (`sqrt`, `ceil`, `floor`, `pi`), parsed by the existing classical-context expression parser and evaluated once at compile time to a fixed integer bound. For `[loop until: <predicate>]` (adaptive), `<predicate>` is a classical-context boolean expression (it may reference context fields and call a `## actions` function whose return type is `bool`). The annotation composes with `[initial]`/`[final]` on the same heading. A state with no `[loop …]` annotation behaves exactly as before this change.

The parser SHALL recognize two Action-column tags: `loop_done` (the transition that exits the loop) and `loop_back` (the back-edge that re-enters the body), each settable alongside a real action name (e.g. `measure_all, loop_done`), recorded as `loop_done` / `loop_back` flags on the `QTransition`.

#### Scenario: Fixed-count loop annotation parses

- **WHEN** a heading is `## state |amplified> [loop ceil(pi/4 * sqrt(N))]`
- **THEN** the state carries a `QLoopAnnotation` of kind `fixed` whose bound expression is `ceil(pi/4 * sqrt(N))`

#### Scenario: Adaptive loop annotation parses

- **WHEN** a heading is `## state |collected> [loop until: rank >= n - 1]`
- **THEN** the state carries a `QLoopAnnotation` of kind `adaptive` whose predicate is `rank >= n - 1`

#### Scenario: Loop transition tags recognized

- **WHEN** a transition's Action cell is `measure_all, loop_done` and another is `identity, loop_back`
- **THEN** the first transition has `loop_done = True` (with action `measure_all`) and the second has `loop_back = True`

#### Scenario: Unannotated state is unchanged

- **WHEN** a state heading carries no `[loop …]` annotation
- **THEN** its `QLoopAnnotation` is absent and the machine parses and compiles identically to before this change
