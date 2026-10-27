"""OXR（Open eXtended Reader）远程 PDF 解析适配器。"""

from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

import pymupdf

from paperbase.config.models import RemotePdfProviderConfig
from paperbase.utils.markdown import find_local_absolute_image_paths


@dataclass(frozen=True)
class OxrCandidate:
    """OXR 返回的待校验 Markdown 候选。"""

    markdown: str
    assets: tuple[str, ...] = ()
    page_data: dict[str, object] | None = None


class OxrCandidateError(Exception):
    """当前 OXR 候选不可用；消息不包含密钥或响应正文。"""

    def __init__(self, message: str, *, transient: bool = False) -> None:
        super().__init__(message)
        self.transient = transient


def parseWithOxr(source_pdf: Path, provider: RemotePdfProviderConfig) -> OxrCandidate:  # noqa: N802
    """向单条 OXR 配置请求同步解析，返回正文候选。"""
    try:
        source_bytes = source_pdf.read_bytes()
    except OSError as exc:
        raise OxrCandidateError("无法读取源 PDF 文件") from exc

    upload_id = uuid4().hex
    boundary = f"----paperbase-{upload_id}"
    request = Request(
        f"{provider.base_url.rstrip('/')}/parse/sync",
        data=_buildMultipartBody(
            f"paperbase-{upload_id}.pdf", source_bytes, provider.api_key, boundary
        ),
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=provider.timeout) as response:
            raw_body = response.read()
    except HTTPError as exc:
        transient = exc.code in {408, 429} or exc.code >= 500
        raise OxrCandidateError(f"OXR 服务返回 HTTP {exc.code}", transient=transient) from exc
    except OSError as exc:
        raise OxrCandidateError("OXR 服务请求失败", transient=True) from exc

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OxrCandidateError("OXR 响应不是有效 JSON", transient=True) from exc
    if not isinstance(payload, dict):
        raise OxrCandidateError("OXR 响应结构无效")
    if type(payload.get("code")) is not int or payload["code"] != 0:
        code = payload.get("code")
        if type(code) is int and code in {1101, 1105, 1107, 1108, 1123, 1124, 1132, 1133, 1137}:
            raise OxrCandidateError(
                f"OXR 服务返回 code={code}",
                transient=code in {1101, 1124},
            )
        raise OxrCandidateError("OXR 服务拒绝了解析请求")

    data = payload.get("data")
    result = data.get("result") if isinstance(data, dict) else None
    outputs = result.get("outputs") if isinstance(result, dict) else None
    markdown = outputs.get("markdown") if isinstance(outputs, dict) else None
    if not isinstance(markdown, str) or not markdown.strip():
        raise OxrCandidateError("OXR 响应缺少正文")
    page_data = outputs.get("json") if isinstance(outputs, dict) else None
    saved_paths: list[Path] = []
    source_paths: dict[str, str] = {}
    assets: list[str] = []
    paper_dir = source_pdf.parent.parent
    try:
        markdown = _rewriteImages(markdown, paper_dir, provider, source_paths, saved_paths, assets)
        if isinstance(page_data, dict):
            page_data = _rewritePageData(
                page_data, paper_dir, provider, source_paths, saved_paths, assets
            )
    except (binascii.Error, OSError, ValueError) as exc:
        for saved_path in saved_paths:
            saved_path.unlink(missing_ok=True)
        raise OxrCandidateError("OXR 图片无法保存为本地资产") from exc
    return OxrCandidate(
        markdown=markdown,
        assets=tuple(assets),
        page_data=page_data if isinstance(page_data, dict) else None,
    )


def _buildMultipartBody(  # noqa: N802
    filename: str,
    source_bytes: bytes,
    api_key: str,
    boundary: str,
) -> bytes:
    parts: list[bytes] = [
        (
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            "Content-Type: application/pdf\r\n\r\n"
        ).encode("utf-8"),
        source_bytes,
        b"\r\n",
    ]
    for value in ("markdown", "json"):
        parts.append(
            (
                f"--{boundary}\r\n"
                'Content-Disposition: form-data; name="output_formats"\r\n\r\n'
                f"{value}\r\n"
            ).encode("utf-8")
        )
    parts.append(
        (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="api_key"\r\n\r\n'
            f"{api_key}\r\n"
        ).encode("utf-8")
    )
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(parts)


