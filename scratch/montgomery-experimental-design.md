# Applying Montgomery's Experimental Design to TDEC

Thoughts on how Douglas Montgomery's *Design and Analysis of Experiments*
framework applies to structured LLM debate tournaments.

## What We're Already Doing

TDEC's tournament structure maps naturally to several DoE concepts:

- **Factorial design**: The cross-table is a full factorial in (pro model x
  con model x topic). Every combination is run.
- **Controls**: Self-debates are a control condition - they isolate the effect
  of side assignment from model strength.
- **Replication**: Multiple judges per debate provide independent replications
  of the measurement (verdict).
- **Blocking on confounds**: Parallel rounds block on speaker order, removing
  first-mover and last-rebuttal advantages as confounds.

## What We Should Add

### 1. Proper Factorial Decomposition

The twenty-motions run with 2 models x 20 topics is a two-factor experiment.
But we analyze it with Elo, which collapses everything into a single ranking.
A two-way ANOVA would decompose the variance in outcomes into:

- **Model effect**: Does model A consistently outperform model B?
- **Topic effect**: Are some topics more pro-favorable or more contested?
- **Model x Topic interaction**: Does model A's advantage depend on the
  topic domain? (e.g., strong on economic motions, weak on social ones)

The interaction term is the most interesting - it tells us whether model
rankings are stable across domains or domain-dependent.

For the strategy run (empiricist/pragmatist/narrative/principled on one
topic), a one-way ANOVA on judge scores would test whether strategy
significantly affects debate outcomes. The F-test tells us if the strategy
differences are real or could be chance.

### 2. Blocking

Topics are a natural blocking variable. Montgomery's randomized complete
block design (RCBD) fits perfectly: each topic is a block, and within each
block we observe every model pairing. This gives cleaner estimates of
model effects by removing topic-to-topic variance.

Currently we compute a single Elo across all topics. A blocked analysis
would compute model effects adjusted for topic difficulty, revealing
whether a model's high Elo comes from genuine strength or from being
lucky on favorable topics.

### 3. Power Analysis

How many judges do we need per debate to detect a meaningful difference
between debaters? The Kimi API failure in the industrial policy run
shows we're running close to the edge.

With 2 judges per debate and a binary outcome, we have very low power
to detect anything other than unanimous agreement. Montgomery's power
calculations would tell us: given the observed variance in judge scores,
how many judges are needed for 80% power to detect (say) a 15-point
difference in average score?

Rule of thumb from the existing data: judges agreed ~80% of the time in
the single-payer run. With 2 judges, a split (1-1) tells us nothing. With
3 judges, a 2-1 split at least gives a majority. With 5 judges, the
variance in the estimated win rate drops substantially.

### 4. Response Surface

We're currently using a binary outcome (winner). But the judge data
includes continuous responses:

- `pro_score` and `con_score` (0-100)
- `confidence` (0-1)
- Six rubric subscores (0-10 each): breadth, responsiveness, evidence
  quality, moral reasoning, institutional reasoning, strategic clarity

ANOVA or mixed models on these continuous variables extract far more
signal than the binary winner. A debate scored 72-68 tells us something
very different from one scored 90-30, but both count as "pro wins" in
the current analysis.

The rubric subscores are particularly rich. A model might score high on
evidence quality but low on moral reasoning - this profile information
is lost when we collapse to a single winner.

### 5. Randomization

Currently the debater list order determines pairing generation order,
which determines execution order (partially - the thread pool adds
some randomness). True randomization of run order would guard against
time-dependent confounds (API performance degradation, rate limiting,
model provider updates mid-run).

### 6. Fractional Factorial for Large Runs

A full factorial with 5 models, 20 topics, and self-debates produces
500 debates. Montgomery's fractional factorial designs could identify
which model x topic combinations to run to get most of the information
at a fraction of the cost. A Resolution V design would estimate all
main effects and two-factor interactions without running every cell.

This becomes important when adding factors: model x strategy x topic x
prompt-set is a four-factor experiment that quickly becomes expensive
as a full factorial.

## Practical Implementation

### Phase 1: Analysis tooling (no run changes needed)

A `tdec analyze` command or Jupyter notebook that reads summary.json and
existing artifacts to produce:

- Two-way ANOVA table (model x topic) with interaction test
- Blocked Elo estimates (Elo within each topic, then aggregated)
- Win rate confidence intervals per model
- Rubric subscore profiles per model (radar chart or heatmap)
- Power analysis: recommended number of judges given observed variance
- Effect sizes: Cohen's d for model differences

Libraries: `scipy.stats` for ANOVA, `statsmodels` for mixed models,
`matplotlib`/`seaborn` for visualization.

### Phase 2: Design specification (run config changes)

Extend run configs to express experimental designs:

- Specify factors and levels explicitly
- Support fractional factorial designs (auto-generate the pairing subset)
- Power-based judge count recommendation
- Randomized run ordering

### Phase 3: Adaptive designs

Montgomery covers sequential experimentation - run a screening experiment
first (few runs, many factors) to identify which factors matter, then a
focused experiment (many runs, few factors) on the important ones. TDEC
could support this as a two-stage workflow.

## Key Reference

Montgomery, D.C. *Design and Analysis of Experiments*, 10th edition.
Particularly relevant chapters:

- Ch 3-4: Factorial experiments (our core design)
- Ch 5: Randomized blocks (topic blocking)
- Ch 8: Fractional factorials (scaling up)
- Ch 10: Response surface methodology (using continuous judge scores)
- Ch 13: Nested and split-plot designs (judges nested within debates)
