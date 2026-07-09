# PaperBase 常见问题排查补充

最后更新：2026-01-16

本文档补充 `troubleshooting.md`，专注于本次集成相关的问题。

## paper-fetch 相关问题

### paper-fetch 未安装

**症状**：
```
✗ paper-fetch not found
提示: 安装方式: uv tool install git+https://github.com/Dictation354/paper-fetch-skill.git
```

**解决方法**：
```bash
uv tool install git+https://github.com/Dictation354/paper-fetch-skill.git
paper-fetch --version  # 验证安装（应显示 3.0.1）
```

**重要说明**：
- paper-fetch 是外部 CLI 工具，安装到 `~/.local/bin/`
- **不需要**安装到 `~/.claude/skills/` 或项目 `skills/` 目录
- PaperBase 通过 `subprocess` 调用，只要命令在 PATH 中即可
- 安装后重启终端以刷新 PATH

### paper-fetch 调用失败

**症状**：
```
Error: paper-fetch command failed with exit code 1
```

**可能原因**：
1. DOI/arXiv ID 格式错误
2. 网络连接问题
3. paper-fetch 版本过旧

**解决方法**：
```bash
# 1. 验证标识符格式
paperbase ingest "doi:10.1038/nature"  # 正确
paperbase ingest "10.1038/nature"      # 也支持

# 2. 检查网络
curl -I https://doi.org/10.1038/nature

# 3. 更新 paper-fetch
uv tool upgrade paper-fetch-skill
paper-fetch --version  # 确认版本 >= 3.0.1
```

---

## graphify 相关问题

### graphify 找不到文件

**症状**：
```
[graphify extract] found 0 code, 0 docs, 0 papers
[graphify extract] graph is empty — extraction produced no nodes
```

**根本原因**：
`.gitignore` 配置错误，导致 graphify 无法扫描 `library/papers/` 目录。

**解决方法**：

检查并修复 `.gitignore`：
```bash
# 错误配置（会排除整个 papers 目录）
library/papers/

# 正确配置（只排除子目录，不排除 paper.md）
library/papers/*/
!library/papers/*.md
```

**验证修复**：
```bash
# 测试 graphify 是否能识别文件
graphify library/papers 2>&1 | grep "found"
# 应显示: found X docs, Y papers
```

### graphify LLM 模型不支持

**症状**：
```
Error code: 400 - {'error': {'message': 'Unsupported model gpt-4.1-mini'}}
```

**原因**：
graphify 默认使用 `gpt-4.1-mini`，但自定义 API 不支持该模型。

**解决方法**：

1. 在 `config/paperbase.yaml` 中配置正确的模型：
```yaml
llm:
  base_url: ${PAPERBASE_LLM_BASE_URL}
  api_key: ${PAPERBASE_LLM_API_KEY}
  model: gpt-4o-mini  # 或你的 API 支持的其他模型
```

2. 或通过环境变量：
```bash
export PAPERBASE_LLM_MODEL="gpt-4o-mini"
```

3. 验证配置：
```bash
uv run paperbase config show | grep model
```

### graphify API Key 无效

**症状**：
```
Error code: 401 - {'error': {'message': 'Invalid API Key'}}
```

**解决方法**：

1. 检查 API Key：
```bash
uv run paperbase config show | grep api_key
# 应显示: api_key: sk-...（前10位）
```

2. 重新设置环境变量：
```bash
export PAPERBASE_LLM_API_KEY="sk-your-actual-key"
```

3. 验证 API Key 是否有效：
```bash
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $PAPERBASE_LLM_API_KEY"
```

---

## 目录结构问题

### 扁平化结构（当前实现）

**当前结构**（2026-07-09）：
- ✅ **扁平化结构**：`library/papers/p_xxx.md` + `library/papers/p_xxx/`
- Canonical Markdown 与目录同级，便于 graphify 批量扫描

**扁平化优势**：
1. graphify 工具可直接扫描 papers/ 目录（不需要递归）
2. 相关文件集中管理（paper.md、source.pdf、assets）
3. graphify 效果更好（29 nodes vs 14 nodes）
4. 符合设计理念

**如果你使用了扁平化结构**：

恢复到立体结构：
```bash
# 移动 .md 文件到子目录
cd library/papers
for file in *.md; do
  storage_id="${file%.md}"
  mkdir -p "$storage_id"
  mv "$file" "$storage_id/paper.md"
done
```

---

## 配置问题

### LLM 配置缺失

**症状**：
```
error: no LLM API key found
```

**解决方法**：

完整配置 LLM（graphify 必需）：
```bash
export PAPERBASE_LLM_BASE_URL="https://api.openai.com/v1"
export PAPERBASE_LLM_API_KEY="sk-..."
export PAPERBASE_LLM_MODEL="gpt-4o-mini"
```

或编辑 `config/paperbase.yaml`。

### 环境变量未生效

**症状**：
配置了环境变量但 `paperbase config show` 不显示。

**解决方法**：

1. 确认变量名正确：
```bash
# 正确
export PAPERBASE_LLM_API_KEY="..."

# 错误
export LLM_API_KEY="..."  # 缺少 PAPERBASE_ 前缀
```

2. 重新加载配置：
```bash
source ~/.bashrc  # 或 ~/.zshrc
```

3. 在同一会话中验证：
```bash
echo $PAPERBASE_LLM_API_KEY
uv run paperbase config show
```

---

## 诊断命令

### 快速健康检查

```bash
# 检查所有依赖
uv run paperbase doctor

# 检查 paper-fetch
paper-fetch --version

# 检查 graphify
graphify --version

# 检查 LLM 配置
uv run paperbase config show
```

### 验证 graphify 集成

```bash
# 1. 检查文件识别
graphify library/papers 2>&1 | grep "found"

# 2. 测试完整流程
uv run paperbase graph update --force

# 3. 查看图谱统计
uv run paperbase graph status
```

---

## 相关文档

- [troubleshooting.md](troubleshooting.md) - 完整故障排查指南
- [cli_commands.md](cli_commands.md) - CLI 命令参考
- [installation.md](installation.md) - 安装指南
