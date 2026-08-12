"""Pure, local validation before adopting Canonical Markdown."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from paperbase.core.reference_extractor import extract_references
from paperbase.schemas.paper import PaperMetadata
from paperbase.utils.markdown import (
    find_local_absolute_image_paths,
    parse_frontmatter,
)

_IMAGE_TARGET_PATTERN = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
_REFERENCE_HEADING_PATTERN = re.compile(r"^(#+)\s+(References?|Bibliography)\s*$", re.I)
_STANDALONE_LITERAL_ESCAPE = re.compile(r"(?m)^[ \t]*\\(?:n|r|t)[ \t]*$")
_TEMPORARY_VISUAL_MARKERS = (
    "<!-- paperbase:visual-page-start",
    "<!-- paperbase:visual-page-end",
)


class CanonicalAdoptionGateError(ValueError):
    """Stable rejection raised by the local Canonical adoption gate."""

    code = "canonical_adoption_gate_failed"

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


@dataclass(frozen=True)
class CanonicalAdoptionCheck:
    """Validated data reusable by later adoption steps."""

    metadata: PaperMetadata
    references: tuple[dict[str, Any], ...]


def validateFinalMarkdownHealth(markdown: str) -> None:  # noqa: N802
    """Reject deterministic extraction debris without writing any state."""
    if "\ufffd" in markdown:
        raise CanonicalAdoptionGateError(
            "unicode_replacement_character",
            "Markdown contains Unicode replacement characters",
        )
    if any(ord(character) < 32 and character not in {"\n", "\r", "\t"} for character in markdown):
        raise CanonicalAdoptionGateError(
            "invalid_c0_control_character",
            "Markdown contains invalid C0 control characters",
        )
    if _STANDALONE_LITERAL_ESCAPE.search(markdown):
        raise CanonicalAdoptionGateError(
            "standalone_literal_escape",
            "Markdown contains standalone literal escape fragments",
        )
    if any(marker in markdown for marker in _TEMPORARY_VISUAL_MARKERS):
        raise CanonicalAdoptionGateError(
            "temporary_visual_marker",
            "Markdown contains temporary visual page markers",
        )


def validateMarkdownHealth(markdown: str) -> None:  # noqa: N802
    """Compatibility name for callers validating non-final Markdown."""
    validateFinalMarkdownHealth(markdown)


def inspectCanonicalTextForGraph(content: str, minimum_chars: int) -> str | None:  # noqa: N802
    """Return the existing local Graphify preflight reason for Canonical text."""
    try:
        metadata, body = parse_frontmatter(content)
    except ValueError as exc:
        return f"Canonical Markdown 无法解析: {exc}"

    body_metadata, body_text = _extractEmbeddedMetadata(body)
    if body_metadata.get("content_kind") in {"metadata_only", "abstract_only"}:
        return f"content_kind={body_metadata['content_kind']}"
    if body_metadata.get("has_fulltext") is False:
        return "has_fulltext=false"

    embedded_fulltext = (
        body_metadata.get("content_kind") == "fulltext" or body_metadata.get("has_fulltext") is True
    )
    quality = metadata.get("quality") or {}
    if not embedded_fulltext:
        if quality.get("fulltext") is False:
            return "quality.fulltext=false"
        if quality.get("needs_review") is True:
            return "quality.needs_review=true"

    if len(body_text.strip()) < minimum_chars:
        return f"Canonical 正文不足 {minimum_chars} 字符"
    return None


def validateCanonicalAdoption(  # noqa: N802
    canonical: str,
    *,
    expected_paper_id: str,
    expected_storage_id: str,
    minimum_body_chars: int,
) -> CanonicalAdoptionCheck:
    """Validate an in-memory Canonical candidate before any persistent adoption."""
    validateFinalMarkdownHealth(canonical)

    try:
        raw_metadata, body = parse_frontmatter(canonical)
    except ValueError as exc:
        raise CanonicalAdoptionGateError(
            "frontmatter_invalid",
            f"Canonical frontmatter is invalid: {exc}",
        ) from exc

    try:
        metadata = PaperMetadata.model_validate(raw_metadata)
    except ValidationError as exc:
        raise CanonicalAdoptionGateError(
            "schema_invalid",
            f"Canonical schema validation failed: {exc}",
        ) from exc

    if metadata.paper_id != expected_paper_id:
        raise CanonicalAdoptionGateError(
            "paper_id_mismatch",
            f"Canonical paper_id does not match expected paper_id {expected_paper_id}",
        )
    if metadata.storage_id != expected_storage_id:
        raise CanonicalAdoptionGateError(
            "storage_id_mismatch",
            f"Canonical storage_id does not match expected storage_id {expected_storage_id}",
        )

    _validate_asset_targets(canonical)

    graph_reason = inspectCanonicalTextForGraph(canonical, minimum_body_chars)
    if graph_reason is not None:
        raise CanonicalAdoptionGateError("graph_preflight_failed", graph_reason)

    references = tuple(extract_references(canonical, metadata.paper_id))
    if _referencesSectionHasContent(body) and not references:
        raise CanonicalAdoptionGateError(
            "references_unparseable",
            "References section has content but no structured references can be parsed",
        )

    return CanonicalAdoptionCheck(metadata=metadata, references=references)


def _validate_asset_targets(markdown: str) -> None:
    absolute_targets = find_local_absolute_image_paths(markdown)
    if absolute_targets:
        raise CanonicalAdoptionGateError(
            "asset_path_invalid",
            f"Canonical asset path must be relative: {absolute_targets[0]}",
        )

    for raw_target in _IMAGE_TARGET_PATTERN.findall(markdown):
        target = raw_target.strip().strip("<>").split(maxsplit=1)[0]
        relative_parts = target.removeprefix("./").split("/")
        if (
            not target.startswith("./assets/")
            or "\\" in target
            or len(relative_parts) < 2
            or any(part in {"", ".", ".."} for part in relative_parts)
        ):
            raise CanonicalAdoptionGateError(
                "asset_path_invalid",
                f"Canonical asset target must use ./assets/: {target}",
            )


def _extractEmbeddedMetadata(body: str) -> tuple[dict[str, Any], str]:  # noqa: N802
    stripped = body.lstrip()
    if not stripped.startswith("---\n"):
        return {}, body
    try:
        metadata, remainder = parse_frontmatter(stripped)
    except ValueError:
        return {}, body
    return metadata, remainder


def _referencesSectionHasContent(body: str) -> bool:  # noqa: N802
    lines = body.splitlines()
    for index, line in enumerate(lines):
        heading_match = _REFERENCE_HEADING_PATTERN.match(line)
        if heading_match is None:
            continue
        heading_level = len(heading_match.group(1))
        for candidate in lines[index + 1 :]:
            next_heading = re.match(r"^(#+)\s+", candidate)
            if next_heading is not None and len(next_heading.group(1)) <= heading_level:
                return False
            if candidate.strip():
                return True
        return False
    return False
