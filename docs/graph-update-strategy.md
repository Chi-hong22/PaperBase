# 图谱更新策略

## 概述

PaperBase 的知识图谱通过 [Graphify](https://github.com/your/graphify) 生成，支持三种更新策略：

1. **自动更新**（默认）：摄入论文后立即更新图谱
2. **延迟更新**：批量摄入后统一更新图谱
3. **增量更新**：仅更新内容发生变化的论文

## 更新时机说明

### 默认行为：自动更新

单篇摄入时，默认在摄入完成后自动触发图谱更新：

```bash
paperbase ingest paper.pdf
# 自动执行 graph update
```

**适用场景**：
- 偶尔添加 1-2 篇论文
- 需要立即在图谱中查看新论文

### 跳过自动更新：--no-graph

使用 `--no-graph` 参数跳过自动图谱更新：

```bash
paperbase ingest paper.pdf --no-graph
```

**适用场景**：
- 连续摄入多篇论文
- 图谱更新失败但不想阻塞摄入流程
- 手动控制图谱更新时机

### 批量摄入模式：--batch

批量摄入会自动延迟图谱更新，所有论文摄入完成后统一更新：

```bash
# 创建批量文件 papers.txt
cat > papers.txt << EOF
/path/to/paper1.pdf
/path/to/paper2.pdf
/path/to/paper3.pdf
EOF

# 批量摄入（自动延迟图谱更新）
paperbase ingest --batch papers.txt
```

**批量文件格式**：
- 每行一个 PDF 路径（绝对或相对路径）
- 支持 `#` 注释行
- 空行会被忽略

**跳过批量图谱更新**：

```bash
paperbase ingest --batch papers.txt --no-graph
```

### 增量更新：--incremental

仅更新内容发生变化的论文，通过比对 `content_sha256_at_index` 检测变化：

```bash
paperbase graph update --incremental
```

**检测逻辑**：
1. 未图谱化的论文 → 需要更新
2. `canonical_md.sha256` 发生变化 → 需要更新
3. 缺少 `content_sha256_at_index`（旧数据）→ 需要更新

**适用场景**：
- 定期同步图谱
- 修改了部分论文的 frontmatter
- 大型知识库的日常维护

## 性能对比

| 场景 | 论文数 | 全量更新 | 增量更新 |
|------|--------|----------|----------|
| 新增 1 篇 | 100 | ~30s | ~3s |
| 新增 10 篇 | 100 | ~30s | ~8s |
| 修改 1 篇 | 100 | ~30s | ~3s |
| 无变化 | 100 | ~30s | <1s |

> 注：实际性能取决于论文长度和硬件性能。

## 最佳实践

### 日常使用

**单篇摄入**：使用默认行为
```bash
paperbase ingest paper.pdf
```

**批量摄入**：使用 --batch
```bash
paperbase ingest --batch papers.txt
```

### 大规模初始化

摄入大量论文时，分阶段处理：

```bash
# 1. 批量摄入（跳过图谱）
paperbase ingest --batch papers.txt --no-graph

# 2. 统一构建图谱
paperbase graph update
```

### 定期维护

使用增量更新保持图谱同步：

```bash
# 1. 先检查 Canonical Markdown 质量
paperbase graph preflight

# 2. Agent 优先：只从 Canonical Markdown 建图
/graphify library/papers --update --no-viz
paperbase graph adopt

# 手动 headless 备用路径，才读取本地 LLM
paperbase graph update --incremental
```

预检发现 `NEEDS_REVIEW` 时，PaperBase 会在耗时建图前停止并保留旧图；只修复对应论文的摄入/Canonical 内容后重跑，不在 Graphify 阶段直接读取 PDF 或原始 URL。这样可避免 Graphify 扫描整库时把质量不足的论文重新带入图谱，也不会误标为 `READY`。

### 重跑时的耗时与稳定性优化

- **先预检再抽取**：先定位 metadata-only、abstract-only、解析失败和正文过短的论文，避免 Agent 读到一半才发现输入不可用。
- **按论文/分块重试**：语义 Agent 结果先落盘为 chunk，单个 chunk 失败只重试该 chunk；不要重跑整库，也不要让长 JSON 依赖一次聊天响应传回。
- **复用两类缓存**：保留 `library/papers/graphify-out/cache/semantic/`，内容哈希未变化的论文直接复用；只有 Canonical 哈希变化才重新抽取。
- **失败不覆盖旧图**：Graphify 进程失败、来源门失败或健康检查失败时，保留当前 `graph/`；只有通过来源和质量门后才原子替换。
- **审核状态不重复消耗**：`NEEDS_REVIEW` 会记录审核时 Canonical 哈希；内容未修复前，增量更新跳过它，但 `preflight` 仍会持续显示它。
- **阻塞先停再建图**：只要本次变更或已有状态中存在 `NEEDS_REVIEW`，`update`/`adopt` 都不启动或接纳整库 Graphify；修复后一次重跑，避免先耗时再回滚。
- **配置层次分明**：`process_timeout` 控制外层进程，默认不限制；`api_timeout` 只控制单次 LLM 请求，避免把两种时间概念混成固定 300 秒。

### CI/CD 流水线

```bash
# 摄入新论文（跳过图谱）
paperbase ingest new-paper.pdf --no-graph

# 运行测试
pytest tests/

# 通过后更新图谱
paperbase graph update
```

## 内部机制

### 变化检测

每次图谱更新时，PaperBase 会在 `manifest.json` 中记录：

```json
{
  "graph": {
    "indexed": true,
    "updated_at": "2026-07-07T12:00:00Z",
    "content_sha256_at_index": "abc123..."
  }
}
```

增量更新时，比对当前 `canonical_md.sha256` 与 `content_sha256_at_index`，检测内容变化。

### 向后兼容

旧版本数据缺少 `content_sha256_at_index` 字段，增量更新会将其视为需要更新，首次运行后会补齐字段。

### 幂等性保证

- 重复运行 `graph update` 是安全的
- 增量更新检测到无变化时会跳过 graphify
- 全量更新会覆盖现有图谱数据

## 故障排查

### 图谱更新失败

**症状**：摄入成功但图谱更新报错

**排查步骤**：
1. 检查 graphify 是否安装：`uv tool list`
2. 手动运行：`paperbase graph update`
3. 查看日志输出

**解决方案**：
- 使用 `--no-graph` 跳过自动更新
- 修复问题后手动运行 `graph update`

### 增量更新未检测到变化

**症状**：修改了 paper.md 但增量更新跳过

**排查步骤**：
1. 检查 `manifest.json` 中的 `canonical_md.sha256`
2. 检查 `graph.content_sha256_at_index`
3. 确认修改后是否重新生成了 manifest

**解决方案**：
- 使用全量更新：`paperbase graph update`
- 或强制重建：`paperbase graph update --force`

### 批量摄入部分失败

**症状**：批量文件中某些 PDF 摄入失败

**表现**：
- 失败的论文会显示错误信息
- 成功的论文会继续处理
- 最后统计显示成功/失败数量

**解决方案**：
- 检查失败的 PDF 文件
- 修复后重新摄入失败的论文
- 或从批量文件中移除问题文件

## 相关命令

```bash
# 查看图谱状态
paperbase graph status

# 强制重建图谱
paperbase graph update --force

# 增量更新图谱
paperbase graph update --incremental

# 查看论文状态
paperbase status <paper_id>
```

## 参考

- [Canonical Schema](../src/paperbase/schemas/manifest.py)
- [Graph Updater](../src/paperbase/core/graph_updater.py)
- [Graphify Adapter](../src/paperbase/adapters/graphify_adapter.py)
