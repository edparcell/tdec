from langchain_core.messages import BaseMessage

from tdec.config import JudgingConfig, ModelConfig, TopicConfig
from tdec.debate_types import DebateTranscript
from tdec.judging import judge_debate, parse_json_response

from tests._fakes import fake_ai, fake_factory


def test_parse_json_response_accepts_plain_json() -> None:
    parsed = parse_json_response('{"winner": "pro", "confidence": 0.8}')

    assert parsed == {"winner": "pro", "confidence": 0.8}


def test_parse_json_response_extracts_json_from_text() -> None:
    parsed = parse_json_response('Here is my judgement:\n{"winner": "con"}')

    assert parsed == {"winner": "con"}


def test_judge_debate_records_parse_error_instead_of_raising() -> None:
    transcript = DebateTranscript(
        id="debate",
        topic=TopicConfig(id="topic", motion="Motion", pro_position="Pro", con_position="Con"),
        pro_model=ModelConfig(id="pro", provider="test", model="pro"),
        con_model=ModelConfig(id="con", provider="test", model="con"),
        rounds=1,
        turns=[],
    )

    def respond(_model_id: str, _messages: list[BaseMessage]):
        return fake_ai(
            '{"winner": "pro", "summary": "unterminated',
            cost_usd=None,
            cost_error="missing price",
            latency=0.5,
            prompt_tokens=10,
            completion_tokens=4,
        )

    judgement = judge_debate(
        chat_factory=fake_factory(respond),
        transcript=transcript,
        judge_model=ModelConfig(id="judge", provider="test", model="judge"),
    )

    assert judgement.parsed["winner"] == "parse_error"
    assert "Unterminated string" in judgement.parsed["error"]
    assert judgement.metrics is not None
    assert judgement.metrics.cost_error == "missing price"
    assert judgement.attempts is not None
    assert [attempt.kind for attempt in judgement.attempts] == ["initial", "repair", "retry"]


def test_judge_debate_repairs_bad_json() -> None:
    transcript = DebateTranscript(
        id="debate",
        topic=TopicConfig(id="topic", motion="Motion", pro_position="Pro", con_position="Con"),
        pro_model=ModelConfig(id="pro", provider="test", model="pro"),
        con_model=ModelConfig(id="con", provider="test", model="con"),
        rounds=1,
        turns=[],
    )

    calls: list[list[BaseMessage]] = []

    def respond(_model_id: str, messages: list[BaseMessage]):
        calls.append(list(messages))
        if len(calls) == 2:
            return fake_ai(
                '{"winner": "con", "winner_label": "B", "confidence": 0.6}',
                cost_usd=0.001,
                latency=0.5,
                prompt_tokens=10,
                completion_tokens=4,
            )
        return fake_ai(
            '{"winner": "con", "summary": "unterminated',
            cost_usd=0.001,
            latency=0.5,
            prompt_tokens=10,
            completion_tokens=4,
        )

    judgement = judge_debate(
        chat_factory=fake_factory(respond),
        transcript=transcript,
        judge_model=ModelConfig(id="judge", provider="test", model="judge"),
        judging_config=JudgingConfig(repair_retries=1, parse_retries=0),
    )

    assert judgement.parsed["winner"] == "con"
    assert judgement.attempts is not None
    assert [attempt.kind for attempt in judgement.attempts] == ["initial", "repair"]
    assert "not valid JSON" in str(calls[1][-1].content)
