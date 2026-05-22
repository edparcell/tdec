from pathlib import Path
import json
import threading
import time

from tdec.config import (
    DebaterConfig,
    JudgeModelConfig,
    JudgingConfig,
    ModelConfig,
    RunConfig,
    TopicConfig,
    TournamentConfig,
    load_prompt_set_config,
)
from tdec.debate_types import ModelCallMetrics, ModelCallResult, TokenUsage
from tdec.models import ModelCallError
from tdec.tournament import run_tournament

_PROMPT_SET_CONFIG = load_prompt_set_config(Path("configs/prompt-sets/default.yaml"))


def _config(tmp_path: Path, **overrides) -> TournamentConfig:
    defaults = {
        "run": RunConfig(name="test", rounds=1, output_dir=tmp_path, include_self_debates=False),
        "topics": [TopicConfig(id="topic", motion="Motion")],
        "debaters": [
            DebaterConfig(id="a", provider="test", model="a"),
            DebaterConfig(id="b", provider="test", model="b"),
            DebaterConfig(id="c", provider="test", model="c"),
        ],
        "judges": [
            JudgeModelConfig(id="judge_1", provider="test", model="j1"),
            JudgeModelConfig(id="judge_2", provider="test", model="j2"),
        ],
        "judging": JudgingConfig(),
        "prompt_set": _PROMPT_SET_CONFIG,
    }
    defaults.update(overrides)
    return TournamentConfig(**defaults)


class StubClient:
    def __init__(self) -> None:
        self.calls = 0
        self.judge_calls = 0

    def call(self, model: ModelConfig, messages: list[dict[str, str]]) -> ModelCallResult:
        self.calls += 1
        if model.id.startswith("judge"):
            self.judge_calls += 1
            winner = "pro" if self.judge_calls <= 6 else "con"
            winner_label = "A" if winner == "pro" else "B"
            return self._result(
                model,
                f'{{"winner": "{winner}", "winner_label": "{winner_label}", "confidence": 0.7}}',
            )
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


class FailingDebateClient(StubClient):
    def call(self, model: ModelConfig, messages: list[dict[str, str]]) -> ModelCallResult:
        raise ModelCallError(model, RuntimeError("provider unavailable api_key=sk-secret123456"))


class FailingJudgeClient(StubClient):
    def call(self, model: ModelConfig, messages: list[dict[str, str]]) -> ModelCallResult:
        if model.id.startswith("judge"):
            raise ModelCallError(model, RuntimeError("provider unavailable"))
        return super().call(model, messages)


class MetadataClient(StubClient):
    def _result(self, model: ModelConfig, content: str) -> ModelCallResult:
        result = super()._result(model, content)
        return ModelCallResult(
            content=content,
            metrics=ModelCallMetrics(
                model_id=result.metrics.model_id,
                provider=result.metrics.provider,
                model=result.metrics.model,
                latency_seconds=result.metrics.latency_seconds,
                usage=result.metrics.usage,
                cost_usd=result.metrics.cost_usd,
                response_metadata={
                    "id": "response-id",
                    "model": model.model,
                    "provider": model.provider,
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "index": 0,
                            "message": {
                                "content": content,
                                "role": "assistant",
                                "reasoning_content": "one kept reasoning copy",
                                "provider_specific_fields": {
                                    "reasoning": "duplicate reasoning",
                                    "reasoning_content": "duplicate reasoning",
                                    "reasoning_details": [
                                        {"type": "reasoning.encrypted", "data": "encrypted"}
                                    ],
                                },
                            },
                        }
                    ],
                },
            ),
        )


class BlankMetadataClient(MetadataClient):
    def _result(self, model: ModelConfig, content: str) -> ModelCallResult:
        return super()._result(model, "")


class ThreadRecordingClient(StubClient):
    def __init__(self) -> None:
        super().__init__()
        self.thread_ids: set[int] = set()
        self.lock = threading.Lock()

    def call(self, model: ModelConfig, messages: list[dict[str, str]]) -> ModelCallResult:
        with self.lock:
            self.thread_ids.add(threading.get_ident())
        time.sleep(0.02)
        return self._result(model, f"{model.id} debate response")


