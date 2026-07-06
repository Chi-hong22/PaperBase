"""快速验证 ingest 命令是否可以导入和运行"""

import sys
from pathlib import Path

# 测试导入
try:
    from paperbase.cli.commands.ingest import ingest, generate_canonical_markdown
    print("✓ ingest 模块导入成功")
except ImportError as e:
    print(f"✗ 导入失败: {e}")
    sys.exit(1)

# 测试 generate_canonical_markdown 函数
try:
    from paperbase.schemas.paper import PaperMetadata, PaperAuthor, PaperSource, PaperProvenance

    # 创建测试 metadata
    metadata = PaperMetadata(
        schema_version="1.0",
        paper_id="test:example",
        storage_id="p_test",
        title="Test Paper",
        authors=[PaperAuthor(name="John Doe")],
        year=2025,
        abstract="This is a test abstract.",
        source=PaperSource(discovery="test", fulltext_provider="test"),
        provenance=PaperProvenance(
            ingested_at="2025-01-01T00:00:00Z",
            converter={"name": "test", "version": "1.0"},
            normalizer={"name": "test", "version": "1.0"},
            canonical_content_sha256="abc123"
        )
    )

    body = "# Test\n\nThis is test content."

    result = generate_canonical_markdown(metadata, body)

    # 验证结果
    if result.startswith("---\n"):
        print("✓ generate_canonical_markdown 函数正常")
        print(f"  输出长度: {len(result)} 字符")
        print(f"  包含 frontmatter: {result.count('---') >= 2}")
    else:
        print("✗ generate_canonical_markdown 输出格式错误")
        sys.exit(1)

except Exception as e:
    print(f"✗ 测试失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n✅ 所有快速验证通过")
print("\n建议运行完整测试:")
print('  uv run paperbase ingest "F:\\__CODE__\\240408_TerrainBioSLAM\\paper\\reference\\Liu 等 - 2025 - A review of AUV-based bathymetric SLAM technology.pdf"')
