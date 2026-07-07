"""Paper Canonical Schema 定义

Canonical Markdown frontmatter 的 pydantic 模型
"""

from datetime import datetime
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


class PaperAuthor(BaseModel):
    """论文作者"""
    name: str
    orcid: str | None = None
    affiliation: str | None = None


class PaperVenue(BaseModel):
    """发表venue"""
    name: str
    type: str  # journal, conference, preprint


class PaperIdentifiers(BaseModel):
    """论文标识符"""
    doi: str | None = None
    arxiv: str | None = None
    pmid: str | None = None
    openalex: str | None = None
    semantic_scholar: str | None = None


class PaperSource(BaseModel):
    """数据来源"""
    discovery: str  # zotero, search, manual
    fulltext_provider: str | None = None  # paper-fetch, manual
    original_url: str | None = None


class PaperProvenance(BaseModel):
    """溯源信息"""
    ingested_at: str  # ISO 8601
    converter: dict[str, str]  # {name, version}
    normalizer: dict[str, str]  # {name, version}
    source_pdf_sha256: str | None = None
    canonical_content_sha256: str

    @field_validator("ingested_at")
    @classmethod
    def validate_ingested_at(cls, v: str) -> str:
        return validate_iso8601_timestamp(v)


class PaperAssets(BaseModel):
    """资产配置"""
    root: str = "./assets"


class PaperReferences(BaseModel):
    """引用信息"""
    path: str = "./references.jsonl"
    count: int


class PaperChunks(BaseModel):
    """分块信息"""
    path: str = "./chunks.jsonl"
    strategy: str = "section-aware-v1"


class PaperQuality(BaseModel):
    """质量标记"""
    fulltext: bool = True
    metadata_complete: bool = True
    references_parsed: bool = True
    needs_review: bool = False


class PaperMetadata(BaseModel):
    """Paper Canonical Metadata (YAML frontmatter)"""
    schema_version: str
    paper_id: str
    storage_id: str

    title: str
    authors: list[PaperAuthor]
    year: int
    published_at: str | None = None

    venue: PaperVenue | None = None
    identifiers: PaperIdentifiers | None = None
    language: str = "en"
    abstract: str
    keywords: list[str] = Field(default_factory=list)

    source: PaperSource | None = None
    provenance: PaperProvenance | None = None

    assets: PaperAssets = Field(default_factory=PaperAssets)
    references: PaperReferences | None = None
    chunks: PaperChunks | None = None
    quality: PaperQuality = Field(default_factory=PaperQuality)
