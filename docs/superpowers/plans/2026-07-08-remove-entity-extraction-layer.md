# 移除实体提取层架构重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构 PaperBase 架构，移除实体提取中间层，建立 Registry（结构查询）和 Graph（语义查询）的正交双轨系统

**Architecture:** 
- 删除 EntityManager 实体提取职责和相关命令（extract/update/build-entities）
- 简化状态机：NORMALIZED → VALIDATED → READY 简化为 NORMALIZED → READY
- graphify 为唯一图谱工具，删除 EntityGraphBuilder 降级逻辑
- 创建统一 paperbase skill，内部智能路由到 registry 或 graphify

**Tech Stack:** Python 3.12+, Click, Pydantic, graphify, SQLite

## Global Constraints

- Python 版本: ≥3.12
- 所有文件使用 UTF-8 编码
- 遵循项目现有代码风格
- 每个 task 完成后必须运行测试验证
- Git commit 遵循 Conventional Commits 规范
- 所有数据修改前必须备份

---

### Task 1: 数据迁移 - VALIDATED 状态论文

**Files:**
- Create: scripts/migrate_validated_to_normalized.py

**Interfaces:**
- Consumes: 现有 library/ 中处于 VALIDATED 状态的论文
- Produces: 所有 VALIDATED 论文迁移到 NORMALIZED 状态

- [ ] Step 1.1: 创建迁移脚本 scripts/migrate_validated_to_normalized.py
- [ ] Step 1.2: 运行迁移脚本 (uv run python scripts/migrate_validated_to_normalized.py)
- [ ] Step 1.3: 验证迁移结果 (paperbase status)
- [ ] Step 1.4: Commit (git commit -m "chore: migrate VALIDATED papers to NORMALIZED")

---

### Task 2: 简化状态机 - 删除 VALIDATED 状态

**Files:**
- Modify: src/paperbase/schemas/manifest.py:18-30
- Modify: AGENTS.md

**Interfaces:**
- Consumes: Task 1 迁移后的数据
- Produces: PaperState 枚举只包含 NORMALIZED, READY 和异常状态

- [ ] Step 2.1: 修改 PaperState 枚举，删除 VALIDATED
- [ ] Step 2.2: 更新 AGENTS.md 状态机文档
- [ ] Step 2.3: 验证语法
- [ ] Step 2.4: Commit

---

### Task 3: 移除 ingest 命令中的实体提取调用

**Files:**
- Modify: src/paperbase/cli/commands/ingest.py:146-182

**Interfaces:**
- Consumes: PaperState.NORMALIZED (from Task 2)
- Produces: ingest 命令不再调用实体提取

- [ ] Step 3.1: 删除实体提取代码块 (第 146-182 行)
- [ ] Step 3.2: 更新步骤编号
- [ ] Step 3.3: 验证 (uv run python -m py_compile src/paperbase/cli/commands/ingest.py)
- [ ] Step 3.4: Commit

---

### Task 4: 删除 graph 命令中的降级逻辑和 build-entities

**Files:**
- Modify: src/paperbase/cli/commands/graph.py:106-135,154,200-end

**Interfaces:**
- Consumes: PaperState.NORMALIZED (from Task 2)
- Produces: graph update 只调用 graphify；删除 build-entities 命令

- [ ] Step 4.1: 删除 EntityGraphBuilder 降级逻辑 (第 106-135 行)
- [ ] Step 4.2: 更新状态判断 (只检查 NORMALIZED)
- [ ] Step 4.3: 删除 build_entities 命令 (第 200 行到末尾)
- [ ] Step 4.4: 移除 EntityGraphBuilder 导入
- [ ] Step 4.5: 验证 (paperbase graph --help)
- [ ] Step 4.6: Commit

---

### Task 5: 删除实体提取命令和相关文件

