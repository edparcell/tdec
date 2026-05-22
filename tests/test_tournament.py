from pathlib import Path
import json
import threading
import time

import pytest
from langchain_core.messages import BaseMessage

from tdec.config import JudgingConfig, ModelConfig, RunConfig, TopicConfig, TournamentConfig
from tdec.models import ModelCallError
from tdec.tournament import run_tournament

from tests._fakes import fake_ai, fake_factory


def _stub_state():
    """Standard StubClient behaviour: text for debaters, JSON for judges.

    The first 6 judge invocations vote pro; later ones vote con — matches the
    legacy fixture so the existing tournament assertions still pass.
    """
    state = {"judge_calls": 0}

    def respond(model_id: str, _messages: list[BaseMessage]):
        if model_id.startswith("judge"):
            state["judge_calls"] += 1
            winner = "pro" if state["judge_calls"] <= 6 else "con"
            winner_label = "A" if winner == "pro" else "B"
            content = f'{{"winner": "{winner}", "winner_label": "{winner_label}", "confidence": 0.7}}'
            return fake_ai(content)
        return fake_ai(f"{model_id} debate response")

    return respond


def _unknown_cost_responder():
    base = _stub_state()

    def respond(model_id, messages):
        ai = base(model_id, messages)
        ai.additional_kwargs["tdec_cost_usd"] = None
        ai.additional_kwargs["tdec_cost_error"] = "missing price"
        return ai

    return respond


def _failing_debate_responder():
    def respond(_model_id, _messages):
        raise RuntimeError("provider unavailable api_key=sk-secret123456")

    return respond


def _failing_judge_responder():
    base = _stub_state()

    def respond(model_id, messages):
        if model_id.startswith("judge"):
            raise RuntimeError("provider unavailable")
        return base(model_id, messages)

    return respond


def _metadata_responder(*, blank: bool = False):
    base = _stub_state()

    def respond(model_id, messages):
        ai = base(model_id, messages)
        content = "" if blank else str(ai.content)
        provider = "test"
        # Mimic litellm's completion response shape so the artifacts compactor
        # has something representative to chew on.
        ai.response_metadata = {
            "id": "response-id",
            "model": model_id,
            "provider": provider,
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
        }
        if blank:
            ai.content = ""
        return ai

    return respond


def _thread_recording_responder(thread_ids: set[int], lock: threading.Lock):
    base = _stub_state()

    def respond(model_id, messages):
        with lock:
            thread_ids.add(threading.get_ident())
        time.sleep(0.02)
        return base(model_id, messages)

    return respond


