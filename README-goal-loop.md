# `/goal` autonomous loop — setup & run

A fixed-window, unattended driver that runs the `/goal` prompt against Claude Code over and over
until a wall-clock deadline (default **4 hours**), keeps the machine awake, checkpoints every
iteration to git, and runs a final end-to-end verification pass.

## How it actually works (read this once)
A single Claude Code prompt can't hold a 4-hour clock — Claude Code runs **turn by turn** and stops
when a turn finishes. So persistence lives in a thin **driver loop** (`run-goal-loop.sh` /
`.ps1`) that re-invokes the `/goal` prompt headlessly each turn until the timer is up. Each turn is
a **fresh** headless session; all continuity lives on disk (`GOAL.md`, `PROGRESS.md`, `BACKLOG.md`,
and the git history). That's deliberate — it avoids context-window blowups over a long run, and any
single iteration is `git revert`-able.

```
run-goal-loop.sh ──┐  (re-invokes every turn until deadline)
                   ├──> claude -p "<contents of .claude/commands/goal.md> + live time-remaining"
.claude/commands/  │        --dangerously-skip-permissions --output-format stream-json
  goal.md  ────────┘   ↑ reads GOAL.md / PROGRESS.md / BACKLOG.md, builds+verifies+commits one increment
```

## Prerequisites
- **Claude Code** installed and logged in (`claude --version` works). It needs Node.js.
- **git** (the loop relies on it for durable, revertable state).
- **Python 3.11+** for the project the agent builds. Postgres is optional — it falls back to SQLite.

## Files
| file | role |
|---|---|
| `GOAL.md` | the mission/spec/architecture/verification-gates the agent reads first every turn |
| `.claude/commands/goal.md` | the `/goal` slash command — the per-iteration build/verify/brainstorm prompt |
| `run-goal-loop.sh` | macOS/Linux driver (uses `caffeinate` / `systemd-inhibit` to stay awake) |
| `run-goal-loop.ps1` | Windows driver (uses `SetThreadExecutionState`) |
| `PROGRESS.md`, `BACKLOG.md`, `FINAL_REPORT.md` | created/maintained by the loop itself |

## Run it

**macOS / Linux**
```bash
chmod +x run-goal-loop.sh
./run-goal-loop.sh                 # 4 hours, this directory
GOAL_DURATION_SECONDS=3600 ./run-goal-loop.sh   # 1-hour test run first (recommended)
```

**Windows (PowerShell)**
```powershell
.\run-goal-loop.ps1
$env:GOAL_DURATION_SECONDS=3600; .\run-goal-loop.ps1   # 1-hour test run
```

You can also drive it interactively: open `claude` in this directory and type `/goal` (optionally
`/goal fetchers` to focus a turn).

## Knobs (env)
`GOAL_DURATION_SECONDS` (14400) · `GOAL_PROJECT_DIR` ($PWD) · `GOAL_MODEL` (e.g. `claude-opus-4-8`) ·
`GOAL_CLAUDE_BIN` (`claude`) · `GOAL_INTER_ITER_SLEEP` (3) · `GOAL_MAX_BACKOFF` (60).

## Watch / stop / resume
- **Watch:** `tail -f logs/iter-*.log`, or `watch git log --oneline`, or read `PROGRESS.md`.
- **Stop:** `Ctrl-C` — the loop checkpoints and prints a summary.
- **Resume:** just run it again. It reads `PROGRESS.md` + git and picks up where it left off.

## Note on `--dangerously-skip-permissions`
The loop passes this so headless turns don't block on permission prompts (there's nobody to click
"approve"). It lets Claude Code run file edits / shell / network without asking. The loop commits to
git every iteration, so any step is recoverable; run it in a directory you're comfortable letting it
write to.
