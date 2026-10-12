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
    assert _is_ignored("library/papers/p_example.md")


def test_graphify_reincludes_local_canonical_markdown():
    rules = [
        line.strip()
        for line in (
            REPO_ROOT / "library" / "papers" / ".graphifyignore"
        ).read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    # 本地 Canonical Markdown 必须被重新纳入 Graphify 扫描
    assert "!p_*.md" in rules

    # 任何针对具体论文的精确排除（BLOCKED 等）都必须排在重新纳入规则之后，
    # 否则会被 !p_*.md 覆盖而失效。
    reinclude_index = rules.index("!p_*.md")
    specific_rules = [
        rule for rule in rules if rule.startswith("p_") and rule.endswith(".md")
    ]
    assert all(rules.index(rule) > reinclude_index for rule in specific_rules)
