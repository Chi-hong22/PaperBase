# Zotero Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现从 Zotero 导入论文（结构化数据和 PDF）到 PaperBase 的功能

**Architecture:** 通过 Python 模块直接调用 zotero_mcp.tools 而非 CLI，创建 ZoteroAdapter 适配器，扩展 ingest 命令支持 --zotero-key、--zotero-collection、--zotero-recent 选项

**Tech Stack:** 
- pyzotero 1.13.2 (Zotero API 客户端)
- zotero_mcp 0.6.0 (工具模块)
- PaperBase adapters 模式 (参考 PaperFetchAdapter)

## Global Constraints

- Python 3.11+
- 保持与现有 ingest 流程的一致性（查重、状态机、索引更新）
- 支持 local_mode（连接本地 Zotero）和 API 模式（使用 Web API）
- 环境变量命名遵循 ZOTERO_ 前缀
- 不修改 PaperBase core schemas
- PDF 不可用时降级为仅元数据导入
- 所有文件使用 UTF-8 编码

---

## File Structure

**New files:**
- `src/paperbase/adapters/zotero_adapter.py` - Zotero 工具适配器，负责调用 zotero_mcp 模块
- `tests/unit/test_zotero_adapter.py` - ZoteroAdapter 单元测试
- `docs/integrations/zotero.md` - Zotero 集成使用文档

**Modified files:**
- `src/paperbase/cli/commands/ingest.py` - 添加 Zotero 导入选项和处理逻辑
- `CLAUDE.md` - 更新快速上手部分，添加 Zotero 导入示例
- `README.md` - 添加 Zotero 集成说明

---


### Task 1: 调研 Zotero MCP 接口并创建基础适配器

**Files:**
- Create: `src/paperbase/adapters/zotero_adapter.py`

**Interfaces:**
- Consumes: zotero_mcp.tools.retrieval (外部模块)
- Produces: 
  - `class ZoteroUnavailable(RuntimeError)` - Zotero 不可用异常
  - `@dataclass ZoteroItem` - Zotero 条目数据类
    - key: str
    - title: str
    - authors: list[str]
    - year: int
    - doi: str | None
    - abstract: str
    - item_type: str
    - url: str | None
    - has_pdf: bool
  - `class ZoteroAdapter` - 核心适配器
    - `__init__(local_mode: bool = True, api_key: str | None = None, library_id: str | None = None, library_type: str = "user")`
    - `fetch_item(item_key: str) -> ZoteroItem`
    - `list_recent(limit: int = 50) -> list[ZoteroItem]`

- [ ] **Step 1: 安装并测试 zotero_mcp 模块**

```bash
# 确认 zotero-mcp-server 已安装
pip show zotero-mcp-server

# 测试模块可用性
python -c "from zotero_mcp.tools import retrieval; from zotero_mcp.cli_standalone import CLIContext; print('zotero_mcp available')"
```

Expected: 显示版本信息和 "zotero_mcp available"

- [ ] **Step 2: 创建测试脚本验证接口**

创建 `test_zotero_interface.py`:

```python
"""临时测试脚本，验证 zotero_mcp 接口"""
from zotero_mcp.tools import retrieval
from zotero_mcp.cli_standalone import CLIContext

ctx = CLIContext(verbose=True)

# 测试获取最近条目
try:
    result = retrieval.get_recent(limit=3, ctx=ctx)
    print("get_recent result:", result[:200])
except Exception as e:
    print(f"Error (expected if Zotero not running): {e}")

# 测试获取集合
try:
    collections = retrieval.get_collections(limit=10, ctx=ctx)
    print("get_collections result:", collections[:200])
except Exception as e:
    print(f"Error: {e}")
```

- [ ] **Step 3: 运行测试脚本**

Run: `python test_zotero_interface.py`
Expected: 如果 Zotero 未运行则报错 "WinError 10061"，否则显示条目/集合数据

- [ ] **Step 4: 编写 ZoteroAdapter 基础结构**

创建 `src/paperbase/adapters/zotero_adapter.py`:

