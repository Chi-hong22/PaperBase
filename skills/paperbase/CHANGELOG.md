# PaperBase Skill - 更新日志

## [2026-07-09-v2] - 查询系统全面优化

### ✨ 新增功能

#### 1. query topic --include-refs（引用文献扩展）
- **新增选项**：`--include-refs` 扩展查询范围到引用文献
- 默认只返回本地论文（向后兼容）
- 启用后同时显示论文引用的外部文献
- 分离显示本地论文和引用文献

**示例：**
```bash
paperbase query topic "attention"                # 仅本地论文
paperbase query topic "attention" --include-refs # 包含引用文献
# 输出：本地论文: 1 篇, 引用文献: 1 篇
```

#### 2. query topic 分词匹配
- **改进匹配逻辑**：支持多词查询（如 "deep learning"）
- 单词查询：完整子串匹配
- 多词查询：任意词匹配即返回
- 大小写不敏感

**提升效果：**
- "deep learning" 从 0 篇 → 1 篇
- "transformer" 从 0 篇 → 2 篇

### 🐛 Bug 修复（P0 - 严重问题）

#### 1. query topic 覆盖率仅 62.5%
- **问题**：正则表达式只匹配 `p_xxx` 和 `p_xxx_paper`
- **遗漏**：自定义后缀节点（如 `p_xxx_vit_paper`）
- **修复**：改用前缀检查 `node_id.startswith("p_")`（更健壮）
- **结果**：覆盖率提升至 100%（8/8 篇论文）

#### 2. query topic 结果重复
- **问题**：多个节点（如 `p_xxx_paper` 和 `p_xxx_vit_paper`）映射到同一 storage_id
- **修复**：在 CLI 层添加 storage_id 去重逻辑
- **结果**：每篇论文只显示一次

#### 3. query related 返回空结果（P1）
- **问题**：CLI 使用 storage_id 查询，但图谱节点有 `_paper` 后缀
- **修复**：在图谱中查找匹配的节点 ID（支持后缀变体）
- **增强**：引用文献从图谱提取标题显示，而非 N/A

**验证：**
```bash
paperbase query related "fallback:69e64477ae777598"  # 2 篇相关 ✓
paperbase query related "fallback:c23839e43de0a596"  # 3 篇相关 ✓
```

#### 4. 新摄入论文未自动索引
- **问题**：摄入流程缺少索引更新调用
- **修复**：在 `_ingest_online`、`_ingest_local_pdf`、`_ingest_batch` 添加自动索引
- **结果**：新论文摄入后立即可搜索

#### 5. 节点格式兼容性
- **问题**：图谱节点格式从 `p_xxx` 变为 `p_xxx_paper`
- **修复**：正则改为 `^p_[0-9a-f]{12}(_paper)?$` 兼容两种格式
- **增强**：映射时自动去除后缀提取 storage_id

### 🔧 技术改进

#### 核心模块优化
- `graph_query.py`：
  - 前缀检查代替脆弱的正则匹配
  - 添加分词逻辑支持多词查询
  - 支持 `include_refs` 参数

- `query.py`：
  - 节点 ID 映射逻辑（处理后缀变体）
  - storage_id 去重机制
  - 引用文献标题提取和显示
  - 本地论文与引用文献分离显示

- `ingest.py`：
  - 3 个摄入路径全部集成自动索引

### 📊 修复前后对比

| 功能 | 修复前 | 修复后 | 改进 |
|------|--------|--------|------|
| **query topic 覆盖率** | 62.5% (5/8) | 100% (8/8) | +37.5% |
| **query topic "deep learning"** | 0 篇 | 1 篇 | 从不可用 → 可用 |
| **query topic 重复** | 有重复 | 已去重 | ✓ |
| **query related** | 返回空 | 正常工作 | 从不可用 → 可用 |
| **新论文索引** | 手动 | 自动 | 流程简化 |
| **引用文献显示** | N/A | 显示标题 | 信息完整 |

### 🎯 验证结果

