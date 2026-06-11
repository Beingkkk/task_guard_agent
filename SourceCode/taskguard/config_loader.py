"""Configuration loader.

Relates-to: FR-3
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class LLMConfig:
    """LLM provider configuration."""

    model: str = ""
    api_key: str = ""
    base_url: str | None = None
    min_interval: int = 60
    max_log_lines: int = 50
    regex_threshold: float = 0.6


@dataclass
class CrashConfig:
    """Crash/OOM scene preservation configuration."""

    max_dumps: int = 10
    log_lines: int = 500
    metrics_minutes: int = 10


@dataclass
class AppConfig:
    """Application configuration."""

    agent_name: str = "TaskGuard"
    collect_interval: int = 30
    data_dir: Path = field(default_factory=lambda: Path("./data"))
    llm: LLMConfig = field(default_factory=LLMConfig)
    crash: CrashConfig = field(default_factory=CrashConfig)


class ConfigLoader:
    """Loads and merges config.yaml and config-claude.json."""

    @classmethod
    def load(cls, config_dir: Path) -> AppConfig:
        config_path = config_dir / "config.yaml"

        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        llm_cfg = raw.get("llm", {})
        crash_cfg = raw.get("crash", {})

        # Always load config-claude.json (only provider supported)
        claude_path = config_dir / "config-claude.json"

        if not claude_path.exists():
            raise FileNotFoundError(f"LLM config file not found: {claude_path}")

        with open(claude_path, encoding="utf-8") as f:
            claude_raw = json.load(f)

        # Merge rules: yaml overrides json for model name
        # api_key and base_url come from json only
        model_name = llm_cfg.get("model", claude_raw.get("model_name", ""))

        llm = LLMConfig(
            model=model_name,
            api_key=claude_raw.get("auth_key", ""),
            base_url=claude_raw.get("llm_base_url"),
            min_interval=llm_cfg.get("min_interval", 60),
            max_log_lines=llm_cfg.get("max_log_lines", 50),
            regex_threshold=llm_cfg.get("regex_threshold", 0.6),
        )

        return AppConfig(
            agent_name=raw.get("agent_name", "TaskGuard"),
            collect_interval=raw.get("collect_interval", 30),
            data_dir=Path(raw.get("data_dir", "./data")),
            llm=llm,
            crash=CrashConfig(
                max_dumps=crash_cfg.get("max_dumps", 10),
                log_lines=crash_cfg.get("log_lines", 500),
                metrics_minutes=crash_cfg.get("metrics_minutes", 10),
            ),
        )
