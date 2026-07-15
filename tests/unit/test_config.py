"""配置系统单元测试"""

import pytest
from pathlib import Path
from pydantic import ValidationError
from paperbase.config.models import (
    LLMConfig,
    GraphConfig,
    PaperBaseConfig,
    ConfigError,
)


class TestLLMConfig:
    """测试 LLM 配置"""

    def test_is_enabled(self):
        """测试 is_enabled"""
        config1 = LLMConfig(base_url="https://api.openai.com/v1", model="gpt-4o")
        assert config1.is_enabled() is True

        config2 = LLMConfig()
        assert config2.is_enabled() is False

    def test_dependency_validation_missing_model(self):
        """测试缺少 model 时的验证"""
        with pytest.raises(ConfigError, match="model is required"):
            LLMConfig(base_url="https://api.openai.com/v1")

    def test_get_base_url(self):
        """测试 get_base_url"""
        config = LLMConfig(base_url="https://api.openai.com/v1", model="gpt-4o")
        assert config.get_base_url() == "https://api.openai.com/v1"

    def test_get_api_key(self):
        """测试 get_api_key"""
        config = LLMConfig(base_url="https://api.openai.com/v1", model="gpt-4o", api_key="sk-test")
        assert config.get_api_key() == "sk-test"

        config2 = LLMConfig(base_url="http://localhost:11434/v1", model="llama3.2")
        assert config2.get_api_key() == "not-required"

    def test_disabled_llm(self):
        """测试禁用的 LLM"""
        config = LLMConfig()
        assert config.is_enabled() is False
        assert config.get_base_url() == ""

    def test_default_values(self):
        """测试默认值"""
        config = LLMConfig(base_url="https://api.openai.com/v1", model="gpt-4o")
        assert config.get_timeout() == 30
        assert config.get_max_input_tokens() == 4000


class TestGraphConfig:
    """测试 GraphConfig"""

    def test_auto_update_string(self):
        """测试 auto_update 字符串值"""
        config = GraphConfig(auto_update="on_entity_change")
        assert config.auto_update == "on_entity_change"
        assert config.get_triggers() == ["entity_change", "paper_ingest"]

    def test_auto_update_bool_migration(self):
        """测试 bool 类型自动迁移"""
        config = GraphConfig(auto_update=True)
        assert config.auto_update == "on_entity_change"

    def test_auto_update_false(self):
        """测试 auto_update=False"""
        config = GraphConfig(auto_update=False)
        assert config.auto_update == "never"
        assert config.get_triggers() == []

    def test_get_mode(self):
        """测试 get_mode"""
        config = GraphConfig()
        assert config.get_mode() == "incremental"
        assert config.advanced.mode == "incremental"

    def test_graphify_timeouts(self):
        """外层批处理默认不限制，总体请求沿用 Graphify 默认值。"""
        config = GraphConfig()
        assert config.get_process_timeout() is None
        assert config.get_api_timeout() == 600
        assert config.get_minimum_canonical_body_chars() == 500

        configured = GraphConfig(
            advanced={"process_timeout": 900, "api_timeout": 120}
        )
        assert configured.get_process_timeout() == 900
        assert configured.get_api_timeout() == 120
