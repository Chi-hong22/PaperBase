# PaperBase

<div align="center">

**Transform academic papers into structured knowledge assets**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-77%20passed-brightgreen.svg)](tests/)
[![Code style: Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

[English](#) | [中文文档](#)

</div>

---

## 📖 What is PaperBase?

PaperBase is an **academic paper knowledge base scaffold** designed for the AI era. It solves a critical limitation of traditional reference managers (Zotero, Mendeley): **the inability to transform papers into machine-understandable structured knowledge**.

When researchers need to extract key concepts from hundreds of papers, trace methodological evolution, or build domain knowledge graphs, existing tools only provide PDF files and metadata. PaperBase provides:

- 📝 **Canonical Markdown** with full semantic structure
- 🔗 **Rebuildable knowledge graph** projections (paper relationship networks)
- 🔄 **Idempotent processing pipeline** (interruptible, resumable, traceable)
- 🤖 **AI Agent friendly** (CLI + structured output)

## ✨ Key Features

| Feature | Description |
|---------|-------------|
| **Canonical Markdown as Source of Truth** | All derived data (graphs, indexes, chunks) can be rebuilt from normalized Markdown files |
| **Content-Addressed Storage** | PDFs stored by SHA256 hash, eliminating duplication |
| **Idempotent State Machine** | Paper processing (download → convert → normalize → graph) is interruptible and resumable |
| **Incremental Graph Updates** | Detect content changes via SHA256 comparison, update only modified papers |
| **Batch Ingestion Mode** | Delay graph updates until all papers are ingested (3-5x faster) |
| **Full-Text Search** | SQLite FTS5-powered search with Boolean operators |
| **Schema Validation** | Pydantic-based strict validation (timestamps, enums, SHA256, ranges) |
| **Tool Agnostic** | Works with AI agents and traditional scripts alike |

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (Python package manager)
- Git

### Installation

```bash
# Clone the repository
git clone https://github.com/Chi-hong22/PaperBase.git
cd PaperBase

# Install dependencies
uv sync

# Install global tools
uv tool install graphify           # Knowledge graph builder
uv tool install zotero-mcp-server  # Zotero integration (optional)

# Verify installation
graphify --version
uv run paperbase --help
```

### Your First Paper

```bash
# Ingest a paper (supports DOI, arXiv, PMID, local PDF)
uv run paperbase ingest "10.1038/s41586-021-03819-2"

# Check status
uv run paperbase status "doi:10.1038/s41586-021-03819-2"

# Search content
uv run paperbase search "deep learning"

# Update knowledge graph
uv run paperbase graph update
```

Papers are stored as `library/papers/<storage_id>/paper.md` with structured frontmatter.

## 📂 Repository Structure

```
paperbase/
├── library/                   # Knowledge base
│   ├── sources/pdf/          # Content-addressed PDF storage (SHA256)
│   ├── papers/               # Normalized papers
│   │   └── p_<storage_id>/  # Single paper
│   │       ├── paper.md      # Canonical Markdown (source of truth)
│   │       ├── manifest.json # State and provenance
│   │       ├── chunks.jsonl  # Search chunks (derived)
│   │       └── references.jsonl # Structured citations (derived)
│   ├── collections/          # User collections
│   └── notes/                # User notes
├── registry/                 # SQLite query index (derived)
├── graph/                    # Graphify knowledge graph (derived)
├── src/paperbase/           # Python package
├── skills/paperbase-skill/  # Global AI agent skill
└── tests/                    # Test suite
```

**Important**: Only `library/papers/*/paper.md` and `manifest.json` are source of truth—everything else is rebuildable.

## 🎯 Use Cases

| Use Case | Description |
|----------|-------------|
| **Personal Knowledge Base** | Build a searchable, graph-based academic library |
| **AI Agent Data Source** | Provide structured paper data for LLM applications |
| **Team Collaboration** | Git-based version control for literature management |
| **Domain Knowledge Graph** | Analyze citation networks and methodological evolution |

## 📋 Usage

### Ingesting Papers

```bash
# Via DOI
uv run paperbase ingest "10.1038/nature12373"

# Via arXiv
uv run paperbase ingest "arxiv:2301.07041"

# Via local PDF
uv run paperbase ingest --file paper.pdf

# Batch ingestion (recommended for multiple papers)
cat > papers.txt << EOF
/path/to/paper1.pdf
/path/to/paper2.pdf
/path/to/paper3.pdf
EOF

uv run paperbase ingest --batch papers.txt

# Skip automatic graph update (for continuous ingestion)
uv run paperbase ingest paper.pdf --no-graph
```

### Searching and Querying

```bash
# View all papers
uv run paperbase status

# View papers in specific state
uv run paperbase status --state ready

# Full-text search
uv run paperbase search "transformer architecture" -n 20

# Search in Zotero (requires zotero-mcp)
uv run paperbase search --zotero "quantum computing"
```

### Knowledge Graph

```bash
# Update graph (process newly ingested papers)
uv run paperbase graph update

# Incremental update (only changed papers)
uv run paperbase graph update --incremental

# Force rebuild graph
uv run paperbase graph update --force

# View graph status
uv run paperbase graph status
```

**Graph Update Strategy**:
- Default: Auto-update after each ingestion
- Batch mode: Delay update until all papers ingested
- Incremental: Only process papers with content changes (recommended for maintenance)

See [docs/graph-update-strategy.md](docs/graph-update-strategy.md) for details.

## 🤖 AI Agent Integration

### Global Skill Installation

PaperBase provides a global skill for AI agents (Claude Code, Codex):

```bash
# Run one-command setup
./skills/paperbase-skill/install.sh

# Or manual installation
# For Claude Code / Codex:
cp -r skills/paperbase-skill ~/.claude/skills/
```

After installation, invoke with `/paperbase` in any AI agent session:

```
/paperbase ingest "10.1038/nature12373"
/paperbase search "deep learning"
/paperbase status
```

See [skills/paperbase-skill/README.md](skills/paperbase-skill/README.md) for detailed configuration.

## 🏗️ Architecture

### State Machine

Papers progress through a state machine (defined in `manifest.json`):

```
DISCOVERED → RESOLVED → SOURCE_READY → CONVERTED → NORMALIZED → VALIDATED → GRAPHED → READY
```

- **DISCOVERED**: Paper identifier recognized (DOI/arXiv/etc.)
- **SOURCE_READY**: PDF downloaded
- **CONVERTED**: PDF converted to initial Markdown
- **NORMALIZED**: Markdown normalized (conforms to schema)
- **VALIDATED**: Passed schema validation
- **GRAPHED**: Added to knowledge graph
- **READY**: Usable state

### Core Modules

- **`core/identity.py`**: paper_id normalization and storage_id generation
- **`core/paths.py`**: Path management (with security validation)
- **`core/manifest.py`**: State machine and provenance management
- **`core/normalizer.py`**: Markdown normalizer
- **`core/registry.py`**: SQLite index (with context manager support)
- **`core/search_engine.py`**: Full-text search (FTS5)
- **`adapters/`**: External tool adapters (PDF extraction, conversion, Graphify)

### Design Decisions

**Why not just use Zotero?**
- Zotero excels at reference management but isn't ideal for AI agents: difficult to graph, coarse search granularity, uncontrollable schema
- PaperBase complements Zotero: import via MCP, but store as structured Markdown

**Why Markdown instead of JSON?**
- Markdown is human and AI friendly, supports rich text and images, easy to version control
- JSON for metadata (manifest.json), Markdown for content (paper.md)

**Why separate PDF storage?**
- Content addressing (SHA256) eliminates duplication, same PDF can be referenced by multiple paper metadata entries
- Supports multi-source scenarios: same paper from arXiv, journal, conference

## 🧪 Development

### Running Tests

```bash
# Run all tests
uv run pytest

# Run specific tests
uv run pytest tests/unit/test_identity.py -v

# View coverage
uv run pytest --cov=paperbase --cov-report=html
open htmlcov/index.html
```

### Code Style

```bash
# Check formatting
uv run ruff check src/

# Auto-fix
uv run ruff check --fix src/
```

### Extending Adapters

To support new paper sources or formats, create a new adapter:

```python
# src/paperbase/adapters/my_adapter.py
from pathlib import Path

def fetch_from_source(identifier: str) -> Path:
    """
    Fetch paper from custom source
    
    Returns:
        Path: Downloaded PDF path
    """
    # Implementation
    pass
```

Then register the new command in CLI.

## 🔧 Troubleshooting

### PDF Conversion Failure

```bash
# Error: Empty conversion result
# Cause: Scanned PDF or encrypted PDF
# Solution: Preprocess with OCR tool or manually edit paper.md
```

### State Stuck in BLOCKED

```bash
# Check error_log in manifest.json
uv run paperbase status <paper_id>

# Manually fix, then reset state
# Edit manifest.json, change state to previous state, then re-run
```

### Slow Graphify Updates

```bash
# Use incremental update (recommended)
uv run paperbase graph update --incremental

# Skip auto-update during batch ingestion
uv run paperbase ingest --batch papers.txt

# Force rebuild if graph corrupted (time-consuming)
uv run paperbase graph update --force
```

**Performance**:
- Incremental update: 1 modified paper out of 100, ~30s → ~3s
- Batch ingestion: 10 papers, 3-5x faster than individual ingestion

### Registry Data Inconsistency

```bash
# Registry can be rebuilt
rm registry/papers.sqlite
uv run paperbase status  # Auto-rebuild index
```

## ⚙️ Configuration

Main config: `config/paperbase.yaml`

```yaml
project:
  name: "PaperBase"
  version: "0.1.0"

paths:
  library: "library"
  registry: "registry"
  graph: "graph"

adapters:
  paper_fetch:
    enabled: true
  zotero:
    enabled: true
    local_mode: true
  scansci:
    enabled: false
    scihub_enabled: false  # Disable Sci-Hub
    require_authorized_access: true

graphify:
  auto_update: true
  ignore_patterns:
    - "sources/"
    - "registry/"
```

## 🤝 Contributing

Contributions welcome! Before submitting:
1. Run tests to ensure passing
2. Follow code style (Ruff)
3. Update relevant documentation

## 📜 License

MIT License

## 🔗 Links

- [AGENTS.md](AGENTS.md) - Agent working guide (must-read)
- [CLAUDE.md](CLAUDE.md) - Claude-specific guide
- [Graphify](https://github.com/your-org/graphify) - Knowledge graph tool
- [Zotero MCP](https://github.com/your-org/zotero-mcp-server) - Zotero integration

## 🙏 Acknowledgments

- [markitdown](https://github.com/microsoft/markitdown) - Microsoft's Markdown conversion tool
- [PyMuPDF](https://pymupdf.readthedocs.io/) - PDF processing library

---

<div align="center">
Made with ❤️ by researchers, for researchers
</div>
