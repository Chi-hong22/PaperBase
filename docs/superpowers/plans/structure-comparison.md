# 平面结构 vs 立体结构对比分析

## 图谱构建效率

### 立体结构（当前）
```
library/papers/
├── p_1636de654dd3/
│   └── paper.md
├── p_2ddac761b162/
│   └── paper.md
```

**graphify 扫描**:
- 需要明确指定每个目录: `graphify extract p_1/ p_2/ p_3/`
- 扫描复杂度: O(n) - 需要遍历所有论文目录
- 命令行长度: 随论文数量线性增长

**优点**:
- 资源隔离清晰（paper.md + assets + manifest.json 在同一目录）
- 符合"每个论文是一个独立单元"的语义
- 文件组织直观

**缺点**:
- graphify 扫描需要明确指定每个子目录
- 命令行参数随论文数量增长

### 平面结构
```
library/papers/
├── p_1636de654dd3.md   ← 论文内容
├── p_2ddac761b162.md
├── p_1636de654dd3/     ← 元数据和资源
│   ├── manifest.json
│   └── assets/
```

**graphify 扫描**:
- 一次扫描: `graphify extract library/papers/`
- 扫描复杂度: O(1) - 单个命令
- graphify 自动识别所有 .md 文件

**优点**:
- ✓ graphify 扫描效率高（一次命令）
- ✓ 命令行参数固定
- ✓ 对图谱工具友好

**缺点**:
- 资源分离（paper.md 和 manifest.json 不在同一目录）
- 需要维护 `p_xxx.md` ↔ `p_xxx/` 的对应关系

## 性能测试估算

### 论文数量增长影响

| 论文数量 | 立体结构命令长度 | 平面结构命令长度 |
|---------|----------------|----------------|
| 10      | ~200 chars     | 30 chars       |
| 100     | ~2000 chars    | 30 chars       |
| 1000    | ~20000 chars   | 30 chars       |

**命令行长度限制**:
- Windows CMD: 8191 chars
- PowerShell: 32768 chars
- Linux Bash: ~2MB

**风险**: 立体结构在 200+ 论文时可能达到 Windows CMD 限制

### graphify 执行时间

假设单个论文扫描耗时 t:

- **立体结构**: T = n * t + overhead(进程启动)
- **平面结构**: T = n * t

差异不大，主要在命令复杂度而非执行时间。

## 建议

### 推荐：平面结构 ✓

**理由**:
1. **图谱工具友好**: 一次扫描，无需遍历子目录
2. **可扩展性好**: 命令行长度不随论文数量增长
3. **简化 adapter 逻辑**: 不需要收集所有 p_* 目录

**实施方案**:
```python
# graphify_adapter.py 修改
cmd = [
    "graphify",
    "extract",
    str(papers_dir),  # 直接扫描 papers 目录
    "--backend", "openai",
]
```

**文件结构**:
```
library/papers/
├── p_1636de654dd3.md        ← 论文内容（标准化 Markdown）
├── p_1636de654dd3/          ← 元数据和资源
│   ├── manifest.json        ← 状态、pipeline 信息
│   ├── source.pdf           ← 原始 PDF（可选）
│   └── assets/              ← 图片等资源
│       ├── image_1.png
│       └── image_2.png
```

### 迁移成本评估

**需要修改的代码**:
1. `PaperPaths` - 调整路径计算逻辑
2. `graphify_adapter.py` - 简化扫描逻辑
3. `ingest.py` - 调整文件保存位置

**数据迁移**:
```bash
# 将 p_xxx/paper.md 移动到 p_xxx.md
for dir in library/papers/p_*/; do
    id=$(basename "$dir")
    mv "$dir/paper.md" "library/papers/$id.md"
done
```

**向后兼容**: 需要迁移现有 3 篇论文

## 结论

**推荐采用平面结构** ✓

- 图谱构建效率更高
- 可扩展性更好
- 简化 adapter 逻辑
- 命令行长度不受论文数量限制

**权衡**:
- 需要一次性迁移现有数据
- 资源隔离稍弱（但可通过命名约定维护）
