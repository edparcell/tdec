# Debug Blank Outputs And Provider Failures

Use this guide when a model returns blank content, invalid JSON, or a provider
error.

## Find Skipped Calls

Open the run summary:

```powershell
Get-Content runs\<run-dir>\summary.md
```

If calls were skipped, the summary contains a "Skipped Calls" section.

## Inspect Error Artifacts

Provider call failures are written under `errors/`:

```powershell
Get-ChildItem runs\<run-dir>\errors
Get-Content runs\<run-dir>\errors\errors.jsonl
```

Each error includes:

- `stage`: `debate` or `judgement`.
- `debate_id`.
- `model_id`.
- `error_type`.
- `error_message`.
- `traceback`.

Obvious API key and token patterns are redacted.

## Inspect Blank Model Outputs

Blank model outputs keep full raw response metadata even when artifact verbosity
is compact.

Open the debate artifact:

```powershell
Get-Content runs\<run-dir>\debates\<debate-id>.json
```

Look at:

- `turns[].content`
- `turns[].metrics.finish_reason`
- `turns[].metrics.usage`
- `turns[].metrics.response_metadata`

Useful provider-specific data is often under `choices`, `message`,
`provider_specific_fields`, or hidden LiteLLM fields.

## Preserve Full Metadata For Every Call

Run with full artifact verbosity:

```powershell
uv run tdec run configs/my-run.yaml --artifact-verbosity full
```

This makes artifacts larger, but it preserves the full serializable model
response for every successful call.

## Reduce Failures

Try these changes one at a time:

1. Lower `run.workers` or use `--workers 1`.
2. Increase `max_tokens` for judges that return truncated JSON.
3. Use `temperature: null` for models that reject temperature.
4. Replace flaky models or providers.
5. Keep `judging.repair_retries` and `judging.parse_retries` at least `1`.