```python
"""Adapter for Zotero via zotero_mcp Python module.

zotero_mcp 作为已安装的 Python 包，通过模块导入调用。
输入：Zotero item key、collection key 或查询条件
输出：标准化的 ZoteroItem 数据结构
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ZoteroUnavailable(RuntimeError):
    """Raised when zotero_mcp module is not available or Zotero is not running."""


class ZoteroConnectionError(RuntimeError):
    """Raised when connection to Zotero fails."""


@dataclass(frozen=True)
class ZoteroItem:
    """Zotero 条目数据结构"""
    key: str
    title: str
    authors: list[str]
    year: int
    item_type: str
    doi: str | None = None
    abstract: str = ""
    url: str | None = None
    has_pdf: bool = False
    pdf_path: Path | None = None
    raw_data: dict[str, Any] = field(default_factory=dict)


def _check_zotero_available() -> bool:
    """Check if zotero_mcp module is available."""
    try:
        import zotero_mcp  # noqa: F401
        return True
    except ImportError:
        return False


def _parse_year(date_str: str | None) -> int:
    """Parse year from Zotero date string.
    
    Returns current year as fallback for missing/invalid dates.
    """
    from datetime import datetime
    
    current_year = datetime.now().year
    
    if not date_str:
        return current_year
    
    # Try to extract 4-digit year
    for token in date_str.replace("/", "-").replace(".", "-").split("-"):
        if token.isdigit() and len(token) == 4:
            year = int(token)
            if 1000 <= year <= current_year + 1:
                return year
    
    return current_year


# Import CLIContext from zotero_mcp instead of custom implementation
# This ensures compatibility with zotero_mcp's expected interface


class ZoteroAdapter:
    """Fetch Zotero items via zotero_mcp Python module.
    
    Supports two modes:
    - local_mode=True: Connect to local Zotero (requires Zotero running)
    - local_mode=False: Use Zotero Web API (requires api_key, library_id)
    """
    
    def __init__(
        self,
        local_mode: bool = True,
        api_key: str | None = None,
        library_id: str | None = None,
        library_type: str = "user",
        verbose: bool = False,
    ):
        if not _check_zotero_available():
            raise ZoteroUnavailable(
                "zotero_mcp module is not available. Install with:\n"
                "  pip install --user zotero-mcp-server"
            )
        
        self.local_mode = local_mode
        self.api_key = api_key
        self.library_id = library_id
        self.library_type = library_type
        self.verbose = verbose
        
        # Use zotero_mcp's CLIContext
        from zotero_mcp.cli_standalone import CLIContext
        self._ctx = CLIContext(verbose=verbose)
        
        # Setup environment for zotero_mcp
        if not local_mode:
            if not api_key or not library_id:
                raise ValueError(
                    "api_key and library_id are required for non-local mode"
                )
            os.environ["ZOTERO_API_KEY"] = api_key
            os.environ["ZOTERO_LIBRARY_ID"] = str(library_id)
            os.environ["ZOTERO_LIBRARY_TYPE"] = library_type
        else:
            # Local mode: set ZOTERO_LOCAL=1
            os.environ["ZOTERO_LOCAL"] = "1"
    
    def fetch_item(self, item_key: str) -> ZoteroItem:
        """Fetch a single Zotero item by key.
        
        Args:
            item_key: Zotero item key (e.g., "ABCD1234")
        
        Returns:
            ZoteroItem with normalized data
        
        Raises:
            ZoteroConnectionError: If connection fails
        """
        try:
            from zotero_mcp.tools import retrieval
        except ImportError as e:
            raise ZoteroUnavailable(f"Failed to import zotero_mcp.tools: {e}")
        
        try:
            # Get item metadata
            metadata_json = retrieval.get_item_metadata(
                item_key=item_key,
                include_abstract=True,
                format="json",
                ctx=self._ctx,
            )
            metadata = json.loads(metadata_json)
            
            # Get children (attachments)
            children_json = retrieval.get_item_children(
                item_key=item_key,
                ctx=self._ctx,
            )
            children = json.loads(children_json)
            
        except ConnectionRefusedError as e:
            raise ZoteroConnectionError(
                f"Cannot connect to Zotero. "
                f"Make sure Zotero is running (local mode) or API credentials are correct.\n"
                f"Error: {e}"
            )
        except Exception as e:
            raise ZoteroConnectionError(f"Failed to fetch item {item_key}: {e}")
        
        return self._parse_item(metadata, children)
    
    def list_recent(self, limit: int = 50) -> list[ZoteroItem]:
        """List recent Zotero items.
        
        Args:
            limit: Maximum number of items to return
        
        Returns:
            List of ZoteroItem
        
        Raises:
            ZoteroConnectionError: If connection fails
        """
        try:
            from zotero_mcp.tools import retrieval
        except ImportError as e:
            raise ZoteroUnavailable(f"Failed to import zotero_mcp.tools: {e}")
        
        try:
            result_json = retrieval.get_recent(
                limit=limit,
                ctx=self._ctx,
            )
            result = json.loads(result_json)
            
        except ConnectionRefusedError as e:
            raise ZoteroConnectionError(
                f"Cannot connect to Zotero. "
                f"Make sure Zotero is running (local mode) or API credentials are correct.\n"
                f"Error: {e}"
            )
        except Exception as e:
            raise ZoteroConnectionError(f"Failed to list recent items: {e}")
        
        items = []
        for item_data in result.get("items", []):
            # For list view, we don't fetch children yet (performance)
            items.append(self._parse_item(item_data, {}))
        
        return items
    
    def _parse_item(self, item_data: dict, children_data: dict | None = None) -> ZoteroItem:
        """Parse Zotero API response into ZoteroItem.
        
        Args:
            item_data: Item metadata from get_item_metadata
            children_data: Children data from get_item_children (optional)
        
        Returns:
            ZoteroItem
        """
        data = item_data.get("data", {})
        
        # Extract authors
        creators = data.get("creators", [])
        authors = []
        for creator in creators:
            if "name" in creator:
                authors.append(creator["name"])
            else:
                parts = []
                if creator.get("firstName"):
                    parts.append(creator["firstName"])
                if creator.get("lastName"):
                    parts.append(creator["lastName"])
                if parts:
                    authors.append(" ".join(parts))
        
        if not authors:
            authors = ["Unknown"]
        
        # Extract year
        year = _parse_year(data.get("date"))
        
        # Check for PDF attachments
        has_pdf = False
        pdf_path = None
        
        if children_data:
            for child in children_data.get("children", []):
                child_data = child.get("data", {})
                if child_data.get("contentType") == "application/pdf":
                    has_pdf = True
                    # Try to get attachment path (local mode only)
                    if self.local_mode:
                        try:
                            from zotero_mcp.tools import retrieval
                            path_result = retrieval.get_attachment_path(
                                item_key=child.get("key", ""),
                                ctx=self._ctx,
                            )
                            if path_result and path_result != "null":
                                path_data = json.loads(path_result)
                                if "path" in path_data:
                                    pdf_path = Path(path_data["path"])
                        except Exception:
                            pass  # Attachment path retrieval failed, continue without it
                    break
        
        return ZoteroItem(
            key=item_data.get("key", ""),
            title=data.get("title", "Untitled"),
            authors=authors,
            year=year,
            item_type=data.get("itemType", "unknown"),
            doi=data.get("DOI"),
            abstract=data.get("abstractNote", ""),
            url=data.get("url"),
            has_pdf=has_pdf,
            pdf_path=pdf_path,
            raw_data=item_data,
        )
```

