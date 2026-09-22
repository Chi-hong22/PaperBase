# PaperBase Skill - 更新日志

## [2026-09-22-v1.6] - Graphify 调用统一为本机扫描根约定（TD-GRAPH-002）

- 所有 Graphify 调用示例统一为「先切工作目录到本机 `library/papers`，再运行 `/graphify . --update --no-viz`」，覆盖 SKILL.md、README 与全部 references，替换旧的 `/graphify library/papers …` 形式；各主机路径本地解析，不硬编码绝对路径。
- 诊断命令修正：graphify 0.9.10 CLI 不存在的 `graphify detect` 全部替换为实测有效的 `graphify.detect` Python 探测命令（在 `library/papers` 目录下用 `graphify-out/.graphify_python` 运行）。
- `query_router.py` 的 `graphify query` 显式传 `--graph` 指向已接纳图谱 `graph/graph.json`，去除对工作目录下 `graphify-out` 的隐式依赖，并新增回归测试 `tests/unit/test_query_router.py`。
- 配套（仓库侧）：`paperbase graph preflight` 增加游离 `graphify-out/` 与异机 `.graphify_root` 的环境警告；本机路径类文件（`.graphify_root`、`.graphify_python`、`cache/stat-index.json`）从 Syncthing 同步中排除。

---

## [2026-09-12-v1.5] - 视觉返工重审入口与故障恢复文档

- **新增 `paperbase ingest --re-review`**：仅当 run 处于 `ready_to_adopt` 时有效；保留各 chunk 的 `completed` 状态，作废已失效的 boundary-review 产物与 run 局部 fallback-assets，状态回 `running`，并由同一次调用重新准备边界复核任务包、返回 `AgentActionRequired`。可与 `--accept-visual-warnings` 组合；条件不满足报 `visual_re_review_invalid`（映射 `NEEDS_REVIEW`）。取代手工"改 `run.json` state + 删 `boundary-review/` 目录"的旧恢复流程。
- **错误信息改进**：`visual_warning_adoption_failed` 及资产冲突类错误列出具体冲突文件路径；`references_unparseable` 说明解析器仅支持 `[n]` 连续编号文献，并指路"补编号后重跑"。
- **`paperbase remove` 审计缓存 stash**：默认把 `paper_dir/.visual-auto-audit/` 保留到 `library/audits-stash/<storage_id>/` 并打印恢复方法；重摄入同一 PDF 前移回 `library/papers/<storage_id>/.visual-auto-audit` 即可复用。
- **文档增补**：SKILL.md 新增视觉阶段协议小节、瘦身典型对话并与 `AGENTS.md` Invariants 去重（v1.5）；`references/visual_pdf_conversion.md` 新增"故障恢复"章节；`references/troubleshooting.md` 增加索引；新增 `docs/adr/0002-visual-rework-re-review-via-cli.md`；CONTEXT.md 收录 Re-review 术语；ROADMAP 登记作者-年份式（APA）参考文献解析工单。

---

## [2026-07-16-v1.4] - Graphify 扫描根一致性护栏

- 固定 Agent 增量流程的唯一扫描根为 `<base_dir>/library/papers`，覆盖 detect、cache、merge 和 manifest。
- 发现旧图与本次根不一致或混合 `source_file` 形式时，停止合并和 `adopt`，先恢复旧图。
- 将代码级根身份校验登记到本地工单 `.scratch/graphify-scan-root-consistency/issues/01-enforce-scan-root-consistency.md`（`TD-GRAPH-001`）。

---

## [2026-07-16-v1.3] - 并行语义 subagents 契约

- 语义 Agent 固定为编排者，不得自行读取正文或串行代做语义抽取。
- 2 篇及以上 Canonical Markdown 必须由至少 2 个 subagents 并行处理；单篇也必须委派给 subagent。
- 宿主不支持 subagents 时明确报告阻塞，不得静默切换到 PaperBase 本地 LLM。

---

## [2026-07-16-v1.2] - Agent-first CLI 优先级

