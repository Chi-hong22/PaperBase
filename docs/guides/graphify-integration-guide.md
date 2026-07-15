# Graphify 技术参考

最后更新：2026-07-08

本文档只介绍 Graphify。它存放在当前项目中，是为了后续做接口对接、工具调用和工作流设计时，有一份本地可读的技术依据，不再临时猜测或依赖上网搜索。

## 1. 文档边界

本文覆盖：

- Graphify 是什么。
- Graphify 的输入、输出和核心工作流。
- Agent 模式和 headless CLI 模式的调用方式。
- Graphify 是否需要 LLM，以及需要时如何接入。
- Graphify 生成物的目录结构和查询方式。
- 后续项目接入 Graphify 时应遵守的通用接口契约。

本文不覆盖：

- 当前项目内部代码实现。
- 当前项目的 adapter、状态机、registry、schema 或命令实现。
- 任何外部论文下载、PDF 转换、Zotero 或业务侧实体提取流程。

## 2. 本地依据

优先使用以下本地资料，不要先上网搜索：

| 类型 | 位置或命令 | 用途 |
|---|---|---|
| 本机版本 | `graphify --version` | 确认当前 Graphify 版本 |
| CLI 帮助 | `graphify --help` | 确认可用命令、参数和输出路径语义 |
| Codex skill | `C:\Users\Chihong\.codex\skills\graphify\SKILL.md` | Agent 模式 `/graphify` 工作流 |
| Agents skill | `C:\Users\Chihong\.agents\skills\graphify\SKILL.md` | 其他 agent 环境中的同类工作流 |

当前本机已验证：

```powershell
graphify --version
```

输出：

```text
graphify 0.9.10
```

本机 `graphify --help` 已确认包含：

- `install`
- `update <path>`
- `extract <path>`
- `query "<question>"`
- `path "A" "B"`
- `explain "X"`
- `cluster-only <path>`
- `label <path>`
- `benchmark [graph.json]`
- `export callflow-html`

## 3. Graphify 是什么

Graphify 是一个把文件集合转换为可查询知识图谱的工具。它面向代码、文档、论文、图片、音视频等输入，生成：

- 图数据：`graph.json`
- 审计报告：`GRAPH_REPORT.md`
- 可视化图：`graph.html`
- 可选导出：Obsidian vault、SVG、GraphML、Neo4j/FalkorDB Cypher、wiki、MCP server 等

Graphify 的核心价值不是简单全文检索，而是把输入语料中的节点和关系组织成图谱，用于：

- 查询概念之间的路径。
- 发现跨文件、跨模块、跨论文的联系。
- 识别高连接度节点。
- 聚类社区。
- 对代码库或文档库做结构化导航。

Graphify 输出是 derived artifact。它适合作为投影、索引和分析结果，不应被当成原始内容 source of truth。

## 4. 输入类型

Graphify 可以处理多类输入：

| 输入类型 | 典型文件 | 抽取方式 | 是否通常需要 LLM |
|---|---|---|---:|
| 代码 | `.py`, `.ts`, `.go`, `.rs`, `.java` 等 | AST structural extraction | 否 |
| Markdown/文本 | `.md`, `.txt` | semantic extraction | 是 |
| 论文/PDF | `.pdf` 或转换后的论文文本 | semantic extraction | 是 |
| 图片 | `.png`, `.jpg` 等 | vision/semantic extraction | 是 |
| 音视频 | `.mp4`, `.mp3` 等 | 先转录，再作为文本处理 | 是 |
| 已有图谱 | `graph.json` | 查询/聚类/解释 | 否 |

关键判断：

- 纯代码图谱可以不依赖 LLM。
- 文档、论文、图片要抽取“语义关系”，通常需要 LLM。
- 已经生成的图谱查询不需要 LLM，只读取已有 `graph.json`。

## 5. 两种使用模式

Graphify 有两种主要使用模式：

```text
Agent 模式：/graphify <path>
Headless CLI 模式：graphify extract <path> ...
```

二者目标相同，但运行机制不同。

### 5.1 Agent 模式

Agent 模式通过安装到 AI coding assistant 的 skill 运行。常见调用：

