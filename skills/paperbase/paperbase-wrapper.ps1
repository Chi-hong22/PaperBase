# PaperBase CLI Wrapper - Auto-detect library and execute commands
# Version: 0.2.0 - Added workspace configuration persistence

# Color output
$ErrorColor = "Red"
$SuccessColor = "Green"
$WarningColor = "Yellow"

# Get skill installation directory
function Get-SkillDir {
    return Split-Path -Parent $PSCommandPath
}

# Get configuration file path
function Get-ConfigPath {
    $skillDir = Get-SkillDir
    return Join-Path $skillDir "workspaces.json"
}

# Find project root (向上查找 .git 或 pyproject.toml)
function Find-ProjectRoot {
    $currentDir = Get-Location

    while ($currentDir.Path -ne $currentDir.Root) {
        if ((Test-Path (Join-Path $currentDir ".git")) -or
            (Test-Path (Join-Path $currentDir "pyproject.toml"))) {
            return $currentDir.Path
        }
        $currentDir = Split-Path -Parent $currentDir.Path
    }

    return $null
}

# Load library path from configuration
function Load-Config {
    param([string]$ProjectRoot)

    $configPath = Get-ConfigPath

    if (-not (Test-Path $configPath)) {
        return $null
    }

    try {
        $config = Get-Content $configPath -Raw | ConvertFrom-Json
        $workspace = $config.workspaces.$ProjectRoot

        if ($workspace -and $workspace.library_path -and (Test-Path $workspace.library_path)) {
            return $workspace.library_path
        }
    } catch {
        # Ignore errors
    }

    return $null
}

# Save library path to configuration
function Save-Config {
    param(
        [string]$ProjectRoot,
        [string]$LibraryPath
    )

    $configPath = Get-ConfigPath

    # Read existing configuration
    if (Test-Path $configPath) {
        try {
            $config = Get-Content $configPath -Raw | ConvertFrom-Json
        } catch {
            $config = @{ workspaces = @{} }
        }
    } else {
        $config = @{ workspaces = @{} }
    }

    # Ensure workspaces property exists
    if (-not $config.workspaces) {
        $config | Add-Member -NotePropertyName workspaces -NotePropertyValue @{} -Force
    }

    # Update configuration
    $workspaceInfo = @{
        library_path = $LibraryPath
        last_used = (Get-Date).ToUniversalTime().ToString("o")
    }

    # PowerShell hashtable to PSCustomObject conversion
    if ($config.workspaces -is [System.Management.Automation.PSCustomObject]) {
        $config.workspaces | Add-Member -NotePropertyName $ProjectRoot -NotePropertyValue $workspaceInfo -Force
    } else {
        $config.workspaces[$ProjectRoot] = $workspaceInfo
    }

    # Write configuration
    $config | ConvertTo-Json -Depth 10 | Set-Content $configPath -Encoding UTF8
}

# Auto-detect PaperBase library
function Detect-Library {
    # Step 1: Check environment variable first
    if ($env:PAPERBASE_LIBRARY -and (Test-Path $env:PAPERBASE_LIBRARY)) {
        return $env:PAPERBASE_LIBRARY
    }

    # Step 2: Find project root
    $projectRoot = Find-ProjectRoot

    if ($projectRoot) {
        # Step 3: Try loading from configuration
        $cachedLibrary = Load-Config -ProjectRoot $projectRoot
        if ($cachedLibrary) {
            return $cachedLibrary
        }

        # Step 4: Auto-detect in project root
        $libraryPath = Join-Path $projectRoot "library"
        if (Test-Path (Join-Path $libraryPath "papers")) {
            Save-Config -ProjectRoot $projectRoot -LibraryPath $libraryPath
            return $libraryPath
        }
    }

    # Step 5: Fallback - Check current directory
    if (Test-Path ".\library\papers") {
        return "$PWD\library"
    }

    # Step 6: Fallback - Check parent directory
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

# Determine repository root
# If LibraryPath ends with \library, use parent; otherwise use LibraryPath itself
if ($LibraryPath -match '\\library$') {
    $RepoRoot = Split-Path -Parent $LibraryPath
} else {
    $RepoRoot = $LibraryPath
}
Set-Location $RepoRoot

# Check if uv is available
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Error: 'uv' command not found" -ForegroundColor $ErrorColor
    Write-Host "Install: https://github.com/astral-sh/uv"
    exit 1
}

# Execute paperbase CLI
Write-Host "[PaperBase] Using library: $RepoRoot" -ForegroundColor $SuccessColor
uv run paperbase --base-dir $RepoRoot @args
