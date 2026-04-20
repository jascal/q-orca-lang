## 1. Parser

- [ ] 1.1 Rename `_has_trailing_mutation` in
  `q_orca/parser/markdown_parser.py` to something that reflects
  what it actually detects (a mutation op appearing after a gate
  call within the same effect string). Current name reads like
  "this effect ends with a mutation" which is misleading.
  (Source: Hermes QA on PR #21, low severity.)

## 2. Verifier / backend adapters

- [ ] 2.1 Audit CUDA-Q backend error reporting for `severity` /
  `valid` field consistency. Hermes flagged cases where a result
  could carry `severity="error"` alongside `valid=True`, or the
  inverse. Confirm the convention (error severity must mean
  `valid=False`) and fix any drift.
  (Source: Hermes QA on PR #21, low severity.)

## 3. How to use this file

- [ ] 3.1 **Meta**: when an item is fixed, leave the task checked
  rather than deleting it — the archived copy of this change is
  our record. If an item grows beyond "small," spin it out into
  a dedicated OpenSpec change and replace the task body with a
  pointer (e.g. "→ spun out as `add-xyz`").