```text
/graphify
/graphify <path>
/graphify <path> --mode deep
/graphify <path> --update
/graphify <path> --cluster-only
/graphify <path> --no-viz
/graphify <path> --wiki
/graphify query "<question>"
/graphify path "A" "B"
/graphify explain "X"
```

Agent 模式的特点：

- 适合交互式代码库、文档库、论文库分析。
- 当前 agent 可以参与 semantic extraction。
- 对 docs/papers/images，如果没有 Gemini key，skill 允许由 host agent 本身完成语义抽取。
- 如果已有 `graphify-out/graph.json`，自然语言查询会优先复用已有图，而不是重新构建。
- 会在对话中返回报告摘要和后续可探索问题。

Agent 模式的默认输出目录：

```text
<scan_root>/graphify-out/
```

常见输出：

```text
graphify-out/
  graph.json
  GRAPH_REPORT.md
  graph.html
  cost.json
  manifest.json
```

### 5.2 Headless CLI 模式

Headless CLI 适合脚本、CI、自动化服务和明确 backend 的批处理。

主入口：

```powershell
graphify extract <path>
```

常用参数：

```powershell
graphify extract <path> `
  --backend gemini|kimi|claude|openai|deepseek|ollama `
  --model <model> `
  --mode deep `
  --token-budget 60000 `
  --max-concurrency 4 `
  --api-timeout 600 `
  --out <dir> `
  --no-cluster
```

重要输出路径语义：

```powershell
graphify extract <path> --out <dir>
```

写入的是：

```text
<dir>/graphify-out/
```

不是：

```text
<dir>/graph.json
```

因此任何项目接入 Graphify CLI 时，都必须明确自己的输出路径契约：是直接读取 `<dir>/graphify-out/graph.json`，还是把它复制、移动或转换到项目自己的图谱目录。

`--api-timeout` 只限制单次 LLM 请求，不限制整批 corpus 的总执行时间。批量论文的完整运行时间可能超过单次请求超时；外层脚本不应再硬编码一个更短的固定进程超时。Graphify 在已有 `graphify-out/manifest.json` 和 `graph.json` 时会执行增量扫描，因此接入方应保留 `graphify-out/cache/`，不要在每次运行前删除整个输出目录。

### Canonical-only 论文约束

论文库接入时，Graphify 的输入必须是 `library/papers/*.md` 这层 Canonical Markdown。`source/*.pdf`、原始 URL、Zotero 附件和临时下载文件属于上游摄入材料，不能在图谱阶段直接读取。正确顺序是：

```text
PDF/URL/Zotero -> 摄入或修复 -> Canonical Markdown -> Graphify -> graph/投影
```

如果 Canonical 是 `metadata_only`、`abstract_only`、无有效全文标记或正文不足，接入方应将论文留在待审核状态，而不是用 PDF 旁路补抽取。正文级 `content_kind=fulltext` 且长度达标时，可覆盖历史遗留的外层 quality 标记。若图谱证据出现 `.pdf`、URL 或 `external_pdf:`，接纳阶段应拒绝替换旧图。

## 6. 核心工作流

Graphify 的完整构建流程可以理解为：

```text
输入路径
  -> detect corpus
  -> structural extraction
  -> semantic extraction
  -> merge extraction
  -> build graph
  -> cluster communities
  -> label communities
  -> generate report
  -> export graph
  -> query/path/explain
```

### 6.1 Detect corpus

Graphify 会先扫描输入目录，识别：

- code files
- documents
- papers
- images
- videos
- skipped sensitive files

如果 corpus 过大，Agent 模式应提示用户缩小扫描范围。

接入方必须明确扫描根目录，避免把生成物、缓存、依赖目录、敏感文件扫进图谱。

### 6.2 Structural extraction

代码文件走 structural extraction。其特点：

- 基于 AST。
- 不需要 LLM。
- 适合提取函数、类、模块、调用、依赖等结构关系。
- 成本低，可在代码变更后频繁更新。

相关 CLI：

```powershell
graphify update <path>
```

`update <path>` 的帮助文本说明它用于重新提取代码文件并更新图谱，且不需要 LLM。

### 6.3 Semantic extraction

