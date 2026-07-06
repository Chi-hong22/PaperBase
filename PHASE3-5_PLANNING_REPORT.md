# PaperBase Phase 3-5 规划完成报告

**日期：** 2026-07-07  
**状态：** 计划编写完成，等待 Codex 审核

---

## 执行总结

### ✅ 已完成的工作

**1. Phase 3-5 计划编写**
- ✅ Phase 3: 图谱集成 (`docs/superpowers/plans/2026-07-07-paperbase-phase3-graph.md`)
- ✅ Phase 4: 增强摄入 (`docs/superpowers/plans/2026-07-07-paperbase-phase4-enhanced-ingestion.md`)
- ✅ Phase 5: 搜索和查询 (`docs/superpowers/plans/2026-07-07-paperbase-phase5-search.md`)

**2. Codex 审核启动**
- 🔄 Phase 2 阻塞问题修复（运行中，26分钟）
- 🔄 Phase 3 计划审核（运行中，11分钟，phase: verifying）

**3. 计划结构**
每个 Phase 都包含：
- Global Constraints（继承前序约束）
- 详细的 Task 分解
- TDD 流程（测试 → 失败 → 实现 → 通过 → 提交）
- 验收标准
- 后续工作说明

---

## Phase 3: 图谱集成

### 目标
将 NORMALIZED 状态的论文推进到 GRAPHED 状态

### 核心 Task
1. **Task 1**: Graphify Adapter - 调用全局 graphify 命令
2. **Task 2**: graph update 命令 - 更新知识图谱，更新 manifest 状态
3. **Task 3**: 集成测试 - 端到端验证

### 关键设计
- graphify 使用全局安装（`uv tool install graphify`）
- 只扫描 `library/papers/**/paper.md`
- 图谱输出到 `graph/` 目录
- 支持 `--force` 重建
- 幂等操作（重复运行安全）

### 验收标准
- `paperbase graph update` 命令可用
- manifest.json 的 state 变为 GRAPHED
- manifest.json 包含 graph.indexed = true
- graph/ 目录生成图谱文件

---

## Phase 4: 增强摄入

### 目标
支持 DOI/arXiv ID/URL 输入，批量摄入，增量更新，生成 chunks 和 references

### 核心 Task
1. **Task 1**: 集成 paper-fetch-skill（简化实现，优先 arXiv API）
2. **Task 2**: 批量摄入（`--batch` 选项，并发处理）
3. **Task 3**: 增量更新（判重逻辑，`--update` 选项）
4. **Task 4**: 生成 chunks.jsonl（用于检索）
5. **Task 5**: 生成 references.jsonl（结构化引用）
6. **Task 6**: 集成测试

### 关键设计
- paper-fetch-skill 通过 git clone 安装
- 并发处理（ThreadPoolExecutor，max_workers=3）
- 判重通过 paper_id 在 registry 中查询
- chunks 按段落或固定 token 数分块
- references 从 PaperMetadata.citations 提取

### 验收标准
- `paperbase ingest arxiv:2401.12345` 可用
- `paperbase ingest --batch paper_list.txt` 可用
- 支持 `--update` 增量更新
- 生成 chunks.jsonl 和 references.jsonl
- 批量摄入有进度显示

---

## Phase 5: 搜索和查询

### 目标
实现全文检索、语义搜索、图谱查询，集成 Zotero MCP

### 核心 Task
1. **Task 1**: 全文检索（SQLite FTS5 索引）
2. **Task 2**: search 命令（`paperbase search "query"`）
3. **Task 3**: 集成 Zotero MCP（导入/导出）
4. **Task 4**: 图谱查询（基于 graphify 输出）
5. **Task 5**: query 命令（`paperbase query related/topic`）
6. **Task 6**: 集成测试

### 关键设计
- FTS5 索引基于 chunks.jsonl
- zotero-mcp 使用全局安装
- 图谱查询解析 graphify 的 JSON 输出
- 支持布尔查询（AND/OR/NOT）
- 搜索结果包含相关性分数

### 验收标准
- `paperbase search "query"` 可用
- `paperbase query related <paper_id>` 可用
- `paperbase query topic <topic>` 可用
- Zotero 导入/导出功能可用
- FTS5 索引正确构建
- 图谱查询返回相关论文

---

## 计划审核流程

根据你的要求，每个 Phase 的执行流程：

1. **编写计划** ✅ （Phase 3-5 已完成）
2. **Codex 审核** 🔄 （Phase 3 审核中）
3. **根据反馈调整计划**
4. **执行计划**（使用 subagent-driven-development）
5. **遇到阻塞问题调用 Codex rescue**

---

## 当前阻塞问题

### Phase 2 阻塞（Codex 修复中）

**问题：**
1. uv sync 网络超时（markitdown[pdf] 依赖）
2. git commit 持续超时
3. ingest 命令缺少 PDF 依赖

**Codex 状态：** 运行中（26分钟），正在诊断和修复

### Phase 3 计划审核（Codex 验证中）

**审核要点：**
- graphify 命令行参数正确性
- GraphInfo schema 是否已定义
- 状态转换逻辑
- 接口设计完整性
- 幂等性保证

**Codex 状态：** verifying 阶段（11分钟）

---

## 下一步行动

### 等待 Codex 完成

1. **Phase 2 修复**
   - 应用 Codex 的修复方案
   - 验证 ingest 命令可用
   - 完成 Phase 2 验收

2. **Phase 3 审核**
   - 查看 Codex 的 P0/P1/P2 反馈
   - 修复 P0 问题（必须修复）
   - 应用 P1 建议（强烈推荐）

### 执行 Phase 3

审核通过后：
1. 使用 subagent-driven-development 执行计划
2. Task 1: Graphify Adapter
3. Task 2: graph update 命令
4. Task 3: 集成测试
5. 验收并进入 Phase 4

### 迭代 Phase 4-5

根据 Phase 3 的经验：
1. 调整 Phase 4-5 计划（如需要）
2. Codex 审核 Phase 4
3. 执行 Phase 4
4. Codex 审核 Phase 5
5. 执行 Phase 5

---

## 技术债务和优化点

### Phase 4 简化

由于 paper-fetch-skill 的具体 API 未知，Task 1 采用简化实现：
- 优先使用 arXiv API
- DOI 暂时提示用户手动下载
- 预留接口供后续集成

### Phase 5 可选功能

- 语义搜索需要 embedding 模型（可选）
- 图谱查询功能依赖 graphify 输出格式
- Zotero 集成需要验证 MCP 可用性

---

## 总结

**Phase 3-5 的计划已完整编写**，遵循以下原则：
1. ✅ TDD 流程（测试 → 失败 → 实现 → 通过 → 提交）
2. ✅ 详细的步骤分解（每步 2-5 分钟）
3. ✅ 完整的代码示例（无 placeholder）
4. ✅ 明确的验收标准
5. ✅ 继承前序 Phase 的约束

**等待 Codex 审核完成后，即可开始执行 Phase 3。** 🎉

---

**报告生成时间：** 2026-07-07  
**Orchestrator：** Claude Fable 5
