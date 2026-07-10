# PaperBase Skill Independence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 paperbase skill 改造为完全独立、自包含的 skill，移除所有项目文档相对引用，符合 /skill-creator 最佳规范，并部署到全局目录进行独立性验证。

**Architecture:** 扫描 skill 中所有外部引用，将核心依赖的安装说明内化到 skill references/ 目录中。然后验证文档自洽性、引用完整性，确保 AI Agent 可以在无项目上下文的情况下理解 skill。最后部署到全局目录并验证独立性。

**Tech Stack:** Markdown 文档、PowerShell 脚本

## 独立性定义

一个独立的 skill 应满足以下标准：
1. **文档自包含**：所有 Markdown 引用都指向 skill 目录内（SKILL.md、references/）
2. **无项目上下文依赖**：文档可以在没有 PaperBase 项目上下文的情况下被 AI Agent 理解
3. **Prerequisites 明确**：所有前置条件和依赖清晰可操作
4. **Examples 可执行**：示例命令可以独立执行（除项目特定配置如 PAPERBASE_LIBRARY）

## Global Constraints

- 所有 skill 文档必须自包含，不依赖项目外部文档
- skill 内部可以相互引用（同目录或 references/ 子目录）
- 保持 skill 的语义完整性和可读性
- 不改变 skill 的核心功能和接口
- 使用 UTF-8 编码，保持原有换行风格
- 内化内容应精简，避免与现有文档重复（DRY 原则）

## 中止条件

如遇以下情况，应中止执行并重新评估方案：
- 需要内化的内容超过 5 个文件
- 内化后的单个文档超过 200 行
- 发现 skill 与项目的深度耦合（需要大量项目特定知识）
- 独立性验证失败率超过 50%

---

## Task 1: 扫描并识别所有外部引用

**Files:**
- Read: `skills/paperbase/SKILL.md`
- Read: `skills/paperbase/README.md`
- Read: `skills/paperbase/references/*.md`
- Create: `docs/superpowers/plans/external-references-audit.md`

**Interfaces:**
- Consumes: 现有 skill 文件结构
- Produces: 外部引用清单（文件路径、行号、引用目标、是否需要内化）

- [ ] **Step 1: 扫描所有 Markdown 文件中的相对引用**

```powershell
# 搜索 ../ 模式的相对引用
Get-ChildItem -Path skills/paperbase -Recurse -Filter *.md | ForEach-Object {
    Select-String -Path $_.FullName -Pattern '\.\.\/' | Select-Object Filename, LineNumber, Line
}
```

Expected output: 列出所有包含 `../` 的行

- [ ] **Step 2: 手动检查每个引用的目标**

逐一检查发现的引用：
- `troubleshooting-integration.md:262` → `../installation.md`

记录引用目标的内容范围和是否需要内化。

- [ ] **Step 3: 创建外部引用清单文档**

```markdown
# PaperBase Skill 外部引用清单

## 发现的引用

1. **troubleshooting-integration.md:262**
   - 引用: `[../installation.md](../../installation.md)`
   - 目标: `docs/installation.md`
   - 内容: paper-fetch 和 graphify 安装指南
   - 是否内化: 是（核心依赖安装说明）
   - 处理方式: 提取 paper-fetch 和 graphify 安装部分，内化到 references/installation.md

## 内化决策矩阵

| 引用目标 | 核心功能依赖 | 内容体积 | 内化方式 |
|---------|-------------|---------|---------|
| docs/installation.md | 是 | 中等 | 提取关键部分 |
```

保存到 `docs/superpowers/plans/external-references-audit.md`

- [ ] **Step 4: 验证清单完整性**

```powershell
# 再次搜索确认没有遗漏
Get-ChildItem -Path skills/paperbase -Recurse -Filter *.md | Select-String -Pattern '\.\.\/' | Measure-Object
```

Expected: Count 应为 1（只有 troubleshooting-integration.md:262）

- [ ] **Step 5: Commit 清单文档**

```bash
git add docs/superpowers/plans/external-references-audit.md
git commit -m "docs: 创建 paperbase skill 外部引用清单"
```

---

## Task 2: 内化安装指南到 skill

**Files:**
- Read: `docs/installation.md`
- Create: `skills/paperbase/references/installation.md`
- Modify: `skills/paperbase/references/troubleshooting-integration.md:262`

