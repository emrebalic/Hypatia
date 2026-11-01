# Hypatia unattended loop. The agent (Muse Code, headless) only edits files: no shell, no web.
# This script does everything else on the host: runs check.ps1, feeds failures back, commits.
# Why no agent shell: see NOTES.md "Muse Code on this machine".
# Usage from repo root (needs at least one commit and a clean tree):
#   powershell -ExecutionPolicy Bypass -File scripts/run-loop.ps1 -Push
# Stops on: all tasks ticked, -Deadline, -MaxSpendUsd, -MaxIterations, -MaxBlockedInARow, or a suspected secret.
param(
    [int]$MaxIterations = 60,
    [int]$MaxAttemptsPerTask = 4,
    [int]$MaxBlockedInARow = 2,
    [int]$MaxModelSteps = 80,
    [int]$MuseTimeoutMinutes = 30,
    [int]$CheckTimeoutMinutes = 15,
    [string]$Model = "muse-spark-1.3",
    [string]$ReasoningEffort = "high",
    [double]$MaxSpendUsd = 120,
    [datetime]$Deadline = "2026-11-03T12:00:00+03:00",
    [switch]$Push
)

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
New-Item -ItemType Directory -Force -Path "logs" | Out-Null
$utf8 = New-Object System.Text.UTF8Encoding($false)

function Say($msg) { Write-Host "[$(Get-Date -Format 'MM-dd HH:mm:ss')] $msg" }

# Unticked tasks above the Stretch section, in file order.
function Get-OpenTasks {
    $tasks = @()
    foreach ($line in [IO.File]::ReadAllLines((Join-Path $root "TASKS.md"), $utf8)) {
        if ($line -match '^## Stretch') { break }
        if ($line -match '^- \[ \] (\d+)\.\s*(.*)$') {
            $tasks += [pscustomobject]@{ Number = [int]$Matches[1]; Text = $Matches[2] }
        }
    }
    return $tasks
}

function Test-Ticked([int]$number) {
    return [bool](Select-String -Path "TASKS.md" -Pattern "^- \[x\] $number\." -Quiet)
}

# Estimated spend so far, from the run_usage events in all logs/muse-*.jsonl, so it survives restarts.
# Prices are USD per 1M tokens (input, cached input, output) from NOTES.md. Cached tokens count inside input.
function Get-SpendUsd {
    $prices = @{
        "muse-wonder-1.0"            = @(4.00, 0.20, 20.00)
        "muse-spark-1.3"             = @(1.25, 0.15, 4.25)
        "muse-spark-1.3-contributor" = @(0.10, 0.002, 0.20)
    }
    $total = 0.0
    foreach ($file in Get-ChildItem "logs" -Filter "muse-*.jsonl" -ErrorAction SilentlyContinue) {
        $last = Select-String -Path $file.FullName -Pattern '"kind":"run_usage"' | Select-Object -Last 1
        if (-not $last) { continue }
        $usage = ($last.Line | ConvertFrom-Json).payload
        foreach ($m in $usage.models) {
            $p = $prices[$m.model]
            if (-not $p) { $p = $prices["muse-wonder-1.0"] }  # unknown model: assume the most expensive
            $fresh = $m.input_tokens - $m.cached_tokens
            $total += ($fresh * $p[0] + $m.cached_tokens * $p[1] + $m.output_tokens * $p[2]) / 1000000
        }
    }
    return $total
}

