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

### 3. 配置环境变量（推荐）

为了在任意目录调用 PaperBase，建议设置环境变量：

**Linux/macOS:**
```bash
# 添加到 ~/.bashrc 或 ~/.zshrc
export PAPERBASE_LIBRARY="/path/to/PaperBase"
```

**Windows PowerShell:**
```powershell
# 添加到 PowerShell Profile ($PROFILE)
$env:PAPERBASE_LIBRARY = "C:\path\to\PaperBase"
```

**验证环境变量：**
```bash
# Linux/macOS
echo $PAPERBASE_LIBRARY

# Windows
echo $env:PAPERBASE_LIBRARY
```

### 4. 验证安装

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

## 论文导入方式

### 首选：从 Zotero 导入

建议先在 Zotero 中收集、整理并下载论文附件，再将条目导入 PaperBase。Zotero 负责文献管理、阅读和引用，PaperBase 负责 Canonical Markdown、全文检索和知识图谱分析。

```bash
# 安装 Zotero 集成工具
uv tool install zotero-mcp-server

# 单篇导入：将 <ITEM_KEY> 替换为 Zotero 条目的 Item Key
uv run paperbase ingest --zotero-key <ITEM_KEY>

# 批量导入最近 N 篇
uv run paperbase ingest --zotero-recent 10
```

本地模式下请启动 Zotero 并启用 HTTP 服务器；如果条目有本机可访问的 PDF 附件，PaperBase 会处理完整全文。Web API 模式或没有可访问 PDF 附件时，会降级为元数据/摘要导入。详细配置见 [Zotero 集成指南](integrations/zotero.md)。

### 其他外部工具（可选）

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
**要求**: Agent 模式由宿主 Agent/Graphify skill 完成语义抽取；只有 headless CLI 模式需要 PaperBase 本地 LLM 配置

#### 先检查已有安装，再选择来源

```powershell
uv run paperbase graph runtime
```

输出分别报告本地安装、uv 安装是否可用，以及最终选中的来源、版本和 Python。这里的 `uv run` 只是在项目环境中运行 PaperBase，不代表选用了 uv 安装的 Graphify。

| 选择 | 行为 | 用法 |
|---|---|---|
| `auto`（默认） | 优先发现可用的本地安装，其次选择已有 uv 工具 | `uv run paperbase --graphify-source auto graph runtime` |
| `local` | 只用非 uv tool 管理的安装，包括 pip 用户安装、pipx、独立虚拟环境 | `uv run paperbase --graphify-source local graph runtime` |
| `uv` | 只用已经安装的 uv 工具 | `uv run paperbase --graphify-source uv graph runtime` |

确认选中环境后，把示例末尾的 `graph runtime` 换成实际命令，例如：

```powershell
uv run paperbase --graphify-source uv graph update --incremental

# 未在 PATH 中的本地环境：替换为真实路径
uv run paperbase --graphify-source local --graphify-python 'C:\path\to\python.exe' graph runtime
# 或指定本地 Graphify 命令，与 --graphify-python 二选一
uv run paperbase --graphify-source local --graphify-command 'C:\path\to\graphify.exe' graph runtime
```

三个选项都是全局选项，必须位于 `graph`、`doctor` 或 `ingest` 等子命令之前。显式来源或目标不可用时直接报错，不安装、不下载临时环境、不静默换源。自动发现不会遍历磁盘中所有虚拟环境，未被发现的安装请显式指定 Python。

#### 本机默认选择与环境变量

| 环境变量 | 含义 |
|---|---|
| `PAPERBASE_GRAPHIFY_SOURCE` | `auto`、`local` 或 `uv`，未设置时为 `auto` |
| `PAPERBASE_GRAPHIFY_PYTHON` | 独立本地 Python 的路径或命令 |
| `PAPERBASE_GRAPHIFY_COMMAND` | 独立本地 Graphify 命令或路径，与上一项二选一 |

