"""测试配置加载（集成测试）"""

import pytest
from pathlib import Path
import yaml
import tempfile
from paperbase.config import load_config, ConfigError


class TestConfigLoader:
    """测试配置加载器"""

    def test_load_default_config(self):
        """测试加载默认配置"""
        config = load_config()
        assert config is not None
        assert hasattr(config, "llm")
        assert hasattr(config, "graph")

    def test_default_config_disables_scihub(self):
        """默认配置不得授权通过 Sci-Hub 绕过付费墙。"""
        config = load_config()

        assert config.adapters["scansci"]["scihub_enabled"] is False

    def test_load_nonexistent_config(self):
        """测试加载不存在的配置文件"""
        config = load_config(Path("/nonexistent/config.yaml"))
        # 应返回默认配置，不抛出异常
        assert config is not None
        assert config.llm.is_enabled() is False

    def test_load_simple_config(self):
        """测试加载简单配置"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({
                "llm": {
                    "enabled": True,
                    "base_url": "https://api.openai.com/v1",
                    "model": "gpt-4o-mini",
                    "api_key": "test-key"
                },
                "graph": {
                    "auto_update": True
                },
                "adapters": {
                    "paper_fetch": {
                        "enabled": True,
                        "artifact_mode": "markdown-assets"
                    }
                }
            }, f)
            config_path = Path(f.name)

        try:
            config = load_config(config_path)

            # 验证 LLM 配置
            assert config.llm.is_enabled() is True
            assert config.llm.model == "gpt-4o-mini"
            assert config.llm.get_base_url() == "https://api.openai.com/v1"

            # 验证 Graph 配置
            assert config.graph.auto_update == "on_entity_change"
            assert config.graph.get_triggers() == ["entity_change", "paper_ingest"]

            # 验证 Adapter 配置
            adapter = config.get_paper_fetch_adapter()
            assert adapter.artifact_mode == "markdown-assets"

        finally:
            config_path.unlink()

    def test_load_old_format_config(self):
        """测试加载旧格式配置（向后兼容）"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({
                "llm": {
                    "enabled": True,
                    "base_url": "https://api.openai.com/v1",
                    "model": "gpt-4o-mini",
                    "api_key": "test-key"
                },
                "graph": {
                    "auto_update": True,
                    "auto_update_on": ["entity_change", "paper_ingest"]
                },
                "adapters": {
                    "paper_fetch": {
                        "enabled": True,
                        "artifact_mode": "markdown-assets",
                        "include_refs": "all"
                    }
                }
            }, f)
            config_path = Path(f.name)

        try:
            config = load_config(config_path)

            # 验证加载成功
            assert config.llm.is_enabled() is True
            assert config.llm.model == "gpt-4o-mini"

            assert config.graph.auto_update == "on_entity_change"
            assert config.graph.auto_update_on == ["entity_change", "paper_ingest"]
            assert config.graph.get_triggers() == ["entity_change", "paper_ingest"]

            adapter = config.get_paper_fetch_adapter()
            assert adapter.artifact_mode == "markdown-assets"

        finally:
            config_path.unlink()

    def test_load_config_with_env_vars(self, monkeypatch):
        """测试环境变量展开"""
        monkeypatch.setenv("TEST_API_KEY", "secret-key")
        monkeypatch.setenv("TEST_MODEL", "gpt-4o")
        monkeypatch.setenv("TEST_BASE_URL", "https://api.example.com/v1")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({
                "llm": {
                    "enabled": True,
                    "base_url": "${TEST_BASE_URL}",
                    "api_key": "${TEST_API_KEY}",
                    "model": "${TEST_MODEL}"
                }
            }, f)
            config_path = Path(f.name)

        try:
            config = load_config(config_path)
            assert config.llm.api_key == "secret-key"
            assert config.llm.model == "gpt-4o"
            assert config.llm.base_url == "https://api.example.com/v1"

        finally:
            config_path.unlink()

    def test_load_invalid_config(self):
        """测试加载无效配置"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({
                "llm": {
                    "enabled": True,
                    "base_url": "https://api.openai.com/v1",
                    # 缺少 model（必需）
                    "api_key": "test-key"
                }
            }, f)
            config_path = Path(f.name)

        try:
            with pytest.raises(ConfigError, match="llm.model is required"):
                load_config(config_path)

        finally:
            config_path.unlink()

    def test_load_config_malformed_yaml(self):
        """测试加载格式错误的 YAML"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("invalid: yaml: content:\n  - missing\n    - indent")
            config_path = Path(f.name)

        try:
            with pytest.raises(ConfigError, match="Failed to load config file"):
                load_config(config_path)

        finally:
            config_path.unlink()

    def test_load_custom_base_url_config(self):
        """测试加载自定义 base_url 配置"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({
                "llm": {
                    "enabled": True,
                    "base_url": "https://my-llm.example.com/v1",
                    "model": "custom-model",
                    "api_key": "test-key"
                }
            }, f)
            config_path = Path(f.name)

        try:
            config = load_config(config_path)
            assert config.llm.is_enabled() is True
            assert config.llm.get_base_url() == "https://my-llm.example.com/v1"

        finally:
            config_path.unlink()

    def test_load_disabled_llm_config(self):
        """测试加载禁用 LLM 的配置"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({
                "llm": {
                    "enabled": False
                }
            }, f)
            config_path = Path(f.name)

        try:
            config = load_config(config_path)
            assert config.llm.is_enabled() is False

        finally:
            config_path.unlink()

    def test_load_minimal_adapter_config(self):
        """测试加载最小化 adapter 配置"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({
                "adapters": {
                    "paper_fetch": {
                        "enabled": True,
                        "artifact_mode": "markdown",
                        "allow_metadata_only": True
                    }
                }
            }, f)
            config_path = Path(f.name)

        try:
            config = load_config(config_path)
            adapter = config.get_paper_fetch_adapter()
            assert adapter.artifact_mode == "markdown"
            assert adapter.allow_metadata_only is True

        finally:
            config_path.unlink()
