# PaperBase

<div align="center">

**Transform academic papers into structured knowledge assets**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-198%20passed-brightgreen.svg)](tests/)
[![Code style: Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Security](https://img.shields.io/badge/security-11%20fixes-orange.svg)](#security-improvements)

English | [中文文档](README.md)

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

### Retrieval Architecture: Why Both SQLite FTS5 and Knowledge Graph?

**Different purposes, complementary strengths**:

| Dimension | SQLite FTS5 (Full-Text Search) | Graphify (Knowledge Graph) |
|-----------|-------------------------------|---------------------------|
| **Search Target** | Find papers containing specific keywords | Discover relationships and paths between papers |
| **Query Type** | "Find all papers mentioning 'transformer'" | "Find 5 papers closest to this one by citation" |
| **Indexed Content** | Full text (title, abstract, body) | Relationships (citations, co-authors, topics) |
| **Query Complexity** | O(log N), inverted index | O(N), graph traversal |
| **Results** | Document list + matched snippets | Relationship network + path distances |
| **Typical Use** | Keyword search, Boolean queries, fuzzy matching | Literature review, citation analysis, concept tracing |

**Real-world examples**:

```bash
# FTS5: "Which papers discuss attention mechanisms?"
uv run paperbase search "attention mechanism"
# Returns: List of papers containing these words, ranked by relevance

# Graphify: "What's the research lineage related to the Transformer paper?"
uv run paperbase query related "doi:10.48550/arXiv.1706.03762" --depth 2
# Returns: Citation tree, co-citation network
```

**Why not use only graph?**
- Graphs excel at relationship queries but not full-text semantic matching
- Graph traversal is expensive (O(N)) vs FTS5's inverted index (O(log N))
- Graphs require structured relationships; FTS5 handles arbitrary text

**Why not use only FTS5?**
- FTS5 returns matching documents but can't discover implicit relationships
- Can't answer "shortest citation path between these papers"
- Can't support "domain landscape view" for literature reviews

**Conclusion**:
- **FTS5 = Fast Locating** ("Find")
- **Graphify = Relationship Discovery** ("Understand")
- **Combined = Complete Knowledge Base Capability**

For full documentation, see [README.md (Chinese)](README.md).

## 📜 License

MIT License

## 🙏 Acknowledgments

This project benefits from the following open-source tools and projects:

### Core Dependencies
- [markitdown](https://github.com/microsoft/markitdown) - Microsoft's Markdown conversion tool
- [PyMuPDF](https://pymupdf.readthedocs.io/) - PDF processing library
- [Pydantic](https://docs.pydantic.dev/) - Data validation and schema management
- [paper-fetch-skill](https://github.com/Dictation354/paper-fetch-skill) - Online paper fetching and conversion

### External Tool Integration
- [uv](https://github.com/astral-sh/uv) - Fast Python package manager by Astral
- [Graphify](https://github.com/graphify-ai/graphify) - Knowledge graph construction tool
- [Zotero](https://www.zotero.org/) - Reference management software
- [Zotero MCP Server](https://github.com/modelcontextprotocol/servers/tree/main/src/zotero) - Zotero MCP integration service

### Development Tools
- [Ruff](https://github.com/astral-sh/ruff) - Extremely fast Python linter and formatter
- [pytest](https://docs.pytest.org/) - Python testing framework

---

<div align="center">
Made with ❤️ by researchers, for researchers
</div>
