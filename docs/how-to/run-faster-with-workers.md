# Run Tournaments Faster With Workers

Use workers to run independent debates and judgements concurrently.

## Set Workers In YAML

Add `workers` under `run`:

```yaml
run:
  name: my-run
  rounds: 3
  output_dir: runs
  workers: 4
```

## Override Workers At The CLI

The CLI option overrides the YAML value:

```powershell
uv run tdec run configs/my-run.yaml --workers 10
```

## Pick A Worker Count

Start with `2` or `4` for hosted providers.

Use a higher number only when:

- The provider allows enough concurrent requests.
- You are comfortable with costs accumulating faster.
- You are not running local models that will saturate your machine.

## What Runs In Parallel

TDEC parallelizes at job boundaries:

- Complete debate jobs run in parallel.
- After debates finish, judge jobs run in parallel.
- Turns inside a single debate stay sequential so each side can respond to the
  previous turn.

## Handling Rate Limits

If a provider returns a service error, TDEC skips the failed debate or judgement
and writes an error artifact. The tournament continues. Lower `workers` and
rerun if many calls are skipped.
