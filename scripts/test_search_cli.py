"""端到端测试 search CLI 命令"""

from pathlib import Path
from paperbase.core.search_engine import SearchEngine
from paperbase.core.registry import PaperRegistry
from paperbase.schemas.manifest import PaperState
import json
import tempfile
import shutil
import subprocess


def test_search_cli_e2e():
    """端到端测试 search CLI 命令"""
    # 创建临时目录
    test_dir = Path(tempfile.mkdtemp())

    try:
        # 创建目录结构
        library_path = test_dir / "library" / "papers"
        index_path = test_dir / "index"
        registry_path = test_dir / "registry"

        library_path.mkdir(parents=True)
        index_path.mkdir(parents=True)
        registry_path.mkdir(parents=True)

        print(f"测试目录: {test_dir}")

        # 创建测试论文
        paper_dir = library_path / "paper001"
        paper_dir.mkdir()

        chunks = [
            {
                "id": "chunk001",
                "paper_id": "paper001",
                "content": "Machine learning is a subset of artificial intelligence.",
                "position": 0
            },
            {
                "id": "chunk002",
                "paper_id": "paper001",
                "content": "Deep learning uses neural networks with multiple layers.",
                "position": 1
            }
        ]

        with open(paper_dir / "chunks.jsonl", "w", encoding="utf-8") as f:
            for chunk in chunks:
                f.write(json.dumps(chunk) + "\n")

        print("✓ 创建测试数据")

        # 初始化 registry
        registry = PaperRegistry(registry_path / "papers.db")
        registry.register_paper(
            paper_id="paper001",
            storage_id="paper001",
            state=PaperState.READY,
            title="Introduction to Machine Learning",
            authors=["John Doe"],
            year=2024
        )
        registry.close()

        print("✓ 初始化 registry")

        # 构建索引
        engine = SearchEngine(index_path / "fts.db", library_path)
        engine.build_index()
        engine.close()

        print("✓ 构建搜索索引")

        # 测试 CLI 命令
        result = subprocess.run(
            ["uv", "run", "paperbase", "--base-dir", str(test_dir), "search", "machine learning"],
            capture_output=True,
            text=True
        )

        print("\n--- CLI 输出 ---")
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        print("--- 输出结束 ---\n")

        # 验证输出
        assert result.returncode == 0, f"命令执行失败: {result.returncode}"
        # 标题可能被换行，检查关键词
        assert "Introduction" in result.stdout and "Machine" in result.stdout, "输出应包含论文标题关键词"
        assert "找到" in result.stdout, "输出应包含结果计数"
        assert "learning" in result.stdout, "输出应包含搜索关键词"

        print("✓ CLI 命令测试通过")

        # 测试无结果情况
        result = subprocess.run(
            ["uv", "run", "paperbase", "--base-dir", str(test_dir), "search", "quantum computing"],
            capture_output=True,
            text=True
        )

        assert result.returncode == 0
        assert "未找到匹配结果" in result.stdout

        print("✓ 无结果测试通过")

        # 测试 limit 参数
        result = subprocess.run(
            ["uv", "run", "paperbase", "--base-dir", str(test_dir), "search", "learning", "-n", "1"],
            capture_output=True,
            text=True
        )

        assert result.returncode == 0
        assert "learning" in result.stdout.lower()

        print("✓ Limit 参数测试通过")

        print("\n✓ 所有 CLI 测试通过")

    finally:
        # 清理
        shutil.rmtree(test_dir, ignore_errors=True)
        print("\n✓ 清理完成")


if __name__ == "__main__":
    test_search_cli_e2e()
