# PaperBase Skill

PaperBase 统一交互接口，提供命令包装和查询路由功能。

## 功能

1. **命令包装器** - 自动检测库路径，执行 CLI 命令
2. **查询路由** - 智能路由结构化查询（Registry）和语义查询（Graphify）

## 安装

### 自动安装（推荐）

```bash
# Unix/Linux/macOS
cd <PaperBase 仓库>/skills/paperbase
./install.sh

# Windows
cd <PaperBase 仓库>\skills\paperbase
powershell -ExecutionPolicy Bypass -File install.ps1                 # 默认安装到 Codex
powershell -ExecutionPolicy Bypass -File install.ps1 -Agent claude  # 安装到 Claude Code
powershell -ExecutionPolicy Bypass -File install.ps1 -Agent both    # 同时安装到两者
```

更新已有 skill 时，安装脚本会分别保留 Codex 和 Claude Code 原有的 `workspaces.json`。

### 手动安装

将 `paperbase-wrapper.sh` (Unix) 或 `paperbase-wrapper.ps1` (Windows) 添加到 PATH。

## 使用方式

### 查询路由（AI Agent）

```bash
/paperbase doi:10.1234/abc           # Registry 结构化查询
/paperbase state:ready               # 状态查询
/paperbase SLAM 相关论文             # Graphify 语义查询
```

### CLI 命令（终端用户）

```bash
paperbase-wrapper.sh ingest "doi:10.1234/abc"
paperbase-wrapper.sh graph preflight
# Agent 中运行：/graphify library/papers --update --no-viz
# 语义 Agent 编排多个 subagents 并行抽取 Canonical Markdown
paperbase-wrapper.sh graph adopt
paperbase-wrapper.sh status
```

## 查询路由规则

**结构化查询** → Registry:
- `doi:`, `paper_id:`, `state:`, `year:`, `author:`

**语义查询** → Graphify:
- 自然语言查询
- 概念关联、主题探索

## 目录结构

```
paperbase/
├── SKILL.md                    # Skill 文档
├── README.md                   # 安装指南
├── query_router.py             # 查询路由逻辑
├── paperbase-wrapper.sh        # Unix 包装器
├── paperbase-wrapper.ps1       # Windows 包装器
├── install.sh                  # Unix 安装脚本
├── install.ps1                 # Windows 安装脚本
└── workspaces.json             # 库路径缓存
```

## 依赖

- Python 3.11+
- uv (包管理器)
- PaperBase CLI
- graphify（用于语义图谱）

## 更多信息

详见 [SKILL.md](SKILL.md)
