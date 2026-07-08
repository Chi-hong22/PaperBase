# PaperBase Data Architecture

Understanding how PaperBase organizes and manages knowledge.

## Core Principles

### 1. Canonical Markdown as Single Source of Truth

Every paper has ONE authoritative representation: `paper.md`

```
library/papers/{storage_id}/
├── paper.md          ← ONLY source of truth
├── manifest.json     ← State tracking + SHA256 hashes
└── source/
    └── source.pdf    ← Original material (preserved)
```

**Key insight**: All derived data (registry, graph) can be rebuilt from `paper.md`.

---

### 2. State Machine

Papers flow through a simplified 2-state machine:

```
PDF/DOI → NORMALIZED → READY
          (摄入规范化)  (加入图谱)
```

**State Definitions**:

| State | Meaning | Can Query? |
|-------|---------|-----------|
| `NORMALIZED` | Paper ingested, `paper.md` created | ❌ Registry only |
| `READY` | Added to graph, fully indexed | ✅ Both tracks |

**Exception States** (edge cases):
- `NEEDS_REVIEW` - Requires human review
- `BLOCKED` - Processing blocked
- `FAILED_RETRYABLE` - Temporary failure, can retry
- `FAILED_PERMANENT` - Permanent failure

**State Transitions**:
- `ingest` → `NORMALIZED`
- `graph update` → `READY`
- No backward transitions (monotonic)

---

### 3. Projection Layers (Rebuildable)

Two derived indexes built from `paper.md`:

#### Registry (SQLite)

**Purpose**: Fast structured queries

**Location**: `registry/papers.db`

**Data Source**: 
- `manifest.json` (state, timestamps)
- `paper.md` frontmatter (title, authors, year, doi)

**Schema**:
```sql
CREATE TABLE papers (
    paper_id TEXT PRIMARY KEY,
    storage_id TEXT NOT NULL,
    state TEXT NOT NULL,
    title TEXT,
    authors TEXT,  -- JSON array
    year INTEGER,
    doi TEXT,
    created_at TEXT,
    updated_at TEXT
);
```

**Rebuild Command**:
```bash
rm registry/papers.db
# Registry auto-rebuilds on next CLI command
```

#### Graph (Graphify)

**Purpose**: Semantic relationship queries

**Location**: `graph/`

**Data Source**: 
- All `library/papers/*/paper.md` files

**Rebuild Command**:
```bash
paperbase graph update --force
```

---

## Storage Structure

### Directory Layout

```
PaperBase/
├── library/
│   └── papers/
│       └── p_164622e0fc87/              # storage_id (derived from paper_id)
│           ├── paper.md                 # Canonical Markdown
│           ├── manifest.json            # State + provenance
│           ├── source/
│           │   └── source.pdf           # Original PDF
│           └── assets/                  # (optional) Extracted figures
│
├── registry/
│   └── papers.db                        # SQLite index (REBUILDABLE)
│
├── graph/
│   ├── graph.json                       # Knowledge graph (REBUILDABLE)
│   └── entities.jsonl                   # Entity index (REBUILDABLE)
│
└── config/
    └── paperbase.yaml                   # Configuration
```

### paper.md Structure

```markdown
---
schema_version: '1.0'
paper_id: doi:10.1109/access.2021.3088541
storage_id: p_164622e0fc87
title: "Bathymetric Particle Filter SLAM..."
authors:
- name: Qianyi Zhang
- name: Ye Li
year: 2021
language: en
abstract: "..."
keywords: []
source:
  discovery: manual
  fulltext_provider: markitdown
provenance:
  ingested_at: '2026-07-08T11:01:36.763752Z'
  converter:
    name: markitdown
---

# Paper Content

[Full markdown content here...]
```

### manifest.json Structure

```json
{
  "paper_id": "doi:10.1109/access.2021.3088541",
  "storage_id": "p_164622e0fc87",
  "state": "ready",
  
  "source_pdf": {
    "path": "./source/source.pdf",
    "sha256": "8e31939e055efa...",
    "acquired_at": "2026-07-08T11:01:36.763752Z"
  },
  
  "canonical_md": {
    "path": "./paper.md",
    "sha256": "6b77f95dfc7c24...",
    "schema_version": "1.0"
  },
  
  "pipeline": {
    "converter": "markitdown",
    "converter_version": "0.0.1",
    "normalizer_version": "1.0.0"
  },
  
  "graph": {
    "indexed": true,
    "updated_at": "2026-07-08T13:12:39.660119+00:00Z",
    "content_sha256_at_index": "6b77f95dfc7c24..."
  },
  
  "created_at": "2026-07-08T11:01:36.769454+00:00",
  "updated_at": "2026-07-08T13:12:39.660941+00:00"
}
```

---

## Content Addressing (SHA256)

### Why SHA256?