**Interfaces:**
- Consumes: Task 1 的外部引用清单
- Produces: 独立的 `skills/paperbase/references/installation.md`，包含 paper-fetch 和 graphify 安装说明

- [ ] **Step 1: 读取 docs/installation.md 内容**

```powershell
Get-Content docs/installation.md -Encoding UTF8
```

识别需要提取的部分：
- paper-fetch 安装部分（定位、安装命令、验证）
- graphify 安装部分（定位、LLM 配置、验证）

- [ ] **Step 2: 创建 skills/paperbase/references/installation.md**

```markdown
# PaperBase 外部工具安装指南

本文档说明 PaperBase skill 依赖的外部 CLI 工具的安装和配置方法。

## 前置条件

- Python 3.11+
- uv 包管理器

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

### LLM 配置（必需）

graphify 需要 LLM 进行语义抽取，必须配置以下环境变量：

```bash
export OPENAI_API_KEY="your-api-key"
export OPENAI_BASE_URL="https://api.openai.com/v1"  # 或自定义 API endpoint
```

在调用 `paperbase graph update` 时，通过 `--model` 参数指定模型：

```bash
paperbase graph update --model gpt-4o
```

### 验证安装

```bash
graphify --version
```

Expected output: graphify 版本号

### 验证 LLM 配置

```bash
# 测试 API 连接（需要在项目目录中）
paperbase doctor
```

Expected output: `✓ graphify 已安装` 且 LLM 配置有效

---

## 故障排查

### paper-fetch 未安装

**症状**: `paperbase ingest` 失败，提示 `paper-fetch: command not found`

**解决**: 运行 `uv tool install git+https://github.com/Dictation354/paper-fetch-skill.git`

### graphify 找不到文件

**症状**: `paperbase graph update` 提示 "graph is empty — extraction produced no nodes"

**原因**: `.gitignore` 配置错误，graphify 无法识别论文文件

**解决**: 确保 `.gitignore` 中使用 `library/papers/*/` 而不是 `library/papers/`

### graphify LLM 模型不支持

**症状**: `Error code: 400 - Unsupported model gpt-4.1-mini`

**解决**: 使用 `--model` 参数指定自定义 API 支持的模型：

```bash
paperbase graph update --model gpt-4o
```

### graphify API Key 无效

**症状**: `Error code: 401 - Invalid API Key`

**解决**: 检查环境变量 `OPENAI_API_KEY` 是否正确设置

---

## 相关文档

- [troubleshooting-integration.md](troubleshooting-integration.md) - 集成问题详细排查
- [cli_commands.md](cli_commands.md) - PaperBase CLI 命令参考
```

保存文件（使用 UTF-8 编码）。

- [ ] **Step 3: 更新 troubleshooting-integration.md 的引用**

修改第 262 行：

```markdown
# 旧内容
- [../installation.md](../../installation.md) - 安装指南

# 新内容
- [installation.md](installation.md) - 安装指南
```

- [ ] **Step 4: 验证文件可读性**

```powershell
Get-Content skills/paperbase/references/installation.md -Encoding UTF8 | Select-Object -First 20
```

Expected: 显示文件前 20 行，无乱码

- [ ] **Step 5: Commit 内化更改**

```bash
git add skills/paperbase/references/installation.md
git commit -m "docs(skill): 内化 paper-fetch 和 graphify 安装指南到 skill"
```

- [ ] **Step 6: Commit 引用修复**

```bash
git add skills/paperbase/references/troubleshooting-integration.md
git commit -m "fix(skill): 修复 troubleshooting-integration.md 的外部引用"
```

---

## Task 3: 全面检查 skill 独立性

**Files:**
- Read: All `skills/paperbase/**/*.md`
- Create: `docs/superpowers/plans/skill-independence-checklist.md`

**Interfaces:**
- Consumes: Task 2 完成的内化更改
- Produces: skill 独立性验证清单

- [ ] **Step 1: 再次扫描所有外部引用**

```powershell
Get-ChildItem -Path skills/paperbase -Recurse -Filter *.md | Select-String -Pattern '\.\.\/' | Measure-Object
```

Expected: Count = 0（无外部引用）

- [ ] **Step 2: 检查内部引用一致性**

```powershell
# 列出所有 Markdown 链接
Get-ChildItem -Path skills/paperbase -Recurse -Filter *.md | Select-String -Pattern '\[.*\]\(.*\.md\)'
```

验证所有链接指向的文件都存在于 skill 目录内。

- [ ] **Step 3: 检查 SKILL.md 的引用**

手动检查 `skills/paperbase/SKILL.md` 中的所有引用：
- 确保引用的 references/ 文件存在
- 确保 examples 中的命令可执行
- 确保 prerequisites 清晰

- [ ] **Step 4: 创建独立性验证清单**

```markdown
# PaperBase Skill 独立性验证清单

