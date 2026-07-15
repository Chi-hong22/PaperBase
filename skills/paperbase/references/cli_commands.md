# PaperBase CLI Commands Reference

Complete reference for all PaperBase CLI commands.

## Core Commands

### ingest - 摄入论文

将学术论文转化为结构化知识。

```bash
paperbase ingest <identifier>           # 摄入单篇论文
paperbase ingest --file <path>          # 摄入本地 PDF
paperbase ingest --batch <file>         # 批量摄入
paperbase ingest <id> --no-graph        # 跳过图谱更新
```

**支持的输入格式**：
- DOI: `10.1038/nature12373`
- arXiv: `arxiv:1706.03762` 或 `1706.03762`
- PMID: `pmid:12345678`
- URL: `https://www.nature.com/articles/...`
- 本地 PDF: `/path/to/paper.pdf`
- 批量文件: `papers.txt`（每行一个标识符）

**功能**：
- 自动检测重复论文（基于 DOI 和标题）
- 防止重复摄入相同论文
- 支持单篇、本地文件、批量处理

**示例**：
```bash
# 在线摄入
paperbase ingest "doi:10.1038/nature12373"
paperbase ingest "arxiv:1706.03762"
paperbase ingest "https://www.nature.com/articles/..."

# 本地 PDF
paperbase ingest --file ~/Downloads/paper.pdf

# 批量摄入（推荐使用 --no-graph 延迟图谱更新）
paperbase ingest --batch papers.txt --no-graph
paperbase graph update  # 统一更新图谱

# 注意：--batch 模式本身不会跳过图谱更新，需要显式加 --no-graph
# 建议：批量摄入时总是使用 --no-graph，最后统一更新图谱（性能提升 3-5 倍）
```

---

### graph - 图谱管理

构建和管理知识图谱。

```bash
paperbase graph preflight                # 建图前检查 Canonical 正文质量
paperbase graph preflight --force        # 检查全部论文
paperbase graph adopt                   # 接纳 Agent 已生成的 graphify-out
paperbase graph adopt --force           # 接纳 Agent 全量图谱
paperbase graph update                  # 手动 headless 更新，读取本地 LLM
paperbase graph update --incremental    # 手动 headless 增量更新
paperbase graph update --force          # 手动 headless 强制全量重建
paperbase graph status                  # 查看图谱统计
```

**更新模式**：
- **Agent 模式**: Graphify skill 先生成 `library/papers/graphify-out/`，再用 `adopt` 做无 LLM 状态投影
- **手动默认模式**: `update` 调用 headless Graphify，读取 `config/paperbase.yaml` 的本地 LLM
- **增量模式** (`--incremental`): 通过 SHA256 检测内容变化；保留 `graphify-out/cache/` 供 Graphify 复用
- **强制模式** (`--force`): 删除 Graphify 缓存并全量重建
- **质量门**: metadata-only、abstract-only、无有效全文标记或正文不足的论文进入 `NEEDS_REVIEW`；正文级 fulltext 标记且长度达标可覆盖历史遗留 quality 标记
- **来源门**: `.pdf`、URL、`external_pdf:` 证据会让 adopt 整批失败，旧图保持不变
- **阻塞门**: 只要存在未修复的 `NEEDS_REVIEW`，`update`/`adopt` 会在调用或接纳 Graphify 前停止；先修复 Canonical 再重试

**示例**：
```bash
# Agent 生成图谱后的接纳（推荐）
paperbase graph adopt

# 手动 headless 更新（处理新摄入的论文）
paperbase graph update

# 增量更新（日常维护，快 10 倍）
paperbase graph update --incremental

# 强制重建（修复图谱问题）
paperbase graph update --force
```

**Canonical-only 约束**：Graphify 建图阶段只读取 `library/papers/*.md`。PDF、网页和 Zotero 附件必须先经过摄入/修复流程写回 Canonical Markdown；Zotero 元数据优先，PDF 不得覆盖权威元数据。

---

### status - 状态查询

查看论文状态。

