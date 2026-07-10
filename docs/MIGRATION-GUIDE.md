# 迁移指南 - 高优先级修复

本文档说明本次优化对现有代码的影响。

## 向后兼容性

✅ **所有修改都是向后兼容的**，现有代码无需修改即可继续工作。

## 新增功能

### 1. 统一异常类 (`paperbase.core.exceptions`)

**推荐用法：**

```python
from paperbase.core.exceptions import ValidationError, PaperBaseSystemError, TransientError

# 用户可修复的错误
if not valid_schema:
    raise ValidationError("Invalid paper schema", context={"field": "year"})

# 系统错误
if not db_path.exists():
    raise PaperBaseSystemError("Database not found")

# 临时错误（可重试）
try:
    response = api_call()
except TimeoutError:
    raise TransientError("API timeout, retry recommended")
```

---

### 2. Markdown 工具 (`paperbase.utils.markdown`)

**推荐用法：**

```python
from paperbase.utils.markdown import (
    parse_frontmatter,
    generate_canonical_markdown,
    update_frontmatter_file
)

# 解析
metadata, body = parse_frontmatter(content)

# 生成
canonical_md = generate_canonical_markdown(metadata_dict, body)

# 原子更新
update_frontmatter_file(paper_md_path, {"year": 2025})
```

**已迁移模块：**
- ✅ `entity_graph_builder.py`
- ✅ `ingest.py`

---

## Bug 修复

### 1. 图谱统计不准确

**修复前：** 总是返回 `{"nodes": 0, "edges": 0}`

**修复后：** 返回真实统计，如 `{"nodes": 127, "edges": 384}`

### 2. PDF 资源泄漏

**修复前：** 使用 try-finally，可能在异常时泄漏

**修复后：** 使用上下文管理器，保证资源清理

---

## 测试覆盖

| 模块 | 新增测试 |
|------|---------|
| exceptions | 5 tests |
| markdown utils | 8 tests |
| graphify_adapter | 5 tests |
| pdf_extractor | 2 tests |
| doctor command | 3 tests |

---

## 问题反馈

如有问题，请提交 Issue 并包含：
- PaperBase 版本
- Python 版本
- `paperbase doctor` 输出
- 错误日志
