# ADR-0003：Graphify 调用统一为本机扫描根约定

Status: accepted
Date: 2026-09-22

## Context

Graphify 以「扫描根（root）」计算来源文件身份：manifest、语义缓存与 graph.json 中记录的来源路径都相对于该 root。旧约定下 Agent 从仓库根调用 `/graphify library/papers …`，与 headless 路径及部分 skill 步骤使用的 `library/papers` 根并存，同一篇 Canonical 会以 `p_xxx.md` 与 `library/papers/p_xxx.md` 两种 `source_file` 进入图谱，触发节点碰撞与增量替换异常；仓库根还残留了游离 `graphify-out/`（现场记录于 TD-GRAPH-001）。

论文库通过 Syncthing 在两台主机间同步，使根身份治理多出一层约束：`library/papers/graphify-out/.graphify_root` 与 `.graphify_python` 记录单机绝对路径与解释器，跨机同步会让另一台主机调用不存在的解释器或误判扫描根。另外经实测，graphify 0.9.10 CLI 并不存在旧文档引用的 `graphify detect` 子命令，识别诊断只能经由 Python API（`graphify.detect.detect`）。

## Decision

1. 所有 Agent 侧 Graphify 调用统一为「先切工作目录到本机 `library/papers`，再运行 `/graphify . --update --no-viz`」；`/graphify query` 同理。不硬编码主机绝对路径，各主机本地解析。
2. headless `paperbase graph update / adopt` 不变：该路径本就以 `library/papers` 为根。
3. `paperbase graph preflight` 增加环境警告：仓库根存在游离 `graphify-out/`，或 `.graphify_root` 为指向异机的**绝对**路径（相对路径或本机路径不告警，避免跨机误报）。仅提示，不阻断。
4. Syncthing `.stignore` 排除本机路径类文件（`.graphify_root`、`.graphify_python`、`cache/stat-index.json`）；`cache/semantic/` 保持同步以复用语义缓存。已同步的旧副本不会自动消失，由各主机下次 Graphify skill 运行重写或一次性手工清理。
5. 诊断命令与仓库脚本随约定校正：文档中的 `graphify detect` 替换为实测有效的 `graphify.detect` Python 探测；`query_router.py` 的 `graphify query` 显式传 `--graph <base_dir>/graph/graph.json`，去除对工作目录下 `graphify-out` 的隐式依赖。
6. 代码级「写图前拒绝根不一致」加固不在本 ADR 范围内，继续由 TD-GRAPH-001 跟踪。

## Consequences

### Positive

- manifest、缓存键与节点身份在两台主机上统一为 `p_xxx.md` 相对形式，增量合并不再产生混合来源。
- 本机路径类文件不再跨机传播，Graphify skill 每台主机调用各自解释器；语义缓存仍跨机复用。
- `preflight` 能在接纳前暴露「游离输出目录」与「异机扫描根标记」两类真实故障。

### Negative

- 调用方需遵守「先切目录、再调用」；错误调用不会立即失败，只在根不一致时留下症状（preflight 与 adopt 来源门可兜底发现）。
- 两台主机各自可能需要一次旧标记清理/重写（历史同步的 `.graphify_root` 副本）。

## Rejected alternatives

- **保留参数化调用（`/graphify library/papers --update --no-viz`）**：调用根（CWD）与参数根可以不同源，正是漂移的温床；单一 CWD 约定让根唯一且两机通用。
- **以仓库根为唯一扫描根**：与 headless 路径不一致，且把 PDF/附件目录带入扫描面；统一 CWD 到 `library/papers` 成本更低。
- **在 skill 或配置中硬编码主机绝对路径**：双主机路径不同，硬编码必然在另一台失败（`.graphify_python` 跨机事故即为实例）。
- **在本次一并实现代码级写前拒绝**：属 TD-GRAPH-001 的独立加固；当前以操作约定 + preflight 早期警告 + 多机同步治理满足需求，避免扩大改动面。
