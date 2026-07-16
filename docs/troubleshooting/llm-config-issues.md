# LLM 配置问题排查记录

> **历史问题记录（2026-07-08）**：本文用于保留旧版 headless LLM 配置故障的诊断证据，其中命令和模块名可能已失效。当前 Agent 建图优先走 `paperbase graph preflight → /graphify library/papers --update --no-viz → paperbase graph adopt`；当前 headless 配置请以 `docs/installation.md` 和 `paperbase config --help` 为准。

**日期**: 2026-07-08  
**问题**: .env 已配置 LLM API，但实际调用显示未配置

---

## 问题诊断

### 根因分析

发现了 **3 个独立但叠加的问题**：

#### 1. 项目未加载 .env 文件

**现象**:
- `.env` 文件存在且配置正确
- 但环境变量 `PAPERBASE_LLM_*` 在运行时为空

**根因**:
- 项目代码中没有调用 `load_dotenv()`
- Python 不会自动加载 `.env` 文件

**验证**:
```python
import os
print(os.getenv('PAPERBASE_LLM_API_KEY'))  # None
```

---

#### 2. LLM 配置不完整

**现象**:
- `config/paperbase.yaml` 中 `llm.base_url` 或 `llm.model` 未配置

**影响**:
- LLMClient 判断 LLM 未启用，跳过初始化

**配置位置**:
```yaml
llm:
  base_url: ${PAPERBASE_LLM_BASE_URL}  # 必须设置
  model: ${PAPERBASE_LLM_MODEL}        # 必须设置
  api_key: ${PAPERBASE_LLM_API_KEY}
```

---

#### 3. 配置文件路径计算错误（最关键）

**现象**:
- LLMClient 初始化时 `config` 为空或使用默认值
- 即使启用 LLM 并加载 .env，仍然显示 `enabled: False`

**根因**:
```python
# src/paperbase/core/llm_client.py (修复前)
config_path = Path(__file__).parent.parent.parent / "config" / "paperbase.yaml"
```

**路径计算错误**:
- `__file__` = `F:\__PaperBase__\src\paperbase\core\llm_client.py`
- `.parent` × 3 = `F:\__PaperBase__\src`
- 最终路径 = `F:\__PaperBase__\src\config\paperbase.yaml` ❌
- 实际路径 = `F:\__PaperBase__\config\paperbase.yaml` ✓

**后果**:
- 配置文件不存在，触发 fallback 逻辑（第 47 行）
- 返回默认配置 `{"llm": {"enabled": False}}`

---

## 修复方案

### 修复 1: 添加 .env 加载

**文件**: `src/paperbase/cli/main.py`

```python
from dotenv import load_dotenv

# 加载 .env 文件（如果存在）
load_dotenv()
```

**文件**: `src/paperbase/core/llm_client.py`

```python
from dotenv import load_dotenv

# 确保 .env 被加载（幂等操作）
load_dotenv()
```

**说明**: 在两处都加载，确保无论从哪里导入 LLMClient 都能生效。

---

### 修复 2: 完善 LLM 配置

**文件**: `config/paperbase.yaml`

```yaml
llm:
  base_url: ${PAPERBASE_LLM_BASE_URL}
  api_key: ${PAPERBASE_LLM_API_KEY}
  model: ${PAPERBASE_LLM_MODEL}
```

**说明**: LLM 启用状态由 `base_url` 和 `model` 两个字段共同决定，两者都必须配置且非空。

---

### 修复 3: 修正配置路径

**文件**: `src/paperbase/core/llm_client.py`

```python
# 修复前（错误）
config_path = Path(__file__).parent.parent.parent / "config" / "paperbase.yaml"
# → F:\__PaperBase__\src\config\paperbase.yaml ❌

# 修复后（正确）
config_path = Path(__file__).parent.parent.parent.parent / "config" / "paperbase.yaml"
# → F:\__PaperBase__\config\paperbase.yaml ✓
```

**关键变化**: 增加一级 `.parent`（从 3 个变为 4 个）

---

## 验证结果