文档、论文、图片等内容走 semantic extraction。其特点：

- 需要语义理解。
- 可能消耗 LLM token。
- 适合抽取概念、方法、主题、约束、跨文档关系等。
- 输出关系应带审计语义，不能编造边。

Agent 模式下，semantic extraction 可由 host agent 或 Gemini 完成。

Headless CLI 下，需要显式 backend 或可自动检测的 API key。可用 backend 以本机 `graphify --help` 为准：

```text
gemini, kimi, claude, openai, deepseek, ollama
```

### 6.4 Merge extraction

Graphify 会合并 structural extraction 和 semantic extraction：

```text
AST nodes/edges + semantic nodes/edges -> merged extraction
```

接入方需要注意：

- 同一个节点可能来自结构抽取或语义抽取。
- semantic edge 可能包含置信度或推断属性。
- 不要假设所有边都同等可靠。

### 6.5 Build graph

Graphify 根据 extraction 构建 graph：

- 默认可视为无向图使用。
- 如果传入 directed 语义，则保留 source -> target 方向。
- 空图应视为失败或至少是强警告。
- 大图导出 HTML 前应评估节点规模。

### 6.6 Cluster and label

Graphify 会对图做 community detection，并为 community 打标签。

输出中常见内容：

- God Nodes
- Surprising Connections
- Suggested Questions
- cohesion scores

Honesty rule：

- 不要隐藏 cohesion 原始数值。
- 不要把推断关系写成确定事实。
- 不要发明不存在的边。

### 6.7 Export

默认或常见输出：

```text
graphify-out/
  graph.json
  GRAPH_REPORT.md
  graph.html
```

可选输出：

```text
graphify-out/obsidian/
graphify-out/wiki/
graphify-out/cypher.txt
graphify-out/graph.svg
graphify-out/graph.graphml
```

导出能力以 `graphify --help` 和 skill references 为准。

## 7. 图谱查询

已有 `graph.json` 后，Graphify 可以查询，不必重建。

常用命令：

```powershell
graphify query "<question>"
graphify query "<question>" --dfs
graphify query "<question>" --budget 1500
graphify path "A" "B"
graphify explain "X"
graphify cluster-only <path>
graphify label <path>
graphify benchmark graph.json
```

查询原则：

- 查询应基于已有 graph。
- 回答应引用图谱中的节点、边和 source location。
- 如果图中没有证据，应说明没有证据，而不是补全想象。
- BFS 适合广度探索。
- DFS 适合追踪特定路径。
- `path` 适合解释两个概念、模块或实体之间的连接。
- `explain` 适合解释单个节点及其邻居。

## 8. LLM 边界

### 8.1 不需要 LLM 的情况

以下情况通常不需要 LLM：

- 纯代码 AST 抽取。
- `graphify update <path>` 的代码更新路径。
- 已有 `graph.json` 上的 `query`、`path`、`explain`。
- `benchmark`。
- 部分格式导出。

### 8.2 需要 LLM 的情况

以下情况通常需要 LLM：

- Markdown 文档语义抽取。
- 论文语义抽取。
- 图片理解。
- community label 生成。
- 需要跨文档关系推断的 deep mode。

### 8.3 Agent 模式和 CLI 模式的差异

Agent 模式：

- 如果有 Gemini key，可使用 Gemini。
- 如果没有 Gemini key，host agent 可以承担 semantic extraction。
- 不应因为缺少 OpenAI、Anthropic 等 key 就停止 Agent 模式流程。

Headless CLI 模式：

- 需要可调用的 backend。
- backend 由 `--backend` 或环境变量决定。
- 可选 backend 包括 `gemini`、`kimi`、`claude`、`openai`、`deepseek`、`ollama`。
- 本地模型通常应降低并发，例如 `--max-concurrency 1`。

## 9. 接入方接口契约

任何项目接入 Graphify 前，应明确以下契约。

### 9.1 输入契约

必须明确：

- 扫描根目录。
- 文件类型范围。
- 忽略规则。
- 是否允许扫描生成物。
- 是否允许扫描依赖目录。
- 是否允许扫描包含密钥或隐私信息的文件。

推荐做法：

