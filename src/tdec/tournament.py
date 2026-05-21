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
        })
    return {
        "run_dir": str(run_dir),
        "debates": debate_summaries,
    }


def _count_winners(judgements: list[Judgement], winner: str) -> int:
    return sum(1 for judgement in judgements if judgement.parsed.get("winner") == winner)

