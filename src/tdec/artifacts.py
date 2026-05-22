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
    lines.append(f"- Total cost: {_format_cost(summary['total_cost_usd'])}")
    lines.append(f"- Total latency: {summary['total_latency_seconds']:.2f}s")
    if summary["cost_errors"]:
        lines.append(f"- Cost errors: {len(summary['cost_errors'])}")
    lines.append("")

    lines.append("## Motions")
    lines.append("")
    lines.append("| Motion | Pro judges | Con judges | Ties | Result |")
    lines.append("| --- | ---: | ---: | ---: | --- |")
    for motion in summary["motions"]:
        lines.append(
            f"| `{motion['topic_id']}` | {motion['pro_judges']} | {motion['con_judges']} | "
            f"{motion['tie_judges']} | {motion['result']} |"
        )
    lines.append("")

    lines.append("## Debater Elo")
    lines.append("")
    lines.append("| Model | Elo |")
    lines.append("| --- | ---: |")
    for model in sorted(
        (m for m in summary["models"] if "debater" in m["roles"]),
        key=lambda row: row["elo"] or 0,
        reverse=True,
    ):
        elo = "n/a" if model["elo"] is None else f"{model['elo']:.1f}"
        lines.append(f"| `{model['model_id']}` | {elo} |")
    lines.append("")

    lines.append("## Model Timings And Costs")
    lines.append("")
    lines.append("| Model | Roles | Calls | Latency | Cost | Prompt | Completion | Total tokens |")
    lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for model in summary["models"]:
        lines.append(
            f"| `{model['model_id']}` | {', '.join(model['roles'])} | {model['calls']} | "
            f"{model['latency_seconds']:.2f}s | {_format_cost(model['cost_usd'])} | "
            f"{model['prompt_tokens']} | {model['completion_tokens']} | {model['total_tokens']} |"
        )
    lines.append("")

    lines.append("## Debate Pair Results")
    lines.append("")
    lines.append("| Debate | Pro model | Con model | Pro judges | Con judges | Ties | Parse errors |")
    lines.append("| --- | --- | --- | ---: | ---: | ---: | ---: |")
    for pair in summary["pairs"]:
        lines.append(
            f"| `{pair['debate_id']}` | `{pair['pro_model_id']}` | `{pair['con_model_id']}` | "
            f"{pair['pro_judges']} | {pair['con_judges']} | {pair['tie_judges']} | "
            f"{pair['parse_errors']} |"
        )
    lines.append("")

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
        lines.append(f"- Debate latency: {debate['debate_latency_seconds']:.2f}s")
        lines.append(f"- Judging latency: {debate['judging_latency_seconds']:.2f}s")
        lines.append(f"- Debate cost: {_format_cost(debate['debate_cost_usd'])}")
        lines.append(f"- Judging cost: {_format_cost(debate['judging_cost_usd'])}")
        if debate["cost_errors"]:
            lines.append("- Cost errors:")
            lines.extend(f"  - {error}" for error in debate["cost_errors"])
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


def _format_cost(value: float | None) -> str:
    if value is None:
        return "unknown"
    return f"${value:.6f}"