- [ ] **Step 5: 提交基础适配器**

```bash
git add src/paperbase/adapters/zotero_adapter.py
git commit -m "feat(zotero): 添加 ZoteroAdapter 基础结构

Agent-Task: Zotero MCP 集成 - Task 1
Agent-Model: claude-fable-5
Agent-Decision: 使用 Python 模块导入而非 CLI 调用，性能更好且易于错误处理
Agent-Limitation: 当前仅实现 fetch_item 和 list_recent，后续任务添加集合和批量导入

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```


---

### Task 2: 扩展 ingest 命令支持 Zotero 导入

**Files:**
- Modify: `src/paperbase/cli/commands/ingest.py`

**Interfaces:**
- Consumes: 
  - `ZoteroAdapter` from Task 1
  - `ZoteroItem` from Task 1
  - Existing `_ingest_local_pdf()` function
- Produces:
  - `_ingest_from_zotero(ctx, item_key: str, no_graph: bool) -> None`
  - CLI options: `--zotero-key`, `--zotero-recent`

- [ ] **Step 1: 编写失败测试 - Zotero 导入函数不存在**

创建 `tests/integration/test_zotero_ingest.py`:

```python
"""Integration tests for Zotero ingest functionality."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from click.testing import CliRunner

from paperbase.cli.main import cli


def test_ingest_zotero_key_option_exists():
    """Test that --zotero-key option is available."""
    runner = CliRunner()
    result = runner.invoke(cli, ["ingest", "--help"])
    assert result.exit_code == 0
    assert "--zotero-key" in result.output


@patch("paperbase.cli.commands.ingest.ZoteroAdapter")
@patch("paperbase.cli.commands.ingest._ingest_local_pdf")
def test_ingest_from_zotero_with_pdf(mock_ingest_pdf, mock_adapter_class):
    """Test ingesting a Zotero item with PDF."""
    from paperbase.adapters.zotero_adapter import ZoteroItem
    
    # Mock ZoteroAdapter
    mock_adapter = Mock()
    mock_adapter_class.return_value = mock_adapter
    
    mock_item = ZoteroItem(
        key="ABCD1234",
        title="Test Paper",
        authors=["John Doe"],
        year=2024,
        item_type="journalArticle",
        doi="10.1234/test",
        abstract="Test abstract",
        has_pdf=True,
        pdf_path=Path("/tmp/test.pdf"),
    )
    mock_adapter.fetch_item.return_value = mock_item
    
    # Run ingest command
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(cli, [
            "ingest",
            "--zotero-key", "ABCD1234",
            "--no-graph",
        ], obj={"base_dir": Path.cwd()})
        
        # Should call fetch_item
        mock_adapter.fetch_item.assert_called_once_with("ABCD1234")
        
        # Should call _ingest_local_pdf with the PDF
        assert mock_ingest_pdf.called
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/integration/test_zotero_ingest.py::test_ingest_zotero_key_option_exists -v`
Expected: FAIL with "AssertionError: assert '--zotero-key' in ..."

