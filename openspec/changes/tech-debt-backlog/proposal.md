## Why

We keep turning up small issues during code review and QA triage that
aren't worth their own OpenSpec change — internal naming nits,
minor error-severity inconsistencies, leftover dead code, error
messages that could be clearer, and so on — but they also shouldn't
disappear into commit-message limbo.

## What Changes

- Create a rolling "backlog" change that collects these small items
  in one `tasks.md`, grouped by area.
- Items are added as they come up (from QA triage, self-review,
  user feedback). Once an item is fixed, its task is marked
  complete but **not** removed — the archive eventually preserves
  what was done.
- When an item grows enough to warrant its own proposal/design
  (behavior change, new requirement, cross-module impact), it is
  pulled out into a dedicated OpenSpec change and the backlog entry
  is marked with a pointer to that change.
- This change is intentionally long-lived: it stays open until it
  gets too big to manage, at which point we archive it as a
  snapshot and start a fresh one.

## Impact

- Affected specs: **none** — this is a process/backlog change, not a
  requirements change. No `specs/` deltas.
- Affected code: items land as small PRs referencing their task
  number in `tech-debt-backlog/tasks.md`.
