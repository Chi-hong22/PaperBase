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
4. **外部工具使用全局安装**（`uv tool install`），不作为项目依赖：
   - `paper-fetch`: 通过 CLI 调用，作为外部黑盒工具
   - `graphify`: 知识图谱构建
   - `zotero-mcp`: Zotero 集成
5. **目录结构**：
   - 立体结构：`library/papers/p_xxx/paper.md`（推荐）
   - 每个 paper 独立文件夹，包含 paper.md、manifest.json、source/、assets/
6. **Graphify 扫描**：
   - 扫描 `library/papers/` 及其子目录
   - `.gitignore` 必须配置为 `library/papers/*/` 只排除子目录，不排除 .md 文件
   - graphify 需要 `--model` 参数和环境变量（OPENAI_API_KEY, OPENAI_BASE_URL）
7. **所有资产路径必须是相对路径**（`./assets/fig-001.png`）
8. **状态转换必须更新 `manifest.json` 的 `updated_at`**
9. **不修改 `paper.md` 的 frontmatter 必须保持 `canonical_content_sha256` 不变**

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

## 查询双轨系统

**Registry (结构化查询)**：
- 精确匹配：doi、paper_id
- 状态筛选：state
- 元数据查询：year、author
- 后端：SQLite 索引

**Graph (语义查询)**：
- 概念关联
- 路径推理
- 社区发现
- 后端：Graphify 知识图谱

**统一入口**：/paperbase skill 自动路由

## Commands

```bash
# 摄入单篇论文
paperbase ingest "10.1038/s41586-026-10265-5"
paperbase ingest "arxiv:2401.12345"
paperbase ingest --file paper.pdf

# 搜索论文
paperbase search "machine learning"

# 从 Zotero 导入条目
paperbase ingest --zotero-key <item-key>

# 查询状态
paperbase status <paper_id>

# 更新图谱
paperbase graph update

# 验证环境和知识库一致性
paperbase doctor
paperbase sync
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
  - paper-fetch (`uv tool install git+https://github.com/Dictation354/paper-fetch-skill.git`) - 在线论文获取（可选）
- **外部黑盒工具**:
  - paper-fetch-skill: PaperBase 通过 CLI 调用，不关心其安装方式
    - 推荐: `uv tool install git+https://github.com/Dictation354/paper-fetch-skill.git` (全局安装)
    - 备选: `uv sync --extra online-fetch` (项目依赖)
    - 职责: 论文抓取、元数据提取、PDF 处理
    - 接口: CLI (`paper-fetch --query <id> --format both`)
    - 数据流: 查询 → paper-fetch CLI → JSON 输出 → PaperBase adapter → Canonical Markdown
