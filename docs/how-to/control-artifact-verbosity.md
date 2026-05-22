# Control Artifact Size And Raw Metadata

TDEC writes compact artifacts by default. Use this guide to choose how much raw
provider metadata to keep.

## Use Compact Artifacts

This is the default:

```powershell
uv run tdec run configs/my-run.yaml
```

Compact artifacts keep:

- Transcript text.
- Timing.
- Token usage.
- Cost data or cost errors.
- Finish reason.
- One reasoning text copy when available.
- Basic provider response identifiers.

Compact artifacts remove duplicated visible text, repeated reasoning fields, and
encrypted/additional provider reasoning blobs when visible content exists.

## Use Full Artifacts

Use full metadata when diagnosing provider behavior:

```powershell
uv run tdec run configs/my-run.yaml --artifact-verbosity full
```

Full artifacts keep the full serializable LiteLLM response metadata for every
successful call, with credential-like fields redacted.

## Blank Outputs Always Keep Full Metadata

If a model returns blank visible content, TDEC keeps full response metadata for
that call even in compact mode. This is intentional: blank outputs are exactly
where provider-specific metadata is most useful.

## Keep Runs Out Of Git

Generated runs are ignored by git:

```text
runs/*
!runs/.gitkeep
```

You can keep large diagnostic runs locally without publishing them.
