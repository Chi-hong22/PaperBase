# PaperBase 功能缺口与改进建议

**日期**: 2026-07-08  
**发现者**: 实际使用过程中的用户反馈

---

## 发现的功能缺口

### 问题 4: 缺少独立的实体提取命令

**问题描述**:
- 实体提取只在 `ingest` 时触发（需要 `auto_extract_on_ingest: true`）
- 对于已摄入但未提取实体的论文，没有官方命令重新提取
- 无法对历史论文批量补充实体

**影响场景**:
1. 用户在 LLM 配置完成**之前**已经摄入了论文
2. 用户想切换 LLM 模型重新提取实体
3. 用户想对历史论文补充实体数据
4. 实体提取失败后需要重试

**现有变通方法**:
- 手动编写脚本调用 `EntityManager.auto_extract_entities()`（不推荐）
- 删除论文重新摄入（会丢失其他数据）

---

## 解决方案

### 新增命令: `paperbase extract`

**设计目标**:
- 提供独立的实体提取入口
- 支持单篇论文和批量提取
- 智能跳过已有实体（可用 `--force` 覆盖）
- 提供 JSON 输出用于自动化

**命令接口**:

```bash
# 提取单篇论文
paperbase extract <paper_id>

# 提取所有未提取的论文
paperbase extract --all

# 强制重新提取所有论文（覆盖已有实体）
paperbase extract --all --force

# JSON 输出（用于脚本）
paperbase extract <paper_id> --output-json
```

**实现文件**: `src/paperbase/cli/commands/extract.py`

---

## 功能特性

### 1. 智能过滤

**默认行为** (不使用 `--force`):
- 检查 `paper.md` 的 `entities` 字段
- 跳过已有实体的论文
- 只处理空实体或缺失实体的论文

**强制模式** (使用 `--force`):
- 重新提取所有论文
- 覆盖现有实体

### 2. 批量处理

使用 `rich.Progress` 显示进度：
```
批量提取实体: 4 篇论文
LLM 模型: mimo-v2.5

  ✓ Bathymetric Particle Filter SLAM... (12 个实体)
  ✓ MINS: Tightly coupled MultiBeam... (14 个实体)
  ✓ The state of the art in key technologies... (5 个实体)
  ✓ A review of AUV-based bathymetric SLAM... (10 个实体)

✓ 批量提取完成
  成功: 4 篇
  失败: 0 篇
```

### 3. JSON 输出

用于自动化脚本：

```json
{
  "success": true,
  "total": 4,
  "success_count": 4,
  "failed_count": 0,
  "results": [
    {
      "paper_id": "doi:10.1109/access.2021.3088541",
      "success": true,
      "entities": {
        "methods": [
          {"name": "Bathymetric Particle Filter SLAM", "type": "localization"}
        ],
        "domains": [...]
      }
    }
  ]
}
```

### 4. 错误处理

- LLM 未启用 → 明确提示配置步骤
- 论文不存在 → 清晰的错误信息
- 提取失败 → 记录错误但继续处理其他论文

---

## 命令对比

### 现有命令的局限

#### `paperbase ingest`
- **用途**: 摄入新论文
- **实体提取**: 可选（`auto_extract_on_ingest`）
- **局限**: 无法对已摄入论文补充实体

#### `paperbase update`
- **用途**: 手动更新实体
- **输入**: 需要用户提供 JSON 字符串
- **局限**: 
  - 不调用 LLM，需要手动编写 JSON
  - 适合外部工具集成，不适合普通用户

### 新命令的优势

#### `paperbase extract`
- **用途**: 专门的实体提取
- **自动化**: 自动调用 LLM
- **灵活性**: 单篇/批量，跳过/强制
- **用户友好**: 无需手动编写 JSON

---

## 使用场景

### 场景 1: 补充历史论文实体

```bash
# 用户在配置 LLM 前已摄入 100 篇论文
# 现在想补充实体

paperbase extract --all
```

**结果**: 只提取没有实体的论文，不影响已有数据。

---

### 场景 2: 切换 LLM 模型重新提取

```bash
# 用户从 gpt-4o-mini 切换到 gpt-4o
# 想获得更准确的实体

paperbase extract --all --force
```

**结果**: 强制重新提取所有论文的实体。

---

### 场景 3: 单篇论文提取失败后重试

```bash
# 提取时网络中断，需要重试

paperbase extract doi:10.1109/access.2021.3088541 --force
```

**结果**: 重新提取指定论文。

---

### 场景 4: 自动化脚本集成

```bash
# CI/CD 脚本自动提取实体

paperbase extract --all --output-json > results.json

# 检查结果
jq '.success_count' results.json
```

**结果**: 获取结构化输出用于进一步处理。

---

## 工作流改进

