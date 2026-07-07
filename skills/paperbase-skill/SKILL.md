# PaperBase - Academic Paper Knowledge Base Management

## ⚠️ Skill Type: Reference Documentation + Lightweight Wrapper

**当前版本（v0.2）提供：**
1. **参考文档**：AI Agent 可阅读本文档了解可用命令
2. **包装器脚本**：`paperbase-wrapper.sh` (Unix) / `paperbase-wrapper.ps1` (Windows) 提供自动库路径检测

**使用方式：**
- AI Agent 构造命令：`paperbase-wrapper.sh <subcommand> <args>`
- 包装器自动检测库位置（当前目录、父目录、`$PAPERBASE_LIBRARY`）
- 无需手动 `cd` 到仓库根目录

**未来版本**将深度集成 MCP server 模式，支持智能错误处理和状态诊断。

---

Manage your academic paper knowledge base with structured ingestion, search, and graph operations.

## When to Use

Use this skill when the user wants to:
- Ingest papers from DOI, arXiv, PMID, or local PDF files
- Search full-text content across their paper library
- Check paper processing status and state
- Update or query the knowledge graph
- Manage their PaperBase library
- **Diagnose environment issues**
- **Get quick help with common operations**

## Quick Start

### Basic Commands (Most Common)

```bash
# Ingest a paper (open access recommended)
/paperbase ingest arxiv:1706.03762

# Check what papers you have
/paperbase status

# Search for content
/paperbase search "deep learning"

# Diagnose problems
/paperbase doctor
```

### For AI Agents

When invoking this skill, use the wrapper script for automatic path detection:

```bash
# Unix/Linux/macOS
paperbase-wrapper.sh <command> <args>

# Windows
paperbase-wrapper.ps1 <command> <args>
```

The wrapper automatically:
- ✅ Detects PaperBase library location (with configuration persistence)
- ✅ Remembers library paths across sessions (stores in `workspaces.json`)
- ✅ Validates uv is installed
- ✅ Navigates to repository root
- ✅ Executes the CLI command
- ✅ Compatible with both `~/.claude/skills` and `~/.codex/skills`

## Commands

### Ingest Papers

Ingest academic papers into the knowledge base:

```
/paperbase ingest <identifier>
/paperbase ingest --file <path>
/paperbase ingest --batch <file>
/paperbase ingest <identifier> --no-graph
```

**Examples:**
- `/paperbase ingest 10.1038/nature12373` - Ingest by DOI
- `/paperbase ingest arxiv:2301.07041` - Ingest by arXiv ID
- `/paperbase ingest --file paper.pdf` - Ingest local PDF
- `/paperbase ingest --batch papers.txt` - Batch ingest from file list
- `/paperbase ingest doi:10.1038/nature --no-graph` - Skip graph update

### Search Papers

Search full-text content with Boolean operators:

```
/paperbase search "<query>"
/paperbase search "<query>" -n <limit>
```

**Examples:**
- `/paperbase search "deep learning"` - Basic search
- `/paperbase search "transformer AND attention" -n 20` - Boolean search with limit
- `/paperbase search "neural OR network"` - OR operator

### Check Status

View paper status and processing state:

```
/paperbase status
/paperbase status <paper_id>
/paperbase status --state <state>
```

**Examples:**
- `/paperbase status` - List all papers
- `/paperbase status doi:10.1038/nature12373` - Check specific paper
- `/paperbase status --state ready` - Filter by state (discovered/resolved/source_ready/converted/normalized/validated/graphed/ready)

### Graph Operations

Manage the knowledge graph:

```
/paperbase graph update
/paperbase graph update --incremental
/paperbase graph update --force
/paperbase graph status
```

**Examples:**
- `/paperbase graph update` - Update graph with new papers
- `/paperbase graph update --incremental` - Only update changed papers
- `/paperbase graph update --force` - Force rebuild entire graph
- `/paperbase graph status` - View graph statistics

### Diagnostics

Check environment and dependencies:

```
/paperbase doctor
```

**Output includes:**
- ✅ Python version check (>= 3.11)
- ✅ uv availability
- ⚠️ graphify installation (optional)
- ✅ SQLite version (FTS5 support)
- ✅ Library location and paper count
- ✅ Registry database status
- ✅ Knowledge graph status

### Entity Management (NEW)

Update paper entities for structured queries and graph relationships:

```
/paperbase update <paper_id> --json '<entities_json>'
/paperbase update <paper_id> --merge --json '<entities_json>'
/paperbase update <paper_id> --output-json --json '<entities_json>'
```

**Entity Categories:**
- `methods`: Algorithms, models, techniques (e.g., SLAM, Transformer, submap)
- `datasets`: Training/evaluation datasets (e.g., ImageNet, KITTI, AQUALOC)
- `domains`: Application areas (e.g., AUV navigation, sentiment analysis, object detection)
- `platforms`: Hardware/software platforms (e.g., AUV, GPU, mobile device)
- `constraints`: Key limitations (e.g., underwater environment, real-time requirement)

