"""Tests for Provider factory.

Relates-to: FR-3
"""

from taskguard.llm.claude_provider import ClaudeProvider
from taskguard.llm.factory import LLMConfig, create_provider


class TestCreateProvider:
    def test_claude_provider(self) -> None:
        config = LLMConfig(
            model="claude-test",
            api_key="key",
            base_url="https://custom.example.com",
        )
        provider = create_provider(config)
        assert isinstance(provider, ClaudeProvider)