- [ ] **Step 3: 实现 _ingest_from_zotero 函数**

在 `src/paperbase/cli/commands/ingest.py` 中添加（在 `_ingest_local_pdf` 函数之后）:

```python
def _ingest_from_zotero(ctx, item_key: str, no_graph: bool):
    """从 Zotero 摄入单篇论文"""
    console = Console()
    base_dir = ctx.obj["base_dir"]
    
    console.print(f"[cyan]从 Zotero 获取论文:[/cyan] {item_key}")
    
    try:
        # Import ZoteroAdapter
        from paperbase.adapters.zotero_adapter import (
            ZoteroAdapter,
            ZoteroUnavailable,
            ZoteroConnectionError,
        )
    except ImportError as e:
        console.print(f"[red]❌ Zotero adapter 不可用: {e}[/red]")
        console.print("[yellow]提示: 安装 zotero-mcp-server:[/yellow]")
        console.print("  pip install --user zotero-mcp-server")
        raise click.Abort()
    
    # Initialize adapter from config
    config_path = base_dir / "config" / "paperbase.yaml"
    local_mode = True
    api_key = None
    library_id = None
    library_type = "user"
    
    if config_path.exists():
        import yaml
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
            zotero_config = config.get("adapters", {}).get("zotero", {})
            local_mode = zotero_config.get("local_mode", True)
    
    # Override with environment variables
    api_key = os.getenv("ZOTERO_API_KEY", api_key)
    library_id = os.getenv("ZOTERO_LIBRARY_ID", library_id)
    library_type = os.getenv("ZOTERO_LIBRARY_TYPE", library_type)
    
    try:
        adapter = ZoteroAdapter(
            local_mode=local_mode,
            api_key=api_key,
            library_id=library_id,
            library_type=library_type,
        )
    except (ZoteroUnavailable, ValueError) as e:
        console.print(f"[red]❌ Zotero 初始化失败: {e}[/red]")
        raise click.Abort()
    
    # Fetch item from Zotero
    try:
        console.print("[yellow]1. 从 Zotero 获取论文信息...[/yellow]")
        item = adapter.fetch_item(item_key)
        console.print(f"   标题: {item.title}")
        console.print(f"   作者: {', '.join(item.authors)}")
        console.print(f"   年份: {item.year}")
        console.print(f"   DOI: {item.doi or 'N/A'}")
        console.print(f"   PDF: {'有' if item.has_pdf else '无'}")
    except ZoteroConnectionError as e:
        console.print(f"[red]❌ 无法连接 Zotero: {e}[/red]")
        if local_mode:
            console.print("[yellow]提示: 确保 Zotero 应用正在运行[/yellow]")
        else:
            console.print("[yellow]提示: 检查 API key 和 library ID 是否正确[/yellow]")
        raise click.Abort()
    
    # Check if PDF is available
    if item.has_pdf and item.pdf_path and item.pdf_path.exists():
        console.print(f"\n[yellow]2. 摄入 PDF 文件...[/yellow]")
        console.print(f"   路径: {item.pdf_path}")
        
        # Use existing PDF ingest flow
        _ingest_local_pdf(ctx, item.pdf_path, no_graph)
        
        console.print(f"\n[green]✓ 从 Zotero 成功导入论文（含 PDF）[/green]")
    else:
        # No PDF available - ingest metadata only
        console.print(f"\n[yellow]2. PDF 不可用，仅摄入元数据...[/yellow]")
        
        # Convert ZoteroItem to metadata dict compatible with normalize_paper
        metadata = {
            "title": item.title,
            "authors": item.authors,
            "year": item.year,
            "doi": item.doi,
            "abstract": item.abstract,
            "url": item.url,
        }
        
        # Generate paper_id
        if item.doi:
            paper_id = normalize_paper_id(item.doi)
        else:
            paper_id = f"zotero:{item.key}"
            paper_id = normalize_paper_id(paper_id)
        
        storage_id = generate_storage_id(paper_id)
        
        console.print(f"   paper_id: {paper_id}")
        console.print(f"   storage_id: {storage_id}")
        
        # Check duplicates
        registry_path = base_dir / "registry" / "papers.db"
        if registry_path.exists():
            registry = PaperRegistry(registry_path)
            
            if item.doi:
                existing = registry.find_by_doi(item.doi)
                if existing:
                    registry.close()
                    console.print(f"[yellow]⚠️  论文已存在（DOI 重复）[/yellow]")
                    console.print(f"   Paper ID: {existing['paper_id']}")
                    raise click.Abort()
            
            existing = registry.find_by_title(item.title)
            if existing:
                registry.close()
                console.print(f"[yellow]⚠️  论文可能已存在（标题相同）[/yellow]")
                console.print(f"   Paper ID: {existing['paper_id']}")
                raise click.Abort()
            
            registry.close()
        
        # Create directory structure
        paths = PaperPaths(storage_id=storage_id, base_dir=base_dir)
        paths.create_directories()
        
        # Create markdown from metadata
        candidate_md = f"""# {item.title}

## Abstract

{item.abstract or 'No abstract available.'}

## Metadata

- **Authors**: {', '.join(item.authors)}
- **Year**: {item.year}
- **DOI**: {item.doi or 'N/A'}
- **Item Type**: {item.item_type}
- **URL**: {item.url or 'N/A'}
- **Zotero Key**: {item.key}
"""
        
        # Normalize paper
        paper_metadata = normalize_paper(
            candidate_md=candidate_md,
            metadata=metadata,
            paper_id=paper_id,
            storage_id=storage_id,
            source_provider="zotero"
        )
        
        # Generate canonical markdown
        metadata_dict = paper_metadata.model_dump(mode="json", exclude_none=True)
        canonical_md = generate_canonical_markdown(metadata_dict, candidate_md)
        paths.paper_md.write_text(canonical_md, encoding="utf-8")
        canonical_sha256 = sha256_string(canonical_md)
        
        # Generate chunks
        chunks = generate_chunks(canonical_md, paper_id)
        if chunks:
            write_chunks_jsonl(chunks, paths.chunks_jsonl)
        
        # Save manifest
        manifest = create_manifest(paper_id, storage_id)
        manifest.state = PaperState.NORMALIZED
        manifest.canonical_md = CanonicalMD(
            path=f"../{storage_id}.md",
            sha256=canonical_sha256,
            schema_version="1.0"
        )
        manifest.pipeline = PipelineInfo(
            converter="zotero",
            converter_version="0.6.0",
            normalizer_version="1.0.0"
        )
        save_manifest(manifest, paths.manifest_json)
        
        # Register
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
            doi=item.doi
        )
        registry.close()
        
        console.print(f"\n[green]✓ 从 Zotero 成功导入论文（仅元数据）[/green]")
        console.print(f"   路径: {paths.paper_dir}")
        
        # Update index if needed
        if not no_graph:
            console.print("\n[yellow]更新全文检索索引...[/yellow]")
            try:
                from paperbase.core.search_engine import SearchEngine
                index_path = base_dir / "index" / "fts.db"
                library_path = base_dir / "library" / "papers"
                with SearchEngine(index_path, library_path) as engine:
                    engine.build_index()
                console.print("[green]✓ 索引更新完成[/green]")
            except Exception as e:
                console.print(f"[yellow]⚠ 索引更新失败: {e}[/yellow]")
```

