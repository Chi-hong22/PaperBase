"""Markdown 规范化器

将候选 Markdown 转换为 Canonical Markdown
"""

import re
from datetime import datetime, UTC
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
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
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
