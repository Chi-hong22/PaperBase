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
  4. 接收 CLI 输出的 Agent 建图交接，执行 preflight → /graphify → adopt（状态 → READY）
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
paperbase ingest <id> --no-graph     # 跳过本次索引和图谱后续处理
paperbase ingest <id> --headless-graph  # 显式本地 LLM 备用路径
paperbase ingest --file paper.pdf --accept-visual-warnings  # 仅在用户确认视觉警告后使用
paperbase ingest <id> --re-review       # Agent 修改 chunk 结果后的重审入口（仅 ready_to_adopt 有效）
```

### 视觉阶段协议（按需加载）

视觉论文在普通 `ingest`（推荐配合 `--no-graph`）下按阶段推进，**每次调用只推进一个阶段**：
`auto audit（自动文字审计）→ chunk 转译 → Boundary Review → adopt`。每完成一批 Agent 侧工作，重复执行**同一条原 ingest 命令**，由 PaperBase 校验并进入下一阶段。

- **`task_package` 路径**：CLI 输出 `AgentActionRequired(task_package)` 时，表示 PaperBase 正在等待 Agent Host 接手视觉任务。读取 `references/visual_pdf_conversion.md`，按任务包交给 Agent Host 的视觉 worker 继续处理；不要寻找或虚构独立的视觉转换命令。
- **`--accept-visual-warnings`**：Boundary Review 通过但存在低风险警告（如保真裁剪）时的用户确认门。先向用户完整展示 warnings，只有用户明确确认后，才在**同一原始 ingest 命令**上添加该旗标后重复执行；Agent 不得自行确认。
- **`--re-review`（视觉返工重审）**：Agent 在两次 ingest 调用之间直接修改了 `.visual-runs/<run_id>/chunks/` 下的 chunk 结果文件后使用。仅当 run 处于 `ready_to_adopt` 时有效：保留各 chunk 的 `completed` 状态，作废已失效的 boundary-review 产物与 run 局部 fallback-assets，状态回 `running`，并由同一次 ingest 调用重新准备边界复核任务包、返回新的 `AgentActionRequired` 交接。可与 `--accept-visual-warnings` 组合；条件不满足时报 `visual_re_review_invalid`（映射 `NEEDS_REVIEW`），按错误信息去掉旗标重跑即可。它是旧手工流程“改 `run.json` state + 删 `boundary-review/` 目录”的官方替代，不要再手工编辑 run.json。
- **`remove` 的审计缓存 stash**：`paperbase remove` 默认把 `paper_dir/.visual-auto-audit/` stash 到 `library/audits-stash/<storage_id>/` 并打印恢复方法；重摄入同一 PDF 前把它移回 `library/papers/<storage_id>/.visual-auto-audit` 即可复用，无需重新自动审计。

### 任务收尾清理

导入/建图任务完成后，必须删除本次任务在工作区产生的临时文件，尤其是视觉流水线残留。

**应删除（Agent 自建、可重建）**：
- 仓库根或任务目录下的 `_hdr_tmp*/`、`tmp_vis/`、`_pdf_text/`、`_pages.pkl`、页图/裁剪草稿、一次性校验脚本
- 图谱步骤产生的 `_run_*.py`、`_list_*.py` 等辅助脚本（Graphify 流水线中间件按 graphify skill Step 9 处理）

**不得删除（系统状态与可复用缓存）**：
- `library/papers/<sid>/.visual-runs/`、`.visual-auto-audit/` 与 `library/audits-stash/`
- `library/papers/graphify-out/cache/`、`manifest.json`、正式 `graph.json` 与 `graph/`
- `.scratch/` 工单与任何来源不明的非本任务文件

不确定是否系统文件时保留，并在交付说明中列出。收尾检查：工作区不应残留本任务产生的 `_` / `tmp_` 前缀临时物。

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
  3. 没有阻塞项时，先切工作目录到本机 `library/papers`，再只对 Canonical Markdown 调用 Graphify skill：`/graphify . --update --no-viz`
  4. 调用 `paperbase graph adopt`，只接纳 graphify-out 并推进状态，不读取本地 LLM 配置
  完成：节点 +5，边 +12
```
（全量重建走同一顺序，把 preflight、`/graphify`、adopt 换成对应 `--force` 形式，执行前先向用户确认耗时。）

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

**与 AGENTS.md 的分工**：图谱输入范围（只扫描 `library/papers/p_*.md`，不在建图阶段读取 PDF、URL 或附件，PDF/网页须先经摄入或修复写回 Canonical）、semantic queue 准入、subagents 并行数、扫描根统一、`.graphifyignore` 处理、本地 LLM 隔离与私有语料本地边界等总则，统一维护在仓库根 `AGENTS.md`（Invariants 第 6、10 条），本 skill 不重复；以下只保留 skill 侧操作细节。

