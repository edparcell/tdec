"""Command-line interface."""

from __future__ import annotations

from pathlib import Path

import click

from tdec.config import load_tournament_config
from tdec.env import load_env_file
from tdec.models import LiteLLMClient
from tdec.tournament import run_tournament
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
def run(
    config_path: Path,
    output_dir: Path | None,
    artifact_verbosity: str,
    workers: int | None,
) -> None:
    """Run a debate tournament from a YAML config."""
    load_env_file(config_path.parent.parent / ".env")
    load_env_file(".env")
    config = load_tournament_config(config_path)
    result = run_tournament(
        config=config,
        client=LiteLLMClient(),
        output_dir=output_dir,
        artifact_verbosity=artifact_verbosity,
        workers=workers,
    )
    click.echo(f"Wrote run to {result['run_dir']}")


@main.command()
@click.argument("run_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--port", type=int, default=None, help="Port to serve on (default: auto).")
def view(run_dir: Path, port: int | None) -> None:
    """View a tournament run in the browser."""
    summary_path = run_dir / "summary.json"
    if not summary_path.exists():
        raise click.ClickException(f"No summary.json found in {run_dir}")
    serve_viewer(run_dir, port=port)


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
