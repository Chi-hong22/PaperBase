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


def _expand_env_vars_for_display(config: dict) -> dict:
    """展开环境变量用于显示"""
    import copy
    import re
    config = copy.deepcopy(config)

    if "llm" in config:
        llm = config["llm"]
        for key in ["base_url", "api_key", "model"]:
            if key in llm and isinstance(llm[key], str):
                value = llm[key]
                # 支持 ${VAR} 和 $VAR 格式
                if value.startswith("${") and value.endswith("}"):
                    env_var = value[2:-1]
                    llm[key] = os.getenv(env_var, f"(环境变量 {env_var} 未设置)")
                elif value.startswith("$"):
                    env_var = value[1:]
                    llm[key] = os.getenv(env_var, f"(环境变量 {env_var} 未设置)")

    return config


def _mask_secret(value: str) -> str:
    """脱敏显示密钥"""
    if not value:
        return "(未设置)"
    if len(value) < 10:
        return "(已设置)"
    return f"{value[:8]}...{value[-4:]}"
