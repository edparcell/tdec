# TDEC

Top Debate Engine Championship: run structured debates between LLMs and score
them with independent judge LLMs.

TDEC is useful when you want to compare models as debaters, test how a motion
survives adversarial argument, or study judge/model bias across repeated
pairings.

## Quick Start

```powershell
uv sync
uv run tdec run configs/tournament.yaml
```

Generated runs are written under `runs/<timestamp>__<run-name>/`.

For OpenRouter, create `.env`:

```text
OPENROUTER_API_KEY=sk-or-...
```

Then run a small OpenRouter tournament:

```powershell
uv run tdec run configs/openrouter-cheap.yaml
```

## How It Works

1. Load debater and judge models from YAML.
2. Run each debater pair both ways round: A pro/B con and B pro/A con,
   including same-model self-debates by default.
3. Run judge models over each complete transcript.
4. Save machine-readable debate, judgement, and summary artifacts.

## Documentation

The docs follow the Divio documentation system:

- [Tutorials](docs/tutorials/first-tournament.md) - start here if you want to run TDEC once.
- [How-to guides](docs/how-to/) - solve specific tasks.
- [Reference](docs/reference/) - look up commands, configuration, and artifact formats.
- [Explanation](docs/explanation/) - understand tournament design and scoring.

For LLM coding agents, start with [llms.txt](llms.txt).

## Common Commands

Run with more parallelism:

```powershell
uv run tdec run configs/single-payer-openrouter.yaml --workers 10
```

Keep full raw provider metadata in every artifact:

```powershell
uv run tdec run configs/openrouter-cheap.yaml --artifact-verbosity full
```

Run checks:

```powershell
uv run pytest
uv run ruff check .
```
