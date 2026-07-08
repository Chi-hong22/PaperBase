# PaperBase Skill

PaperBase 统一查询接口，智能路由到结构化查询（Registry）或语义查询（Graph）。

## 与 CLI `query` 命令的区别

| 特性 | `/paperbase` skill | `paperbase query` CLI |
|------|-------------------|----------------------|
| **适用场景** | AI Agent 自然语言交互 | 高级用户参数化控制 |
| **查询方式** | 自动识别查询类型并路由 | 显式指定子命令 (related/topic) |
| **参数控制** | 无参数，智能推断 | 支持 --depth 等参数 |
| **返回格式** | 文本格式（适合 Agent） | Rich Table（适合终端） |

**推荐使用**：
- AI Agent 工作流 → 使用 `/paperbase` skill
- 终端手动查询 → 使用 `paperbase query` CLI

## 用法

```bash
/paperbase <query>
```

## 路由规则

**结构化查询** (Registry):
- `doi:`, `paper_id:` 前缀
- `state:`, `year:`, `author:` 前缀  
- `list`, `show all` 关键词

**语义查询** (Graphify):
- 概念、关系、主题查询
- `path`, `between` 关键词
- `explain`, `about` 关键词

## 示例

```bash
/paperbase doi:10.1038/nature          # Registry 查询
/paperbase state:normalized            # Registry 筛选
/paperbase list all papers             # Registry 列表
/paperbase 强化学习的核心概念          # Graphify 查询
/paperbase path "Transformer" "Attention"  # Graphify 路径查询
```

## 架构

- **Registry**: SQLite 索引，精确匹配、状态筛选、元数据查询
- **Graphify**: 语义图谱，概念关联、路径推理、社区发现
- **智能路由**: 基于查询模式自动选择最合适的查询后端
