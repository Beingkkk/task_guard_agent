"""Tests for ConfigLoader.

Relates-to: FR-3
"""

import json
from pathlib import Path

import pytest
import yaml

from taskguard.config_loader import AppConfig, ConfigLoader, LLMConfig


class TestConfigLoader:
    def test_load_claude_provider(self, tmp_path: Path) -> None:  # type: ignore[name-defined]
        config_dir = tmp_path
        config_yaml = {
            "agent_name": "TestGuard",
            "collect_interval": 15,
            "llm": {
                "provider": "claude",
                "model": "claude-sonnet-4-6",
                "min_interval": 30,
                "max_log_lines": 40,
                "regex_threshold": 0.7,
            },
        }
        (config_dir / "config.yaml").write_text(yaml.dump(config_yaml))

        claude_json = {
            "llm_base_url": "https://api.anthropic.com/",
            "auth_key": "sk-claude-key",
            "model_name": "default-model",
        }
        (config_dir / "config-claude.json").write_text(json.dumps(claude_json))

        cfg = ConfigLoader.load(config_dir)
        assert isinstance(cfg, AppConfig)
        assert cfg.agent_name == "TestGuard"
        assert cfg.collect_interval == 15
        assert cfg.llm.provider == "claude"
        assert cfg.llm.model == "claude-sonnet-4-6"  # yaml overrides json
        assert cfg.llm.api_key == "sk-claude-key"
        assert cfg.llm.base_url == "https://api.anthropic.com/"
        assert cfg.llm.min_interval == 30
        assert cfg.llm.max_log_lines == 40
        assert cfg.llm.regex_threshold == 0.7

    def test_load_openai_provider(self, tmp_path: Path) -> None:  # type: ignore[name-defined]
        config_dir = tmp_path
        (config_dir / "config.yaml").write_text(
            yaml.dump({"llm": {"provider": "openai"}}),
        )
        (config_dir / "config-openai.json").write_text(
            json.dumps(
                {"auth_key": "k", "model_name": "kimi-k2.6", "llm_base_url": "https://api.kimi.com"}
            ),
        )

        cfg = ConfigLoader.load(config_dir)
        assert cfg.llm.provider == "openai"
        assert cfg.llm.model == "kimi-k2.6"
        assert cfg.llm.base_url == "https://api.kimi.com"

    def test_default_provider_is_claude(self, tmp_path: Path) -> None:  # type: ignore[name-defined]
        """When llm.provider is not specified, default to claude."""
        config_dir = tmp_path
        (config_dir / "config.yaml").write_text(yaml.dump({}))
        (config_dir / "config-claude.json").write_text(
            json.dumps({"auth_key": "k", "model_name": "default"}),
        )

        cfg = ConfigLoader.load(config_dir)
        assert cfg.llm.provider == "claude"

    def test_model_fallback_to_json(self, tmp_path: Path) -> None:  # type: ignore[name-defined]
        config_dir = tmp_path
        (config_dir / "config.yaml").write_text(yaml.dump({"llm": {"provider": "claude"}}))
        (config_dir / "config-claude.json").write_text(
            json.dumps({"auth_key": "k", "model_name": "json-model"}),
        )

        cfg = ConfigLoader.load(config_dir)
        assert cfg.llm.model == "json-model"

    def test_missing_config_yaml(self, tmp_path: Path) -> None:  # type: ignore[name-defined]
        with pytest.raises(FileNotFoundError):
            ConfigLoader.load(tmp_path)

    def test_missing_claude_config_json(self, tmp_path: Path) -> None:  # type: ignore[name-defined]
        (tmp_path / "config.yaml").write_text(yaml.dump({"llm": {"provider": "claude"}}))
        with pytest.raises(FileNotFoundError):
            ConfigLoader.load(tmp_path)

    def test_missing_openai_config_json(self, tmp_path: Path) -> None:  # type: ignore[name-defined]
        (tmp_path / "config.yaml").write_text(yaml.dump({"llm": {"provider": "openai"}}))
        with pytest.raises(FileNotFoundError):
            ConfigLoader.load(tmp_path)

    def test_invalid_yaml(self, tmp_path: Path) -> None:  # type: ignore[name-defined]
        (tmp_path / "config.yaml").write_text("{invalid yaml")
        (tmp_path / "config-claude.json").write_text("{}")
        with pytest.raises((Exception,)):
            ConfigLoader.load(tmp_path)

    def test_invalid_json(self, tmp_path: Path) -> None:  # type: ignore[name-defined]
        (tmp_path / "config.yaml").write_text(yaml.dump({}))
        (tmp_path / "config-claude.json").write_text("not json")
        with pytest.raises((Exception,)):
            ConfigLoader.load(tmp_path)


class TestAppConfigDefaults:
    def test_llm_defaults(self) -> None:
        llm = LLMConfig(provider="openai", model="x", api_key="k")
        assert llm.min_interval == 60
        assert llm.max_log_lines == 50
        assert llm.regex_threshold == 0.6
