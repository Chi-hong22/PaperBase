# Search 命令使用指南

## 概述

`paperbase search` 命令提供基于 SQLite FTS5 的全文检索功能，支持关键词搜索和多维度过滤。

**与 `query` 命令的区别**：

| 特性           | `search`（本文档）                | `query`                           |
| ---------------- | ----------------------------------- | ----------------------------------- |
| **检索目标**   | 查找包含特定关键词的论文          | 发现论文之间的关系和路径          |
| **索引依赖**   | `registry/papers.db`（FTS5 索引） | `graph/graph.json`（知识图谱）    |
| **查询类型**   | 关键词匹配 + 元数据过滤           | 关系查询（引用、相似度）          |
| **典型场景**   | "找到所有提到 transformer 的论文" | "找到与这篇论文引用关系最近的论文" |
| **性能**       | O(log N)，快速                    | O(N)，图遍历较慢                  |
| **过滤维度**   | 状态、年份、特定论文              | 关系深度、相似度阈值              |

## 基本用法

```bash
paperbase search <query> [OPTIONS]
```

## 参数说明

### 必需参数

- `<query>`：搜索关键词，支持布尔运算符（AND、OR、NOT）

### 可选参数

| 参数 | 简写 | 类型 | 默认值 | 说明 |
|------|------|------|--------|------|
| `--limit` | `-n` | int | 10 | 返回结果数量上限 |
| `--paper-id` | | str | - | 限定在指定论文中搜索 |
| `--state` | | str | - | 按论文状态过滤（normalized/ready） |
| `--year` | | int | - | 按发表年份过滤（精确匹配） |
| `--year-min` | | int | - | 按发表年份过滤（最小值） |
| `--year-max` | | int | - | 按发表年份过滤（最大值） |
| `--base-dir` | | path | 当前目录 | 指定 PaperBase 项目路径 |

## 使用示例

### 1. 基本搜索

```bash
# 搜索包含 "transformer" 的论文
paperbase search "transformer"

# 搜索短语（精确匹配）
paperbase search "attention mechanism"

# 限制返回数量
paperbase search "deep learning" --limit 20
paperbase search "neural network" -n 5
```

### 2. 布尔运算符

```bash
# AND: 必须同时包含两个词
paperbase search "transformer AND attention"

# OR: 包含任一词即可
paperbase search "LSTM OR GRU"

# NOT: 排除特定词
paperbase search "vision NOT transformer"

# 组合使用
paperbase search "(neural network OR deep learning) AND computer vision"
```

### 3. 状态过滤

```bash
# 仅搜索已规范化的论文
paperbase search "SLAM" --state normalized

# 仅搜索已加入知识图谱的论文
paperbase search "reinforcement learning" --state ready
```

**状态说明**：
- `normalized`：论文已摄入并转换为 Canonical Markdown
- `ready`：论文已加入知识图谱，可供语义查询

### 4. 年份过滤

```bash
# 精确年份匹配
paperbase search "attention mechanism" --year 2017

# 年份范围（闭区间）
paperbase search "SLAM" --year-min 2020 --year-max 2024

# 仅指定最小年份（2020 年及以后）
paperbase search "GPT" --year-min 2020

# 仅指定最大年份（2019 年及以前）
paperbase search "LSTM" --year-max 2019
```

**注意**：
- `--year` 与 `--year-min`/`--year-max` 互斥，不能同时使用
- 年份基于论文元数据中的 `published_date` 字段

### 5. 特定论文搜索

```bash
# 在指定论文中搜索关键词
paperbase search "threshold" --paper-id "doi:10.1109/tro.2008.2004520"

# 适用场景：快速定位论文中的特定内容
paperbase search "algorithm" --paper-id "arxiv:1706.03762"
```

**用途**：
- 在已知论文中快速定位特定段落
- 验证论文是否讨论了某个主题
- 提取论文中的特定信息片段

### 6. 组合过滤

```bash
# 状态 + 年份
paperbase search "transformer" --state ready --year-min 2020

# 状态 + 年份范围 + 限制数量
paperbase search "vision" --state ready --year-min 2022 --year-max 2024 --limit 10

# 特定论文 + 限制数量
paperbase search "method" --paper-id "arxiv:2301.07041" --limit 5
```

### 7. 指定项目路径

```bash
# 搜索指定路径的知识库
paperbase search "deep learning" --base-dir /path/to/paperbase

# 或通过环境变量（推荐）
export PAPERBASE_LIBRARY="/path/to/paperbase"
paperbase search "deep learning"
```

## 输出格式

### 成功输出示例

```
找到 3 篇相关论文:

1. Attention Is All You Need
   Paper ID: arxiv:1706.03762
   Authors: Vaswani et al.
   Year: 2017
   Relevance: 0.95

2. BERT: Pre-training of Deep Bidirectional Transformers
   Paper ID: arxiv:1810.04805
   Authors: Devlin et al.
   Year: 2018
   Relevance: 0.87

3. GPT-3: Language Models are Few-Shot Learners
   Paper ID: arxiv:2005.14165
   Authors: Brown et al.
   Year: 2020
   Relevance: 0.82
```

### 空结果输出

```
未找到匹配的论文
```

## 常见问题

### Q1: 搜索不到论文？

**检查清单**：

