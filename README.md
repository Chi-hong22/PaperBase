# PaperBase

学术论文知识库基础设施 —— 让论文成为可复用的知识资产。

## 核心理念

PaperBase 将学术论文转化为结构化、可检索、可图谱化的知识库：

- **Canonical Markdown 是唯一真相源** - 所有数据投影（图谱、索引、分块）均可从规范化 Markdown 重建
- **幂等状态机管理** - 论文处理流程可中断、可恢复、可追溯
- **内容寻址存储** - PDF 和元数据分离存储，避免重复
- **工具无关设计** - 既可用于 AI Agent 工作流，也可用于传统脚本

## 快速开始

### 环境要求

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (Python 包管理器)
- Git

### 安装

```bash
# 1. 克隆项目
git clone <your-repo-url>
cd PaperBase

# 2. 安装项目依赖
uv sync

# 3. 安装全局工具（必需）
uv tool install graphify           # 知识图谱构建
uv tool install zotero-mcp-server  # Zotero 集成（可选）

# 4. 验证安装
graphify --version
uv run paperbase --help
```

### 第一篇论文

```bash
# 摄入一篇论文（支持 DOI、arXiv、PMID）
uv run paperbase ingest "10.1038/s41586-021-03819-2"

# 查看论文状态
uv run paperbase status "doi:10.1038/s41586-021-03819-2"

# 搜索论文内容
uv run paperbase search "deep learning"

# 更新知识图谱
uv run paperbase graph update
```

成功后，论文会被存储在 `library/papers/<storage_id>/paper.md`。

## 核心概念

### Canonical Markdown

每篇论文对应一个规范化的 Markdown 文件 (`paper.md`)，包含：

```yaml
---
# Frontmatter (结构化元数据)
schema_version: "0.1.0"
paper_id: "doi:10.1038/s41586-021-03819-2"
storage_id: "p_a1b2c3d4e5f6"
title: "Paper Title"
authors: [...]
year: 2021
# ...
---

# Paper Title

## Abstract
...

## Introduction
...

## References
1. Author et al. (2020). Title. Journal.
```

### 状态机

论文处理流程通过状态机管理（定义在 `manifest.json` 中）：

```
DISCOVERED → RESOLVED → SOURCE_READY → CONVERTED → NORMALIZED → VALIDATED → GRAPHED → READY
```

- **DISCOVERED**: 识别到论文标识（DOI/arXiv 等）
- **SOURCE_READY**: PDF 已下载
- **CONVERTED**: PDF 已转换为初步 Markdown
- **NORMALIZED**: Markdown 已规范化（符合 schema）
- **VALIDATED**: 通过 schema 验证
- **GRAPHED**: 已加入知识图谱
- **READY**: 可用状态

### 目录结构

```
paperbase/
├── library/                    # 知识库主体
│   ├── sources/pdf/           # 内容寻址的 PDF 存储 (SHA256)
│   ├── papers/                # 规范化论文
│   │   └── p_<storage_id>/   # 单篇论文
│   │       ├── paper.md       # Canonical Markdown (source of truth)
│   │       ├── manifest.json  # 状态和溯源信息
│   │       ├── chunks.jsonl   # 检索用分块 (derived)
│   │       ├── references.jsonl # 结构化引用 (derived)
│   │       ├── assets/        # 图表资源
│   │       └── source/        # 原始 PDF
│   ├── collections/           # 用户论文集合
│   └── notes/                 # 用户笔记
├── registry/                  # SQLite 快速查询索引 (derived)
├── graph/                     # Graphify 知识图谱 (derived)
├── config/                    # 配置文件
├── src/paperbase/            # Python 包
└── skills/                    # 项目级 skills
```

**重要**: 只有 `library/papers/*/paper.md` 和 `manifest.json` 是 source of truth，其他均可重建。

## 使用教程

### 人类用户

#### 摄入论文

```bash
# 通过 DOI
uv run paperbase ingest "10.1038/nature12373"

# 通过 arXiv
uv run paperbase ingest "arxiv:2301.07041"

# 通过本地 PDF
uv run paperbase ingest --file paper.pdf

# 批量摄入（推荐用于多篇论文）
cat > papers.txt << EOF
/path/to/paper1.pdf
/path/to/paper2.pdf
/path/to/paper3.pdf
EOF

uv run paperbase ingest --batch papers.txt

# 跳过自动图谱更新（适用于连续摄入）
uv run paperbase ingest paper.pdf --no-graph
```

**批量摄入说明**：
- 批量模式会自动延迟图谱更新，所有论文摄入完成后统一更新
- 文件格式：每行一个路径，支持 `#` 注释
- 详见 [图谱更新策略](docs/graph-update-strategy.md)


#### 查询和搜索

```bash
# 查看所有论文
uv run paperbase status

# 查看特定状态的论文
uv run paperbase status --state ready

# 全文搜索
uv run paperbase search "transformer architecture" -n 20

# 在 Zotero 中搜索（需安装 zotero-mcp）
uv run paperbase search --zotero "quantum computing"
```

#### 知识图谱

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
- 批量摄入：自动延迟至全部完成后统一更新
- 增量更新：仅处理内容发生变化的论文（推荐定期维护）
- 详见 [图谱更新策略](docs/graph-update-strategy.md)


### AI Agent 用户

#### 接入指南

1. **阅读 Agent 文档**: 参考 [AGENTS.md](AGENTS.md) 和 [CLAUDE.md](CLAUDE.md)
2. **使用 CLI 接口**: 所有操作通过 `paperbase` 命令完成
3. **遵循 Invariants**: 详见 AGENTS.md 中的不可违反规则

#### 示例：Agent 工作流

