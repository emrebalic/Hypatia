# One-time setup for Hypatia. Run from the repo root in PowerShell:
#   powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

Write-Host "== Tool check ==" -ForegroundColor Cyan
$missing = @()
foreach ($t in @("git", "node", "npm", "muse")) {
    if (Get-Command $t -ErrorAction SilentlyContinue) { Write-Host "  OK  $t" }
    else { Write-Host "  MISSING  $t" -ForegroundColor Red; $missing += $t }
}
$v = $null
try { $v = py -3.12 --version 2>$null } catch {}
if ($v -match "3\.12") { Write-Host "  OK  python (py -3.12)" } else { Write-Host "  MISSING  Python 3.12" -ForegroundColor Red; $missing += "python3.12" }
if ($missing.Count -gt 0) {
    Write-Host "Install the missing tools, then run this script again." -ForegroundColor Yellow
    Write-Host "  Python: winget install Python.Python.3.12   Node: winget install OpenJS.NodeJS.LTS"
    exit 1
}
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Host "  NOTE  ffmpeg not found: only needed for non-WAV uploads (winget install Gyan.FFmpeg)" -ForegroundColor Yellow
}

Write-Host "== Allow local scripts for this user (npm, .ps1) ==" -ForegroundColor Cyan
# Reports an error when -ExecutionPolicy Bypass overrides it for this run; the saved setting still applies.
try { Set-ExecutionPolicy -Scope CurrentUser RemoteSigned -Force -ErrorAction Stop } catch { Write-Host "  (overridden for this run, fine)" }

Write-Host "== Muse Code auth ==" -ForegroundColor Cyan
Write-Host "If you have not stored your Meta API key yet, run:  muse auth set --api-key-stdin"

Write-Host "== Git: first commit + push ==" -ForegroundColor Cyan
$ErrorActionPreference = "Continue"  # git writes normal progress to stderr; rely on exit codes
git add -A
git commit -m "Starter kit: spec, agent rules, tasks, fixtures, loop scripts"
if ($LASTEXITCODE -ne 0) { Write-Host "git commit failed." -ForegroundColor Red; exit 1 }
git push -u origin main
if ($LASTEXITCODE -ne 0) { Write-Host "git push failed." -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "Done. Next: powershell -ExecutionPolicy Bypass -File scripts/run-loop.ps1 -Push" -ForegroundColor Green
