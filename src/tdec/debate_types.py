"""Shared data structures for debates and judgements."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from tdec.config import ModelConfig, TopicConfig

Side = Literal["pro", "con"]
TournamentErrorStage = Literal["debate", "judgement"]


@dataclass(frozen=True)
class TokenUsage:
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None


@dataclass(frozen=True)
class ModelCallMetrics:
    model_id: str
    provider: str
    model: str
    latency_seconds: float
    usage: TokenUsage
    cost_usd: float | None
    cost_error: str | None = None
    finish_reason: str | None = None
    response_metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class ModelCallResult:
    content: str
    metrics: ModelCallMetrics


@dataclass(frozen=True)
class JudgeAttempt:
    kind: str
    raw_text: str
    parsed: dict[str, Any] | None
    error: str | None
    metrics: ModelCallMetrics


@dataclass(frozen=True)
class DebateTurn:
    speaker_label: str
    speaker_model_id: str
    side: Side
    turn_number: int
    content: str
    metrics: ModelCallMetrics | None = None


@dataclass(frozen=True)
class DebateTranscript:
    id: str
    topic: TopicConfig
    pro_model: ModelConfig
    con_model: ModelConfig
    rounds: int
    turns: list[DebateTurn]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "topic": asdict(self.topic),
            "pro_model": public_model_dict(self.pro_model),
            "con_model": public_model_dict(self.con_model),
            "rounds": self.rounds,
            "turns": [asdict(turn) for turn in self.turns],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DebateTranscript:
        topic_data = data["topic"]
        return cls(
            id=data["id"],
            topic=TopicConfig(
                id=topic_data["id"],
                motion=topic_data["motion"],
                context=topic_data.get("context"),
            ),
            pro_model=_model_config_from_dict(data["pro_model"]),
            con_model=_model_config_from_dict(data["con_model"]),
            rounds=data["rounds"],
            turns=[_turn_from_dict(t) for t in data["turns"]],
        )


@dataclass(frozen=True)
class Judgement:
    debate_id: str
    judge_model_id: str
    raw_text: str
    parsed: dict[str, Any]
    metrics: ModelCallMetrics | None = None
    attempts: list[JudgeAttempt] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Judgement:
        return cls(
            debate_id=data["debate_id"],
            judge_model_id=data["judge_model_id"],
            raw_text=data.get("raw_text", ""),
            parsed=data.get("parsed", {}),
            metrics=_metrics_from_dict(data.get("metrics")),
            attempts=[_attempt_from_dict(a) for a in data.get("attempts") or []],
        )


@dataclass(frozen=True)
class TournamentError:
    stage: TournamentErrorStage
    topic_id: str
    debate_id: str
    pro_model_id: str
    con_model_id: str
    judge_model_id: str | None
    model_id: str
    error_type: str
    error_message: str
    traceback: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def public_model_dict(model: ModelConfig) -> dict[str, Any]:
    data = asdict(model)
    data["api_key"] = "<redacted>" if data.get("api_key") else None
    return data


def _model_config_from_dict(data: dict[str, Any]) -> ModelConfig:
    return ModelConfig(
        id=data["id"],
        provider=data["provider"],
        model=data["model"],
        api_base=data.get("api_base"),
        api_key=data.get("api_key"),
        temperature=data.get("temperature", 0.2),
        max_tokens=data.get("max_tokens", 4096),
    )


def _usage_from_dict(data: dict[str, Any] | None) -> TokenUsage:
    if data is None:
        return TokenUsage(prompt_tokens=None, completion_tokens=None, total_tokens=None)
    return TokenUsage(
        prompt_tokens=data.get("prompt_tokens"),
        completion_tokens=data.get("completion_tokens"),
        total_tokens=data.get("total_tokens"),
    )


def _metrics_from_dict(data: dict[str, Any] | None) -> ModelCallMetrics | None:
    if data is None:
        return None
    return ModelCallMetrics(
        model_id=data["model_id"],
        provider=data["provider"],
        model=data["model"],
        latency_seconds=data["latency_seconds"],
        usage=_usage_from_dict(data.get("usage")),
        cost_usd=data.get("cost_usd"),
        cost_error=data.get("cost_error"),
        finish_reason=data.get("finish_reason"),
        response_metadata=data.get("response_metadata"),
    )


def _turn_from_dict(data: dict[str, Any]) -> DebateTurn:
    return DebateTurn(
        speaker_label=data["speaker_label"],
        speaker_model_id=data["speaker_model_id"],
        side=data["side"],
        turn_number=data["turn_number"],
        content=data["content"],
        metrics=_metrics_from_dict(data.get("metrics")),
    )


def _attempt_from_dict(data: dict[str, Any]) -> JudgeAttempt:
    return JudgeAttempt(
        kind=data["kind"],
        raw_text=data.get("raw_text", ""),
        parsed=data.get("parsed"),
        error=data.get("error"),
        metrics=_metrics_from_dict(data.get("metrics")),
    )
