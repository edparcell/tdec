from tdec.config import ModelConfig, TopicConfig
from tdec.debate import debate_pairings, run_debate
from tdec.debate_types import DebateTranscript, DebateTurn


class StubClient:
    def __init__(self) -> None:
        self.calls = []

    def call(self, model: ModelConfig, messages: list[dict[str, str]]) -> str:
        self.calls.append((model.id, messages[-1]["content"]))
        return f"{model.id} response {len(self.calls)}"


def test_debate_pairings_runs_each_pair_both_ways() -> None:
    models = [
        ModelConfig(id="a", provider="test", model="a"),
        ModelConfig(id="b", provider="test", model="b"),
        ModelConfig(id="c", provider="test", model="c"),
    ]

    assert [(pro.id, con.id) for pro, con in debate_pairings(models)] == [
        ("a", "b"),
        ("b", "a"),
        ("a", "c"),
        ("c", "a"),
        ("b", "c"),
        ("c", "b"),
    ]


def test_run_debate_produces_three_rounds_per_side() -> None:
    topic = TopicConfig(
        id="topic",
        motion="Motion text",
        pro_position="Pro position",
        con_position="Con position",
    )
    pro = ModelConfig(id="model_a", provider="test", model="a")
    con = ModelConfig(id="model_b", provider="test", model="b")
    client = StubClient()

    transcript = run_debate(
        client=client,
        topic=topic,
        pro_model=pro,
        con_model=con,
        rounds=3,
    )

    assert transcript.id == "topic__model_a_pro__model_b_con"
    assert len(transcript.turns) == 6
    assert [turn.side for turn in transcript.turns] == ["pro", "con", "pro", "con", "pro", "con"]
    assert [turn.turn_number for turn in transcript.turns] == [1, 1, 2, 2, 3, 3]
    assert "Go wide" in client.calls[0][1]
    assert "Motion text" in client.calls[1][1]


def test_transcript_artifact_redacts_api_keys() -> None:
    topic = TopicConfig(
        id="topic",
        motion="Motion text",
        pro_position="Pro position",
        con_position="Con position",
    )
    transcript = DebateTranscript(
        id="debate",
        topic=topic,
        pro_model=ModelConfig(id="pro", provider="openrouter", model="model-a", api_key="secret"),
        con_model=ModelConfig(id="con", provider="openrouter", model="model-b", api_key="secret"),
        rounds=1,
        turns=[
            DebateTurn(
                speaker_label="A",
                speaker_model_id="pro",
                side="pro",
                turn_number=1,
                content="hello",
            ),
        ],
    )

    data = transcript.to_dict()

    assert data["pro_model"]["api_key"] == "<redacted>"
    assert data["con_model"]["api_key"] == "<redacted>"
