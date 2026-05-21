# TDEC

Top Debate Engine Championship: a small harness for running structured debates
between LLMs and scoring them with independent judge LLMs.

The first version uses LiteLLM directly. The core workflow is:

1. Load debater and judge models from YAML.
2. Run each debater pair both ways round: A pro/B con and B pro/A con.
3. Run judge models over each complete transcript.
4. Save machine-readable debate, judgement, and summary artifacts.

## Quick Start

```powershell
uv sync
uv run tdec run configs/tournament.yaml
```

Generated runs are written under `runs/<timestamp>/`.

## Configuration

`configs/tournament.yaml` contains the default shape:

- `topics`: debate motions.
- `debaters`: model IDs used as competitors.
- `judges`: model IDs used as judges.
- `rounds`: number of turns per side.

Models use LiteLLM provider/model IDs, for example:

```yaml
provider: ollama
model: tinyllama
api_base: http://localhost:11434
```

## Outputs

Each run writes:

- `debates/*.json` - full transcript and metadata.
- `judgements/*.json` - each judge result for each debate.
- `summary.json` - aggregate machine-readable summary.
- `summary.md` - compact human-readable summary.