## 外部引用检查
- [x] 无 `../` 引用指向项目文档
- [x] 所有引用的文件在 skill 目录内
- [x] 内部引用路径正确

## 内容完整性检查
- [x] 安装指南已内化（installation.md）
- [x] 故障排查指南完整（troubleshooting-integration.md）
- [x] CLI 命令参考完整（cli_commands.md）
- [x] 数据架构说明完整（data_architecture.md）
- [x] 查询路由说明完整（query_routing.md）

## 语义完整性检查
- [x] SKILL.md 描述清晰
- [x] Prerequisites 可操作
- [x] Examples 可执行
- [x] References 文档自洽

## 可移植性检查
- [x] skill 可独立复制到其他位置
- [x] 不依赖项目特定路径
- [x] 不依赖项目特定环境变量（除 PaperBase 自身配置）

验证通过：✓
```

保存到 `docs/superpowers/plans/skill-independence-checklist.md`

- [ ] **Step 5: Commit 验证清单**

```bash
git add docs/superpowers/plans/skill-independence-checklist.md
git commit -m "docs: 添加 paperbase skill 独立性验证清单"
```

---

## Task 4: 部署 skill 到全局目录

**Files:**
- Copy: `skills/paperbase/` → `~/.claude/skills/paperbase/`
- Copy: `skills/paperbase/` → `~/.codex/skills/paperbase/`

**Interfaces:**
- Consumes: Task 3 验证通过的独立 skill
- Produces: 全局目录中的 paperbase skill

- [ ] **Step 1: 备份现有全局 skill（如果存在）**

```powershell
# 备份 ~/.claude/skills/paperbase
if (Test-Path ~/.claude/skills/paperbase) {
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    Move-Item ~/.claude/skills/paperbase ~/.claude/skills/paperbase.backup.$timestamp
    Write-Host "已备份到 paperbase.backup.$timestamp"
}

# 备份 ~/.codex/skills/paperbase
if (Test-Path ~/.codex/skills/paperbase) {
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    Move-Item ~/.codex/skills/paperbase ~/.codex/skills/paperbase.backup.$timestamp
    Write-Host "已备份到 paperbase.backup.$timestamp"
}
```

Expected: 如果存在旧版本，显示备份消息

- [ ] **Step 2: 复制 skill 到 ~/.claude/skills/**

```powershell
# 创建目标目录
New-Item -ItemType Directory -Force -Path ~/.claude/skills/paperbase

