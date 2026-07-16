# Graphify 故障排查指南

## 推荐诊断顺序

```powershell
uv run paperbase graph preflight
graphify detect library/papers
uv run paperbase graph status
uv run paperbase doctor
```

PaperBase 的 Graphify 输入只应来自 `library/papers/p_*.md`。不要在图谱阶段直接读取 PDF、URL 或 Zotero 附件，也不要因为 Git 忽略了论文文件就强制暂存它们。

## 问题 1：Graphify 未发现 Canonical Markdown

**症状**：`graphify detect library/papers` 显示 0 个文档，或抽取后图谱为空。

**检查**：

```powershell
Get-ChildItem library/papers -Filter 'p_*.md' -File
Get-Content library/papers/.graphifyignore
```

`.gitignore` 与 `.graphifyignore` 职责不同：前者阻止真实论文进入 Git，后者决定 Graphify 是否扫描本地文件。PaperBase 的 `.graphifyignore` 必须包含 `!p_*.md`；需要阻塞的 Canonical 再用更靠后的精确规则排除。

## 问题 2：`NEEDS_REVIEW` 阻止更新或接纳

**症状**：`preflight` 报告正文不足，`graph update` 或 `graph adopt` 在调用/接纳 Graphify 前停止。

这是质量门的预期行为。修复对应 Canonical 的来源或正文，更新 manifest 哈希后重跑：

```powershell
uv run paperbase graph preflight
# Agent 中运行：/graphify library/papers --update --no-viz
uv run paperbase graph adopt
```

不要在 Graphify 阶段旁路读取原始 PDF；否则 `adopt` 的来源门会拒绝整批投影并保留旧图。

## 问题 3：`BLOCKED` 论文仍被扫描

`BLOCKED` 论文不应进入增量候选，也不应进入 Graphify corpus。确认：

1. manifest 的状态确实为 `BLOCKED`；
2. `library/papers/.graphifyignore` 有该 Canonical 的精确排除规则；
3. `graphify detect library/papers` 的文件数不包含该论文。

解除阻塞后，应先更新状态与 Canonical/manifest，再删除相应的精确排除规则。

## 问题 4：Registry 与文件系统不一致

```powershell
uv run paperbase status
uv run paperbase sync
uv run paperbase doctor
```

`sync` 负责从 Canonical 与 manifest 重建 Registry 投影。真实论文、Registry、`graph/` 和 `graphify-out/` 都是本地数据，不应加入 Git。

## `graphify-out` 的正确处理

`library/papers/graphify-out/` 是正常的 Graphify 输出和缓存目录。增量更新依赖其中的 manifest、graph 和 cache；不要把“目录存在”当作故障原因，也不要在每次运行前删除。只有确认需要全量重建且已接受成本时，才使用 Graphify/PaperBase 提供的强制重建流程。

## 相关文档

- [知识图谱更新策略](../graph-update-strategy.md)
- [Graphify 集成指南](../guides/graphify-integration-guide.md)
- [安装指南](../installation.md)
