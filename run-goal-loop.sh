#!/usr/bin/env bash
# run-goal-loop.sh — drive the /goal prompt autonomously for a fixed wall-clock window.
# macOS + Linux. Keeps the machine awake, re-invokes Claude Code headlessly each iteration,
# checkpoints to git every pass, and runs a final end-to-end verification at the deadline.
#
# Usage:   ./run-goal-loop.sh
# Knobs (env):
#   GOAL_DURATION_SECONDS  total run length          (default 14400 = 4h)
#   GOAL_PROJECT_DIR       project root              (default: $PWD)
#   GOAL_PROMPT_FILE       the /goal prompt          (default: .claude/commands/goal.md)
#   GOAL_MODEL             pin a model               (optional, e.g. claude-opus-4-8)
#   GOAL_CLAUDE_BIN        claude executable         (default: claude)
#   GOAL_INTER_ITER_SLEEP  pause between iterations  (default 3s — just lets git/fs settle)
#   GOAL_MAX_BACKOFF       cap on error backoff      (default 60s)

set -uo pipefail   # NOT -e: the loop must survive a failing iteration.

DURATION="${GOAL_DURATION_SECONDS:-14400}"
PROJECT_DIR="${GOAL_PROJECT_DIR:-$PWD}"
PROMPT_FILE="${GOAL_PROMPT_FILE:-$PROJECT_DIR/.claude/commands/goal.md}"
CLAUDE_BIN="${GOAL_CLAUDE_BIN:-claude}"
INTER_ITER_SLEEP="${GOAL_INTER_ITER_SLEEP:-3}"
MAX_BACKOFF="${GOAL_MAX_BACKOFF:-60}"
MODEL_ARG=()
[ -n "${GOAL_MODEL:-}" ] && MODEL_ARG=(--model "$GOAL_MODEL")

# ── Keep the machine awake (best-effort background companion; NEVER fatal) ──────
# We do not exec into the inhibitor: on headless hosts with no session bus,
# systemd-inhibit dies immediately, and exec-ing into it would kill the loop.
NOSLEEP_PID=""
keep_awake() {
  if [ "$(uname)" = "Darwin" ] && command -v caffeinate >/dev/null 2>&1; then
    caffeinate -dimsu -w "$$" >/dev/null 2>&1 &   # awake for as long as this script lives
    NOSLEEP_PID=$!
    echo "[goal-loop] caffeinate holding system awake (pid $NOSLEEP_PID)."
  elif command -v systemd-inhibit >/dev/null 2>&1; then
    systemd-inhibit --what=idle:sleep:handle-lid-switch --who="goal-loop" \
      --why="autonomous build window" sleep "$DURATION" >/dev/null 2>&1 &
    NOSLEEP_PID=$!
    sleep 0.3
    if kill -0 "$NOSLEEP_PID" 2>/dev/null; then
      echo "[goal-loop] systemd-inhibit holding sleep/idle locks (pid $NOSLEEP_PID)."
    else
      NOSLEEP_PID=""
      echo "[goal-loop] note: systemd-inhibit unavailable here (no session bus) — relying on OS power settings."
    fi
  else
    echo "[goal-loop] note: no caffeinate/systemd-inhibit found — relying on OS power settings."
  fi
}

cd "$PROJECT_DIR" || { echo "[goal-loop] cannot cd to $PROJECT_DIR"; exit 1; }
[ -f "$PROMPT_FILE" ] || { echo "[goal-loop] prompt file not found: $PROMPT_FILE"; exit 1; }
command -v "$CLAUDE_BIN" >/dev/null 2>&1 || { echo "[goal-loop] '$CLAUDE_BIN' not on PATH"; exit 1; }
mkdir -p logs
[ -d .git ] || { git init -q && echo "[goal-loop] initialized git repo"; }
git add -A 2>/dev/null && git commit -q -m "goal-loop: baseline checkpoint" 2>/dev/null || true

START=$(date +%s)
DEADLINE=$((START + DURATION))
ITER=0
backoff=0

