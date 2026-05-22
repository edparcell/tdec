# Judging, Scoring, And Failures

TDEC is designed to keep going when individual model calls fail. Long
tournaments involve many provider calls, and hosted models sometimes return
service errors, malformed JSON, truncated output, or blank visible content.

## Judging

Each completed debate is sent to every configured judge. Judges see the
transcript with debaters identified as `A` and `B`, plus each side's `pro` or
`con` role.

The judge is asked to return compact JSON. TDEC parses that JSON and records the
raw text, parsed object, metrics, and all attempts.

If parsing fails:

1. TDEC asks the same judge to repair the bad JSON.
2. If repair attempts fail, TDEC can rerun the original judgement prompt.
3. If all attempts fail, TDEC records a judgement with `winner: parse_error`.

The retry counts come from `judging.repair_retries` and
`judging.parse_retries`.

## Motion Results

For each motion, TDEC counts judge decisions:

- Pro wins.
- Con wins.
- Ties.

If pro wins exceed con wins, the motion is `carried`. If con wins exceed pro
wins, the motion is `defeated`. Otherwise it is `tied`.

## Pair Results

Pair summaries report how judges scored each ordered debate:

```text
topic__model_a_pro__model_b_con
```

The same two models can appear twice with sides reversed. This helps separate
model strength from side advantage.

## Elo

TDEC computes a simple Elo table for debaters:

- Starting rating: `1500`.
- K factor: `32`.
- Each judge vote is treated as one game.
- Pro win scores `1.0`.
- Con win scores `0.0` for pro and `1.0` for con.
- Tie scores `0.5`.
- Parse errors are skipped.
- Self-debates are skipped.

Elo is a quick comparative signal, not a complete statistical model. It is most
useful when there are enough cross-model debates and multiple judges.

## Costs

TDEC records cost when LiteLLM or provider metadata exposes it. If cost
extraction fails, the call still records timing and token usage, and the summary
marks cost as unknown with a cost error.

Missing API keys are different: TDEC refuses to start if a config names an
`api_key_env` that is not set. This prevents anonymous or accidental calls.

## Provider Failures

If a model call raises a provider error:

- A failed debate writes no debate or judgement artifact.
- A failed judgement writes no judgement artifact.
- The tournament continues with other jobs.
- The failure is written under `errors/`.
- The summary reports skipped calls.

Error messages and tracebacks are redacted for obvious API key and token
patterns.

## Blank Outputs

Blank visible model output is not treated as a provider exception. The call
succeeded, but the content is empty. TDEC keeps full raw response metadata for
blank outputs even when artifacts are otherwise compact, because the answer is
often hidden in provider-specific fields such as finish reasons, reasoning
metadata, or nonstandard message fields.
