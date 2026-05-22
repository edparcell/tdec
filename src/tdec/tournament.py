"""Tournament orchestration."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
import re
import traceback
from typing import TypedDict

from tdec.artifacts import (
    ArtifactVerbosity,
    make_run_dir,
    write_debate,
    write_error,
    write_judgement,
    write_summary,
)
from tdec.config import ModelConfig, TournamentConfig
from tdec.debate import debate_pairings, run_debate
from tdec.debate_types import DebateTranscript, Judgement, TournamentError
from tdec.judging import judge_debate
from tdec.models import ChatModel, ModelCallError

ELO_K = 32
STARTING_ELO = 1500.0


class TournamentResult(TypedDict):
    run_dir: str
    debates: list[dict]


@dataclass(frozen=True)
class DebateJob:
    index: int
    topic_index: int
    topic_id: str
    debate_id: str
    pro_model_id: str
    con_model_id: str


@dataclass(frozen=True)
class JudgementJob:
    index: int
    topic_id: str
    debate_id: str
    pro_model_id: str
    con_model_id: str
    judge_model_id: str


def run_tournament(
    *,
    config: TournamentConfig,
    client: ChatModel,
    output_dir: Path | None = None,
    artifact_verbosity: ArtifactVerbosity = "compact",
    workers: int | None = None,
) -> TournamentResult:
    base_output_dir = output_dir or config.run.output_dir
    run_dir = make_run_dir(base_output_dir, config.run.name)
    errors: list[TournamentError] = []
    worker_count = config.run.workers if workers is None else workers
    if worker_count < 1:
        raise ValueError("workers must be at least 1")

    debate_results: list[tuple[int, DebateTranscript]] = []
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(
                run_debate,
                client=client,
                topic=config.topics[job.topic_index],
                pro_model=_model_by_id(config.debaters, job.pro_model_id),
                con_model=_model_by_id(config.debaters, job.con_model_id),
                rounds=config.run.rounds,
            ): job
            for job in _debate_jobs(config)
        }
        for future in as_completed(futures):
            job = futures[future]
            try:
                transcript = future.result()
            except ModelCallError as e:
                error = _tournament_error(
                    stage="debate",
                    topic_id=job.topic_id,
                    debate_id=job.debate_id,
                    pro_model_id=job.pro_model_id,
                    con_model_id=job.con_model_id,
                    judge_model_id=None,
                    exc=e,
                )
                errors.append(error)
                write_error(run_dir, error, len(errors))
                continue
            debate_results.append((job.index, transcript))
            write_debate(run_dir, transcript, artifact_verbosity=artifact_verbosity)

    debates = [transcript for _, transcript in sorted(debate_results, key=lambda item: item[0])]

    judgement_results: list[tuple[int, Judgement]] = []
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(
                judge_debate,
                client=client,
                transcript=transcript,
                judge_model=_model_by_id(config.judges, job.judge_model_id),
                judging_config=config.judging,
            ): job
            for job, transcript in _judgement_jobs(debates, config)
        }
        for future in as_completed(futures):
            job = futures[future]
            try:
                judgement = future.result()
            except ModelCallError as e:
                error = _tournament_error(
                    stage="judgement",
                    topic_id=job.topic_id,
                    debate_id=job.debate_id,
                    pro_model_id=job.pro_model_id,
                    con_model_id=job.con_model_id,
                    judge_model_id=job.judge_model_id,
                    exc=e,
                )
                errors.append(error)
                write_error(run_dir, error, len(errors))
                continue
            judgement_results.append((job.index, judgement))
            write_judgement(run_dir, judgement, artifact_verbosity=artifact_verbosity)

    judgements = [
        judgement for _, judgement in sorted(judgement_results, key=lambda item: item[0])
    ]

    summary = summarize(run_dir, debates, judgements, errors)
    write_summary(run_dir, summary)
    return summary


def _debate_jobs(config: TournamentConfig) -> list[DebateJob]:
    jobs = []
    for topic_index, topic in enumerate(config.topics):
        for pro_model, con_model in debate_pairings(
            config.debaters,
            include_self_debates=config.run.include_self_debates,
        ):
            jobs.append(
                DebateJob(
                    index=len(jobs),
                    topic_index=topic_index,
                    topic_id=topic.id,
                    debate_id=f"{topic.id}__{pro_model.id}_pro__{con_model.id}_con",
                    pro_model_id=pro_model.id,
                    con_model_id=con_model.id,
                )
            )
    return jobs


def _judgement_jobs(
    debates: list[DebateTranscript],
    config: TournamentConfig,
) -> list[tuple[JudgementJob, DebateTranscript]]:
    jobs = []
    for debate in debates:
        for judge_model in config.judges:
            jobs.append((
                JudgementJob(
                    index=len(jobs),
                    topic_id=debate.topic.id,
                    debate_id=debate.id,
                    pro_model_id=debate.pro_model.id,
                    con_model_id=debate.con_model.id,
                    judge_model_id=judge_model.id,
                ),
                debate,
            ))
    return jobs


def _model_by_id(models: list[ModelConfig], model_id: str) -> ModelConfig:
    return next(model for model in models if model.id == model_id)


def summarize(
    run_dir: Path,
    debates: list[DebateTranscript],
    judgements: list[Judgement],
    errors: list[TournamentError] | None = None,
) -> TournamentResult:
    errors = errors or []
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
    model_summaries = _model_summaries(debates, judgements)
    pair_summaries = _pair_summaries(debate_summaries)
    pair_matrices = _pair_matrices(pair_summaries)
    motion_summaries = _motion_summaries(debate_summaries)
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
        "errors": [error.to_dict() for error in errors],
        "total_latency_seconds": sum(
            debate["debate_latency_seconds"] + debate["judging_latency_seconds"]
            for debate in debate_summaries
        ),
        "models": model_summaries,
        "pairs": pair_summaries,
        "pair_matrices": pair_matrices,
        "motions": motion_summaries,
        "debates": debate_summaries,
    }


def _tournament_error(
    *,
    stage: str,
    topic_id: str,
    debate_id: str,
    pro_model_id: str,
    con_model_id: str,
    judge_model_id: str | None,
    exc: ModelCallError,
) -> TournamentError:
    return TournamentError(
        stage=stage,
        topic_id=topic_id,
        debate_id=debate_id,
        pro_model_id=pro_model_id,
        con_model_id=con_model_id,
        judge_model_id=judge_model_id,
        model_id=exc.model_id,
        error_type=type(exc.cause).__name__,
        error_message=_redact_error_text(str(exc.cause)),
        traceback=_redact_error_text("".join(traceback.format_exception(exc.cause))),
    )


def _redact_error_text(text: str) -> str:
    redacted = re.sub(r"\b(sk-[A-Za-z0-9_-]{8,})\b", "sk-<redacted>", text)
    redacted = re.sub(r"\b(gh[opsu]_[A-Za-z0-9_]{8,})\b", "gh-<redacted>", redacted)
    redacted = re.sub(
        r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{8,}",
        r"\1<redacted>",
        redacted,
    )
    redacted = re.sub(
        r"(?i)((?:api[_-]?key|authorization|token)\s*[=:]\s*)[^\s,;]+",
        r"\1<redacted>",
        redacted,
    )
    return redacted


def _count_winners(judgements: list[Judgement], winner: str) -> int:
    return sum(1 for judgement in judgements if judgement.parsed.get("winner") == winner)


def _model_summaries(debates: list[DebateTranscript], judgements: list[Judgement]) -> list[dict]:
    totals: dict[str, dict] = {}
    for debate in debates:
        for turn in debate.turns:
            if turn.metrics is not None:
                _add_metric(totals, turn.speaker_model_id, "debater", turn.metrics)
    for judgement in judgements:
        if judgement.metrics is not None:
            _add_metric(totals, judgement.judge_model_id, "judge", judgement.metrics)

    elos = _elo_ratings(debates, judgements)
    rows = []
    for model_id, data in sorted(totals.items()):
        rows.append({
            "model_id": model_id,
            "roles": sorted(data["roles"]),
            "calls": data["calls"],
            "latency_seconds": data["latency_seconds"],
            "cost_usd": data["cost_usd"] if data["unknown_costs"] == 0 else None,
            "unknown_costs": data["unknown_costs"],
            "prompt_tokens": data["prompt_tokens"],
            "completion_tokens": data["completion_tokens"],
            "total_tokens": data["total_tokens"],
            "elo": elos.get(model_id),
        })
    return rows


def _add_metric(totals: dict[str, dict], model_id: str, role: str, metrics) -> None:
    data = totals.setdefault(
        model_id,
        {
            "roles": set(),
            "calls": 0,
            "latency_seconds": 0.0,
            "cost_usd": 0.0,
            "unknown_costs": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    )
    data["roles"].add(role)
    data["calls"] += 1
    data["latency_seconds"] += metrics.latency_seconds
    if metrics.cost_usd is None:
        data["unknown_costs"] += 1
    else:
        data["cost_usd"] += metrics.cost_usd
    data["prompt_tokens"] += metrics.usage.prompt_tokens or 0
    data["completion_tokens"] += metrics.usage.completion_tokens or 0
    data["total_tokens"] += metrics.usage.total_tokens or 0


def _pair_summaries(debate_summaries: list[dict]) -> list[dict]:
    rows = []
    for debate in debate_summaries:
        rows.append({
            "debate_id": debate["debate_id"],
            "topic_id": debate["topic_id"],
            "pro_model_id": debate["pro_model_id"],
            "con_model_id": debate["con_model_id"],
            "pro_judges": debate["pro_wins"],
            "con_judges": debate["con_wins"],
            "tie_judges": debate["ties"],
            "parse_errors": debate["parse_errors"],
        })
    return rows


def _pair_matrices(pair_summaries: list[dict]) -> list[dict]:
    by_topic: dict[str, dict] = {}
    for pair in pair_summaries:
        matrix = by_topic.setdefault(
            pair["topic_id"],
            {
                "topic_id": pair["topic_id"],
                "pro_model_ids": _model_ids_for_topic(pair_summaries, pair["topic_id"]),
                "con_model_ids": _model_ids_for_topic(pair_summaries, pair["topic_id"]),
                "cells": {},
            },
        )
        matrix["cells"].setdefault(pair["pro_model_id"], {})[pair["con_model_id"]] = {
            "debate_id": pair["debate_id"],
            "result": f"{pair['pro_judges']}/{pair['con_judges']}",
            "pro_judges": pair["pro_judges"],
            "con_judges": pair["con_judges"],
            "tie_judges": pair["tie_judges"],
            "parse_errors": pair["parse_errors"],
        }
    return list(by_topic.values())


def _model_ids_for_topic(pair_summaries: list[dict], topic_id: str) -> list[str]:
    model_ids = []
    for pair in pair_summaries:
        if pair["topic_id"] != topic_id:
            continue
        for key in ("pro_model_id", "con_model_id"):
            if pair[key] not in model_ids:
                model_ids.append(pair[key])
    return model_ids


def _motion_summaries(debate_summaries: list[dict]) -> list[dict]:
    by_topic: dict[str, dict] = {}
    for debate in debate_summaries:
        data = by_topic.setdefault(
            debate["topic_id"],
            {"topic_id": debate["topic_id"], "pro_judges": 0, "con_judges": 0, "tie_judges": 0},
        )
        data["pro_judges"] += debate["pro_wins"]
        data["con_judges"] += debate["con_wins"]
        data["tie_judges"] += debate["ties"]

    rows = []
    for data in by_topic.values():
        if data["pro_judges"] > data["con_judges"]:
            result = "carried"
        elif data["con_judges"] > data["pro_judges"]:
            result = "defeated"
        else:
            result = "tied"
        rows.append({**data, "result": result})
    return sorted(rows, key=lambda row: row["topic_id"])


def _elo_ratings(debates: list[DebateTranscript], judgements: list[Judgement]) -> dict[str, float]:
    ratings: dict[str, float] = {}
    debate_by_id = {debate.id: debate for debate in debates}
    for judgement in judgements:
        winner = judgement.parsed.get("winner")
        if winner in {"parse_error", None}:
            continue
        debate = debate_by_id[judgement.debate_id]
        pro_id = debate.pro_model.id
        con_id = debate.con_model.id
        if pro_id == con_id:
            continue
        ratings.setdefault(pro_id, STARTING_ELO)
        ratings.setdefault(con_id, STARTING_ELO)
        score_pro = _pro_score_for_winner(winner)
        expected_pro = _expected_score(ratings[pro_id], ratings[con_id])
        expected_con = 1 - expected_pro
        ratings[pro_id] += ELO_K * (score_pro - expected_pro)
        ratings[con_id] += ELO_K * ((1 - score_pro) - expected_con)
    return {model_id: round(rating, 1) for model_id, rating in ratings.items()}


def _pro_score_for_winner(winner: str) -> float:
    if winner == "pro":
        return 1.0
    if winner == "con":
        return 0.0
    return 0.5


def _expected_score(rating_a: float, rating_b: float) -> float:
    return 1 / (1 + 10 ** ((rating_b - rating_a) / 400))


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
