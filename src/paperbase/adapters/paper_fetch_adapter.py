"""Adapter boundary for Dictation354/paper-fetch-skill."""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from typing import Any, Callable


class PaperFetchUnavailable(RuntimeError):
    """Raised when optional paper-fetch support is not installed."""


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


def _load_fetch_paper() -> Callable[..., Any]:
    try:
        service = import_module("paper_fetch.service")
    except ImportError as exc:
        raise PaperFetchUnavailable(
            "paper-fetch-skill is not installed. Install with `uv sync --extra online-fetch`."
        ) from exc
    return service.fetch_paper


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
    """Fetch DOI/URL/title queries through paper-fetch-skill."""

    def __init__(self, fetch_paper_fn: Callable[..., Any] | None = None):
        self._fetch_paper_fn = fetch_paper_fn or _load_fetch_paper()

    def fetch(self, query: str) -> FetchedPaper:
        envelope = self._fetch_paper_fn(
            query,
            modes={"article", "markdown", "metadata"},
            render=None,
        )
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
