# PaperBase Phase 2: 论文摄入流程实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现从本地 PDF 到 Canonical Markdown 的论文摄入流程，包括元数据提取、内容转换、规范化和状态管理。

**Architecture:** 基于 Phase 1 的基础设施，实现 Adapter 层和 Normalizer 层，支持 PDF → Candidate MD → Canonical MD 的转换流程。

**Tech Stack:**
- PyMuPDF (PDF 处理)
- markitdown (通用转换)
- pydantic v2 (数据验证)
- 已有：PaperRegistry, ManifestSchema, PaperPaths

## Global Constraints

- 继承 Phase 1 的所有约束
- 本地 PDF 优先，不依赖外部 API（paper-fetch 作为后续扩展）
- 使用 PyMuPDF 提取元数据和文本
- 使用 markitdown 作为 fallback 转换器
- 所有转换过程可追溯（保留 source 信息）
- 状态机严格遵循：DISCOVERED → RESOLVED → SOURCE_READY → CONVERTED → NORMALIZED
- 遵循 TDD：先写测试，再写实现

---

## Phase 2: 论文摄入流程

### Task 1: PDF 元数据提取器

**Files:**
- Create: `src/paperbase/adapters/pdf_extractor.py`
- Create: `tests/unit/test_pdf_extractor.py`
- Create: `tests/fixtures/sample.pdf` (从测试文献复制)

**Interfaces:**
- Consumes: Path (PDF 文件路径)
- Produces: 
  - `extract_pdf_metadata(pdf_path: Path) -> dict`
  - 返回：title, authors, year, doi (如果有)

- [ ] **Step 1: 复制测试 PDF**

```bash
cp "F:\__CODE__\240408_TerrainBioSLAM\paper\reference\Liu 等 - 2025 - A review of AUV-based bathymetric SLAM technology.pdf" tests/fixtures/sample_liu2025.pdf
```

Expected: 测试 fixture 已创建

- [ ] **Step 2: 编写 PDF 元数据提取测试**

创建 `tests/unit/test_pdf_extractor.py`：

```python
import pytest
from pathlib import Path
from paperbase.adapters.pdf_extractor import extract_pdf_metadata


@pytest.fixture
def sample_pdf():
    """测试 PDF 路径"""
    return Path("tests/fixtures/sample_liu2025.pdf")


def test_extract_pdf_metadata(sample_pdf):
    """测试提取 PDF 元数据"""
    if not sample_pdf.exists():
        pytest.skip("测试 PDF 不存在")
    
    metadata = extract_pdf_metadata(sample_pdf)
    
    assert "title" in metadata
    assert "authors" in metadata
    assert isinstance(metadata["authors"], list)


def test_extract_pdf_metadata_missing_file():
    """测试提取不存在的 PDF"""
    with pytest.raises(FileNotFoundError):
        extract_pdf_metadata(Path("nonexistent.pdf"))
```

- [ ] **Step 3: 运行测试确认失败**

```bash
uv run pytest tests/unit/test_pdf_extractor.py -v
```

Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 4: 添加 PyMuPDF 依赖**

在 `pyproject.toml` 中添加：

```toml
dependencies = [
    "pydantic>=2.13.0",
    "pyyaml>=6.0",
    "click>=8.1.0",
    "rich>=13.0.0",
    "pymupdf>=1.24.0",
]
```

- [ ] **Step 5: 安装依赖**

```bash
uv sync
```

Expected: PyMuPDF 安装成功

- [ ] **Step 6: 实现 PDF 元数据提取器**

创建 `src/paperbase/adapters/pdf_extractor.py`：

