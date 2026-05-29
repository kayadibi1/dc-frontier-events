<#
  run-goal-loop.ps1 — drive the /goal prompt autonomously for a fixed wall-clock window (Windows).
  Prevents sleep via SetThreadExecutionState, re-invokes Claude Code headlessly each iteration,
  checkpoints to git every pass, and runs a final end-to-end verification at the deadline.

  Usage:   .\run-goal-loop.ps1
  Knobs (env or params): DurationSeconds (14400), ProjectDir ($PWD),
                         PromptFile (.claude\commands\goal.md), Model, ClaudeBin (claude),
                         InterIterSleep (3), MaxBackoff (60)
#>
param(
  [int]$DurationSeconds = $(if ($env:GOAL_DURATION_SECONDS) { [int]$env:GOAL_DURATION_SECONDS } else { 14400 }),
  [string]$ProjectDir   = $(if ($env:GOAL_PROJECT_DIR)      { $env:GOAL_PROJECT_DIR }      else { $PWD.Path }),
  [string]$PromptFile   = $(if ($env:GOAL_PROMPT_FILE)      { $env:GOAL_PROMPT_FILE }      else { "" }),
  [string]$Model        = $(if ($env:GOAL_MODEL)            { $env:GOAL_MODEL }            else { "" }),
  [string]$ClaudeBin    = $(if ($env:GOAL_CLAUDE_BIN)       { $env:GOAL_CLAUDE_BIN }       else { "claude" }),
  [int]$InterIterSleep  = $(if ($env:GOAL_INTER_ITER_SLEEP) { [int]$env:GOAL_INTER_ITER_SLEEP } else { 3 }),
  [int]$MaxBackoff      = $(if ($env:GOAL_MAX_BACKOFF)      { [int]$env:GOAL_MAX_BACKOFF }      else { 60 })
)

if (-not $PromptFile) { $PromptFile = Join-Path $ProjectDir ".claude\commands\goal.md" }
Set-Location $ProjectDir
if (-not (Test-Path $PromptFile)) { Write-Error "prompt file not found: $PromptFile"; exit 1 }
if (-not (Get-Command $ClaudeBin -ErrorAction SilentlyContinue)) { Write-Error "'$ClaudeBin' not on PATH"; exit 1 }
New-Item -ItemType Directory -Force -Path "logs" | Out-Null
if (-not (Test-Path ".git")) { git init -q; Write-Host "[goal-loop] initialized git repo" }
git add -A 2>$null; git commit -q -m "goal-loop: baseline checkpoint" 2>$null

# ── Keep the machine awake ───────────────────────────────────────────────
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class GoalSleep {
  [DllImport("kernel32.dll")]
  public static extern uint SetThreadExecutionState(uint esFlags);
}
"@
$ES_CONTINUOUS = [uint32]"0x80000000"; $ES_SYSTEM = [uint32]1; $ES_DISPLAY = [uint32]2
[GoalSleep]::SetThreadExecutionState($ES_CONTINUOUS -bor $ES_SYSTEM -bor $ES_DISPLAY) | Out-Null
Write-Host "[goal-loop] sleep/display kept awake via SetThreadExecutionState."

function HMS([int]$s) { '{0:00}:{1:00}:{2:00}' -f [int]($s/3600), [int](($s%3600)/60), [int]($s%60) }

$start = Get-Date; $deadline = $start.AddSeconds($DurationSeconds); $iter = 0; $backoff = 0
$modelArgs = @(); if ($Model) { $modelArgs = @("--model", $Model) }

Write-Host "[goal-loop] start: $start"
Write-Host "[goal-loop] window: $(HMS $DurationSeconds)  ->  deadline $deadline"
Write-Host "[goal-loop] project: $ProjectDir"

try {
  while ((Get-Date) -lt $deadline) {
    $iter++
    $remaining = [int]($deadline - (Get-Date)).TotalSeconds
    $elapsed   = [int]((Get-Date) - $start).TotalSeconds
    Write-Host ""
    Write-Host "==== iteration $iter | elapsed $(HMS $elapsed) | remaining $(HMS $remaining) ===="

    $ctx = @"

AUTONOMOUS LOOP CONTEXT (injected by the runner - do not question it):
- This is iteration #$iter of an unattended loop.
- Wall-clock remaining in this run: ${remaining}s ($(HMS $remaining)).
- No human is watching. Make decisions and proceed. Finish + verify + commit THIS iteration.
"@
    $prompt = (Get-Content $PromptFile -Raw) + $ctx
    $log = "logs\iter-{0:0000}.log" -f $iter

    & $ClaudeBin -p $prompt --dangerously-skip-permissions --output-format stream-json --verbose @modelArgs *>&1 |
      Tee-Object -FilePath $log
    $code = $LASTEXITCODE

    if ($code -ne 0) {
      Write-Host "[goal-loop] claude exited non-zero ($code)."
      if ($backoff -eq 0) { $backoff = 5 } else { $backoff = $backoff * 2 }
      if ($backoff -gt $MaxBackoff) { $backoff = $MaxBackoff }
      Write-Host "[goal-loop] backing off ${backoff}s."
      Start-Sleep -Seconds $backoff
    } else { $backoff = 0 }

    if (git status --porcelain) {
      git add -A; git commit -q -m "goal-loop: iteration $iter auto-checkpoint" 2>$null
    }
    Start-Sleep -Seconds $InterIterSleep
  }

  Write-Host "`n[goal-loop] window complete - running FINAL end-to-end verification pass."
  $finalPrompt = "Read GOAL.md and PROGRESS.md. Do a FINAL end-to-end verification ONLY (add no features): run the full test suite, run the real pipeline against live sources, validate that events.ics parses with the icalendar library and feed.xml parses with feedparser, and report exact event/source/dedupe/big-name counts. Then write FINAL_REPORT.md summarizing what works, what is verified (with numbers), known gaps, and the top 5 next steps. Commit it."
  & $ClaudeBin -p $finalPrompt --dangerously-skip-permissions --output-format stream-json --verbose @modelArgs *>&1 |
    Tee-Object -FilePath "logs\final-verification.log"
  git add -A; git commit -q -m "goal-loop: final verification report" 2>$null
}
finally {
  [GoalSleep]::SetThreadExecutionState($ES_CONTINUOUS) | Out-Null   # release the wake-lock
  $elapsed = [int]((Get-Date) - $start).TotalSeconds
  Write-Host "`n--------------------------------------------------------------"
  Write-Host "[goal-loop] stopped after $iter iteration(s), elapsed $(HMS $elapsed)."
  Write-Host "[goal-loop] commits during this run:"
  git log --oneline --since="$($start.ToString('o'))" 2>$null | ForEach-Object { "    $_" }
  Write-Host "--------------------------------------------------------------"
}