### 修复后测试

```python
from paperbase.core.llm_client import LLMClient

client = LLMClient()
print(f"LLM 启用: {client.enabled}")
print(f"模型: {client.model}")
print(f"端点: {client.config['llm']['base_url']}")
```

**输出**:
```
LLM 启用: True
模型: mimo-v2.5
端点: https://api.xiaomimimo.com/v1
```

### 实体提取测试

对 4 篇论文进行实体提取：

| Paper ID | 状态 | Methods | Datasets | Domains | Platforms | Constraints |
|----------|------|---------|----------|---------|-----------|-------------|
| doi:10.1109/access.2021.3088541 | ✓ | 4 | 2 | 2 | 1 | 3 |
| doi:10.1016/j.joes.2025.08.010 | ✓ | 10 | 0 | 3 | 1 | 1 |
| doi:10.1016/j.eng.2025.08.002 | ✓ | 0 | 0 | 5 | 0 | 0 |
| doi:10.1016/j.oceaneng.2025.122858 | ✓ | 4 | 0 | 3 | 1 | 1 |

**总计**: 41 个唯一实体节点，82 个对象（节点 + 边）

---

## 问题反思

### 为什么问题难以发现？

1. **多层级故障**
   - 3 个问题叠加，每一个都会导致相同的症状（LLM 未启用）
   - 修复其中一个不会解决问题，必须全部修复

2. **路径问题隐蔽**
   - 文件不存在时返回默认配置，而不是抛出异常
   - 没有明确的日志说明配置文件路径

3. **缺少调试工具**
   - 没有 `paperbase config show` 命令查看当前配置
   - 没有 `paperbase doctor` 检查 LLM 配置状态

### 改进建议

#### 1. 增强错误提示

**当前逻辑**:
```python
if not config_path.exists():
    return {"llm": {"enabled": False}}
```

**建议改进**:
```python
if not config_path.exists():
    logger.warning(f"Config file not found: {config_path}")
    logger.info(f"Using default config (LLM disabled)")
    return {"llm": {"enabled": False}}
```

---

## 配置诊断工具

项目已实现以下配置诊断命令：

### 1. 查看当前配置

```bash
paperbase config show
```

输出示例：
```
配置文件: F:\__PaperBase__\config\paperbase.yaml

LLM 配置:
  enabled: True
  base_url: https://api.xiaomimimo.com/v1
  api_key: sk-xxxxx...xxxx
  model: mimo-v2.5
  timeout: 60
  max_input_tokens: 4000

知识图谱配置:
  auto_update: on_entity_change
  mode: incremental
```

### 2. 验证 LLM 配置

```bash
paperbase config show
```

输出示例：
```
✓ 配置文件存在
✓ LLM 已启用
✓ PAPERBASE_LLM_BASE_URL: https://api.xiaomimimo.com/v1
✓ PAPERBASE_LLM_API_KEY: sk-xxxxx...xxxx
✓ PAPERBASE_LLM_MODEL: mimo-v2.5
✓ 初始化成功
✓ 配置检查通过
```

### 3. 显示配置文件路径

```bash
paperbase config path
```

---

## 文档改进

### 需要更新的文档

1. **README.md**
   - 明确说明需要 `python-dotenv` 依赖
   - 说明 `.env` 必须放在项目根目录

2. **docs/configuration.md**
   - 添加配置文件路径说明
   - 添加故障排查流程图

3. **.env.example**
   - 已经完善，无需修改

---

## 相关 Issue

- 配置文件路径计算错误可能影响其他功能
- 建议全局搜索 `Path(__file__).parent` 检查其他路径计算

---

## 总结

这是一个典型的**多层级配置问题**：

1. 环境变量未加载（缺少 `load_dotenv()`）
2. 功能未启用（配置文件中 `enabled: false`）
3. 配置文件路径错误（少一级 `parent`）

**关键教训**:
- 配置系统需要明确的错误提示
- 路径计算应该使用绝对路径或配置项，而不是相对于模块文件
- 需要完善的诊断工具帮助用户排查问题
