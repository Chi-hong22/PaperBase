# PaperBase - Academic Paper Knowledge Base Management

## Skill Type: Command Wrapper + Query Router

**功能：**
1. **命令包装器**：自动检测库路径，执行 CLI 命令
2. **查询路由**：智能路由结构化查询（Registry）和语义查询（Graphify）

**使用方式：**
- 结构化查询：`/paperbase doi:10.1234/abc`、`/paperbase state:ready`
- 语义查询：`/paperbase SLAM 相关论文`
- CLI 命令：`paperbase-wrapper.sh ingest "doi:10.1234/abc"`

---

## When to Use

Use this skill when the user wants to:
- Ingest papers from DOI, arXiv, PMID, or local PDF files
- Search full-text content across their paper library
- Check paper processing status and state
- Update or query the knowledge graph
- Manage their PaperBase library
- Diagnose environment issues

## Query Routing

The skill intelligently routes queries:

**Structured Queries** (Registry):
- `doi:`, `paper_id:` prefix
- `state:`, `year:`, `author:` prefix
- `list`, `show all` keywords

**Semantic Queries** (Graphify):
- Natural language queries
- Concept and relationship queries
- Topic exploration

## Commands

### Ingest Papers

Ingest academic papers into the knowledge base:

```bash
/paperbase ingest <identifier>
/paperbase ingest --file <path>
/paperbase ingest --batch <file>
/paperbase ingest <identifier> --no-graph
```

**Examples:**
- `/paperbase ingest 10.1038/nature12373` - Ingest by DOI
- `/paperbase ingest arxiv:2301.07041` - Ingest by arXiv ID
- `/paperbase ingest --file paper.pdf` - Ingest local PDF
- `/paperbase ingest --batch papers.txt` - Batch ingest

**Options:**
- `--no-graph` - Skip automatic graph update

### Search Papers

Search full-text content:

```bash
/paperbase search "<query>"
/paperbase search "<query>" -n <limit>
```

**Examples:**
- `/paperbase search "deep learning"`
- `/paperbase search "transformer AND attention" -n 20`

### Check Status

View paper status:

```bash
/paperbase status
/paperbase status <paper_id>
/paperbase status --state <state>
```

**States:** `normalized`, `ready`

**Examples:**
- `/paperbase status` - List all papers
- `/paperbase status doi:10.1038/nature12373` - Check specific paper
- `/paperbase status --state ready` - Filter by state

### Graph Operations

Manage the knowledge graph:

```bash
/paperbase graph update
/paperbase graph update --incremental
/paperbase graph update --force
/paperbase graph status
```

**Examples:**
- `/paperbase graph update` - Update graph with new papers
- `/paperbase graph update --incremental` - Only update changed papers
- `/paperbase graph update --force` - Force rebuild entire graph

### Query Papers

Query papers using CLI (advanced parameters):

```bash
paperbase-wrapper.sh query related <paper_id> --depth <N>
paperbase-wrapper.sh query topic "<topic>"
```

**Examples:**
- `paperbase-wrapper.sh query related doi:10.1038/nature01 --depth 2`
- `paperbase-wrapper.sh query topic "deep learning"`

**Or use natural language via /paperbase:**
- `/paperbase doi:10.1038/nature01 相关论文`
- `/paperbase 深度学习主题`

### Configuration

Manage configuration:

```bash
/paperbase config show
/paperbase config check-llm
/paperbase config path
```

### Diagnostics

Check environment:

```bash
/paperbase doctor
```

**Output includes:**
- Python version check (>= 3.11)
- uv availability
- graphify installation (optional)
- SQLite FTS5 support
- Library status

### Remove Papers

Permanently delete papers:

```bash
/paperbase remove <paper_id>
/paperbase remove <paper_id> --confirm
```

**Warning:** This operation is irreversible.

## Wrapper Scripts

For AI Agents, use the wrapper scripts for automatic path detection:

```bash
# Unix/Linux/macOS
paperbase-wrapper.sh <command> <args>

# Windows
paperbase-wrapper.ps1 <command> <args>
```

The wrapper automatically:
- ✅ Detects PaperBase library location
- ✅ Validates uv installation
- ✅ Navigates to repository root
- ✅ Executes CLI commands
- ✅ Remembers library paths (workspaces.json)

## State Machine

Papers progress through simplified states:

```
NORMALIZED → READY
```

**NORMALIZED**: Paper ingested and normalized  
**READY**: Added to knowledge graph, ready for queries

## Performance Notes

- Batch ingestion is 3-5x faster than individual ingestion
- Incremental graph updates reduce time from ~30s to ~3s
- Use `--no-graph` for continuous ingestion, then run `graph update` once

## Configuration

### Environment Variables

```bash
export PAPERBASE_LIBRARY="/path/to/PaperBase"
export PAPERBASE_TIMEOUT=600
```

### Config File

Located at `config/paperbase.yaml`:

```yaml
llm:
  base_url: ${PAPERBASE_LLM_BASE_URL}
  api_key: ${PAPERBASE_LLM_API_KEY}
  model: ${PAPERBASE_LLM_MODEL}

graph:
  auto_update: on_ingest
```

## Examples

### Workflow 1: Single Paper

```
User: "Ingest this paper: 10.1038/s41586-021-03819-2"
Agent: /paperbase ingest 10.1038/s41586-021-03819-2

User: "Search for mentions of 'neural networks'"
Agent: /paperbase search "neural networks"

User: "Update the knowledge graph"
Agent: /paperbase graph update
```

### Workflow 2: Natural Language Query

```
User: "列出所有已就绪的论文"
Agent: /paperbase state:ready

User: "找到关于 SLAM 的论文"
Agent: /paperbase SLAM

User: "doi:10.1038/nature 的相关论文"
Agent: /paperbase doi:10.1038/nature
```

### Workflow 3: Batch Ingestion

```
User: "I have 10 papers in papers.txt, ingest them all"
Agent: /paperbase ingest --batch papers.txt

User: "Check the status"
Agent: /paperbase status

User: "Update the graph incrementally"
Agent: /paperbase graph update --incremental
```

## Notes

- Always run from PaperBase repository root or set `PAPERBASE_LIBRARY`
- For batch operations, prefer `--batch` over multiple individual ingests
- Use `--incremental` for regular maintenance
- All operations are logged in `manifest.json` for each paper

## Related Files

- [README.md](README.md) - Installation guide
- [../../AGENTS.md](../../AGENTS.md) - Agent guidelines
- [../../CLAUDE.md](../../CLAUDE.md) - Claude instructions
