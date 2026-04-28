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

# --- LAN IPs (filtered for usable addresses, may have multiple) ---
# $Host is reserved in PowerShell — use $MachineName / $LanIps for ours.
$LanIps = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object {
        $_.IPAddress      -notmatch '^(127\.|169\.254\.)' -and
        $_.PrefixOrigin   -ne       'WellKnown'           -and
        $_.InterfaceAlias -notmatch 'Loopback|Virtual|WSL|vEthernet'
    } |
    Select-Object -ExpandProperty IPAddress -Unique

if ($env:FLASK_DEBUG) { } else { $env:FLASK_DEBUG = "1" }

# Computer name lets other devices on the LAN reach this box by hostname
# instead of an IP that changes between networks. Doane standard: surface
# all three reachability forms (Local / By name / Network) per service.
$MachineName = $env:COMPUTERNAME

Write-Host "---"
Write-Host "Flask:"
Write-Host "  Local:    http://localhost:5050"
if ($MachineName) { Write-Host "  By name:  http://${MachineName}:5050" }
foreach ($ip in $LanIps) { Write-Host "  Network:  http://${ip}:5050" }
if (-not $BackendOnly) {
    Write-Host "Vite (use this URL for live dev):"
    Write-Host "  Local:    http://localhost:5174"
    if ($MachineName) { Write-Host "  By name:  http://${MachineName}:5174" }
    foreach ($ip in $LanIps) { Write-Host "  Network:  http://${ip}:5174" }
}
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