```python
"""PDF 元数据提取器

使用 PyMuPDF 提取 PDF 元数据和文本
"""

from pathlib import Path
import pymupdf


def extract_pdf_metadata(pdf_path: Path) -> dict:
    """
    提取 PDF 元数据
    
    Returns:
        dict: {
            "title": str | None,
            "authors": list[str],
            "year": int | None,
            "doi": str | None,
            "subject": str | None,
            "keywords": str | None
        }
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF 文件不存在: {pdf_path}")
    
    doc = pymupdf.open(pdf_path)
    metadata = doc.metadata or {}
    
    # 提取作者列表
    authors = []
    if metadata.get("author"):
        # 处理多种作者分隔符
        author_str = metadata["author"]
        for sep in [";", ",", " and ", "，"]:
            if sep in author_str:
                authors = [a.strip() for a in author_str.split(sep) if a.strip()]
                break
        if not authors:
            authors = [author_str.strip()]
    
    # 提取年份
    year = None
    if metadata.get("creationDate"):
        # PyMuPDF 日期格式：D:YYYYMMDD...
        date_str = metadata["creationDate"]
        if date_str.startswith("D:") and len(date_str) >= 10:
            try:
                year = int(date_str[2:6])
            except ValueError:
                pass
    
    # 提取 DOI（从 subject 或 keywords 中）
    doi = None
    for field in ["subject", "keywords"]:
        if field in metadata and metadata[field]:
            text = metadata[field].lower()
            if "doi" in text or "10." in text:
                # 简单的 DOI 提取
                import re
                match = re.search(r'10\.\d{4,}/[^\s]+', text)
                if match:
                    doi = match.group(0)
                    break
    
    doc.close()
    
    return {
        "title": metadata.get("title"),
        "authors": authors,
        "year": year,
        "doi": doi,
        "subject": metadata.get("subject"),
        "keywords": metadata.get("keywords"),
    }


def extract_pdf_text(pdf_path: Path, max_pages: int = 10) -> str:
    """
    提取 PDF 文本内容
    
    Args:
        pdf_path: PDF 文件路径
        max_pages: 最多提取页数（用于摘要提取）
    
    Returns:
        str: 文本内容
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF 文件不存在: {pdf_path}")
    
    doc = pymupdf.open(pdf_path)
    text_parts = []
    
    for page_num in range(min(max_pages, len(doc))):
        page = doc[page_num]
        text_parts.append(page.get_text())
    
    doc.close()
    
    return "\n\n".join(text_parts)
```

- [ ] **Step 7: 运行测试确认通过**

```bash
uv run pytest tests/unit/test_pdf_extractor.py -v
```

Expected: 测试通过

- [ ] **Step 8: 提交 PDF 提取器**

```bash
git add src/paperbase/adapters/pdf_extractor.py tests/unit/test_pdf_extractor.py tests/fixtures/ pyproject.toml
git commit -m "feat: add PDF metadata extractor

Agent-Task: 实现 PDF 元数据和文本提取
Agent-Model: claude-sonnet-4-6
Agent-Decision: 使用 PyMuPDF 提取元数据，支持多种作者分隔符和 DOI 提取
Agent-Limitation: DOI 提取仅支持简单正则，复杂格式可能失败

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

Expected: 成功提交

---

### Task 2: PDF 到 Markdown 转换器

**Files:**
- Create: `src/paperbase/adapters/pdf_converter.py`
- Create: `tests/unit/test_pdf_converter.py`

**Interfaces:**
- Consumes: Path (PDF 文件路径)
- Produces:
  - `convert_pdf_to_markdown(pdf_path: Path) -> str`
  - 返回 Markdown 文本

- [ ] **Step 1: 添加 markitdown 依赖**

在 `pyproject.toml` 中添加：

```toml
dependencies = [
    # ... existing
    "markitdown>=0.0.1",
]
```

- [ ] **Step 2: 安装依赖**

```bash
uv sync
```

- [ ] **Step 3: 编写转换器测试**

创建 `tests/unit/test_pdf_converter.py`：

```python
import pytest
from pathlib import Path
from paperbase.adapters.pdf_converter import convert_pdf_to_markdown


