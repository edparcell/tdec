from langchain_core.messages import BaseMessage

from tdec.config import ModelConfig, TopicConfig
from tdec.debate import debate_pairings, run_debate
from tdec.debate_types import DebateTranscript, DebateTurn

from tests._fakes import fake_ai, fake_factory


def test_debate_pairings_includes_self_debates_by_default() -> None:
    models = [
        ModelConfig(id="a", provider="test", model="a"),
        ModelConfig(id="b", provider="test", model="b"),
        ModelConfig(id="c", provider="test", model="c"),
    ]

    assert [(pro.id, con.id) for pro, con in debate_pairings(models)] == [
        ("a", "a"),
        ("a", "b"),
        ("b", "a"),
        ("a", "c"),
        ("c", "a"),
        ("b", "b"),
        ("b", "c"),
        ("c", "b"),
        ("c", "c"),
    ]


def test_debate_pairings_can_skip_self_debates() -> None:
    models = [
        ModelConfig(id="a", provider="test", model="a"),
        ModelConfig(id="b", provider="test", model="b"),
        ModelConfig(id="c", provider="test", model="c"),
    ]

    assert [
        (pro.id, con.id)
        for pro, con in debate_pairings(models, include_self_debates=False)
    ] == [
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

    calls: list[tuple[str, str]] = []
    counter = {"n": 0}

    def respond(model_id: str, messages: list[BaseMessage]):
        counter["n"] += 1
        last_human = messages[-1].content
        calls.append((model_id, str(last_human)))
        return fake_ai(
            f"{model_id} response {counter['n']}",
            cost_usd=0.001,
            latency=0.25,
        )

    transcript = run_debate(
        chat_factory=fake_factory(respond),
        topic=topic,
        pro_model=pro,
        con_model=con,
        rounds=3,
    )

    assert transcript.id == "topic__model_a_pro__model_b_con"
    assert len(transcript.turns) == 6
    assert [turn.side for turn in transcript.turns] == ["pro", "con", "pro", "con", "pro", "con"]
    assert [turn.turn_number for turn in transcript.turns] == [1, 1, 2, 2, 3, 3]
    assert transcript.turns[0].metrics is not None
    assert transcript.turns[0].metrics.cost_usd == 0.001
    assert "Go wide" in calls[0][1]
    assert "Motion text" in calls[1][1]


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
