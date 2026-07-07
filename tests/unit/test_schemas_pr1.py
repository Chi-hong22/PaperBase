"""Schema PR1 基础验证测试"""

import pytest
from datetime import datetime


def test_timestamp_validation_iso8601():
    """测试时间戳必须符合 ISO 8601 格式"""
    from paperbase.schemas.paper import PaperProvenance

    # 有效格式
    valid_timestamps = [
        "2026-07-07T10:30:00Z",
        "2026-07-07T10:30:00+08:00",
        "2026-07-07T10:30:00.123456Z",
    ]

    for ts in valid_timestamps:
        prov = PaperProvenance(
            ingested_at=ts,
            converter={"name": "test", "version": "1.0"},
            normalizer={"name": "test", "version": "1.0"},
            canonical_content_sha256="a" * 64
        )
        assert prov.ingested_at == ts

    # 无效格式
    invalid_timestamps = [
        "2026-07-07",
        "10:30:00",
        "2026/07/07 10:30:00",
        "not-a-timestamp",
    ]

    for ts in invalid_timestamps:
        with pytest.raises(ValueError, match="ISO 8601"):
            PaperProvenance(
                ingested_at=ts,
                converter={"name": "test", "version": "1.0"},
                normalizer={"name": "test", "version": "1.0"},
                canonical_content_sha256="a" * 64
            )


def test_manifest_timestamp_validation():
    """测试 Manifest 时间戳验证"""
    from paperbase.schemas.manifest import ManifestSchema, PaperState, SourcePDF

    # SourcePDF.acquired_at 无效
    with pytest.raises(ValueError, match="ISO 8601"):
        ManifestSchema(
            paper_id="doi:10.1234/test",
            storage_id="p_abc123",
            state=PaperState.DISCOVERED,
            source_pdf=SourcePDF(
                path="test.pdf",
                sha256="a" * 64,
                acquired_at="invalid-timestamp"
            ),
            created_at="2026-07-07T10:30:00Z",
            updated_at="2026-07-07T10:30:00Z"
        )


def test_paper_venue_type_enum():
    """测试 PaperVenue.type 必须是有效枚举值"""
    from paperbase.schemas.paper import PaperVenue

    # 有效值
    for t in ["journal", "conference", "preprint"]:
        venue = PaperVenue(name="Test Venue", type=t)
        assert venue.type == t

    # 无效值
    with pytest.raises(ValueError, match="type"):
        PaperVenue(name="Test Venue", type="invalid-type")


def test_paper_source_discovery_enum():
    """测试 PaperSource.discovery 必须是有效枚举值"""
    from paperbase.schemas.paper import PaperSource

    # 有效值
    for d in ["zotero", "search", "manual"]:
        source = PaperSource(discovery=d)
        assert source.discovery == d

    # 无效值
    with pytest.raises(ValueError, match="discovery"):
        PaperSource(discovery="invalid-discovery")


def test_paper_chunks_strategy_enum():
    """测试 PaperChunks.strategy 必须是有效枚举值"""
    from paperbase.schemas.paper import PaperChunks

    # 有效值
    chunks = PaperChunks(path="./chunks.jsonl", strategy="section-aware-v1")
    assert chunks.strategy == "section-aware-v1"

    # 无效值
    with pytest.raises(ValueError, match="strategy"):
        PaperChunks(path="./chunks.jsonl", strategy="invalid-strategy")


def test_paper_references_count_non_negative():
    """测试 PaperReferences.count 必须非负"""
    from paperbase.schemas.paper import PaperReferences

    # 有效值
    refs = PaperReferences(path="./references.jsonl", count=0)
    assert refs.count == 0

    refs = PaperReferences(path="./references.jsonl", count=42)
    assert refs.count == 42

    # 无效值
    with pytest.raises(ValueError, match="count"):
        PaperReferences(path="./references.jsonl", count=-1)


def test_paper_metadata_year_range():
    """测试 PaperMetadata.year 必须在合理范围内 (1000-2100)"""
    from paperbase.schemas.paper import (
        PaperMetadata,
        PaperAuthor,
        PaperProvenance
    )

    base_data = {
        "schema_version": "1.0.0",
        "paper_id": "doi:10.1234/test",
        "storage_id": "p_abc123",
        "title": "Test Paper",
        "authors": [{"name": "Alice"}],
        "abstract": "Test abstract",
        "provenance": {
            "ingested_at": "2026-07-07T10:30:00Z",
            "converter": {"name": "test", "version": "1.0"},
            "normalizer": {"name": "test", "version": "1.0"},
            "canonical_content_sha256": "a" * 64
        }
    }

    # 有效值
    for year in [1000, 1500, 2026, 2100]:
        paper = PaperMetadata(**base_data, year=year)
        assert paper.year == year

    # 无效值
    for year in [999, 2101]:
        with pytest.raises(ValueError, match="year"):
            PaperMetadata(**base_data, year=year)


def test_sha256_format_validation():
    """测试 SHA256 字段必须是 64 位小写十六进制格式"""
    from paperbase.schemas.paper import PaperProvenance
    from paperbase.schemas.manifest import ManifestSchema, PaperState, SourcePDF

    # 有效格式
    valid_sha256 = "a" * 64
    prov = PaperProvenance(
        ingested_at="2026-07-07T10:30:00Z",
        converter={"name": "test", "version": "1.0"},
        normalizer={"name": "test", "version": "1.0"},
        canonical_content_sha256=valid_sha256
    )
    assert prov.canonical_content_sha256 == valid_sha256

    # 无效格式
    invalid_hashes = [
        "A" * 64,  # 大写
        "a" * 63,  # 太短
        "a" * 65,  # 太长
        "g" * 64,  # 非十六进制字符
        "abcd1234",  # 太短
    ]

    for bad_hash in invalid_hashes:
        with pytest.raises(ValueError, match="SHA256|sha256"):
            PaperProvenance(
                ingested_at="2026-07-07T10:30:00Z",
                converter={"name": "test", "version": "1.0"},
                normalizer={"name": "test", "version": "1.0"},
                canonical_content_sha256=bad_hash
            )

    # 测试 manifest.py 中的 SourcePDF.sha256
    manifest = ManifestSchema(
        paper_id="doi:10.1234/test",
        storage_id="p_abc123",
        state=PaperState.DISCOVERED,
        source_pdf=SourcePDF(
            path="test.pdf",
            sha256=valid_sha256,
            acquired_at="2026-07-07T10:30:00Z"
        ),
        created_at="2026-07-07T10:30:00Z",
        updated_at="2026-07-07T10:30:00Z"
    )
    assert manifest.source_pdf.sha256 == valid_sha256

    # SourcePDF.sha256 无效
    with pytest.raises(ValueError, match="SHA256|sha256"):
        ManifestSchema(
            paper_id="doi:10.1234/test",
            storage_id="p_abc123",
            state=PaperState.DISCOVERED,
            source_pdf=SourcePDF(
                path="test.pdf",
                sha256="invalid-hash",
                acquired_at="2026-07-07T10:30:00Z"
            ),
            created_at="2026-07-07T10:30:00Z",
            updated_at="2026-07-07T10:30:00Z"
        )
