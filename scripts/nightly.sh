#!/bin/zsh
# Q-Orca nightly development run
# Runs at 2:07am, implements next pending OpenSpec change, opens PR for review.

export HOME="/Users/allans"
export PATH="/Users/allans/.local/bin:/usr/local/bin:/usr/bin:/bin"
LOG_DIR="/Users/allans/code/q-orca-lang/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/nightly-$(date +%Y-%m-%d).log"

echo "=== Q-Orca nightly run $(date) ===" >> "$LOG"

\
  claude -p "$(cat /tmp/q-orca-nightly-prompt.txt)" \
    --allowedTools "Bash,Read,Write,Edit,Glob,Grep,Agent" \
    --output-format text \
    >> "$LOG" 2>&1

echo "=== Done $(date) ===" >> "$LOG"
