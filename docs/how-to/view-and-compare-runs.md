# How to View and Compare Runs

## View a Single Run

```powershell
tdec view runs/<run-dir>
```

Opens a local server. Add `--open` to auto-launch the browser.
Add `--port 8080` to pick a specific port.

## View Multiple Runs

```powershell
tdec view runs/run1 runs/run2 runs/run3
```

Or with a glob:

```powershell
tdec view runs/*bias-ubi*
```

A run selector dropdown appears. The **Comparison** tab shows
cross-run ANOVA when runs have different `conditions` metadata.

## Export a Standalone Report

```powershell
tdec export runs/<run-dir> -o report.html
```

Generates a self-contained HTML file with all data embedded.
Works offline - just open the file in a browser. Single-run only.

## Viewer Tabs

- **Motions** (default for multi-topic): per-motion results table with
  per-judge breakdowns. Click a motion to jump to its cross-table.
- **Debates**: Elo rankings, cross-table matrix. Click a cell for
  judge verdicts, rubric scores, and full debate transcript.
- **Judges**: pro/con voting bar chart, judge-by-debater win rate
  matrix, inter-judge agreement matrix.
- **Analysis**: side bias test, model strength with confidence intervals,
  rubric profile heatmap, statistical power, within-run ANOVA.
- **Comparison** (multi-run only): cross-run ANOVA with per-factor
  breakdown tables.
