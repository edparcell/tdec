# CLI Reference

The command-line entry point is:

```powershell
uv run tdec
```

## `tdec run`

Run a tournament from a YAML config.

```powershell
uv run tdec run CONFIG_PATH [OPTIONS]
```

Arguments:

| Argument | Description |
| --- | --- |
| `CONFIG_PATH` | Path to a tournament YAML file. Must exist. |

Options:

| Option | Values | Description |
| --- | --- | --- |
| `--output-dir PATH` | Directory path | Override `run.output_dir` from the config. |
| `--artifact-verbosity compact` | `compact` | Default. Write smaller artifacts with compact response metadata. |
| `--artifact-verbosity full` | `full` | Preserve full serializable response metadata for every call. |
| `--workers N` | Integer >= 1 | Override `run.workers`. |

Examples:

```powershell
uv run tdec run configs/tournament.yaml
uv run tdec run configs/openrouter-cheap.yaml --workers 4
uv run tdec run configs/openrouter-cheap.yaml --artifact-verbosity full
uv run tdec run configs/openrouter-cheap.yaml --output-dir scratch-runs
```

## Environment Loading

Before loading the config, TDEC reads:

1. `.env` in the parent of the config directory.
2. `.env` in the current working directory.

For configs under `configs/`, this normally means the repository root `.env`.
