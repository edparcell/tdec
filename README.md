# TDEC

Top Debate Engine Championship: a small harness for running structured debates
between LLMs and scoring them with independent judge LLMs.

The first version uses LiteLLM directly. The core workflow is:

1. Load debater and judge models from YAML.
2. Run each debater pair both ways round: A pro/B con and B pro/A con,
   including same-model self-debates by default.
3. Run judge models over each complete transcript.
4. Save machine-readable debate, judgement, and summary artifacts.

## Quick Start

```powershell
uv sync
uv run tdec run configs/tournament.yaml
```

Generated runs are written under `runs/<timestamp>/`.

For OpenRouter, put your key in `.env`:

```text
OPENROUTER_API_KEY=sk-or-...
```

Then run the cheap OpenRouter smoke tournament:

```powershell
uv run tdec run configs/openrouter-cheap.yaml
```

Artifacts are compact by default. To preserve full raw LiteLLM/OpenRouter
response metadata for every call:

```powershell
uv run tdec run configs/openrouter-cheap.yaml --artifact-verbosity full
```

## Configuration

`configs/tournament.yaml` contains the default shape:

- `topics`: debate motions.
- `debaters`: model IDs used as competitors.
- `judges`: model IDs used as judges.
- `rounds`: number of turns per side.
- `include_self_debates`: whether to run each model against itself. Defaults to `true`.
- `workers`: concurrent debate and judgement jobs. Defaults to `1`.
- `judging`: retry settings for malformed judge JSON.

Judge retries are conservative by default:

```yaml
judging:
  repair_retries: 1
  parse_retries: 1
```

TDEC first asks the judge to repair invalid JSON. If that fails, it can rerun
the judgement prompt. All attempts are preserved in the judgement artifact with
their timing and cost metrics.

Models use LiteLLM provider/model IDs, for example:

```yaml
provider: ollama
model: tinyllama
api_base: http://localhost:11434
```

You can override worker count from the CLI:

```powershell
uv run tdec run configs/openrouter-cheap.yaml --workers 4
```

Higher worker counts make the tournament faster, but increase concurrent
provider requests and may hit rate limits sooner.

## Outputs

Each run writes:

- `debates/*.json` - transcript and model call metadata.
- `judgements/*.json` - each judge result for each completed debate.
- `errors/*.json` and `errors/errors.jsonl` - skipped provider call failures.
- `summary.json` - aggregate machine-readable summary.
- `summary.md` - compact human-readable summary.

By default, response metadata is compacted to avoid duplicating visible content
and repeated reasoning fields. Blank model outputs keep the full raw metadata
automatically so they can be debugged after the run.
