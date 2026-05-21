from tdec.config import ModelConfig, TopicConfig
from tdec.debate import debate_pairings, run_debate


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

