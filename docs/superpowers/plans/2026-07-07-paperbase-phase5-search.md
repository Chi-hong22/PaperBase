# PaperBase Phase 5: 搜索和查询实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现多模态搜索和查询功能，包括全文检索、语义搜索、图谱查询，集成 Zotero MCP。

**Architecture:** 基于 Phase 4 生成的 chunks.jsonl 实现全文检索，集成 Zotero MCP 进行文献管理，使用 graphify 的图谱输出实现关系查询。

**Tech Stack:**
- SQLite FTS5 (全文检索)
- zotero-mcp (全局安装)
- graphify 图谱输出
- 已有：PaperRegistry, chunks, graph

## Global Constraints

- 继承 Phase 1-4 的所有约束
- zotero-mcp 使用全局安装（uv tool install zotero-mcp-server）
- 全文检索基于 SQLite FTS5
- 语义搜索为可选功能（需要 embedding 模型）
- 图谱查询基于 graphify 的 JSON 输出
- 搜索结果返回 paper_id 列表 + 相关性分数
- 遵循 TDD：先写测试，再写实现

---

## Phase 5: 搜索和查询

### Task 1: 实现全文检索

**Files:**
- Create: `src/paperbase/core/search_engine.py`
- Create: `tests/unit/test_search_engine.py`

**Interfaces:**
- Consumes: chunks.jsonl, query string
- Produces:
  - `search_fulltext(query: str, limit: int = 10) -> list[dict]`
  - 返回：`[{"paper_id": str, "score": float, "snippet": str}]`

**实现说明：**
1. 构建 FTS5 索引（从 chunks.jsonl）
2. 支持布尔查询（AND/OR/NOT）
3. 返回 paper_id + 匹配片段

---

### Task 2: 实现 search 命令

**Files:**
- Create: `src/paperbase/cli/commands/search.py`
- Modify: `src/paperbase/cli/main.py` (注册命令)

**Interfaces:**
- Consumes: search_fulltext()
- Produces: `paperbase search "machine learning"`

**实现说明：**
1. 调用 search_fulltext()
2. 从 registry 获取论文元数据
3. 使用 rich.table 显示结果

---

### Task 3: 集成 Zotero MCP

**Files:**
- Create: `src/paperbase/adapters/zotero_adapter.py`
- Create: `tests/unit/test_zotero_adapter.py`

**Interfaces:**
- Consumes: paper_id, PaperMetadata
- Produces:
  - `export_to_zotero(paper_metadata: PaperMetadata) -> bool`
  - `import_from_zotero(collection_id: str) -> list[str]`

**实现说明：**
1. 调用 zotero-mcp CLI
2. 导出：将 PaperMetadata 转换为 Zotero 格式
3. 导入：从 Zotero 获取 paper_id 列表

---

### Task 4: 实现图谱查询

**Files:**
- Create: `src/paperbase/core/graph_query.py`
- Create: `tests/unit/test_graph_query.py`

**Interfaces:**
- Consumes: graph/ 目录的 JSON 文件
- Produces:
  - `find_related_papers(paper_id: str, depth: int = 1) -> list[str]`
  - `find_papers_by_topic(topic: str) -> list[str]`

**实现说明：**
1. 解析 graphify 输出的 JSON
2. 实现简单的图遍历
3. 返回相关 paper_id 列表

---

### Task 5: 实现 query 命令

**Files:**
- Create: `src/paperbase/cli/commands/query.py`
- Modify: `src/paperbase/cli/main.py` (注册命令)

**Interfaces:**
- Consumes: find_related_papers(), find_papers_by_topic()
- Produces:
  - `paperbase query related <paper_id>`
  - `paperbase query topic <topic>`

**实现说明：**
1. 调用图谱查询函数
2. 从 registry 获取论文元数据
3. 使用 rich.table 显示结果

---

### Task 6: 集成测试

**Files:**
- Create: `tests/integration/test_search_workflow.py`
- Create: `scripts/verify_phase5.py`

**实现说明：**
1. 端到端测试搜索流程
2. 验证 Zotero 集成
3. 验证图谱查询

---

## 验收标准

- [ ] `paperbase search "query"` 可用
- [ ] `paperbase query related <paper_id>` 可用
- [ ] `paperbase query topic <topic>` 可用
- [ ] Zotero 导入/导出功能可用
- [ ] FTS5 索引正确构建
- [ ] 搜索结果包含相关性分数
- [ ] 图谱查询返回正确的相关论文

---

**计划编写完成。** 🎉
