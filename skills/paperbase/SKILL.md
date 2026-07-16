---
name: paperbase
description: >
  AI Agent 全能力管理学术论文知识库。将 PDF 论文转化为结构化知识，构建语义图谱，支持双轨查询（结构化 + 语义）。适用场景：摄入论文（DOI/arXiv/PDF）、批量处理、知识图谱构建、语义检索、状态管理、环境诊断。当用户提到论文管理、文献库、知识图谱、学术搜索、DOI、arXiv、PDF 转换、论文检索等任何相关内容时使用此 skill。
---

# PaperBase Skill

**让 AI Agent 成为你的学术知识库管家**

用自然语言完成论文摄入、组织、检索、管理的全流程操作。

---

## 核心能力

### 1️⃣ 知识摄入

将学术论文转化为结构化知识。

**支持输入**：DOI、arXiv、PMID、URL、本地 PDF、批量文件

**前置条件**：
- 在线摄入需要安装 `paper-fetch`：
  ```bash
  uv tool install git+https://github.com/Dictation354/paper-fetch-skill.git
  ```
- 本地 PDF 摄入无需额外工具

**典型对话**：
```
人类: "帮我摄入这篇论文 10.1038/nature"
Agent: 
  1. 检查 paper-fetch 是否可用
  2. 识别 DOI 并调用 paper-fetch CLI
  3. 提取元数据并生成 `library/papers/p_<storage_id>.md`（状态: NORMALIZED）
  4. 更新知识图谱 (状态 → READY)
  完成！论文已加入知识库

人类: "批量摄入 papers.txt 中的所有论文"
Agent:
  1. 读取 50 个标识符
  2. 批量摄入（跳过图谱）
  3. 统一更新图谱
  完成: 48 成功, 2 失败
```

**关键命令**：
```bash
paperbase ingest <identifier>        # 单篇摄入
paperbase ingest --file <path>       # 本地 PDF
paperbase ingest --batch <file>      # 批量摄入
paperbase ingest <id> --no-graph     # 跳过图谱
```

**辅助脚本**：
```bash
python scripts/batch_ingest.py papers.txt  # 批量摄入助手
```

---

### 2️⃣ 知识组织

构建论文语义关联网络。

**状态机**：
```
PDF/DOI → NORMALIZED → READY
          (已摄入)     (可查询)
```

**典型对话**：
```
人类: "更新知识图谱"
Agent:
  1. 运行 `paperbase graph preflight`，先报告正文不足或需要审核的论文
  2. 若预检有 `NEEDS_REVIEW`，先修复并重试；`BLOCKED` 论文保持排除，不进入增量候选或 Graphify corpus
  3. 没有阻塞项时，只对 Canonical Markdown 调用 Graphify skill：`/graphify library/papers --update --no-viz`
  4. 调用 `paperbase graph adopt`，只接纳 graphify-out 并推进状态，不读取本地 LLM 配置
  完成：节点 +5，边 +12

人类: "重建整个图谱"
Agent:
  警告：全量重建耗时较长
  确认后运行 `paperbase graph preflight --force`，调用 `/graphify library/papers --no-viz`，再执行 `paperbase graph adopt --force`
  完成：已处理 100 篇论文
```

**关键命令**：
```bash
paperbase graph preflight             # 建图前检查 Canonical 正文质量
paperbase graph preflight --force     # 检查全部论文
paperbase graph adopt                 # 接纳 Agent 已生成的 graphify-out（默认增量）
paperbase graph adopt --force         # 接纳 Agent 全量图谱
paperbase graph update                # 手动 headless 更新，读取本地 LLM 配置
paperbase graph update --incremental  # 手动 headless 增量更新
paperbase graph update --force        # 手动 headless 强制重建
paperbase graph status                # 查看统计
```

