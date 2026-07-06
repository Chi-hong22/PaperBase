# PaperBase

学术论文知识库基础设施。

## 特性

- 🎯 Canonical Markdown 作为 source of truth
- 📊 幂等状态机管理论文摄入流程
- 🔍 集成 Zotero、paper-fetch、graphify
- 📝 CSL JSON 标准元数据
- 🔄 可重建的知识图谱

## 快速开始

```bash
# 安装
uv sync

# 摄入论文
paperbase ingest "10.1038/s41586-026-10265-5"

# 查询知识库
paperbase search "machine learning"
```

## 文档

- [AGENTS.md](AGENTS.md) - Agent 工作指南
- [架构设计](docs/architecture.md)
- [API 文档](docs/api.md)

## 许可

MIT License