# Runs a process with a hard timeout, killing its whole tree. Returns the exit code, or -1 on timeout.
function Invoke-Timed($file, [string[]]$arguments, [int]$minutes, $stdout, $stderr) {
    $p = Start-Process -FilePath $file -ArgumentList $arguments -WorkingDirectory $root `
        -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru -WindowStyle Hidden
    $null = $p.Handle  # keeps ExitCode readable after exit
    if (-not $p.WaitForExit($minutes * 60 * 1000)) {
        taskkill /PID $p.Id /T /F | Out-Null
        return -1
    }
    return $p.ExitCode
}

# The agent may not weaken the gate: rules, scripts and existing tests go back to HEAD before check.ps1.
function Restore-Protected {
    git checkout HEAD -- SPEC.md AGENTS.md CLAUDE.md .gitignore scripts fixtures/sample_debate.json fixtures/sample_transcript.txt
    git clean -fdq -- scripts
    $deleted = @(git diff --diff-filter=D --name-only HEAD -- backend/tests)
    foreach ($f in $deleted) { if ($f) { git checkout HEAD -- $f; Say "  restored deleted test: $f" } }
}

# Returns a reason string if the staged diff looks like it contains a secret, else $null.
function Find-Secret {
    $names = @(git diff --cached --name-only)
    foreach ($n in $names) {
        if ($n -match '(^|/)\.env$') { return "staged env file: $n" }
    }
    $added = @(git diff --cached -U0 | Where-Object { $_ -match '^\+' -and $_ -notmatch '^\+\+\+' })
    $envFile = "backend/.env"
    if (Test-Path $envFile) {
        foreach ($line in Get-Content $envFile) {
            if ($line -match '^\s*(META_API_KEY|MODEL_API_KEY)\s*=\s*(\S{8,})') {
                $value = $Matches[2]
                foreach ($a in $added) { if ($a.Contains($value)) { return "API key value in staged diff" } }
            }
        }
    }
    foreach ($a in $added) {
        if ($a -match '(?i)(api[_-]?key|secret|token|authorization)["'']?\s*[:=]\s*["'']?(bearer\s+)?[A-Za-z0-9_\-\.]{24,}') {
            return "secret-like line in staged diff (values not shown)"
        }
    }
    return $null
}

function Save-Commit([string]$message) {
    git add -A
    $reason = Find-Secret
    if ($reason) {
        git reset -q
        Say "STOP: $reason. Nothing committed; changes left in the working tree."
        exit 2
    }
    git commit -q -m $message
    if ($LASTEXITCODE -ne 0) { Say "  git commit failed (exit $LASTEXITCODE)"; return }
    Say "  committed: $message"
    if ($Push) {
        git push -q origin main
        if ($LASTEXITCODE -ne 0) { Say "  WARNING: git push failed, will retry on next commit" }
    }
}

# --- preflight ---
git rev-parse --verify -q HEAD | Out-Null
if ($LASTEXITCODE -ne 0) { Say "No commits yet. Run scripts/setup.ps1 first."; exit 1 }
if (git status --porcelain) { Say "Working tree is not clean. Commit or stash first."; exit 1 }

$template = [IO.File]::ReadAllText((Join-Path $root "scripts/loop-prompt.md"), $utf8)
$attempts = @{}
$blocked = @{}
$blockedInARow = 0
$lastFailure = ""

for ($i = 1; $i -le $MaxIterations; $i++) {
    if ((Get-Date) -ge $Deadline) { Say "Feature freeze reached ($Deadline). Stopping."; break }
    $spend = Get-SpendUsd
    if ($spend -ge $MaxSpendUsd) { Say ("Budget reached: about `${0:N2} of `${1:N2}. Stopping." -f $spend, $MaxSpendUsd); break }
    Say ("Estimated spend so far: `${0:N2} of `${1:N2}" -f $spend, $MaxSpendUsd)

    $open = @((Get-OpenTasks) | Where-Object { -not $blocked.ContainsKey($_.Number) })
    if ($open.Count -eq 0) { Say "No open tasks left."; break }
    $task = $open[0]
    $n = $task.Number
    $attempts[$n] = 1 + [int]$attempts[$n]
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    Say "Iteration $i/$MaxIterations - task $n, attempt $($attempts[$n])/$MaxAttemptsPerTask ($($open.Count) open)"

    $feedback = if ($lastFailure) { $lastFailure } else { "(none: this is the first attempt)" }
    $prompt = $template.Replace("{{TASK_NUMBER}}", "$n").Replace("{{TASK_TEXT}}", $task.Text).Replace("{{FEEDBACK}}", $feedback)
    $promptFile = "logs/prompt-$stamp.md"
    [IO.File]::WriteAllText((Join-Path $root $promptFile), $prompt, $utf8)

    $museArgs = @("exec", "--json", "--disable-shell", "--disable-web-tools", "--disable-approval",
        "--disable-request-user-input", "--trust-workspace", "--sandbox-network", "restricted",
        "--model", $Model, "--reasoning-effort", $ReasoningEffort, "--max-model-steps", "$MaxModelSteps",
        "--prompt-file", $promptFile)
    $museExit = Invoke-Timed "muse.cmd" $museArgs $MuseTimeoutMinutes "logs/muse-$stamp.jsonl" "logs/muse-$stamp.err.txt"
    Say "  muse exit $museExit"

    Restore-Protected

    $checkLog = "logs/check-$stamp.txt"
    $checkArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "scripts/check.ps1")
    $checkExit = Invoke-Timed "powershell.exe" $checkArgs $CheckTimeoutMinutes $checkLog "logs/check-$stamp.err.txt"

    if ($checkExit -eq 0 -and (Test-Ticked $n)) {
        $summary = $task.Text -replace '[`"]', ''
        if ($summary.Length -gt 60) { $summary = $summary.Substring(0, 60) }
        Save-Commit "task ${n}: $summary"
        $lastFailure = ""
        $blockedInARow = 0
        continue
    }

    if ($checkExit -eq 0) {
        $lastFailure = "check.ps1 passed but task $n is not ticked in TASKS.md. Finish the task, then tick it."
    } else {
        $out = (Get-Content $checkLog -Tail 60 -ErrorAction SilentlyContinue) -join "`n"
        $err = (Get-Content "logs/check-$stamp.err.txt" -Tail 20 -ErrorAction SilentlyContinue) -join "`n"
        $lastFailure = "check.ps1 FAILED (exit $checkExit). Output tail:`n$out`n$err"
        Say "  check.ps1 failed, see $checkLog"
    }

    if ($attempts[$n] -ge $MaxAttemptsPerTask) {
        # Park the broken work in a stash so the next task starts from a green tree.
        git add -A
        git stash push -q -m "blocked task $n ($stamp)"
        $note = "`n- task ${n}: blocked after $($attempts[$n]) attempts ($stamp). Work is in git stash; last check log: $checkLog`n"
        [IO.File]::AppendAllText((Join-Path $root "NOTES.md"), $note, $utf8)
        Save-Commit "notes: task $n blocked"
        $blocked[$n] = $true
        $lastFailure = ""
        $blockedInARow++
        Say "  task $n BLOCKED ($blockedInARow in a row)"
        if ($blockedInARow -ge $MaxBlockedInARow) { Say "Too many blocked tasks in a row. Stopping to save credits."; break }
    }
    Start-Sleep -Seconds 5
}

git log --oneline -n 15
Say "Open tasks left: $(@(Get-OpenTasks).Count). See NOTES.md (## Blocked) and logs/."
