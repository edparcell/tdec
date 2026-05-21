from pathlib import Path

from tdec.config import ModelConfig, RunConfig, TopicConfig, TournamentConfig
from tdec.tournament import run_tournament


class StubClient:
    def __init__(self) -> None:
        self.calls = 0

    def call(self, model: ModelConfig, messages: list[dict[str, str]]) -> str:
        self.calls += 1
        if model.id.startswith("judge"):
            return '{"winner": "pro", "winner_label": "A", "confidence": 0.7}'
        return f"{model.id} debate response"


def test_run_tournament_writes_debates_judgements_and_summary(tmp_path: Path) -> None:
    config = TournamentConfig(
        run=RunConfig(name="test", rounds=1, output_dir=tmp_path),
        topics=[
            TopicConfig(
                id="topic",
                motion="Motion",
                pro_position="Pro",
                con_position="Con",
            ),
        ],
        debaters=[
            ModelConfig(id="a", provider="test", model="a"),
            ModelConfig(id="b", provider="test", model="b"),
            ModelConfig(id="c", provider="test", model="c"),
        ],
        judges=[
            ModelConfig(id="judge_1", provider="test", model="j1"),
            ModelConfig(id="judge_2", provider="test", model="j2"),
        ],
    )

    summary = run_tournament(config=config, client=StubClient())
    run_dir = Path(summary["run_dir"])

    assert len(summary["debates"]) == 6
    assert all(debate["judgement_count"] == 2 for debate in summary["debates"])
    assert all(debate["parse_errors"] == 0 for debate in summary["debates"])
    assert len(list((run_dir / "debates").glob("*.json"))) == 6
    assert len(list((run_dir / "judgements").glob("*.json"))) == 12
    assert (run_dir / "summary.json").is_file()
    assert (run_dir / "summary.md").is_file()
