"""Skills 安装和配置脚本"""

import subprocess
import sys
from pathlib import Path


def run_command(cmd: list[str], description: str):
    """运行命令并处理错误"""
    print(f"\n{'='*60}")
    print(f"{description}")
    print(f"{'='*60}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print(f"❌ 失败: {result.stderr}", file=sys.stderr)
        return False
    print("✅ 成功")
    return True


def main():
    base_dir = Path(__file__).parent.parent
    skills_dir = base_dir / "skills"
    skills_dir.mkdir(exist_ok=True)

    print("🚀 PaperBase Skills 安装")

    success_count = 0
    total_count = 4

    # 1. paper-fetch-skill
    if not (skills_dir / "paper-fetch-skill").exists():
        if run_command(
            ["git", "clone", "https://github.com/Dictation354/paper-fetch-skill.git",
             str(skills_dir / "paper-fetch-skill")],
            "📥 克隆 paper-fetch-skill"
        ):
            success_count += 1
    else:
        print("\n✅ paper-fetch-skill 已存在，跳过")
        success_count += 1

    # 2. citation-check-skill
    print("\n" + "="*60)
    print("⚠️  citation-check-skill 需要手动下载")
    print("="*60)
    print("下载地址: https://github.com/serenakeyitan/citation-check-skill/releases")
    print("解压到: skills/citation-check-skill/")

    # 3. zotero-mcp
    if run_command(
        ["uv", "tool", "install", "zotero-mcp-server"],
        "📦 安装 zotero-mcp"
    ):
        success_count += 1

    # 4. graphify
    if run_command(
        ["uv", "tool", "install", "graphify"],
        "📦 安装 graphify"
    ):
        success_count += 1

    print("\n" + "="*60)
    print(f"✨ Skills 安装完成 ({success_count}/{total_count} 成功)")
    print("="*60)


if __name__ == "__main__":
    main()
