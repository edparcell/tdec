# CLI Reference

## `tdec run`

Run a tournament from a run config.

```powershell
tdec run CONFIG_PATH [OPTIONS]
```

| Argument | Description |
|----------|-------------|
| `CONFIG_PATH` | Path to a run YAML file (e.g. `configs/runs/single-payer.yaml`). |

| Option | Description |
|--------|-------------|
| `--output-dir PATH` | Override `run.output_dir` from the config. |
| `--artifact-verbosity compact\|full` | Compact (default) or full response metadata. |
| `--workers N` | Override `run.workers`. |
| `--no-reuse-openings` | Disable pro opening reuse across debates. |
| `--resume DIR` | Resume a previous run, filling in missing debates and judgements. |

```powershell
tdec run configs/runs/twenty-motions.yaml --workers 10
tdec run configs/runs/single-payer.yaml --resume runs/20260522-123456__single-payer
```

## `tdec view`

View one or more tournament runs in the browser.

```powershell
tdec view RUN_DIR [RUN_DIR2 ...] [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--port N` | Port to serve on (default: auto). |
| `--open` | Auto-open the browser. |

```powershell
tdec view runs/20260522-233636__twenty-motions
tdec view runs/*bias-ubi*
```

Multiple directories enables the Comparison tab with cross-run ANOVA.

## `tdec export`

Export a standalone HTML viewer for sharing.

```powershell
tdec export RUN_DIR [-o OUTPUT_PATH]
```

Generates a self-contained HTML file with all data embedded.

## `tdec judge`

Add judges to an existing run without re-debating.

```powershell
tdec judge RUN_DIR JUDGE_CONFIG_PATH [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--workers N` | Concurrent judging jobs (default: 1). |
| `--artifact-verbosity compact\|full` | Metadata verbosity. |
| `--prompt-set PATH` | Prompt-set YAML (default: `configs/prompt-sets/default.yaml`). |

Skips judge/debate combinations that already have judgement files.

## `tdec relabel`

Create a label-swapped copy of a run and rejudge it for bias testing.

```powershell
tdec relabel SOURCE_DIR JUDGE_CONFIG_PATH [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--output-dir PATH` | Output directory (default: `runs/`). |
| `--workers N` | Concurrent judging jobs (default: 1). |
| `--prompt-set PATH` | Prompt-set YAML. |

Swaps A/B labels in transcripts so the judge sees the same debate with
reversed anonymization. Compares verdicts to detect judge label bias.

## Environment Loading

Before loading configs, TDEC reads `.env` files:

1. Relative to the config file location.
2. `.env` in the current working directory.