**LLM 优先级约定**：
- Agent 调用本 skill 时，语义抽取优先使用 Graphify skill 的 Agent/self/subagent 能力；不得把 `config/paperbase.yaml` 的本地 LLM 配置注入该流程。
- 只有人类明确执行 `paperbase graph update` 时，才使用 PaperBase 的本地 OpenAI-compatible LLM 配置。
- `paperbase graph adopt` 是无 LLM 的确定性状态投影步骤。

**Canonical-only 图谱约束**：
- Graphify 语义抽取的唯一输入是 `library/papers/*.md`；不得在建图阶段打开 `source/*.pdf`、访问 `original_url` 或直接从 URL/PDF 补抽取。
- PDF/网页只能先经过摄入或修复流程，转换结果写回 Canonical Markdown，并重算 manifest 哈希后才能建图。
- Zotero 元数据优先于 PDF 元数据；PDF 只能补正文或缺失字段，不能覆盖 Zotero 的标题、作者、年份等权威字段。
- `content_kind=metadata_only/abstract_only`、无有效全文标记或正文不足的论文保持 `NEEDS_REVIEW`，不推进 `READY`；正文级 `content_kind=fulltext` 且长度达标时，可覆盖历史遗留的外层 quality 标记。
- `BLOCKED` 论文不属于可重试候选：增量检测跳过它，`.graphifyignore` 也必须排除其 Canonical；解除阻塞后再恢复扫描。
- Graphify 产物若含 `.pdf`、URL 或 `external_pdf:` 证据，`paperbase graph adopt` 会拒绝整批投影，避免污染现有图谱。
- 只要存在未修复的 `NEEDS_REVIEW` 论文，`update` 和 `adopt` 都会在耗时建图/投影前停止；先修复 Canonical，再重跑，避免“状态未就绪但图谱已收录”。

**推荐重跑顺序**：
```bash
paperbase graph preflight
# Agent 中运行：/graphify library/papers --update --no-viz
paperbase graph adopt
paperbase doctor
```

**本地私有语料边界**：真实 Canonical、manifest、源 PDF、Registry 与图谱产物只保留在本地并由 Git 忽略；仓库跟踪的 `library/papers/.graphifyignore` 用 `!p_*.md` 重新纳入本地 Canonical，因此不需要、也不得用 `git add -f` 让 Graphify 工作。

预检发现 `NEEDS_REVIEW` 时，先修复对应 Canonical Markdown；PaperBase 会保留旧图谱且不调用 Graphify，再重复上述四步。不要在 Graphify 阶段绕过 Canonical 去读取 PDF。

---

### 3️⃣ 知识检索

双轨查询系统（结构化 + 语义）+ 全文检索。

**智能路由**：

| 查询模式 | 示例 | 路由到 |
|---------|------|--------|
| `doi:` | `doi:10.1234/abc` | Registry |
| `state:` | `state:ready` | Registry |
| `year:` | `year:2024` | Registry |
| `author:` | `author:Zhang` | Registry |
| 自然语言 | `SLAM 相关论文` | Graphify |
| 全文关键词 | `transformer` | FTS5 |

