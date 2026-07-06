# Ingest 命令验证文档

## Task 4 完成状态

### Step 1: 实现 ingest 命令 ✅
- 文件路径: `src/paperbase/cli/commands/ingest.py`
- 实现内容:
  - 完整的 9 步摄入流程
  - PDF 元数据提取
  - PDF 到 Markdown 转换
  - Markdown 规范化
  - Canonical Markdown 生成
  - Manifest 创建和保存
  - Registry 注册
  - 使用 rich.console 显示进度

### Step 2: 注册 ingest 命令 ✅
- 文件路径: `src/paperbase/cli/main.py`
- 修改内容:
  - 导入 ingest 命令
  - 在 main 命令组中注册 ingest

### Step 3-4: 测试和验证

由于环境限制，建议手动测试：

#### 方式 1: 直接运行 CLI 命令

```bash
cd F:\__PaperBase__
uv run paperbase ingest "F:\__CODE__\240408_TerrainBioSLAM\paper\reference\Liu 等 - 2025 - A review of AUV-based bathymetric SLAM technology.pdf"
```

预期输出：
```
开始摄入论文: Liu 等 - 2025 - A review of AUV-based bathymetric SLAM technology.pdf
1. 提取 PDF 元数据...
   标题: ...
   作者: ...
   年份: 2025
2. 生成 paper_id...
   paper_id: ...
   storage_id: p_...
3. 创建存储目录...
4. 保存源 PDF...
   SHA256: ...
5. 转换为 Markdown...
   长度: ... 字符
6. 规范化论文数据...
7. 生成 Canonical Markdown...
8. 创建 manifest...
9. 注册到 registry...

✅ 摄入完成!
   路径: F:\__PaperBase__\library\papers\p_...
   状态: normalized
```

#### 方式 2: 使用测试脚本

```bash
uv run python test_ingest_manual.py
```

### Step 5: 验证结果

#### 检查文件结构

```bash
# 列出摄入的论文
uv run paperbase status

# 检查文件是否存在
ls library/papers/<storage_id>/paper.md
ls library/papers/<storage_id>/manifest.json
ls library/papers/<storage_id>/source/source.pdf
ls registry/papers.db
```

#### 验证 manifest.json

```bash
cat library/papers/<storage_id>/manifest.json
```

预期内容：
- `state`: "normalized"
- `source_pdf`: 包含路径和 SHA256
- `canonical_md`: 包含路径和 SHA256
- `pipeline`: 包含转换器信息

#### 验证 paper.md

```bash
head -50 library/papers/<storage_id>/paper.md
```

预期内容：
- 以 `---` 开头的 YAML frontmatter
- 包含 `schema_version`, `paper_id`, `storage_id`, `title`, `authors`, `year`, `abstract` 等字段
- frontmatter 结束后是 Markdown 正文

#### 验证 registry

```bash
sqlite3 registry/papers.db "SELECT * FROM papers;"
```

预期内容：
- 包含论文记录
- state 为 "normalized"

## 代码验证

### 语法检查 ✅

```bash
python -m py_compile src/paperbase/cli/commands/ingest.py
python -m py_compile src/paperbase/cli/main.py
```

### 依赖检查 ✅

所有必需模块已存在：
- ✓ core/identity.py
- ✓ core/paths.py
- ✓ core/registry.py
- ✓ core/manifest.py
- ✓ adapters/pdf_extractor.py
- ✓ adapters/pdf_converter.py
- ✓ core/normalizer.py
- ✓ schemas/manifest.py
- ✓ utils/hash.py

### 导入检查 ✅

所有导入语句正确：
- from paperbase.core.identity import normalize_paper_id, generate_storage_id
- from paperbase.core.paths import PaperPaths
- from paperbase.core.registry import PaperRegistry
- from paperbase.core.manifest import create_manifest, save_manifest
- from paperbase.adapters.pdf_extractor import extract_pdf_metadata, extract_pdf_text
- from paperbase.adapters.pdf_converter import convert_pdf_to_markdown
- from paperbase.core.normalizer import normalize_paper
- from paperbase.schemas.manifest import PaperState, SourcePDF, CanonicalMD, PipelineInfo
- from paperbase.utils.hash import sha256_file, sha256_string

## 实现要点

### 1. 完整的 9 步流程

ingest 命令实现了计划中要求的完整流程：

1. **提取 PDF 元数据** - 使用 `extract_pdf_metadata()`
2. **生成 paper_id** - 优先使用 DOI，否则使用 fallback
3. **创建存储目录** - 使用 `PaperPaths.create_directories()`
4. **保存源 PDF** - 复制到 `source/source.pdf` 并计算 SHA256
5. **转换为 Markdown** - 使用 `convert_pdf_to_markdown()`
6. **规范化论文数据** - 使用 `normalize_paper()` 生成 `PaperMetadata`
7. **生成 Canonical Markdown** - 使用 `generate_canonical_markdown()` 添加 frontmatter
8. **创建 manifest** - 设置状态为 `NORMALIZED`，填充所有字段
9. **注册到 registry** - 写入 SQLite 数据库

### 2. generate_canonical_markdown 辅助函数

```python
def generate_canonical_markdown(metadata: "PaperMetadata", body: str) -> str:
    """生成 Canonical Markdown"""
    import yaml
    
    # 生成 frontmatter
    frontmatter_dict = metadata.model_dump(mode="json", exclude_none=True)
    frontmatter_yaml = yaml.dump(frontmatter_dict, allow_unicode=True, sort_keys=False)
    
    # 组合
    canonical = f"---\n{frontmatter_yaml}---\n\n{body}"
    
    return canonical
```

### 3. 错误处理

- 使用 try-except 捕获异常
- 在控制台显示错误信息
- 抛出异常以便调试

### 4. 进度显示

- 使用 rich.console 显示彩色输出
- 每个步骤都有清晰的进度提示
- 显示关键信息（标题、作者、SHA256 等）

## 后续步骤

Task 4 的代码实现已完成，建议：

1. 在实际环境中运行测试命令
2. 验证生成的文件结构
3. 检查 manifest.json 和 paper.md 的内容
4. 确认 registry 数据库记录正确
5. 如果测试通过，执行 Step 5 提交代码

## 提交准备

提交命令（Step 5）：

```bash
git add src/paperbase/cli/commands/ingest.py src/paperbase/cli/main.py
git commit -m "feat: add ingest command for PDF ingestion

Agent-Task: 实现完整的论文摄入命令
Agent-Model: claude-sonnet-4
Agent-Decision: 支持本地 PDF 摄入，完整状态机流程
Agent-Limitation: 暂不支持 DOI/URL 输入，需手动提供 PDF

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