#### query topic 测试
```bash
paperbase query topic "numpy"        # 1 篇（NumPy）✓
paperbase query topic "transformer"  # 2 篇（BERT, ViT）✓
paperbase query topic "protein"      # 1 篇（AlphaFold）✓
paperbase query topic "attention" --include-refs  # 1 本地 + 1 引用 ✓
```

#### query related 测试
```bash
paperbase query related "fallback:69e64477ae777598"          # 2 篇 ✓
paperbase query related "fallback:e32543f9588bc9f3" --depth 2 # 2 篇 ✓
paperbase query related "fallback:c23839e43de0a596"          # 3 篇 ✓
```

### 📈 最新数据统计

| 指标 | 数值 |
|------|------|
| 论文总数 | 8 篇 |
| query topic 覆盖率 | 100% |
| 全文检索覆盖率 | 100% (8/8) |
| 图谱节点 | 29 个 |
| 图谱 hyperedges | 4 条 |

### 📦 提交记录

```
5dcd007 - fix(query): 修复 related 查询节点匹配问题
a2cca51 - fix(query): 提升覆盖率至100%并修复重复问题
0426536 - fix(query): 支持新旧两种节点格式
fda002c - feat(query): 支持 --include-refs 扩展查询到引用文献
7301acf - fix(query): 精确过滤非标准论文节点 + 自动索引
```

### 🎯 升级指南

**验证新功能：**
```bash
# 1. 测试覆盖率提升
paperbase query topic "numpy"         # 应能找到 NumPy 论文

# 2. 测试引用扩展
paperbase query topic "attention" --include-refs

# 3. 测试关联查询修复
paperbase query related "fallback:69e64477ae777598"

# 4. 重建图谱（解决孤立节点）
paperbase graph update

# 5. 验证自动索引
paperbase ingest "doi:10.xxxx/xxxx"  # 新论文应立即可搜索
```

---

## [2026-07-09] - 重大功能增强与修复

### ✨ 新增功能

#### 1. 自动文本分块
- **摄入时自动生成** `chunks.jsonl`
- 支持全文检索索引构建
- 按段落智能分块（最大 2048 字符）
- 智能断句（句号、问号、感叹号）

**影响：**
- `paperbase index` 现在可以找到 chunks 文件
- `paperbase search` 全文检索功能可用

#### 2. query 命令支持 graphify 0.9.10
- **适配 hyperedges 格式** - graphify 新版本使用超边
- 自动转换 hyperedges → edges（完全图）
- `query related` 和 `query topic` 恢复正常

**验证：**
```bash
paperbase query related "fallback:78c552c752e0e59b"  # 找到相关论文 ✓
paperbase query topic "transformer"                   # 找到 2 篇论文 ✓
```

#### 3. status 命令增强
- **新增过滤参数**：`--year` 和 `--state`
- 支持组合过滤

**示例：**
```bash
paperbase status --year 2021              # 2021 年的论文
paperbase status --state ready            # 已就绪的论文
paperbase status --year 2021 --state ready # 组合过滤
```

#### 4. remove 命令自动化
- **新增参数**：`--yes` / `-y` 和 `--force` / `-f`
- 支持非交互式删除
- 适合脚本和后台自动化

**示例：**
```bash
paperbase remove <paper_id> --yes    # 自动确认删除
paperbase remove <paper_id> -y       # 短参数
```

#### 5. 批量补生成 chunks 脚本
- **新增脚本**：`scripts/regenerate_chunks.py`
- 为现有论文批量生成 chunks.jsonl
- 支持单篇或全部论文
- 自动跳过已有 chunks（`--force` 覆盖）

**用法：**
```bash
python scripts/regenerate_chunks.py              # 全部论文
python scripts/regenerate_chunks.py --paper-id <id>  # 单篇
python scripts/regenerate_chunks.py --force       # 强制覆盖
```

### 🐛 Bug 修复

#### 1. 扁平化结构统计错误
- **修复 doctor 命令**：`glob("p_*")` 重复计数文件+目录
- 显示 6 篇 → 正确显示 6 篇