```powershell
# 当前 PowerShell 会话默认使用 uv
$env:PAPERBASE_GRAPHIFY_SOURCE = 'uv'
uv run paperbase graph runtime

# 如需后续新终端也使用 uv，由使用者执行；不影响已经打开的其他终端
[Environment]::SetEnvironmentVariable('PAPERBASE_GRAPHIFY_SOURCE', 'uv', 'User')
```

命令行参数优先于环境变量；切换为 uv 时应清除本地 Python/命令变量。上述选择控制 PaperBase 执行、诊断、项目技能查询和相关测试，不写入共享的 `config/paperbase.yaml`。宿主直接运行外部 `/graphify` 时，仍需采用 PaperBase 解析出的 Python，不能假定外部技能自动读取 PaperBase 的 CLI 选项。详细边界见 [运行环境故障排查](troubleshooting/graphify-issues.md#选择-graphify-安装来源)。

#### 尚未安装时

已有可用安装无需重装。以下 `graphifyy` 是本项目已验证环境的发行包名，安装后提供的命令仍叫 `graphify`。

**安装：**
```bash
uv tool install graphifyy
```

**验证：**
```bash
graphify --version
uv run paperbase graph runtime
```

**推荐的 Agent 路径：**

```bash
uv run paperbase graph preflight
# 在支持 Graphify skill 的 Agent 中运行（先切到本机 library/papers 目录）：/graphify . --update --no-viz
uv run paperbase graph adopt
```

这条路径不读取 PaperBase 的本地 LLM 配置。只有显式运行 `uv run paperbase graph update` 时，才需要在 `config/paperbase.yaml` 中配置 OpenAI-compatible LLM；可用 `uv run paperbase config show` 查看生效配置，用 `uv run paperbase doctor` 检查 Graphify 是否可用。不要在文档或提交中记录真实密钥。

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

### 推荐工作流（Zotero + graphify）

```bash
# 1. 安装工具
uv tool install zotero-mcp-server
uv tool install graphifyy

# 2. 在 Zotero 中整理论文并下载需要的 PDF 附件

# 3. 从 Zotero 导入
uv run paperbase ingest --zotero-key <ITEM_KEY>

# 4. 更新图谱
uv run paperbase graph preflight
# 在支持 Graphify skill 的 Agent 中运行（先切到本机 library/papers 目录）：/graphify . --update --no-viz
uv run paperbase graph adopt

# 5. 查询论文
uv run paperbase status
```

### 备选工作流（paper-fetch + graphify）

```bash
# 1. 安装工具
uv tool install git+https://github.com/Dictation354/paper-fetch-skill.git
uv tool install graphifyy

# 2. 配置 LLM（graphify 需要）
export PAPERBASE_LLM_API_KEY="sk-..."

# 3. 摄入论文
uv run paperbase ingest "10.1038/s41586-021-03819-2"

# 4. 更新图谱
uv run paperbase graph update

# 5. 查询论文
uv run paperbase status
```

### 其他备选工作流（仅本地 PDF）

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

先用 `uv run paperbase graph runtime` 查看所选来源是否可用；若只缺本地安装而 uv 可用，可由使用者明确选择 `--graphify-source uv`。仅在确认未安装且决定安装后执行以下命令。

**症状：**
```
⚠️ graphify (optional) not found
```

**解决：**
```bash
uv tool install graphifyy
graphify --version
```

### LLM API 配置错误

**症状：**
```
LLM Configuration: disabled
```

**解决：**

Agent 路径无需 PaperBase 本地 LLM 配置；先运行 `uv run paperbase graph preflight`，再由 Graphify skill 建图并执行 `uv run paperbase graph adopt`。若明确使用 headless `paperbase graph update`，请在 `config/paperbase.yaml` 中配置 OpenAI-compatible LLM，并用以下命令检查：

```bash
uv run paperbase config show
uv run paperbase doctor
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
    ├─ 生成 library/papers/p_<storage_id>.md
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
- 投影层（registry/graph）可从 Canonical Markdown 与 manifest 重建

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
