# PaperBase - Claude 特定指南

## 项目简介

PaperBase 是论文知识库脚手架，核心理念：
- Canonical Markdown 是唯一 source of truth
- 幂等状态机管理论文处理
- 所有投影层（graph/registry）可重建

## 快速上手

**常见任务：**

1. **摄入新论文**
   ```bash
   paperbase ingest "doi:10.1038/nature"
   ```

2. **检查论文状态**
   ```bash
   paperbase status "doi:10.1038/nature"
   ```

3. **更新知识图谱**
   ```bash
   paperbase graph update
   ```

## Canonical Schema 位置

- Paper frontmatter: `src/paperbase/schemas/paper.py` - `PaperMetadata`
- Manifest: `src/paperbase/schemas/manifest.py` - `ManifestSchema`
- CSL JSON: `src/paperbase/schemas/csl.py` - `CSLItem`

## 修改边界

**可修改：**
- 实现新的 adapter（`src/paperbase/adapters/`）
- 添加新的 CLI 命令（`src/paperbase/cli/`）
- 扩展 schema 字段（向后兼容）

**不可修改（除非明确要求）：**
- Canonical Schema 的核心字段（schema_version/paper_id/storage_id）
- 状态机转换规则
- Invariants（AGENTS.md 中列出的）
- library/ 目录结构

## 调试建议

1. **查看 manifest.json** 确认状态
2. **检查 paper.md frontmatter** 是否通过 schema 验证
3. **查看 registry/papers.sqlite** 确认索引状态
4. **检查 .graphifyignore** 确保 Graphify 不扫描重复内容

## Skills 使用

项目集成的 skills：
- `paper-fetch-skill`: 在 `skills/paper-fetch-skill/`
- `citation-check-skill`: 在 `skills/citation-check-skill/`
- `zotero-mcp`: 通过 MCP 调用（全局安装）
- `graphify`: 通过 MCP 调用（全局安装）

**注意：** graphify 和 zotero-mcp 使用 `uv tool install` 全局安装，不在项目目录中。

## 测试

```bash
# 运行所有测试
uv run pytest

# 运行特定测试
uv run pytest tests/unit/test_schemas.py -v

# 测试覆盖率
uv run pytest --cov=paperbase --cov-report=html
```
