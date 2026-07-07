# PaperBase

<div align="center">

**将学术论文转化为可复用的知识资产**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-77%20passed-brightgreen.svg)](tests/)
[![Code style: Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

[English](README_EN.md) | 中文文档

</div>

---

## 📖 PaperBase 是什么？

PaperBase 是专为 AI 时代设计的**学术论文知识库脚手架**，解决传统文献管理工具（Zotero、Mendeley）的核心痛点：**无法将论文转化为机器可理解的结构化知识**。

当研究者需要从数百篇论文中提取关键概念、追溯方法演进、构建领域知识图谱时，现有工具只能提供 PDF 文件和元数据。PaperBase 提供：

- 📝 **规范化 Markdown 文档**，包含完整语义结构
- 🔗 **可重建的知识图谱**投影（论文关系网络）
- 🔄 **幂等处理流程**（可中断、可恢复、可追溯）
- 🤖 **AI Agent 友好接口**（CLI + 结构化输出）

## ✨ 核心特性

| 特性 | 说明 |
|------|------|
| **Canonical Markdown 作为唯一真相源** | 所有派生数据（图谱、索引、分块）均可从规范化 Markdown 重建 |
| **内容寻址存储** | PDF 通过 SHA256 哈希存储，消除重复 |
| **幂等状态机** | 论文处理（下载 → 转换 → 规范化 → 图谱化）可中断和恢复 |
| **增量图谱更新** | 通过 SHA256 比对检测内容变化，仅更新修改的论文 |
| **批量摄入模式** | 延迟图谱更新至全部摄入完成（速度提升 3-5 倍） |
| **全文检索** | SQLite FTS5 驱动的搜索引擎，支持布尔运算符 |
| **Schema 验证** | 基于 Pydantic 的严格验证（时间戳、枚举、SHA256、范围） |
| **工具无关** | 同时适用于 AI Agent 和传统脚本 |

## 🚀 快速开始

### 环境要求

- Python 3.11+
- [uv](https://github.com/astral-sh/uv)（Python 包管理器）
- Git

### 安装

```bash
# 克隆仓库
git clone https://github.com/Chi-hong22/PaperBase.git
cd PaperBase

# 安装依赖
uv sync

# 安装全局工具
uv tool install graphify           # 知识图谱构建工具
uv tool install zotero-mcp-server  # Zotero 集成（可选）

# 验证安装
graphify --version
uv run paperbase --help
```

### 摄入第一篇论文

```bash
# 摄入论文（支持 DOI、arXiv、PMID、本地 PDF）
uv run paperbase ingest "10.1038/s41586-021-03819-2"

# 查看状态
uv run paperbase status "doi:10.1038/s41586-021-03819-2"

# 搜索内容
uv run paperbase search "deep learning"

# 更新知识图谱
uv run paperbase graph update
```

论文存储为 `library/papers/<storage_id>/paper.md`，带有结构化 frontmatter。

## 📂 仓库结构

```
paperbase/
├── library/                   # 知识库主体
│   ├── sources/pdf/          # 内容寻址的 PDF 存储（SHA256）
│   ├── papers/               # 规范化论文
│   │   └── p_<storage_id>/  # 单篇论文
│   │       ├── paper.md      # Canonical Markdown（真相源）
│   │       ├── manifest.json # 状态和溯源信息
│   │       ├── chunks.jsonl  # 检索分块（派生）
│   │       └── references.jsonl # 结构化引用（派生）
│   ├── collections/          # 用户论文集合
│   └── notes/                # 用户笔记
├── registry/                 # SQLite 查询索引（派生）
├── graph/                    # Graphify 知识图谱（派生）
├── src/paperbase/           # Python 包
├── skills/paperbase-skill/  # 全局 AI Agent skill
└── tests/                    # 测试套件
```

**重要**：只有 `library/papers/*/paper.md` 和 `manifest.json` 是真相源，其他均可重建。

## 🎯 适用场景

| 场景 | 说明 |
|------|------|
| **个人知识库** | 构建可搜索、可图谱化的学术文库 |
| **AI Agent 数据源** | 为 LLM 应用提供结构化论文数据 |
| **团队协作** | 基于 Git 的文献管理版本控制 |
| **领域知识图谱** | 分析引用网络和方法论演进 |

## 📋 使用方法

### 摄入论文

```bash
# 通过 DOI
uv run paperbase ingest "10.1038/nature12373"

# 通过 arXiv
uv run paperbase ingest "arxiv:2301.07041"

# 本地 PDF
uv run paperbase ingest --file paper.pdf

# 批量摄入（推荐用于多篇论文）
cat > papers.txt << EOF
/path/to/paper1.pdf
/path/to/paper2.pdf
/path/to/paper3.pdf
EOF

uv run paperbase ingest --batch papers.txt

# 跳过自动图谱更新（连续摄入时使用）
uv run paperbase ingest paper.pdf --no-graph
```

### 搜索和查询

```bash
# 查看所有论文
uv run paperbase status

# 查看特定状态的论文
uv run paperbase status --state ready

# 全文搜索
uv run paperbase search "transformer architecture" -n 20

# 在 Zotero 中搜索（需要 zotero-mcp）
uv run paperbase search --zotero "quantum computing"
```

### 知识图谱

```bash
# 更新图谱（处理新摄入的论文）
uv run paperbase graph update

# 增量更新（仅更新内容变化的论文）
uv run paperbase graph update --incremental

# 强制重建图谱
uv run paperbase graph update --force

# 查看图谱状态
uv run paperbase graph status
```

**图谱更新策略**：
- 默认：单篇摄入后自动更新图谱
- 批量模式：延迟至全部摄入完成后统一更新
- 增量更新：仅处理内容发生变化的论文（推荐定期维护）

详见 [docs/graph-update-strategy.md](docs/graph-update-strategy.md)。

## 🤖 AI Agent 集成

### 全局 Skill 安装

PaperBase 提供全局 skill，适配 Claude Code 和 Codex：

```bash
# 一键安装
./skills/paperbase-skill/install.sh

# 或手动安装
# 适用于 Claude Code / Codex:
cp -r skills/paperbase-skill ~/.claude/skills/
```

安装后在任意 AI Agent 会话中调用 `/paperbase`：

```
/paperbase ingest "10.1038/nature12373"
/paperbase search "deep learning"
/paperbase status
```

详见 [skills/paperbase-skill/README.md](skills/paperbase-skill/README.md)。

## 🏗️ 架构说明

### 状态机

论文通过状态机处理（定义在 `manifest.json` 中）：

```
DISCOVERED → RESOLVED → SOURCE_READY → CONVERTED → NORMALIZED → VALIDATED → GRAPHED → READY
```

- **DISCOVERED**: 识别论文标识（DOI/arXiv 等）
- **SOURCE_READY**: PDF 已下载
- **CONVERTED**: PDF 已转换为初步 Markdown
- **NORMALIZED**: Markdown 已规范化（符合 schema）
- **VALIDATED**: 通过 schema 验证
- **GRAPHED**: 已加入知识图谱
- **READY**: 可用状态

### 核心模块

- **`core/identity.py`**: paper_id 规范化和 storage_id 生成
- **`core/paths.py`**: 路径管理（带安全验证）
- **`core/manifest.py`**: 状态机和溯源管理
- **`core/normalizer.py`**: Markdown 规范化器
- **`core/registry.py`**: SQLite 索引（支持上下文管理器）
- **`core/search_engine.py`**: 全文检索（FTS5）
- **`adapters/`**: 外部工具适配器（PDF 提取、转换、Graphify）

### 检索架构：为什么同时需要 SQLite FTS5 和知识图谱？

**定位不同，互为补充**：

| 维度 | SQLite FTS5（全文检索） | Graphify（知识图谱） |
|------|-------------------------|---------------------|
| **检索目标** | 查找包含特定关键词的论文 | 发现论文之间的关系和路径 |
| **查询类型** | "找到所有提到 'transformer' 的论文" | "找到与这篇论文引用关系最近的 5 篇" |
| **索引内容** | 论文全文（标题、摘要、正文） | 论文间关系（引用、共同作者、主题） |
| **查询复杂度** | O(log N)，基于倒排索引 | O(N)，图遍历算法 |
| **返回结果** | 文档列表 + 匹配片段 | 关系网络 + 路径距离 |
| **典型场景** | 关键词搜索、布尔查询、模糊匹配 | 文献综述、引用分析、概念追溯 |

**实际使用示例**：

```bash
# FTS5: "哪些论文讨论了注意力机制？"
uv run paperbase search "attention mechanism"
# 返回：包含这些词的论文列表，按相关性排序

# Graphify: "与 Transformer 论文相关的研究脉络是什么？"
uv run paperbase query related "doi:10.48550/arXiv.1706.03762" --depth 2
# 返回：引用树、被引用树、共同引用的论文网络
```

**为什么不能只用图谱？**
- 图谱擅长关系查询，但不擅长全文语义匹配
- 图遍历成本高（O(N)），而 FTS5 倒排索引是 O(log N)
- 图谱需要结构化关系数据（引用、作者），FTS5 可处理任意文本

**为什么不能只用 FTS5？**
- FTS5 只返回匹配文档，无法发现论文间的隐含关系
- 无法回答"这两篇论文的最短引用路径"类问题
- 无法支持文献综述的"领域全景视图"

**结论**：
- **FTS5 = 快速定位**（"找到"）
- **Graphify = 关系发现**（"理解"）
- **组合使用 = 完整知识库能力**

### 设计决策

**为什么不直接用 Zotero？**
- Zotero 擅长文献管理，但不适合 AI Agent：难以图谱化、检索粒度粗、schema 不可控
- PaperBase 与 Zotero 互补：可通过 MCP 从 Zotero 导入论文，但以结构化 Markdown 存储

**为什么用 Markdown 而不是 JSON？**
- Markdown 对人类和 AI 都友好，支持富文本和图表，易于版本控制
- JSON 适合元数据（manifest.json），Markdown 适合内容（paper.md）

**为什么分离 PDF 存储？**
- 内容寻址（SHA256）消除重复存储，同一 PDF 可被多篇论文元数据引用
- 支持多来源场景：同一论文可能从 arXiv、期刊、会议获取不同版本

## 🧪 开发指南

### 运行测试

```bash
# 运行所有测试
uv run pytest

# 运行特定测试
uv run pytest tests/unit/test_identity.py -v

# 查看覆盖率
uv run pytest --cov=paperbase --cov-report=html
open htmlcov/index.html
```

### 代码规范

```bash
# 格式检查
uv run ruff check src/

# 自动修复
uv run ruff check --fix src/
```

### 扩展 Adapter

要支持新的论文来源或格式，创建新的 adapter：

```python
# src/paperbase/adapters/my_adapter.py
from pathlib import Path

def fetch_from_source(identifier: str) -> Path:
    """
    从自定义来源获取论文
    
    Returns:
        Path: 下载的 PDF 路径
    """
    # 实现逻辑
    pass
```

然后在 CLI 中注册新命令。

## 🔧 故障排查

### PDF 转换失败

```bash
# 错误: 转换结果为空
# 原因: 扫描版 PDF 或加密 PDF
# 解决: 使用 OCR 工具预处理，或手动编辑 paper.md
```

### 状态卡在 BLOCKED

```bash
# 查看 manifest.json 中的 error_log
uv run paperbase status <paper_id>

# 手动修复后重置状态
# 编辑 manifest.json，将 state 改为前一个状态，然后重新运行
```

### Graphify 更新缓慢

```bash
# 使用增量更新（推荐）
uv run paperbase graph update --incremental

# 批量摄入时跳过自动更新
uv run paperbase ingest --batch papers.txt

# 如果图谱损坏，强制重建（耗时）
uv run paperbase graph update --force
```

**性能优化**：
- 增量更新：100 篇论文中修改 1 篇，从 ~30s 降至 ~3s
- 批量摄入：10 篇论文一次性更新图谱，比逐个摄入快 3-5 倍

### Registry 数据不一致

```bash
# Registry 可以重建
rm registry/papers.sqlite
uv run paperbase status  # 自动重建索引
```

## ⚙️ 配置

主配置文件：`config/paperbase.yaml`

```yaml
project:
  name: "PaperBase"
  version: "0.1.0"

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
  scansci:
    enabled: false
    scihub_enabled: false  # 禁止使用 Sci-Hub
    require_authorized_access: true

graphify:
  auto_update: true
  ignore_patterns:
    - "sources/"
    - "registry/"
```

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

贡献前请：
1. 运行测试确保通过
2. 遵循代码规范（Ruff）
3. 更新相关文档

## 📜 许可

MIT License

## 🔗 相关链接

- [AGENTS.md](AGENTS.md) - Agent 工作指南（必读）
- [CLAUDE.md](CLAUDE.md) - Claude 特定指南
- [Graphify](https://github.com/your-org/graphify) - 知识图谱工具
- [Zotero MCP](https://github.com/your-org/zotero-mcp-server) - Zotero 集成

## 🙏 致谢

- [markitdown](https://github.com/microsoft/markitdown) - Microsoft 的 Markdown 转换工具
- [PyMuPDF](https://pymupdf.readthedocs.io/) - PDF 处理库

---

<div align="center">
Made with ❤️ by researchers, for researchers
</div>
