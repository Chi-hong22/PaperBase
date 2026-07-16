# PaperBase Skills

本目录用于存放项目级 skills（如果需要）。

## 外部工具说明

PaperBase 使用**外部黑盒工具**架构，核心功能通过 CLI 调用独立工具：

### paper-fetch-skill
- **定位**: 外部 CLI 工具（黑盒调用）
- **安装位置**: 全局（`~/.local/bin/paper-fetch`）
- **调用方式**: CLI (`paper-fetch --format both`)
- **职责**: 论文获取、元数据提取、PDF 处理
- **安装**: `uv tool install git+https://github.com/Dictation354/paper-fetch-skill.git`
- **验证**: `paper-fetch --version`（应显示 3.0.1）
- **数据流**: `subprocess → JSON → PaperBase Adapter → Canonical Markdown`

### graphify
- **定位**: 外部 CLI 工具
- **安装位置**: 全局（`~/.local/bin/graphify`）
- **调用方式**: Agent 优先使用 `/graphify library/papers --update --no-viz`；手动 headless 备用路径使用 `paperbase graph update`
- **职责**: 知识图谱构建、语义分析
- **安装**: `uv tool install graphify`
- **验证**: `graphify --version`（应显示 0.9.10+）
- **要求**: Agent 路径不读取 PaperBase 本地 LLM 配置；headless 路径读取 `config/paperbase.yaml`

### zotero-mcp
- **定位**: 外部 MCP 服务
- **安装位置**: 全局
- **调用方式**: MCP 协议
- **职责**: Zotero 文献管理器集成
- **安装**: `uv tool install zotero-mcp-server`

## 架构原理

**为什么使用外部工具？**

PaperBase 遵循 **Unix 哲学**：每个工具做好一件事。

**职责划分：**
- **PaperBase**: 知识库管理（规范化存储、状态机、索引、查询）
- **paper-fetch**: 论文获取（多 provider、浏览器渲染、PDF 降级）
- **graphify**: 知识图谱（语义抽取、关系推理）
- **zotero-mcp**: Zotero 集成（文献导入）

**优点：**
- ✅ 维护负担低（各工具独立更新）
- ✅ 代码简洁（adapter 层只需转换数据）
- ✅ 灵活性高（可切换工具版本）
- ✅ 符合 YAGNI 原则（不重复造轮子）

## 注意事项

**这些工具不需要安装到以下位置：**
- ❌ `~/.claude/skills/` - Claude Code 的 Skill 定义目录（用于对话式调用）
- ❌ 本项目的 `skills/` 目录 - 仅用于项目特定的 skill 定义

**正确的安装位置：**
- ✅ 全局 CLI 工具：`~/.local/bin/` (通过 `uv tool install`)
- ✅ 只要命令在 PATH 中，PaperBase 就能调用

## 目录结构验证

**当前平面 Canonical + 同名资源目录结构：**
```
library/papers/
  ├── p_2ddac761b162.md      # Canonical Markdown（内容真相源）
  ├── p_2ddac761b162/
  │   ├── manifest.json      # 元数据和状态
  │   ├── references.jsonl   # 引用数据
  │   ├── source/            # 原始 PDF
  │   │   └── source.pdf
  │   └── assets/            # 图片资源
  │       ├── figure-001.png
  │       └── ...
  └── ...
```

**验证结果：**
- ✅ Graphify 只扫描 `p_*.md` Canonical，资源目录不会重复进入 corpus
- ✅ `.gitignore` 可排除本地论文内容，`.graphifyignore` 用 `!p_*.md` 独立重新纳入扫描
- ✅ `BLOCKED` Canonical 由精确 ignore 规则排除，不进入增量建图

## 相关文档

- [docs/installation.md](../docs/installation.md) - 完整安装指南
- [AGENTS.md](../AGENTS.md) - 项目架构和工作流
- [CLAUDE.md](../CLAUDE.md) - Claude Agent 使用指南
