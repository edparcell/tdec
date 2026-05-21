"""Shared data structures for debates and judgements."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from tdec.config import ModelConfig, TopicConfig

Side = Literal["pro", "con"]


@dataclass(frozen=True)
class DebateTurn:
    speaker_label: str
    speaker_model_id: str
    side: Side
    turn_number: int
    content: str


@dataclass(frozen=True)
class DebateTranscript:
    id: str
    topic: TopicConfig
    pro_model: ModelConfig
    con_model: ModelConfig
    rounds: int
    turns: list[DebateTurn]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Judgement:
    debate_id: str
    judge_model_id: str
    raw_text: str
    parsed: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

