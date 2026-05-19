# Jarvis one-command install script (Windows PowerShell).
#
# Usage: irm https://raw.githubusercontent.com/terialion/jarvis/main/scripts/install.ps1 | iex
#    or: gh repo clone terialion/jarvis; cd jarvis; .\scripts\install.ps1

param(
    [string]$InstallRoot = "$env:USERPROFILE\.jarvis",
    [string]$PythonPath = "python",
    [switch]$SkipNode = $false
)

$ErrorActionPreference = "Stop"

function Write-Step { Write-Host "[jarvis] $args" -ForegroundColor Cyan }
function Write-OK    { Write-Host "[jarvis] $args" -ForegroundColor Green }
function Write-Warn  { Write-Host "[jarvis] $args" -ForegroundColor Yellow }

# ── Check Python ──────────────────────────────────────────────
Write-Step "Checking prerequisites..."
try {
    $pyVer = & $PythonPath -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    if ([version]$pyVer -lt [version]"3.11") {
        Write-Warn "Python 3.11+ required (found $pyVer)"
        exit 1
    }
    Write-OK "Python $pyVer ✓"
} catch {
    Write-Warn "Python not found. Install from https://python.org/downloads/"
    exit 1
}

# ── Check Node.js ─────────────────────────────────────────────
$hasNode = $false
if (-not $SkipNode) {
    try {
        $nodeVer = node -v 2>$null
        if ($nodeVer) {
            $major = [int]($nodeVer -replace 'v','' -replace '\..*','')
            if ($major -ge 18) {
                $hasNode = $true
                Write-OK "Node.js $nodeVer ✓"
            }
        }
    } catch {}
}
if (-not $hasNode) {
    Write-Step "Node.js 18+ not found — TUI mode unavailable. Install from https://nodejs.org/"
}

# ── Clone or use existing ─────────────────────────────────────
if (Test-Path $InstallRoot) {
    Write-Step "Using existing Jarvis at $InstallRoot"
    Set-Location $InstallRoot
    git pull --ff-only 2>$null
} else {
    Write-Step "Cloning Jarvis to $InstallRoot..."
    git clone https://github.com/terialion/jarvis.git $InstallRoot
    Set-Location $InstallRoot
}

# ── Python venv ───────────────────────────────────────────────
Write-Step "Creating Python virtual environment..."
& $PythonPath -m venv .venv
$pyExe = "$InstallRoot\.venv\Scripts\python.exe"

Write-Step "Installing Python dependencies..."
& $pyExe -m pip install --upgrade pip -q
& $pyExe -m pip install -e ".[dev]" -q

# ── Node.js TUI ───────────────────────────────────────────────
if ($hasNode) {
    Write-Step "Installing TUI dependencies..."
    Push-Location "$InstallRoot\jarvis_tui"
    npm install --silent 2>$null
    Pop-Location
}

# ── Create launcher ───────────────────────────────────────────
$localBin = "$env:USERPROFILE\AppData\Local\Jarvis\bin"
New-Item -ItemType Directory -Force -Path $localBin | Out-Null

@"
@echo off
call "$InstallRoot\.venv\Scripts\activate.bat"
python -m jarvis %*
"@ | Out-File -FilePath "$localBin\jarvis.bat" -Encoding ASCII

# Add to user PATH
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$localBin*") {
    [Environment]::SetEnvironmentVariable("Path", "$userPath;$localBin", "User")
    Write-OK "Added $localBin to user PATH"
}

# ── Configure ─────────────────────────────────────────────────
if (-not (Test-Path "$InstallRoot\.env")) {
    Write-Step ""
    Write-Step "Configuration: Create $InstallRoot\.env with:"
    Write-Host "  JARVIS_LLM_API_KEY=sk-your-key"
    Write-Host "  JARVIS_LLM_PROVIDER=deepseek"
    Write-Host "  JARVIS_LLM_MODEL=deepseek-v4-pro"
}

# ── Done ──────────────────────────────────────────────────────
Write-OK ""
Write-OK "Jarvis installed successfully!"
Write-Host ""
Write-Host "  Run:   jarvis"
Write-Host "  TUI:   jarvis --tui"
Write-Host ""
Write-Host "  Restart your terminal or refresh PATH to use the 'jarvis' command."
