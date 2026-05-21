"""Shared data structures for debates and judgements."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from tdec.config import ModelConfig, TopicConfig

Side = Literal["pro", "con"]


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


def public_model_dict(model: ModelConfig) -> dict[str, Any]:
    data = asdict(model)
    data["api_key"] = "<redacted>" if data.get("api_key") else None
    return data