hms() { local s=$1; printf '%02d:%02d:%02d' $((s/3600)) $(((s%3600)/60)) $((s%60)); }
human_deadline() { date -d "@$DEADLINE" 2>/dev/null || date -r "$DEADLINE" 2>/dev/null || echo "$DEADLINE"; }

summary() {
  local now; now=$(date +%s)
  [ -n "$NOSLEEP_PID" ] && kill "$NOSLEEP_PID" 2>/dev/null || true
  echo ""
  echo "──────────────────────────────────────────────────────────────"
  echo "[goal-loop] stopped after $ITER iteration(s), elapsed $(hms $((now-START)))."
  echo "[goal-loop] commits during this run:"
  git log --oneline --since="@$START" 2>/dev/null | sed 's/^/    /' || true
  echo "──────────────────────────────────────────────────────────────"
}
on_signal() {
  echo; echo "[goal-loop] interrupted by signal — shutting down cleanly."
  pkill -P $$ 2>/dev/null || true   # stop any in-flight claude/tee child
  if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
    git add -A && git commit -q -m "goal-loop: interrupted checkpoint" 2>/dev/null || true
  fi
  summary
  exit 0
}
trap on_signal INT TERM

echo "[goal-loop] start: $(date)"
echo "[goal-loop] window: $(hms "$DURATION")  →  deadline $(human_deadline)"
echo "[goal-loop] project: $PROJECT_DIR"
keep_awake

while [ "$(date +%s)" -lt "$DEADLINE" ]; do
  ITER=$((ITER+1))
  now=$(date +%s); elapsed=$((now-START)); remaining=$((DEADLINE-now))
  echo ""
  echo "════ iteration $ITER · elapsed $(hms "$elapsed") · remaining $(hms "$remaining") ════"

  CTX="AUTONOMOUS LOOP CONTEXT (injected by the runner — do not question it):
- This is iteration #$ITER of an unattended loop.
- Wall-clock remaining in this run: ${remaining}s ($(hms "$remaining")).
- No human is watching. Make decisions and proceed. Finish + verify + commit THIS iteration."

  PROMPT="$(cat "$PROMPT_FILE")

$CTX"

  "$CLAUDE_BIN" -p "$PROMPT" \
      --dangerously-skip-permissions \
      --output-format stream-json --verbose \
      "${MODEL_ARG[@]}" \
      2>&1 | tee -a "logs/iter-$(printf '%04d' "$ITER").log"
  code=${PIPESTATUS[0]}

  if [ "$code" -ne 0 ]; then
    echo "[goal-loop] claude exited non-zero ($code)."
    backoff=$(( backoff == 0 ? 5 : backoff * 2 ))
    [ "$backoff" -gt "$MAX_BACKOFF" ] && backoff=$MAX_BACKOFF
    echo "[goal-loop] backing off ${backoff}s before next iteration."
    sleep "$backoff"
  else
    backoff=0
  fi

  # Safety net: never lose work, even if the agent forgot to commit. Every step stays git-revertable.
  if [ -n "$(git status --porcelain)" ]; then
    git add -A && git commit -q -m "goal-loop: iteration $ITER auto-checkpoint" || true
  fi

  sleep "$INTER_ITER_SLEEP"
done

echo ""
echo "[goal-loop] window complete — running FINAL end-to-end verification pass."
"$CLAUDE_BIN" -p "Read GOAL.md and PROGRESS.md. Do a FINAL end-to-end verification ONLY (add no features): \
run the full test suite, run the real pipeline against live sources, validate that events.ics parses \
with the icalendar library and feed.xml parses with feedparser, and report exact event/source/dedupe/big-name \
counts. Then write FINAL_REPORT.md summarizing what works, what is verified (with the numbers), known gaps, \
and the top 5 next steps. Commit it." \
    --dangerously-skip-permissions --output-format stream-json --verbose "${MODEL_ARG[@]}" \
    2>&1 | tee -a "logs/final-verification.log"
git add -A && git commit -q -m "goal-loop: final verification report" 2>/dev/null || true

summary
