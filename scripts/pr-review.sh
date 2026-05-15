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

# Watchdog: kill the claude invocation if it exceeds the ceiling.
# Same pattern as nightly.sh — a hung tool call can't block all
# future scheduled runs. Typical PR review run ≤ 5 min.
TIMEOUT_SECONDS=1200  # 20 min ceiling.

claude -p "$(cat "$PROMPT_TMP")" \
  --allowedTools "Bash,Read,Write,Edit,Glob,Grep,Agent" \
  --output-format text \
  >> "$LOG" 2>&1 &
CLAUDE_PID=$!

(
  sleep $TIMEOUT_SECONDS
  if kill -0 $CLAUDE_PID 2>/dev/null; then
    echo "=== WATCHDOG: claude exceeded ${TIMEOUT_SECONDS}s; killing PID $CLAUDE_PID ===" >> "$LOG"
    kill -9 $CLAUDE_PID 2>/dev/null
    pkill -9 -P $CLAUDE_PID 2>/dev/null
  fi
) &
WATCHDOG_PID=$!

wait $CLAUDE_PID
EXIT_CODE=$?
# Cancel watchdog: kill its `sleep` child first (else it orphans
# and holds file descriptors), then the subshell.
pkill -P $WATCHDOG_PID 2>/dev/null
kill $WATCHDOG_PID 2>/dev/null

echo "=== Done $(date) (exit $EXIT_CODE) ===" >> "$LOG"
