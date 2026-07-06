# PaperBase

学术论文知识库基础设施。

## 特性

- 🎯 Canonical Markdown 作为 source of truth
- 📊 幂等状态机管理论文摄入流程
- 🔍 集成 Zotero、paper-fetch、graphify
- 📝 CSL JSON 标准元数据
- 🔄 可重建的知识图谱

## 快速开始

### 安装项目依赖

```bash
# 安装 Python 依赖
uv sync
```

### 安装全局工具（必需）

PaperBase 依赖以下全局工具，需要单独安装：

```bash
# 安装 graphify（知识图谱构建）
uv tool install graphify

# 安装 zotero-mcp（Zotero 集成）
uv tool install zotero-mcp-server

# 验证安装
graphify --version
zotero-cli --version
```

### 使用

```bash
# 摄入论文
paperbase ingest "10.1038/s41586-026-10265-5"

# 查询知识库
paperbase search "machine learning"

# 更新知识图谱
paperbase graph update
```

## 文档

- [AGENTS.md](AGENTS.md) - Agent 工作指南
- [架构设计](docs/architecture.md)
- [API 文档](docs/api.md)

## 许可

MIT License
