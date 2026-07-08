"""Manifest Schema 定义

每篇论文的状态和溯源信息
"""

from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, field_validator


def validate_iso8601_timestamp(v: str | None) -> str | None:
    """验证 ISO 8601 时间戳格式"""
    if v is None:
        return v

    try:
        # 必须包含 'T' 分隔符，确保是完整的日期时间格式
        if 'T' not in v:
            raise ValueError(f"时间戳必须符合 ISO 8601 格式，收到: {v}")

        datetime.fromisoformat(v.replace("Z", "+00:00"))
        return v
    except (ValueError, AttributeError):
        raise ValueError(f"时间戳必须符合 ISO 8601 格式，收到: {v}")


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

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, v: str) -> str:
        import re
        if not re.match(r'^[a-f0-9]{64}$', v):
            raise ValueError(f"SHA256 必须是 64 位小写十六进制，收到: {v}")
        return v

    @field_validator("acquired_at")
    @classmethod
    def validate_acquired_at(cls, v: str) -> str:
        return validate_iso8601_timestamp(v)


class SourceArtifact(BaseModel):
    """Non-PDF source artifact produced by an acquisition adapter."""

    path: str
    kind: str
    acquired_at: str
    provider: str | None = None
    original_url: str | None = None
    sha256: str | None = None

    @field_validator("acquired_at")
    @classmethod
    def validate_acquired_at(cls, v: str) -> str:
        return validate_iso8601_timestamp(v)

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, v: str | None) -> str | None:
        if v is None:
            return v
        import re

        if not re.match(r"^[a-f0-9]{64}$", v):
            raise ValueError(f"SHA256 必须是 64 位小写十六进制，收到: {v}")
        return v


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
    updated_at: str | None = None
    content_sha256_at_index: str | None = None  # 新增：记录图谱化时的内容 SHA256


class ManifestSchema(BaseModel):
    """Paper Manifest (manifest.json)"""
    paper_id: str
    storage_id: str
    state: PaperState

    source_pdf: SourcePDF | None = None
    source_artifacts: list[SourceArtifact] = Field(default_factory=list)
    canonical_md: CanonicalMD | None = None
    pipeline: PipelineInfo | None = None
    graph: GraphInfo | None = None

    created_at: str | None = None
    updated_at: str | None = None
