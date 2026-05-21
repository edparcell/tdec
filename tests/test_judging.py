from tdec.config import ModelConfig, TopicConfig
from tdec.debate_types import DebateTranscript
from tdec.judging import judge_debate, parse_json_response


def test_parse_json_response_accepts_plain_json() -> None:
    parsed = parse_json_response('{"winner": "pro", "confidence": 0.8}')

    assert parsed == {"winner": "pro", "confidence": 0.8}


def test_parse_json_response_extracts_json_from_text() -> None:
    parsed = parse_json_response('Here is my judgement:\n{"winner": "con"}')

    assert parsed == {"winner": "con"}


class BadJsonClient:
    def call(self, model: ModelConfig, messages: list[dict[str, str]]) -> str:
        return '{"winner": "pro", "summary": "unterminated'


def test_judge_debate_records_parse_error_instead_of_raising() -> None:
    transcript = DebateTranscript(
        id="debate",
        topic=TopicConfig(id="topic", motion="Motion", pro_position="Pro", con_position="Con"),
        pro_model=ModelConfig(id="pro", provider="test", model="pro"),
        con_model=ModelConfig(id="con", provider="test", model="con"),
        rounds=1,
        turns=[],
    )

    judgement = judge_debate(
        client=BadJsonClient(),
        transcript=transcript,
        judge_model=ModelConfig(id="judge", provider="test", model="judge"),
    )

    assert judgement.parsed["winner"] == "parse_error"
    assert "Unterminated string" in judgement.parsed["error"]
