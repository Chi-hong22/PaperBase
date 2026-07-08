"""配置加载器（支持环境变量展开、验证、友好错误提示）"""

import os
import re
from pathlib import Path
import yaml
from pydantic import ValidationError
import logging

from .models import PaperBaseConfig, ConfigError

logger = logging.getLogger(__name__)


def expand_env_vars(config: dict) -> None:
    """
    展开配置中的环境变量 ${VAR}

    Args:
        config: 配置字典（会被原地修改）
    """
    def _expand_value(value):
        """递归展开值"""
        if isinstance(value, str):
            # 匹配 ${VAR} 或 $VAR
            if value.startswith("${") and value.endswith("}"):
                env_var = value[2:-1]
                return os.getenv(env_var, "")
            elif value.startswith("$") and not value.startswith("${"):
                env_var = value[1:]
                return os.getenv(env_var, "")
            return value
        elif isinstance(value, dict):
            return {k: _expand_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [_expand_value(item) for item in value]
        else:
            return value

    # 原地修改
    for key, value in config.items():
        config[key] = _expand_value(value)


def load_config(config_path: Path | None = None) -> PaperBaseConfig:
    """
    加载并验证配置文件

    Args:
        config_path: 配置文件路径（默认为项目根目录的 config/paperbase.yaml）

    Returns:
        验证后的配置对象

    Raises:
        ConfigError: 配置无效
    """
    # 默认配置路径
    if config_path is None:
        # 从 src/paperbase/config/loader.py 向上 3 级到项目根目录
        project_root = Path(__file__).parent.parent.parent.parent
        config_path = project_root / "config" / "paperbase.yaml"

    # 检查文件是否存在
    if not config_path.exists():
        logger.warning(f"Config file not found: {config_path}")
        logger.info("Using default config (minimal features enabled)")
        return PaperBaseConfig()

    # 加载 YAML
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            raw_config = yaml.safe_load(f)
    except Exception as e:
        raise ConfigError(
            f"Failed to load config file: {config_path}\n"
            f"Error: {e}\n"
            f"Please check YAML syntax."
        ) from e

    if raw_config is None:
        raw_config = {}

    # 展开环境变量
    expand_env_vars(raw_config)

    # 使用 Pydantic 验证
    try:
        config = PaperBaseConfig.model_validate(raw_config)
        logger.debug(f"Config loaded successfully from {config_path}")
        return config

    except ValidationError as e:
        # 提供友好的错误信息
        error_msg = _format_validation_error(e, config_path)
        raise ConfigError(error_msg) from e


def _format_validation_error(error: ValidationError, config_path: Path) -> str:
    """
    格式化验证错误信息，提供修复建议

    Args:
        error: Pydantic ValidationError
        config_path: 配置文件路径

    Returns:
        友好的错误信息
    """
    lines = [
        f"Configuration validation failed: {config_path}",
        "",
        "Errors found:",
    ]

    for err in error.errors():
        loc = " -> ".join(str(l) for l in err["loc"])
        msg = err["msg"]
        lines.append(f"  - {loc}: {msg}")

    lines.append("")
    lines.append("Common fixes:")

    # 根据错误类型提供修复建议
    error_str = str(error)

    if "llm.base_url" in error_str or "llm.model" in error_str or "llm.api_key" in error_str:
        lines.extend([
            "  LLM Configuration:",
            "    1. Set llm.enabled to: true",
            "    2. Set llm.base_url (e.g., 'https://api.openai.com/v1')",
            "    3. Set llm.model (e.g., 'gpt-4o-mini')",
            "    4. Set environment variable: PAPERBASE_LLM_API_KEY",
            "",
            "  Example:",
            "    llm:",
            "      enabled: true",
            "      base_url: ${PAPERBASE_LLM_BASE_URL}",
            "      api_key: ${PAPERBASE_LLM_API_KEY}",
            "      model: ${PAPERBASE_LLM_MODEL}",
        ])

    if "graph.auto_update" in error_str:
        lines.extend([
            "  Graph Configuration:",
            "    Set graph.auto_update to: true / false",
            "",
            "  Example:",
            "    graph:",
            "      auto_update: true",
            "      update_mode: incremental",
        ])

    if "adapters" in error_str:
        lines.extend([
            "  Adapter Configuration:",
            "    Configure adapter parameters directly",
            "",
            "  Example:",
            "    adapters:",
            "      paper_fetch:",
            "        enabled: true",
            "        artifact_mode: markdown-assets",
            "        asset_profile: body",
        ])

    lines.append("")
    lines.append(f"For more details, see: docs/improvements/config-refactoring.md")

    return "\n".join(lines)


def get_default_config_path() -> Path:
    """获取默认配置文件路径"""
    project_root = Path(__file__).parent.parent.parent.parent
    return project_root / "config" / "paperbase.yaml"


def validate_config_file(config_path: Path | None = None) -> tuple[bool, str]:
    """
    验证配置文件（用于 CLI 命令）

    Args:
        config_path: 配置文件路径

    Returns:
        (is_valid, message)
    """
    try:
        config = load_config(config_path)

        lines = ["Configuration is valid!", ""]

        # 显示关键配置
        if config.llm.is_enabled():
            lines.append(f"✓ LLM enabled: {config.llm.base_url} / {config.llm.model}")
        else:
            lines.append("○ LLM disabled")

        lines.append(f"✓ Graph auto-update: {config.graph.auto_update}")

        adapter = config.get_paper_fetch_adapter()
        if adapter.enabled:
            lines.append(f"✓ Paper fetch: {adapter.artifact_mode}")
        else:
            lines.append("○ Paper fetch disabled")

        return True, "\n".join(lines)

    except ConfigError as e:
        return False, str(e)
