"""Command-line interface."""

from __future__ import annotations

from pathlib import Path

import click

from tdec.config import load_tournament_config
from tdec.env import load_env_file
from tdec.models import LiteLLMClient
from tdec.tournament import run_tournament


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
def run(config_path: Path, output_dir: Path | None, artifact_verbosity: str) -> None:
    """Run a debate tournament from a YAML config."""
    load_env_file(config_path.parent.parent / ".env")
    load_env_file(".env")
    config = load_tournament_config(config_path)
    result = run_tournament(
        config=config,
        client=LiteLLMClient(),
        output_dir=output_dir,
        artifact_verbosity=artifact_verbosity,
    )
    click.echo(f"Wrote run to {result['run_dir']}")


if __name__ == "__main__":
    main()