```bash
paperbase status                        # 列出所有论文
paperbase status <paper_id>             # 查询单篇论文
paperbase status --year <year>          # 按年份筛选（NEW）
paperbase status --state <state>        # 按状态筛选（NEW）
paperbase status --year 2021 --state ready  # 组合过滤（NEW）
```

**可用状态**：
- `normalized` - 已摄入并规范化（未加入图谱）
- `ready` - 已加入图谱，可供查询
- `needs_review` - 需要人工审核
- `blocked` - 处理被阻塞
- `failed_retryable` - 临时失败，可重试
- `failed_permanent` - 永久失败

**示例**：
```bash
# 列出所有论文
paperbase status

# 查询特定论文
paperbase status "doi:10.1038/nature12373"

# 按年份筛选（NEW）
paperbase status --year 2021

# 按状态筛选
paperbase status --state ready

# 组合过滤（NEW）
paperbase status --year 2021 --state normalized
```

# 筛选已就绪的论文
paperbase status --state ready

# 筛选待处理的论文
paperbase status --state normalized
```

---

### search - 全文检索

基于 SQLite FTS5 的全文检索。

```bash
paperbase search "<query>"              # 基本搜索
paperbase search "<query>" -n <limit>   # 限制结果数
```

**支持的运算符**：
- `AND` - 同时包含
- `OR` - 包含任一
- `NOT` - 不包含
- `"exact phrase"` - 精确短语

**示例**：
```bash
# 基本搜索
paperbase search "deep learning"

# Boolean 运算
paperbase search "transformer AND attention"
paperbase search "neural OR network"
paperbase search "machine learning NOT supervised"

# 精确短语
paperbase search '"generative adversarial network"'

# 限制结果
paperbase search "SLAM" -n 20
```

---

### query - 图谱查询

基于知识图谱的关系查询（需要 graphify）。

```bash
paperbase query related <paper_id> --depth <N>  # 查找相关论文
paperbase query topic "<topic>"                 # 按主题查找
paperbase query topic "<topic>" --include-refs  # 包含引用文献
```

**示例**：
```bash
# 查找直接相关的论文
paperbase query related "doi:10.1038/nature01"

# 查找二度相关的论文
paperbase query related "arxiv:1706.03762" --depth 2

# 按主题查找（仅本地论文）
paperbase query topic "deep learning"
paperbase query topic "underwater navigation"

# 扩展到引用文献
paperbase query topic "attention" --include-refs
# 输出：本地论文: 1 篇, 引用文献: 2 篇
```

**query topic 说明**：
- 支持多词查询（如 "deep learning"），任意词匹配即返回
- 默认只返回本地论文
- 使用 `--include-refs` 扩展到引用的外部文献
- 大小写不敏感

**query related 说明**：
- 基于知识图谱查找相关论文
- `--depth` 控制遍历深度（1=直接相关，2=二度相关）
- 结果包含本地论文和引用文献

---

### config - 配置管理

管理和诊断配置。

```bash
paperbase config show                   # 显示配置
paperbase config show              # 验证 LLM 配置
paperbase config path                   # 配置文件路径
```

**示例**：
```bash
# 显示完整配置
paperbase config show

# 验证 LLM 配置
paperbase config show

