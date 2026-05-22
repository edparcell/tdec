"""Judging orchestration and JSON parsing."""

from __future__ import annotations

import json
import re

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from tdec.config import JudgingConfig, ModelConfig
from tdec.debate_types import DebateTranscript, JudgeAttempt, Judgement, ModelCallMetrics
from tdec.models import ChatModelFactory, ModelCallError, metrics_from_ai_message
from tdec.prompts import JUDGE_SYSTEM_PROMPT, judge_prompt, judge_repair_prompt


def judge_debate(
    *,
    chat_factory: ChatModelFactory,
    transcript: DebateTranscript,
    judge_model: ModelConfig,
    judging_config: JudgingConfig | None = None,
) -> Judgement:
    config = judging_config or JudgingConfig()
    chat = chat_factory(judge_model)
    base_messages: list[BaseMessage] = [
        SystemMessage(content=JUDGE_SYSTEM_PROMPT),
        HumanMessage(content=judge_prompt(transcript)),
    ]
    attempts: list[JudgeAttempt] = []

    initial = _attempt(chat, judge_model, "initial", base_messages)
    attempts.append(initial)
    if initial.parsed is not None:
        return _judgement_from_attempts(transcript.id, judge_model.id, attempts)

    for _ in range(config.repair_retries):
        repair_messages: list[BaseMessage] = [
            *base_messages,
            AIMessage(content=attempts[-1].raw_text),
            HumanMessage(
                content=judge_repair_prompt(
                    attempts[-1].raw_text,
                    attempts[-1].error or "unknown error",
                )
            ),
        ]
        repair = _attempt(chat, judge_model, "repair", repair_messages)
        attempts.append(repair)
        if repair.parsed is not None:
            return _judgement_from_attempts(transcript.id, judge_model.id, attempts)

    for _ in range(config.parse_retries):
        retry = _attempt(chat, judge_model, "retry", base_messages)
        attempts.append(retry)
        if retry.parsed is not None:
            return _judgement_from_attempts(transcript.id, judge_model.id, attempts)

    return _judgement_from_attempts(transcript.id, judge_model.id, attempts)


def _attempt(chat, judge_model: ModelConfig, kind: str, messages: list[BaseMessage]) -> JudgeAttempt:
    try:
        ai = chat.invoke(messages)
    except ModelCallError:
        raise
    except Exception as e:
        raise ModelCallError(judge_model, e) from e
    if not isinstance(ai, AIMessage):
        raise TypeError(f"Expected AIMessage from chat.invoke, got {type(ai).__name__}")
    metrics = metrics_from_ai_message(ai, judge_model)
    parsed, error = _parse_attempt(str(ai.content))
    return JudgeAttempt(
        kind=kind,
        raw_text=str(ai.content),
        parsed=parsed,
        error=error,
        metrics=metrics,
    )


def _parse_attempt(text: str) -> tuple[dict | None, str | None]:
    try:
        return parse_json_response(text), None
    except (json.JSONDecodeError, ValueError) as e:
        return None, str(e)


def _judgement_from_attempts(
    debate_id: str,
    judge_model_id: str,
    attempts: list[JudgeAttempt],
) -> Judgement:
    final = next(
        (attempt for attempt in reversed(attempts) if attempt.parsed is not None),
        attempts[-1],
    )
    parsed = final.parsed
    if parsed is None:
        parsed = {
            "winner": "parse_error",
            "winner_label": "parse_error",
            "confidence": 0,
            "error": final.error,
        }
    return Judgement(
        debate_id=debate_id,
        judge_model_id=judge_model_id,
        raw_text=final.raw_text,
        parsed=parsed,
        metrics=_merge_attempt_metrics(attempts),
        attempts=attempts,
    )


def _merge_attempt_metrics(attempts: list[JudgeAttempt]) -> ModelCallMetrics | None:
    # Preserve previous behaviour: the surfaced `metrics` on a Judgement is the
    # successful attempt's metrics (or the last attempt if none parsed).
    successful = next(
        (attempt for attempt in reversed(attempts) if attempt.parsed is not None),
        attempts[-1],
    )
    return successful.metrics


def parse_json_response(text: str) -> dict:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match is None:
            raise
        value = json.loads(match.group(0))

    if not isinstance(value, dict):
        raise ValueError("Judge response JSON must be an object")
    return value
