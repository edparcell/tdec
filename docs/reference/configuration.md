# Configuration Reference

Configs are split across four directories under `configs/`:

```
configs/
  debaters/       # one YAML per debater
  judges/         # one YAML per judge
  prompt-sets/    # prompt templates
  runs/           # run configs referencing the above
```

## Debater Config

Each debater is a separate YAML file in `configs/debaters/`.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes | Stable identifier used in summaries and filenames. |
| `provider` | string | Yes | LiteLLM provider (e.g. `openrouter`, `ollama`). |
| `model` | string | Yes | Provider model name. |
| `api_base` | string | No | Custom API base URL. |
| `api_key` | string | No | Inline API key. |
| `api_key_env` | string | No | Environment variable containing the API key. |
| `temperature` | number or null | No | Sampling temperature. `null` omits the parameter. Default `0.2`. |
| `max_tokens` | integer | No | Completion token cap. Default `4096`. |
| `strategy` | string | Yes | Debating strategy/style. May be empty. |

```yaml
# configs/debaters/deepseek-v4-flash.yaml
id: deepseek_v4_flash
provider: openrouter
model: deepseek/deepseek-v4-flash
api_key_env: OPENROUTER_API_KEY
temperature: 0.7
max_tokens: 10000
strategy: ""
```

## Judge Config

Each judge is a separate YAML file in `configs/judges/`.

Same fields as debater, but `style` instead of `strategy`:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `style` | string | Yes | Judging approach/style. May be empty. |

```yaml
# configs/judges/kimi-k2-5.yaml
id: kimi_k2_5
provider: openrouter
model: moonshotai/kimi-k2.5
api_key_env: OPENROUTER_API_KEY
temperature: 0.2
max_tokens: 10000
style: ""
```

## Prompt-Set Config

Prompt templates in `configs/prompt-sets/`. Uses `$placeholder` syntax
(`string.Template`) to avoid conflicts with JSON braces in judge prompts.

| Field | Description |
|-------|-------------|
| `id` | Identifier for this prompt set. |
| `debater_system` | System prompt for debaters. `$strategy_block` is injected. |
| `opening` | First-speaker opening prompt. `$motion`, `$context_block`, `$side`, `$rounds`. |
| `response` | Subsequent turn prompt. Adds `$turn_name`. |
| `parallel_opening` | Opening prompt for simultaneous-round debates. |
| `parallel_response` | Response prompt for simultaneous-round debates. |
| `judge_system` | Judge system prompt for sequential debates. `$style_block` is injected. |
| `parallel_judge_system` | Judge system prompt for parallel debates. Explains simultaneous structure. |
| `judge` | Judge evaluation prompt. `$motion`, `$transcript`. |
| `judge_repair` | Prompt for repairing malformed judge JSON. `$error`, `$bad_output`. |

Two prompt sets are included: `default` (structured) and `natural` (flowing
prose, anti-AI-speak rules, no bullets).

## Run Config

Run configs in `configs/runs/` reference debaters, judges, and prompt-set
by filename (without `.yaml`). Topics are inline.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `prompt_set` | string | Required | Prompt-set filename in `configs/prompt-sets/`. |
| `debaters` | list of strings | Required | Debater filenames in `configs/debaters/`. |
| `judges` | list of strings | Required | Judge filenames in `configs/judges/`. |
| `topics` | list | Required | Inline topic definitions. |

### `topics` fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Stable identifier. |
| `motion` | string | The resolution being debated. |
| `context` | string | Optional background context both sides see. |

### `run` fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | string | Config filename | Run name for output directory. |
| `rounds` | integer | `3` | Turns per side. |
| `output_dir` | path | `runs` | Base output directory. |
| `include_self_debates` | boolean | `true` | Include same-model debates. |
| `workers` | integer | `1` | Concurrent jobs. |
| `reuse_openings` | boolean | `true` | Cache opening statements across opponents. |
| `debate_mode` | string | `pro_first` | `pro_first`, `con_first`, or `parallel`. |
| `debate_api_retries` | integer | `2` | Retries for failed debate API calls. |
| `conditions` | dict | `{}` | Experimental metadata for cross-run comparison. |

### `judging` fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `repair_retries` | integer | `1` | Attempts to repair malformed judge JSON. |
| `parse_retries` | integer | `1` | Fresh retries after repair fails. |
| `api_retries` | integer | `2` | Retries for failed judge API calls. |

### Example

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
    context: >-
      Consider cost, labor markets, and political feasibility.

run:
  name: ubi-debate
  rounds: 3
  output_dir: runs
  workers: 10
  debate_mode: parallel
  conditions:
    debate_mode: parallel
    motion_polarity: positive

judging:
  repair_retries: 1
  parse_retries: 1
  api_retries: 2
```

## Post-Hoc Judge Config

Used with `tdec judge`. Can reference judges by filename or define inline:

```yaml
# Reference judges from configs/judges/
judges:
  - kimi-k2-5
  - gpt-5-mini

judging:
  repair_retries: 1
  parse_retries: 1
  api_retries: 2
```
