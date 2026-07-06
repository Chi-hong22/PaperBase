#!/usr/bin/env python
"""快速测试 Phase 2 功能"""

from pathlib import Path
from paperbase.adapters.pdf_extractor import extract_pdf_metadata
from paperbase.adapters.pdf_converter import convert_pdf_to_markdown
from paperbase.core.normalizer import normalize_paper, extract_abstract
from paperbase.core.identity import normalize_paper_id, generate_storage_id

# 测试 PDF
pdf_path = Path(r"F:\__CODE__\240408_TerrainBioSLAM\paper\reference\Liu 等 - 2025 - A review of AUV-based bathymetric SLAM technology.pdf")

print("=" * 60)
print("Phase 2 功能测试")
print("=" * 60)

# 1. 测试元数据提取
print("\n1. 测试 PDF 元数据提取...")
metadata = extract_pdf_metadata(pdf_path)
print(f"   标题: {metadata.get('title', 'N/A')}")
print(f"   作者: {metadata.get('authors', [])}")
print(f"   年份: {metadata.get('year', 'N/A')}")
print(f"   DOI: {metadata.get('doi', 'N/A')}")

# 2. 测试 paper_id 生成
print("\n2. 测试 paper_id 生成...")
if metadata.get("doi"):
    paper_id = normalize_paper_id(metadata["doi"])
else:
    paper_id = normalize_paper_id(f"fallback:{pdf_path.stem}")
storage_id = generate_storage_id(paper_id)
print(f"   paper_id: {paper_id}")
print(f"   storage_id: {storage_id}")

# 3. 测试 PDF 转换
print("\n3. 测试 PDF 转 Markdown...")
try:
    markdown = convert_pdf_to_markdown(pdf_path)
    print(f"   Markdown 长度: {len(markdown)} 字符")
    print(f"   前 200 字符: {markdown[:200]}...")
except Exception as e:
    print(f"   转换失败: {e}")

# 4. 测试规范化
print("\n4. 测试规范化...")
try:
    paper_metadata = normalize_paper(
        candidate_md=markdown,
        metadata=metadata,
        paper_id=paper_id,
        storage_id=storage_id
    )
    print(f"   Paper ID: {paper_metadata.paper_id}")
    print(f"   Title: {paper_metadata.title}")
    print(f"   Authors: {[a.name for a in paper_metadata.authors]}")
    print(f"   摘要长度: {len(paper_metadata.abstract)} 字符")
except Exception as e:
    print(f"   规范化失败: {e}")

print("\n" + "=" * 60)
print("✅ Phase 2 核心功能测试完成")
print("=" * 60)
