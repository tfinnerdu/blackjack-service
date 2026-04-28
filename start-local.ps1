# Doane launcher standard. Zero-arg invocation starts the dev environment.
# - Boots Flask on :5050 (api + serves built React)
# - Boots Vite on :5174 (live frontend with /api proxy to Flask)
# Open http://localhost:5174 for development.

param(
    [switch]$ForceDeps,
    [switch]$BackendOnly
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
Set-Location $ProjectRoot

$LogDir = Join-Path $ProjectRoot ".hub-logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

$ts = Get-Date -Format "yyyyMMdd-HHmmss"
$Log = Join-Path $LogDir "launch-$ts.log"
if (Test-Path $Log) { Remove-Item $Log -Force }
if (Test-Path "$Log.err") { Remove-Item "$Log.err" -Force }

# --- Python venv ---
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Host "Creating .venv..."
    python -m venv .venv
}

if ($ForceDeps -or -not (Test-Path (Join-Path $ProjectRoot ".venv\Lib\site-packages\flask"))) {
    Write-Host "Installing Python deps..."
    & $VenvPython -m pip install --upgrade pip | Out-Null
    & $VenvPython -m pip install -r requirements.txt
}

# --- Node deps ---
if (-not $BackendOnly) {
    if ($ForceDeps -or -not (Test-Path (Join-Path $ProjectRoot "client\node_modules"))) {
        Write-Host "Installing client deps..."
        Push-Location (Join-Path $ProjectRoot "client")
        npm install
        Pop-Location
    }
}

# --- LAN IP (filtered for usable addresses) ---
$LanIp = (Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object {
        $_.IPAddress -notmatch '^127\.' -and
        $_.IPAddress -notmatch '^169\.254\.' -and
        $_.InterfaceAlias -notmatch 'vEthernet|WSL|Loopback'
    } | Select-Object -First 1).IPAddress

if ($env:FLASK_DEBUG) { } else { $env:FLASK_DEBUG = "1" }

# Computer name lets other devices on the LAN reach this box by
# hostname instead of IP (Doane standard: prefer COMPUTERNAME-based URLs
# over raw localhost / IP for shared dev / device testing).
$Host = $env:COMPUTERNAME

Write-Host "---"
Write-Host "Flask:  http://localhost:5050"
if ($Host) { Write-Host "        http://${Host}:5050" }
if (-not $BackendOnly) {
    Write-Host "Vite:   http://localhost:5174 (use this for dev)"
    if ($Host) { Write-Host "        http://${Host}:5174" }
}
if ($LanIp) { Write-Host "LAN:    http://${LanIp}:5174" }
Write-Host "Logs:   $Log"
Write-Host "---"

# --- Start Flask in background ---
$flaskJob = Start-Job -ScriptBlock {
    param($root, $py, $log)
    Set-Location $root
    & $py -u wsgi.py *> $log 2>&1
} -ArgumentList $ProjectRoot, $VenvPython, $Log

if ($BackendOnly) {
    Write-Host "Flask running (job id $($flaskJob.Id)). Ctrl+C to stop."
    Wait-Job $flaskJob
    exit
}

# --- Run Vite in foreground so Ctrl+C stops everything cleanly ---
try {
    Push-Location (Join-Path $ProjectRoot "client")
    npm run dev
} finally {
    Pop-Location
    Stop-Job $flaskJob -ErrorAction SilentlyContinue
    Remove-Job $flaskJob -ErrorAction SilentlyContinue
}
