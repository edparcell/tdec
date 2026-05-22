# Tournament Model

TDEC treats a debate tournament as two separate problems:

1. Generate adversarial transcripts.
2. Score those transcripts with independent judges.

Keeping those problems separate makes the artifacts easier to inspect. A debate
artifact says what the debaters did. A judgement artifact says what one judge
made of that transcript.

## Pairings

For each topic, TDEC builds ordered pairings from the debater list.

With models `A`, `B`, and `C`, the default pairings are:

```text
A pro / A con
A pro / B con
B pro / A con
A pro / C con
C pro / A con
B pro / B con
B pro / C con
C pro / B con
C pro / C con
```

Self-debates are included by default because they reveal how strongly the motion
or prompt setup favors one side when model quality is held constant. Disable
them with:

```yaml
run:
  include_self_debates: false
```

Self-debates contribute to motion and pair summaries. They do not affect Elo,
because a model cannot gain useful skill rating information by beating itself.

## Debate Order

Inside one debate, turns are sequential:

1. Pro opening.
2. Con response.
3. Pro response.
4. Con response.
5. Repeat until the configured number of rounds is complete.

Each side has its own message history. After every turn, TDEC shares that turn
with the opponent as a user message. This keeps the implementation close to the
manual workflow of copying one model's output into the other model.

## Concurrency

Different debates are independent, so TDEC can run them concurrently. Judgements
are also independent once the debate transcript exists, so TDEC runs those
concurrently too.

Turns inside a debate are not parallelized. A turn depends on the prior turn.

The `workers` setting controls the thread pool size. Higher values reduce wall
clock time but increase simultaneous provider requests.

## Topics And Positions

A topic has a neutral motion plus explicit pro and con instructions. This lets
you keep the motion short while still telling each side to argue broadly across
the relevant terrain.

The debater system prompt also tells models not to collapse onto one narrow
point, not to dictate the opponent's framing, and not to fabricate private facts
or sources.
