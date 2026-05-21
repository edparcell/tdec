from pathlib import Path

from tdec.config import ModelConfig, RunConfig, TopicConfig, TournamentConfig
from tdec.debate_types import ModelCallMetrics, ModelCallResult, TokenUsage
from tdec.tournament import run_tournament


class StubClient:
    def __init__(self) -> None:
        self.calls = 0

    def call(self, model: ModelConfig, messages: list[dict[str, str]]) -> ModelCallResult:
        self.calls += 1
        if model.id.startswith("judge"):
            return self._result(model, '{"winner": "pro", "winner_label": "A", "confidence": 0.7}')
        return self._result(model, f"{model.id} debate response")

    def _result(self, model: ModelConfig, content: str) -> ModelCallResult:
        return ModelCallResult(
            content=content,
            metrics=ModelCallMetrics(
                model_id=model.id,
                provider=model.provider,
                model=model.model,
                latency_seconds=1.0,
                usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
                cost_usd=0.01,
            ),
        )


class UnknownCostClient(StubClient):
    def _result(self, model: ModelConfig, content: str) -> ModelCallResult:
        result = super()._result(model, content)
        return ModelCallResult(
            content=result.content,
            metrics=ModelCallMetrics(
                model_id=result.metrics.model_id,
                provider=result.metrics.provider,
                model=result.metrics.model,
                latency_seconds=result.metrics.latency_seconds,
                usage=result.metrics.usage,
                cost_usd=None,
                cost_error="missing price",
            ),
        )


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
    assert summary["total_cost_usd"] == 0.24
    assert summary["total_latency_seconds"] == 24.0
    assert all(debate["judgement_count"] == 2 for debate in summary["debates"])
    assert all(debate["parse_errors"] == 0 for debate in summary["debates"])
    assert all(debate["debate_cost_usd"] == 0.02 for debate in summary["debates"])
    assert all(debate["judging_cost_usd"] == 0.02 for debate in summary["debates"])
    assert len(list((run_dir / "debates").glob("*.json"))) == 6
    assert len(list((run_dir / "judgements").glob("*.json"))) == 12
    assert (run_dir / "summary.json").is_file()
    assert (run_dir / "summary.md").is_file()


def test_run_tournament_marks_total_cost_unknown_when_component_cost_is_unknown(
    tmp_path: Path,
) -> None:
    config = TournamentConfig(
        run=RunConfig(name="test", rounds=1, output_dir=tmp_path),
        topics=[TopicConfig(id="topic", motion="Motion", pro_position="Pro", con_position="Con")],
        debaters=[
            ModelConfig(id="a", provider="test", model="a"),
            ModelConfig(id="b", provider="test", model="b"),
        ],
        judges=[ModelConfig(id="judge_1", provider="test", model="j1")],
    )

    summary = run_tournament(config=config, client=UnknownCostClient())

    assert summary["total_cost_usd"] is None
    assert summary["cost_errors"]
