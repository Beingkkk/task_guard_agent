"""Tests for ConfigLoader.

Relates-to: FR-3
"""

import json
from pathlib import Path

import pytest
import yaml

from taskguard.config_loader import AppConfig, ConfigLoader, CrashConfig, LLMConfig


class TestConfigLoader:
    def test_load_claude_config(self, tmp_path: Path) -> None:  # type: ignore[name-defined]
        config_dir = tmp_path
        config_yaml = {
            "agent_name": "TestGuard",
            "collect_interval": 15,
            "llm": {
                "model": "claude-sonnet-4-6",
                "min_interval": 30,
                "max_log_lines": 40,
                "regex_threshold": 0.7,
                "state_analysis_enabled": True,
                "state_analysis_interval": 120,
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
        assert cfg.llm.model == "claude-sonnet-4-6"  # yaml overrides json
        assert cfg.llm.api_key == "sk-claude-key"
        assert cfg.llm.base_url == "https://api.anthropic.com/"
        assert cfg.llm.min_interval == 30
        assert cfg.llm.max_log_lines == 40
        assert cfg.llm.regex_threshold == 0.7
        assert cfg.llm.state_analysis_enabled is True
        assert cfg.llm.state_analysis_interval == 120
        assert isinstance(cfg.crash, CrashConfig)
        assert cfg.crash.max_dumps == 10
        assert cfg.crash.log_lines == 500
        assert cfg.crash.metrics_minutes == 10

    def test_model_fallback_to_json(self, tmp_path: Path) -> None:  # type: ignore[name-defined]
        config_dir = tmp_path
        (config_dir / "config.yaml").write_text(yaml.dump({}))
        (config_dir / "config-claude.json").write_text(
            json.dumps({"auth_key": "k", "model_name": "json-model"}),
        )

        cfg = ConfigLoader.load(config_dir)
        assert cfg.llm.model == "json-model"

    def test_missing_config_yaml(self, tmp_path: Path) -> None:  # type: ignore[name-defined]
        with pytest.raises(FileNotFoundError):
            ConfigLoader.load(tmp_path)

    def test_missing_claude_config_json(self, tmp_path: Path) -> None:  # type: ignore[name-defined]
        (tmp_path / "config.yaml").write_text(yaml.dump({}))
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
        llm = LLMConfig(model="x", api_key="k")
        assert llm.min_interval == 60
        assert llm.max_log_lines == 50
        assert llm.regex_threshold == 0.6

    def test_crash_defaults(self) -> None:
        crash = CrashConfig()
        assert crash.max_dumps == 10
        assert crash.log_lines == 500
        assert crash.metrics_minutes == 10

    def test_crash_config_override(self, tmp_path: Path) -> None:  # type: ignore[name-defined]
        config_dir = tmp_path
        config_yaml = {
            "crash": {
                "max_dumps": 5,
                "log_lines": 200,
                "metrics_minutes": 5,
            },
        }
        (config_dir / "config.yaml").write_text(yaml.dump(config_yaml))
        (config_dir / "config-claude.json").write_text(json.dumps({"auth_key": "k"}))

        cfg = ConfigLoader.load(config_dir)
        assert cfg.crash.max_dumps == 5
        assert cfg.crash.log_lines == 200
        assert cfg.crash.metrics_minutes == 5
