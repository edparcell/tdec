# Create An OpenRouter Tournament

Use this guide when you want to run TDEC against hosted models through
OpenRouter.

## Add Your API Key

Create `.env` in the repository root:

```text
OPENROUTER_API_KEY=sk-or-...
```

`.env` is ignored by git. The tracked `.env.sample` file shows the expected
variable name without containing a key.

## Copy A Config

Start from the cheap OpenRouter example:

```powershell
Copy-Item configs\openrouter-cheap.yaml configs\my-openrouter.yaml
```

## Set The Motion

Edit the `topics` block:

```yaml
topics:
  - id: my_motion
    motion: >-
      The motion text goes here.
    pro_position: >-
      Argue for the motion. Build the widest serious case.
    con_position: >-
      Argue against the motion. Build the widest serious case.
```

Use a short, stable `id`. It becomes part of artifact filenames.

## Choose Debaters

Each debater needs an `id`, provider, model, API key source, temperature, and
token cap:

```yaml
debaters:
  - id: model_a
    provider: openrouter
    model: provider/model-name
    api_key_env: OPENROUTER_API_KEY
    temperature: 0.7
    max_tokens: 2000
```

Use `temperature: null` for models that reject a temperature parameter.

## Choose Judges

Judges use the same model shape:

```yaml
judges:
  - id: judge_a
    provider: openrouter
    model: provider/judge-model-name
    api_key_env: OPENROUTER_API_KEY
    temperature: 0.2
    max_tokens: 3000
```

Judges should have enough output tokens to return the full JSON judgement. If
the judge returns invalid JSON, TDEC attempts repair and retry according to the
`judging` settings.

## Run It

```powershell
uv run tdec run configs/my-openrouter.yaml
```

Use more workers if the tournament is slow:

```powershell
uv run tdec run configs/my-openrouter.yaml --workers 4
```

Higher worker counts create more simultaneous provider requests. If the provider
rate-limits you, lower the worker count.