- [ ] **Step 4: 添加导入语句**

在 `src/paperbase/cli/commands/ingest.py` 顶部添加:

```python
import os
```

- [ ] **Step 5: 添加 CLI 选项**

修改 `ingest` 命令装饰器（在第 234 行附近）:

```python
@click.command()
@click.argument("target", required=False)
@click.option("--file", "file_path", type=click.Path(exists=True, path_type=Path), help="本地 PDF 文件路径")
@click.option("--zotero-key", type=str, help="从 Zotero 导入指定 item key 的论文")
@click.option("--zotero-recent", type=int, help="从 Zotero 导入最近 N 篇论文")
@click.option("--no-graph", is_flag=True, help="跳过图谱更新")
@click.option("--batch", type=click.Path(exists=True, path_type=Path), help="批量摄入文件列表（每行一个路径、DOI、URL 或标题）")
@click.pass_context
def ingest(ctx, target: str | None, file_path: Path | None, zotero_key: str | None, zotero_recent: int | None, no_graph: bool, batch: Path | None):
    """摄入论文：本地 PDF、DOI/URL/title 或 Zotero"""
    console = Console()
    
    # 互斥检查
    input_sources = [bool(target), bool(file_path), bool(zotero_key), bool(zotero_recent), bool(batch)]
    if sum(input_sources) > 1:
        console.print("[red]❌ 只能指定一个输入源：TARGET、--file、--zotero-key、--zotero-recent 或 --batch[/red]")
        raise click.Abort()
    
    if sum(input_sources) == 0:
        console.print("[red]❌ 必须提供输入源[/red]")
        raise click.Abort()
    
    # Zotero 导入模式
    if zotero_key:
        _ingest_from_zotero(ctx, zotero_key, no_graph)
        return
    
    if zotero_recent:
        _ingest_zotero_recent(ctx, zotero_recent, no_graph)
        return
    
    # 批量模式
    if batch:
        _ingest_batch(ctx, batch, no_graph)
        return
    
    # (existing code continues...)
```

