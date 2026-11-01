# Quality gate for Hypatia: backend tests (offline) + frontend production build. Exit 0 = green.
# Runs on the host, called by scripts/run-loop.ps1. Usage from repo root:
#   powershell -ExecutionPolicy Bypass -File scripts/check.ps1
# Parts that do not exist yet (no requirements.txt / package.json) are skipped.
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot

# Tests must stay offline: never hand them a key or the live switch.
Remove-Item Env:META_API_KEY, Env:MODEL_API_KEY, Env:RUN_LIVE -ErrorAction SilentlyContinue

function Fail($msg) { Write-Host "CHECK FAILED: $msg"; exit 1 }

$backend = Join-Path $root "backend"
$requirements = Join-Path $backend "requirements.txt"
if (Test-Path $requirements) {
    Set-Location $backend
    $python = Join-Path $backend ".venv\Scripts\python.exe"
    if (-not (Test-Path $python)) {
        Write-Host "== creating backend/.venv =="
        py -3.12 -m venv .venv
        if ($LASTEXITCODE -ne 0) { Fail "could not create venv with py -3.12" }
    }
    # Reinstall only when requirements.txt changed.
    $stamp = Join-Path $backend ".venv\requirements.sha256"
    $hash = (Get-FileHash $requirements -Algorithm SHA256).Hash
    if (-not (Test-Path $stamp) -or (Get-Content $stamp) -ne $hash) {
        Write-Host "== pip install =="
        & $python -m pip install --disable-pip-version-check -q -r requirements.txt
        if ($LASTEXITCODE -ne 0) { Fail "pip install" }
        Set-Content -Path $stamp -Value $hash
    }
    Write-Host "== pytest =="
    & $python -m pytest -q --ignore=tests/live
    if ($LASTEXITCODE -ne 0) { Fail "pytest (exit $LASTEXITCODE)" }
} else {
    Write-Host "== backend not created yet, skipping =="
}

$frontend = Join-Path $root "frontend"
if (Test-Path (Join-Path $frontend "package.json")) {
    Set-Location $frontend
    if (Test-Path "package-lock.json") {
        Write-Host "== npm ci =="
        npm.cmd ci --no-audit --no-fund
    } else {
        Write-Host "== npm install =="
        npm.cmd install --no-audit --no-fund
    }
    if ($LASTEXITCODE -ne 0) { Fail "npm install" }
    Write-Host "== npm run build =="
    npm.cmd run build
    if ($LASTEXITCODE -ne 0) { Fail "npm run build" }
} else {
    Write-Host "== frontend not created yet, skipping =="
}

Write-Host "CHECK PASSED"
exit 0
