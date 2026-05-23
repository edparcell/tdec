# TDEC

Top Debate Engine Championship: run structured debates between LLMs and score
them with independent judge LLMs.

TDEC is useful when you want to compare models as debaters, test how a motion
survives adversarial argument, study judge/model bias, or run controlled
experiments on debate format and strategy.

## Quick Start

```powershell
uv sync
```

Create `.env` with your API key:

```text
OPENROUTER_API_KEY=sk-or-...
```

Run a tournament:

```powershell
tdec run configs/runs/single-payer.yaml
```

View the results:

```powershell
tdec view runs/<timestamp>__single-payer-openrouter
```

## Config Structure

Configs are split across four directories under `configs/`:

```
configs/
  debaters/       # one YAML per debater (model + optional strategy)
  judges/         # one YAML per judge (model + optional style)
  prompt-sets/    # debate and judge prompt templates
  runs/           # run configs referencing the above
```

A run config references debaters and judges by filename and specifies
topics inline:

```yaml
prompt_set: natural
debaters:
  - deepseek-v4-flash
  - mistral-small-4
judges:
  - kimi-k2-5
  - gpt-5-mini
topics:
  - id: ubi
    motion: >-
      Wealthy democracies should replace most welfare programs with a
      universal basic income.
run:
  name: ubi-debate
  rounds: 3
  workers: 10
  debate_mode: parallel
```

## Commands

| Command | Description |
|---------|-------------|
| `tdec run <config>` | Run a tournament. `--resume <dir>` fills gaps from a previous run. |
| `tdec view <dir> [dir2 ...]` | View results in the browser. Multiple dirs for comparison. |
| `tdec export <dir>` | Export a standalone HTML report. |
| `tdec judge <dir> <judge-config>` | Add judges to an existing run. |
| `tdec relabel <dir> <judge-config>` | Create a label-swapped copy and rejudge for bias testing. |

## Debate Modes

| Mode | Description |
|------|-------------|
| `pro_first` | Sequential: pro speaks first each round (default). |
| `con_first` | Sequential: con speaks first each round. |
| `parallel` | Both sides compose simultaneously each round. |

## Viewer

The viewer has five tabs:

- **Motions** - per-motion results with per-judge breakdowns (default for multi-topic runs)
- **Debates** - cross-table matrix with drill-down to judge verdicts and transcripts
- **Judges** - judge voting patterns, win rates by debater, inter-judge agreement
- **Analysis** - statistical tests: side bias, model strength with confidence intervals, rubric profiles, ANOVA
- **Comparison** - cross-run ANOVA when viewing multiple runs with different experimental conditions

## Documentation

- [Tutorials](docs/tutorials/first-tournament.md) - start here.
- [How-to guides](docs/how-to/) - solve specific tasks.
- [Reference](docs/reference/) - commands, configuration, and artifact formats.
- [Explanation](docs/explanation/) - design rationale and scoring.

For LLM coding agents, start with [llms.txt](llms.txt).

## Development

```powershell
uv run pytest
uv run ruff check .
```