```python
# Agent 伪代码示例
def process_paper(doi: str):
    # 1. 摄入论文
    run_command(f"paperbase ingest {doi}")
    
    # 2. 检查状态
    status = run_command(f"paperbase status {doi}")
    
    # 3. 读取 Canonical Markdown
    paper_md = read_file(f"library/papers/{storage_id}/paper.md")
    
    # 4. 提取信息或生成笔记
    # ...
    
    # 5. 更新图谱
    run_command("paperbase graph update")
```

#### 作为 Skill 集成

项目包含示例 skills（位于 `skills/` 目录）：
- `paper-fetch-skill`: 论文获取和元数据提取
- `citation-check-skill`: 引用真实性验证

可将 PaperBase 封装为自定义 skill，供其他项目调用。

## 架构说明

### 数据流

```
PDF 输入 → 元数据提取 → 内容转换 → Markdown 规范化 → Schema 验证 → 图谱构建
   ↓            ↓              ↓               ↓              ↓            ↓
sources/   manifest.json   paper.md      paper.md      registry/    graph/
           (state)         (draft)       (canonical)   (index)      (projection)
```

### 核心模块

- **`core/identity.py`**: paper_id 规范化和 storage_id 生成
- **`core/paths.py`**: 路径管理（带安全验证）
- **`core/manifest.py`**: 状态机和溯源管理
- **`core/normalizer.py`**: Markdown 规范化器
- **`core/registry.py`**: SQLite 索引（支持上下文管理器）
- **`core/search_engine.py`**: 全文检索（FTS5）
- **`adapters/`**: 外部工具适配器（PDF 提取、转换、Graphify）

### 设计决策

- **为什么不直接用 Zotero？** Zotero 适合文献管理，但不适合作为 AI Agent 的知识库（难以图谱化、检索粒度粗、schema 不可控）
- **为什么用 Markdown 而不是 JSON？** Markdown 对人类和 AI 都友好，支持富文本和图表，易于版本控制
- **为什么分离 PDF 存储？** 内容寻址避免重复存储，同一 PDF 可被多篇论文元数据引用

## 能力边界

### 能做什么 ✅

- 摄入和规范化学术论文（DOI、arXiv、PMID、本地 PDF）
- 提取结构化元数据（标题、作者、摘要、引用）
- 全文检索（支持 AND/OR/NOT）
- 构建论文关系图谱（通过 Graphify）
- 幂等处理流程（可中断、可恢复）
- 与 Zotero 集成（通过 MCP）

### 不能做什么 ❌

- **不会绕过付费墙** - 只从合法来源获取内容（需配置 `scihub_enabled=false`）
- **不做 OCR** - 扫描版 PDF 转换效果差（可考虑预处理）
- **不做语义理解** - 只做结构化和图谱化，不生成摘要或评论
- **不是参考文献管理器** - 更偏向知识库而非文献管理（但可与 Zotero 互补）

### 已知限制

- PDF 转换质量依赖 `markitdown`（复杂排版可能有问题）
- 引用提取基于正则匹配（非标准格式可能失败）
- 图谱构建依赖 Graphify（需单独安装）
- 并发写入可能需要外部锁（SQLite WAL 模式已启用）

## 开发指南

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
    # 实现获取逻辑
    pass
```

然后在 CLI 中注册新命令。

### 目录约定

- 不修改 `library/` 结构（Invariant）
- 新增功能优先通过 adapter 扩展
- Schema 修改必须向后兼容（增加 `schema_version`）

## 故障排查

### PDF 转换失败

```bash
# 错误: PDF 转换结果为空
# 可能原因: 扫描版 PDF 或加密 PDF
# 解决: 使用支持 OCR 的工具预处理，或手动编辑 paper.md
```

### 状态卡在 BLOCKED

```bash
# 检查 manifest.json 中的 error_log
uv run paperbase status <paper_id>

# 手动修复后重置状态
# 编辑 manifest.json，将 state 改为前一个状态，然后重新运行
```

### Graphify 更新缓慢

```bash
# 使用增量更新只处理变更文件（推荐）
uv run paperbase graph update --incremental

# 批量摄入时跳过自动更新，最后统一更新
uv run paperbase ingest --batch papers.txt

# 如果图谱损坏，强制重建（耗时）
uv run paperbase graph update --force
```

**性能优化**：
- 增量更新：100 篇论文中修改 1 篇，从 ~30s 降至 ~3s
- 批量摄入：10 篇论文一次性更新图谱，比逐个摄入快 3-5 倍
- 详见 [图谱更新策略](docs/graph-update-strategy.md)


### Registry 数据不一致

```bash
# Registry 可以重建
rm registry/papers.sqlite
uv run paperbase status  # 自动重建索引
```

## 配置

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

## 贡献

欢迎提交 Issue 和 Pull Request！

贡献前请：
1. 运行测试确保通过
2. 遵循代码规范（Ruff）
3. 更新相关文档

## 许可

MIT License

---

## 相关链接

- [AGENTS.md](AGENTS.md) - Agent 工作指南（必读）
- [CLAUDE.md](CLAUDE.md) - Claude 特定指南
- [依赖项目](https://github.com/Dictation354/paper-fetch-skill) - paper-fetch-skill
- [Graphify](https://github.com/your-org/graphify) - 知识图谱工具
- [Zotero MCP](https://github.com/your-org/zotero-mcp-server) - Zotero 集成

## 致谢

- [markitdown](https://github.com/microsoft/markitdown) - Microsoft 的 Markdown 转换工具
- [PyMuPDF](https://pymupdf.readthedocs.io/) - PDF 处理库
- [Graphify](https://graphify.ai/) - 知识图谱构建