- [ ] **Step 6: 运行测试确认通过**

Run: `uv run pytest tests/integration/test_zotero_ingest.py::test_ingest_zotero_key_option_exists -v`
Expected: PASS

- [ ] **Step 7: 提交 ingest 命令扩展**

```bash
git add src/paperbase/cli/commands/ingest.py tests/integration/test_zotero_ingest.py
git commit -m "feat(zotero): 扩展 ingest 命令支持 Zotero 导入

添加 --zotero-key 选项导入单篇论文
支持有 PDF 和无 PDF 两种场景
复用现有查重和索引更新逻辑

Agent-Task: Zotero MCP 集成 - Task 2
Agent-Model: claude-fable-5
Agent-Decision: 有 PDF 时复用 _ingest_local_pdf，无 PDF 时降级为元数据导入
Agent-Limitation: 尚未实现 --zotero-recent 批量导入

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```


---

### Task 3: 实现批量导入功能

**Files:**
- Modify: `src/paperbase/cli/commands/ingest.py`

**Interfaces:**
- Consumes:
  - `ZoteroAdapter.list_recent()` from Task 1
  - `_ingest_from_zotero()` from Task 2
- Produces:
  - `_ingest_zotero_recent(ctx, limit: int, no_graph: bool) -> None`

- [ ] **Step 1: 实现 _ingest_zotero_recent 函数**

在 `src/paperbase/cli/commands/ingest.py` 中的 `_ingest_from_zotero` 函数之后添加:

```python
def _ingest_zotero_recent(ctx, limit: int, no_graph: bool):
    """从 Zotero 批量摄入最近的论文"""
    console = Console()
    base_dir = ctx.obj["base_dir"]
    
    console.print(f"[cyan]从 Zotero 批量导入最近 {limit} 篇论文[/cyan]\n")
    
    try:
        from paperbase.adapters.zotero_adapter import (
            ZoteroAdapter,
            ZoteroUnavailable,
            ZoteroConnectionError,
        )
    except ImportError as e:
        console.print(f"[red]❌ Zotero adapter 不可用: {e}[/red]")
        raise click.Abort()
    
    # Initialize adapter
    config_path = base_dir / "config" / "paperbase.yaml"
    local_mode = True
    api_key = None
    library_id = None
    library_type = "user"
    
    if config_path.exists():
        import yaml
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
            zotero_config = config.get("adapters", {}).get("zotero", {})
            local_mode = zotero_config.get("local_mode", True)
    
    api_key = os.getenv("ZOTERO_API_KEY", api_key)
    library_id = os.getenv("ZOTERO_LIBRARY_ID", library_id)
    library_type = os.getenv("ZOTERO_LIBRARY_TYPE", library_type)
    
    try:
        adapter = ZoteroAdapter(
            local_mode=local_mode,
            api_key=api_key,
            library_id=library_id,
            library_type=library_type,
        )
    except (ZoteroUnavailable, ValueError) as e:
        console.print(f"[red]❌ Zotero 初始化失败: {e}[/red]")
        raise click.Abort()
    
    # List recent items
    try:
        console.print("[yellow]获取 Zotero 论文列表...[/yellow]")
        items = adapter.list_recent(limit=limit)
        console.print(f"[green]✓ 找到 {len(items)} 篇论文[/green]\n")
    except ZoteroConnectionError as e:
        console.print(f"[red]❌ 无法连接 Zotero: {e}[/red]")
        raise click.Abort()
    
    if not items:
        console.print("[yellow]没有找到论文[/yellow]")
        return
    
    # Import each item
    success_count = 0
    skip_count = 0
    failed_count = 0
    
    for i, item in enumerate(items, 1):
        console.print(f"[cyan][{i}/{len(items)}] {item.title[:60]}...[/cyan]")
        
        try:
            # Check if already exists (by DOI or title)
            registry_path = base_dir / "registry" / "papers.db"
            if registry_path.exists():
                registry = PaperRegistry(registry_path)
                
                existing = None
                if item.doi:
                    existing = registry.find_by_doi(item.doi)
                if not existing:
                    existing = registry.find_by_title(item.title)
                
                registry.close()
                
                if existing:
                    console.print(f"  [dim]跳过（已存在）[/dim]")
                    skip_count += 1
                    continue
            
            # Import this item (skip graph update for batch)
            _ingest_from_zotero(ctx, item.key, no_graph=True)
            success_count += 1
            console.print(f"  [green]✓ 导入成功[/green]")
            
        except click.Abort:
            # User aborted or duplicate detected
            skip_count += 1
            console.print(f"  [dim]跳过[/dim]")
        except Exception as e:
            console.print(f"  [red]✗ 失败: {e}[/red]")
            failed_count += 1
        
        console.print()  # 空行分隔
    
    # Summary
    console.print(f"[cyan]批量导入完成[/cyan]")
    console.print(f"  成功: {success_count} 篇")
    console.print(f"  跳过: {skip_count} 篇")
    console.print(f"  失败: {failed_count} 篇")
    
    # Update index once at the end
    if not no_graph and success_count > 0:
        console.print("\n[yellow]更新全文检索索引...[/yellow]")
        try:
            from paperbase.core.search_engine import SearchEngine
            index_path = base_dir / "index" / "fts.db"
            library_path = base_dir / "library" / "papers"
            with SearchEngine(index_path, library_path) as engine:
                engine.build_index()
            console.print("[green]✓ 索引更新完成[/green]")
        except Exception as e:
            console.print(f"[yellow]⚠ 索引更新失败: {e}[/yellow]")
```

