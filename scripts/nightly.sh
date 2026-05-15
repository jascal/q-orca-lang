#!/bin/zsh
# Q-Orca nightly development run
# Runs at 2:07am, implements next pending OpenSpec change, opens PR for review.

export HOME="/Users/allans"
export PATH="/Users/allans/.local/bin:/usr/local/bin:/usr/bin:/bin"
LOG_DIR="/Users/allans/code/q-orca-lang/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/nightly-$(date +%Y-%m-%d).log"

PROMPT_SRC="/Users/allans/code/q-orca-lang/scripts/nightly-prompt.txt"
PROMPT_TMP="/tmp/q-orca-nightly-prompt.txt"
cp "$PROMPT_SRC" "$PROMPT_TMP"

echo "=== Q-Orca nightly run $(date) ===" >> "$LOG"

# Watchdog: kill the claude invocation after TIMEOUT_SECONDS so a hung
# tool call can't block all future scheduled runs (see logs/nightly-
# 2026-05-11.log — that one stuck for 4 days). macOS doesn't ship
# `timeout`, so we use a background sleep + kill pattern.
TIMEOUT_SECONDS=2400  # 40 min ceiling; typical run ≤ 10 min.

claude -p "$(cat "$PROMPT_TMP")" \
  --model claude-opus-4-7 \
  --allowedTools "Bash,Read,Write,Edit,Glob,Grep,Agent" \
  --output-format text \
  >> "$LOG" 2>&1 &
CLAUDE_PID=$!

(
  sleep $TIMEOUT_SECONDS
  if kill -0 $CLAUDE_PID 2>/dev/null; then
    echo "=== WATCHDOG: claude exceeded ${TIMEOUT_SECONDS}s; killing PID $CLAUDE_PID ===" >> "$LOG"
    kill -9 $CLAUDE_PID 2>/dev/null
    # Also kill any orphaned children (subshells, gh, pytest, etc.)
    pkill -9 -P $CLAUDE_PID 2>/dev/null
  fi
) &
WATCHDOG_PID=$!

wait $CLAUDE_PID
EXIT_CODE=$?
# Cancel watchdog. Kill children first (the `sleep` inside the
# subshell) so it doesn't outlive the script as an orphan holding
# file descriptors. Then kill the watchdog subshell itself.
pkill -P $WATCHDOG_PID 2>/dev/null
kill $WATCHDOG_PID 2>/dev/null

echo "=== Done $(date) (exit $EXIT_CODE) ===" >> "$LOG"