- `paperbase ingest` 默认完成摄入和全文索引后交接给 Graphify Agent，不再自动调用本地 LLM。
- 新增 `--headless-graph`，仅在明确降级时读取 `config/paperbase.yaml`；与 `--no-graph` 互斥。
- 增加 Canonical Markdown 进入 Graphify semantic queue 的回归契约，确保正文执行语义抽取而非仅被扫描。

---

## [2026-07-16-v1.1] - 私有语料与图谱边界同步

- 将 Canonical 路径统一为 `library/papers/p_<storage_id>.md`，同名目录保存 manifest、源文件和派生数据。
- 明确真实论文内容只保留在本地并由 Git 忽略；`.graphifyignore` 独立重新纳入 Canonical，避免与 Graphify 冲突。
- 固化 Agent 建图顺序 `preflight → /graphify → adopt`，并说明 headless `graph update` 才读取本地 LLM 配置。
- 将 `BLOCKED` 论文定义为不可重试候选，要求增量检测与 Graphify corpus 同时排除。

---

## [2026-07-09-v2] - 查询系统全面优化

### ✨ 新增功能

- **query topic --include-refs** - 扩展查询到引用文献
- **分词匹配** - 支持多词查询（如 "deep learning"）
- **自动索引** - 摄入时自动更新全文检索

### 🐛 Bug 修复

- **query topic 覆盖率** - 从 62.5% 提升至 100%
- **query related** - 修复节点 ID 匹配问题，恢复功能
- **结果去重** - 避免同一论文重复显示
- **节点格式兼容** - 支持新旧格式（`p_xxx` 和 `p_xxx_paper`）

### 📊 改进效果

| 功能 | 之前 | 现在 |
|------|------|------|
| query topic 覆盖率 | 62.5% | 100% |
| query related | 不可用 | 正常工作 |
| 新论文索引 | 手动 | 自动 |

**验证：**
```bash
paperbase query topic "transformer"  # 2 篇 ✓
paperbase query topic "attention" --include-refs  # 1 本地 + 1 引用 ✓
paperbase query related "fallback:c23839e43de0a596"  # 3 篇 ✓
```

---

## [2026-07-09] - 重大功能增强与修复

### ✨ 新增功能

#### 1. 自动文本分块
- **摄入时自动生成** `chunks.jsonl`
- 支持全文检索索引构建
- 按段落智能分块（最大 2048 字符）
- 智能断句（句号、问号、感叹号）

**影响：**
- `paperbase index` 现在可以找到 chunks 文件
- `paperbase search` 全文检索功能可用

#### 2. query 命令支持 graphify 0.9.10
- **适配 hyperedges 格式** - graphify 新版本使用超边
- 自动转换 hyperedges → edges（完全图）
- `query related` 和 `query topic` 恢复正常

**验证：**
```bash
paperbase query related "fallback:78c552c752e0e59b"  # 找到相关论文 ✓
paperbase query topic "transformer"                   # 找到 2 篇论文 ✓
```

#### 3. status 命令增强
- **新增过滤参数**：`--year` 和 `--state`
- 支持组合过滤

**示例：**
```bash
paperbase status --year 2021              # 2021 年的论文
paperbase status --state ready            # 已就绪的论文
paperbase status --year 2021 --state ready # 组合过滤
```

#### 4. remove 命令自动化
- **新增参数**：`--yes` / `-y` 和 `--force` / `-f`
- 支持非交互式删除
- 适合脚本和后台自动化

**示例：**
```bash
paperbase remove <paper_id> --yes    # 自动确认删除
paperbase remove <paper_id> -y       # 短参数
```

#### 5. 批量补生成 chunks 脚本
- **新增脚本**：`scripts/regenerate_chunks.py`
- 为现有论文批量生成 chunks.jsonl
- 支持单篇或全部论文
- 自动跳过已有 chunks（`--force` 覆盖）

**用法：**
```bash
python scripts/regenerate_chunks.py              # 全部论文
python scripts/regenerate_chunks.py --paper-id <id>  # 单篇
python scripts/regenerate_chunks.py --force       # 强制覆盖
```

### 🐛 Bug 修复

#### 1. 扁平化结构统计错误
- **修复 doctor 命令**：`glob("p_*")` 重复计数文件+目录
- 显示 6 篇 → 正确显示 6 篇

