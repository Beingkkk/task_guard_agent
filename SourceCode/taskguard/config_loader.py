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

    provider: str = "claude"
    model: str = ""
    api_key: str = ""
    base_url: str | None = None
    min_interval: int = 60
    max_log_lines: int = 50
    regex_threshold: float = 0.6


@dataclass
class AppConfig:
    """Application configuration."""

    agent_name: str = "TaskGuard"
    collect_interval: int = 30
    data_dir: Path = field(default_factory=lambda: Path("./data"))
    llm: LLMConfig = field(default_factory=LLMConfig)


class ConfigLoader:
    """Loads and merges config.yaml and llm_config_claude.json."""

    @classmethod
    def load(cls, config_dir: Path) -> AppConfig:
        config_path = config_dir / "config.yaml"
        llm_path = config_dir / "llm_config_claude.json"

        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
        if not llm_path.exists():
            raise FileNotFoundError(f"LLM config file not found: {llm_path}")

        with open(config_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        with open(llm_path, encoding="utf-8") as f:
            llm_raw = json.load(f)

        llm_cfg = raw.get("llm", {})

        # Merge rules: yaml overrides json for most fields
        # api_key and base_url come from json only (v0.1)
        model_name = llm_cfg.get("model", llm_raw.get("model_name", ""))

        llm = LLMConfig(
            provider=llm_cfg.get("provider", "claude"),
            model=model_name,
            api_key=llm_raw.get("auth_key", ""),
            base_url=llm_raw.get("llm_base_url"),
            min_interval=llm_cfg.get("min_interval", 60),
            max_log_lines=llm_cfg.get("max_log_lines", 50),
            regex_threshold=llm_cfg.get("regex_threshold", 0.6),
        )

        return AppConfig(
            agent_name=raw.get("agent_name", "TaskGuard"),
            collect_interval=raw.get("collect_interval", 30),
            data_dir=Path(raw.get("data_dir", "./data")),
            llm=llm,
        )
