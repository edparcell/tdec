"""Judging orchestration and JSON parsing."""

from __future__ import annotations

import json
import re

from tdec.config import ModelConfig
from tdec.debate_types import DebateTranscript, Judgement
from tdec.models import ChatModel
from tdec.prompts import JUDGE_SYSTEM_PROMPT, judge_prompt


def judge_debate(
    *,
    client: ChatModel,
    transcript: DebateTranscript,
    judge_model: ModelConfig,
) -> Judgement:
    raw = client.call(
        judge_model,
        [
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": judge_prompt(transcript)},
        ],
    )
    parsed = parse_json_response(raw)
    return Judgement(
        debate_id=transcript.id,
        judge_model_id=judge_model.id,
        raw_text=raw,
        parsed=parsed,
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

