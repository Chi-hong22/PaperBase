#!/usr/bin/env python3
"""
Batch Ingest Helper Script

Assists with batch ingestion of papers from various sources.
"""

import sys
import subprocess
import time
from pathlib import Path
from typing import List, Dict


def parse_batch_file(file_path: Path) -> List[str]:
    """Parse batch file and extract identifiers"""
    identifiers = []

    with open(file_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue

            # Validate identifier format
            if any(pattern in line.lower() for pattern in ['doi:', 'arxiv:', 'pmid:', 'http']):
                identifiers.append(line)
            elif Path(line).exists():
                # Local file path
                identifiers.append(line)
            else:
                print(f"⚠️  Line {line_num}: 无效标识符 '{line}'")

    return identifiers


def ingest_paper(identifier: str, base_dir: Path, skip_graph: bool = True) -> bool:
    """Ingest a single paper"""
    cmd = ["uv", "run", "paperbase", "ingest"]

    if identifier.startswith('/') or Path(identifier).exists():
        cmd.extend(["--file", identifier])
    else:
        cmd.append(identifier)

    if skip_graph:
        cmd.append("--no-graph")

    try:
        result = subprocess.run(
            cmd,
            cwd=base_dir,
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode == 0:
            print(f"✅ {identifier}")
            return True
        else:
            print(f"❌ {identifier}")
            if result.stderr:
                print(f"   Error: {result.stderr.strip()}")
            return False
    except subprocess.TimeoutExpired:
        print(f"⏱️  {identifier} - 超时")
        return False
    except Exception as e:
        print(f"❌ {identifier} - {e}")
        return False


def main():
    """Main batch ingest workflow"""
    if len(sys.argv) < 2:
        print("Usage: python batch_ingest.py <batch_file>")
        print("\nBatch file format:")
        print("  doi:10.1234/abc")
        print("  arxiv:1706.03762")
        print("  /path/to/paper.pdf")
        print("  # Comments start with #")
        sys.exit(1)

    batch_file = Path(sys.argv[1])

    if not batch_file.exists():
        print(f"❌ 文件不存在: {batch_file}")
        sys.exit(1)

    # Determine base directory
    base_dir = Path.cwd()
    if not (base_dir / "library").exists():
        base_dir = base_dir.parent
        if not (base_dir / "library").exists():
            print("❌ 未找到 PaperBase 库")
            sys.exit(1)

    print(f"📁 Base Directory: {base_dir}")
    print(f"📄 Batch File: {batch_file}\n")

    # Parse batch file
    identifiers = parse_batch_file(batch_file)

    if not identifiers:
        print("❌ 批处理文件为空或无有效标识符")
        sys.exit(1)

    print(f"📋 找到 {len(identifiers)} 个标识符\n")
    print("=" * 60)

    # Ingest papers
    start_time = time.time()
    success_count = 0
    failed = []

    for i, identifier in enumerate(identifiers, 1):
        print(f"\n[{i}/{len(identifiers)}] ", end="")

        if ingest_paper(identifier, base_dir, skip_graph=True):
            success_count += 1
        else:
            failed.append(identifier)

        # Small delay to avoid overwhelming the system
        time.sleep(1)

    elapsed = time.time() - start_time

    # Summary
    print("\n" + "=" * 60)
    print(f"\n✅ 成功: {success_count}/{len(identifiers)}")
    if failed:
        print(f"❌ 失败: {len(failed)}")
        print("\n失败列表:")
        for identifier in failed:
            print(f"  - {identifier}")

    print(f"\n⏱️  总耗时: {elapsed:.1f} 秒")
    print(f"📊 平均速度: {elapsed/len(identifiers):.1f} 秒/篇")

    # Suggest graph update
    if success_count > 0:
        print("\n💡 建议:")
        print(f"   cd {base_dir}")
        print("   paperbase graph update")

    sys.exit(0 if len(failed) == 0 else 1)


if __name__ == "__main__":
    main()
