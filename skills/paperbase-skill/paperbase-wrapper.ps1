# PaperBase CLI Wrapper - Auto-detect library and execute commands
# Version: 0.1.0

# Color output
$ErrorColor = "Red"
$SuccessColor = "Green"
$WarningColor = "Yellow"

# Auto-detect PaperBase library
function Detect-Library {
    # Check environment variable first
    if ($env:PAPERBASE_LIBRARY -and (Test-Path $env:PAPERBASE_LIBRARY)) {
        return $env:PAPERBASE_LIBRARY
    }

    # Check current directory
    if (Test-Path ".\library\papers") {
        return "$PWD\library"
    }

    # Check parent directory
    if (Test-Path "..\library\papers") {
        return (Resolve-Path "..\library").Path
    }

    # Not found
    return $null
}

# Main execution
$LibraryPath = Detect-Library

if (-not $LibraryPath) {
    Write-Host "Error: PaperBase library not found" -ForegroundColor $ErrorColor
    Write-Host ""
    Write-Host "Solutions:"
    Write-Host "  1. Run from PaperBase repository root"
    Write-Host "  2. Set environment variable: `$env:PAPERBASE_LIBRARY = 'C:\path\to\library'"
    Write-Host "  3. Navigate to a PaperBase directory"
    exit 1
}

# Navigate to repository root
$RepoRoot = Split-Path -Parent $LibraryPath
Set-Location $RepoRoot

# Check if uv is available
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Error: 'uv' command not found" -ForegroundColor $ErrorColor
    Write-Host "Install: https://github.com/astral-sh/uv"
    exit 1
}

# Execute paperbase CLI
Write-Host "[PaperBase] Using library: $LibraryPath" -ForegroundColor $SuccessColor
uv run paperbase @args
