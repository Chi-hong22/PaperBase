#!/usr/bin/env python3
"""Phase 5 验证脚本

验证搜索和查询功能的完整性
"""

import sys
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel


def check_file_exists(file_path: Path, description: str) -> bool:
    """检查文件是否存在"""
    if file_path.exists():
        return True
    return False


def check_module_importable(module_name: str) -> bool:
    """检查模块是否可导入"""
    try:
        __import__(module_name)
        return True
    except ImportError:
        return False


def verify_phase5(base_dir: Path) -> dict:
    """
    验证 Phase 5 实现

    Returns:
        dict: 验证结果
    """
    console = Console()
    results = {
        "core_modules": [],
        "cli_commands": [],
        "test_files": [],
        "data_files": [],
        "overall": True
    }

    console.print("\n[bold cyan]Phase 5 验证 - 搜索和查询功能[/bold cyan]\n")

    # 1. 检查核心模块
    console.print("[bold]1. 核心模块检查[/bold]")

    core_modules = [
        ("paperbase.core.search_engine", "SearchEngine - 全文检索引擎"),
        ("paperbase.core.graph_query", "GraphQuery - 图谱查询功能"),
    ]

    for module_name, description in core_modules:
        importable = check_module_importable(module_name)
        status = "[green]✓[/green]" if importable else "[red]✗[/red]"
        console.print(f"  {status} {description}")
        results["core_modules"].append({
            "name": module_name,
            "description": description,
            "status": importable
        })
        if not importable:
            results["overall"] = False

    # 2. 检查 CLI 命令
    console.print("\n[bold]2. CLI 命令检查[/bold]")

    cli_commands = [
        (base_dir / "src" / "paperbase" / "cli" / "commands" / "search.py", "search 命令"),
        (base_dir / "src" / "paperbase" / "cli" / "commands" / "query.py", "query 命令"),
    ]

    for file_path, description in cli_commands:
        exists = check_file_exists(file_path, description)
        status = "[green]✓[/green]" if exists else "[red]✗[/red]"
        console.print(f"  {status} {description}: {file_path.name}")
        results["cli_commands"].append({
            "file": str(file_path),
            "description": description,
            "status": exists
        })
        if not exists:
            results["overall"] = False

    # 3. 检查测试文件
    console.print("\n[bold]3. 测试文件检查[/bold]")

    test_files = [
        (base_dir / "tests" / "unit" / "test_search_engine.py", "SearchEngine 单元测试"),
        (base_dir / "tests" / "unit" / "test_graph_query.py", "GraphQuery 单元测试"),
        (base_dir / "tests" / "integration" / "test_search_workflow.py", "搜索工作流集成测试"),
    ]

    for file_path, description in test_files:
        exists = check_file_exists(file_path, description)
        status = "[green]✓[/green]" if exists else "[red]✗[/red]"
        console.print(f"  {status} {description}")
        results["test_files"].append({
            "file": str(file_path),
            "description": description,
            "status": exists
        })
        if not exists:
            results["overall"] = False

    # 4. 检查功能可用性
    console.print("\n[bold]4. 功能可用性检查[/bold]")

    try:
        from paperbase.core.search_engine import SearchEngine
        console.print("  [green]✓[/green] SearchEngine 类可导入")

        # 检查关键方法
        required_methods = ["build_index", "search", "close"]
        for method in required_methods:
            if hasattr(SearchEngine, method):
                console.print(f"    [green]✓[/green] {method}() 方法存在")
            else:
                console.print(f"    [red]✗[/red] {method}() 方法缺失")
                results["overall"] = False

    except ImportError as e:
        console.print(f"  [red]✗[/red] SearchEngine 导入失败: {e}")
        results["overall"] = False

    try:
        from paperbase.core.graph_query import find_related_papers, find_papers_by_topic
        console.print("  [green]✓[/green] GraphQuery 函数可导入")

        # 检查函数签名
        import inspect

        sig1 = inspect.signature(find_related_papers)
        if "graph_dir" in sig1.parameters and "paper_id" in sig1.parameters:
            console.print("    [green]✓[/green] find_related_papers() 签名正确")
        else:
            console.print("    [red]✗[/red] find_related_papers() 签名错误")
            results["overall"] = False

        sig2 = inspect.signature(find_papers_by_topic)
        if "graph_dir" in sig2.parameters and "topic" in sig2.parameters:
            console.print("    [green]✓[/green] find_papers_by_topic() 签名正确")
        else:
            console.print("    [red]✗[/red] find_papers_by_topic() 签名错误")
            results["overall"] = False

    except ImportError as e:
        console.print(f"  [red]✗[/red] GraphQuery 导入失败: {e}")
        results["overall"] = False

    # 5. 检查数据文件状态（可选）
    console.print("\n[bold]5. 数据文件状态（可选）[/bold]")

    data_files = [
        (base_dir / "index" / "fts.db", "FTS5 索引文件"),
        (base_dir / "graph" / "graph.json", "图谱 JSON 文件"),
    ]

    for file_path, description in data_files:
        exists = check_file_exists(file_path, description)
        status = "[yellow]○[/yellow]" if not exists else "[green]✓[/green]"
        hint = " (需要运行 paperbase index)" if not exists and "index" in str(file_path) else ""
        hint = " (需要运行 paperbase graph)" if not exists and "graph" in str(file_path) else hint
        console.print(f"  {status} {description}{hint}")
        results["data_files"].append({
            "file": str(file_path),
            "description": description,
            "status": exists
        })

    # 6. 生成总结
    console.print("\n" + "="*60)

    if results["overall"]:
        console.print(Panel(
            "[bold green]Phase 5 验证通过！[/bold green]\n\n"
            "所有核心功能已正确实现：\n"
            "  • SearchEngine 全文检索\n"
            "  • GraphQuery 图谱查询\n"
            "  • search 命令\n"
            "  • query 命令\n"
            "  • 集成测试\n\n"
            "[dim]提示：运行测试以验证功能正确性[/dim]\n"
            "[dim]  pytest tests/unit/test_search_engine.py[/dim]\n"
            "[dim]  pytest tests/unit/test_graph_query.py[/dim]\n"
            "[dim]  pytest tests/integration/test_search_workflow.py[/dim]",
            title="验证结果",
            border_style="green"
        ))
    else:
        console.print(Panel(
            "[bold red]Phase 5 验证失败！[/bold red]\n\n"
            "部分功能缺失或不可用，请检查上述错误。",
            title="验证结果",
            border_style="red"
        ))

    return results


def main():
    """主函数"""
    # 获取项目根目录
    script_dir = Path(__file__).parent
    base_dir = script_dir.parent

    # 添加 src 到 sys.path
    src_dir = base_dir / "src"
    if src_dir.exists():
        sys.path.insert(0, str(src_dir))

    # 执行验证
    results = verify_phase5(base_dir)

    # 返回状态码
    sys.exit(0 if results["overall"] else 1)


if __name__ == "__main__":
    main()
