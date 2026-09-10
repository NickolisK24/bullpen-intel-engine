# Consequence Intelligence V1

Consequence Intelligence V1 is a deterministic backend foundation that
translates existing bullpen conditions and meaningful day-over-day changes into
baseball consequences.

It consumes existing BaseballOS intelligence only:

- Capacity Intelligence
- Resource Health
- Coverage Safety
- Trust Hierarchy
- Bullpen Identity
- What Changed Since Yesterday

V1 emits descriptive consequence records with a consequence type, summary,
context, significance, confidence, and supporting facts.

## What It Does

Consequence Intelligence explains why a meaningful bullpen change matters in
baseball terms. It can describe:

- more or less flexibility
- more or less coverage margin
- wider or narrower trust support
- easier workload distribution or heavier workload concentration
- a more or less settled bullpen shape

The layer is intentionally explanatory. It turns existing structured reads into
plain baseball implications such as fewer clean paths, more coverage margin, or
a narrower trusted support layer.

## Narrative Language Standard

Any user-facing consequence, summary, or explanatory line derived from this
layer must comply with
[`docs/product/BASEBALLOS_WRITING_RULES.md`](../product/BASEBALLOS_WRITING_RULES.md).
Internal metric names should be translated into baseball meaning before reaching
users, with the managerial consequence made explicit.

## What It Does Not Do

This layer does not predict game outcomes, forecast performance, estimate
probabilities, rank teams or relievers, recommend pitcher usage, select a
reliever, simulate a game, add betting language, or expose raw internal scores.

The payload preserves the existing governance posture:

```text
ranking_applied === false
selection_made === false
prediction_applied === false
```

## Difference From What Changed V1

What Changed Since Yesterday V1 answers what moved between the current snapshot
and the prior snapshot. It emits the change ledger: rested options changed,
coverage improved, the trusted group narrowed, or the bullpen identity changed.

Consequence Intelligence V1 answers why that meaningful movement matters in
baseball language. It does not re-detect the change. It uses the existing change
ledger and current intelligence context to explain the consequence: more
flexibility, less coverage margin, wider trust support, heavier workload
concentration, or a more settled bullpen shape.

## Difference From Predictions

Consequences describe structural implications, not future outcomes. Saying that
coverage has less margin is different from saying the bullpen will struggle.
Saying the trusted group is narrower is different from telling a manager who to
use.

V1 stays on the descriptive side of that line. It explains the baseball shape of
the current read without projecting what will happen next.
