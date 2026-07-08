# PaperBase Skill

PaperBase 统一查询接口，智能路由到结构化查询（Registry）或语义查询（Graph）。

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
