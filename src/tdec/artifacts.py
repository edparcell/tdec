"""Run artifact writing."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from tdec.debate_types import DebateTranscript, Judgement


def make_run_dir(output_dir: Path, run_name: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = output_dir / f"{timestamp}__{run_name}"
    (run_dir / "debates").mkdir(parents=True)
    (run_dir / "judgements").mkdir(parents=True)
    return run_dir


def write_debate(run_dir: Path, transcript: DebateTranscript) -> Path:
    path = run_dir / "debates" / f"{transcript.id}.json"
    write_json(path, transcript.to_dict())
    return path


def write_judgement(run_dir: Path, judgement: Judgement) -> Path:
    path = run_dir / "judgements" / f"{judgement.debate_id}__{judgement.judge_model_id}.json"
    write_json(path, judgement.to_dict())
    return path


def write_summary(run_dir: Path, summary: dict) -> None:
    write_json(run_dir / "summary.json", summary)
    lines = ["# TDEC Summary", ""]
    for debate in summary["debates"]:
        lines.append(f"## {debate['debate_id']}")
        lines.append("")
        lines.append(f"- Pro: `{debate['pro_model_id']}`")
        lines.append(f"- Con: `{debate['con_model_id']}`")
        lines.append(f"- Judgements: {debate['judgement_count']}")
        lines.append(f"- Pro wins: {debate['pro_wins']}")
        lines.append(f"- Con wins: {debate['con_wins']}")
        lines.append(f"- Ties: {debate['ties']}")
        lines.append(f"- Parse errors: {debate['parse_errors']}")
        lines.append("")
    (run_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def write_json(path: Path, data: object) -> None:
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, default=_json_default),
        encoding="utf-8",
    )


def _json_default(value: object) -> object:
    if isinstance(value, Path):
        return str(value)
    try:
        return asdict(value)
    except TypeError:
        return str(value)
