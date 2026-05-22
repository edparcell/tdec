"""Configuration loading and validation."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ModelConfig:
    id: str
    provider: str
    model: str
    api_base: str | None = None
    api_key: str | None = None
    temperature: float | None = 0.2
    max_tokens: int = 4096

    @property
    def litellm_model_id(self) -> str:
        return f"{self.provider}/{self.model}"


@dataclass(frozen=True)
class TopicConfig:
    id: str
    motion: str
    pro_position: str
    con_position: str


@dataclass(frozen=True)
class RunConfig:
    name: str
    rounds: int
    output_dir: Path


@dataclass(frozen=True)
class JudgingConfig:
    repair_retries: int = 1
    parse_retries: int = 1


@dataclass(frozen=True)
class TournamentConfig:
    run: RunConfig
    topics: list[TopicConfig]
    debaters: list[ModelConfig]
    judges: list[ModelConfig]
    judging: JudgingConfig


def load_tournament_config(path: str | Path) -> TournamentConfig:
    config_path = Path(path)
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Config {config_path} must contain a YAML object")

    run_data = _required_mapping(data, "run")
    run = RunConfig(
        name=str(run_data.get("name", config_path.stem)),
        rounds=int(run_data.get("rounds", 3)),
        output_dir=Path(run_data.get("output_dir", "runs")),
    )

    return TournamentConfig(
        run=run,
        topics=[_topic_config(item) for item in _required_list(data, "topics")],
        debaters=[_model_config(item) for item in _required_list(data, "debaters")],
        judges=[_model_config(item) for item in _required_list(data, "judges")],
        judging=_judging_config(data.get("judging", {})),
    )


def _model_config(data: dict[str, Any]) -> ModelConfig:
    api_key = data.get("api_key")
    api_key_env = data.get("api_key_env")
    if api_key_env:
        api_key = os.environ.get(str(api_key_env))
        if not api_key:
            raise ValueError(f"Required API key environment variable is not set: {api_key_env}")

    temperature = data.get("temperature", 0.2)
    return ModelConfig(
        id=str(data["id"]),
        provider=str(data["provider"]),
        model=str(data["model"]),
        api_base=data.get("api_base"),
        api_key=api_key,
        temperature=None if temperature is None else float(temperature),
        max_tokens=int(data.get("max_tokens", 4096)),
    )


def _topic_config(data: dict[str, Any]) -> TopicConfig:
    return TopicConfig(
        id=str(data["id"]),
        motion=str(data["motion"]),
        pro_position=str(data["pro_position"]),
        con_position=str(data["con_position"]),
    )


def _judging_config(data: Any) -> JudgingConfig:
    if not isinstance(data, dict):
        raise ValueError("Config key 'judging' must be a mapping when present")
    return JudgingConfig(
        repair_retries=int(data.get("repair_retries", 1)),
        parse_retries=int(data.get("parse_retries", 1)),
    )


def _required_mapping(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"Config key {key!r} must be a mapping")
    return value


def _required_list(data: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = data.get(key)
    if not isinstance(value, list):
        raise ValueError(f"Config key {key!r} must be a list")
    return value
