# Graphify 故障排查指南

## 常见问题与解决方案

### 问题 1: "graph is empty — extraction produced no nodes"

**症状**:
```bash
uv run paperbase graph update
# 输出: graphify 失败: graph is empty — extraction produced no nodes
```

**根本原因**:
测试或调试过程中在 `library/papers/` 目录下创建了 `graphify-out` 目录，干扰了 Graphify 的扫描逻辑。

**详细说明**:
- Graphify 在扫描目录时会跳过名为 `graphify-out` 的目录（这是它的输出目录）
- 如果在 `library/papers/` 下存在 `graphify-out` 目录，Graphify 可能误判整个 papers 目录已被处理
- 这导致 Graphify 跳过所有论文文件，返回空图谱

**解决方法**:
```bash
# 删除干扰的 graphify-out 目录
rm -rf library/papers/graphify-out

# 重新运行图谱更新
uv run paperbase graph update --force
```

**预防措施**:
1. **不要在 library/papers 目录下手动创建 graphify-out 目录**
2. 测试 Graphify 时使用临时目录，不要在生产数据目录中测试
3. `.gitignore` 已配置忽略 `library/papers/graphify-out/`，但这不影响本地文件系统

**相关 issue**: 发生于 2026-07-10，修改 .gitignore 后进行 Graphify 测试时

---

### 问题 2: Registry 和文件系统不一致

**症状**:
- Registry 显示 13 篇论文
- 本地有 16 个 .md 文件

**原因**:
- 3 篇论文未完成摄入流程，只生成了 .md 文件但未更新 Registry
- 或者论文处于 NORMALIZED 状态（未达到 READY 状态）

**检查方法**:
```bash
# 查看所有状态的论文
uv run paperbase status

# 查看特定状态
uv run paperbase status --state normalized
```

**解决方法**:
```bash
# 重新索引缺失的论文
uv run paperbase sync

# 或手动重新摄入
uv run paperbase ingest <paper_id>
```

---

## 相关文档

- [知识图谱更新策略](../graph-update-strategy.md)
- [LLM 配置问题](./llm-config-issues.md)
- [安装指南](../installation.md)
