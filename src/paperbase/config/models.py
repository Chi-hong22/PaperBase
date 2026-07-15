"""配置数据模型（使用 Pydantic 验证）"""

import os
from typing import Literal
from pathlib import Path
from pydantic import BaseModel, field_validator, model_validator, Field
import logging

logger = logging.getLogger(__name__)


class ConfigError(Exception):
    """配置错误"""
    pass


class LLMAdvancedConfig(BaseModel):
    """LLM 高级配置"""
    timeout: int = 30
    max_input_tokens: int = 4000
    retry_on_failure: bool = True


class LLMConfig(BaseModel):
    """LLM 配置"""

    # OpenAI-compatible API 配置
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None

    # 可选配置
    advanced: LLMAdvancedConfig = LLMAdvancedConfig()

    # 向后兼容旧格式
    enabled: bool | None = None
    provider: str | None = None  # 向后兼容，但不再使用

    @model_validator(mode="after")
    def validate_and_migrate(self):
        """验证配置并迁移旧格式"""

        # 向后兼容：旧格式迁移
        if self.enabled is not None and self.base_url is None:
            logger.warning("Using legacy config format (enabled). Consider using base_url directly.")
            if not self.enabled:
                self.base_url = None

        # 迁移 provider 格式（已废弃）
        if self.provider is not None:
            logger.warning("provider field is deprecated. Use base_url directly.")
            # 不再自动推导，用户需要明确设置 base_url

        # 验证：如果配置了 base_url，必须配置 model
        if self.base_url and not self.model:
            raise ConfigError(
                "llm.model is required when llm.base_url is set.\n"
                "Example: llm.model = 'gpt-4o-mini'"
            )

        return self

    def is_enabled(self) -> bool:
        """LLM 是否启用"""
        return bool(self.base_url and self.model)

    def get_base_url(self) -> str:
        """获取 base_url"""
        return self.base_url or ""

    def get_api_key(self) -> str:
        """获取 api_key"""
        return self.api_key or "not-required"

    def get_timeout(self) -> int:
        """获取超时时间"""
        return self.advanced.timeout

    def get_max_input_tokens(self) -> int:
        """获取最大输入长度"""
        return self.advanced.max_input_tokens


class GraphAdvancedConfig(BaseModel):
    """图谱高级配置"""
    mode: Literal["incremental", "full"] = "incremental"
    ignore_patterns: list[str] = []
    process_timeout: float | None = None
    api_timeout: float | None = 600


class GraphConfig(BaseModel):
    """图谱配置"""

    # 新格式
    auto_update: Literal["never", "on_ingest", "on_entity_change", "always"] | bool = "on_entity_change"
    advanced: GraphAdvancedConfig = GraphAdvancedConfig()

    # 向后兼容
    update_mode: str | None = None
    auto_update_on: list[str] | None = None

    @model_validator(mode="after")
    def migrate_legacy(self):
        """迁移旧格式"""

        # 迁移 update_mode 到 advanced.mode
        if self.update_mode:
            self.advanced.mode = self.update_mode

        # 向后兼容 bool 类型的 auto_update
        if isinstance(self.auto_update, bool):
            if self.auto_update:
                self.auto_update = "on_entity_change"
            else:
                self.auto_update = "never"

        return self

    def get_triggers(self) -> list[str]:
        """获取触发条件"""
        if self.auto_update == "never":
            return []
        elif self.auto_update == "on_ingest":
            return ["paper_ingest"]
        elif self.auto_update == "on_entity_change":
            return ["entity_change", "paper_ingest"]
        elif self.auto_update == "always":
            return ["any"]
        return []

    def get_mode(self) -> str:
        """获取更新模式"""
        # update_mode 是向后兼容字段，优先使用
        if self.update_mode is not None:
            return self.update_mode
        # 否则使用 advanced.mode
        return self.advanced.mode

    def get_ignore_patterns(self) -> list[str]:
        """获取忽略模式"""
        return [
            "sources/",
            "registry/",
            "**/source/",
            "**/*.pdf",
            "**/chunks.jsonl",
            "**/references.jsonl",
        ]

    def get_process_timeout(self) -> float | None:
        """获取 PaperBase 对 graphify 进程设置的外层超时。"""
        return self.advanced.process_timeout

    def get_api_timeout(self) -> float | None:
        """获取 graphify 单次 LLM 请求超时。"""
        return self.advanced.api_timeout


class AdapterConfig(BaseModel):
    """Adapter 配置"""

    enabled: bool = True
    artifact_mode: str = "markdown-assets"
    asset_profile: str = "body"
    include_refs: str = "all"
    max_tokens: str = "full_text"
    allow_metadata_only: bool = False

    def get_artifact_mode(self) -> str:
        """获取 artifact_mode"""
        return self.artifact_mode

    def get_asset_profile(self) -> str:
        """获取 asset_profile"""
        return self.asset_profile

    def get_include_refs(self) -> str:
        """获取 include_refs"""
        return self.include_refs

    def get_max_tokens(self) -> str:
        """获取 max_tokens"""
        return self.max_tokens

    def get_allow_metadata_only(self) -> bool:
        """获取 allow_metadata_only"""
        return self.allow_metadata_only


class GraphifyConfig(BaseModel):
    """Graphify 配置（向后兼容）"""

    auto_update: bool = True
    ignore_patterns: list[str] = []
    _explicitly_set: bool = False

    @model_validator(mode="before")
    @classmethod
    def mark_explicit(cls, data):
        """标记配置是否被显式设置"""
        if isinstance(data, dict) and data:
            # 如果传入了非空字典，说明配置文件中显式包含了 graphify 字段
            if "_explicitly_set" not in data:
                data["_explicitly_set"] = True
        return data

    @model_validator(mode="after")
    def warn_deprecated(self):
        """警告：graphify 配置已废弃（仅在显式配置时）"""
        if self._explicitly_set:
            logger.warning(
                "graphify section is deprecated. "
                "Please use 'graph.auto_update' and ignore patterns in .graphifyignore instead."
            )
        return self


class PaperBaseConfig(BaseModel):
    """PaperBase 完整配置"""

    # 项目元信息
    project: dict = Field(default_factory=dict)

    # 核心配置
    llm: LLMConfig = LLMConfig()
    graph: GraphConfig = GraphConfig()

    # Adapter 配置
    adapters: dict = Field(default_factory=dict)

    # 向后兼容字段
    paths: dict = Field(default_factory=dict)
    storage: dict = Field(default_factory=dict)
    state_machine: dict = Field(default_factory=dict)
    terminology: dict = Field(default_factory=dict)
    graphify: GraphifyConfig = GraphifyConfig()

    @model_validator(mode="after")
    def normalize_adapters(self):
        """规范化 adapters 配置"""

        # 确保 paper_fetch 存在
        if "paper_fetch" not in self.adapters:
            self.adapters["paper_fetch"] = AdapterConfig().model_dump()
        elif not isinstance(self.adapters["paper_fetch"], AdapterConfig):
            # 从 dict 转换为 AdapterConfig
            self.adapters["paper_fetch"] = AdapterConfig.model_validate(self.adapters["paper_fetch"])

        return self

    def get_paper_fetch_adapter(self) -> AdapterConfig:
        """获取 paper_fetch adapter 配置"""
        adapter = self.adapters.get("paper_fetch")
        if isinstance(adapter, AdapterConfig):
            return adapter
        return AdapterConfig.model_validate(adapter)
