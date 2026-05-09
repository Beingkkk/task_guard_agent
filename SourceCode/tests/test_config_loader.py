"""Tests for ConfigLoader.

Relates-to: FR-3
"""

import json

import pytest
import yaml

from taskguard.config_loader import AppConfig, ConfigLoader, LLMConfig


class TestConfigLoader:
    def test_load_valid_config(self, tmp_path) -> None:
        config_dir = tmp_path
        config_yaml = {
            "agent_name": "TestGuard",
            "collect_interval": 15,
            "llm": {
                "provider": "openai",
                "model": "kimi-for-coding",
                "min_interval": 30,
                "max_log_lines": 40,
                "regex_threshold": 0.7,
            },
        }
        (config_dir / "config.yaml").write_text(yaml.dump(config_yaml))

        llm_json = {
            "llm_base_url": "https://api.kimi.com/coding/",
            "auth_key": "sk-test-key",
            "model_name": "default-model",
        }
        (config_dir / "llm_config_claude.json").write_text(json.dumps(llm_json))

        cfg = ConfigLoader.load(config_dir)
        assert isinstance(cfg, AppConfig)
        assert cfg.agent_name == "TestGuard"
        assert cfg.collect_interval == 15
        assert cfg.llm.provider == "openai"
        # yaml model overrides json model_name
        assert cfg.llm.model == "kimi-for-coding"
        assert cfg.llm.api_key == "sk-test-key"
        assert cfg.llm.base_url == "https://api.kimi.com/coding/"
        assert cfg.llm.min_interval == 30
        assert cfg.llm.max_log_lines == 40
        assert cfg.llm.regex_threshold == 0.7

    def test_model_fallback_to_json(self, tmp_path) -> None:
        config_dir = tmp_path
        (config_dir / "config.yaml").write_text(yaml.dump({"llm": {"provider": "openai"}}))
        (config_dir / "llm_config_claude.json").write_text(
            json.dumps({"auth_key": "k", "model_name": "json-model"})
        )

        cfg = ConfigLoader.load(config_dir)
        assert cfg.llm.model == "json-model"

    def test_missing_config_yaml(self, tmp_path) -> None:
        with pytest.raises(FileNotFoundError):
            ConfigLoader.load(tmp_path)

    def test_missing_llm_config_json(self, tmp_path) -> None:
        (tmp_path / "config.yaml").write_text(yaml.dump({}))
        with pytest.raises(FileNotFoundError):
            ConfigLoader.load(tmp_path)

    def test_invalid_yaml(self, tmp_path) -> None:
        (tmp_path / "config.yaml").write_text("{invalid yaml")
        (tmp_path / "llm_config_claude.json").write_text("{}")
        with pytest.raises((Exception,)):
            ConfigLoader.load(tmp_path)

    def test_invalid_json(self, tmp_path) -> None:
        (tmp_path / "config.yaml").write_text(yaml.dump({}))
        (tmp_path / "llm_config_claude.json").write_text("not json")
        with pytest.raises((Exception,)):
            ConfigLoader.load(tmp_path)


class TestAppConfigDefaults:
    def test_llm_defaults(self) -> None:
        llm = LLMConfig(provider="openai", model="x", api_key="k")
        assert llm.min_interval == 60
        assert llm.max_log_lines == 50
        assert llm.regex_threshold == 0.6