def test_run_tournament_writes_debates_judgements_and_summary(tmp_path: Path) -> None:
    config = _config(tmp_path)
    summary = run_tournament(config=config, client=StubClient())
    run_dir = Path(summary["run_dir"])

    assert len(summary["debates"]) == 6
    assert summary["total_cost_usd"] == 0.24
    assert summary["errors"] == []
    assert summary["total_latency_seconds"] == 24.0
    assert summary["motions"] == [
        {
            "topic_id": "topic",
            "pro_judges": 6,
            "con_judges": 6,
            "tie_judges": 0,
            "result": "tied",
        },
    ]
    assert len(summary["pairs"]) == 6
    assert summary["pairs"][0]["pro_judges"] == 2
    assert summary["pairs"][0]["con_judges"] == 0
    assert summary["pairs"][-1]["pro_judges"] == 0
    assert summary["pairs"][-1]["con_judges"] == 2
    assert summary["pair_matrices"] == [
        {
            "topic_id": "topic",
            "pro_model_ids": ["a", "b", "c"],
            "con_model_ids": ["a", "b", "c"],
            "cells": {
                "a": {
                    "b": {
                        "debate_id": "topic__a_pro__b_con",
                        "result": "2/0",
                        "pro_judges": 2,
                        "con_judges": 0,
                        "tie_judges": 0,
                        "parse_errors": 0,
                    },
                    "c": {
                        "debate_id": "topic__a_pro__c_con",
                        "result": "2/0",
                        "pro_judges": 2,
                        "con_judges": 0,
                        "tie_judges": 0,
                        "parse_errors": 0,
                    },
                },
                "b": {
                    "a": {
                        "debate_id": "topic__b_pro__a_con",
                        "result": "2/0",
                        "pro_judges": 2,
                        "con_judges": 0,
                        "tie_judges": 0,
                        "parse_errors": 0,
                    },
                    "c": {
                        "debate_id": "topic__b_pro__c_con",
                        "result": "0/2",
                        "pro_judges": 0,
                        "con_judges": 2,
                        "tie_judges": 0,
                        "parse_errors": 0,
                    },
                },
                "c": {
                    "a": {
                        "debate_id": "topic__c_pro__a_con",
                        "result": "0/2",
                        "pro_judges": 0,
                        "con_judges": 2,
                        "tie_judges": 0,
                        "parse_errors": 0,
                    },
                    "b": {
                        "debate_id": "topic__c_pro__b_con",
                        "result": "0/2",
                        "pro_judges": 0,
                        "con_judges": 2,
                        "tie_judges": 0,
                        "parse_errors": 0,
                    },
                },
            },
        }
    ]
    assert {model["model_id"] for model in summary["models"]} == {
        "a", "b", "c", "judge_1", "judge_2"
    }
    assert {model["model_id"]: model["calls"] for model in summary["models"]} == {
        "a": 4, "b": 4, "c": 4, "judge_1": 6, "judge_2": 6,
    }
    debater_elos = {
        model["model_id"]: model["elo"]
        for model in summary["models"]
        if "debater" in model["roles"]
    }
    assert set(debater_elos) == {"a", "b", "c"}
    assert debater_elos["a"] > debater_elos["b"] > debater_elos["c"]
    assert all(debate["judgement_count"] == 2 for debate in summary["debates"])
    assert all(debate["parse_errors"] == 0 for debate in summary["debates"])
    assert all(debate["debate_cost_usd"] == 0.02 for debate in summary["debates"])
    assert all(debate["judging_cost_usd"] == 0.02 for debate in summary["debates"])
    assert len(list((run_dir / "debates").glob("*.json"))) == 6
    assert len(list((run_dir / "judgements").glob("*.json"))) == 12
    assert (run_dir / "summary.json").is_file()
    assert (run_dir / "summary.md").is_file()
    summary_md = (run_dir / "summary.md").read_text(encoding="utf-8")
    assert "| Pro \\ Con | `a` | `b` | `c` |" in summary_md
    assert "| `a` | - | 2/0 | 2/0 |" in summary_md


def test_run_tournament_includes_self_debates_by_default(tmp_path: Path) -> None:
    config = _config(
        tmp_path,
        run=RunConfig(name="test", rounds=1, output_dir=tmp_path),
        debaters=[
            DebaterConfig(id="a", provider="test", model="a"),
            DebaterConfig(id="b", provider="test", model="b"),
        ],
        judges=[JudgeModelConfig(id="judge_1", provider="test", model="j1")],
    )

    summary = run_tournament(config=config, client=StubClient())

    assert [pair["debate_id"] for pair in summary["pairs"]] == [
        "topic__a_pro__a_con",
        "topic__a_pro__b_con",
        "topic__b_pro__a_con",
        "topic__b_pro__b_con",
    ]