@pytest.fixture
def sample_pdf():
    return Path("tests/fixtures/sample_liu2025.pdf")


def test_convert_pdf_to_markdown(sample_pdf):
    """测试 PDF 转 Markdown"""
    if not sample_pdf.exists():
        pytest.skip("测试 PDF 不存在")
    
    markdown = convert_pdf_to_markdown(sample_pdf)
    
    assert isinstance(markdown, str)
    assert len(markdown) > 100  # 至少有一些内容
```

- [ ] **Step 4: 运行测试确认失败**

```bash
uv run pytest tests/unit/test_pdf_converter.py -v
```

Expected: FAIL

- [ ] **Step 5: 实现 PDF 转换器**

创建 `src/paperbase/adapters/pdf_converter.py`：

```python
"""PDF 到 Markdown 转换器"""

from pathlib import Path
from markitdown import MarkItDown


def convert_pdf_to_markdown(pdf_path: Path) -> str:
    """
    将 PDF 转换为 Markdown
    
    使用 markitdown 进行转换
    
    Args:
        pdf_path: PDF 文件路径
    
    Returns:
        str: Markdown 文本
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF 文件不存在: {pdf_path}")
    
    md = MarkItDown()
    result = md.convert(str(pdf_path))
    
    return result.text_content
```

- [ ] **Step 6: 运行测试确认通过**

```bash
uv run pytest tests/unit/test_pdf_converter.py -v
```

Expected: 测试通过

- [ ] **Step 7: 提交转换器**

```bash
git add src/paperbase/adapters/pdf_converter.py tests/unit/test_pdf_converter.py pyproject.toml
git commit -m "feat: add PDF to Markdown converter

Agent-Task: 实现 PDF 到 Markdown 转换
Agent-Model: claude-sonnet-4-6
Agent-Decision: 使用 markitdown 作为通用转换器
Agent-Limitation: 转换质量依赖 markitdown，复杂 PDF 可能格式不佳

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

Expected: 成功提交

---

### Task 3: Markdown 规范化器

**Files:**
- Create: `src/paperbase/core/normalizer.py`
- Create: `tests/unit/test_normalizer.py`

**Interfaces:**
- Consumes: 候选 Markdown + 元数据 dict
- Produces:
  - `normalize_paper(candidate_md: str, metadata: dict, paper_id: str, storage_id: str) -> PaperMetadata`
  - 返回规范化的 PaperMetadata

- [ ] **Step 1: 编写 normalizer 测试**

创建 `tests/unit/test_normalizer.py`：

```python
import pytest
from paperbase.core.normalizer import normalize_paper, extract_abstract


def test_normalize_paper_minimal():
    """测试最小规范化"""
    candidate_md = """
# Test Paper

## Abstract
This is a test abstract.

## Introduction
Some content here.
"""
    
    metadata = {
        "title": "Test Paper",
        "authors": ["John Smith"],
        "year": 2025
    }
    
    result = normalize_paper(
        candidate_md=candidate_md,
        metadata=metadata,
        paper_id="doi:10.1234/test",
        storage_id="p_test123"
    )
    
    assert result.paper_id == "doi:10.1234/test"
    assert result.title == "Test Paper"
    assert len(result.authors) == 1
    assert result.year == 2025
    assert "test abstract" in result.abstract.lower()


def test_extract_abstract():
    """测试摘要提取"""
    text = """
# Title

## Abstract
This is the abstract content.
It spans multiple lines.

## Introduction
This is not abstract.
"""
    
    abstract = extract_abstract(text)
    assert "abstract content" in abstract.lower()
    assert "introduction" not in abstract.lower()
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/unit/test_normalizer.py -v
```

Expected: FAIL

- [ ] **Step 3: 实现 normalizer**

创建 `src/paperbase/core/normalizer.py`：

```python
"""Markdown 规范化器