_MARKDOWN_IMAGE = re.compile(
    r'!\[(?P<alt>[^\]]*)\]\(\s*(?:<(?P<angle>[^>]+)>|(?P<source>[^)\s]+))'
    r'(?:\s+["\'][^)]*["\'])?\s*\)'
)
_HTML_IMAGE = re.compile(
    r"<img\b[^>]*?\bsrc=(?P<quote>[\"'])(?P<source>[^\"']+)(?P=quote)",
    re.IGNORECASE,
)
_IMAGE_SUFFIXES = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "image/gif": "gif",
}


def _rewriteImages(  # noqa: N802
    markdown: str,
    paper_dir: Path,
    provider: RemotePdfProviderConfig,
    source_paths: dict[str, str],
    saved_paths: list[Path],
    assets: list[str],
) -> str:
    """将 OXR Markdown 图片改为本地 assets 引用。"""
    image_matches = sorted(
        [*_MARKDOWN_IMAGE.finditer(markdown), *_HTML_IMAGE.finditer(markdown)],
        key=lambda match: match.start(),
    )
    if not image_matches:
        return markdown

    assets_dir = paper_dir / "assets"
    rewritten = markdown
    for match in reversed(image_matches):
        source = match.groupdict().get("angle") or match.groupdict().get("source")
        if source is None:
            source = match.group("source")
        relative_path = source_paths.get(source)
        if relative_path is None:
            if source.startswith("data:image/"):
                header, encoded = source.split(",", 1)
                media_type = header[5:].split(";", 1)[0].lower()
                image_bytes = base64.b64decode(encoded, validate=True)
            else:
                parsed_url = urlparse(source)
                if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
                    raise ValueError("unsupported OXR image URL")
                with urlopen(Request(source), timeout=provider.timeout) as response:
                    media_type = response.headers.get_content_type().lower()
                    image_bytes = response.read()

            suffix = _IMAGE_SUFFIXES.get(media_type)
            if suffix is None or not image_bytes:
                raise ValueError("unsupported OXR image result")
            try:
                image = pymupdf.Pixmap(image_bytes)
                if image.width <= 0 or image.height <= 0:
                    raise ValueError("empty OXR image result")
            except Exception as exc:
                raise ValueError("invalid OXR image bytes") from exc

            relative_path = f"./assets/oxr-{uuid4().hex}.{suffix}"
            target = assets_dir / relative_path.removeprefix("./assets/")
            assets_dir.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as image_file:
                saved_paths.append(target)
                image_file.write(image_bytes)
            assets.append(relative_path)
            source_paths[source] = relative_path
        if "alt" in match.groupdict():
            target_group = "angle" if match.group("angle") is not None else "source"
            start, end = match.span(target_group)
            replacement = (
                match.group(0)[: start - match.start()]
                + relative_path
                + match.group(0)[end - match.start() :]
            )
        else:
            replacement = match.group().replace(source, relative_path, 1)
        rewritten = rewritten[: match.start()] + replacement + rewritten[match.end() :]

    if find_local_absolute_image_paths(rewritten):
        raise ValueError("OXR Markdown still contains a local image path")
    return rewritten


def _rewritePageData(  # noqa: N802
    page_data: dict[str, object],
    paper_dir: Path,
    provider: RemotePdfProviderConfig,
    source_paths: dict[str, str],
    saved_paths: list[Path],
    assets: list[str],
) -> dict[str, object]:
    """保留 OXR 页面信息，并将块正文中的图片引用指向同一份本地资产。"""
    def rewrite(value: object, key: str = "") -> object:
        if isinstance(value, dict):
            return {name: rewrite(item, name) for name, item in value.items()}
        if isinstance(value, list):
            return [rewrite(item, key) for item in value]
        if key == "content" and isinstance(value, str):
            return _rewriteImages(value, paper_dir, provider, source_paths, saved_paths, assets)
        return value

    return cast(dict[str, object], rewrite(page_data))