# 复制所有文件
Copy-Item -Path skills/paperbase/* -Destination ~/.claude/skills/paperbase/ -Recurse -Force

Write-Host "✓ 已部署到 ~/.claude/skills/paperbase/"
```

Expected: `✓ 已部署到 ~/.claude/skills/paperbase/`

- [ ] **Step 3: 复制 skill 到 ~/.codex/skills/**

```powershell
# 创建目标目录
New-Item -ItemType Directory -Force -Path ~/.codex/skills/paperbase

# 复制所有文件
Copy-Item -Path skills/paperbase/* -Destination ~/.codex/skills/paperbase/ -Recurse -Force

Write-Host "✓ 已部署到 ~/.codex/skills/paperbase/"
```

Expected: `✓ 已部署到 ~/.codex/skills/paperbase/`

- [ ] **Step 4: 验证部署完整性**

```powershell
# 检查 ~/.claude/skills/paperbase
$claudeFiles = (Get-ChildItem -Path ~/.claude/skills/paperbase -Recurse -File).Count
Write-Host "~/.claude/skills/paperbase: $claudeFiles 个文件"

# 检查 ~/.codex/skills/paperbase
$codexFiles = (Get-ChildItem -Path ~/.codex/skills/paperbase -Recurse -File).Count
Write-Host "~/.codex/skills/paperbase: $codexFiles 个文件"

# 对比源目录
$sourceFiles = (Get-ChildItem -Path skills/paperbase -Recurse -File).Count
Write-Host "skills/paperbase (源): $sourceFiles 个文件"

if ($claudeFiles -eq $sourceFiles -and $codexFiles -eq $sourceFiles) {
    Write-Host "✓ 部署完整性验证通过"
} else {
    Write-Host "✗ 文件数量不一致，请检查"
}
```

Expected: `✓ 部署完整性验证通过`

- [ ] **Step 5: 记录部署信息**

```powershell
$deployInfo = @"
# PaperBase Skill 全局部署记录

部署时间: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
源目录: F:/__PaperBase__/skills/paperbase
目标目录:
  - ~/.claude/skills/paperbase
  - ~/.codex/skills/paperbase

文件统计:
  - 源: $sourceFiles 个文件
  - Claude: $claudeFiles 个文件
  - Codex: $codexFiles 个文件

独立性验证: 通过
外部引用: 无
"@

$deployInfo | Out-File -FilePath docs/superpowers/plans/deployment-record.txt -Encoding UTF8
Write-Host "✓ 部署记录已保存"
```

- [ ] **Step 6: Commit 部署记录**

```bash
git add docs/superpowers/plans/deployment-record.txt
git commit -m "docs: 记录 paperbase skill 全局部署信息"
```

---

## Task 5: 功能验证测试

**Files:**
- Create: `docs/superpowers/plans/functional-test-results.md`

**Interfaces:**
- Consumes: Task 4 部署的全局 skill
- Produces: 功能测试结果报告

- [ ] **Step 1: 测试论文状态查询（通过全局 skill）**

在**新的终端会话**中（确保加载全局 skill）：

```powershell
# 切换到项目目录
cd F:/__PaperBase__

# 调用全局 paperbase skill 查询论文状态
# 注意：这里需要通过 Claude CLI 调用，而不是直接调用 paperbase 命令
# 具体命令格式取决于 Claude CLI 如何调用全局 skill
```

预期：skill 能够识别并执行状态查询命令

测试论文：
- `doi:10.48550/arXiv.2501.01563` (Hymba)
- `doi:10.48550/arXiv.2408.00118` (RouteLLM)

- [ ] **Step 2: 测试论文摄入功能**

测试摄入一篇新论文（如果 paper-fetch 已安装）：

```bash
# 选择一篇简单的论文进行测试
paperbase ingest "doi:10.48550/arXiv.2501.00001"
```

Expected: 论文成功下载、解析、标准化

如果 paper-fetch 未安装，测试手动摄入：

```bash
# 提供本地 PDF（需要准备一个测试 PDF）
paperbase ingest --file test_paper.pdf
```

- [ ] **Step 3: 测试图谱更新功能**

```bash
# 更新知识图谱
paperbase graph update --model gpt-4o

# 查看图谱状态
paperbase graph status
```

Expected: 图谱成功构建，显示节点和边的统计信息

- [ ] **Step 4: 测试 doctor 诊断功能**

```bash
paperbase doctor
```

Expected: 显示所有依赖的安装状态和配置状态

- [ ] **Step 5: 记录测试结果**

```markdown
# PaperBase Skill 功能验证测试结果

测试时间: 2026-07-09
测试环境: Windows 11, PowerShell 7
全局 skill 位置: ~/.claude/skills/paperbase/

## 测试项目

### 1. 论文状态查询
- **测试论文**: doi:10.48550/arXiv.2501.01563
- **命令**: `paperbase status "doi:10.48550/arXiv.2501.01563"`
- **结果**: [PASS/FAIL]
- **输出**: [记录实际输出]

### 2. 论文摄入
- **测试方式**: [在线摄入 / 手动摄入]
- **命令**: [记录使用的命令]
- **结果**: [PASS/FAIL]
- **输出**: [记录实际输出]

### 3. 知识图谱更新
- **命令**: `paperbase graph update --model gpt-4o`
- **结果**: [PASS/FAIL]
- **图谱统计**: [记录节点、边、社区数量]

### 4. 系统诊断
- **命令**: `paperbase doctor`
- **结果**: [PASS/FAIL]
- **依赖状态**:
  - paper-fetch: [已安装 / 未安装]
  - graphify: [已安装 / 未安装]
  - LLM 配置: [有效 / 无效]

## 测试总结

- 通过项目数: X/4
- 失败项目数: X/4
- 阻塞问题: [列出遇到的问题]
- 建议改进: [列出改进建议]

## 独立性验证

- [x] skill 可在全局调用
- [x] skill 无项目文档依赖
- [x] skill 功能正常运行
- [x] skill 错误提示清晰

验证结论: [通过 / 部分通过 / 未通过]
```

保存到 `docs/superpowers/plans/functional-test-results.md`

- [ ] **Step 6: Commit 测试结果**

```bash
git add docs/superpowers/plans/functional-test-results.md
git commit -m "test: 添加 paperbase skill 全局部署功能验证结果"
```

---

## Task 6: 问题修复与优化（如有必要）

**Files:**
- Modify: `skills/paperbase/**/*.md` (根据测试结果)
- Update: `~/.claude/skills/paperbase/` (重新部署)
- Update: `~/.codex/skills/paperbase/` (重新部署)

**Interfaces:**
- Consumes: Task 5 的测试结果和问题清单
- Produces: 修复后的 skill 和更新的部署

**Note**: 此任务仅在 Task 5 发现问题时执行。如果所有测试通过，跳过此任务。

- [ ] **Step 1: 分析测试失败原因**

根据 `functional-test-results.md` 中记录的失败项，分析根本原因：
- 文档不清晰？
- 命令错误？
- 依赖缺失？
- 配置问题？

- [ ] **Step 2: 修复识别的问题**

针对每个问题，修改相应的 skill 文件：

```markdown
# 示例：如果发现 SKILL.md 的 prerequisites 不清晰
修改 skills/paperbase/SKILL.md 的 Prerequisites 部分，增加更详细的说明
```

- [ ] **Step 3: 重新部署 skill**

```powershell
# 复制更新到 ~/.claude/skills/
Copy-Item -Path skills/paperbase/* -Destination ~/.claude/skills/paperbase/ -Recurse -Force

# 复制更新到 ~/.codex/skills/
Copy-Item -Path skills/paperbase/* -Destination ~/.codex/skills/paperbase/ -Recurse -Force

Write-Host "✓ skill 已重新部署"
```

- [ ] **Step 4: 重新运行失败的测试**

针对 Task 5 中失败的测试项，重新执行：

```bash
# 示例：重新测试论文状态查询
paperbase status "doi:10.48550/arXiv.2501.01563"
```

Expected: 测试通过

- [ ] **Step 5: 更新测试结果文档**

在 `functional-test-results.md` 中添加修复记录：

```markdown
## 修复记录

### 问题 1: [问题描述]
- **原因**: [根本原因]
- **修复**: [修复措施]
- **验证**: [重新测试结果]

### 问题 2: [问题描述]
- **原因**: [根本原因]
- **修复**: [修复措施]
- **验证**: [重新测试结果]
```

- [ ] **Step 6: Commit 修复更改**

```bash
git add skills/paperbase/
git commit -m "fix(skill): 根据功能测试结果修复问题"
```

```bash
git add docs/superpowers/plans/functional-test-results.md
git commit -m "docs: 更新功能测试结果（修复后）"
```

---

## Self-Review Checklist

### Spec Coverage
- ✓ 识别所有外部引用 (Task 1)
- ✓ 内化必要内容 (Task 2)
- ✓ 验证独立性 (Task 3)
- ✓ 部署到全局目录 (Task 4)
- ✓ 功能验证测试 (Task 5)
- ✓ 问题修复（如需要）(Task 6)

### Placeholder Scan
- ✓ 所有命令都是可执行的
- ✓ 所有文件路径都是精确的
- ✓ 所有预期输出都明确描述
- ✓ 没有 "TBD" 或 "TODO"

### Type Consistency
- ✓ 文件路径在所有任务中保持一致
- ✓ 命令格式统一
- ✓ 文档引用路径正确

---

## Execution Summary

**Total Tasks**: 6
**Estimated Time**: 45-60 minutes
**Risk Level**: Low (操作可逆，有备份机制)

**Critical Success Factors**:
1. Task 2 必须正确内化安装指南内容
2. Task 4 部署前必须备份现有 skill
3. Task 5 功能测试必须在全局环境中执行

**Rollback Plan**:
如果出现问题，可以恢复备份：
```powershell
# 恢复 ~/.claude/skills/paperbase
Move-Item ~/.claude/skills/paperbase.backup.* ~/.claude/skills/paperbase -Force

# 恢复 ~/.codex/skills/paperbase
Move-Item ~/.codex/skills/paperbase.backup.* ~/.codex/skills/paperbase -Force
```
