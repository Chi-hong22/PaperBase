# PaperBase Skill Installer for Windows (PowerShell)
# Installs or updates the PaperBase skill for Codex, Claude Code, or both.

[CmdletBinding()]
param(
    [ValidateSet("codex", "claude", "both")]
    [string]$Agent = "codex"
)

Write-Host "🚀 PaperBase Skill Installer" -ForegroundColor Cyan
Write-Host "==============================" -ForegroundColor Cyan
Write-Host ""

# Get script directory
$source_dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$agent_specs = @()

if ($Agent -in @("codex", "both")) {
    $agent_specs += [pscustomobject]@{
        Name = "Codex"
        SkillsDir = Join-Path $env:USERPROFILE ".codex\skills"
    }
}

if ($Agent -in @("claude", "both")) {
    $agent_specs += [pscustomobject]@{
        Name = "Claude Code"
        SkillsDir = Join-Path $env:USERPROFILE ".claude\skills"
    }
}

$installed_targets = @()

foreach ($agent_spec in $agent_specs) {
    $skills_dir = $agent_spec.SkillsDir
    $target_dir = Join-Path $skills_dir "paperbase"
    $workspace_cache_bytes = $null

    if (-not (Test-Path -LiteralPath $skills_dir)) {
        Write-Host "Creating $($agent_spec.Name) skills directory: $skills_dir" -ForegroundColor Yellow
        New-Item -ItemType Directory -Path $skills_dir -Force | Out-Null
    }

    $resolved_source = [System.IO.Path]::GetFullPath($source_dir).TrimEnd('\')
    $resolved_target = [System.IO.Path]::GetFullPath($target_dir).TrimEnd('\')

    if ($resolved_source.Equals($resolved_target, [System.StringComparison]::OrdinalIgnoreCase)) {
        Write-Host "✓ $($agent_spec.Name) already uses this skill directory: $target_dir" -ForegroundColor Green
        $installed_targets += $target_dir
        continue
    }

    if (Test-Path -LiteralPath $target_dir) {
        Write-Host "⚠️  $($agent_spec.Name) skill already exists at: $target_dir" -ForegroundColor Yellow
        $overwrite = Read-Host "   Overwrite? (y/n)"
        if ($overwrite -notmatch '^[Yy]$') {
            Write-Host "❌ Installation cancelled." -ForegroundColor Red
            exit 1
        }
        $existing_workspace_cache = Join-Path $target_dir "workspaces.json"
        if (Test-Path -LiteralPath $existing_workspace_cache -PathType Leaf) {
            $workspace_cache_bytes = [System.IO.File]::ReadAllBytes($existing_workspace_cache)
        }
        Write-Host "   Removing old version..." -ForegroundColor Yellow
        Remove-Item -LiteralPath $target_dir -Recurse -Force
    }

    Write-Host "📦 Installing $($agent_spec.Name) skill to: $target_dir" -ForegroundColor Cyan
    Copy-Item -LiteralPath $source_dir -Destination $target_dir -Recurse
    if ($null -ne $workspace_cache_bytes) {
        $installed_workspace_cache = Join-Path $target_dir "workspaces.json"
        [System.IO.File]::WriteAllBytes($installed_workspace_cache, $workspace_cache_bytes)
        Write-Host "✓ Preserved workspace cache: $installed_workspace_cache" -ForegroundColor Green
    }
    $installed_targets += $target_dir
}

# Verify installation
foreach ($target_dir in $installed_targets) {
    if (-not ((Test-Path -LiteralPath (Join-Path $target_dir "SKILL.md")) -and
        (Test-Path -LiteralPath (Join-Path $target_dir "README.md")) -and
        (Test-Path -LiteralPath (Join-Path $target_dir "paperbase-wrapper.ps1")))) {
        Write-Host "❌ Installation failed at: $target_dir" -ForegroundColor Red
        exit 1
    }
}

Write-Host ""
Write-Host "🎉 Done! The /paperbase skill is now available globally." -ForegroundColor Green
foreach ($target_dir in $installed_targets) {
    Write-Host "   ✓ $target_dir" -ForegroundColor Green
}
Write-Host ""
Write-Host "📋 Next steps:" -ForegroundColor Cyan
Write-Host "   1. Restart your AI agent (if currently running)"
Write-Host "   2. In any conversation, type: /paperbase --help"
Write-Host "   3. Try: /paperbase status"
Write-Host ""
Write-Host "🔍 Verifying dependencies..." -ForegroundColor Cyan

# Check uv
if (Get-Command uv -ErrorAction SilentlyContinue) {
    $uvVersion = uv --version
    Write-Host "✓ uv: $uvVersion" -ForegroundColor Green
} else {
    Write-Host "⚠️  'uv' not found. Install: https://github.com/astral-sh/uv" -ForegroundColor Yellow
}

# Check paperbase CLI (optional, only if in a PaperBase repo)
if (Test-Path "..\..\pyproject.toml") {
    Set-Location ..\..
    try {
        $null = uv run paperbase --version 2>$null
        Write-Host "✓ PaperBase CLI: Available" -ForegroundColor Green
    } catch {
        Write-Host "⚠️  PaperBase CLI not available. Run 'uv sync' in project root." -ForegroundColor Yellow
    }
}
