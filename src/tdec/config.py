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
class DebaterConfig(ModelConfig):
    strategy: str | None = None


@dataclass(frozen=True)
class JudgeModelConfig(ModelConfig):
    style: str | None = None


@dataclass(frozen=True)
class TopicConfig:
    id: str
    motion: str
    context: str | None = None


@dataclass(frozen=True)
class RunConfig:
    name: str
    rounds: int
    output_dir: Path
    include_self_debates: bool = True
    workers: int = 1
    reuse_openings: bool = True
    parallel_rounds: bool = False


@dataclass(frozen=True)
class JudgingConfig:
    repair_retries: int = 1
    parse_retries: int = 1


@dataclass(frozen=True)
class PromptSetConfig:
    id: str
    debater_system: str
    opening: str
    response: str
    parallel_opening: str
    parallel_response: str
    judge_system: str
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


# ── Default prompt set (current hardcoded prompts as templates) ──

DEFAULT_PROMPT_SET_CONFIG = PromptSetConfig(
    id="default",
    debater_system="""\
You are a serious competitive debater in a model-vs-model debate.
$strategy_block
Rules:
- Argue only for your assigned side.
- Build a broad case across the whole motion. Include moral, institutional,
  legal, economic, strategic, execution, and real-world tradeoff dimensions when
  relevant.
- Do not let the debate collapse onto one narrow example unless that example is
  genuinely decisive.
- Rebut the opponent directly, but do not accept their framing as the full map
  of the debate.
- Do not tell the opponent which points they must answer.
- Use clear structure and concrete reasoning.
- Do not claim access to private facts or fabricated sources.
""",
    opening="""\
Motion: $motion
$context_block
You are arguing $side.

This debate has $rounds turns per side. You go first.

Give your opening case. Go wide: identify the strongest affirmative and
negative terrain and explain why your side should win across the motion as a
whole. Do not frame the opponent's choices for them.
""",
    response="""\
Motion: $motion
$context_block
You are arguing $side.

This is your $turn_name of $rounds. Answer the opponent's strongest points,
but keep the whole motion in view. If this is your closing turn, explain why
your side wins overall rather than only on the most recent sub-point.
""",
    parallel_opening="""\
Motion: $motion
$context_block
You are arguing $side.

This debate has $rounds turns per side. Both sides deliver their opening
cases simultaneously — you have not seen the opponent's opening.

Give your opening case. Go wide: identify the strongest affirmative and
negative terrain and explain why your side should win across the motion as a
whole. Do not frame the opponent's choices for them.
""",
    parallel_response="""\
Motion: $motion
$context_block
You are arguing $side.

This is your $turn_name of $rounds. Both sides speak simultaneously each
round — you have seen all prior rounds from both sides, but you have not
seen the opponent's current round. Answer the opponent's strongest points
from previous rounds, but keep the whole motion in view. If this is your
closing turn, explain why your side wins overall rather than only on the
most recent sub-point.
""",
    judge_system="""\
You are an impartial judge in a model-vs-model debate tournament.
$style_block
Judge the debate from the transcript only. The debaters are anonymized as
Debater A and Debater B. Do not reward a side because of your prior political or
policy preference. Reward debate quality: breadth, responsiveness, evidence,
moral reasoning, institutional reasoning, strategic clarity, and closing
weighing.

Return only valid compact JSON. Do not wrap it in Markdown. Keep all string
values short enough that the entire response can fit comfortably in 900 tokens.
""",
    judge="""\
Motion: $motion

Transcript:
$transcript

Return exactly this compact JSON shape:
{
  "winner": "pro" | "con" | "tie",
  "winner_label": "A" | "B" | "tie",
  "confidence": 0.0,
  "pro_score": 0,
  "con_score": 0,
  "rubric": {
    "breadth": {"pro": 0, "con": 0},
    "responsiveness": {"pro": 0, "con": 0},
    "evidence_quality": {"pro": 0, "con": 0},
    "moral_reasoning": {"pro": 0, "con": 0},
    "institutional_reasoning": {"pro": 0, "con": 0},
    "strategic_clarity": {"pro": 0, "con": 0}
  },
  "decisive_reasons": ["reason under 120 chars", "reason under 120 chars", "reason under 120 chars"],
  "audience_estimate": {"pro_votes": 0, "con_votes": 0},
  "summary": "one sentence under 200 chars"
}

Scores are 0-100 for side totals and 0-10 for rubric cells. Audience votes must
sum to 100. Use "tie" only when genuinely inseparable.
""",
    judge_repair="""\
Your previous judgement was not valid JSON.

JSON parse error:
$error

Previous output:
$bad_output

Return only corrected compact JSON in the same schema requested before. Do not
add Markdown or commentary. Do not change the judgement unless required to make
the JSON valid.
""",
)


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
    if prompt_set_name:
        prompt_set = load_prompt_set_config(
            config_dir / "prompt-sets" / f"{prompt_set_name}.yaml"
        )
    else:
        prompt_set = DEFAULT_PROMPT_SET_CONFIG

    run_data = _required_mapping(data, "run")
    run = RunConfig(
        name=str(run_data.get("name", config_path.stem)),
        rounds=int(run_data.get("rounds", 3)),
        output_dir=Path(run_data.get("output_dir", "runs")),
        include_self_debates=_bool_value(run_data.get("include_self_debates", True)),
        workers=_positive_int(run_data.get("workers", 1), "run.workers"),
        reuse_openings=_bool_value(run_data.get("reuse_openings", True)),
        parallel_rounds=_bool_value(run_data.get("parallel_rounds", False)),
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
    base = _model_config_fields(data)
    return DebaterConfig(**base, strategy=data.get("strategy"))


def load_judge_model_config(path: str | Path) -> JudgeModelConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise ValueError(f"Judge config not found: {config_path}")
    data = _load_yaml(config_path)
    base = _model_config_fields(data)
    return JudgeModelConfig(**base, style=data.get("style"))


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
        judge=str(data["judge"]),
        judge_repair=str(data["judge_repair"]),
    )


def load_judge_config(path: str | Path) -> JudgeRunConfig:
    config_path = Path(path)
    data = _load_yaml(config_path)
    return JudgeRunConfig(
        judges=[_judge_model_config_inline(item) for item in _required_list(data, "judges")],
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
    base = _model_config_fields(data)
    return JudgeModelConfig(**base, style=data.get("style"))


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
