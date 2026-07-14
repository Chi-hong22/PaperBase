import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).parents[2]


def _is_ignored(relative_path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "--quiet", "--", relative_path],
        cwd=REPO_ROOT,
        check=False,
    )
    return result.returncode == 0


def test_paperbase_derived_and_private_paths_are_ignored():
    ignored_paths = [
        "library/sources/example.pdf",
        "library/collections/example.md",
        "library/notes/example.md",
        "library/papers/p_example/source/source.pdf",
        "library/papers/p_example/assets/figure.png",
        "library/papers/graphify-out/cache.json",
        "index/fts.db",
    ]

    assert all(_is_ignored(path) for path in ignored_paths)
    assert not _is_ignored("library/papers/p_example.md")
