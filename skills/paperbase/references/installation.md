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
- **要求**: Agent 模式由宿主 Agent/Graphify skill 完成语义抽取；headless 模式才需要 PaperBase 本地 LLM 配置

### 安装命令

```bash
uv tool install graphify
```

### 验证安装

```bash
graphify --version
```

Expected output: `graphify 0.9.10+`

### 推荐的 Agent 工作流

```bash
paperbase graph preflight
# Agent 中运行：/graphify library/papers --update --no-viz
paperbase graph adopt
paperbase doctor
```

这条路径不读取 PaperBase 本地 LLM 配置。只有显式运行 `paperbase graph update` 时，才需要在 `config/paperbase.yaml` 中配置 OpenAI-compatible LLM；使用 `paperbase config show` 查看当前配置。不要在 skill、文档或 Git 提交中记录真实密钥。

真实论文内容可以被 `.gitignore` 排除；`library/papers/.graphifyignore` 会用 `!p_*.md` 重新纳入本地 Canonical，二者不冲突。

---

## 相关文档

- [troubleshooting-integration.md](troubleshooting-integration.md) - 集成问题详细排查
- [cli_commands.md](cli_commands.md) - PaperBase CLI 命令参考
- [troubleshooting.md](troubleshooting.md) - 完整故障排查指南
