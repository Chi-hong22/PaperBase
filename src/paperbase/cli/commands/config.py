"""config 命令实现 - 配置管理和诊断"""

import click
from rich.console import Console
from rich.table import Table
from pathlib import Path
import yaml
import os


@click.group()
def config():
    """配置管理和诊断"""
    pass


@config.command()
@click.pass_context
def show(ctx):
    """显示当前配置"""
    console = Console()
    base_dir = ctx.obj["base_dir"]
    config_path = base_dir / "config" / "paperbase.yaml"

    if not config_path.exists():
        console.print(f"[red]配置文件不存在: {config_path}[/red]")
        ctx.exit(1)

    # 读取配置
    with open(config_path, "r", encoding="utf-8") as f:
        raw_config = yaml.safe_load(f)

    # 展开环境变量
    config_display = _expand_env_vars_for_display(raw_config)

    console.print(f"[cyan]配置文件:[/cyan] {config_path}")
    console.print()

    # 显示 LLM 配置
    if "llm" in config_display:
        console.print("[bold]LLM 配置:[/bold]")
        llm = config_display["llm"]

        base_url = llm.get('base_url', '')
        model = llm.get('model', '')
        is_enabled = bool(base_url and model)

        console.print(f"  enabled: {is_enabled}")
        console.print(f"  base_url: {base_url if base_url else '(未设置)'}")
        console.print(f"  api_key: {_mask_secret(llm.get('api_key', '(未设置)'))}")
        console.print(f"  model: {model if model else '(未设置)'}")

        if 'advanced' in llm:
            adv = llm['advanced']
            console.print(f"  timeout: {adv.get('timeout', 30)}")
            console.print(f"  max_input_tokens: {adv.get('max_input_tokens', 4000)}")
        console.print()

    # 显示知识图谱配置
    if "graph" in config_display:
        console.print("[bold]知识图谱配置:[/bold]")
        graph = config_display["graph"]
        auto_update = graph.get('auto_update', 'on_entity_change')
        console.print(f"  auto_update: {auto_update}")

        if 'advanced' in graph:
            adv = graph['advanced']
            console.print(f"  mode: {adv.get('mode', 'incremental')}")
        elif 'update_mode' in graph:
            console.print(f"  mode: {graph.get('update_mode', 'incremental')}")
        console.print()

    # 显示路径配置
    if "paths" in config_display:
        console.print("[bold]路径配置:[/bold]")
        paths = config_display["paths"]
        for key, value in paths.items():
            console.print(f"  {key}: {value}")


@config.command()
@click.pass_context
def path(ctx):
    """显示配置文件路径"""
    console = Console()
    base_dir = ctx.obj["base_dir"]
    config_path = base_dir / "config" / "paperbase.yaml"

    console.print(f"[cyan]配置文件路径:[/cyan]")
    console.print(f"  {config_path}")
    console.print()

    if config_path.exists():
        console.print(f"[green]✓ 文件存在[/green]")
    else:
        console.print(f"[red]✗ 文件不存在[/red]")


@config.command(name="check-llm")
@click.pass_context
def check_llm(ctx):
    """验证 LLM 配置"""
    console = Console()
    base_dir = ctx.obj["base_dir"]

    console.print("[cyan]检查 LLM 配置...[/cyan]\n")

    # 1. 检查配置文件
    config_path = base_dir / "config" / "paperbase.yaml"

    if not config_path.exists():
        console.print(f"[red]✗ 配置文件不存在: {config_path}[/red]")
        ctx.exit(1)

    console.print(f"[green]✓ 配置文件存在[/green]")

    # 2. 读取配置
    with open(config_path, "r", encoding="utf-8") as f:
        raw_config = yaml.safe_load(f)

    llm_config = raw_config.get("llm", {})

    # 检查是否启用（通过 base_url 和 model 判断）
    base_url = llm_config.get("base_url")
    model = llm_config.get("model")

    # 展开环境变量
    if base_url and base_url.startswith("${"):
        env_var = base_url[2:-1]
        base_url = os.getenv(env_var, "")

    if model and model.startswith("${"):
        env_var = model[2:-1]
        model = os.getenv(env_var, "")

    enabled = bool(base_url and model)

    if enabled:
        console.print(f"[green]✓ LLM 已启用[/green]")
    else:
        console.print(f"[yellow]⚠ LLM 未启用[/yellow]")
        console.print("  启用方法:")
        console.print("  1. 编辑 config/paperbase.yaml")
        console.print("  2. 设置 llm.base_url 和 llm.model")
        console.print("  3. 配置环境变量 PAPERBASE_LLM_BASE_URL, PAPERBASE_LLM_MODEL")
        ctx.exit(1)

    # 4. 检查环境变量
    console.print()
    console.print("[cyan]检查环境变量...[/cyan]")

    env_vars = {
        "PAPERBASE_LLM_BASE_URL": os.getenv("PAPERBASE_LLM_BASE_URL"),
        "PAPERBASE_LLM_API_KEY": os.getenv("PAPERBASE_LLM_API_KEY"),
        "PAPERBASE_LLM_MODEL": os.getenv("PAPERBASE_LLM_MODEL"),
    }

    all_set = True
    for key, value in env_vars.items():
        if value:
            display_value = _mask_secret(value) if "KEY" in key else value
            console.print(f"[green]✓ {key}: {display_value}[/green]")
        else:
            console.print(f"[red]✗ {key}: (未设置)[/red]")
            all_set = False

    if not all_set:
        console.print()
        console.print("[yellow]部分环境变量未设置，请检查配置文件。[/yellow]")
        ctx.exit(1)

    # 5. 测试初始化
    console.print()
    console.print("[cyan]测试 LLM 客户端初始化...[/cyan]")

    try:
        from paperbase.core.llm_client import LLMClient

        client = LLMClient()

        if client.enabled:
            console.print(f"[green]✓ 初始化成功[/green]")
            console.print(f"  model: {client.model}")
            console.print(f"  base_url: {client.config['llm']['base_url']}")
        else:
            console.print(f"[red]✗ 初始化失败[/red]")
            ctx.exit(1)

    except Exception as e:
        console.print(f"[red]✗ 初始化失败: {e}[/red]")
        ctx.exit(1)

    console.print()
    console.print("[green]✓ 配置检查通过[/green]")


def _expand_env_vars_for_display(config: dict) -> dict:
    """展开环境变量用于显示"""
    import copy
    config = copy.deepcopy(config)

    if "llm" in config:
        llm = config["llm"]
        for key in ["base_url", "api_key", "model"]:
            if key in llm and isinstance(llm[key], str):
                value = llm[key]
                if value.startswith("${") and value.endswith("}"):
                    env_var = value[2:-1]
                    llm[key] = os.getenv(env_var, f"(环境变量 {env_var} 未设置)")

    return config


def _mask_secret(value: str) -> str:
    """脱敏显示密钥"""
    if not value or len(value) < 10:
        return "(已设置)"
    return f"{value[:8]}...{value[-4:]}"
