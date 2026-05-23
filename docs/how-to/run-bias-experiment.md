# How to Run a Bias Experiment

This guide shows how to test for structural biases in the debate
format: does speaking order matter? Does motion framing matter?
Do judges have label preferences?

## Design

Cross three factors:

- **debate_mode**: `pro_first`, `con_first`, `parallel`
- **motion_polarity**: positive ("X should happen") and negative ("X should not happen")
- **label_swap**: original A/B labels vs swapped

Use `conditions` in each run config to tag the experimental factors:

```yaml
run:
  name: bias-ubi-pro-first
  debate_mode: pro_first
  reuse_openings: false
  conditions:
    debate_mode: pro_first
    motion_polarity: positive
```

Set `reuse_openings: false` so each debate generates independent openings.

## Create the Run Configs

Create one config per condition combination. For a 3x2 design
(debate_mode x polarity), that's 6 configs:

- `configs/runs/bias-ubi-pro-first.yaml` (positive, pro_first)
- `configs/runs/bias-ubi-con-first.yaml` (positive, con_first)
- `configs/runs/bias-ubi-parallel.yaml` (positive, parallel)
- `configs/runs/bias-ubi-negated-pro-first.yaml` (negative, pro_first)
- `configs/runs/bias-ubi-negated-con-first.yaml` (negative, con_first)
- `configs/runs/bias-ubi-negated-parallel.yaml` (negative, parallel)

## Run All Conditions

```powershell
tdec run configs/runs/bias-ubi-pro-first.yaml
tdec run configs/runs/bias-ubi-con-first.yaml
tdec run configs/runs/bias-ubi-parallel.yaml
tdec run configs/runs/bias-ubi-negated-pro-first.yaml
tdec run configs/runs/bias-ubi-negated-con-first.yaml
tdec run configs/runs/bias-ubi-negated-parallel.yaml
```

## Add Label-Swap Runs

Create relabeled copies with a matched judge config (same judges
as the original runs):

```powershell
tdec relabel runs/<timestamp>__bias-ubi-pro-first configs/bias-judges.yaml --prompt-set configs/prompt-sets/natural.yaml --workers 10
```

Repeat for all 6 runs. This adds 6 more runs with `label_swap: true`
in their conditions.

## View the Results

Load all 12 runs in the viewer:

```powershell
tdec view runs/*bias-ubi*
```

The **Comparison** tab shows a cross-run ANOVA decomposing score
variance across `label_swap`, `motion_polarity`, and `debate_mode`,
with per-factor breakdown tables.

## Interpret the Results

- **label_swap** significant: judges are biased by A/B labeling.
- **motion_polarity** significant: the framing of the motion
  (positive vs negative) affects outcomes beyond the substantive
  position. Note: the ANOVA does not yet normalize for polarity
  direction, so this may partly reflect framing effects.
- **debate_mode** significant: speaking order or simultaneous
  structure affects outcomes.
- High residual: most variance is noise. Consider more judges or
  more repeated independent runs.
