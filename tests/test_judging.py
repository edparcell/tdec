from pathlib import Path

from tdec.config import DebaterConfig, JudgeModelConfig, JudgingConfig, TopicConfig, load_prompt_set_config
from tdec.debate_types import (
    DebateTranscript,
    ModelCallMetrics,
    ModelCallResult,
    TokenUsage,
)
from tdec.judging import judge_debate, parse_json_response
from tdec.prompts import PromptSet

_PROMPT_SET = PromptSet(load_prompt_set_config(Path("configs/prompt-sets/default.yaml")))


def test_parse_json_response_accepts_plain_json() -> None:
    parsed = parse_json_response('{"winner": "pro", "confidence": 0.8}')

    assert parsed == {"winner": "pro", "confidence": 0.8}


def test_parse_json_response_extracts_json_from_text() -> None:
    parsed = parse_json_response('Here is my judgement:\n{"winner": "con"}')

    assert parsed == {"winner": "con"}


class BadJsonClient:
    def call(self, model, messages):
        return ModelCallResult(
            content='{"winner": "pro", "summary": "unterminated',
            metrics=ModelCallMetrics(
                model_id=model.id,
                provider=model.provider,
                model=model.model,
                latency_seconds=0.5,
                usage=TokenUsage(prompt_tokens=10, completion_tokens=4, total_tokens=14),
                cost_usd=None,
                cost_error="missing price",
            ),
        )


class RepairJsonClient:
    def __init__(self) -> None:
        self.calls: list[list[dict[str, str]]] = []

    def call(self, model, messages):
        self.calls.append(messages)
        content = (
            '{"winner": "con", "winner_label": "B", "confidence": 0.6}'
            if len(self.calls) == 2
            else '{"winner": "con", "summary": "unterminated'
        )
        return _result(model, content)


def _result(model, content: str) -> ModelCallResult:
    return ModelCallResult(
        content=content,
        metrics=ModelCallMetrics(
            model_id=model.id,
            provider=model.provider,
            model=model.model,
            latency_seconds=0.5,
            usage=TokenUsage(prompt_tokens=10, completion_tokens=4, total_tokens=14),
            cost_usd=0.001,
        ),
    )


def _transcript() -> DebateTranscript:
    return DebateTranscript(
        id="debate",
        topic=TopicConfig(id="topic", motion="Motion"),
        pro_model=DebaterConfig(strategy="", id="pro", provider="test", model="pro"),
        con_model=DebaterConfig(strategy="", id="con", provider="test", model="con"),
        rounds=1,
        turns=[],
    )


def test_judge_debate_records_parse_error_instead_of_raising() -> None:
    judgement = judge_debate(
        client=BadJsonClient(),
        transcript=_transcript(),
        judge_model=JudgeModelConfig(style="", id="judge", provider="test", model="judge"),
        prompt_set=_PROMPT_SET,
    )

    assert judgement.parsed["winner"] == "parse_error"
    assert "Unterminated string" in judgement.parsed["error"]
    assert judgement.metrics is not None
    assert judgement.metrics.cost_error == "missing price"
    assert judgement.attempts is not None
    assert [attempt.kind for attempt in judgement.attempts] == ["initial", "repair", "retry"]


def test_judge_debate_repairs_bad_json() -> None:
    client = RepairJsonClient()

    judgement = judge_debate(
        client=client,
        transcript=_transcript(),
        judge_model=JudgeModelConfig(style="", id="judge", provider="test", model="judge"),
        judging_config=JudgingConfig(repair_retries=1, parse_retries=0),
        prompt_set=_PROMPT_SET,
    )

    assert judgement.parsed["winner"] == "con"
    assert judgement.attempts is not None
    assert [attempt.kind for attempt in judgement.attempts] == ["initial", "repair"]
    assert "not valid JSON" in client.calls[1][-1]["content"]