### 修复前的工作流

```
用户摄入论文 → 发现未提取实体 → ❌ 没有解决方案
                                → ⚠️ 编写脚本调用内部 API
                                → ⚠️ 删除论文重新摄入
```

### 修复后的工作流

```
用户摄入论文 → 发现未提取实体 → ✅ paperbase extract --all
                                → ✅ 简单、安全、官方支持
```

---

## 实现细节

### 依赖的核心 API

```python
from paperbase.core.entity_manager import EntityManager

entity_manager = EntityManager(base_dir=base_dir)

# 检查 LLM 是否启用
if entity_manager.llm_client.enabled:
    # 提取单篇论文实体
    entities = entity_manager.auto_extract_entities(paper_id, storage_id)
```

**关键**: 复用了现有的 `EntityManager.auto_extract_entities()`，保持一致性。

---

### 智能过滤逻辑

```python
# 检查论文是否已有实体
with open(paper_md_path, "r", encoding="utf-8") as f:
    content = f.read()

# 简单但有效的检查
if 'entities:' in content and '- name:' in content:
    # 已有实体，跳过（除非 --force）
    pass
```

**改进空间**: 可以解析 YAML frontmatter 做更精确的检查。

---

## 测试验证

### 测试 1: 检测已有实体

```bash
$ paperbase extract --all
所有论文已有实体
提示: 使用 --force 强制重新提取
```

✅ 通过：智能跳过已提取的论文

---

### 测试 2: 命令帮助

```bash
$ paperbase extract --help
Usage: paperbase extract [OPTIONS] [PAPER_ID]

  提取论文实体（使用 LLM）
  
  用法:
    paperbase extract <paper_id>           提取单篇论文
    paperbase extract --all                提取所有未提取的论文
    paperbase extract --all --force        强制重新提取所有论文

Options:
  --all          提取所有论文的实体（覆盖已有实体）
  --force        强制重新提取（即使已有实体）
  --output-json  以 JSON 格式输出结果
  --help         Show this message and exit.
```

✅ 通过：帮助信息清晰

---

### 测试 3: 集成到主命令

```bash
$ paperbase --help
Commands:
  ...
  extract  提取论文实体（使用 LLM）
  ...
```

✅ 通过：命令已注册

---

## 后续改进建议

### 1. 增量提取模式

```bash
paperbase extract --incremental
```

**行为**: 
- 只提取内容发生变化的论文
- 通过比对 `canonical_content_sha256` 判断

---

### 2. 批量提取时的并发控制

**当前**: 串行提取（避免 API 限流）

**改进**: 
```bash
paperbase extract --all --concurrency 3
```

**行为**: 同时处理 3 篇论文（需注意 API rate limit）

---

### 3. 提取结果缓存

**问题**: 同一篇论文多次提取会重复调用 LLM

**改进**:
- 记录提取时的 `content_sha256`
- 内容未变化时使用缓存结果

**数据结构** (在 manifest.json):
```json
{
  "entities_cache": {
    "content_sha256": "abc123...",
    "extracted_at": "2026-07-08T19:30:00Z",
    "model": "mimo-v2.5",
    "entities": {...}
  }
}
```

---

### 4. 提取质量评分

**目标**: 评估提取结果的置信度

**实现**:
- 记录 LLM 输出的 token 使用量
- 检查实体数量是否合理（如太少可能提取失败）
- 提供 `--verify` 选项重新检查低质量提取

---

## 文档更新

### 需要更新的文档

1. **README.md**
   - 添加 `extract` 命令到快速上手
   - 更新"常见任务"示例

2. **docs/cli-reference.md**
   - 添加 `extract` 命令完整文档
   - 包含所有选项和示例

3. **docs/workflows.md**
   - 添加"补充历史论文实体"工作流
   - 添加"批量重新提取"工作流

---

## 总结

### 问题本质

这是一个**工作流完整性问题**：
- 项目有内部 API (`EntityManager.auto_extract_entities`)
- 但缺少暴露给用户的命令行接口
- 导致用户只能通过编写脚本调用内部 API

### 解决方案本质

**补全 CLI 接口**:
- 将内部 API 通过命令行暴露
- 添加用户友好的选项和提示
- 保持与现有命令的一致性

### 设计原则

1. **复用而非重写**: 使用现有 `EntityManager` API
2. **渐进式增强**: 默认智能跳过，`--force` 强制覆盖
3. **清晰的反馈**: 进度条、成功/失败统计、错误提示
4. **自动化友好**: 提供 `--output-json` 用于脚本

---

## 相关 Issue

建议为此功能创建 Issue 跟踪：

**标题**: Add `paperbase extract` command for entity extraction

**标签**: enhancement, cli, user-experience

**优先级**: High（影响用户工作流的核心功能）
