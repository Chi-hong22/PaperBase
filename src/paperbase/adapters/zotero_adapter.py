"""Adapter boundary for Zotero integration via zotero-mcp-server.

使用 zotero-mcp-server Python 模块直接调用，支持本地和 API 两种模式。
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime


class ZoteroUnavailable(RuntimeError):
    """Raised when Zotero is not available or not configured."""


@dataclass(frozen=True)
class ZoteroItem:
    """Zotero 条目数据类（不可变）。"""

    key: str
    title: str
    authors: list[str]
    year: int | None
    doi: str | None
    arxiv_id: str | None
    abstract: str
    item_type: str
    url: str | None


def _parse_year(value: str | None) -> int | None:
    """Parse year from date string with validation.

    Returns None for missing/invalid dates so downstream sources can fill it.
    Rejects placeholder years like 9999.
    """
    current_year = datetime.now().year

    if not value:
        return None

    # Try common date formats: YYYY-MM-DD, YYYY/MM/DD, YYYY
    for token in str(value).replace("/", "-").split("-"):
        if token.isdigit() and len(token) == 4:
            year = int(token)
            # Validate year is in reasonable range (1000-current_year+1)
            if 1000 <= year <= current_year + 1:
                return year

    return None


class ZoteroAdapter:
    """Fetch papers from Zotero via zotero-mcp-server Python module.

    Supports two modes:
    - local_mode=True: Connect to local Zotero instance (requires Zotero running)
    - local_mode=False: Use Zotero Web API (requires api_key and library_id)
    """

    def __init__(
        self,
        local_mode: bool = True,
        api_key: str | None = None,
        library_id: str | None = None,
        library_type: str = "user",
    ):
        """Initialize Zotero adapter.

        Args:
            local_mode: If True, connect to local Zotero. If False, use Web API.
            api_key: Zotero Web API key (required if local_mode=False)
            library_id: Zotero library ID (required if local_mode=False)
            library_type: Library type ("user" or "group"), default "user"

        Raises:
            ZoteroUnavailable: If zotero-mcp-server is not installed
        """
        try:
            from zotero_mcp.cli_standalone import CLIContext
            from zotero_mcp.tools import retrieval
        except ImportError as e:
            raise ZoteroUnavailable(
                "zotero-mcp-server is not installed. Install with:\n"
                "  uv tool install zotero-mcp-server"
            ) from e

        self._retrieval = retrieval
        self.local_mode = local_mode

        # Set environment variables for zotero_mcp
        if local_mode:
            os.environ["ZOTERO_LOCAL"] = "true"
        else:
            if not api_key or not library_id:
                raise ZoteroUnavailable(
                    "api_key and library_id are required when local_mode=False"
                )
            os.environ["ZOTERO_API_KEY"] = api_key
            os.environ["ZOTERO_LIBRARY_ID"] = library_id
            os.environ["ZOTERO_LIBRARY_TYPE"] = library_type

        # Create context (verbose=False to reduce noise)
        self._ctx = CLIContext(verbose=False)

    def fetch_item(self, item_key: str) -> ZoteroItem:
        """Fetch a specific Zotero item by key.

        Args:
            item_key: Zotero item key (8-character alphanumeric)

        Returns:
            ZoteroItem with parsed data

        Raises:
            ZoteroUnavailable: If item not found or Zotero is unavailable
        """
        try:
            result = self._retrieval.get_item_metadata(
                item_key=item_key,
                include_abstract=True,
                format="json",
                ctx=self._ctx,
            )
            payload = json.loads(result)
        except Exception as e:
            raise ZoteroUnavailable(f"Failed to fetch item {item_key}: {e}") from e

        data = payload.get("data", payload)
        key = payload.get("key") or data.get("key") or item_key
        title = data.get("title", "")
        if not title:
            raise ZoteroUnavailable(f"Failed to parse Zotero item {item_key}: missing title")

        authors = []
        for creator in data.get("creators", []):
            if creator.get("name"):
                authors.append(creator["name"])
                continue

            first_name = creator.get("firstName", "")
            last_name = creator.get("lastName", "")
            if first_name and last_name:
                authors.append(f"{last_name}, {first_name}")
            elif last_name or first_name:
                authors.append(last_name or first_name)

        return ZoteroItem(
            key=key,
            title=title,
            authors=authors,
            year=_parse_year(data.get("date")),
            doi=data.get("DOI") or None,
            arxiv_id=data.get("archiveID") or None,
            abstract=data.get("abstractNote", "") or "",
            item_type=data.get("itemType", "journalArticle"),
            url=data.get("url") or None,
        )

    def list_recent(self, limit: int = 50) -> list[ZoteroItem]:
        """List recent Zotero items.

        Args:
            limit: Maximum number of items to return (default 50)

        Returns:
            List of ZoteroItem objects

        Raises:
            ZoteroUnavailable: If Zotero is unavailable
        """
        try:
            result = self._retrieval.get_recent(limit=limit, ctx=self._ctx)
        except Exception as e:
            raise ZoteroUnavailable(f"Failed to list recent items: {e}") from e

        # Check if result indicates error
        if result.lstrip().lower().startswith("error"):
            raise ZoteroUnavailable(f"Zotero error: {result}")

        item_keys = re.findall(
            r"^\*\*Item Key:\*\*\s*([A-Za-z0-9]+)\s*$",
            result,
            flags=re.MULTILINE,
        )
        return [self.fetch_item(item_key) for item_key in item_keys]

    def get_pdf_path(self, item_key: str) -> str | None:
        """Get local PDF attachment path for a Zotero item.

        Args:
            item_key: Zotero item key

        Returns:
            Local file path to PDF, or None if no PDF attachment found

        Raises:
            ZoteroUnavailable: If Zotero is unavailable or not in local mode
        """
        if not self.local_mode:
            # Web API mode doesn't support local file paths
            return None

        try:
            result = self._retrieval.get_attachment_path(item_key=item_key, ctx=self._ctx)
        except Exception as e:
            # Not finding attachments is not an error - return None
            return None

        # Parse result: zotero_mcp returns markdown with file paths
        # Example: "**Path**: /path/to/file.pdf"
        if not result or result.lstrip().lower().startswith("error"):
            return None

        # Extract file path from markdown
        for line in result.split("\n"):
            line = line.strip()
            local_path_match = re.match(r"^-\s*Local path:\s*`?(.+?)`?$", line)
            if local_path_match:
                path = local_path_match.group(1)
            elif line.startswith("**Path**:") or line.startswith("Path:"):
                path = line.split(":", 1)[-1].strip()
            else:
                continue

            if path.lower().endswith(".pdf") and os.path.exists(path):
                return path

        return None