- Detects content changes for incremental updates
- Ensures data integrity
- Enables deduplication

### SHA256 Usage

| Hash Location | Purpose |
|--------------|---------|
| `source_pdf.sha256` | PDF integrity verification |
| `canonical_md.sha256` | Current paper.md content |
| `graph.content_sha256_at_index` | Content when last indexed |

**Incremental Update Logic**:
```python
if canonical_md.sha256 != graph.content_sha256_at_index:
    # Content changed, re-index this paper
    rebuild_graph_for_paper(paper_id)
```

---

## Data Consistency

### Invariants

1. **manifest ↔ registry consistency**: State must match
   - `manifest.json` state == `papers.db` state
   - Both updated atomically by CLI

2. **paper_id uniqueness**: One paper = one paper_id
   - DOI-based: `doi:10.1234/abc`
   - Fallback: `fallback:filename`

3. **storage_id stability**: Never changes after creation
   - Derived from paper_id via SHA256 hash
   - Directory name: `p_{first_12_chars_of_hash}`

### Consistency Checks

```bash
# Check manifest ↔ registry consistency
python -m scripts.check_consistency

# Rebuild registry from manifests
rm registry/papers.db
paperbase status  # Auto-rebuilds

# Rebuild graph from paper.md files
paperbase graph update --force
```

---

## Query Routing

### Dual-Track System

```
User Query
    ↓
Is Structured?
    ├─ Yes → Registry (SQLite)
    │        - doi:, state:, year:, author:
    │        - Fast, precise
    │
    └─ No  → Graphify (Semantic)
             - Natural language
             - Concept relationships
```

### Registry Queries (Structured)

**Strengths**:
- Fast (SQL index)
- Precise matching
- No LLM cost

**Limitations**:
- No semantic understanding
- Exact match only

**Examples**:
```python
# Pattern matching
doi:10.1234/abc        → get_paper(paper_id)
state:ready            → list_papers(state=READY)
year:2024              → filter(year=2024)
author:Zhang           → filter(authors__contains)
```

### Graphify Queries (Semantic)

**Strengths**:
- Semantic understanding
- Concept relationships
- Theme exploration

**Limitations**:
- Slower (LLM inference)
- Requires graphify + LLM
- Costs API tokens

**Examples**:
```python
"SLAM 相关论文"              → semantic_search()
"深度学习和计算机视觉"       → concept_intersection()
"水下导航技术演进"           → temporal_analysis()
```

---

## Performance Characteristics

### Storage

| Component | Typical Size | Growth Rate |
|-----------|-------------|-------------|
| paper.md | 50-500 KB | Linear with papers |
| source.pdf | 1-10 MB | Linear with papers |
| registry/papers.db | ~10 KB/paper | Linear |
| graph/ | ~50 KB/paper | Linear |

**100 papers**: ~1 GB total

### Query Speed

| Operation | Typical Time |
|-----------|-------------|
| Registry query | < 100 ms |
| Full-text search | < 500 ms |
| Graphify query | 2-5 seconds |
| Graph update (incremental) | 3-10 seconds |
| Graph update (full) | 30-60 seconds |

---

## Backup & Recovery

### What to Backup

**Essential** (cannot be rebuilt):
- `library/papers/*/paper.md`
- `library/papers/*/source/source.pdf`
- `library/papers/*/manifest.json`
- `config/paperbase.yaml`

**Optional** (can be rebuilt):
- `registry/papers.db` → rebuild from manifests
- `graph/` → rebuild with `graph update --force`

### Recovery Procedure

```bash
# 1. Restore library/ and config/
cp -r backup/library/ .
cp -r backup/config/ .

# 2. Rebuild registry
rm -f registry/papers.db
paperbase status  # Auto-rebuilds

# 3. Rebuild graph
paperbase graph update --force
```

---

## Schema Versioning

### Current Version

`schema_version: "1.0"` (in paper.md frontmatter)

### Migration Strategy

When schema changes:
1. New version increments: `1.0` → `1.1`
2. CLI reads both versions
3. Migration script converts old → new
4. Old versions deprecated after 2 releases

**No breaking changes to `paper.md`** - it's the source of truth.

---

## Design Rationale

### Why Not Store Metadata in Database?

❌ **Bad**: Metadata in SQLite, paper.md is just text
✅ **Good**: Metadata in paper.md frontmatter, SQLite is projection

**Reason**: 
- Single source of truth
- Git-friendly (plain text)
- Human-readable
- Tool-independent

### Why Two Query Tracks?

Registry alone: No semantic understanding  
Graphify alone: Slow for simple queries

**Both together**: Fast precise queries + semantic exploration

### Why Graphify External?

- Specialized tool, well-maintained
- Supports multiple LLM providers
- Can be upgraded independently
- PaperBase stays focused on paper management