**Files:**
- Delete: src/paperbase/cli/commands/extract.py
- Delete: src/paperbase/cli/commands/update.py
- Delete: src/paperbase/core/entity_manager.py
- Delete: src/paperbase/adapters/entity_graph_builder.py
- Modify: src/paperbase/cli/__init__.py

**Interfaces:**
- Consumes: 无
- Produces: 移除 extract、update 命令注册

- [ ] Step 5.1: 备份要删除的文件
- [ ] Step 5.2: 删除文件 (git rm ...)
- [ ] Step 5.3: 更新 CLI 命令注册
- [ ] Step 5.4: 验证 (paperbase --help)
- [ ] Step 5.5: Commit

---

### Task 6: 删除 schema 中的 entities 字段

**Files:**
- Modify: src/paperbase/schemas/paper.py

**Interfaces:**
- Consumes: 无
- Produces: PaperMetadata 不再包含 entities 字段

- [ ] Step 6.1: 备份现有 paper.md 的 entities 字段到 .backup/entities_backup.json
- [ ] Step 6.2: 删除 entities 字段定义
- [ ] Step 6.3: 验证 (from paperbase.schemas.paper import PaperMetadata)
- [ ] Step 6.4: Commit

---

### Task 7: 创建统一 paperbase skill

**Files:**
- Create: skills/paperbase/SKILL.md
- Create: skills/paperbase/skill.py
- Create: skills/paperbase/__init__.py

**Interfaces:**
- Consumes: PaperRegistry, graphify CLI
- Produces: /paperbase 统一查询接口

- [ ] Step 7.1: 验证 Registry API (inspect.signature)
- [ ] Step 7.2: 创建 skill 目录 (mkdir -p skills/paperbase)
- [ ] Step 7.3: 编写 SKILL.md (使用说明和路由规则)
- [ ] Step 7.4: 编写 skill.py (智能路由逻辑)
- [ ] Step 7.5: 创建 __init__.py
- [ ] Step 7.6: Commit

---

### Task 8: 状态更新完整性审计

**Files:**
- Audit: src/paperbase/cli/commands/ingest.py
- Audit: src/paperbase/cli/commands/graph.py

**Interfaces:**
- Consumes: 所有前面的修改
- Produces: 确认状态更新覆盖所有路径

- [ ] Step 8.1: 检查 ingest 状态更新 (grep manifest.state + registry.register_paper)
- [ ] Step 8.2: 检查 graph 状态更新 (grep manifest.state + registry.update_state)
- [ ] Step 8.3: 端到端测试 (ingest → status → graph update → status)
- [ ] Step 8.4: Commit (如有修复)

---

### Task 9: 清理测试和文档

**Files:**
- Delete: tests/unit/test_entity_extraction.py (if exists)
- Modify: README.md
- Modify: AGENTS.md

**Interfaces:**
- Consumes: 所有前面的修改
- Produces: 测试通过，文档更新

- [ ] Step 9.1: 删除实体提取相关测试
- [ ] Step 9.2: 运行测试套件 (uv run pytest -v)
- [ ] Step 9.3: 更新 README.md (删除 extract/update 说明)
- [ ] Step 9.4: 更新 AGENTS.md (补充查询双轨系统)
- [ ] Step 9.5: Commit

---

## 实施顺序

1. Task 1: 数据迁移 (必须最先)
2. Task 2-6: 串行执行
3. Task 7: 创建 skill (可与 Task 6 并行)
4. Task 8: 审计 (在 Task 2-6 完成后)
5. Task 9: 清理 (最后执行)

## 成功标准

- [ ] 所有 VALIDATED 论文已迁移
- [ ] 状态机只有 NORMALIZED 和 READY
- [ ] graphify 为唯一图谱工具
- [ ] /paperbase skill 正常工作
- [ ] 所有测试通过
- [ ] 文档反映新架构

## 回滚方案

如需回滚：
1. 恢复备份文件 (.backup/entity-extraction/)
2. git revert 重构相关的 commits
3. 运行数据恢复脚本

