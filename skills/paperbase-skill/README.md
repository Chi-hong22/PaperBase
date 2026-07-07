# PaperBase Skill

AI Agent skill for managing academic paper knowledge base.

## Overview

This skill provides a unified interface for AI agents (Claude Code, Codex) to interact with PaperBase, eliminating the need for verbose CLI commands in every conversation.

## Features

- 📥 **Ingest papers** from DOI, arXiv, PMID, or local PDF
- 🔍 **Search** full-text content with Boolean operators
- 📊 **Status** checking and state management
- 🔗 **Graph** updates (incremental or full)
- 🎯 **Context-aware** library path detection

## Installation

### One-Command Setup

**For Unix/Linux/macOS:**
```bash
./skills/paperbase-skill/install.sh
```

**For Windows (PowerShell):**
```powershell
.\skills\paperbase-skill\install.ps1
```

This script will:
1. Detect your AI agent configuration directory (`~/.claude/skills/` or `~/.codex/skills/`)
2. Copy the skill to the global location
3. Verify installation

### Manual Installation

**For Claude Code:**
```bash
# Copy skill to global directory
cp -r skills/paperbase-skill ~/.claude/skills/

# Verify installation
ls ~/.claude/skills/paperbase-skill/
```

**For Codex:**
```bash
# Copy skill to global directory
cp -r skills/paperbase-skill ~/.codex/skills/

# Verify installation
ls ~/.codex/skills/paperbase-skill/
```

**For Windows:**
```powershell
# For Claude Code
Copy-Item -Recurse skills\paperbase-skill $env:USERPROFILE\.claude\skills\

# For Codex
Copy-Item -Recurse skills\paperbase-skill $env:USERPROFILE\.codex\skills\
```

## Usage

After installation, invoke the skill in any AI agent session:

### Ingesting Papers

```
/paperbase ingest 10.1038/nature12373
/paperbase ingest arxiv:2301.07041
/paperbase ingest --file /path/to/paper.pdf
/paperbase ingest --batch papers.txt
```

### Searching

```
/paperbase search "deep learning"
/paperbase search "transformer architecture" -n 20
```

### Status Management

```
/paperbase status
/paperbase status doi:10.1038/nature12373
/paperbase status --state ready
```

### Graph Operations

```
/paperbase graph update
/paperbase graph update --incremental
/paperbase graph update --force
/paperbase graph status
```

## Configuration

### Environment Variables

The skill automatically detects the PaperBase library location. To override:

```bash
export PAPERBASE_LIBRARY="/path/to/your/library"
```

### Custom Library Path

Edit `SKILL.md` and update the `library_path` parameter:

```yaml
library_path: "/custom/path/to/library"
```

## Troubleshooting

### Skill Not Found

```bash
# Verify installation
ls ~/.claude/skills/paperbase-skill/SKILL.md

# Reinstall
./skills/paperbase-skill/install.sh
```

### Library Path Not Detected

```bash
# Check current working directory
pwd

# Ensure you're in a PaperBase repository or set PAPERBASE_LIBRARY
export PAPERBASE_LIBRARY="/path/to/PaperBase"
```

### Permission Issues

```bash
# Make install script executable
chmod +x skills/paperbase-skill/install.sh

# Re-run installation
./skills/paperbase-skill/install.sh
```

## Architecture

The skill is a thin wrapper around the PaperBase CLI:
- Detects library context (current directory or `PAPERBASE_LIBRARY`)
- Translates natural language commands to CLI invocations
- Provides structured output for AI agent consumption

## Development

### Testing the Skill

```bash
# Test in Claude Code
# In any conversation: /paperbase --help

# Verify skill is loaded
# Look for "paperbase" in available skills list
```

### Updating the Skill

After modifying `SKILL.md`:

```bash
# Reinstall to global location
./skills/paperbase-skill/install.sh
```

## License

MIT License (same as PaperBase)
