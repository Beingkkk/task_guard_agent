"""Tests for Provider factory.

Relates-to: FR-3
"""

import pytest

from taskguard.llm.claude_provider import ClaudeProvider
from taskguard.llm.factory import LLMConfig, create_provider
from taskguard.llm.openai_provider import OpenAIProvider


class TestCreateProvider:
    def test_claude_provider(self) -> None:
        config = LLMConfig(
            provider="claude",
            model="claude-test",
            api_key="key",
            base_url="https://custom.example.com",
        )
        provider = create_provider(config)
        assert isinstance(provider, ClaudeProvider)

    def test_openai_provider(self) -> None:
        config = LLMConfig(
            provider="openai",
            model="gpt-test",
            api_key="key",
            base_url="https://api.kimi.com/coding",
        )
        provider = create_provider(config)
        assert isinstance(provider, OpenAIProvider)

    def test_openai_default_base_url(self) -> None:
        config = LLMConfig(
            provider="openai",
            model="gpt-test",
            api_key="key",
        )
        provider = create_provider(config)
        assert isinstance(provider, OpenAIProvider)

    def test_unknown_provider_raises(self) -> None:
        config = LLMConfig(provider="unknown", model="x", api_key="k")
        with pytest.raises(ValueError, match="Unknown provider"):
            create_provider(config)