**典型对话**：
```
# 结构化查询（Registry）
人类: "列出所有已就绪的论文"
Agent: [查询 state:ready] → 返回 12 篇

人类: "2024 年的论文"
Agent: [查询 year:2024] → 返回 5 篇

# 语义查询（Graphify）
人类: "找出关于 SLAM 的论文"
Agent: [语义查询] → 返回 15 篇 + 关联路径

人类: "深度学习和计算机视觉的交叉研究"
Agent: [图谱推理] → 返回概念交集论文

# 全文检索（FTS5）
人类: "搜索提到 transformer 的论文"
Agent: [FTS5 检索] → 返回 7 篇 + 匹配片段

# 在指定论文中搜索
人类: "查询 RatSLAM 论文中 threshold 的相关内容"
Agent: [单篇论文全文检索] → 返回 4 个匹配片段，显示上下文

# 全文检索 + 过滤（NEW）
人类: "搜索 transformer，限定 2024 年的论文"
Agent: [FTS5 检索 + 年份过滤] → 返回 3 篇 + 匹配片段

人类: "搜索 deep learning，只看 Zhang 作者的"
Agent: [FTS5 检索 + 作者过滤] → 返回 2 篇 + 匹配片段

人类: "搜索 SLAM，只看 2020-2024 年的作者包含 Li 的论文"
Agent: [FTS5 检索 + 年份范围 + 作者过滤] → 返回 2 篇 + 匹配片段

# 主题查询（NEW - 图谱标签匹配）
人类: "查找 attention mechanism 相关的论文"
Agent: [query topic] → 本地论文: 2 篇

人类: "包含引用文献一起查"
Agent: [query topic --include-refs] → 本地: 2 篇, 引用: 3 篇

# 关联查询（图谱遍历）
人类: "找出与 BERT 论文相关的研究"
Agent: [query related --depth 2] → 相关论文: 5 篇（通过共享概念关联）

人类: "只看直接引用的文献"
Agent: [query related --depth 1] → 直接连接: 18 个节点（主要是引用和概念）
```

**depth 参数说明**：
- `--depth 1`: 直接连接的节点，主要是概念、引用文献、技术节点。论文之间很少直接连接。
- `--depth 2`: **推荐值**。通过共享概念（如 bathymetric_slam）或共享引用找到相关论文。
- `--depth 3`: 更广泛的关联，但噪音较大。

**学术图谱特点**：论文之间通过主题、方法论、引用文献间接关联，depth=2 是发现论文语义关联的最佳平衡点。

**关键命令**：
```bash
paperbase status                       # 列出所有论文
paperbase status <paper_id>            # 查询单篇
paperbase status --year <year>         # 按年份筛选
paperbase status --state <state>       # 按状态筛选
paperbase search "<query>"             # 全文检索（全局）
paperbase search "<query>" --paper-id <id>  # 在指定论文中搜索
paperbase search "<query>" --year <year>    # 按年份过滤搜索结果（NEW，支持 '2023' 或 '2020-2024'）
paperbase search "<query>" --author <name>  # 按作者过滤搜索结果（NEW，模糊匹配）
paperbase query related <id> --depth 2 # 相关论文（推荐 depth=2）
paperbase query topic "<topic>"        # 主题查找（图谱标签）
paperbase query topic "<topic>" --include-refs  # 包含引用文献
```

**query topic 增强**：
- ✅ 覆盖率 100%（支持所有节点格式）
- ✅ 分词匹配（"deep learning" 自动分词）
- ✅ 引用扩展（`--include-refs` 显示外部文献）
- ✅ 自动去重（多节点映射同一论文）

**NEW - search 过滤增强**：
- ✅ 年份过滤（`--year 2024` 或 `--year 2020-2024`，支持单一年份和范围）
- ✅ 作者过滤（`--author Zhang`，模糊匹配，"Zhang" 可匹配 "Zhang Li" 或 "Li Zhang"）
- ✅ 多条件组合（可同时使用年份和作者过滤器）
- ❌ 期刊过滤暂不支持（Registry 中无 venue 字段，待扩展 schema）

**search vs query 区别**：
- `search`：全文关键词检索（FTS5），适合查找具体术语、方法名
- `query topic`：图谱标签匹配，适合查找主题概念
- `query related`：图谱遍历，适合发现论文关联

---

### 4️⃣ 知识管理

维护知识库健康。