#### 2. query related 命令不工作
- **问题**：使用 paper_id 但图谱存储 storage_id
- **修复**：添加 paper_id → storage_id 映射转换
- **验证**：正确显示相关论文及元数据

#### 3. query topic 命令不工作
- **问题 A**：字段名错误（`type` → `file_type`）
- **问题 B**：查询逻辑错误（不存在的 `attributes.topics`）
- **修复**：在 `label` 和 `norm_label` 中搜索关键词
- **验证**：`query topic "transformer"` 找到 2 篇论文

#### 4. manifest path 引用错误
- **修复相对路径**：`./paper.md` → `../{storage_id}.md`
- 适配扁平化结构（paper.md 与目录同级）

#### 5. 文档与实现不一致
- 移除不存在的 `list` 命令引用（7 处）
- 更新所有路径示例为扁平化结构
- 修复 troubleshooting 文档中的命令示例

### 📚 文档更新

#### 内化外部依赖文档
- **paper-fetch 安装指南** - 从外部链接改为内嵌完整说明
- **graphify 安装指南** - 同上
- **集成故障排查** - 更新为最新实现

#### 结构说明更新
- 标注当前使用**扁平化结构**（`p_xxx.md` + `p_xxx/`）
- 说明优势：graphify 批量扫描效率更高
- 更新所有示例路径

### 🔧 技术改进

#### 核心模块
- `graph_query.py` - 支持 hyperedges 自动转换 + paper_id 映射
- `online_ingest.py` - 集成 chunker
- `ingest.py` - 同上集成
- `status.py` - 添加过滤参数
- `remove.py` - 添加自动化参数
- `doctor.py` - 修复论文计数
- `query.py` - 添加 paper_id ↔ storage_id 映射

#### 测试覆盖
- `test_online_ingest.py` - 更新路径为扁平化结构
- 所有单元测试通过 ✓

### 📊 性能影响

| 功能 | 之前 | 现在 | 改进 |
|------|------|------|------|
| 论文统计 | 错误（重复计数） | 准确 | 100% |
| query related | 不可用 | 正常工作 | 从 0 → 可用 |
| query topic | 不可用 | 正常工作 | 从 0 → 可用 |
| 全文检索 | 部分论文 | 全部论文 | 覆盖率 100% |
| 批量删除 | 需交互 | 自动化 | 流程简化 |

### 📈 数据统计（验证结果）

| 指标 | 数值 |
|------|------|
| 论文总数 | 6 篇 |
| chunks 文件 | 6 个（全覆盖） |
| chunks 总大小 | 354.89 KB |
| 文本块总数 | 595 个 |
| 图谱节点 | 44 个 |
| 图谱边 | 49 条 |

### ⚠️ 破坏性变更

无破坏性变更。所有修改向后兼容。

### 🎯 升级指南

**从旧版本升级：**

1. **无需手动操作** - 新摄入的论文自动支持所有新功能

2. **现有论文补充 chunks**：
   ```bash
   # 使用补生成脚本
   python scripts/regenerate_chunks.py
   
   # 重建搜索索引
   paperbase index
   ```

3. **验证升级**：
   ```bash
   paperbase doctor                    # 检查论文数量正确
   paperbase status --year 2021        # 测试过滤功能
   paperbase query topic "transformer" # 测试图谱查询
   paperbase search "attention"        # 测试全文检索
   ```

### 📦 提交记录

```
2a09cf6 - fix(query): 修复 related 和 topic 命令
0c07c63 - feat(scripts): 添加补生成chunks脚本
dc3ca8a - docs(skill): 同步最新功能到全局 skill
8938bb7 - feat(query): 适配 graphify 0.9.10 hyperedges 格式
991927b - feat(cli): 增强 status 和 remove 命令
840e048 - docs(skill): 更新文档为扁平化结构
0ca027c - fix(flat): 修复扁平化结构导致的 3 个 bug
```

### 🙏 致谢

感谢用户反馈的 bug 报告和功能建议！

---

## 历史版本

### [2026-01-16] - 初始版本
- 基础摄入和图谱功能
- Registry 和状态管理
- 文档框架建立

