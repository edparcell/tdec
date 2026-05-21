"""Configuration loading and validation."""

from __future__ import annotations

from dataclasses import dataclass
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
    temperature: float = 0.2
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
class TournamentConfig:
    run: RunConfig
    topics: list[TopicConfig]
    debaters: list[ModelConfig]
    judges: list[ModelConfig]


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
    )


def _model_config(data: dict[str, Any]) -> ModelConfig:
    return ModelConfig(
        id=str(data["id"]),
        provider=str(data["provider"]),
        model=str(data["model"]),
        api_base=data.get("api_base"),
        api_key=data.get("api_key"),
        temperature=float(data.get("temperature", 0.2)),
        max_tokens=int(data.get("max_tokens", 4096)),
    )


def _topic_config(data: dict[str, Any]) -> TopicConfig:
    return TopicConfig(
        id=str(data["id"]),
        motion=str(data["motion"]),
        pro_position=str(data["pro_position"]),
        con_position=str(data["con_position"]),
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

