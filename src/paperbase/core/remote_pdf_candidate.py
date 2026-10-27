"""Temporary, secret-free cache for a remote PDF conversion candidate."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

from paperbase.config.models import PdfConversionConfig
from paperbase.core.visual_repair_run import isPathReparsePoint
from paperbase.utils.hash import sha256_file

CACHE_FILENAME = ".remote-candidate.json"


def remoteCandidateIdentity(  # noqa: N802
    source_pdf: Path, conversion_config: PdfConversionConfig
) -> str:
    providers = [
        {
            "name": provider.name,
            "provider": provider.provider,
            "base_url": provider.base_url,
            "timeout": provider.timeout,
        }
        for provider in conversion_config.remote.providers
    ]
    identity = {
        "source_pdf_sha256": sha256_file(source_pdf),
        "parser": conversion_config.parser,
        "providers": providers,
    }
    encoded_identity = json.dumps(identity, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded_identity).hexdigest()


def loadRemoteCandidate(source_pdf: Path, identity: str) -> dict[str, object] | None:  # noqa: N802
    cache_path = _cachePath(source_pdf)
    if cache_path is None or isPathReparsePoint(cache_path) or not cache_path.is_file():
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("identity") != identity:
        return None
    markdown = payload.get("markdown")
    assets = payload.get("assets")
    converter = payload.get("converter")
    converter_version = payload.get("converter_version")
    page_data = payload.get("page_data")
    if (
        not isinstance(markdown, str)
        or not markdown.strip()
        or not isinstance(assets, list)
        or not all(isinstance(asset, str) for asset in assets)
        or not isinstance(converter, str)
        or not isinstance(converter_version, str)
        or (page_data is not None and not isinstance(page_data, dict))
        or not _assetsExist(source_pdf, assets)
    ):
        return None
    return {
        "markdown": markdown,
        "assets": assets,
        "converter": converter,
        "converter_version": converter_version,
        "page_data": page_data,
    }


def saveRemoteCandidate(  # noqa: N802
    source_pdf: Path,
    identity: str,
    *,
    markdown: str,
    assets: tuple[str, ...],
    converter: str,
    converter_version: str,
    page_data: dict[str, object] | None,
) -> None:
    cache_path = _cachePath(source_pdf)
    if cache_path is None:
        return
    payload = {
        "identity": identity,
        "markdown": markdown,
        "assets": assets,
        "converter": converter,
        "converter_version": converter_version,
        "page_data": page_data,
    }
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=cache_path.parent,
            prefix=".remote-candidate-",
            suffix=".tmp",
            delete=False,
        ) as cache_file:
            temporary_path = Path(cache_file.name)
            json.dump(payload, cache_file, ensure_ascii=False)
            cache_file.flush()
            os.fsync(cache_file.fileno())
        os.replace(temporary_path, cache_path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def clearRemoteCandidate(paper_dir: Path) -> None:  # noqa: N802
    cache_path = Path(paper_dir) / CACHE_FILENAME
    if isPathReparsePoint(cache_path):
        raise ValueError("remote candidate cache is unsafe")
    cache_path.unlink(missing_ok=True)


def _cachePath(source_pdf: Path) -> Path | None:  # noqa: N802
    source_pdf = Path(source_pdf)
    if source_pdf.name != "source.pdf" or source_pdf.parent.name != "source":
        return None
    return source_pdf.parent.parent / CACHE_FILENAME


def _assetsExist(source_pdf: Path, assets: list[str]) -> bool:  # noqa: N802
    assets_root = source_pdf.parent.parent / "assets"
    if not assets:
        return True
    if not assets_root.is_dir():
        return False
    for asset in assets:
        if not asset.startswith("./assets/") or "\\" in asset:
            return False
        parts = asset.removeprefix("./assets/").split("/")
        if not parts or any(part in {"", ".", ".."} for part in parts):
            return False
        if not assets_root.joinpath(*parts).is_file():
            return False
    return True