1. **索引是否存在**
   ```bash
   # 检查索引文件
   ls -lh registry/papers.db
   
   # 重建索引
   paperbase index
   ```

2. **论文是否已摄入**
   ```bash
   # 查看所有论文
   paperbase status
   
   # 检查特定论文
   paperbase status "doi:10.1038/nature"
   ```

3. **关键词是否正确**
   ```bash
   # 尝试更通用的关键词
   paperbase search "transformer"  # ✓
   paperbase search "transformers" # ✗ 可能匹配不到
   ```

### Q2: 过滤结果为空？

**可能原因**：

1. **状态不匹配**
   ```bash
   # 检查论文实际状态
   paperbase status --state normalized
   paperbase status --state ready
   ```

2. **年份超出范围**
   ```bash
   # 检查论文年份分布
   paperbase status | grep "Year:"
   ```

3. **过滤条件过于严格**
   ```bash
   # 逐步放宽条件
   paperbase search "SLAM" --year-min 2020 --year-max 2024
   paperbase search "SLAM" --year-min 2020  # 放宽上限
   paperbase search "SLAM"                   # 移除所有过滤
   ```

### Q3: 搜索速度慢？

**优化建议**：

1. **缩小搜索范围**
   ```bash
   # 使用更具体的关键词
   paperbase search "visual SLAM" --limit 10
   ```

2. **添加过滤条件**
   ```bash
   # 缩小候选集
   paperbase search "deep learning" --year-min 2020 --state ready
   ```

3. **检查索引健康**
   ```bash
   # 重建索引
   paperbase index
   
   # 清理孤立记录
   paperbase sync
   ```

### Q4: 如何搜索多个关键词？

```bash
# 必须同时包含（AND）
paperbase search "transformer AND attention"

# 包含任一即可（OR）
paperbase search "LSTM OR GRU OR RNN"

# 排除特定词（NOT）
paperbase search "neural network NOT CNN"

# 复杂组合
paperbase search "(deep learning OR machine learning) AND vision NOT medical"
```

### Q5: 如何查看论文全文？

```bash
# 搜索定位论文
paperbase search "attention mechanism" --limit 5

# 查看论文 Markdown 文件
cat library/papers/p_<storage_id>.md

# 或使用状态命令获取路径
paperbase status "arxiv:1706.03762"
```

## 最佳实践

### 1. 从宽到窄的搜索策略

```bash
# 第 1 步：宽泛搜索，了解整体结果
paperbase search "transformer" --limit 20

# 第 2 步：添加状态过滤
paperbase search "transformer" --state ready --limit 20

# 第 3 步：添加年份过滤
paperbase search "transformer" --state ready --year-min 2020 --limit 10

# 第 4 步：精炼关键词
paperbase search "vision transformer" --state ready --year-min 2020
```

### 2. 结合 query 命令深度分析

```bash
# 第 1 步：用 search 找到相关论文
paperbase search "attention mechanism" --year 2017

# 输出：arxiv:1706.03762 (Attention Is All You Need)

# 第 2 步：用 query 查看引用关系
paperbase query related "arxiv:1706.03762" --depth 2

# 第 3 步：用 query 找到相似论文
paperbase query similar "arxiv:1706.03762" --limit 5
```

### 3. 定期维护索引

```bash
# 摄入新论文后，索引会自动更新
paperbase ingest "arxiv:2301.07041"

# 批量摄入后，手动重建索引（可选）
paperbase ingest --batch papers.txt
paperbase index

# 定期清理孤立记录
paperbase sync
```

### 4. 使用环境变量简化命令

```bash
# 设置默认路径
export PAPERBASE_LIBRARY="/path/to/paperbase"

# 之后无需指定 --base-dir
paperbase search "deep learning"
paperbase search "transformer" --state ready
```

## 技术细节

### FTS5 索引内容

搜索索引包含以下字段：

- **标题**（title）：权重最高
- **摘要**（abstract）：权重次之
- **正文**（content）：权重最低
- **作者**（authors）：可搜索，但不影响相关性排序

### 相关性排序算法

FTS5 使用 BM25 算法计算相关性分数：

- **TF（词频）**：关键词在文档中出现的频率
- **IDF（逆文档频率）**：关键词在整个语料库中的稀有程度
- **文档长度归一化**：避免长文档占优

### 性能特征

| 操作 | 时间复杂度 | 说明 |
|------|------------|------|
| 索引构建 | O(N) | N = 论文数量，一次性操作 |
| 关键词搜索 | O(log N) | 基于倒排索引，快速 |
| 状态过滤 | O(1) | 索引字段，直接查询 |
| 年份过滤 | O(1) | 索引字段，直接查询 |
| 特定论文搜索 | O(1) | 主键查询，极快 |

## 相关命令

- `paperbase status`：查看论文状态和元数据
- `paperbase query`：知识图谱关系查询
- `paperbase index`：手动重建搜索索引
- `paperbase sync`：同步索引与文件系统

## 另见

- [docs/graph-update-strategy.md](../graph-update-strategy.md) - 知识图谱更新策略
- [docs/guides/graphify-integration-guide.md](../guides/graphify-integration-guide.md) - Graphify 集成指南
- [AGENTS.md](../../AGENTS.md) - Agent 工作指南
