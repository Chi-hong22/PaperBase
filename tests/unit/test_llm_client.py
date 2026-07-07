"""LLM Client 单元测试"""

import pytest
import os
from pathlib import Path
from paperbase.core.llm_client import LLMClient


def test_llm_client_disabled_by_default():
    """Test LLM client is disabled when no config"""
    client = LLMClient()
    assert client.enabled is False
    assert client.extract_entities("test content") is None


def test_llm_client_with_config():
    """Test LLM client with mock config"""
    config = {
        "llm": {
            "enabled": True,
            "base_url": "https://api.openai.com/v1",
            "api_key": "test-key",
            "model": "gpt-4o-mini"
        }
    }
    client = LLMClient(config=config)
    assert client.enabled is True
    assert client.model == "gpt-4o-mini"


def test_llm_client_env_var_expansion():
    """Test API key from environment variable"""
    os.environ["TEST_PAPERBASE_LLM_API_KEY"] = "env-test-key"

    config = {
        "llm": {
            "enabled": True,
            "base_url": "https://api.openai.com/v1",
            "api_key": "${TEST_PAPERBASE_LLM_API_KEY}",
            "model": "gpt-4o-mini"
        }
    }
    client = LLMClient(config=config)
    assert client.config["llm"]["api_key"] == "env-test-key"

    # Cleanup
    del os.environ["TEST_PAPERBASE_LLM_API_KEY"]


def test_llm_client_local_llm_without_api_key():
    """Test local LLM (Ollama) without API key"""
    config = {
        "llm": {
            "enabled": True,
            "base_url": "http://localhost:11434/v1",
            "api_key": "not-required",
            "model": "llama3.2"
        }
    }
    client = LLMClient(config=config)
    assert client.enabled is True
    assert client.model == "llama3.2"


def test_llm_client_missing_config():
    """Test LLM client disables when config incomplete"""
    config = {
        "llm": {
            "enabled": True,
            "base_url": "",  # Missing
            "api_key": "test-key",
            "model": "gpt-4o-mini"
        }
    }
    client = LLMClient(config=config)
    assert client.enabled is False


@pytest.mark.integration
def test_llm_client_real_extraction():
    """
    集成测试：使用真实 API 提取实体

    需要 .env 文件配置：
    PAPERBASE_LLM_BASE_URL=https://api.openai.com/v1
    PAPERBASE_LLM_API_KEY=sk-xxx
    PAPERBASE_LLM_MODEL=gpt-4o-mini
    """
    # 从 .env 加载环境变量
    from dotenv import load_dotenv
    load_dotenv()

    # 检查环境变量是否配置
    if not os.getenv("PAPERBASE_LLM_API_KEY"):
        pytest.skip("PAPERBASE_LLM_API_KEY not configured")

    config = {
        "llm": {
            "enabled": True,
            "base_url": os.getenv("PAPERBASE_LLM_BASE_URL", "https://api.openai.com/v1"),
            "api_key": os.getenv("PAPERBASE_LLM_API_KEY"),
            "model": os.getenv("PAPERBASE_LLM_MODEL", "gpt-4o-mini"),
            "extract_timeout": 30,
            "max_content_length": 4000
        }
    }

    client = LLMClient(config=config)
    assert client.enabled is True

    # 测试论文摘要
    test_abstract = """
    We propose a submap-based SLAM system for AUVs operating in underwater environments.
    Our method uses a Particle Filter for localization and is evaluated on the AQUALOC dataset.
    We compare with ORB-SLAM2 in the related work section.
    """

    result = client.extract_entities(test_abstract)

    # 验证返回格式
    assert result is not None
    assert isinstance(result, dict)
    assert "methods" in result
    assert "datasets" in result
    assert "domains" in result
    assert "platforms" in result
    assert "constraints" in result

    # 验证内容（基于 prompt 设计）
    assert len(result["methods"]) >= 1  # 应该提取 submap, Particle Filter
    assert len(result["datasets"]) >= 1  # 应该提取 AQUALOC

    # ORB-SLAM2 不应该被提取（仅在 Related Work 提及）
    method_names = [m["name"] for m in result["methods"]]
    assert "ORB-SLAM2" not in method_names

    print(f"\n提取结果：{result}")
