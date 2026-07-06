# PaperBase Phase 4: 增强摄入实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 增强摄入能力，支持 DOI/arXiv ID/URL 输入，批量摄入，增量更新，以及生成 chunks 和 references。

**Architecture:** 扩展现有 ingest 命令，集成 paper-fetch-skill 获取远程 PDF，支持批量处理和并发限流，实现判重逻辑，生成结构化的检索和引用数据。

**Tech Stack:**
- paper-fetch-skill (git clone 到 skills/)
- concurrent.futures (并发处理)
- 已有：PaperRegistry, identity, normalizer

## Global Constraints

- 继承 Phase 1-3 的所有约束
- paper-fetch-skill 通过 git clone 安装到 skills/ 目录
- 不得使用 Sci-Hub 绕过付费墙（scihub_enabled=false）
- 批量摄入支持并发，但需要限流（max_workers=3）
- 增量更新通过 paper_id 判重
- chunks 和 references 生成不阻塞主流程
- 遵循 TDD：先写测试，再写实现

---

## Phase 4: 增强摄入

### Task 1: 集成 paper-fetch-skill

**Files:**
- Create: `src/paperbase/adapters/paper_fetch_adapter.py`
- Create: `tests/unit/test_paper_fetch_adapter.py`
- Create: `skills/README.md` (更新安装说明)

**Interfaces:**
- Consumes: paper_id (DOI/arXiv/URL)
- Produces:
  - `fetch_paper_pdf(paper_id: str, output_dir: Path) -> dict`
  - 返回：`{"success": bool, "pdf_path": Path | None, "error": str | None}`

**实现说明：**
由于 paper-fetch-skill 的具体 API 未知，此 Task 采用简化实现：
1. 优先使用 arXiv API（对于 arXiv ID）
2. 对于 DOI，返回建议用户手动下载
3. 为后续集成 paper-fetch-skill 预留接口

**Task 完成后效果：**
- 支持 `paperbase ingest arxiv:2401.12345`
- 对于 DOI，提示用户提供 PDF 路径

---

### Task 2: 实现批量摄入

**Files:**
- Modify: `src/paperbase/cli/commands/ingest.py` (添加 --batch 选项)
- Create: `tests/integration/test_batch_ingest.py`

**Interfaces:**
- Consumes: 文件列表（paper_list.txt，每行一个 paper_id 或 PDF 路径）
- Produces: `paperbase ingest --batch paper_list.txt`

**实现说明：**
1. 读取输入文件
2. 使用 ThreadPoolExecutor 并发处理（max_workers=3）
3. 使用 rich.progress 显示进度
4. 收集失败项，最后汇总报告

---

### Task 3: 实现增量更新

**Files:**
- Modify: `src/paperbase/cli/commands/ingest.py` (添加 --update 和判重逻辑)
- Create: `src/paperbase/core/deduplication.py`

**Interfaces:**
- Consumes: paper_id, PaperRegistry
- Produces:
  - `is_paper_ingested(paper_id: str, registry: PaperRegistry) -> bool`
  - `paperbase ingest --update <input>`

**实现说明：**
1. 在摄入前检查 registry 是否已有该 paper_id
2. 如果已存在且 state >= NORMALIZED，跳过
3. 如果 --update 未指定，默认跳过已存在的论文
4. 支持 --force 强制重新摄入

---

### Task 4: 生成 chunks.jsonl

**Files:**
- Create: `src/paperbase/core/chunker.py`
- Create: `tests/unit/test_chunker.py`

**Interfaces:**
- Consumes: paper.md 内容
- Produces:
  - `generate_chunks(markdown: str, paper_id: str) -> list[dict]`
  - 输出：`library/papers/<storage_id>/chunks.jsonl`

**实现说明：**
1. 按段落或固定 token 数分块
2. 每个 chunk 包含：id, paper_id, content, position
3. 输出 JSONL 格式（每行一个 JSON 对象）

---

### Task 5: 生成 references.jsonl

**Files:**
- Create: `src/paperbase/core/reference_extractor.py`
- Create: `tests/unit/test_reference_extractor.py`

**Interfaces:**
- Consumes: paper.md 的 frontmatter (citations 字段)
- Produces:
  - `extract_references(metadata: PaperMetadata) -> list[dict]`
  - 输出：`library/papers/<storage_id>/references.jsonl`

**实现说明：**
1. 从 PaperMetadata.citations 提取引用
2. 每个引用包含：title, authors, year, doi
3. 输出 JSONL 格式

---

### Task 6: 集成测试

**Files:**
- Create: `tests/integration/test_enhanced_ingestion.py`
- Create: `scripts/verify_phase4.py`

**实现说明：**
1. 端到端测试批量摄入
2. 验证 chunks 和 references 生成
3. 验证增量更新逻辑

---

## 验收标准

- [ ] `paperbase ingest arxiv:2401.12345` 可用
- [ ] `paperbase ingest --batch paper_list.txt` 可用
- [ ] 支持 --update 增量更新模式
- [ ] 生成 chunks.jsonl
- [ ] 生成 references.jsonl
- [ ] 批量摄入有进度显示
- [ ] 判重逻辑正确

---

## 后续工作

### Phase 5: 搜索和查询
- 实现全文检索（基于 chunks.jsonl）
- 集成 Zotero MCP
- 实现语义搜索
- 实现图谱查询 API

---

**计划编写完成。** 🎉
