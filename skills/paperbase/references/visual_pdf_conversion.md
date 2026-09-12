# 视觉 PDF 转换任务包

仅当普通 `paperbase ingest` 返回 `AgentActionRequired(task_package)` 时加载本文件。视觉校正仍是
普通 ingest 的一个转换分支；不要新增或调用独立的视觉转换命令。

## 宿主前提与统一结果

Agent Host 使用自己的原生视觉 subagent 能力读取 `task_package/task.json`。任务带有
`requested_model` 时，原样交给 Agent Host：不猜测、映射或替换模型名称；任务没有该字段时也不自行补造。
不得调用厂商 API，也不得把 PaperBase 的本地 LLM 当作视觉 worker 的后备通道。

模型为空或无效、Agent Host 不具备视觉输入能力、或不具备原生 subagent 能力时，报告 `BLOCKED` 并停止；
不要伪造 worker 输出。保留任务包，待具备能力的 Agent Host 续作。

普通 ingest 的可观察结果及状态映射如下：

| ingest 结果/诊断 | 状态 | 下一步 |
| --- | --- | --- |
| `AgentActionRequired(task_package)` | `BLOCKED` | 由 Agent Host 处理任务包，再重复执行原 ingest |
| 模型或视觉/subagent 能力缺失 | `BLOCKED` | 停止，保留现场 |
| 临时失败在允许的一次重试后仍失败 | `FAILED_RETRYABLE` | 保留现场，稍后重复原 ingest |
| 已完成但有低风险 warnings | `NEEDS_REVIEW` | 展示 warnings，等待用户明确确认 |
| Boundary Review `blocked` 且有 unresolved issues | `NEEDS_REVIEW` | 停止，保留问题；确认参数不能绕过 |
| Boundary Review `pass` 且无待确认警告 | `NORMALIZED` | 普通 ingest 单写者才可采用 Canonical |

`progressPdfConversion(source_pdf, conversion_config)` 与
`prepareOrProgressVisualConversion(source_pdf, candidate_markdown, visual_config)` 是项目可导入的推进边界；
它们由 PaperBase 管理 Run Lease。Agent Host 不编辑 lease 或 `run.json`，只完成下面任务包规定的输出，
然后重复原 ingest 让 PaperBase 校验和推进。

## 所有权和调度

对 worker 而言，PaperBase、task、run、Candidate、Canonical、manifest 及所有输入均为只读。只有普通 ingest
的采用步骤可以写 Canonical、assets 和 manifest；worker 不能修改它们，也不能改 `run.json`。

- 多个 visual chunk 可以使用 Agent Host 的原生 subagent 并行处理。
- 每个 chunk 的核心页不重叠；`context` 页只是只读参考，绝不输出为本块内容。
- Host 只调度和收集 task.json 指定的输出，不能把任务包内容复制回 Candidate，也不能创造额外文件。

## 按 task 类型写回

### 自动文字审计：`pdf_auto_text_audit`

审计 task 的 `kind` 为 `pdf_auto_text_audit`。worker 阅读 `candidate.md`、`layout.json`、源 PDF 引用和
`task.json`，只写 result.json。它必须沿用 task 中的 source/candidate 身份；其他文件、Candidate、Canonical
和 manifest 均为只读。`pass` 只适用于无风险的单栏阅读顺序；多栏、疑似阅读顺序问题或不确定布局写
`visual_required`。写完后重复执行原 ingest。

### 视觉分块：`visual-chunk-result-v1`

分块 task 的 `output_contract.result_schema_version` 是 `visual-chunk-result-v1`。chunk worker 只写本块目录内的
`result.md` 与 `result.json`，即“只写本块”；不得写其他 chunk、共享目录或 run 文件。

`result.md` 必须是 UTF-8，并对每个 core page 按 `task.chunk.core_pages` 顺序恰好写一次下列临时标记：

```text
<!-- paperbase:visual-page-start page={page} -->
本页 Markdown
<!-- paperbase:visual-page-end page={page} -->
```

不得在标记外写正文，不得写 context 或越界页面。`result.json` 按 task 的完整 `visual-chunk-result-v1` 契约写入
身份、`core_pages`、`covered_pages`、状态、warnings、未解决问题、失败码和 crop requests。`completed` 必须完整覆盖
本块核心页；可重试失败只能用 `http_429`、`http_503`、`timeout` 或 `channel_error`；保真裁剪只能是
`formula`、`table` 或 `image`，且每个 crop request 都要有 warning。

裁剪是从已渲染页本地保留的视觉证据，不是机器可读公式或表格。worker 只请求 bbox，不自行生成最终 Canonical
资产。

### Boundary Review：`visual-boundary-review-result-v1`

所有 chunk 已完成并可合并后，PaperBase 通过
`prepareOrValidateBoundaryReview(run_dir)` 创建或复用 `boundary-review/` 包。任务覆盖文档首尾、每个 chunk 接缝和
参考文献尾部区域。Boundary worker 只写 result.json；所有页图、逐页 Markdown、merged Markdown、task 和 run 输入均只读。

结果 schema 为 `visual-boundary-review-result-v1`。`checked_item_ids` 必须准确覆盖 task 的 item；`pass` 不得携带
affected chunks 或 unresolved issues；`rework_required` 必须用 `affected_chunk_ids` 指出需返工的块；`blocked` 必须报告
未解决问题。仅 Boundary Review `pass` 才可进入 Ready 判定。