**Examples:**
- `/paperbase update doi:10.1038/nature --json '{"methods": [{"name": "SLAM"}]}'` - Replace entities
- `/paperbase update arxiv:1706.03762 --merge --json '{"datasets": [{"name": "ImageNet"}]}'` - Append entities
- `/paperbase update doi:10.1038/nature --output-json --json '{"domains": [{"name": "CV"}]}'` - JSON output for parsing

**Entity Format:**
```json
{
  "methods": [
    {"name": "submap", "type": "mapping"},
    {"name": "Particle Filter", "type": "localization"}
  ],
  "datasets": [
    {"name": "AQUALOC"}
  ],
  "domains": [
    {"name": "AUV navigation"},
    {"name": "underwater SLAM"}
  ],
  "platforms": [
    {"name": "AUV"}
  ],
  "constraints": [
    {"name": "underwater environment"}
  ]
}
```

**Auto-Extract (Optional):**
If internal LLM is configured (`config/paperbase.yaml`), entities are automatically extracted during `ingest`:
- ✅ Extracts entities from paper abstract using LLM
- ✅ Normalizes terminology using `config/terminology.yaml`
- ⚠️ Optional: requires OpenAI-compatible API configuration

### Remove Papers

Permanently delete papers (hard delete, irreversible):

```
/paperbase remove <paper_id>
/paperbase remove <paper_id> --confirm
```

**Examples:**
- `/paperbase remove doi:10.1038/nature12373` - Delete with interactive confirmation
- `/paperbase remove arxiv:1706.03762 --confirm` - Delete without confirmation (dangerous)

**Warning:** This operation:
- ❌ Permanently deletes all files (paper.md, source PDF, metadata)
- ❌ Removes registry entries
- ❌ Cannot be undone
- ⚠️ Requires manual knowledge graph update after deletion

**Example:**
```
/paperbase doctor

# Output:
🔍 PaperBase Doctor - Environment Diagnostics
============================================================
✅ Python Version            Python 3.11.5
✅ uv Package Manager        uv 0.5.0
⚠️  graphify (optional)      graphify not found (optional)
✅ SQLite Version            SQLite 3.45.0 (FTS5 supported)
✅ PaperBase Library         Library found (12 papers)
✅ Registry Database         Registry database found (45.3 KB)
✅ Knowledge Graph           Knowledge graph found (3 files)
============================================================

✅ All required checks passed!
```

## Behavior

### Library Detection

The skill automatically detects the PaperBase library location:
1. Check current working directory for `library/` folder
2. Check `PAPERBASE_LIBRARY` environment variable
3. If not found, prompt user to navigate to PaperBase directory

### Output Format

All commands return structured output:
- Success: Confirmation message + relevant data (paper_id, storage_id, state)
- Error: Clear error message with troubleshooting hints
- Status: Formatted table or JSON output

### State Machine

Papers progress through states:
```
DISCOVERED → RESOLVED → SOURCE_READY → CONVERTED → NORMALIZED → VALIDATED → GRAPHED → READY
```

### Performance Notes

- Batch ingestion is 3-5x faster than individual ingestion
- Incremental graph updates reduce time from ~30s to ~3s (for 100 papers with 1 change)
- Use `--no-graph` for continuous ingestion, then run `graph update` once at the end

## Implementation

The skill executes PaperBase CLI commands using `uv run paperbase`:

```python
# Ingest example
command = f"uv run paperbase ingest {identifier}"
result = subprocess.run(command, shell=True, capture_output=True)

# Parse output and return structured response
```

### Error Handling

Common errors and solutions:
- **PDF not found**: Verify file path or DOI validity
- **State stuck in BLOCKED**: Check `manifest.json` error_log, manually reset state
- **Graph update timeout**: Use `--incremental` or increase timeout
- **Registry inconsistency**: Delete `registry/papers.sqlite` and rebuild

## Configuration

### Environment Variables

```bash
# Set custom library path
export PAPERBASE_LIBRARY="/path/to/PaperBase"

# Set timeout for long operations
export PAPERBASE_TIMEOUT=600
```

### Config File

Located at `config/paperbase.yaml` in the library root:

```yaml
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

graphify:
  auto_update: true
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

### Workflow 2: Batch Ingestion

```
User: "I have 10 papers in papers.txt, ingest them all"
Agent: /paperbase ingest --batch papers.txt

User: "Check the status"
Agent: /paperbase status

User: "Update the graph incrementally"
Agent: /paperbase graph update --incremental
```

### Workflow 3: Status Check

```
User: "Show me all papers in ready state"
Agent: /paperbase status --state ready

User: "Check the status of doi:10.1038/nature12373"
Agent: /paperbase status doi:10.1038/nature12373
```

## Notes

- Always run commands from the PaperBase repository root or set `PAPERBASE_LIBRARY`
- For batch operations, prefer `--batch` over multiple individual ingests
- Use `--incremental` for regular maintenance (much faster)
- The skill does not modify files directly, only invokes CLI commands
- All operations are logged in `manifest.json` for each paper

## Related Files

- [README.md](README.md) - Installation and configuration guide
- [../../AGENTS.md](../../AGENTS.md) - Agent working guidelines
- [../../CLAUDE.md](../../CLAUDE.md) - Claude-specific instructions
- [../../docs/graph-update-strategy.md](../../docs/graph-update-strategy.md) - Graph optimization details
