# PaperBase Skill - 更新日志

## [2026-07-09] - 重大功能增强

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
paperbase query related p_5186fb930e31  # 找到 2 个相关论文 ✓
paperbase query topic "transformer"      # 语义查询可用 ✓
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

### 🐛 Bug 修复

#### 1. 扁平化结构统计错误
- **修复 doctor 命令**：`glob("p_*")` 重复计数文件+目录
- 显示 6 篇 → 正确显示 4 篇

#### 2. manifest path 引用错误
- **修复相对路径**：`./paper.md` → `../{storage_id}.md`
- 适配扁平化结构（paper.md 与目录同级）

#### 3. 文档与实现不一致
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
- `graph_query.py` - 支持 hyperedges 自动转换
- `online_ingest.py` - 集成 chunker
- `ingest.py` - 同上集成
- `status.py` - 添加过滤参数
- `remove.py` - 添加自动化参数
- `doctor.py` - 修复论文计数

#### 测试覆盖
- `test_online_ingest.py` - 更新路径为扁平化结构
- 所有单元测试通过 ✓

### 📊 性能影响

| 功能 | 之前 | 现在 | 改进 |
|------|------|------|------|
| 论文统计 | 错误（重复计数） | 准确 | 100% |
| query related | 返回空 | 正常工作 | 从 0 → 可用 |
| 全文检索 | 无 chunks | 自动生成 | 功能启用 |
| 批量删除 | 需交互 | 自动化 | 流程简化 |

### ⚠️ 破坏性变更

无破坏性变更。所有修改向后兼容。

### 🎯 升级指南

**从旧版本升级：**

1. **无需手动操作** - 新摄入的论文自动支持所有新功能
2. **现有论文补充 chunks**（可选）：
   ```bash
   # 未来版本将提供批量生成命令
   # 当前：重新摄入论文会自动生成 chunks
   ```

3. **验证升级**：
   ```bash
   paperbase doctor                    # 检查论文数量正确
   paperbase status --year 2021        # 测试过滤功能
   paperbase query related <paper_id>  # 测试图谱查询
   ```

### 📦 提交记录

```
8938bb7 - feat(query): 适配 graphify 0.9.10 hyperedges 格式
991927b - feat(cli): 增强 status 和 remove 命令
840e048 - docs(skill): 更新文档为扁平化结构
0ca027c - fix(flat): 修复扁平化结构导致的 3 个 bug
f6598f4 - docs(skill): 修复文档与实现不一致的问题
```

### 🙏 致谢

感谢用户反馈的 bug 报告和功能建议！