- [ ] **Step 2: 编写批量导入测试**

在 `tests/integration/test_zotero_ingest.py` 中添加:

```python
@patch("paperbase.cli.commands.ingest.ZoteroAdapter")
def test_ingest_zotero_recent(mock_adapter_class):
    """Test batch import from Zotero recent items."""
    from paperbase.adapters.zotero_adapter import ZoteroItem
    
    mock_adapter = Mock()
    mock_adapter_class.return_value = mock_adapter
    
    # Mock list_recent to return 3 items
    mock_items = [
        ZoteroItem(
            key=f"KEY{i}",
            title=f"Paper {i}",
            authors=["Author"],
            year=2024,
            item_type="journalArticle",
            has_pdf=False,
        )
        for i in range(3)
    ]
    mock_adapter.list_recent.return_value = mock_items
    
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(cli, [
            "ingest",
            "--zotero-recent", "3",
            "--no-graph",
        ], obj={"base_dir": Path.cwd()})
        
        # Should call list_recent
        mock_adapter.list_recent.assert_called_once_with(3)
```

- [ ] **Step 3: 运行测试**

Run: `uv run pytest tests/integration/test_zotero_ingest.py -v`
Expected: PASS for both tests

- [ ] **Step 4: 提交批量导入功能**

```bash
git add src/paperbase/cli/commands/ingest.py tests/integration/test_zotero_ingest.py
git commit -m "feat(zotero): 实现批量导入最近论文功能

添加 --zotero-recent N 选项
自动查重跳过已存在论文
批量导入后统一更新索引

Agent-Task: Zotero MCP 集成 - Task 3
Agent-Model: claude-fable-5
Agent-Decision: 批量导入时跳过单个图谱更新，最后统一更新索引
Agent-Limitation: 暂不支持按集合导入

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: 更新文档

**Files:**
- Create: `docs/integrations/zotero.md`
- Modify: `CLAUDE.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: All implementation from Tasks 1-3
- Produces: User-facing documentation

- [ ] **Step 1: 创建 Zotero 集成文档**

创建 `docs/integrations/zotero.md`:

```markdown
# Zotero 集成指南

PaperBase 支持从 Zotero 导入论文，包括元数据和 PDF 附件。

## 前提条件

安装 zotero-mcp-server:

```bash
pip install --user zotero-mcp-server
```

## 使用方式

### 1. 本地模式（推荐）

连接本地运行的 Zotero 应用。

**配置** (`config/paperbase.yaml`):

```yaml
adapters:
  zotero:
    enabled: true
    local_mode: true
```

**使用前确保**:
- Zotero 应用正在运行
- 论文已在 Zotero 中管理

**导入单篇论文**:

```bash
# 通过 item key 导入
paperbase ingest --zotero-key ABCD1234
```

**批量导入最近论文**:

```bash
# 导入最近 20 篇
paperbase ingest --zotero-recent 20
```

### 2. Web API 模式

通过 Zotero Web API 访问云端库。

**获取 API 凭证**:

1. 访问 https://www.zotero.org/settings/keys
2. 创建新的 API key
3. 记录 Library ID（在 Settings → Feeds/API 中查看）

**配置环境变量**:

```bash
export ZOTERO_API_KEY="your-api-key"
export ZOTERO_LIBRARY_ID="123456"
export ZOTERO_LIBRARY_TYPE="user"  # 或 "group"
```

**配置文件** (`config/paperbase.yaml`):

```yaml
adapters:
  zotero:
    enabled: true
    local_mode: false
