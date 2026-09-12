# ADR-0002：Agent 侧 Chunk 返工经 CLI `--re-review` 显式状态回退

Status: accepted
Date: 2026-09-12

## Context

ADR-0001 确立了视觉 PDF 转译的 Agent Host 中立协议：orchestrator 独占写入 `run.json`，worker 只写自己 chunk 目录内的 `result.md` 与 `result.json`，Agent Host 通过重复执行原 ingest 命令推进状态。该协议覆盖了 PaperBase 主动发起的续作路径，但没有覆盖另一类真实场景：Agent 在两次 ingest 调用之间，直接修正 `.visual-runs/<run_id>/chunks/` 下已 `completed` 的 chunk 结果文件。

这类返工本身是协议内行为——chunk 结果就是 worker（即 Agent）的输出物，Agent 修复自己的输出并不越界。问题出在 run 状态机与返工不同步：run 一旦推进到 `ready_to_adopt`，既有 boundary-review 产物基于返工前的内容，直接重复原 ingest 只会得到 `visual_boundary_review_invalid`，流程无法回到复核阶段。

在 2026-09 的一次 34 篇批量视觉摄入中，这类失步出现了 3 处。当时的恢复手法只能是协议外手工干预：手工把 `run.json` 的 state 改回运行中，再删除 `boundary-review/` 目录。这与 ADR-0001 "Agent Host 不编辑 lease 或 `run.json`"的边界直接冲突；手工步骤没有校验，容易漏作废 run 局部 fallback-assets，留下悬空的裁剪资产引用。

## Decision

为普通 `paperbase ingest` 增加 `--re-review` 旗标，作为 Agent 侧 chunk 返工后的官方重审入口：

- 仅当对应 run 处于 `ready_to_adopt` 时有效；其他状态下报 `visual_re_review_invalid`（映射 `NEEDS_REVIEW`），错误信息指引去掉旗标重跑。
- 保留各 chunk 的 `completed` 状态。返工对象就是 Agent 刚修复完成的输出；重置 chunk 状态只会迫使视觉 worker 重做已经修好的内容，浪费视觉 token，还引入再次出错的机会。
- 作废基于旧内容的 boundary-review 产物与 run 局部 fallback-assets，避免悬空引用进入采纳阶段。
- run 状态回 `running`，并由同一次 ingest 调用重新准备边界复核任务包、返回新的 `AgentActionRequired(task_package)` 交接；Agent Host 处理完任务包后按既有协议重复原命令。
- 可与 `--accept-visual-warnings` 组合：重审通过后若仍有低风险警告，走既有的用户确认门。

同时改进两处错误信息：`visual_warning_adoption_failed` 及资产冲突类错误列出具体冲突文件路径；`references_unparseable` 说明解析器仅支持 `[n]` 连续编号文献，并指路补编号后重跑。

## Consequences

### Positive

- Agent 侧返工有了与协议一致、可校验的恢复路径；run 状态机、boundary-review 产物与 chunk 输出的重新同步由 PaperBase 统一保证。
- 保留 chunk `completed` 使一次重审只消耗边界复核的视觉成本，不重做已修复内容。
- 错误信息携带冲突文件路径与解析器约束，Agent 无需猜测即可继续修复。

### Negative

- `--re-review` 只覆盖 `ready_to_adopt` 一个切入点；更早期阶段（Boundary Review 判 `rework_required` 后）仍按既有协议重复原 ingest 返还 `affected_chunk_ids`，Agent 需要区分两种恢复时机。
- 旗标带有状态相关的前置条件，`visual_re_review_invalid` 成为 Agent 需要认识的新失败码。

## Rejected alternatives

- **纯文档指引（教 Agent 手工改 `run.json` + 删 `boundary-review/` 目录）**：零代码成本，但把协议违规固化为标准操作；手工步骤无法保证 `updated_at`、状态溯源和 fallback-assets 一并作废。34 篇批次中的 3 处手工干预已经证明其易错性。
- **允许 Agent 直接编辑 `run.json`**：违反 ADR-0001 的单写者边界。run 状态机是 PaperBase 的不变式载体，Agent 绕过校验写入任意状态，会让续作、验收和采纳全部失去前提。
- **重审时把全部 chunk 状态重置为待处理**：实现最简单，但重置范围与返工范围不匹配——被重置的是 Agent 刚修复好的输出，重做它们既浪费视觉 token，又可能引入新问题。
- **独立子命令（如 `paperbase visual re-review`）**：重审在语义上是原 ingest 生命周期的受控回退，不是并列工作流；独立命令会重演 ADR-0001 已否决的"视觉命令泄漏为并列工作流"问题，还要重复处理 lease 与配置读取逻辑。