#### 2. query related 命令不工作
- **问题**：使用 paper_id 但图谱存储 storage_id
- **修复**：添加 paper_id → storage_id 映射转换
- **验证**：正确显示相关论文及元数据

#### 3. query topic 命令不工作
- **问题 A**：字段名错误（`type` → `file_type`）
- **问题 B**：查询逻辑错误（不存在的 `attributes.topics`）
- **修复**：在 `label` 和 `norm_label` 中搜索关键词
- **验证**：`query topic "transformer"` 找到 2 篇论文

#### 4. manifest path 引用错误
- **修复相对路径**：`./paper.md` → `../{storage_id}.md`
- 适配扁平化结构（paper.md 与目录同级）

#### 5. 文档与实现不一致
- 移除不存在的 `list` 命令引用（7 处）
- 更新所有路径示例为扁平化结构
- 修复 troubleshooting 文档中的命令示例

### 📚 文档更新

#### 内化外部依赖文档
- **paper-fetch 安装指南** - 从外部链接改为内嵌完整说明
- **graphify 安装指南** - 同上
- **集成故障排查** - 更新为最新实现

#### 结构说明更新
- 标注当前使用**扁平化结构**（`p_xxx.md` + `p_xxx/`）
- 说明优势：graphify 批量扫描效率更高
- 更新所有示例路径

### 🔧 技术改进

#### 核心模块
- `graph_query.py` - 支持 hyperedges 自动转换 + paper_id 映射
- `online_ingest.py` - 集成 chunker
- `ingest.py` - 同上集成
- `status.py` - 添加过滤参数
- `remove.py` - 添加自动化参数
- `doctor.py` - 修复论文计数
- `query.py` - 添加 paper_id ↔ storage_id 映射

#### 测试覆盖
- `test_online_ingest.py` - 更新路径为扁平化结构
- 所有单元测试通过 ✓

### 📊 性能影响

| 功能 | 之前 | 现在 | 改进 |
|------|------|------|------|
| 论文统计 | 错误（重复计数） | 准确 | 100% |
| query related | 不可用 | 正常工作 | 从 0 → 可用 |
| query topic | 不可用 | 正常工作 | 从 0 → 可用 |
| 全文检索 | 部分论文 | 全部论文 | 覆盖率 100% |
| 批量删除 | 需交互 | 自动化 | 流程简化 |

### 📈 数据统计（验证结果）

| 指标 | 数值 |
|------|------|
| 论文总数 | 6 篇 |
| chunks 文件 | 6 个（全覆盖） |
| chunks 总大小 | 354.89 KB |
| 文本块总数 | 595 个 |
| 图谱节点 | 44 个 |
| 图谱边 | 49 条 |

### ⚠️ 破坏性变更

无破坏性变更。所有修改向后兼容。

### 🎯 升级指南

**从旧版本升级：**

1. **无需手动操作** - 新摄入的论文自动支持所有新功能

2. **现有论文补充 chunks**：
   ```bash
   # 使用补生成脚本
   python scripts/regenerate_chunks.py
   
   # 重建搜索索引
   paperbase index
   ```

3. **验证升级**：
   ```bash
   paperbase doctor                    # 检查论文数量正确
   paperbase status --year 2021        # 测试过滤功能
   paperbase query topic "transformer" # 测试图谱查询
   paperbase search "attention"        # 测试全文检索
   ```

### 📦 提交记录

```
2a09cf6 - fix(query): 修复 related 和 topic 命令
0c07c63 - feat(scripts): 添加补生成chunks脚本
dc3ca8a - docs(skill): 同步最新功能到全局 skill
8938bb7 - feat(query): 适配 graphify 0.9.10 hyperedges 格式
991927b - feat(cli): 增强 status 和 remove 命令
840e048 - docs(skill): 更新文档为扁平化结构
0ca027c - fix(flat): 修复扁平化结构导致的 3 个 bug
```

### 🙏 致谢

感谢用户反馈的 bug 报告和功能建议！

---

## 历史版本

### [2026-01-16] - 初始版本
- 基础摄入和图谱功能
- Registry 和状态管理
- 文档框架建立
