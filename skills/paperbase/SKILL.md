# PaperBase Skill

**定位**: 人类通过 AI Agent 全能力管理学术论文知识库的技能包

让 AI Agent 成为你的学术知识库管家，用自然语言完成论文摄入、组织、检索、管理的全流程操作。

---

## 核心能力

### 🎯 为什么需要这个 Skill

**传统方式**：
```bash
# 人类需要记忆命令
uv run paperbase ingest "doi:10.1234/abc"
uv run paperbase graph update --incremental
uv run paperbase search "transformer"
```

**使用 Skill**：
```
人类: "帮我摄入这篇论文 10.1234/abc"
Agent: [自动识别 DOI → 执行摄入 → 更新图谱 → 报告结果]

人类: "找出所有关于 SLAM 的论文"
Agent: [智能路由 → 语义查询 → 格式化结果]

人类: "检查知识库状态"
Agent: [综合诊断 → 呈现健康报告]
```

---

## 能力地图

### 1️⃣ 知识摄入能力

**场景**: 将学术论文转化为结构化知识

**能力**：
- ✅ 智能识别论文来源（DOI、arXiv、PMID、URL、PDF）
- ✅ 自动提取元数据（标题、作者、年份、摘要）
- ✅ 批量摄入策略（延迟图谱更新，提升效率）
- ✅ 状态追踪（摄入进度、失败重试）

**典型对话**：
```
人类: "摄入这些论文：10.1038/nature, arxiv:1706.03762, paper.pdf"
Agent: 
  1. 识别 3 个来源（2个在线 + 1个本地）
  2. 执行摄入，显示进度
  3. 报告成功/失败状态
  4. 询问是否立即更新图谱

人类: "批量摄入 papers.txt 中的所有论文"
Agent:
  1. 读取文件，识别 50 篇论文
  2. 使用 --no-graph 快速摄入
  3. 全部完成后统一更新图谱
  4. 报告最终统计（成功 48，失败 2）
```

---

### 2️⃣ 知识组织能力

**场景**: 构建论文之间的关联网络

**能力**：
- ✅ 自动构建知识图谱（基于内容语义）
- ✅ 增量更新（只处理变更的论文）
- ✅ 状态推进（NORMALIZED → READY）
- ✅ 一致性保障（manifest ↔ registry 同步）

**典型对话**：
```
人类: "更新知识图谱"
Agent:
  1. 检测变更论文（3 篇新增，1 篇修改）
  2. 使用 --incremental 模式
  3. 调用 graphify 构建关联
  4. 更新状态到 READY
  5. 报告图谱统计（节点 +5，边 +12）

人类: "重建整个图谱"
Agent:
  1. 警告：这是全量重建，耗时较长
  2. 确认后使用 --force 模式
  3. 显示进度（已处理 45/100）
  4. 完成后报告最终状态
```

---

### 3️⃣ 知识检索能力

**场景**: 从知识库中找到需要的论文

**能力**：
- ✅ 双轨查询系统
  - Registry 轨道：结构化精确查询（doi, state, year, author）
  - Graphify 轨道：语义关联查询（概念、主题、关系）
- ✅ 智能路由（自动识别查询类型）
- ✅ 全文检索（Boolean 运算符）
- ✅ 结果聚合与格式化

**典型对话**：
```
# 结构化查询（自动路由到 Registry）
人类: "列出所有已就绪的论文"
Agent: [查询 state:ready] → 返回 12 篇论文列表

人类: "2024 年的论文有哪些"
Agent: [查询 year:2024] → 返回 5 篇论文

人类: "作者包含 Zhang 的论文"
Agent: [查询 author:Zhang] → 返回 8 篇论文

# 语义查询（自动路由到 Graphify）
人类: "找出关于 SLAM 的论文"
Agent: [语义查询] → 返回 15 篇相关论文及关联路径

人类: "深度学习和计算机视觉的交叉研究"
Agent: [图谱推理] → 返回概念交集的论文

# 全文检索
人类: "搜索提到 transformer 和 attention 的论文"
Agent: [全文检索 "transformer AND attention"] → 返回 7 篇论文
```

