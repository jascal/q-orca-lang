#!/bin/zsh
# Q-Orca PR review run
# Runs twice daily (9:15am and 4:15pm), reviews open PRs not yet reviewed by Claude.

export HOME="/Users/allans"
export PATH="/Users/allans/.local/bin:/usr/local/bin:/usr/bin:/bin"
LOG_DIR="/Users/allans/code/q-orca-lang/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/pr-review-$(date +%Y-%m-%d).log"

PROMPT_SRC="/Users/allans/code/q-orca-lang/scripts/pr-review-prompt.txt"
PROMPT_TMP="/tmp/q-orca-pr-review-prompt.txt"
cp "$PROMPT_SRC" "$PROMPT_TMP"

echo "=== Q-Orca PR review run $(date) ===" >> "$LOG"

claude -p "$(cat "$PROMPT_TMP")" \
  --allowedTools "Bash,Read,Write,Edit,Glob,Grep,Agent" \
  --output-format text \
  >> "$LOG" 2>&1

echo "=== Done $(date) ===" >> "$LOG"
