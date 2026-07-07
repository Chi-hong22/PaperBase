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
