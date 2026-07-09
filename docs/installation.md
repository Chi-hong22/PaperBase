# PaperBase 安装指南

## 核心安装

### 1. 克隆项目

```bash
git clone https://github.com/Chi-hong22/PaperBase.git
cd PaperBase
```

### 2. 安装 Python 依赖

**要求：** Python 3.11+

```bash
# 安装 uv（如果未安装）
pip install uv

# 安装项目依赖
uv sync
```

### 3. 验证安装

```bash
uv run paperbase doctor
```

应该看到：
```
✅ Python Version
✅ uv Package Manager
✅ SQLite Version
✅ PaperBase Library
✅ Registry Database
```

---

## 外部工具（可选）

PaperBase 采用 **外部黑盒工具** 架构，将专门功能委托给独立工具。

### paper-fetch-skill（在线论文获取）

**作用：** 从 DOI、arXiv ID、URL 获取论文内容和元数据

**推荐安装方式：**
```bash
uv tool install git+https://github.com/Dictation354/paper-fetch-skill.git
```

**验证：**
```bash
paper-fetch --version
```

**备选方案：**
如果不使用在线获取，可以手动提供本地 PDF：
```bash
uv run paperbase ingest --file /path/to/paper.pdf
```

---

### graphify（知识图谱）

**定位**: 外部 CLI 工具
**职责**: 构建论文之间的语义关联网络
**要求**: 需要配置 LLM API

**安装：**
```bash
uv tool install graphify
```

**验证：**
```bash
graphify --version
# 应显示: graphify 0.9.10+
```

**配置 LLM（必需）：**

graphify 需要 LLM 进行语义抽取，必须配置以下环境变量：

```bash
# 方式 1: 使用 OpenAI 兼容 API
export PAPERBASE_LLM_BASE_URL="https://api.openai.com/v1"
export PAPERBASE_LLM_API_KEY="sk-..."
export PAPERBASE_LLM_MODEL="gpt-4o-mini"

# 方式 2: 使用其他提供商（如 Anthropic、Gemini 等）
export PAPERBASE_LLM_BASE_URL="https://api.anthropic.com/v1"
export PAPERBASE_LLM_API_KEY="sk-ant-..."
export PAPERBASE_LLM_MODEL="claude-3-5-sonnet-20241022"
```

**重要说明：**
- PaperBase 会自动将配置传递给 graphify（通过 `--backend openai --model <model>`）
- 必须使用支持的模型名称（不能使用默认的 `gpt-4.1-mini`）
- 配置存储在 `config/paperbase.yaml` 中

**验证配置：**
```bash
uv run paperbase config check-llm
```

---

### zotero-mcp（Zotero 集成）

**作用：** 从 Zotero 文献管理器导入论文

**安装：**
```bash
uv tool install zotero-mcp-server
```

---

## 架构说明

### 为什么使用外部工具？

PaperBase 遵循 **Unix 哲学**：每个工具做好一件事。

**职责划分：**
- **PaperBase**: 知识库管理（规范化存储、状态机、图谱、查询）
- **paper-fetch**: 论文获取（多 provider、PDF 处理、元数据提取）
- **graphify**: 知识图谱构建（语义分析、关系抽取）
- **zotero-mcp**: Zotero 集成（文献导入）

**优点：**
- 维护负担低（各工具独立更新）
- 代码简洁（PaperBase 只需 adapter 层）
- 灵活性高（可切换工具、多源支持）
- 符合 YAGNI 原则

---

## 工作流示例

### 完整工作流（需要 paper-fetch + graphify）

```bash
# 1. 安装工具
uv tool install git+https://github.com/Dictation354/paper-fetch-skill.git
uv tool install graphify

# 2. 配置 LLM（graphify 需要）
export PAPERBASE_LLM_API_KEY="sk-..."

# 3. 摄入论文
uv run paperbase ingest "10.1038/s41586-021-03819-2"

# 4. 更新图谱
uv run paperbase graph update

# 5. 查询论文
uv run paperbase status
```

### 最小工作流（仅本地 PDF）

```bash
# 1. 只安装 PaperBase
uv sync

# 2. 摄入本地 PDF
uv run paperbase ingest --file paper.pdf

# 3. 查询论文
uv run paperbase status
```

---

## 故障排查

### paper-fetch 找不到

**症状：**
```
paper-fetch CLI is not available
```

**解决：**
```bash
# 方法 1: 全局安装（推荐）
uv tool install git+https://github.com/Dictation354/paper-fetch-skill.git

# 方法 2: 项目依赖
cd PaperBase
uv sync --extra online-fetch

# 验证
paper-fetch --version
```

### graphify 找不到

**症状：**
```
⚠️ graphify (optional) not found
```

**解决：**
```bash
uv tool install graphify
graphify --version
```

### LLM API 配置错误

**症状：**
```
LLM Configuration: disabled
```

**解决：**
```bash
# 设置环境变量
export PAPERBASE_LLM_BASE_URL="https://api.openai.com/v1"
export PAPERBASE_LLM_API_KEY="sk-your-key-here"
export PAPERBASE_LLM_MODEL="gpt-4o-mini"

# 验证
uv run paperbase config check-llm
```

---

## 高级配置

### 自定义 paper-fetch 安装位置

如果 paper-fetch 安装在非标准位置，确保它在 PATH 中：

```bash
# Windows
$env:PATH += ";C:\path\to\paper-fetch"

# Linux/macOS
export PATH="$PATH:/path/to/paper-fetch"
```

### 使用 paper-fetch 项目依赖模式

如果你不想全局安装 paper-fetch：

```bash
cd PaperBase
uv sync --extra online-fetch
```

这会将 paper-fetch 安装到项目虚拟环境，但 CLI 调用仍然有效。

---

## 数据流架构

```
查询（DOI/arXiv/URL）
    ↓
paper-fetch CLI (外部工具)
    ├─ 多 provider 支持
    ├─ PDF 处理
    └─ 元数据提取
    ↓
JSON 输出
    ↓
PaperBase Adapter (数据转换)
    ├─ 规范化为 Canonical Schema
    ├─ 生成 paper.md
    └─ 更新 manifest.json
    ↓
Canonical Markdown (唯一真相源)
    ↓
    ├─ Registry (SQLite 索引)
    └─ Graph (Graphify 图谱)
```

**关键点：**
- PaperBase 不关心 paper-fetch 的实现细节
- 只依赖 CLI 接口契约（`--format both` 输出 JSON）
- adapter 层负责数据格式转换
- 投影层（registry/graph）可从 paper.md 重建

---

## 参考文档

- **架构说明**: `AGENTS.md` - 项目架构和工作流
- **使用指南**: `CLAUDE.md` - Claude Agent 特定指南
- **CLI 命令**: `src/paperbase/cli/` - 所有 CLI 命令实现
- **Schema 定义**: `src/paperbase/schemas/` - 数据结构定义

---

**版本**: 1.0.0  
**最后更新**: 2026-07-09  
**维护者**: Chi-hong22
