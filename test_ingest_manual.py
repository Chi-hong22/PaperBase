"""手动测试 ingest 功能"""

import sys
from pathlib import Path

# 添加 src 到路径
sys.path.insert(0, str(Path(__file__).parent / "src"))

from paperbase.cli.commands.ingest import ingest, generate_canonical_markdown
from paperbase.adapters.pdf_extractor import extract_pdf_metadata
from paperbase.adapters.pdf_converter import convert_pdf_to_markdown
from paperbase.core.normalizer import normalize_paper

# 测试路径
test_pdf = Path(r"F:\__CODE__\240408_TerrainBioSLAM\paper\reference\Liu 等 - 2025 - A review of AUV-based bathymetric SLAM technology.pdf")

if not test_pdf.exists():
    print(f"错误: 测试 PDF 不存在: {test_pdf}")
    sys.exit(1)

print("=" * 60)
print("手动测试 ingest 流程")
print("=" * 60)

# Step 1: 测试元数据提取
print("\n[1/4] 测试元数据提取...")
try:
    metadata = extract_pdf_metadata(test_pdf)
    print(f"✓ 标题: {metadata.get('title', 'N/A')}")
    print(f"✓ 作者: {metadata.get('authors', [])}")
    print(f"✓ 年份: {metadata.get('year', 'N/A')}")
except Exception as e:
    print(f"✗ 失败: {e}")
    sys.exit(1)

# Step 2: 测试 PDF 转换
print("\n[2/4] 测试 PDF 转换...")
try:
    candidate_md = convert_pdf_to_markdown(test_pdf)
    print(f"✓ Markdown 长度: {len(candidate_md)} 字符")
    print(f"✓ 前 100 字符: {candidate_md[:100]}...")
except Exception as e:
    print(f"✗ 失败: {e}")
    sys.exit(1)

# Step 3: 测试规范化
print("\n[3/4] 测试规范化...")
try:
    paper_metadata = normalize_paper(
        candidate_md=candidate_md,
        metadata=metadata,
        paper_id="test:liu2025",
        storage_id="p_test123",
        source_provider="markitdown"
    )
    print(f"✓ paper_id: {paper_metadata.paper_id}")
    print(f"✓ storage_id: {paper_metadata.storage_id}")
    print(f"✓ 标题: {paper_metadata.title}")
    print(f"✓ 作者数: {len(paper_metadata.authors)}")
except Exception as e:
    print(f"✗ 失败: {e}")
    sys.exit(1)

# Step 4: 测试生成 Canonical Markdown
print("\n[4/4] 测试生成 Canonical Markdown...")
try:
    canonical_md = generate_canonical_markdown(paper_metadata, candidate_md)
    print(f"✓ Canonical Markdown 长度: {len(canonical_md)} 字符")
    print(f"✓ 包含 frontmatter: {'---' in canonical_md[:50]}")

    # 检查 frontmatter 结构
    if canonical_md.startswith("---\n"):
        parts = canonical_md.split("---\n", 2)
        if len(parts) >= 3:
            print(f"✓ Frontmatter 长度: {len(parts[1])} 字符")
        else:
            print("⚠ Frontmatter 格式可能有问题")
except Exception as e:
    print(f"✗ 失败: {e}")
    sys.exit(1)

print("\n" + "=" * 60)
print("✅ 所有组件测试通过!")
print("=" * 60)
print("\ningest 命令已准备就绪，可以使用:")
print(f"  uv run paperbase ingest \"{test_pdf}\"")