将候选 Markdown 转换为 Canonical Markdown
"""

import re
from datetime import datetime
from paperbase.schemas.paper import (
    PaperMetadata,
    PaperAuthor,
    PaperSource,
    PaperProvenance,
)
from paperbase.utils.hash import sha256_string


def extract_abstract(text: str) -> str:
    """
    从文本中提取摘要
    
    查找 Abstract 标题后的内容，直到下一个标题
    """
    # 查找 Abstract 部分
    abstract_pattern = r'##?\s*Abstract\s*\n(.*?)(?=\n##|\Z)'
    match = re.search(abstract_pattern, text, re.IGNORECASE | re.DOTALL)
    
    if match:
        abstract = match.group(1).strip()
        # 清理多余空白
        abstract = re.sub(r'\n+', ' ', abstract)
        abstract = re.sub(r'\s+', ' ', abstract)
        return abstract
    
    # Fallback: 取前 500 字符
    lines = text.split('\n')
    content_lines = [l for l in lines if l.strip() and not l.startswith('#')]
    if content_lines:
        return ' '.join(content_lines[:5])[:500]
    
    return "No abstract available"


def normalize_paper(
    candidate_md: str,
    metadata: dict,
    paper_id: str,
    storage_id: str,
    source_provider: str = "pdf-local"
) -> PaperMetadata:
    """
    规范化论文数据
    
    Args:
        candidate_md: 候选 Markdown 文本
        metadata: 从 PDF 提取的元数据
        paper_id: 规范化的 paper_id
        storage_id: 存储 ID
        source_provider: 来源提供者
    
    Returns:
        PaperMetadata: 规范化的论文元数据
    """
    # 提取摘要
    abstract = extract_abstract(candidate_md)
    
    # 构建作者列表
    authors = []
    for author_name in metadata.get("authors", []):
        authors.append(PaperAuthor(name=author_name))
    
    if not authors:
        authors = [PaperAuthor(name="Unknown")]
    
    # 构建 source
    source = PaperSource(
        discovery="local",
        fulltext_provider=source_provider
    )
    
    # 构建 provenance
    now = datetime.now().isoformat() + "Z"
    provenance = PaperProvenance(
        ingested_at=now,
        converter={"name": source_provider, "version": "1.0.0"},
        normalizer={"name": "paperbase-normalizer", "version": "1.0.0"},
        canonical_content_sha256=sha256_string(candidate_md)
    )
    
    # 构建 PaperMetadata
    paper = PaperMetadata(
        schema_version="1.0",
        paper_id=paper_id,
        storage_id=storage_id,
        title=metadata.get("title") or "Untitled",
        authors=authors,
        year=metadata.get("year") or 2025,
        abstract=abstract,
        source=source,
        provenance=provenance
    )
    
    return paper
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/unit/test_normalizer.py -v
```

Expected: 测试通过

- [ ] **Step 5: 提交 normalizer**

```bash
git add src/paperbase/core/normalizer.py tests/unit/test_normalizer.py
git commit -m "feat: add Markdown normalizer

Agent-Task: 实现 Canonical Markdown 规范化器
Agent-Model: claude-sonnet-4-6
Agent-Decision: 使用正则提取摘要，构建完整 PaperMetadata
Agent-Limitation: 摘要提取依赖标题识别，格式不规范可能失败

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

Expected: 成功提交

---

### Task 4: 实现 ingest 命令

**Files:**
- Create: `src/paperbase/cli/commands/ingest.py`
- Update: `src/paperbase/cli/main.py`
- Create: `tests/integration/test_ingest.py`

**Interfaces:**
- Consumes: PDF 文件路径
- Produces: 完整的论文摄入（DISCOVERED → NORMALIZED）

- [ ] **Step 1: 实现 ingest 命令**

创建 `src/paperbase/cli/commands/ingest.py`：

```python
"""ingest 命令实现"""

import click
from rich.console import Console
from pathlib import Path
from paperbase.core.identity import normalize_paper_id, generate_storage_id
from paperbase.core.paths import PaperPaths
from paperbase.core.registry import PaperRegistry
from paperbase.core.manifest import create_manifest, save_manifest
from paperbase.adapters.pdf_extractor import extract_pdf_metadata, extract_pdf_text
from paperbase.adapters.pdf_converter import convert_pdf_to_markdown
from paperbase.core.normalizer import normalize_paper
from paperbase.schemas.manifest import PaperState, SourcePDF, CanonicalMD, PipelineInfo
from paperbase.utils.hash import sha256_file, sha256_string
import shutil
import yaml


@click.command()
@click.argument("pdf_path", type=click.Path(exists=True, path_type=Path))
@click.pass_context
def ingest(ctx, pdf_path: Path):
    """摄入论文 PDF"""
    console = Console()
    base_dir = ctx.obj["base_dir"]
    
    console.print(f"[cyan]开始摄入论文:[/cyan] {pdf_path.name}")
    
    try:
        # Step 1: 提取元数据
        console.print("[yellow]1. 提取 PDF 元数据...[/yellow]")
        metadata = extract_pdf_metadata(pdf_path)
        console.print(f"   标题: {metadata.get('title', 'N/A')}")
        console.print(f"   作者: {', '.join(metadata.get('authors', [])) or 'N/A'}")
        console.print(f"   年份: {metadata.get('year', 'N/A')}")
        
        # Step 2: 生成 paper_id
        console.print("[yellow]2. 生成 paper_id...[/yellow]")
        if metadata.get("doi"):
            paper_id = normalize_paper_id(metadata["doi"])
        else:
            # Fallback: 使用文件名
            paper_id = f"fallback:{pdf_path.stem}"
            paper_id = normalize_paper_id(paper_id)
        
        storage_id = generate_storage_id(paper_id)
        console.print(f"   paper_id: {paper_id}")
        console.print(f"   storage_id: {storage_id}")
        
        # Step 3: 创建目录结构
        console.print("[yellow]3. 创建存储目录...[/yellow]")
        paths = PaperPaths(storage_id=storage_id, base_dir=base_dir)
        paths.create_directories()
        
        # Step 4: 复制 PDF 到 source
        console.print("[yellow]4. 保存源 PDF...[/yellow]")
        shutil.copy2(pdf_path, paths.source_pdf)
        pdf_sha256 = sha256_file(paths.source_pdf)
        console.print(f"   SHA256: {pdf_sha256[:16]}...")
        
        # Step 5: 转换为 Markdown
        console.print("[yellow]5. 转换为 Markdown...[/yellow]")
        candidate_md = convert_pdf_to_markdown(pdf_path)
        console.print(f"   长度: {len(candidate_md)} 字符")
        
        # Step 6: 规范化
        console.print("[yellow]6. 规范化论文数据...[/yellow]")
        paper_metadata = normalize_paper(
            candidate_md=candidate_md,
            metadata=metadata,
            paper_id=paper_id,
            storage_id=storage_id,
            source_provider="markitdown"
        )
        
        # Step 7: 生成 Canonical Markdown
        console.print("[yellow]7. 生成 Canonical Markdown...[/yellow]")
        canonical_md = generate_canonical_markdown(paper_metadata, candidate_md)
        paths.paper_md.write_text(canonical_md, encoding="utf-8")
        canonical_sha256 = sha256_string(canonical_md)
        
        # Step 8: 创建 manifest
        console.print("[yellow]8. 创建 manifest...[/yellow]")
        manifest = create_manifest(paper_id, storage_id)
        manifest.state = PaperState.NORMALIZED
        manifest.source_pdf = SourcePDF(
            path="./source/source.pdf",
            sha256=pdf_sha256,
            acquired_at=paper_metadata.provenance.ingested_at
        )
        manifest.canonical_md = CanonicalMD(
            path="./paper.md",
            sha256=canonical_sha256,
            schema_version="1.0"
        )
        manifest.pipeline = PipelineInfo(
            converter="markitdown",
            converter_version="0.0.1",
            normalizer_version="1.0.0"
        )
        save_manifest(manifest, paths.manifest_json)
        
        # Step 9: 注册到 registry
        console.print("[yellow]9. 注册到 registry...[/yellow]")
        registry_path = base_dir / "registry" / "papers.db"
        registry_path.parent.mkdir(exist_ok=True)
        registry = PaperRegistry(registry_path)
        registry.register_paper(
            paper_id=paper_id,
            storage_id=storage_id,
            state=PaperState.NORMALIZED,
            title=paper_metadata.title,
            authors=[a.name for a in paper_metadata.authors],
            year=paper_metadata.year,
            doi=metadata.get("doi")
        )
        registry.close()
        
        console.print(f"\n[green]✅ 摄入完成![/green]")
        console.print(f"   路径: {paths.paper_dir}")
        console.print(f"   状态: {PaperState.NORMALIZED.value}")
        
    except Exception as e:
        console.print(f"\n[red]❌ 摄入失败: {e}[/red]")
        raise


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

- [ ] **Step 2: 注册 ingest 命令**

在 `src/paperbase/cli/main.py` 中添加：

```python
from paperbase.cli.commands.ingest import ingest

# ... existing code ...
main.add_command(ingest)
```

- [ ] **Step 3: 测试 ingest 命令**

```bash
uv run paperbase ingest "F:\__CODE__\240408_TerrainBioSLAM\paper\reference\Liu 等 - 2025 - A review of AUV-based bathymetric SLAM technology.pdf"
```

Expected: 成功摄入论文

- [ ] **Step 4: 验证结果**

```bash
uv run paperbase status
```

Expected: 显示已摄入的论文

- [ ] **Step 5: 提交 ingest 命令**

```bash
git add src/paperbase/cli/commands/ingest.py src/paperbase/cli/main.py
git commit -m "feat: add ingest command for PDF ingestion

Agent-Task: 实现完整的论文摄入命令
Agent-Model: claude-sonnet-4-6
Agent-Decision: 支持本地 PDF 摄入，完整状态机流程
Agent-Limitation: 暂不支持 DOI/URL 输入，需手动提供 PDF

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

Expected: 成功提交

---

## 验收标准

完成以上所有 Task 后，项目应满足：

### 功能完整性
- [ ] 可以从本地 PDF 提取元数据
- [ ] 可以将 PDF 转换为 Markdown
- [ ] 可以规范化 Markdown 为 Canonical 格式
- [ ] `paperbase ingest <pdf>` 命令可用
- [ ] 摄入的论文可通过 `paperbase status` 查看

### 文件结构
- [ ] `library/papers/<storage_id>/paper.md` 存在
- [ ] `library/papers/<storage_id>/manifest.json` 存在
- [ ] `library/papers/<storage_id>/source/source.pdf` 存在
- [ ] `registry/papers.db` 包含论文记录

### 状态管理
- [ ] manifest.json 的 state 为 "normalized"
- [ ] registry 中的 state 为 "normalized"
- [ ] paper.md 的 frontmatter 符合 PaperMetadata schema

### 测试覆盖
- [ ] PDF 提取器测试通过
- [ ] PDF 转换器测试通过
- [ ] Normalizer 测试通过
- [ ] 集成测试通过

---

## 后续工作

Phase 2 完成后，后续开发方向：

### Phase 3: 图谱集成
- 实现 Graphify adapter
- 实现 `paperbase graph update` 命令
- 将 NORMALIZED 状态推进到 GRAPHED

### Phase 4: 增强摄入
- 集成 paper-fetch-skill（支持 DOI/URL 输入）
- 支持批量摄入
- 支持增量更新

### Phase 5: 搜索和查询
- 实现全文检索
- 集成 Zotero MCP
- 实现语义搜索