**典型对话**：
```
人类: "检查知识库健康状态"
Agent:
  ✅ Python 3.11.5
  ✅ uv 0.5.0
  ✅ graphify 已安装
  ✅ 12 篇论文（使用 Registry 统计，优先级高于目录扫描）
  ℹ️  建议：2 篇论文待更新图谱

人类: "显示 LLM 配置"
Agent:
  LLM 状态: 已启用
  Model: gpt-4o-mini
  API Key: sk-xxxxx...xxxx (已脱敏)

人类: "删除论文 doi:10.1234/abc"
Agent:
  已删除：Canonical Markdown、source PDF、registry 记录
  完成！（默认非交互模式）

人类: "我想确认后再删除"
Agent:
  使用 --interactive 启用交互模式
  paperbase remove "doi:10.1234/abc" --interactive

人类: "清理孤立的 Registry 记录"
Agent:
  正在同步 Registry 与文件系统...
  发现 3 条孤立记录（文件已删除但索引仍存在）
  确认清理? (y/n)
```

**关键命令**：
```bash
paperbase doctor                      # 环境诊断（优先使用 Registry 统计）
paperbase config show                 # 显示配置
paperbase config show            # 验证 LLM
paperbase remove <paper_id>           # 删除论文（默认非交互）
paperbase remove <id> --interactive   # 交互式删除（需确认）
paperbase sync                        # 同步 Registry 与文件系统
paperbase sync --dry-run              # 仅查看孤立记录
```

**辅助脚本**：
```bash
python scripts/health_check.py   # 健康检查
python scripts/diagnose.py       # 深度诊断
```

---

## 工作流示例

### 工作流 1: 新论文摄入

```
人类: "我刚下载了 paper.pdf，加入知识库"

Agent:
  步骤 1: 识别本地 PDF
  步骤 2: 提取元数据
    - 标题: "Attention Is All You Need"
    - 作者: Vaswani et al.
    - 年份: 2017
  步骤 3: 生成 `library/papers/p_<storage_id>.md`
    - SHA256: 6b77f95d...
    - 状态: NORMALIZED
  步骤 4: 更新图谱
    - 状态: READY
  
  完成！Paper ID: doi:10.48550/arxiv.1706.03762
  路径: library/papers/p_a7f3b2c1.md
```

### 工作流 2: 批量研究

```
人类: "我在研究 SLAM 技术，帮我找相关论文并总结"

Agent:
  步骤 1: 语义查询 "SLAM"
    → 找到 15 篇论文
  
  步骤 2: 结果聚合
    核心论文 (5篇):
    1. "Bathymetric Particle Filter SLAM" (2021)
    2. "A review of AUV-based bathymetric SLAM" (2025)
    ...
    
    相关主题:
    - 水下导航 (8篇)
    - 粒子滤波 (6篇)
  
  步骤 3: 关系分析
    论文 A (2021) → 引用 → 论文 B (2018)
    方法演进: EKF-SLAM → Particle Filter → Graph-based
```

### 工作流 3: 知识库维护

```
人类: "知识库好像有问题，帮我检查"

Agent:
  步骤 1: 环境诊断
    ✅ Python 3.11.5
    ⚠️  graphify 未找到
  
  步骤 2: 数据一致性
    ✅ Registry 与 manifest 一致
    ⚠️  2 篇论文待更新图谱
  
  步骤 3: 修复建议
    问题 1: graphify 未安装
      解决: uv tool install graphify
    问题 2: 2 篇论文待处理
      解决: paperbase graph preflight → /graphify library/papers --update --no-viz → paperbase graph adopt
  
  是否执行修复? (y/n)
```

---

## 技术架构

### 数据层次

```
Layer 0: 真相源
  library/papers/p_<storage_id>.md (Canonical Markdown)
  └─ frontmatter (元数据) + body (正文)

Layer 1: 投影层（可重建）
  ├─ registry/papers.db (SQLite 索引)
  └─ graph/ (Graphify 图谱)

Layer 2: 状态机
  NORMALIZED → READY
```

### 目录结构

```
PaperBase/
├── library/papers/p_<storage_id>.md   # 内容真相源
├── library/papers/p_<storage_id>/
│   ├── manifest.json                  # 状态与溯源
│   └── source/source.pdf              # 原始 PDF
├── registry/papers.db          # 可重建
├── graph/                      # 可重建
└── config/paperbase.yaml
```

