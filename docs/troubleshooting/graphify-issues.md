# Graphify 故障排查指南

## 推荐诊断顺序

```powershell
uv run paperbase graph preflight
# 在 library/papers 目录下运行；输出应等于可建图 p_*.md 数量
& (Get-Content graphify-out/.graphify_python) -c 'from pathlib import Path; from graphify.detect import detect; print(sum(map(len, detect(Path("."))["files"].values())))'
uv run paperbase graph status
uv run paperbase doctor
```

PaperBase 的 Graphify 输入只应来自 `library/papers/p_*.md`。不要在图谱阶段直接读取 PDF、URL 或 Zotero 附件，也不要因为 Git 忽略了论文文件就强制暂存它们。

## 问题 1：Graphify 未发现 Canonical Markdown

**症状**：在 library/papers 目录下运行下方检测命令输出 0 或明显少于 `p_*.md` 数量，或抽取后图谱为空。

**检查**：

```powershell
Get-ChildItem library/papers -Filter 'p_*.md' -File
Get-Content library/papers/.graphifyignore

# 先切到 library/papers 目录再运行（用 graphify skill 记录的本机解释器统计识别数）：
& (Get-Content graphify-out/.graphify_python) -c 'from pathlib import Path; from graphify.detect import detect; print(sum(map(len, detect(Path("."))["files"].values())))'
```

`.gitignore` 与 `.graphifyignore` 职责不同：前者阻止真实论文进入 Git，后者决定 Graphify 是否扫描本地文件。PaperBase 的 `.graphifyignore` 必须包含 `!p_*.md`；需要阻塞的 Canonical 再用更靠后的精确规则排除。

## 问题 2：`NEEDS_REVIEW` 阻止更新或接纳

**症状**：`preflight` 报告正文不足，`graph update` 或 `graph adopt` 在调用/接纳 Graphify 前停止。

这是质量门的预期行为。修复对应 Canonical 的来源或正文，更新 manifest 哈希后重跑：

```powershell
uv run paperbase graph preflight
# 在本机 library/papers 目录下运行：/graphify . --update --no-viz
uv run paperbase graph adopt
```

不要在 Graphify 阶段旁路读取原始 PDF；否则 `adopt` 的来源门会拒绝整批投影并保留旧图。

## 问题 3：`BLOCKED` 论文仍被扫描

`BLOCKED` 论文不应进入增量候选，也不应进入 Graphify corpus。确认：

1. manifest 的状态确实为 `BLOCKED`；
2. `library/papers/.graphifyignore` 有该 Canonical 的精确排除规则；
3. 用上文的检测命令（在 library/papers 目录下运行）确认输出的文件数不包含该论文。

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

## 问题 5：增量合并出现路径根告警或节点碰撞

**问题编号**：`TD-GRAPH-001`

**症状**：旧图以 `library/papers` 为扫描根，但增量步骤使用仓库根；同一文件同时出现 `p_xxx.md` 与 `library/papers/p_xxx.md` 两种 `source_file`，Graphify 报节点 ID 碰撞或合并后节点异常增长。

**原因**：Graphify 使用相对于 `root` 的来源路径参与文件和节点身份匹配。detect、cache、`build_merge`、`save_manifest` 的根不一致时，增量替换会把同一 Canonical 当成两个来源。节点数量没有下降时，shrink guard 不一定能发现这种错误。

**当前规避（操作级约定，见 `TD-GRAPH-002`）**：

1. 所有增量步骤先切工作目录到本机 `library/papers`，再运行 `/graphify . ...`；各主机路径本地解析，不硬编码绝对路径；
2. Graphify Python 步骤在 `library/papers` 目录执行，确保 manifest 写入正确的 `graphify-out/`；
3. 合并前备份旧 `graph.json`；
4. 接纳前验证来源集合只含活动 `p_*.md`，且不存在 PDF、URL、`p_xxx.md`/`library/papers/p_xxx.md` 混合形式；
5. 出现根不一致时停止接纳、恢复旧图，再用正确根重新合并；
6. `paperbase graph preflight` 会早期警告仓库根游离 `graphify-out/` 或指向异机的 `.graphify_root`；本机路径类文件（`.graphify_root`、`.graphify_python`、`cache/stat-index.json`）已从 Syncthing 同步中排除。

**未来修复**：权威工单为 `.scratch/graphify-scan-root-consistency/issues/01-enforce-scan-root-consistency.md`。代码应在写图前比较持久化扫描根与本次根，不一致时直接失败，并增加对应回归测试。

## 相关文档

- [知识图谱更新策略](../graph-update-strategy.md)
- [Graphify 集成指南](../guides/graphify-integration-guide.md)
- [安装指南](../installation.md)
