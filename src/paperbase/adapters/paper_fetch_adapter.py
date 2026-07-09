"""Adapter boundary for Dictation354/paper-fetch-skill.

paper-fetch-skill 作为外部黑盒工具，通过 CLI 调用。
PaperBase 不关心其安装方式（MCP/Python包/全局命令），只关心输入输出契约。
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class PaperFetchUnavailable(RuntimeError):
    """Raised when paper-fetch CLI is not available."""


@dataclass(frozen=True)
class FetchedReference:
    raw: str
    doi: str | None = None
    title: str | None = None
    year: str | None = None


@dataclass(frozen=True)
class FetchedAsset:
    kind: str
    heading: str
    caption: str | None = None
    source_path: Path | None = None
    original_url: str | None = None


@dataclass(frozen=True)
class FetchedPaper:
    query: str
    title: str
    authors: list[str]
    year: int
    markdown: str
    doi: str | None = None
    abstract: str = ""
    provider: str = "paper-fetch"
    original_url: str | None = None
    has_fulltext: bool = False
    content_kind: str = "metadata_only"
    warnings: list[str] = field(default_factory=list)
    source_trail: list[str] = field(default_factory=list)
    references: list[FetchedReference] = field(default_factory=list)
    assets: list[FetchedAsset] = field(default_factory=list)


def _check_paper_fetch_available() -> bool:
    """Check if paper-fetch CLI is available in PATH."""
    return shutil.which("paper-fetch") is not None


def _call_paper_fetch_cli(query: str) -> dict[str, Any]:
    """Call paper-fetch CLI and return parsed JSON result.

    Args:
        query: DOI, URL, arXiv ID, or paper title

    Returns:
        Parsed JSON output from paper-fetch --format both

    Raises:
        PaperFetchUnavailable: If paper-fetch CLI is not found
        subprocess.CalledProcessError: If paper-fetch execution fails
    """
    if not _check_paper_fetch_available():
        raise PaperFetchUnavailable(
            "paper-fetch CLI is not available. Install with:\n"
            "  1. uv tool install paper-fetch-skill (recommended)\n"
            "  2. Clone to ~/.claude/skills/paper-fetch-skill and add to PATH\n"
            "  3. Run `uv sync --extra online-fetch` in PaperBase project"
        )

    # Call paper-fetch with JSON output format
    result = subprocess.run(
        ["paper-fetch", "--query", query, "--format", "both"],
        capture_output=True,
        text=True,
        check=True,
        encoding="utf-8",
    )

    # Parse JSON output
    return json.loads(result.stdout)


def _get_attr(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _parse_year(value: str | None) -> int:
    """Parse year from date string with validation.

    Returns current year as fallback for missing/invalid dates.
    Rejects placeholder years like 9999.
    """
    from datetime import datetime

    current_year = datetime.now().year

    if not value:
        return current_year

    for token in value.replace("/", "-").split("-"):
        if token.isdigit() and len(token) == 4:
            year = int(token)
            # Validate year is in reasonable range (1000-current_year+1)
            if 1000 <= year <= current_year + 1:
                return year

    return current_year


def _map_references(article: Any) -> list[FetchedReference]:
    references = []
    for item in _get_attr(article, "references", []) or []:
        references.append(
            FetchedReference(
                raw=str(_get_attr(item, "raw", "")),
                doi=_get_attr(item, "doi"),
                title=_get_attr(item, "title"),
                year=_get_attr(item, "year"),
            )
        )
    return references


def _map_assets(article: Any) -> list[FetchedAsset]:
    assets = []
    for item in _get_attr(article, "assets", []) or []:
        raw_path = _get_attr(item, "path")
        assets.append(
            FetchedAsset(
                kind=str(_get_attr(item, "kind", "asset")),
                heading=str(_get_attr(item, "heading", "Asset")),
                caption=_get_attr(item, "caption"),
                source_path=Path(raw_path) if raw_path else None,
                original_url=_get_attr(item, "original_url") or _get_attr(item, "url"),
            )
        )
    return assets


class PaperFetchAdapter:
    """Fetch DOI/URL/title queries through paper-fetch-skill CLI.

    paper-fetch-skill 作为外部黑盒工具，通过 CLI 调用。
    输入：DOI、URL、arXiv ID 或标题
    输出：JSON 格式的论文数据
    """

    def fetch(self, query: str) -> FetchedPaper:
        """Fetch paper metadata and content via paper-fetch CLI.

        Args:
            query: DOI, URL, arXiv ID, or paper title

        Returns:
            FetchedPaper with normalized data

        Raises:
            PaperFetchUnavailable: If paper-fetch CLI is not available
            subprocess.CalledProcessError: If paper-fetch execution fails
        """
        # Call paper-fetch CLI
        envelope = _call_paper_fetch_cli(query)

        # Extract fields from JSON response
        article = _get_attr(envelope, "article")
        metadata = _get_attr(envelope, "metadata") or _get_attr(article, "metadata")
        markdown = _get_attr(envelope, "markdown", "") or ""
        title = _get_attr(metadata, "title", "") or "Untitled"
        authors = list(_get_attr(metadata, "authors", []) or [])
        published = _get_attr(metadata, "published")

        return FetchedPaper(
            query=query,
            doi=_get_attr(envelope, "doi"),
            title=title,
            authors=authors or ["Unknown"],
            year=_parse_year(published),
            abstract=_get_attr(metadata, "abstract", "") or "",
            markdown=markdown,
            provider=str(_get_attr(envelope, "source", "paper-fetch")),
            original_url=_get_attr(metadata, "landing_page_url"),
            has_fulltext=bool(_get_attr(envelope, "has_fulltext", False)),
            content_kind=str(_get_attr(envelope, "content_kind", "metadata_only")),
            warnings=list(_get_attr(envelope, "warnings", []) or []),
            source_trail=list(_get_attr(envelope, "source_trail", []) or []),
            references=_map_references(article),
            assets=_map_assets(article),
        )
