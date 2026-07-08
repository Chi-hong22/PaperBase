"""测试 LLMClient 与新配置系统的集成"""

import pytest
from pathlib import Path
import tempfile
import yaml
from paperbase.core.llm_client import LLMClient
from paperbase.config import PaperBaseConfig, LLMConfig


class TestLLMClientIntegration:
    """测试 LLMClient 与配置系统集成"""

    def test_init_with_config_object(self):
        """测试使用 PaperBaseConfig 对象初始化"""
        config = PaperBaseConfig(
            llm=LLMConfig(
                enabled=True,
                base_url="https://api.openai.com/v1",
                model="gpt-4o-mini",
                api_key="test-key"
            )
        )

        client = LLMClient(config=config)
        assert client.config == config
        assert client.enabled is True

    def test_init_with_config_path(self):
        """测试使用配置文件路径初始化"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({
                "llm": {
                    "enabled": True,
                    "base_url": "https://api.openai.com/v1",
                    "model": "gpt-4o-mini",
                    "api_key": "test-key"
                }
            }, f)
            config_path = Path(f.name)

        try:
            client = LLMClient(config_path=config_path)
            assert client.config.llm.is_enabled() is True
            assert client.config.llm.base_url == "https://api.openai.com/v1"

        finally:
            config_path.unlink()

    def test_init_with_dict_backward_compat(self):
        """测试使用字典初始化（向后兼容）"""
        config_dict = {
            "llm": {
                "enabled": True,
                "base_url": "https://api.openai.com/v1",
                "model": "gpt-4o-mini",
                "api_key": "test-key"
            }
        }

        client = LLMClient(config=config_dict)
        assert client.config.llm.is_enabled() is True
        assert client.config.llm.base_url == "https://api.openai.com/v1"

    def test_init_disabled_llm(self):
        """测试禁用 LLM"""
        config = PaperBaseConfig(
            llm=LLMConfig(enabled=False)
        )

        client = LLMClient(config=config)
        assert client.enabled is False
        assert client.client is None

    def test_extract_entities_disabled(self):
        """测试禁用 LLM 时提取实体返回 None"""
        config = PaperBaseConfig(
            llm=LLMConfig(enabled=False)
        )

        client = LLMClient(config=config)
        result = client.extract_entities("some paper content")
        assert result is None

    def test_init_with_old_format_config_file(self):
        """测试加载旧格式配置文件（向后兼容）"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({
                "llm": {
                    "enabled": True,
                    "base_url": "http://localhost:11434/v1",
                    "model": "llama3.2",
                    "api_key": "not-required"
                }
            }, f)
            config_path = Path(f.name)

        try:
            client = LLMClient(config_path=config_path)
            assert client.config.llm.is_enabled() is True
            assert client.config.llm.base_url == "http://localhost:11434/v1"

        finally:
            config_path.unlink()

    def test_config_default_timeout_and_max_tokens(self):
        """测试默认超时和最大输入长度"""
        config = PaperBaseConfig(
            llm=LLMConfig(
                enabled=True,
                base_url="https://api.openai.com/v1",
                model="gpt-4o-mini",
                api_key="test-key"
            )
        )

        client = LLMClient(config=config)
        assert client.config.llm.get_timeout() == 30
        assert client.config.llm.get_max_input_tokens() == 4000