---

### 4️⃣ 知识管理能力

**场景**: 维护知识库健康状态

**能力**：
- ✅ 环境诊断（Python、uv、graphify、SQLite）
- ✅ 配置检查（LLM、路径、权限）
- ✅ 状态监控（论文数量、图谱统计、磁盘空间）
- ✅ 数据清理（删除论文、重建索引）

**典型对话**：
```
人类: "检查知识库健康状态"
Agent:
  ✅ Python 3.11.5
  ✅ uv 0.5.0
  ✅ graphify 已安装
  ✅ SQLite FTS5 支持
  ✅ 12 篇论文（10 ready, 2 normalized）
  ✅ 图谱文件 3 个
  ℹ️  建议：2 篇论文待更新图谱

人类: "显示 LLM 配置"
Agent:
  配置文件: config/paperbase.yaml
  LLM 状态: 已启用
  Base URL: https://api.openai.com/v1
  Model: gpt-4o-mini
  API Key: sk-xxxxx...xxxx (已脱敏)

人类: "删除这篇论文 doi:10.1234/abc"
Agent:
  ⚠️  警告：此操作不可逆
  1. 删除 paper.md
  2. 删除 source PDF
  3. 删除 registry 记录
  4. 需要手动更新图谱
  确认删除? (y/n)
```

---

## 智能路由规则

Agent 自动识别用户意图并路由到合适的执行路径：

### 结构化查询 → Registry

**触发模式**：
- `doi:10.1234/abc`
- `state:ready`, `state:normalized`
- `year:2024`
- `author:Zhang`
- `list`, `show all`

**特点**：
- 精确匹配
- 快速响应
- 适合状态管理和筛选

### 语义查询 → Graphify

**触发模式**：
- 自然语言描述（"SLAM 相关论文"）
- 概念关联（"深度学习和计算机视觉"）
- 主题探索（"水下导航技术"）

**特点**：
- 语义理解
- 关系推理
- 适合探索式检索

### 全文检索 → Search

**触发模式**：
- 显式搜索关键词（"搜索 transformer"）
- Boolean 运算符（"A AND B", "A OR B"）

**特点**：
- 内容匹配
- 布尔逻辑
- 适合精确内容查找

---

## 工作流示例

### 工作流 1: 新论文摄入

```
人类: "我刚下载了一篇论文 paper.pdf，帮我加入知识库"

Agent:
  步骤 1: 识别输入
    ✓ 本地 PDF 文件
  
  步骤 2: 提取元数据
    ✓ 标题: "Attention Is All You Need"
    ✓ 作者: Vaswani et al.
    ✓ 年份: 2017
  
  步骤 3: 生成规范化文档
    ✓ 创建 paper.md
    ✓ SHA256: 6b77f95d...
    ✓ 状态: NORMALIZED
  
  步骤 4: 更新知识图谱
    ✓ 构建论文关联
    ✓ 状态推进到 READY
  
  完成! 论文已加入知识库
  Paper ID: doi:10.48550/arxiv.1706.03762
  存储路径: library/papers/p_a7f3b2c1/
```

---

### 工作流 2: 批量研究

```
人类: "我在研究 SLAM 技术，帮我找到相关论文并总结"

Agent:
  步骤 1: 语义查询
    [Graphify 查询 "SLAM"] 
    ✓ 找到 15 篇论文
  
  步骤 2: 结果聚合
    核心论文（5篇）:
    1. "Bathymetric Particle Filter SLAM" (2021)
    2. "A review of AUV-based bathymetric SLAM" (2025)
    3. ...
    
    相关主题:
    - 水下导航 (8篇)
    - 粒子滤波 (6篇)
    - 地图构建 (10篇)
  
  步骤 3: 关系可视化
    [生成引用关系图]
    论文 A → 引用 → 论文 B
    论文 B → 相关 → 论文 C
  
  是否需要我深入阅读某篇论文?
```

---

### 工作流 3: 知识库维护

