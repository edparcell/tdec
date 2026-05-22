# Configuration Reference

Tournament configs are YAML files with these top-level keys:

```yaml
run: {}
judging: {}
topics: []
debaters: []
judges: []
```

## `run`

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `name` | string | Config filename stem | Run name used in the output directory. |
| `rounds` | integer | `3` | Number of turns per side in each debate. |
| `output_dir` | path | `runs` | Base directory for generated run artifacts. |
| `include_self_debates` | boolean | `true` | Include same-model pro/con debates. |
| `workers` | integer | `1` | Concurrent debate and judgement jobs. Must be at least `1`. |

Example:

```yaml
run:
  name: single-payer-openrouter
  rounds: 3
  output_dir: runs
  include_self_debates: true
  workers: 10
```

## `judging`

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `repair_retries` | integer | `1` | Attempts to repair malformed judge JSON using the bad output and parse error. |
| `parse_retries` | integer | `1` | Fresh judge prompt retries after repair attempts fail. |

Example:

```yaml
judging:
  repair_retries: 1
  parse_retries: 1
```

## `topics`

Each topic defines one motion.

| Field | Type | Description |
| --- | --- | --- |
| `id` | string | Stable identifier used in artifact filenames. |
| `motion` | string | The resolution being debated. |
| `pro_position` | string | Instruction for the pro side. |
| `con_position` | string | Instruction for the con side. |

Example:

```yaml
topics:
  - id: us_single_payer_healthcare
    motion: The United States should adopt a single-payer healthcare system.
    pro_position: Argue that the United States should adopt a single-payer healthcare system.
    con_position: Argue that the United States should not adopt a single-payer healthcare system.
```

## `debaters` And `judges`

Debaters and judges use the same model config shape.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `id` | string | Yes | Stable model identifier used in summaries and filenames. |
| `provider` | string | Yes | LiteLLM provider name, such as `openrouter` or `ollama`. |
| `model` | string | Yes | Provider model name. |
| `api_base` | string | No | Custom API base URL, commonly used for local Ollama. |
| `api_key` | string | No | Inline API key. Avoid committing configs that use this. |
| `api_key_env` | string | No | Environment variable containing the API key. |
| `temperature` | number or null | No | Sampling temperature. Use `null` to omit the parameter. |
| `max_tokens` | integer | No | Completion token cap. Defaults to `4096`. |

If `api_key_env` is present and the environment variable is missing, TDEC
refuses to start the tournament.

OpenRouter example:

```yaml
debaters:
  - id: gpt_5_nano
    provider: openrouter
    model: openai/gpt-5-nano
    api_key_env: OPENROUTER_API_KEY
    temperature: null
    max_tokens: 10000
```

Ollama example:

```yaml
judges:
  - id: local_tinyllama_judge
    provider: ollama
    model: tinyllama
    api_base: http://localhost:11434
    temperature: 0.2
    max_tokens: 1200
```