```text
只扫描要建图的 source corpus。
排除 graphify-out、缓存、依赖、注册表、临时文件和敏感文件。
```

### 9.2 输出契约

必须明确：

- Graphify 原始输出目录在哪里。
- 项目代码读取哪个 `graph.json`。
- 是否保留 `GRAPH_REPORT.md` 和 `graph.html`。
- 是否需要把 `graphify-out/graph.json` 复制到项目自己的图谱目录。
- 失败时是否保留部分输出用于诊断。

特别注意：

```text
graphify extract <path> --out <dir>
```

生成的是：

```text
<dir>/graphify-out/graph.json
```

### 9.3 LLM 契约

必须明确：

- 当前调用是 Agent 模式还是 headless CLI 模式。
- 是否需要 semantic extraction。
- 使用哪个 backend。
- API key 从哪里来。
- 模型名称从哪里来。
- token budget 和 timeout 如何配置。
- 失败时是否 fallback 到无语义图谱、结构图谱或跳过图谱。

不要把 Agent 模式的“host agent 可承担语义抽取”和 headless CLI 的“需要 backend/API key”混为一谈。

### 9.4 状态和幂等契约

接入方应明确：

- 什么输入变化会触发重建。
- graph 是否可从 source corpus 重建。
- 是否记录生成时的 corpus hash。
- 是否允许增量更新。
- 图谱变小是否应阻止覆盖旧图。
- 是否保留 cost/token 记录。

Graphify skill 中包含 shrink guard、manifest、cost tracker、health check 等概念。接入方应根据项目需要选择实现，不要默默覆盖一个更完整的旧图。

## 10. 常见调用模板

### 10.1 查看本机版本

```powershell
graphify --version
```

### 10.2 查看 CLI 契约

```powershell
graphify --help
```

或只看关键命令：

```powershell
graphify --help | Select-String -Pattern 'extract <path>|update <path>|query "<question>"|path "A" "B"|explain "X"|--backend B|--out DIR'
```

### 10.3 Agent 模式构建当前目录

```text
/graphify .
```

### 10.4 Agent 模式查询已有图

```text
/graphify query "What are the central concepts?"
/graphify path "ConceptA" "ConceptB"
/graphify explain "ConceptA"
```

### 10.5 CLI 模式构建图谱

```powershell
graphify extract . --backend openai --model <model> --out .
```

输出：

```text
.\graphify-out\graph.json
.\graphify-out\GRAPH_REPORT.md
.\graphify-out\graph.html
```

### 10.6 CLI 模式使用本地模型

```powershell
graphify extract . --backend ollama --model <model> --max-concurrency 1 --out .
```

### 10.7 只做代码更新

```powershell
graphify update .
```

### 10.8 查询已有图

```powershell
graphify query "How does the data flow through the system?"
graphify path "Parser" "Database"
graphify explain "Parser"
```

### 10.9 跳过 HTML 可视化生成

Agent 模式支持跳过 HTML 可视化：

```text
/graphify <path> --no-viz
```

含义是跳过 visualization，只保留报告和 JSON 等非 HTML 图谱数据。Graphify skill 明确说明默认会生成 HTML，除非传入 `--no-viz`。

本机 Graphify 0.9.10 CLI 中，`cluster-only` 也暴露了 `--no-viz`：

```powershell
graphify cluster-only <path> --no-viz
```

适用场景是已有 `graph.json`，只重跑聚类或报告相关流程，但不生成 `graph.html`。

注意：本机 `graphify extract <path>` 的 help 未显示 `--no-viz` 参数。因此 headless 全量抽取不能假设支持：

```powershell
graphify extract <path> --no-viz
```

如果 headless 全量抽取必须禁止 HTML，有三种处理方式：

1. 优先使用 Agent 模式的 `/graphify <path> --no-viz`。
2. 若只需要原始抽取结果，可评估 `graphify extract <path> --no-cluster`，但它不是“只禁用 HTML”，而是跳过 clustering 并写 raw extraction，功能面更窄。
3. 在外层 wrapper 中删除或忽略 `graphify-out/graph.html`，但这只是清理产物，不是阻止生成。

## 11. 输出物说明

### 11.1 `graph.json`