## 续作与确认

每批 worker 写完后，重复执行**原 ingest 命令**，例如先前使用的是
`paperbase ingest --file paper.pdf`，就再次运行同一命令。不要创建新命令或手工改运行状态。

- `completed` chunk 会复用，不重做。
- 仅 `http_429`、`http_503`、`timeout`、`channel_error` 触发临时失败续作；核心最多重试一次。PaperBase 会保留已完成块并只把待重试块交回任务包；超过限制映射为 `FAILED_RETRYABLE`。
- Boundary Review `rework_required` 时，PaperBase 只返还 `affected_chunk_ids`，其他 completed 块继续复用。
- Boundary Review `blocked` 时停止并映射 `NEEDS_REVIEW`，保留 unresolved issues；
  `--accept-visual-warnings` 不能接受这类问题。`pass` 后才可能得到 Ready 或 warnings。

若结果含保真裁剪或其他 warnings，先将完整 warnings 展示给用户。只有用户明确确认，才把原命令改为例如：

```powershell
paperbase ingest --file paper.pdf --accept-visual-warnings
```

该参数是普通 ingest 的确认门，不是独立工作流。Agent 不得自行确认，也不得把裁剪说成机器可读结果。

## 故障恢复

以下手法来自 2026-09 一次 34 篇批量视觉摄入的真实故障沉淀。恢复动作全部走普通 ingest，不引入新命令。

### 改 chunk 后重审（Re-review）

**症状**：Agent 在两次 ingest 调用之间直接修改了 `.visual-runs/<run_id>/chunks/` 下的 chunk 结果文件（修复接缝、补参考文献编号等）后，重复原 ingest 报 `visual_boundary_review_invalid`——run 已停在 `ready_to_adopt`，既有 boundary-review 产物基于返工前内容，已经失效。

**恢复**：执行官方重审入口：

```bash
paperbase ingest <id> --re-review
```

`--re-review` 仅当 run 处于 `ready_to_adopt` 时有效：保留各 chunk 的 `completed` 状态（返工对象就是刚修复完成的输出，不重做），作废已失效的 boundary-review 产物与 run 局部 fallback-assets，状态回 `running`，并由同一次 ingest 调用重新准备边界复核任务包、返回新的 `AgentActionRequired` 交接。可与 `--accept-visual-warnings` 组合。run 不在 `ready_to_adopt` 时报 `visual_re_review_invalid`（映射 `NEEDS_REVIEW`），按错误信息去掉旗标重跑即可。

不要手工编辑 `run.json` 的 state 或删除 `boundary-review/` 目录；那是本旗标取代的旧手工流程。

### 采纳资产冲突

**症状**：采纳阶段报 `visual_warning_adoption_failed` 或资产冲突类错误；错误信息现在会列出具体冲突文件路径。

**处理**：按错误清单删除列出的残留文件，然后重复原 ingest 命令重跑采纳（若本轮本就需要用户确认警告，保留 `--accept-visual-warnings`）。这些冲突文件通常是上一轮中断的采纳留下的旧裁剪/fallback 资产：当时 Canonical 尚未写入，源 PDF 与 chunk 结果不受影响，删除是安全的；有效资产会在本次采纳中重新生成。

### 无编号参考文献

**症状**：`references_unparseable`。参考文献解析器仅支持 `[n]` 连续编号格式，作者-年份式（APA）文献列表无法解析。

**处理**：在 chunk 结果中为文献补连续编号 `[1]..[n]`。注意编号必须跨 chunk 全文连续，不能只在单块内连续。补完后用 `--re-review` 重审（见上）。

### Boundary Review 长行误报

reviewer 所用的读取工具对超过 2000 字符的超长行会显示截断，可能据此误报"摘要被截断"或正文缺失。复核这类问题必须用程序化字符计数（例如对原始行做长度统计）验证，不能以工具显示的目测结果为准。

### 其他

- `paperbase remove` 会把 `paper_dir/.visual-auto-audit/` 审计缓存 stash 到 `library/audits-stash/<storage_id>/` 并打印恢复方法；重摄入同一 PDF 前把它移回 `library/papers/<storage_id>/.visual-auto-audit` 即可复用，不必重新自动审计。
- 一次性的 `captcha verify failed` / `Model request failed` 直接重试原 ingest 即可，无需额外处理。

## 场景

1. **普通双栏 auto / always**：`auto` 先完成 `pdf_auto_text_audit`；审计返回 `visual_required` 后重复原 ingest，
   再并行处理不重叠 visual chunks。`always` 直接准备 visual chunks。两者都必须在 Boundary Review `pass` 后才可 Ready。
2. **失败续作**：chunk 写 `retryable_failure` 和稳定失败码；重复原 ingest 后只重交该 pending chunk，最多一次；
   其他 `completed` 块保留。
3. **能力缺失**：模型、视觉输入或原生 subagent 任一缺失时报告 `BLOCKED` 并停止，不调用厂商 API，也不改任务输出。
4. **裁剪 warning 确认**：worker 的 crop request 产生 warning；Boundary Review `pass` 后仍返回 `NEEDS_REVIEW`，
   先等用户明确确认，再用 `--accept-visual-warnings` 重复原 ingest。