详见：`references/data_architecture.md`

---

## 查询路由

**自动识别**：

```python
# 结构化模式 → Registry
doi:, paper_id:, state:, year:, author:

# 语义模式 → Graphify
自然语言、概念关联、主题探索
```

详见：`references/query_routing.md`

---

## 包装器脚本

Agent 通过包装器自动检测库位置：

```bash
# Unix/Linux/macOS
paperbase-wrapper.sh <command> <args>

# Windows
paperbase-wrapper.ps1 <command> <args>
```

**功能**：
- 自动检测 PaperBase 库路径
- 记忆库位置 (`workspaces.json`)
- 验证环境依赖
- 执行 CLI 命令

---

## 辅助脚本

### 健康检查

```bash
python scripts/health_check.py
```

检查：Python 版本、uv、graphify、库结构、registry、graph、配置、磁盘空间

### 深度诊断

```bash
python scripts/diagnose.py
```

诊断：library 完整性、registry 一致性、graph 状态、数据损坏

### 批量摄入

```bash
python scripts/batch_ingest.py papers.txt
```

批量处理论文列表，自动重试失败项

---

## 配置

### 环境变量

```bash
export PAPERBASE_LIBRARY="/path/to/PaperBase"
export PAPERBASE_LLM_BASE_URL="https://api.openai.com/v1"
export PAPERBASE_LLM_API_KEY="sk-..."
export PAPERBASE_LLM_MODEL="gpt-4o-mini"
```

### 配置文件

`config/paperbase.yaml`:
```yaml
llm:
  base_url: ${PAPERBASE_LLM_BASE_URL}
  api_key: ${PAPERBASE_LLM_API_KEY}
  model: ${PAPERBASE_LLM_MODEL}

graph:
  auto_update: on_ingest
  advanced:
    mode: incremental
```

---

## 详细参考

**完整命令参考**：`references/cli_commands.md`
- 所有 CLI 命令详解
- 参数说明和示例
- 性能建议

**数据架构说明**：`references/data_architecture.md`
- 存储结构
- 状态机详解
- 投影层原理
- SHA256 内容寻址

**查询路由详解**：`references/query_routing.md`
- 路由逻辑
- Registry vs Graphify
- 性能对比
- 调试方法

**故障排查指南**：`references/troubleshooting.md`
- 常见问题
- 诊断步骤
- 解决方案
- 紧急恢复

---

## 依赖

**必需**：
- Python 3.11+
- uv (包管理器)
- PaperBase CLI

**可选**：
- graphify (语义图谱，推荐)
- LLM API (用于 graphify)

---

## 与 CLI 的关系

| 特性 | /paperbase skill | paperbase CLI |
|------|------------------|---------------|
| **使用者** | AI Agent | 人类 |
| **交互** | 自然语言 | 显式命令 |
| **智能** | 自动路由 | 手动指定 |
| **场景** | 对话式 | 脚本化 |

**推荐**：
- 日常使用 → `/paperbase` skill
- 脚本自动化 → `paperbase` CLI

---

## 设计理念

### 第一性原理

1. **唯一内容真相源**：`library/papers/p_<storage_id>.md` 是论文内容的源头
2. **状态与溯源**：同名目录中的 `manifest.json` 记录状态、来源和处理历史
3. **可重建投影**：registry 和 graph 可从 Canonical 与 manifest 重建
4. **幂等状态机**：所有操作可重复执行
5. **双轨查询**：结构化 + 语义正交互补

### 用户体验

- **自然语言优先**：用户说人话，Agent 理解执行
- **智能推断**：自动识别查询类型并路由
- **容错处理**：错误时给出解决建议
- **反馈清晰**：操作步骤和结果可视化

---

**版本**: v1.1 | **架构**: 平面 Canonical + 简化状态机 (NORMALIZED → READY) | **更新**: 2026-07-16
