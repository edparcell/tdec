# Run Your First Tournament

This tutorial runs a local smoke tournament using the sample Ollama
configuration. At the end, you will have a run directory containing debate
transcripts, judge decisions, and a summary.

## Before You Start

You need:

- Python 3.11 or newer.
- `uv`.
- Ollama running locally with `tinyllama` available.

If you do not have TinyLlama yet:

```powershell
ollama pull tinyllama
```

## Install The Project

From the TDEC repository root:

```powershell
uv sync
```

This creates the virtual environment and installs the `tdec` command.

## Run The Tournament

Run the included local config:

```powershell
uv run tdec run configs/tournament.yaml
```

When the command finishes, it prints the run directory:

```text
Wrote run to runs/20260521-123456__trump-policy-smoke
```

Your timestamp will be different.

## Open The Summary

Open the Markdown summary in the run directory:

```powershell
Get-Content runs\*\summary.md
```

You should see sections for:

- Motions.
- Debater Elo.
- Model timings and costs.
- Debate pair results.
- Each individual debate.

## Inspect One Debate

List the debate artifacts:

```powershell
Get-ChildItem runs\*\debates
```

Open one JSON file:

```powershell
Get-Content runs\*\debates\*.json | Select-Object -First 40
```

The file contains the motion, public model configuration, turns, text, timing,
token usage, costs when available, finish reason, and compact response metadata.

## What You Did

You ran a full TDEC tournament:

1. Two local TinyLlama debaters argued the configured motion.
2. The same model acted as a judge.
3. TDEC wrote machine-readable artifacts under `runs/`.
4. TDEC wrote a human-readable `summary.md`.

Next, try an OpenRouter tournament with
[Create an OpenRouter tournament](../how-to/create-openrouter-tournament.md).
