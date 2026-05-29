"""Judging orchestration and JSON parsing."""

from __future__ import annotations

import json

from tdec.config import JudgeModelConfig, JudgingConfig
from tdec.debate_types import DebateTranscript, JudgeAttempt, Judgement, ModelCallResult
from tdec.models import ChatModel
from tdec.prompts import PromptSet

_CACHE_CONTROL = {"type": "ephemeral"}


def judge_debate(
    *,
    client: ChatModel,
    transcript: DebateTranscript,
    judge_model: JudgeModelConfig,
    judging_config: JudgingConfig | None = None,
    prompt_set: PromptSet,
) -> Judgement:
    config = judging_config or JudgingConfig()
    is_parallel = transcript.debate_mode == "parallel"
    judge_sys = prompt_set.render_judge_system(style=judge_model.style, parallel=is_parallel)
    base_messages = [
        {"role": "system", "content": [
            {"type": "text", "text": judge_sys,
             "cache_control": _CACHE_CONTROL},
        ]},
        {"role": "user", "content": [
            {"type": "text", "text": prompt_set.render_judge(transcript=transcript),
             "cache_control": _CACHE_CONTROL},
        ]},
    ]
    attempts: list[JudgeAttempt] = []
    label_to_side = _label_to_side(transcript)

    def _finalize() -> Judgement:
        judgement = _judgement_from_attempts(transcript.id, judge_model.id, attempts)
        _resolve_winner(judgement.parsed, label_to_side)
        return judgement

    initial = _attempt(client, judge_model, "initial", base_messages)
    attempts.append(initial)
    if initial.parsed is not None:
        return _finalize()

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
            return _finalize()

    for _ in range(config.parse_retries):
        retry = _attempt(client, judge_model, "retry", base_messages)
        attempts.append(retry)
        if retry.parsed is not None:
            return _finalize()

    return _finalize()


def _label_to_side(transcript: DebateTranscript) -> dict[str, str]:
    """Map each anonymized debater label (A/B) to its true pro/con side."""
    mapping: dict[str, str] = {}
    for turn in transcript.turns:
        mapping.setdefault(turn.speaker_label, turn.side)
    return mapping


def _resolve_winner(parsed: dict, label_to_side: dict[str, str]) -> None:
    """Derive parsed['winner'] (pro/con) from the judge's winner_label (A/B).

    The judge only sees anonymized labels, so winner_label is the authoritative
    verdict; we map it back to the side via the debate's true label->side
    assignment. When no mapping is available (e.g. a transcript with no turns)
    or the label is unrecognized, the judge's own 'winner' field is left as-is.
    """
    label = parsed.get("winner_label")
    if not isinstance(label, str):
        return
    if label in label_to_side:
        parsed["winner"] = label_to_side[label]
    elif label == "tie":
        parsed["winner"] = "tie"


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
        value = _extract_json_object(text)
        if value is None:
            raise

    if not isinstance(value, dict):
        raise ValueError("Judge response JSON must be an object")
    return value


def _extract_json_object(text: str) -> dict | None:
    """Find an embedded JSON object in noisy model output.

    Tries to decode a complete object at each '{', so prose, code fences, or
    trailing text around the JSON do not break parsing. A greedy first-brace to
    last-brace match would instead concatenate multiple objects (or prose
    braces) into invalid JSON. Prefers an object carrying a 'winner' key (the
    verdict); otherwise returns the first decodable object, or None.
    """
    decoder = json.JSONDecoder()
    candidates: list[dict] = []
    index = 0
    length = len(text)
    while index < length:
        if text[index] != "{":
            index += 1
            continue
        try:
            obj, end = decoder.raw_decode(text, index)
        except json.JSONDecodeError:
            index += 1
            continue
        if isinstance(obj, dict):
            candidates.append(obj)
            index = end
        else:
            index += 1
    for obj in candidates:
        if "winner" in obj:
            return obj
    return candidates[0] if candidates else None
