# PaperBase - Agent 工作指南

## 项目定位

PaperBase 是学术论文知识库基础设施，用于：
- 摄入、规范化、验证和图谱化学术论文
- 提供统一的 Canonical Markdown 作为 source of truth
- 支持幂等状态机管理论文处理流程

## Source of Truth

**核心原则：`library/papers/<storage_id>/paper.md` 是唯一 source of truth**

其他都是 derived artifacts（可重建）：
- `graph/` - Graphify 生成的知识图谱
- `registry/` - SQLite 快速查询索引
- `**/chunks.jsonl` - 检索用分块
- `**/references.jsonl` - 结构化引用

## 目录结构

```
paperbase/
├── src/paperbase/          # Python 包
│   ├── core/               # 核心逻辑（identity, paths, state）
│   ├── schemas/            # Pydantic schemas
│   ├── adapters/           # 外部工具适配器
│   ├── cli/                # CLI 入口
│   └── utils/              # 工具函数
├── config/                 # 配置文件
│   ├── paperbase.yaml      # 主配置
│   └── schemas/            # JSON Schema 定义
├── library/                # 知识库主体
│   ├── sources/pdf/        # 内容寻址的 PDF 存储
│   ├── papers/             # 规范化论文（Canonical）
│   ├── collections/        # 用户论文集合
│   └── notes/              # 用户笔记
├── registry/               # SQLite 索引
├── graph/                  # Graphify 输出
├── skills/                 # 项目级 skills
└── docs/                   # 文档
```

## Invariants（不可违反）

1. **每篇论文必须有唯一 `paper_id`**（doi:xxx 优先）
2. **每篇论文必须有 `manifest.json`** 记录状态和溯源
3. **不得通过自动化工作流绕过付费墙**（scansci 必须配置 `scihub_enabled=false`）
4. **graphify 和 zotero-mcp 使用全局安装**（`uv tool install`），不作为项目依赖
5. **Graphify 只扫描 `library/papers/**/paper.md`**（用 `.graphifyignore` 排除其他）
6. **所有资产路径必须是相对路径**（`./assets/fig-001.png`）
7. **状态转换必须更新 `manifest.json` 的 `updated_at`**
8. **不修改 `paper.md` 的 frontmatter 必须保持 `canonical_content_sha256` 不变**

## 工作流状态机

```
NORMALIZED → READY
```

**主流程状态：**
- `NORMALIZED`: 论文已摄入并规范化
- `READY`: 已加入图谱，可供查询

**异常状态：**
- `NEEDS_REVIEW`: 需要人工审核
- `BLOCKED`: 处理被阻塞
- `FAILED_RETRYABLE`: 临时失败，可重试
- `FAILED_PERMANENT`: 永久失败

**状态转换触发：**
- `ingest` → `NORMALIZED`
- `graph update` → `READY`

## Commands

```bash
# 摄入单篇论文
paperbase ingest "10.1038/s41586-026-10265-5"
paperbase ingest "arxiv:2401.12345"
paperbase ingest --file paper.pdf

# 搜索论文
paperbase search "machine learning"
paperbase search --zotero "reinforcement learning"

# 查询状态
paperbase status <paper_id>

# 更新图谱
paperbase graph update

# 验证知识库
paperbase validate
```

## Done Criteria

任务完成的标准：
- [ ] `manifest.json` 存在且 `state = "ready"`
- [ ] `paper.md` 存在且通过 schema validation
- [ ] `paper.md` 的 frontmatter 完整（title/authors/year/abstract）
- [ ] `references.jsonl` 存在且所有引用已 resolved
- [ ] `graph/` 已更新且 `manifest.json` 中 `graph.indexed = true`
- [ ] 所有测试通过

## 技术栈

- **项目管理**: uv
- **Schema 验证**: pydantic v2
- **Registry**: sqlite3
- **元数据标准**: CSL JSON
- **全局工具**（需单独安装）:
  - graphify (`uv tool install graphify`) - 知识图谱构建
  - zotero-mcp (`uv tool install zotero-mcp-server`) - Zotero 集成
- **依赖项目**:
  - paper-fetch-skill (论文获取，git clone 到 skills/)
  - citation-check-skill (引用验证，手动下载到 skills/)
