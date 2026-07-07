# PaperBase One-Command Installer for Windows
# PowerShell 7+ recommended

$ErrorActionPreference = "Stop"

# Colors
function Write-Success { param($msg) Write-Host $msg -ForegroundColor Green }
function Write-Error { param($msg) Write-Host $msg -ForegroundColor Red }
function Write-Warning { param($msg) Write-Host $msg -ForegroundColor Yellow }
function Write-Info { param($msg) Write-Host $msg -ForegroundColor Cyan }

Write-Info "╔════════════════════════════════════════╗"
Write-Info "║   🚀 PaperBase Installer v1.0.0      ║"
Write-Info "╚════════════════════════════════════════╝"
Write-Host ""

# Step 1: Check Python version
Write-Info "[1/6] Checking Python version..."
try {
    $pythonVersion = (python --version 2>&1) -replace 'Python ', ''
    $requiredVersion = [version]"3.11"
    $currentVersion = [version]$pythonVersion

    if ($currentVersion -ge $requiredVersion) {
        Write-Success "✓ Python $pythonVersion"
    } else {
        Write-Error "✗ Python 3.11+ required (found $pythonVersion)"
        Write-Host ""
        Write-Host "Install Python 3.11+:"
        Write-Host "  - Download: https://www.python.org/downloads/"
        Write-Host "  - Or use winget: winget install Python.Python.3.11"
        exit 1
    }
} catch {
    Write-Error "✗ Python not found"
    Write-Host "Install from: https://www.python.org/downloads/"
    exit 1
}

# Step 2: Check Git
Write-Info "[2/6] Checking Git..."
try {
    $gitVersion = (git --version 2>&1) -replace 'git version ', ''
    Write-Success "✓ Git $gitVersion"
} catch {
    Write-Error "✗ Git not found"
    Write-Host ""
    Write-Host "Install Git:"
    Write-Host "  - Download: https://git-scm.com/download/win"
    Write-Host "  - Or use winget: winget install Git.Git"
    exit 1
}

# Step 3: Check disk space
Write-Info "[3/6] Checking disk space..."
$drive = (Get-Location).Drive.Name
$freeSpace = [math]::Round((Get-PSDrive -Name $drive).Free / 1GB, 1)
if ($freeSpace -ge 2) {
    Write-Success "✓ ${freeSpace}GB available"
} else {
    Write-Warning "⚠  Only ${freeSpace}GB available (2GB+ recommended)"
}

# Step 4: Install uv
Write-Info "[4/6] Installing uv package manager..."
if (Get-Command uv -ErrorAction SilentlyContinue) {
    $uvVersion = (uv --version) -replace 'uv ', ''
    Write-Success "✓ uv already installed ($uvVersion)"
} else {
    Write-Host "   Downloading uv..."
    Invoke-WebRequest -Uri "https://astral.sh/uv/install.ps1" -OutFile "$env:TEMP\uv-install.ps1"
    & "$env:TEMP\uv-install.ps1"
    Remove-Item "$env:TEMP\uv-install.ps1"

    # Refresh PATH
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")

    if (Get-Command uv -ErrorAction SilentlyContinue) {
        Write-Success "✓ uv installed successfully"
    } else {
        Write-Error "✗ uv installation failed. Restart PowerShell and try again."
        exit 1
    }
}

# Step 5: Clone PaperBase
Write-Info "[5/6] Cloning PaperBase repository..."
if (Test-Path "PaperBase") {
    Write-Warning "⚠  PaperBase directory already exists"
    $reply = Read-Host "   Remove and re-clone? (y/n)"
    if ($reply -match '^[Yy]$') {
        Remove-Item -Recurse -Force PaperBase
        git clone https://github.com/Chi-hong22/PaperBase.git
    } else {
        Set-Location PaperBase
    }
} else {
    git clone https://github.com/Chi-hong22/PaperBase.git
    Set-Location PaperBase
}

Write-Success "✓ Repository cloned"

# Step 6: Install dependencies
Write-Info "[6/6] Installing dependencies..."
uv sync

Write-Success "✓ Dependencies installed"

# Optional: Install graphify
Write-Host ""
Write-Warning "Optional: Install graphify for knowledge graph features?"
$reply = Read-Host "Install graphify? (y/n)"
if ($reply -match '^[Yy]$') {
    uv tool install graphify
    Write-Success "✓ graphify installed"
} else {
    Write-Warning "⚠  Skipped graphify (can install later with: uv tool install graphify)"
}

# Verify installation
Write-Host ""
Write-Info "Verifying installation..."
try {
    $null = uv run paperbase --version 2>&1
    Write-Success "✓ PaperBase CLI working"
} catch {
    Write-Error "✗ PaperBase CLI verification failed"
    exit 1
}

# Success message
Write-Host ""
Write-Success "╔════════════════════════════════════════╗"
Write-Success "║   ✅ Installation Complete!           ║"
Write-Success "╚════════════════════════════════════════╝"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. cd PaperBase"
Write-Host "  2. uv run paperbase ingest `"arxiv:1706.03762`""
Write-Host "  3. uv run paperbase search `"attention mechanism`""
Write-Host ""
Write-Host "Documentation: https://github.com/Chi-hong22/PaperBase"
Write-Host "Issues: https://github.com/Chi-hong22/PaperBase/issues"