def test_run_tournament_uses_thread_pool_workers(tmp_path: Path) -> None:
    config = _config(
        tmp_path,
        run=RunConfig(name="test", rounds=1, output_dir=tmp_path, include_self_debates=False, workers=2),
        judges=[],
    )
    client = ThreadRecordingClient()

    summary = run_tournament(config=config, client=client)

    assert len(summary["debates"]) == 6
    assert len(client.thread_ids) > 1


def test_run_tournament_marks_total_cost_unknown_when_component_cost_is_unknown(
    tmp_path: Path,
) -> None:
    config = _config(
        tmp_path,
        debaters=[
            DebaterConfig(id="a", provider="test", model="a"),
            DebaterConfig(id="b", provider="test", model="b"),
        ],
        judges=[JudgeModelConfig(id="judge_1", provider="test", model="j1")],
    )

    summary = run_tournament(config=config, client=UnknownCostClient())

    assert summary["total_cost_usd"] is None
    assert summary["cost_errors"]


def test_run_tournament_skips_failed_debates_and_logs_errors(tmp_path: Path) -> None:
    config = _config(
        tmp_path,
        debaters=[
            DebaterConfig(id="a", provider="test", model="a"),
            DebaterConfig(id="b", provider="test", model="b"),
        ],
        judges=[JudgeModelConfig(id="judge_1", provider="test", model="j1")],
    )

    summary = run_tournament(config=config, client=FailingDebateClient())
    run_dir = Path(summary["run_dir"])

    assert summary["debates"] == []
    assert len(summary["errors"]) == 2
    assert len(list((run_dir / "debates").glob("*.json"))) == 0
    assert len(list((run_dir / "errors").glob("*.json"))) == 2
    assert summary["errors"][0]["error_message"] == "provider unavailable api_key=<redacted>"


def test_run_tournament_skips_failed_judgements_and_logs_errors(tmp_path: Path) -> None:
    config = _config(
        tmp_path,
        debaters=[
            DebaterConfig(id="a", provider="test", model="a"),
            DebaterConfig(id="b", provider="test", model="b"),
        ],
        judges=[JudgeModelConfig(id="judge_1", provider="test", model="j1")],
    )

    summary = run_tournament(config=config, client=FailingJudgeClient())

    assert len(summary["debates"]) == 2
    assert len(summary["errors"]) == 2
    assert all(debate["judgement_count"] == 0 for debate in summary["debates"])


def test_default_artifacts_compact_duplicate_response_metadata(tmp_path: Path) -> None:
    config = _config(
        tmp_path,
        debaters=[
            DebaterConfig(id="a", provider="test", model="a"),
            DebaterConfig(id="b", provider="test", model="b"),
        ],
        judges=[],
    )

    summary = run_tournament(config=config, client=MetadataClient())
    run_dir = Path(summary["run_dir"])
    debate_path = next((run_dir / "debates").glob("*.json"))
    data = json.loads(debate_path.read_text(encoding="utf-8"))
    turn = data["turns"][0]
    message = turn["metrics"]["response_metadata"]["choices"][0]["message"]

    assert turn["content"]
    assert message == {
        "role": "assistant",
        "reasoning_content": "one kept reasoning copy",
    }


def test_blank_content_preserves_full_response_metadata_by_default(tmp_path: Path) -> None:
    config = _config(
        tmp_path,
        debaters=[
            DebaterConfig(id="a", provider="test", model="a"),
            DebaterConfig(id="b", provider="test", model="b"),
        ],
        judges=[],
    )

    summary = run_tournament(config=config, client=BlankMetadataClient())
    run_dir = Path(summary["run_dir"])
    debate_path = next((run_dir / "debates").glob("*.json"))
    data = json.loads(debate_path.read_text(encoding="utf-8"))
    message = data["turns"][0]["metrics"]["response_metadata"]["choices"][0]["message"]

    assert data["turns"][0]["content"] == ""
    assert message["content"] == ""
    assert message["provider_specific_fields"]["reasoning_details"][0]["data"] == "encrypted"
