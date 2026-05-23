"""Configuration loading and validation."""

from __future__ import annotations

from dataclasses import dataclass, field
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
class DebaterConfig(ModelConfig):
    strategy: str = ""


@dataclass(frozen=True)
class JudgeModelConfig(ModelConfig):
    style: str = ""


@dataclass(frozen=True)
class TopicConfig:
    id: str
    motion: str
    context: str | None = None


DEBATE_MODES = ("pro_first", "con_first", "parallel")


@dataclass(frozen=True)
class RunConfig:
    name: str
    rounds: int
    output_dir: Path
    include_self_debates: bool = True
    workers: int = 1
    reuse_openings: bool = True
    debate_mode: str = "pro_first"
    debate_api_retries: int = 2
    conditions: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class JudgingConfig:
    repair_retries: int = 1
    parse_retries: int = 1
    api_retries: int = 2


@dataclass(frozen=True)
class PromptSetConfig:
    id: str
    debater_system: str
    opening: str
    response: str
    parallel_opening: str
    parallel_response: str
    judge_system: str
    parallel_judge_system: str
    judge: str
    judge_repair: str


@dataclass(frozen=True)
class TournamentConfig:
    run: RunConfig
    topics: list[TopicConfig]
    debaters: list[DebaterConfig]
    judges: list[JudgeModelConfig]
    judging: JudgingConfig
    prompt_set: PromptSetConfig


@dataclass(frozen=True)
class JudgeRunConfig:
    judges: list[JudgeModelConfig]
    judging: JudgingConfig


# ── Loaders ──


def load_run_config(path: str | Path) -> TournamentConfig:
    config_path = Path(path)
    data = _load_yaml(config_path)
    config_dir = config_path.parent.parent

    debater_names = _required_list(data, "debaters")
    debaters = [
        load_debater_config(config_dir / "debaters" / f"{name}.yaml")
        for name in debater_names
    ]

    judge_names = _required_list(data, "judges")
    judges = [
        load_judge_model_config(config_dir / "judges" / f"{name}.yaml")
        for name in judge_names
    ]

    prompt_set_name = data.get("prompt_set")
    if not prompt_set_name:
        raise ValueError("Config key 'prompt_set' is required")
    prompt_set = load_prompt_set_config(
        config_dir / "prompt-sets" / f"{prompt_set_name}.yaml"
    )

    run_data = _required_mapping(data, "run")
    run = RunConfig(
        name=str(run_data.get("name", config_path.stem)),
        rounds=int(run_data.get("rounds", 3)),
        output_dir=Path(run_data.get("output_dir", "runs")),
        include_self_debates=_bool_value(run_data.get("include_self_debates", True)),
        workers=_positive_int(run_data.get("workers", 1), "run.workers"),
        reuse_openings=_bool_value(run_data.get("reuse_openings", True)),
        debate_mode=_debate_mode(run_data.get("debate_mode", "pro_first")),
        debate_api_retries=int(run_data.get("debate_api_retries", 2)),
        conditions=dict(run_data.get("conditions") or {}),
    )

    return TournamentConfig(
        run=run,
        topics=[_topic_config(item) for item in _required_list(data, "topics")],
        debaters=debaters,
        judges=judges,
        judging=_judging_config(data.get("judging", {})),
        prompt_set=prompt_set,
    )


def load_debater_config(path: str | Path) -> DebaterConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise ValueError(f"Debater config not found: {config_path}")
    data = _load_yaml(config_path)
    if "strategy" not in data:
        raise ValueError(f"Debater config {config_path} must include 'strategy' (may be empty)")
    base = _model_config_fields(data)
    return DebaterConfig(**base, strategy=str(data["strategy"] or ""))


def load_judge_model_config(path: str | Path) -> JudgeModelConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise ValueError(f"Judge config not found: {config_path}")
    data = _load_yaml(config_path)
    if "style" not in data:
        raise ValueError(f"Judge config {config_path} must include 'style' (may be empty)")
    base = _model_config_fields(data)
    return JudgeModelConfig(**base, style=str(data["style"] or ""))


def load_prompt_set_config(path: str | Path) -> PromptSetConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise ValueError(f"Prompt-set config not found: {config_path}")
    data = _load_yaml(config_path)
    return PromptSetConfig(
        id=str(data.get("id", config_path.stem)),
        debater_system=str(data["debater_system"]),
        opening=str(data["opening"]),
        response=str(data["response"]),
        parallel_opening=str(data["parallel_opening"]),
        parallel_response=str(data["parallel_response"]),
        judge_system=str(data["judge_system"]),
        parallel_judge_system=str(data.get("parallel_judge_system") or data["judge_system"]),
        judge=str(data["judge"]),
        judge_repair=str(data["judge_repair"]),
    )


def load_judge_config(path: str | Path) -> JudgeRunConfig:
    config_path = Path(path)
    data = _load_yaml(config_path)
    judges_dir = config_path.parent / "judges"
    judge_entries = _required_list(data, "judges")
    judges = [
        load_judge_model_config(judges_dir / f"{entry}.yaml")
        if isinstance(entry, str)
        else _judge_model_config_inline(entry)
        for entry in judge_entries
    ]
    return JudgeRunConfig(
        judges=judges,
        judging=_judging_config(data.get("judging", {})),
    )


# ── Internal helpers ──


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Config {path} must contain a YAML object")
    return data


def _model_config_fields(data: dict[str, Any]) -> dict[str, Any]:
    api_key = data.get("api_key")
    api_key_env = data.get("api_key_env")
    if api_key_env:
        api_key = os.environ.get(str(api_key_env))
        if not api_key:
            raise ValueError(f"Required API key environment variable is not set: {api_key_env}")
    temperature = data.get("temperature", 0.2)
    return {
        "id": str(data["id"]),
        "provider": str(data["provider"]),
        "model": str(data["model"]),
        "api_base": data.get("api_base"),
        "api_key": api_key,
        "temperature": None if temperature is None else float(temperature),
        "max_tokens": int(data.get("max_tokens", 4096)),
    }


def _judge_model_config_inline(data: dict[str, Any]) -> JudgeModelConfig:
    if "style" not in data:
        raise ValueError("Inline judge config must include 'style' (may be empty)")
    base = _model_config_fields(data)
    return JudgeModelConfig(**base, style=str(data["style"] or ""))


def _topic_config(data: dict[str, Any]) -> TopicConfig:
    return TopicConfig(
        id=str(data["id"]),
        motion=str(data["motion"]),
        context=data.get("context"),
    )


def _judging_config(data: Any) -> JudgingConfig:
    if not isinstance(data, dict):
        raise ValueError("Config key 'judging' must be a mapping when present")
    return JudgingConfig(
        repair_retries=int(data.get("repair_retries", 1)),
        parse_retries=int(data.get("parse_retries", 1)),
        api_retries=int(data.get("api_retries", 2)),
    )


def _required_mapping(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"Config key {key!r} must be a mapping")
    return value


def _required_list(data: dict[str, Any], key: str) -> list:
    value = data.get(key)
    if not isinstance(value, list):
        raise ValueError(f"Config key {key!r} must be a list")
    return value


def _debate_mode(value: Any) -> str:
    mode = str(value)
    if mode not in DEBATE_MODES:
        raise ValueError(f"debate_mode must be one of {DEBATE_MODES}, got {mode!r}")
    return mode


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "1", "on"}:
            return True
        if normalized in {"false", "no", "0", "off"}:
            return False
    raise ValueError(f"Expected boolean value, got {value!r}")


def _positive_int(value: Any, name: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise ValueError(f"{name} must be at least 1")
    return parsed
