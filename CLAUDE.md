# PaperBase - Claude 特定指南

## 项目简介

PaperBase 是论文知识库脚手架，核心理念：
- Canonical Markdown 是唯一 source of truth
- 幂等状态机管理论文处理
- 所有投影层（graph/registry）可重建

## 快速上手

**常见任务：**

1. **摄入新论文**（需要先安装 paper-fetch）
   ```bash
   # 安装 paper-fetch CLI（首次使用）
   uv tool install git+https://github.com/Dictation354/paper-fetch-skill.git
   
   # 摄入论文
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

## 外部工具依赖

**必需：**
- Python 3.11+
- uv 包管理器

**可选（按功能）：**
- **在线论文获取**: `uv tool install git+https://github.com/Dictation354/paper-fetch-skill.git`
  - **定位**: 外部 CLI 工具（黑盒调用）
  - **安装位置**: `~/.local/bin/paper-fetch`（全局 CLI）
  - **调用方式**: PaperBase 通过 `subprocess` 调用 `paper-fetch --format both`
  - **职责**: 从 DOI/arXiv/URL 获取论文内容和元数据
  - **验证**: `paper-fetch --version`（应显示 3.0.1+）
  - **备选**: 手动提供本地 PDF，使用 `paperbase ingest --file paper.pdf`
- **知识图谱**: `uv tool install graphify`
  - **定位**: 外部 CLI 工具
  - **职责**: 构建论文语义关联网络
  - **要求**: 需要配置 LLM（OPENAI_API_KEY, OPENAI_BASE_URL, model）
  - **验证**: `graphify --version`
- **Zotero 集成**: `uv tool install zotero-mcp-server`
  - 从 Zotero 导入论文

## Canonical Schema 位置

- Paper frontmatter: `src/paperbase/schemas/paper.py` - `PaperMetadata`
- Manifest: `src/paperbase/schemas/manifest.py` - `ManifestSchema`
- CSL JSON: `src/paperbase/schemas/csl.py` - `CSLItem`

## 验证规则

所有 schema 包含严格验证规则：
- 时间戳：ISO 8601 格式
- 年份：1000-2100
- SHA256：64 位小写十六进制
- 枚举：严格匹配

详见 `docs/schemas/validation-rules.md`。

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
3. **查看 registry/papers.db** 确认索引状态
4. **检查 .graphifyignore** 确保 Graphify 不扫描重复内容

## Skills 使用

**项目集成的 skill：**
- `paperbase`: 在 `skills/paperbase/`
  - PaperBase 专用的 Claude skill，提供论文摄入、状态管理等功能

**外部工具（通过 `uv tool install` 全局安装）：**
- `paper-fetch`: 从 DOI/arXiv/URL 获取论文
  - 安装: `uv tool install git+https://github.com/Dictation354/paper-fetch-skill.git`
  - 验证: `paper-fetch --version`
- `graphify`: 构建知识图谱
  - 安装: `uv tool install graphify`
  - 验证: `graphify --version`
- `zotero-mcp`: Zotero 集成
  - 安装: `uv tool install zotero-mcp-server`

**注意：** 外部工具安装在用户全局环境（如 `~/.local/bin/`），不在项目目录中。

## 测试

```bash
# 运行所有测试
uv run pytest

# 运行特定测试
uv run pytest tests/unit/test_schemas.py -v

# 测试覆盖率
uv run pytest --cov=paperbase --cov-report=html
```
