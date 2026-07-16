# PaperBase - Agent 工作指南

## 项目定位

PaperBase 是学术论文知识库基础设施，用于：
- 摄入、规范化、验证和图谱化学术论文
- 提供统一的 Canonical Markdown 作为 source of truth
- 支持幂等状态机管理论文处理流程

## Source of Truth

**核心原则：`library/papers/p_<storage_id>.md` 是论文内容的唯一 source of truth；同名目录中的 `manifest.json` 是状态与溯源记录。**

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
   - Canonical 使用平面结构：`library/papers/p_xxx.md`
   - 同名目录 `library/papers/p_xxx/` 保存 `manifest.json`、`source/`、`assets/` 与派生文件
6. **Graphify 扫描**：
   - 只扫描 `library/papers/p_*.md` Canonical，不在建图阶段读取 PDF、URL 或附件
   - `.gitignore` 排除真实论文内容；`library/papers/.graphifyignore` 用 `!p_*.md` 重新纳入本地 Canonical，并精确排除 `BLOCKED` 文件
   - Agent 路径不读取 PaperBase 本地 LLM 配置；headless `paperbase graph update` 才读取 `config/paperbase.yaml`
7. **所有资产路径必须是相对路径**（`./assets/fig-001.png`）
8. **状态转换必须更新 `manifest.json` 的 `updated_at`**
9. **不修改 Canonical frontmatter/正文时必须保持 `canonical_content_sha256` 不变**
10. **真实论文、源 PDF、manifest、Registry 和图谱产物只保留在本地，不得加入 Git 或远程历史**

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

# Agent 推荐的图谱更新
paperbase graph preflight
# /graphify library/papers --update --no-viz
paperbase graph adopt

# 手动 headless 备用路径
paperbase graph update --incremental

# 验证环境和知识库一致性
paperbase doctor
paperbase sync
```

## Done Criteria

任务完成的标准：
- [ ] `manifest.json` 存在且 `state = "ready"`
- [ ] `library/papers/p_<storage_id>.md` 存在且通过 schema validation
- [ ] Canonical frontmatter 完整（title/authors/year/abstract）
- [ ] `references.jsonl` 存在且所有引用已 resolved
- [ ] `graph/` 已更新且 `manifest.json` 中 `graph.indexed = true`
- [ ] 所有测试通过
- [ ] `git ls-files library` 不包含真实论文、manifest、源 PDF 或派生索引

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
