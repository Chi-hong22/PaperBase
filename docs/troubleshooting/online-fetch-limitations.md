# 在线获取论文的局限性

## 问题描述

使用 `paperbase ingest "doi:xxx"` 或在线 URL 摄入论文时，部分论文**无法获取全文**，只能获取到元数据或摘要。

## 根本原因

### paper-fetch 的获取策略

1. **优先尝试开放获取源**
   - Unpaywall API
   - arXiv 预印本服务器
   - PubMed Central

2. **降级到元数据获取**
   - 当全文不可获取时，回退到 CrossRef API
   - 只获取标题、作者、摘要、引用文献等元数据

3. **付费墙限制**
   - SAGE Journals、Elsevier、IEEE 等出版商的付费论文
   - 无机构访问权限时无法突破付费墙

## 典型表现

### 摘要模式（abstract_only）

在 Markdown frontmatter 中标记为：

```yaml
quality:
  fulltext: false
  metadata_complete: true
  references_parsed: true
  needs_review: true
```

在 Markdown 第二部分（paper-fetch 元数据）中标记为：

```yaml
has_fulltext: false
content_kind: "abstract_only"
has_abstract: true
token_estimate: 377  # 仅摘要的 token 数
```

**正文内容**：只包含摘要和引用文献列表

---

### 元数据模式（metadata_only）

```yaml
has_fulltext: false
content_kind: "metadata_only"
has_abstract: false
token_estimate: 0  # 无正文内容
```

**正文内容**：只包含引用文献列表，甚至摘要也缺失（`abstract: No abstract available`）

---

## 影响范围

### 功能受限

1. **知识提取不完整**
   - 无法提取论文核心方法论
   - 无法提取实验细节和结果
   - 图表、公式全部缺失

2. **图谱构建受限**
   - 只能通过引用文献建立连接
   - 无法提取概念、技术、方法论节点
   - 语义关联能力大幅下降

3. **搜索效果下降**
   - 只能匹配标题和摘要
   - 无法进行深层语义检索

### 仍可用的功能

1. **引用关系管理** ✓
2. **基础元数据检索** ✓
3. **通过共享引用发现关联** ✓

---

## 解决方案

### 推荐方案：使用 PDF 本地导入

```bash
# 1. 通过机构访问权限下载 PDF
# 2. 本地导入
paperbase ingest --file /path/to/paper.pdf
```

**优势**：
- ✅ 完整全文内容
- ✅ 保留图表和公式
- ✅ 知识图谱构建完整
- ✅ 不受付费墙限制

---

### 补救方案：为已摄入论文补全全文

如果已经通过在线方式摄入了元数据，后续获得 PDF 后可以：

1. **重新摄入（推荐）**
   ```bash
   # 删除旧记录
   paperbase remove <paper_id>
   
   # 用 PDF 重新摄入
   paperbase ingest --file paper.pdf
   ```

2. **手动替换**（高级用户）
   - 用 paper-fetch 重新转换 PDF
   - 手动替换 `library/papers/<storage_id>.md`
   - 更新 `manifest.json` 中的 `canonical_md.sha256`
   - 运行 `paperbase sync` 重建索引

---

## 最佳实践

### 摄入策略建议

1. **优先使用 PDF 导入**
   - 对于核心论文、重要参考文献
   - 需要深度阅读和知识提取的论文

2. **在线摄入适用场景**
   - 快速构建初始论文库
   - 批量导入大量引用文献
   - 探索性调研阶段

3. **混合模式**
   - 先用在线方式快速摄入，了解论文概况
   - 筛选重要论文后，补充 PDF 全文

### 识别元数据论文

```bash
# 查询所有无全文的论文（需要通过 Registry 查询）
# 检查 frontmatter 中的 quality.fulltext 字段
```

---

## 技术细节

### paper-fetch 降级流程

```
在线源（DOI/arXiv/URL）
    ↓
尝试 Unpaywall API
    ↓ 失败
尝试预印本服务器
    ↓ 失败
尝试出版商直接抓取（HTML/XML）
    ↓ 失败（403/付费墙）
回退到 CrossRef API（元数据）
    ↓
返回 metadata_only 或 abstract_only
```

### 元数据字段说明

| 字段 | 值 | 含义 |
|------|-----|------|
| `has_fulltext` | `false` | 无全文 |
| `content_kind` | `"metadata_only"` | 只有元数据 |
| `content_kind` | `"abstract_only"` | 有摘要无正文 |
| `content_kind` | `"fulltext"` | 完整全文 |
| `token_estimate` | `0` | 无正文内容 |
| `token_estimate` | `>0` | 有部分内容（摘要） |

---

## 相关文档

- [摄入论文](../README.md#摄入论文)
- [PDF 导入指南](../README.md#本地-pdf-导入)
- [知识图谱构建](../graph-update-strategy.md)

---

## FAQ

### Q: 如何判断论文是否获取了全文？

**A**: 检查 Markdown 文件：
1. 打开 `library/papers/<storage_id>.md`
2. 查看第二个 YAML 块中的 `has_fulltext` 和 `content_kind` 字段
3. 查看正文长度（只有摘要和引用则为元数据模式）

### Q: 为什么有些论文有摘要但无正文？

**A**: 出版商 API（如 CrossRef）提供摘要字段，但全文需要付费访问。paper-fetch 尽可能获取摘要，但无法突破付费墙。

### Q: 元数据论文对知识图谱有用吗？

**A**: 有限有用。可以通过引用关系建立连接，但无法提取概念和方法论节点。推荐用 PDF 重新摄入以获得完整图谱。

### Q: 可以批量检测哪些论文缺失全文吗？

**A**: 目前需要手动检查。未来版本会添加 `paperbase doctor --check-fulltext` 功能。
