# How to Add Judges After a Run

You can add new judges to an existing run without re-debating.

## Create a Judge Config

Reference judges from `configs/judges/`:

```yaml
# configs/my-extra-judges.yaml
judges:
  - claude-haiku-4-5
  - grok-4-3

judging:
  repair_retries: 1
  parse_retries: 1
  api_retries: 2
```

## Run the Judging

```powershell
tdec judge runs/<run-dir> configs/my-extra-judges.yaml --workers 10
```

This skips judge/debate combinations that already have judgement
files and regenerates the summary with all judgements (old + new).

## Specify a Prompt-Set

By default, `tdec judge` uses `configs/prompt-sets/default.yaml`.
To use a different prompt-set:

```powershell
tdec judge runs/<run-dir> configs/my-extra-judges.yaml --prompt-set configs/prompt-sets/natural.yaml
```
