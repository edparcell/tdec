# Artifact Reference

Each run creates:

```text
runs/<timestamp>__<run-name>/
  debates/
  judgements/
  errors/
  summary.json
  summary.md
```

## Debate Artifacts

Path:

```text
debates/<topic-id>__<pro-model-id>_pro__<con-model-id>_con.json
```

Top-level fields:

| Field | Description |
| --- | --- |
| `id` | Debate identifier. |
| `topic` | Topic config used for the debate. |
| `pro_model` | Public model config for the pro side, with API key redacted. |
| `con_model` | Public model config for the con side, with API key redacted. |
| `rounds` | Number of turns per side. |
| `turns` | Ordered debate turns. |

Turn fields:

| Field | Description |
| --- | --- |
| `speaker_label` | `A` or `B`. |
| `speaker_model_id` | Model config `id`. |
| `side` | `pro` or `con`. |
| `turn_number` | Round number. |
| `content` | Visible model output. |
| `metrics` | Timing, usage, cost, finish reason, and response metadata. |

## Judgement Artifacts

Path:

```text
judgements/<debate-id>__<judge-model-id>.json
```

Fields:

| Field | Description |
| --- | --- |
| `debate_id` | Debate being judged. |
| `judge_model_id` | Judge model config `id`. |
| `raw_text` | Final judge response text. |
| `parsed` | Parsed judgement JSON, or a parse-error record. |
| `metrics` | Metrics for the final selected judge attempt. |
| `attempts` | Initial, repair, and retry attempts. |

The judge prompt asks for:

- `winner`: `pro`, `con`, or `tie`.
- `winner_label`: `A`, `B`, or `tie`.
- `confidence`.
- `pro_score` and `con_score`.
- Rubric category scores.
- Decisive reasons.
- Audience estimate.
- Summary.

## Error Artifacts

Provider call failures are written under `errors/`.

Individual error path:

```text
errors/0001__<stage>__<debate-id>.json
```

Append-only JSONL path:

```text
errors/errors.jsonl
```

Fields:

| Field | Description |
| --- | --- |
| `stage` | `debate` or `judgement`. |
| `topic_id` | Topic being processed. |
| `debate_id` | Debate identifier. |
| `pro_model_id` | Pro model id. |
| `con_model_id` | Con model id. |
| `judge_model_id` | Judge id for judgement failures, otherwise null. |
| `model_id` | Model whose call failed. |
| `error_type` | Exception type. |
| `error_message` | Redacted message. |
| `traceback` | Redacted traceback. |

## Summary Artifacts

`summary.json` is the machine-readable aggregate.

`summary.md` is the human-readable report with:

- Total cost and latency.
- Motion result table.
- Debater Elo table.
- Per-model timing, cost, and token table.
- Pair result table.
- Skipped call table when errors occurred.
- Per-debate details.

## Metrics

Model call metrics include:

| Field | Description |
| --- | --- |
| `model_id` | TDEC model id. |
| `provider` | LiteLLM provider. |
| `model` | Provider model name. |
| `latency_seconds` | Wall-clock call latency. |
| `usage` | Prompt, completion, and total tokens when available. |
| `cost_usd` | Cost when known. |
| `cost_error` | Cost extraction error when cost is unknown. |
| `finish_reason` | Provider finish reason when available. |
| `response_metadata` | Compact or full serializable response metadata. |