核心图数据。后续 query、path、explain、外部系统导入都依赖它。

接入方不要假设内部 schema 永远稳定。应通过最小样例和当前版本验证字段：

- nodes
- edges
- node id
- source
- target
- relation
- attributes
- source location
- confidence 或 edge context

### 11.2 `GRAPH_REPORT.md`

人类可读报告。通常包含：

- corpus 摘要
- token cost
- god nodes
- surprising connections
- suggested questions
- community 信息
- cohesion scores

适合给 agent 或开发者快速理解图谱质量。

### 11.3 `graph.html`

交互式可视化图。大图可能需要降采样或聚合视图。节点数很大时，生成 HTML 前应提醒或跳过。

### 11.4 `cost.json`

记录 token 使用。适合排查 semantic extraction 成本。

### 11.5 `manifest.json`

记录 Graphify 更新状态和输入文件信息，用于后续增量更新。接入方如果自己管理状态，也应保留等价信息。

## 12. 风险和注意事项

### 12.1 不要混淆包名和命令名

本机命令名是：

```powershell
graphify
```

本机更新时使用的 PyPI 包是：

```text
graphifyy
```

后续安装说明应先以本机验证和官方当前说明为准。

### 12.2 不要把 Graphify 输出当 source of truth

Graphify 输出是源语料的图谱投影。源文件才是事实来源。图谱可以删除、重建、更新，也可能受模型、prompt、版本影响。

### 12.3 不要忽略输出路径

`--out` 的语义容易误读。它不是直接输出 `graph.json` 到该目录，而是写入该目录下的 `graphify-out/`。

### 12.4 不要把 code-only 和 docs/papers 混为一谈

代码 AST 抽取不需要 LLM。论文和文档的语义图谱通常需要 LLM。判断是否需要 LLM 时必须先看 corpus 类型。

### 12.5 不要隐藏不确定边

Graphify 的价值之一是带审计语义。若关系是推断或不确定，应保留 `INFERRED`、`AMBIGUOUS` 等语义，不要在业务侧渲染成确定事实。

### 12.6 不要无提示覆盖旧图

如果新图节点数明显少于旧图，可能是扫描范围、忽略规则、LLM 失败或路径错误导致。覆盖前应有 shrink guard 或人工确认。

## 13. 后续对接前检查清单

接入 Graphify 前：

- [ ] 确认 `graphify --version`。
- [ ] 确认 `graphify --help` 中目标命令仍存在。
- [ ] 明确使用 Agent 模式还是 headless CLI 模式。
- [ ] 明确输入 corpus 范围。
- [ ] 明确忽略规则。
- [ ] 明确是否需要 semantic extraction。
- [ ] 明确 LLM backend、model、API key、timeout、token budget。
- [ ] 明确输出目录和项目读取路径。
- [ ] 明确失败时 fallback 行为。
- [ ] 明确是否保留报告、HTML、cost、manifest。
- [ ] 明确查询命令读取哪个 `graph.json`。

运行 Graphify 后：

- [ ] 检查 `graphify-out/graph.json` 是否存在。
- [ ] 检查 graph 非空。
- [ ] 检查 `GRAPH_REPORT.md` 是否生成。
- [ ] 检查 token cost 是否符合预期。
- [ ] 检查 high-degree nodes 是否合理。
- [ ] 检查是否有异常 shrink。
- [ ] 用 `graphify query` 做一个最小查询。
- [ ] 用 `graphify path` 或 `graphify explain` 做一个结构验证。

## 14. 最小验收命令

```powershell
graphify --version
graphify --help | Select-String -Pattern 'extract <path>|update <path>|query "<question>"|--backend B|--out DIR'
```

如果已有图：

```powershell
graphify query "What are the central nodes?"
graphify benchmark graphify-out/graph.json
```

如果要做 headless 构建，先用小型语料验证：

```powershell
graphify extract <small-corpus> --backend <backend> --model <model> --out <temp-output>
```

确认：

```text
<temp-output>/graphify-out/graph.json
<temp-output>/graphify-out/GRAPH_REPORT.md
<temp-output>/graphify-out/graph.html
```

都按预期生成后，再接入项目主流程。