# 查看配置文件位置
paperbase config path
```

---

### doctor - 环境诊断

检查环境和依赖。

```bash
paperbase doctor
```

**检查项目**：
- Python 版本（需要 >= 3.11）
- uv 包管理器
- graphify 安装状态（可选）
- SQLite 版本和 FTS5 支持
- 知识库状态（优先使用 Registry 统计论文数量，Fallback 到目录统计）
- Registry 数据库状态

**示例输出**：
```
✅ Python 3.11.5
✅ uv 0.5.0
⚠️  graphify 未找到（可选）
✅ SQLite 3.45.0 (FTS5 支持)
✅ 知识库: 12 篇论文
✅ Registry: papers.db (45.3 KB)
✅ 图谱: 3 个文件
```

---

### remove - 删除论文

永久删除论文（不可逆）。

```bash
paperbase remove <paper_id>                # 删除（默认非交互）
paperbase remove <paper_id> --interactive  # 启用交互模式（需确认）
paperbase remove <paper_id> -i             # 短参数
paperbase remove <paper_id> --yes          # 已废弃，保留向后兼容
paperbase remove <paper_id> --force        # 已废弃，保留向后兼容
```

**行为变更**：
- **默认模式**：直接删除，无需确认（适合自动化）
- **交互模式**：使用 `--interactive` / `-i` 启用确认提示（适合手动操作）
- **已废弃参数**：`--yes` / `-y` / `--force` / `-f` 保留向后兼容，但不再推荐使用

**警告**：此操作将：
- 删除论文目录（`p_xxx/`）
- 删除 canonical markdown（`p_xxx.md`）
- 删除 source PDF（如果是孤立的）
- 删除 registry 记录
- **不会自动更新图谱**（需手动运行 `graph update --force`）

**重要**：删除后图谱中仍保留该论文的节点和边关系。这可能导致：
- 语义查询返回已删除论文的引用
- 图谱统计数据不准确
- 关系推理出现死链接

**解决方法**：删除论文后，必须运行 `paperbase graph update --force` 重建图谱。

**示例**：
```bash
# 直接删除（默认非交互）
paperbase remove "doi:10.1038/nature12373"

# 交互式删除（需确认）
paperbase remove "arxiv:1706.03762" --interactive

# 删除后重建图谱
paperbase graph update --force
```

---

### sync - 同步 Registry

同步 Registry 数据库与文件系统，清理孤立的索引记录。

```bash
paperbase sync                  # 同步并确认删除
paperbase sync --dry-run        # 仅显示孤立记录
paperbase sync --yes            # 跳过确认直接清理
```

**功能**：
- 检测 Registry 中存在但文件系统中不存在的论文记录
- 显示孤立记录列表（Paper ID、标题、状态）
- 提供清理选项（仅删除索引，不删除文件）

**使用场景**：
- 手动删除论文目录后清理索引
- Registry 与文件系统不一致时修复
- 定期维护知识库健康

**示例**：
```bash
# 检查孤立记录
paperbase sync --dry-run

# 清理孤立记录（需确认）
paperbase sync

# 自动清理（跳过确认）
paperbase sync --yes
```

---

## 命令组合

### 批量摄入 + 图谱构建

```bash
# 批量摄入（跳过图谱）
paperbase ingest --batch papers.txt --no-graph

# 统一构建图谱
paperbase graph update
```

### 日常维护

```bash
# 摄入新论文
paperbase ingest "doi:10.1234/abc"

# 增量更新图谱
paperbase graph update --incremental

# 检查状态
paperbase status
```

### 问题排查

```bash
# 运行诊断
paperbase doctor

# 检查 LLM 配置
paperbase config show

# 查看特定论文状态
paperbase status "doi:10.1234/abc"

# 强制重建图谱
paperbase graph update --force
```

---

## 退出码

- `0` - 成功
- `1` - 一般错误（文件不存在、配置错误等）
- `2` - 命令行参数错误

---

## 环境变量

```bash
# 知识库路径
export PAPERBASE_LIBRARY="/path/to/PaperBase"

# LLM 配置（用于 graphify）
export PAPERBASE_LLM_BASE_URL="https://api.openai.com/v1"
export PAPERBASE_LLM_API_KEY="sk-..."
export PAPERBASE_LLM_MODEL="gpt-4o-mini"
```

---

## 配置文件

`config/paperbase.yaml`:

```yaml
llm:
  base_url: ${PAPERBASE_LLM_BASE_URL}
  api_key: ${PAPERBASE_LLM_API_KEY}
  model: ${PAPERBASE_LLM_MODEL}
  advanced:
    timeout: 60
    max_input_tokens: 4000

graph:
  auto_update: on_ingest
  advanced:
    mode: incremental
```

---

## 性能建议

- 批量摄入时使用 `--no-graph`，最后统一更新图谱（快 3-5 倍）
- 日常维护使用 `--incremental` 模式（快 10 倍）
- 全文检索比图谱查询快，但语义理解能力弱
- 图谱查询需要 graphify 和 LLM，成本较高但语义理解能力强