def test_run_tournament_writes_debates_judgements_and_summary(tmp_path: Path) -> None:
    config = TournamentConfig(
        run=RunConfig(
            name="test",
            rounds=1,
            output_dir=tmp_path,
            include_self_debates=False,
        ),
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
        judging=JudgingConfig(),
    )

    summary = run_tournament(config=config, chat_factory=fake_factory(_stub_state()))
    run_dir = Path(summary["run_dir"])

    assert len(summary["debates"]) == 6
    assert summary["total_cost_usd"] == pytest.approx(0.24)
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
    assert {model["model_id"] for model in summary["models"]} == {"a", "b", "c", "judge_1", "judge_2"}
    assert {model["model_id"]: model["calls"] for model in summary["models"]} == {
        "a": 4,
        "b": 4,
        "c": 4,
        "judge_1": 6,
        "judge_2": 6,
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
    assert all(debate["debate_cost_usd"] == pytest.approx(0.02) for debate in summary["debates"])
    assert all(debate["judging_cost_usd"] == pytest.approx(0.02) for debate in summary["debates"])
    assert len(list((run_dir / "debates").glob("*.json"))) == 6
    assert len(list((run_dir / "judgements").glob("*.json"))) == 12
    assert (run_dir / "summary.json").is_file()
    assert (run_dir / "summary.md").is_file()
    summary_md = (run_dir / "summary.md").read_text(encoding="utf-8")
    assert "| Pro \\ Con | `a` | `b` | `c` |" in summary_md
    assert "| `a` | - | 2/0 | 2/0 |" in summary_md


def test_run_tournament_includes_self_debates_by_default(tmp_path: Path) -> None:
    config = TournamentConfig(
        run=RunConfig(name="test", rounds=1, output_dir=tmp_path),
        topics=[TopicConfig(id="topic", motion="Motion", pro_position="Pro", con_position="Con")],
        debaters=[
            ModelConfig(id="a", provider="test", model="a"),
            ModelConfig(id="b", provider="test", model="b"),
        ],
        judges=[ModelConfig(id="judge_1", provider="test", model="j1")],
        judging=JudgingConfig(),
    )

    summary = run_tournament(config=config, chat_factory=fake_factory(_stub_state()))

    assert [pair["debate_id"] for pair in summary["pairs"]] == [
        "topic__a_pro__a_con",
        "topic__a_pro__b_con",
        "topic__b_pro__a_con",
        "topic__b_pro__b_con",
    ]
    debater_elos = {
        model["model_id"]: model["elo"]
        for model in summary["models"]
        if "debater" in model["roles"]
    }
    assert set(debater_elos) == {"a", "b"}


def test_run_tournament_uses_thread_pool_workers(tmp_path: Path) -> None:
    config = TournamentConfig(
        run=RunConfig(
            name="test",
            rounds=1,
            output_dir=tmp_path,
            include_self_debates=False,
            workers=2,
        ),
        topics=[TopicConfig(id="topic", motion="Motion", pro_position="Pro", con_position="Con")],
        debaters=[
            ModelConfig(id="a", provider="test", model="a"),
            ModelConfig(id="b", provider="test", model="b"),
            ModelConfig(id="c", provider="test", model="c"),
        ],
        judges=[],
        judging=JudgingConfig(),
    )
    thread_ids: set[int] = set()
    lock = threading.Lock()

    summary = run_tournament(
        config=config,
        chat_factory=fake_factory(_thread_recording_responder(thread_ids, lock)),
    )

    assert len(summary["debates"]) == 6
    assert len(thread_ids) > 1


def test_run_tournament_marks_total_cost_unknown_when_component_cost_is_unknown(
    tmp_path: Path,
) -> None:
    config = TournamentConfig(
        run=RunConfig(
            name="test",
            rounds=1,
            output_dir=tmp_path,
            include_self_debates=False,
        ),
        topics=[TopicConfig(id="topic", motion="Motion", pro_position="Pro", con_position="Con")],
        debaters=[
            ModelConfig(id="a", provider="test", model="a"),
            ModelConfig(id="b", provider="test", model="b"),
        ],
        judges=[ModelConfig(id="judge_1", provider="test", model="j1")],
        judging=JudgingConfig(),
    )

    summary = run_tournament(
        config=config,
        chat_factory=fake_factory(_unknown_cost_responder()),
    )

    assert summary["total_cost_usd"] is None
    assert summary["cost_errors"]


def test_run_tournament_skips_failed_debates_and_logs_errors(tmp_path: Path) -> None:
    config = TournamentConfig(
        run=RunConfig(
            name="test",
            rounds=1,
            output_dir=tmp_path,
            include_self_debates=False,
        ),
        topics=[TopicConfig(id="topic", motion="Motion", pro_position="Pro", con_position="Con")],
        debaters=[
            ModelConfig(id="a", provider="test", model="a"),
            ModelConfig(id="b", provider="test", model="b"),
        ],
        judges=[ModelConfig(id="judge_1", provider="test", model="j1")],
        judging=JudgingConfig(),
    )

    summary = run_tournament(
        config=config,
        chat_factory=fake_factory(_failing_debate_responder()),
    )
    run_dir = Path(summary["run_dir"])

    assert summary["debates"] == []
    assert len(summary["errors"]) == 2
    assert len(list((run_dir / "debates").glob("*.json"))) == 0
    assert len(list((run_dir / "judgements").glob("*.json"))) == 0
    assert len(list((run_dir / "errors").glob("*.json"))) == 2
    assert (run_dir / "errors" / "errors.jsonl").is_file()
    assert summary["errors"][0]["error_message"] == "provider unavailable api_key=<redacted>"


def test_run_tournament_skips_failed_judgements_and_logs_errors(tmp_path: Path) -> None:
    config = TournamentConfig(
        run=RunConfig(
            name="test",
            rounds=1,
            output_dir=tmp_path,
            include_self_debates=False,
        ),
        topics=[TopicConfig(id="topic", motion="Motion", pro_position="Pro", con_position="Con")],
        debaters=[
            ModelConfig(id="a", provider="test", model="a"),
            ModelConfig(id="b", provider="test", model="b"),
        ],
        judges=[ModelConfig(id="judge_1", provider="test", model="j1")],
        judging=JudgingConfig(),
    )

    summary = run_tournament(
        config=config,
        chat_factory=fake_factory(_failing_judge_responder()),
    )
    run_dir = Path(summary["run_dir"])

    assert len(summary["debates"]) == 2
    assert len(summary["errors"]) == 2
    assert all(debate["judgement_count"] == 0 for debate in summary["debates"])
    assert len(list((run_dir / "debates").glob("*.json"))) == 2
    assert len(list((run_dir / "judgements").glob("*.json"))) == 0
    assert len(list((run_dir / "errors").glob("*.json"))) == 2


def test_default_artifacts_compact_duplicate_response_metadata(tmp_path: Path) -> None:
    config = TournamentConfig(
        run=RunConfig(
            name="test",
            rounds=1,
            output_dir=tmp_path,
            include_self_debates=False,
        ),
        topics=[TopicConfig(id="topic", motion="Motion", pro_position="Pro", con_position="Con")],
        debaters=[
            ModelConfig(id="a", provider="test", model="a"),
            ModelConfig(id="b", provider="test", model="b"),
        ],
        judges=[],
        judging=JudgingConfig(),
    )

    summary = run_tournament(
        config=config,
        chat_factory=fake_factory(_metadata_responder()),
    )
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
    config = TournamentConfig(
        run=RunConfig(
            name="test",
            rounds=1,
            output_dir=tmp_path,
            include_self_debates=False,
        ),
        topics=[TopicConfig(id="topic", motion="Motion", pro_position="Pro", con_position="Con")],
        debaters=[
            ModelConfig(id="a", provider="test", model="a"),
            ModelConfig(id="b", provider="test", model="b"),
        ],
        judges=[],
        judging=JudgingConfig(),
    )

    summary = run_tournament(
        config=config,
        chat_factory=fake_factory(_metadata_responder(blank=True)),
    )
    run_dir = Path(summary["run_dir"])
    debate_path = next((run_dir / "debates").glob("*.json"))
    data = json.loads(debate_path.read_text(encoding="utf-8"))
    message = data["turns"][0]["metrics"]["response_metadata"]["choices"][0]["message"]

    assert data["turns"][0]["content"] == ""
    assert message["content"] == ""
    assert message["provider_specific_fields"]["reasoning_details"][0]["data"] == "encrypted"


def test_modelcallerror_propagates_from_fake() -> None:
    # Sanity check that the test fakes can also raise ModelCallError directly.
    model = ModelConfig(id="x", provider="test", model="x")
    raised = ModelCallError(model, RuntimeError("boom"))
    assert "x (test/x) call failed: boom" in str(raised)