```

**使用方式**:

```bash
# 与本地模式相同
paperbase ingest --zotero-key ABCD1234
paperbase ingest --zotero-recent 20
```

## 工作流程

### 导入带 PDF 的论文

1. PaperBase 从 Zotero 获取论文元数据
2. 检查是否有 PDF 附件
3. 复制 PDF 到 PaperBase 存储
4. 转换 PDF 为 Markdown
5. 规范化并索引

### 导入仅元数据的论文

1. PaperBase 从 Zotero 获取元数据
2. 生成基本 Markdown 文档
3. 规范化并索引
4. 后续可手动添加 PDF

## 查重机制

导入时自动检查:
- DOI 重复
- 标题重复

已存在的论文会被跳过。

## 常见问题

### 连接失败: "WinError 10061"

**原因**: Zotero 应用未运行（本地模式）

**解决**:
1. 启动 Zotero 应用
2. 等待几秒让本地 API 就绪
3. 重试导入命令

### "zotero_mcp module is not available"

**原因**: zotero-mcp-server 未安装

**解决**:

```bash
pip install --user zotero-mcp-server
```

### 找不到 PDF

**原因**: 
- PDF 附件不在 Zotero 库中
- 使用链接附件而非存储文件

**解决**:
- PaperBase 会自动降级为仅元数据导入
- 后续可手动添加 PDF: `paperbase ingest --file paper.pdf`

### 批量导入很慢

**原因**: 每篇论文都需要 PDF 转换和索引

**建议**:
- 使用 `--no-graph` 跳过实时索引
- 导入完成后手动运行: `paperbase index`

## 数据映射

| Zotero 字段 | PaperBase 字段 |
|------------|---------------|
| key | paper_id (fallback) |
| DOI | paper_id, doi |
| title | title |
| creators | authors |
| date | year |
| abstractNote | abstract |
| url | original_url |
| attachments (PDF) | source_pdf |

## 限制

- 本地模式需要 Zotero 应用运行
- Web API 模式的 PDF 下载取决于 Zotero 云存储
- 不支持按集合筛选导入（计划中）
- 不支持按标签筛选导入（计划中）

## 下一步

- [摄入命令详解](../cli/ingest.md)
- [配置文件说明](../configuration.md)
- [Paper Fetch 集成](./paper-fetch.md)
```

- [ ] **Step 2: 更新 CLAUDE.md**

在 `CLAUDE.md` 的 "快速上手" 部分（第 7 行之后）添加:

```markdown
4. **从 Zotero 导入论文**（需要先安装 zotero-mcp-server）
   ```bash
   # 安装 zotero-mcp-server（首次使用）
   pip install --user zotero-mcp-server
   
   # 导入单篇（需要 Zotero 应用运行）
   paperbase ingest --zotero-key ABCD1234
   
   # 批量导入最近 20 篇
   paperbase ingest --zotero-recent 20
   ```
```

- [ ] **Step 3: 更新 README.md**

在 README.md 的 "Features" 或 "Usage" 部分添加 Zotero 集成说明。查找合适位置后添加:

```markdown
### Zotero Integration

Import papers directly from your Zotero library:

```bash
# Single paper by item key
paperbase ingest --zotero-key ABCD1234

# Recent papers (batch)
paperbase ingest --zotero-recent 20
```

Supports both local Zotero (requires app running) and Web API modes. See [Zotero Integration Guide](docs/integrations/zotero.md) for details.
```

- [ ] **Step 4: 提交文档更新**

```bash
git add docs/integrations/zotero.md CLAUDE.md README.md
git commit -m "docs(zotero): 添加 Zotero 集成使用文档

详细说明本地模式和 Web API 模式配置
包含常见问题和故障排查
更新快速上手指南

Agent-Task: Zotero MCP 集成 - Task 4
Agent-Model: claude-fable-5
Agent-Decision: 优先说明本地模式（更简单），Web API 作为备选
Agent-Limitation: 暂未实现集合和标签筛选功能

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Self-Review Checklist

**1. Spec coverage:**
- ✅ 调研 Zotero MCP 接口 (Task 1)
- ✅ 创建 ZoteroAdapter (Task 1)
- ✅ 扩展 ingest 命令 (Task 2)
- ✅ 实现单篇导入 (Task 2)
- ✅ 实现批量导入 (Task 3)
- ✅ 配置文件适配 (Task 2, Task 3)
- ✅ 查重机制 (Task 2, Task 3)
- ✅ 文档更新 (Task 4)

**2. Placeholder scan:**
- ✅ 所有代码块完整
- ✅ 所有测试有具体实现
- ✅ 所有命令有预期输出

**3. Type consistency:**
- ✅ ZoteroItem 定义一致
- ✅ ZoteroAdapter 接口一致
- ✅ 函数签名匹配

**4. Missing features (documented as limitations):**
- 按集合导入（计划中）
- 按标签导入（计划中）
- Better BibTeX 支持（计划中）

---

