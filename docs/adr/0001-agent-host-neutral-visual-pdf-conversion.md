# ADR-0001：以 Agent Host 中立协议内化视觉 PDF 转译

Status: accepted
Date: 2026-08-11

## Context

PaperBase 当前把 PDF 转换结果直接作为 Canonical Markdown。该路径无法可靠处理双栏阅读顺序、复杂公式、跨栏图表和局部扫描内容。近期人工协作流程已经证明，确定性转换草稿、逐页渲染与视觉 subagent 校正可以提高这类论文的转换质量，但该流程仍依赖会话内编排，失败后也缺少稳定的续作边界。

PaperBase 需要内化这条能力，同时满足以下约束：

- 不绑定 OpenAI API 或任何单一 Agent 平台。
- 视觉转译是普通 `ingest` 的一种 PDF 转换方法，不新增独立视觉 CLI 命令。
- Agent Host 负责调用自己的视觉 subagent；PaperBase 只提供文件任务协议、状态推进和验收。
- 失败后必须续接同一运行，不能因重试产生无意义的新运行目录。
- Canonical Markdown 仍是唯一内容 source of truth，成功后不长期保留视觉运行收据。
- 项目内 `skills/paperbase/` 是 skill 的唯一编辑源；全局 skill 只是验证后的部署副本。

## Decision

采用一个可重复调用的 PDF 转换边界：

`progressPdfConversion(source_pdf, conversion_config)`

它只返回以下统一结果之一：

- `ready(markdown, assets)`：质量门通过，可以由 ingest 单写者写入 Canonical。
- `agent_action_required(task_package)`：已准备可移交给 Agent Host 的任务包。
- `needs_confirmation(warnings)`：仅剩可接受但不能自动忽略的低风险警告。
- `failed(error)`：根据错误性质映射到状态机。

配置保持最小：

```yaml
conversion:
  pdf:
    visual:
      mode: off       # off | auto | always
      model: ""       # Agent Host 原样解释的手动模型名称
      chunk_pages: 5
      retry: 1
```

代码默认 `mode: off`，以保持现有行为。项目配置可以显式启用 `auto` 或 `always`。PaperBase 不维护跨 Agent 平台的模型名称映射；模型无效、无视觉能力或无 subagent 能力时直接报错。

运行时采用每篇论文一个可恢复的临时 Visual Repair Run：

- `prepare` 优先复用与当前源 PDF、候选稿、模板版本和分块方案兼容的未完成运行。
- 模型名称变化、短暂 429/503/超时或 Agent Host 重启可以续接同一运行。
- 源 PDF、候选稿、提示模板或分块方案变化时创建新运行。
- Run Lease 保证同一时刻只有一个 Agent Host 推进一篇论文；过期租约可恢复。
- orchestrator 独占写入 `run.json`；worker 只写自己的 `result.md` 和 `result.json`。
- 核心页归属不重叠，相邻页只作为只读上下文。
- 独立边界复核覆盖首尾、分块接缝、失败块和参考文献区域。

视觉任务通过标准文件任务包交给 Agent Host。项目 skill 中维护一份 host-neutral 提示模板；task 文件记录手工模板版本，不记录提示词哈希。Agent Host 可用自己的原生 subagent 编排能力，但不得绕过任务包的页归属和写入边界。

公式、表格或图像内容不得猜测。能可靠重建时输出 LaTeX/Markdown；不能可靠重建但能定位完整区域时，允许创建局部保真裁剪资产并产生人工确认警告；无法定位或含义仍有歧义时阻塞采用。裁剪在本地从已渲染页生成，本身不额外消耗视觉 token。

成功采用后删除临时运行目录，仅保留源 PDF、Canonical Markdown、相对资产路径和现有 manifest 字段。失败运行保留以便续作。哈希仅用于既有 source-of-truth 边界和一个运行级候选稿指纹，不引入逐页、提示词或调用级哈希。

状态映射如下：

| 条件 | 状态 |
|---|---|
| 模型无效、无视觉能力、无 subagent 能力 | `BLOCKED` |
| 429、503、超时等临时故障，自动重试至多一次后仍失败 | `FAILED_RETRYABLE` |
| 视觉工作完成但仍有低风险警告或质量门未自动通过 | `NEEDS_REVIEW` |
| 全部质量门通过 | `NORMALIZED` |

警告只能由用户确认；Agent 不得自行推断同意。确认入口仍属于普通 ingest 流程，可通过 `--accept-visual-warnings` 表达，不新增视觉专用命令。

## Skill 发布门禁

1. 先完成核心实现和定向测试。
2. 只修改项目内 `skills/paperbase/`，包括 host-neutral 提示参考文件。
3. 用既定四篇论文验证路由、续作、质量门和警告确认。
4. 由用户确认项目 skill 行为。
5. 最后通过项目内 `install.ps1` 同步到用户选择的全局 Agent skill 目录。

`install.ps1` 是 Windows 的正式安装与更新入口，不另造旁路复制流程。它支持 `codex | claude | both`，默认选择 Codex，统一写入各 Agent 的 `skills\paperbase` 目录。覆盖更新时分别原样保留 Codex 和 Claude Code 现有的 `workspaces.json`；项目 skill 通过验证并获得用户确认后，再用该脚本部署并核对全局受管文件。

## Consequences

### Positive

- PaperBase 不依赖某家模型 API，Codex、Claude Code 或其他 Agent Host 可复用同一任务协议。
- 失败工作可以续接，已完成分块不会因短暂故障重做。
- Canonical 写入仍由 ingest 单写者控制，临时 worker 不能污染 source of truth。
- 成功后不积累视觉运行收据，保持科研级本地仓库简洁。

### Negative

- 普通 CLI 在没有 Agent Host 时只能准备任务并返回“需要 Agent 操作”，不能自行调用视觉模型。
- 模型名称由用户手动填写，跨平台可移植性依赖 Agent Host 的实际支持。
- 保真裁剪会降低机器可读性，因此必须进入人工确认而不是静默通过。

## Rejected alternatives

- **直接调用 OpenAI API 编排**：违反 Agent Host 中立约束。
- **新增 `paperbase visual` 命令**：把转换方法泄漏为并列工作流，增加用户心智负担。
- **成功后永久保存完整运行收据**：源 PDF 与 Canonical 已足以重建，额外收据没有当前价值。
- **立刻引入通用 converter 插件框架**：AnyDoc 尚未进入实现范围，为未来候选提前抽象不符合 YAGNI。
- **用 AnyDoc 替换主引擎**：其本地 PDF 能力不覆盖视觉 OCR、公式重建和 PDF 资产保留，先作为未来 P3 候选评估。
