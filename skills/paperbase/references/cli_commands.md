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
paperbase graph update                  # 更新图谱
paperbase graph update --incremental    # 增量更新（推荐）
paperbase graph update --force          # 强制全量重建
paperbase graph status                  # 查看图谱统计
```

**更新模式**：
- **默认模式**: 只处理 NORMALIZED 状态的论文
- **增量模式** (`--incremental`): 通过 SHA256 检测内容变化，只更新变更的论文
- **强制模式** (`--force`): 删除现有图谱并全量重建

**示例**：
```bash
# 常规更新（处理新摄入的论文）
paperbase graph update

# 增量更新（日常维护，快 10 倍）
paperbase graph update --incremental

# 强制重建（修复图谱问题）
paperbase graph update --force
```

---

### status - 状态查询

查看论文状态。

```bash
paperbase status                        # 列出所有论文
paperbase status <paper_id>             # 查询单篇论文
paperbase status --state <state>        # 按状态筛选
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
```

**示例**：
```bash
# 查找直接相关的论文
paperbase query related "doi:10.1038/nature01"

# 查找二度相关的论文
paperbase query related "arxiv:1706.03762" --depth 2

# 按主题查找
paperbase query topic "deep learning"
paperbase query topic "underwater navigation"
```

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
- 知识库状态（论文数量、图谱文件）
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
paperbase remove <paper_id>             # 删除（需确认）
paperbase remove <paper_id> --confirm   # 跳过确认
```

**警告**：此操作将：
- 删除 `paper.md`
- 删除 `source PDF`
- 删除 `manifest.json`
- 删除 registry 记录
- **不会自动更新图谱**

**重要**：删除后图谱中仍保留该论文的节点和边关系。这可能导致：
- 语义查询返回已删除论文的引用
- 图谱统计数据不准确
- 关系推理出现死链接

**解决方法**：删除论文后，必须运行 `paperbase graph update --force` 重建图谱。

**示例**：
```bash
# 删除论文（会要求确认）
paperbase remove "doi:10.1038/nature12373"

# 跳过确认（危险）
paperbase remove "arxiv:1706.03762" --confirm

# 删除后重建图谱
paperbase graph update --force
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
