"""Command-line interface."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import click

from tdec.config import load_judge_config, load_prompt_set_config, load_run_config
from tdec.env import load_env_file
from tdec.models import LiteLLMClient
from tdec.prompts import PromptSet
from tdec.tournament import run_posthoc_judges, run_tournament
from tdec.viewer import export_html, serve as serve_viewer


@click.group()
def main() -> None:
    """Top Debate Engine Championship."""


@main.command()
@click.argument("config_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Override output directory from config.",
)
@click.option(
    "--artifact-verbosity",
    type=click.Choice(["compact", "full"]),
    default="compact",
    show_default=True,
    help="Use compact artifacts by default, or full raw model response metadata.",
)
@click.option(
    "--workers",
    type=click.IntRange(min=1),
    default=None,
    help="Override run.workers for concurrent debate and judgement jobs.",
)
@click.option(
    "--no-reuse-openings",
    is_flag=True,
    default=False,
    help="Disable pro opening reuse across debates.",
)
@click.option(
    "--resume",
    "resume_dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="Resume a previous run, filling in missing debates and judgements.",
)
def run(
    config_path: Path,
    output_dir: Path | None,
    artifact_verbosity: str,
    workers: int | None,
    no_reuse_openings: bool,
    resume_dir: Path | None,
) -> None:
    """Run a debate tournament from a YAML config."""
    load_env_file(config_path.parent.parent.parent / ".env")
    load_env_file(".env")
    config = load_run_config(config_path)
    if no_reuse_openings:
        config = replace(config, run=replace(config.run, reuse_openings=False))
    result = run_tournament(
        config=config,
        client=LiteLLMClient(),
        output_dir=output_dir,
        artifact_verbosity=artifact_verbosity,
        workers=workers,
        resume_dir=resume_dir,
    )
    click.echo(f"Wrote run to {result['run_dir']}")


@main.command()
@click.argument("run_dirs", nargs=-1, type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--port", type=int, default=None, help="Port to serve on (default: auto).")
@click.option("--open", "open_browser", is_flag=True, default=False, help="Auto-open the browser.")
def view(run_dirs: tuple[Path, ...], port: int | None, open_browser: bool) -> None:
    """View one or more tournament runs in the browser."""
    if not run_dirs:
        raise click.ClickException("At least one run directory is required.")
    for rd in run_dirs:
        if not (rd / "summary.json").exists():
            raise click.ClickException(f"No summary.json found in {rd}")
    dirs = list(run_dirs)
    serve_viewer(dirs if len(dirs) > 1 else dirs[0], port=port, open_browser=open_browser)


@main.command()
@click.argument("run_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.argument("judge_config_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--workers",
    type=click.IntRange(min=1),
    default=1,
    show_default=True,
    help="Concurrent judging jobs.",
)
@click.option(
    "--artifact-verbosity",
    type=click.Choice(["compact", "full"]),
    default="compact",
    show_default=True,
)
@click.option(
    "--prompt-set",
    "prompt_set_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Prompt-set YAML for judge prompts (default: configs/prompt-sets/default.yaml).",
)
def judge(
    run_dir: Path,
    judge_config_path: Path,
    workers: int,
    artifact_verbosity: str,
    prompt_set_path: Path | None,
) -> None:
    """Add judges to an existing tournament run."""
    if not (run_dir / "summary.json").exists():
        raise click.ClickException(f"No summary.json found in {run_dir}")
    load_env_file(judge_config_path.parent / ".env")
    load_env_file(".env")
    if prompt_set_path is None:
        prompt_set_path = Path("configs/prompt-sets/default.yaml")
    if not prompt_set_path.exists():
        raise click.ClickException(f"Prompt-set not found: {prompt_set_path}")
    config = load_judge_config(judge_config_path)
    ps = PromptSet(load_prompt_set_config(prompt_set_path))
    result = run_posthoc_judges(
        run_dir=run_dir,
        judge_config=config,
        client=LiteLLMClient(),
        artifact_verbosity=artifact_verbosity,
        workers=workers,
        prompt_set=ps,
    )
    click.echo(f"Updated summary at {result['run_dir']}")


@main.command()
@click.argument("source_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.argument("judge_config_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Output directory for relabeled run (default: runs/).",
)
@click.option("--workers", type=click.IntRange(min=1), default=1, show_default=True)
@click.option(
    "--prompt-set",
    "prompt_set_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Prompt-set YAML (default: configs/prompt-sets/default.yaml).",
)
def relabel(
    source_dir: Path,
    judge_config_path: Path,
    output_dir: Path | None,
    workers: int,
    prompt_set_path: Path | None,
) -> None:
    """Create a label-swapped copy of a run and rejudge it."""
    from tdec.tournament import run_relabel

    load_env_file(judge_config_path.parent / ".env")
    load_env_file(".env")
    if prompt_set_path is None:
        prompt_set_path = Path("configs/prompt-sets/default.yaml")
    if not prompt_set_path.exists():
        raise click.ClickException(f"Prompt-set not found: {prompt_set_path}")
    judge_cfg = load_judge_config(judge_config_path)
    ps = PromptSet(load_prompt_set_config(prompt_set_path))
    result = run_relabel(
        source_dir=source_dir,
        judge_config=judge_cfg,
        client=LiteLLMClient(),
        prompt_set=ps,
        output_dir=output_dir or Path("runs"),
        workers=workers,
    )
    click.echo(f"Wrote relabeled run to {result['run_dir']}")


@main.command("export")
@click.argument("run_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    "-o",
    "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Output HTML file path (default: <run_dir>/report.html).",
)
def export_cmd(run_dir: Path, output: Path | None) -> None:
    """Export a standalone HTML viewer for a tournament run."""
    summary_path = run_dir / "summary.json"
    if not summary_path.exists():
        raise click.ClickException(f"No summary.json found in {run_dir}")
    if output is None:
        output = run_dir / "report.html"
    export_html(run_dir, output)
    click.echo(f"Wrote {output} ({output.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
