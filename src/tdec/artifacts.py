"""Run artifact writing."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from tdec.debate_types import DebateTranscript, Judgement, TournamentError

# ── Loading artifacts from disk ──


def load_debate_transcripts(run_dir: Path) -> list[DebateTranscript]:
    debates_dir = run_dir / "debates"
    results = []
    for f in sorted(debates_dir.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        results.append(DebateTranscript.from_dict(data))
    return results


def load_all_judgements(run_dir: Path) -> list[Judgement]:
    judgements_dir = run_dir / "judgements"
    results = []
    for f in sorted(judgements_dir.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        results.append(Judgement.from_dict(data))
    return results


def existing_judgement_keys(run_dir: Path) -> set[tuple[str, str]]:
    # Read the ids from each file's contents rather than parsing the filename:
    # debate ids and model ids may themselves contain "__", which breaks a
    # filename rsplit and would cause completed judgements to be re-run on resume.
    judgements_dir = run_dir / "judgements"
    keys: set[tuple[str, str]] = set()
    for f in judgements_dir.glob("*.json"):
        data = json.loads(f.read_text(encoding="utf-8"))
        debate_id = data.get("debate_id")
        judge_model_id = data.get("judge_model_id")
        if debate_id is not None and judge_model_id is not None:
            keys.add((debate_id, judge_model_id))
    return keys

ArtifactVerbosity = Literal["compact", "full"]


def unique_run_dir(output_dir: Path, base_name: str) -> Path:
    """Return output_dir/base_name, adding a numeric suffix if it already exists.

    The second-resolution timestamp in run names collides when two runs start in
    the same second; without this they would raise FileExistsError or merge into
    one directory.
    """
    candidate = output_dir / base_name
    suffix = 2
    while candidate.exists():
        candidate = output_dir / f"{base_name}__{suffix}"
        suffix += 1
    return candidate


def make_run_dir(output_dir: Path, run_name: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = unique_run_dir(output_dir, f"{timestamp}__{run_name}")
    (run_dir / "debates").mkdir(parents=True)
    (run_dir / "judgements").mkdir(parents=True)
    (run_dir / "errors").mkdir(parents=True)
    return run_dir


def write_debate(
    run_dir: Path,
    transcript: DebateTranscript,
    *,
    artifact_verbosity: ArtifactVerbosity = "compact",
) -> Path:
    path = run_dir / "debates" / f"{transcript.id}.json"
    write_json(path, _prepare_debate_artifact(transcript.to_dict(), artifact_verbosity))
    return path


def write_judgement(
    run_dir: Path,
    judgement: Judgement,
    *,
    artifact_verbosity: ArtifactVerbosity = "compact",
) -> Path:
    path = run_dir / "judgements" / f"{judgement.debate_id}__{judgement.judge_model_id}.json"
    write_json(path, _prepare_judgement_artifact(judgement.to_dict(), artifact_verbosity))
    return path


def write_error(run_dir: Path, error: TournamentError, index: int) -> Path:
    path = run_dir / "errors" / f"{index:04d}__{error.stage}__{error.debate_id}.json"
    data = error.to_dict()
    write_json(path, data)
    with (run_dir / "errors" / "errors.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False, default=_json_default) + "\n")
    return path


def write_summary(run_dir: Path, summary: dict) -> None:
    write_json(run_dir / "summary.json", summary)
    lines = ["# TDEC Summary", ""]
    lines.append(f"- Total cost: {_format_cost(summary['total_cost_usd'])}")
    lines.append(f"- Total latency: {summary['total_latency_seconds']:.2f}s")
    if summary["cost_errors"]:
        lines.append(f"- Cost errors: {len(summary['cost_errors'])}")
    if summary["errors"]:
        lines.append(f"- Skipped calls: {len(summary['errors'])}")
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
    lines.append("Cells show pro judge wins / con judge wins for the row model as pro.")
    lines.append("")
    for matrix in summary["pair_matrices"]:
        lines.append(f"### {matrix['topic_id']}")
        lines.append("")
        con_ids = matrix["con_model_ids"]
        lines.append("| Pro \\ Con | " + " | ".join(f"`{model_id}`" for model_id in con_ids) + " |")
        lines.append("| --- | " + " | ".join("---:" for _ in con_ids) + " |")
        for pro_id in matrix["pro_model_ids"]:
            cells = matrix["cells"].get(pro_id, {})
            row = [f"`{pro_id}`"]
            for con_id in con_ids:
                row.append(_format_pair_matrix_cell(cells.get(con_id)))
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")

    lines.append("## Detailed Debate Pair Results")
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

    if summary["errors"]:
        lines.append("## Skipped Calls")
        lines.append("")
        lines.append("| Stage | Debate | Model | Error |")
        lines.append("| --- | --- | --- | --- |")
        for error in summary["errors"]:
            lines.append(
                f"| {error['stage']} | `{error['debate_id']}` | `{error['model_id']}` | "
                f"{error['error_type']}: {_escape_table_text(error['error_message'])} |"
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


def _prepare_debate_artifact(data: dict[str, Any], verbosity: ArtifactVerbosity) -> dict[str, Any]:
    if verbosity == "full":
        return data
    compact = deepcopy(data)
    for turn in compact.get("turns", []):
        if isinstance(turn, dict) and _has_visible_text(turn.get("content")):
            _compact_metrics(turn.get("metrics"))
    return compact


def _prepare_judgement_artifact(data: dict[str, Any], verbosity: ArtifactVerbosity) -> dict[str, Any]:
    if verbosity == "full":
        return data
    compact = deepcopy(data)
    if _has_visible_text(compact.get("raw_text")):
        _compact_metrics(compact.get("metrics"))
    for attempt in compact.get("attempts") or []:
        if isinstance(attempt, dict) and _has_visible_text(attempt.get("raw_text")):
            _compact_metrics(attempt.get("metrics"))
    return compact


def _has_visible_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _compact_metrics(metrics: object) -> None:
    if not isinstance(metrics, dict):
        return
    metadata = metrics.get("response_metadata")
    if isinstance(metadata, dict):
        metrics["response_metadata"] = _compact_response_metadata(metadata)


def _compact_response_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key in (
        "id",
        "created",
        "model",
        "object",
        "system_fingerprint",
        "usage",
        "provider",
        "service_tier",
    ):
        if key in metadata:
            compact[key] = metadata[key]

    choices = metadata.get("choices")
    if isinstance(choices, list):
        compact["choices"] = [_compact_choice(choice) for choice in choices]
    return compact


def _compact_choice(choice: object) -> object:
    if not isinstance(choice, dict):
        return choice

    compact: dict[str, Any] = {}
    for key in ("finish_reason", "index"):
        if key in choice:
            compact[key] = choice[key]

    provider_fields = choice.get("provider_specific_fields")
    if isinstance(provider_fields, dict):
        kept_provider_fields = {
            key: provider_fields[key]
            for key in ("native_finish_reason",)
            if key in provider_fields
        }
        if kept_provider_fields:
            compact["provider_specific_fields"] = kept_provider_fields

    message = choice.get("message")
    if isinstance(message, dict):
        compact["message"] = _compact_message(message)
    return compact


def _compact_message(message: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    if "role" in message:
        compact["role"] = message["role"]
    if message.get("refusal") is not None:
        compact["refusal"] = message["refusal"]

    provider_fields = message.get("provider_specific_fields")
    if isinstance(provider_fields, dict) and provider_fields.get("refusal") is not None:
        compact["refusal"] = provider_fields["refusal"]

    reasoning = _first_reasoning_text(message, provider_fields)
    if reasoning:
        compact["reasoning_content"] = reasoning
    return compact


def _first_reasoning_text(
    message: dict[str, Any],
    provider_fields: object,
) -> str | None:
    for value in (
        message.get("reasoning_content"),
        provider_fields.get("reasoning_content") if isinstance(provider_fields, dict) else None,
        provider_fields.get("reasoning") if isinstance(provider_fields, dict) else None,
    ):
        if isinstance(value, str) and value.strip():
            return value

    if isinstance(provider_fields, dict):
        details = provider_fields.get("reasoning_details")
        if isinstance(details, list):
            for detail in details:
                if not isinstance(detail, dict):
                    continue
                for key in ("summary", "text"):
                    value = detail.get(key)
                    if isinstance(value, str) and value.strip():
                        return value
    return None


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


def _format_pair_matrix_cell(cell: object) -> str:
    if not isinstance(cell, dict):
        return "-"
    extras = []
    if cell["tie_judges"]:
        extras.append(f"T{cell['tie_judges']}")
    if cell["parse_errors"]:
        extras.append(f"E{cell['parse_errors']}")
    result = cell["result"]
    if extras:
        return f"{result} ({' '.join(extras)})"
    return result


def _escape_table_text(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
