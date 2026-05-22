"""Judging orchestration and JSON parsing."""

from __future__ import annotations

import json
import re

from tdec.config import JudgeModelConfig, JudgingConfig
from tdec.debate_types import DebateTranscript, JudgeAttempt, Judgement, ModelCallResult
from tdec.models import ChatModel
from tdec.prompts import PromptSet


def judge_debate(
    *,
    client: ChatModel,
    transcript: DebateTranscript,
    judge_model: JudgeModelConfig,
    judging_config: JudgingConfig | None = None,
    prompt_set: PromptSet,
) -> Judgement:
    config = judging_config or JudgingConfig()
    base_messages = [
        {"role": "system", "content": prompt_set.render_judge_system(style=judge_model.style)},
        {"role": "user", "content": prompt_set.render_judge(transcript=transcript)},
    ]
    attempts: list[JudgeAttempt] = []

    initial = _attempt(client, judge_model, "initial", base_messages)
    attempts.append(initial)
    if initial.parsed is not None:
        return _judgement_from_attempts(transcript.id, judge_model.id, attempts)

    for _ in range(config.repair_retries):
        repair = _attempt(
            client,
            judge_model,
            "repair",
            [
                *base_messages,
                {"role": "assistant", "content": attempts[-1].raw_text},
                {
                    "role": "user",
                    "content": prompt_set.render_judge_repair(
                        bad_output=attempts[-1].raw_text,
                        error=attempts[-1].error or "unknown error",
                    ),
                },
            ],
        )
        attempts.append(repair)
        if repair.parsed is not None:
            return _judgement_from_attempts(transcript.id, judge_model.id, attempts)

    for _ in range(config.parse_retries):
        retry = _attempt(client, judge_model, "retry", base_messages)
        attempts.append(retry)
        if retry.parsed is not None:
            return _judgement_from_attempts(transcript.id, judge_model.id, attempts)

    return _judgement_from_attempts(transcript.id, judge_model.id, attempts)


def _attempt(
    client: ChatModel,
    judge_model: JudgeModelConfig,
    kind: str,
    messages: list[dict[str, str]],
) -> JudgeAttempt:
    result = client.call(judge_model, messages)
    parsed, error = _parse_attempt(result)
    return JudgeAttempt(
        kind=kind,
        raw_text=result.content,
        parsed=parsed,
        error=error,
        metrics=result.metrics,
    )


def _parse_attempt(result: ModelCallResult) -> tuple[dict | None, str | None]:
    try:
        return parse_json_response(result.content), None
    except (json.JSONDecodeError, ValueError) as e:
        return None, str(e)


def _judgement_from_attempts(
    debate_id: str,
    judge_model_id: str,
    attempts: list[JudgeAttempt],
) -> Judgement:
    final = next(
        (attempt for attempt in reversed(attempts) if attempt.parsed is not None), attempts[-1]
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
        metrics=final.metrics,
        attempts=attempts,
    )


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
