# PaperBase 开发路线图

> 当前状态更新于 2026-07-16。已实现能力以代码、CLI `--help` 和主题文档为准；下方工作量估算保留为规划参考。

## 🎯 当前版本功能

### 核心功能
- ✅ PDF 论文摄入（在线下载 + 本地文件）
- ✅ Canonical Markdown 转换
- ✅ 全文检索（SQLite FTS5）
- ✅ 知识图谱构建（基于 graphify）
- ✅ 主题查询（query topic）
- ✅ 自动索引（chunks + FTS5）
- ✅ 批量摄入模式
- ✅ Zotero 单篇与最近条目导入；本地模式可读取可访问的 PDF 附件

### 数据管理
- ✅ Registry 数据库（SQLite）
- ✅ 内容寻址存储（SHA256）
- ✅ 幂等处理流程
- ✅ 增量图谱更新

---

## 🚀 待开发功能清单

### P0 - 高优先级（核心功能增强）

#### 1. 引用解析器集成
**状态**：Open（`TD-REF-001`）
**本地工单**：`.scratch/reference-network-coverage/issues/01-integrate-reference-parser.md`

**目标**：建立论文间引用关系，增强知识图谱连接性

**技术方案**：
- 集成 GROBID（开源引用解析器）
- 解析论文参考文献列表
- 提取引用元数据（标题、作者、年份、DOI）
- 建立论文间引用边

**预期效果**：
- query related 功能从 33% 提升到 80%+
- 形成完整的引用网络
- 支持引用追踪和影响力分析

**工作量评估**：中等（2-3 周）

**依赖**：
- GROBID 服务部署
- 引用匹配算法（DOI/标题模糊匹配）
- 图谱数据结构扩展

---

### P1 - 中优先级（用户体验优化）

#### 2. Web UI 界面
**目标**：提供可视化界面，降低使用门槛

**功能点**：
- 论文列表查看和管理
- 图谱可视化（D3.js / Cytoscape.js）
- 交互式查询界面
- 论文阅读器（Markdown 渲染）

**工作量评估**：大（4-6 周）

---

#### 3. Zotero 集成增强
**当前基础**：已支持 `--zotero-key`、`--zotero-recent`，本地模式可导入可访问的 PDF 附件。

**目标**：补齐更细粒度的 Zotero 同步能力

**功能点**：
- 集合过滤
- 同步 Zotero 标签和笔记
- 双向同步支持

**工作量评估**：待按剩余功能重新评估

---

#### 3a. Zotero item key 溯源持久化
**状态**：Open（`TD-ZOTERO-001`）
**本地工单**：`.scratch/zotero-item-key-provenance/issues/01-persist-zotero-item-key.md`

**问题**：Canonical 的 `source` 当前只能记录来源类型和原始 URL，不能持久化唯一的 Zotero item key；同一 DOI 的条目调整后，无法在本地数据中直接审计其对应的 Zotero 条目。

**拟议解决方向**：
- 为 `PaperSource` 增加可选 `zotero_item_key` 字段，并在 Zotero 摄入、原位重建和迁移流程中写入。
- 对既有 Canonical 提供仅补齐溯源字段的迁移命令，不修改正文或 paper_id。
- 在 Registry/CLI 状态输出中展示该字段，并以 Zotero key + DOI 做一致性诊断。

**验收标准**：给定一个 Canonical 可反查其唯一 Zotero item key；条目附件更新后可在不改变 paper_id 的前提下完成原位重建。

**优先级**：P1（已记录，暂未实现）

---

#### 4. 导出功能增强
**目标**：支持多种格式导出

**功能点**：
- BibTeX 导出
- RIS 格式导出
- 知识图谱导出（GraphML, GEXF）
- 批量 PDF 打包导出

**工作量评估**：小（1 周）

---

### P2 - 低优先级（高级功能）

#### 5. 语义相似度计算
**目标**：基于嵌入向量计算论文相似度

**功能点**：
- 集成 Sentence Transformers
- 计算论文摘要/全文嵌入
- 相似度检索（向量数据库）
- 推荐相关论文

**工作量评估**：大（3-4 周）

---

#### 6. 协作功能
**目标**：多人协作管理论文库

**功能点**：
- 用户权限管理
- 论文标注和评论
- 共享论文集合
- 变更历史追踪

**工作量评估**：大（6-8 周）

---

#### 7. AI 辅助阅读
**目标**：利用 LLM 辅助论文理解

**功能点**：
- 论文摘要生成
- 关键概念提取
- 方法论对比分析
- Q&A 对话界面

**工作量评估**：中等（3-4 周）

---

#### 8. 高级图谱分析
**目标**：深度挖掘论文关系

**功能点**：
- 社区检测算法
- 影响力指标计算（PageRank）
- 研究趋势分析
- 知识演进可视化

**工作量评估**：大（4-5 周）

---

## 📋 技术债务

内部技术债的权威内容和状态统一维护在 `.scratch/`；总索引见 `.scratch/INDEX.md`。本路线图只保留摘要：

| ID | 状态 | 优先级 | 本地工单 |
|---|---|---:|---|
| `TD-REF-001` | open | P0 | `.scratch/reference-network-coverage/issues/01-integrate-reference-parser.md` |
| `TD-GRAPH-001` | open | P1 | `.scratch/graphify-scan-root-consistency/issues/01-enforce-scan-root-consistency.md` |
| `TD-ZOTERO-001` | open | P1 | `.scratch/zotero-item-key-provenance/issues/01-persist-zotero-item-key.md` |
| `TD-INGEST-001` | open | P2 | `.scratch/batch-ingest-memory/issues/01-profile-and-bound-memory.md` |
| `TD-PDF-001` | open | P2 | `.scratch/pdf-conversion-quality/issues/01-define-quality-gates.md` |
| `TD-REGISTRY-001` | open | P2 | `.scratch/performance-optimizations/issues/01-registry-reverse-index.md` |
| `TD-GRAPH-QUERY-001` | open | P2 | `.scratch/performance-optimizations/issues/02-graph-query-cache.md` |
| `TD-SEARCH-001` | open | P2 | `.scratch/performance-optimizations/issues/03-chinese-tokenization.md` |
| `TD-PROCESS-001` | open | P2 | `.scratch/legacy-debt-audit/issues/01-audit-legacy-debt-snapshot.md` |

---

## 🎨 设计原则

### 保持一致
- Canonical Markdown 作为唯一真相源
- 所有投影层可重建
- 幂等处理流程

### 渐进增强
- 核心功能优先稳定
- 高级功能作为可选模块
- 保持 CLI 优先，UI 为辅

### 开放生态
- 工具无关设计
- 标准格式优先
- API 友好

---

## 📅 版本规划

### v1.1 (Q3 2026)
- [ ] P0-1: 引用解析器集成
- [ ] P1-4: 导出功能增强
- [ ] 性能优化

### v1.2 (Q4 2026)
- [ ] P1-2: Web UI 界面
- [ ] P1-3: Zotero 集成

### v2.0 (2027)
- [ ] P2-5: 语义相似度计算
- [ ] P2-7: AI 辅助阅读
- [ ] P2-8: 高级图谱分析

---

## 🤝 贡献指南

欢迎社区贡献！优先级标记：
- **P0**: 核心功能，影响主要用户体验
- **P1**: 重要功能，提升易用性
- **P2**: 高级功能，面向特定场景

内部工程任务、spec 和技术债以本地 `.scratch/` tracker 为准。GitHub Issue 和 PR 仅作为外部问题反馈与代码贡献入口。

---

**最后更新**：2026-07-16
**维护者**：[@Chi-hong22](https://github.com/Chi-hong22)