```
人类: "知识库好像有点问题，帮我全面检查一下"

Agent:
  步骤 1: 环境诊断
    ✅ Python 版本正常
    ✅ uv 已安装
    ⚠️  graphify 未找到
    ✅ SQLite FTS5 支持
  
  步骤 2: 数据一致性检查
    ✅ Registry 与 manifest 一致
    ⚠️  发现 2 篇论文状态为 NORMALIZED（未加入图谱）
  
  步骤 3: 建议修复
    问题 1: graphify 未安装
      解决方案: uv tool install graphify
    
    问题 2: 2 篇论文待更新图谱
      解决方案: paperbase graph update --incremental
  
  是否执行修复? (y/n)
```

---

## 安装与配置

### 快速安装

```bash
# Unix/Linux/macOS
cd ~/.claude/skills
git clone <repo-url> paperbase
cd paperbase
./install.sh

# Windows
cd ~/.claude/skills
git clone <repo-url> paperbase
cd paperbase
powershell -ExecutionPolicy Bypass -File install.ps1
```

### 环境变量

```bash
export PAPERBASE_LIBRARY="/path/to/PaperBase"
export PAPERBASE_LLM_BASE_URL="https://api.openai.com/v1"
export PAPERBASE_LLM_API_KEY="sk-..."
export PAPERBASE_LLM_MODEL="gpt-4o-mini"
```

### 配置文件

`config/paperbase.yaml`:
```yaml
llm:
  base_url: ${PAPERBASE_LLM_BASE_URL}
  api_key: ${PAPERBASE_LLM_API_KEY}
  model: ${PAPERBASE_LLM_MODEL}

graph:
  auto_update: on_ingest
  advanced:
    mode: incremental
```

---

## 技术实现

### 包装器脚本

Agent 通过包装器自动检测库位置：

```bash
# Unix
paperbase-wrapper.sh <command> <args>

# Windows
paperbase-wrapper.ps1 <command> <args>
```

**功能**：
- 自动检测 PaperBase 库路径
- 记忆库位置（workspaces.json）
- 验证环境依赖
- 执行 CLI 命令

### 查询路由器

`query_router.py` 提供智能查询路由：

```python
def paperbase_query(query: str, base_dir: Path) -> str:
    """智能路由查询"""
    if is_structured_query(query):
        return query_registry(query, base_dir)
    else:
        return query_graph(query, base_dir)
```

---

## 依赖

**必需**：
- Python 3.11+
- uv (包管理器)
- PaperBase CLI

**可选**：
- graphify (语义图谱，推荐安装)
- LLM API (用于 graphify 语义理解)

---

## 与 CLI 的关系

| 维度 | /paperbase skill | paperbase CLI |
|------|------------------|---------------|
| **使用者** | AI Agent 代替人类 | 人类直接使用 |
| **交互方式** | 自然语言 | 显式命令 + 参数 |
| **智能程度** | 自动路由、意图理解 | 手动指定子命令 |
| **适用场景** | 对话式交互、复杂流程 | 脚本自动化、精确控制 |

**推荐**：
- 日常使用 → `/paperbase` skill（让 Agent 帮你）
- 脚本自动化 → `paperbase` CLI（精确控制）

---

## 设计理念

### 第一性原理

1. **唯一真相源**: paper.md 是所有数据的源头
2. **可重建投影**: registry 和 graph 可从 paper.md 重建
3. **幂等状态机**: 所有操作可重复执行
4. **双轨查询**: 结构化（Registry）+ 语义（Graphify）

### 用户体验

- **自然语言优先**: 用户用自然语言表达意图
- **智能推断**: Agent 自动识别查询类型
- **容错处理**: 遇到错误时给出解决建议
- **反馈清晰**: 操作步骤和结果可视化

---

## 相关文档

- [README.md](README.md) - 安装指南
- [../../AGENTS.md](../../AGENTS.md) - Agent 工作指南
- [../../CLAUDE.md](../../CLAUDE.md) - Claude 特定指令
- [../../README.md](../../README.md) - PaperBase 项目文档

---

## 版本

**当前版本**: v1.0  
**更新日期**: 2026-07-09  
**兼容性**: PaperBase 架构重构后版本（NORMALIZED → READY 简化状态机）
