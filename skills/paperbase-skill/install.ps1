# PaperBase Skill Installer for Windows (PowerShell)
# Installs the PaperBase skill to user's global AI agent directory

Write-Host "🚀 PaperBase Skill Installer" -ForegroundColor Cyan
Write-Host "==============================" -ForegroundColor Cyan
Write-Host ""

# Detect AI agent configuration directory
$ClaudeDir = "$env:USERPROFILE\.claude\skills"
$CodexDir = "$env:USERPROFILE\.codex\skills"
$InstallDir = $null

if (Test-Path $ClaudeDir) {
    $InstallDir = $ClaudeDir
    Write-Host "✓ Detected Claude Code configuration: $ClaudeDir" -ForegroundColor Green
} elseif (Test-Path $CodexDir) {
    $InstallDir = $CodexDir
    Write-Host "✓ Detected Codex configuration: $CodexDir" -ForegroundColor Green
} else {
    Write-Host "⚠️  No AI agent configuration directory found." -ForegroundColor Yellow
    Write-Host "   Creating Claude Code skills directory..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Path $ClaudeDir -Force | Out-Null
    $InstallDir = $ClaudeDir
    Write-Host "✓ Created: $ClaudeDir" -ForegroundColor Green
}

Write-Host ""

# Get script directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SourceDir = $ScriptDir

# Target directory
$TargetDir = Join-Path $InstallDir "paperbase-skill"

# Check if skill already exists
if (Test-Path $TargetDir) {
    Write-Host "⚠️  Skill already exists at: $TargetDir" -ForegroundColor Yellow
    $Overwrite = Read-Host "   Overwrite? (y/n)"
    if ($Overwrite -notmatch '^[Yy]$') {
        Write-Host "❌ Installation cancelled." -ForegroundColor Red
        exit 1
    }
    Write-Host "   Removing old version..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force $TargetDir
}

# Copy skill to global directory
Write-Host "📦 Installing skill to: $TargetDir" -ForegroundColor Cyan
Copy-Item -Recurse $SourceDir $TargetDir

# Verify installation
if ((Test-Path "$TargetDir\SKILL.md") -and (Test-Path "$TargetDir\README.md")) {
    Write-Host "✅ Installation successful!" -ForegroundColor Green
    Write-Host ""
    Write-Host "📋 Next steps:" -ForegroundColor Cyan
    Write-Host "   1. Restart your AI agent (if currently running)"
    Write-Host "   2. In any conversation, type: /paperbase --help"
    Write-Host "   3. Try: /paperbase status"
    Write-Host ""
    Write-Host "📖 Documentation: $TargetDir\README.md"
} else {
    Write-Host "❌ Installation failed. Please check file permissions." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "🎉 Done! The /paperbase skill is now available globally." -ForegroundColor Green
