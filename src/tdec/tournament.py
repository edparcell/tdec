"""Tournament orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict

from tdec.artifacts import make_run_dir, write_debate, write_judgement, write_summary
from tdec.config import TournamentConfig
from tdec.debate import debate_pairings, run_debate
from tdec.debate_types import DebateTranscript, Judgement
from tdec.judging import judge_debate
from tdec.models import ChatModel


class TournamentResult(TypedDict):
    run_dir: str
    debates: list[dict]


def run_tournament(
    *,
    config: TournamentConfig,
    client: ChatModel,
    output_dir: Path | None = None,
) -> TournamentResult:
    base_output_dir = output_dir or config.run.output_dir
    run_dir = make_run_dir(base_output_dir, config.run.name)
    debates: list[DebateTranscript] = []
    judgements: list[Judgement] = []

    for topic in config.topics:
        for pro_model, con_model in debate_pairings(config.debaters):
            transcript = run_debate(
                client=client,
                topic=topic,
                pro_model=pro_model,
                con_model=con_model,
                rounds=config.run.rounds,
            )
            debates.append(transcript)
            write_debate(run_dir, transcript)

            for judge_model in config.judges:
                judgement = judge_debate(
                    client=client,
                    transcript=transcript,
                    judge_model=judge_model,
                    judging_config=config.judging,
                )
                judgements.append(judgement)
                write_judgement(run_dir, judgement)

    summary = summarize(run_dir, debates, judgements)
    write_summary(run_dir, summary)
    return summary


def summarize(
    run_dir: Path,
    debates: list[DebateTranscript],
    judgements: list[Judgement],
) -> TournamentResult:
    debate_summaries = []
    for debate in debates:
        debate_judgements = [j for j in judgements if j.debate_id == debate.id]
        debate_summaries.append({
            "debate_id": debate.id,
            "topic_id": debate.topic.id,
            "pro_model_id": debate.pro_model.id,
            "con_model_id": debate.con_model.id,
            "judgement_count": len(debate_judgements),
            "pro_wins": _count_winners(debate_judgements, "pro"),
            "con_wins": _count_winners(debate_judgements, "con"),
            "ties": _count_winners(debate_judgements, "tie"),
            "parse_errors": _count_winners(debate_judgements, "parse_error"),
            "debate_latency_seconds": _sum_debate_latency(debate),
            "judging_latency_seconds": _sum_judgement_latency(debate_judgements),
            "debate_cost_usd": _sum_debate_cost(debate),
            "judging_cost_usd": _sum_judgement_cost(debate_judgements),
            "cost_errors": _cost_errors(debate, debate_judgements),
        })
    return {
        "run_dir": str(run_dir),
        "total_cost_usd": _sum_optional_costs(
            debate["debate_cost_usd"] for debate in debate_summaries
        )
        + _sum_optional_costs(debate["judging_cost_usd"] for debate in debate_summaries)
        if _all_costs_known(debate_summaries)
        else None,
        "cost_errors": [
            error for debate in debate_summaries for error in debate["cost_errors"]
        ],
        "total_latency_seconds": sum(
            debate["debate_latency_seconds"] + debate["judging_latency_seconds"]
            for debate in debate_summaries
        ),
        "debates": debate_summaries,
    }


def _count_winners(judgements: list[Judgement], winner: str) -> int:
    return sum(1 for judgement in judgements if judgement.parsed.get("winner") == winner)


def _sum_debate_latency(debate: DebateTranscript) -> float:
    return sum(turn.metrics.latency_seconds for turn in debate.turns if turn.metrics is not None)


def _sum_judgement_latency(judgements: list[Judgement]) -> float:
    return sum(j.metrics.latency_seconds for j in judgements if j.metrics is not None)


def _sum_debate_cost(debate: DebateTranscript) -> float | None:
    return _sum_cost(turn.metrics for turn in debate.turns)


def _sum_judgement_cost(judgements: list[Judgement]) -> float | None:
    return _sum_cost(j.metrics for j in judgements)


def _sum_cost(metrics) -> float | None:
    values = [metric.cost_usd for metric in metrics if metric is not None]
    if any(value is None for value in values):
        return None
    return sum(values)


def _all_costs_known(debate_summaries: list[dict]) -> bool:
    return all(
        debate["debate_cost_usd"] is not None and debate["judging_cost_usd"] is not None
        for debate in debate_summaries
    )


def _sum_optional_costs(values) -> float:
    return sum(value for value in values if value is not None)


def _cost_errors(debate: DebateTranscript, judgements: list[Judgement]) -> list[str]:
    errors = []
    for turn in debate.turns:
        if turn.metrics is not None and turn.metrics.cost_error is not None:
            errors.append(f"{turn.speaker_model_id}: {turn.metrics.cost_error}")
    for judgement in judgements:
        if judgement.metrics is not None and judgement.metrics.cost_error is not None:
            errors.append(f"{judgement.judge_model_id}: {judgement.metrics.cost_error}")
    return errors
