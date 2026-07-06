"""Manifest Schema 定义

每篇论文的状态和溯源信息
"""

from enum import Enum
from pydantic import BaseModel, Field


class PaperState(str, Enum):
    """论文处理状态"""
    DISCOVERED = "discovered"
    RESOLVED = "resolved"
    SOURCE_READY = "source_ready"
    CONVERTED = "converted"
    NORMALIZED = "normalized"
    VALIDATED = "validated"
    GRAPHED = "graphed"
    READY = "ready"
    NEEDS_REVIEW = "needs_review"
    BLOCKED = "blocked"
    FAILED_RETRYABLE = "failed_retryable"
    FAILED_PERMANENT = "failed_permanent"


class SourcePDF(BaseModel):
    """PDF 源文件信息"""
    path: str
    sha256: str
    acquired_at: str


class CanonicalMD(BaseModel):
    """规范化 Markdown 信息"""
    path: str
    sha256: str
    schema_version: str


class PipelineInfo(BaseModel):
    """处理流程信息"""
    converter: str
    converter_version: str
    normalizer_version: str | None = None


class GraphInfo(BaseModel):
    """图谱索引信息"""
    indexed: bool = False
    indexed_content_sha256: str | None = None


class ManifestSchema(BaseModel):
    """Paper Manifest (manifest.json)"""
    paper_id: str
    storage_id: str
    state: PaperState

    source_pdf: SourcePDF | None = None
    canonical_md: CanonicalMD | None = None
    pipeline: PipelineInfo | None = None
    graph: GraphInfo | None = None

    created_at: str | None = None
    updated_at: str | None = None
