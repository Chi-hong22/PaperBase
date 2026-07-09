# PaperBase 外部工具安装指南

本文档说明 PaperBase skill 依赖的外部 CLI 工具的安装和配置方法。

## 前置条件

- Python 3.11+
- uv 包管理器

---

## paper-fetch 安装

### 定位

paper-fetch 是外部 CLI 工具，用于从 DOI/arXiv/URL 获取论文内容和元数据。

- **架构**: 外部 CLI 工具（黑盒调用）
- **安装位置**: `~/.local/bin/paper-fetch`（全局 CLI）
- **调用方式**: PaperBase 通过 `subprocess` 调用 `paper-fetch --format both`

### 安装命令

```bash
uv tool install git+https://github.com/Dictation354/paper-fetch-skill.git
```

### 验证安装

```bash
paper-fetch --version
```

Expected output: `3.0.1` 或更高版本

### 备选方案

如果无法安装 paper-fetch，可以手动提供本地 PDF：

```bash
paperbase ingest --file paper.pdf
```

---

## graphify 安装

### 定位

graphify 是外部 CLI 工具，用于构建论文语义关联网络。

- **架构**: 外部 CLI 工具
- **职责**: 从 Markdown 文件构建知识图谱
- **要求**: 需要配置 LLM（OpenAI API 或兼容接口）

### 安装命令

```bash
uv tool install graphify
```

### 验证安装

```bash
graphify --version
```

Expected output: `graphify 0.9.10+`

### LLM 配置（必需）

graphify 需要 LLM 进行语义抽取，必须配置以下环境变量：

```bash
# 方式 1: 使用 OpenAI 兼容 API
export PAPERBASE_LLM_BASE_URL="https://api.openai.com/v1"
export PAPERBASE_LLM_API_KEY="sk-..."
export PAPERBASE_LLM_MODEL="gpt-4o-mini"

# 方式 2: 使用其他提供商（如 Anthropic、Gemini 等）
export PAPERBASE_LLM_BASE_URL="https://api.anthropic.com/v1"
export PAPERBASE_LLM_API_KEY="sk-ant-..."
export PAPERBASE_LLM_MODEL="claude-3-5-sonnet-20241022"
```

**重要说明：**
- PaperBase 会自动将配置传递给 graphify（通过 `--backend openai --model <model>`）
- 必须使用支持的模型名称（不能使用默认的 `gpt-4.1-mini`）
- 配置存储在 `config/paperbase.yaml` 中

### 验证 LLM 配置

```bash
paperbase config show
```

Expected output: 显示 LLM 配置有效

或使用诊断命令：

```bash
paperbase doctor
```

Expected output: `✓ graphify 已安装` 且 LLM 配置有效

---

## 相关文档

- [troubleshooting-integration.md](troubleshooting-integration.md) - 集成问题详细排查
- [cli_commands.md](cli_commands.md) - PaperBase CLI 命令参考
- [troubleshooting.md](troubleshooting.md) - 完整故障排查指南