**LLM 优先级约定**：
- 每个 subagent 只读取分配到的 Canonical Markdown，返回结构化节点、边和超边；语义 Agent 必须等待全部 subagents，验证来源覆盖、schema、端点和置信度后再合并。
- 宿主不支持 subagents 时应报告阻塞，不得静默切换到本地 LLM。
- `paperbase graph adopt` 是无 LLM 的确定性状态投影步骤。

**Canonical-only 图谱约束（skill 侧操作细节）**：
- Agent 增量流程若发现旧图与本次扫描根不一致，停止合并和 `adopt`，恢复备份后用正确根重跑。
- 接纳前检查 `source_file` 不得同时出现 `p_xxx.md` 与 `library/papers/p_xxx.md` 两种形式。代码级硬校验尚未实现，权威工单为 `.scratch/graphify-scan-root-consistency/issues/01-enforce-scan-root-consistency.md`（`TD-GRAPH-001`）。
- Zotero 元数据优先于 PDF 元数据；PDF 只能补正文或缺失字段，不能覆盖 Zotero 的标题、作者、年份等权威字段。
- Zotero item key 当前只存在于摄入运行时，尚未持久化到 Manifest/Registry；不要声称可稳定反查。权威工单为 `.scratch/zotero-item-key-provenance/issues/01-persist-zotero-item-key.md`（`TD-ZOTERO-001`，`Status: open`）。
- `content_kind=metadata_only/abstract_only`、无有效全文标记或正文不足的论文保持 `NEEDS_REVIEW`，不推进 `READY`；正文级 `content_kind=fulltext` 且长度达标时，可覆盖历史遗留的外层 quality 标记。
- `BLOCKED` 论文不属于可重试候选：增量检测跳过它，`.graphifyignore` 也必须排除其 Canonical；解除阻塞后再恢复扫描。
- Graphify 产物若含 `.pdf`、URL 或 `external_pdf:` 证据，`paperbase graph adopt` 会拒绝整批投影，避免污染现有图谱。
- 只要存在未修复的 `NEEDS_REVIEW` 论文，`update` 和 `adopt` 都会在耗时建图/投影前停止；先修复 Canonical，再重跑，避免“状态未就绪但图谱已收录”。

**推荐重跑顺序**：
```bash
paperbase graph preflight
# 在本机 library/papers 目录下运行：/graphify . --update --no-viz
paperbase graph adopt
paperbase doctor
```

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

# 全文检索 + 过滤（FTS5；--year、--author 可单独或组合使用）
人类: "搜索 transformer，只看 2020-2024 年作者包含 Li 的论文"
Agent: [FTS5 检索 + 年份范围 + 作者过滤] → 返回 2 篇 + 匹配片段

# 语义查询（Graphify）
人类: "找出关于 SLAM 的论文"
Agent: [语义查询] → 返回 15 篇 + 关联路径

# 关联查询（图谱遍历）
人类: "找出与 BERT 论文相关的研究"
Agent: [query related --depth 2] → 相关论文: 5 篇（通过共享概念关联）
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
paperbase search "<query>" --year <year>    # 按年份过滤（支持 '2023' 或 '2020-2024'）
paperbase search "<query>" --author <name>  # 按作者过滤（模糊匹配，"Zhang" 可匹配 "Zhang Li"）
paperbase query related <id> --depth 2 # 相关论文（推荐 depth=2）
paperbase query topic "<topic>"        # 主题查找（图谱标签）
paperbase query topic "<topic>" --include-refs  # 包含引用文献
```

**query topic 增强**：
- ✅ 覆盖率 100%（支持所有节点格式）
- ✅ 分词匹配（"deep learning" 自动分词）
- ✅ 引用扩展（`--include-refs` 显示外部文献）
- ✅ 自动去重（多节点映射同一论文）

**search 过滤增强**：
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
```

**关键命令**：
```bash
paperbase doctor                      # 环境诊断（优先使用 Registry 统计）
paperbase config show                 # 显示配置
paperbase remove <paper_id>           # 删除论文（默认非交互；自动 stash 视觉审计缓存）
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
      解决: paperbase graph preflight →（在 library/papers 目录下运行）/graphify . --update --no-viz → paperbase graph adopt
  
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

**版本**: v1.5 | **架构**: Agent-first 并行语义建图 + 扫描根一致性护栏 + 视觉返工重审入口 | **更新**: 2026-09-12
