# What Changed Since Yesterday V1

What Changed Since Yesterday V1 is a deterministic backend foundation for
explaining what is different in a bullpen intelligence read compared with the
prior snapshot.

It compares existing BaseballOS intelligence only:

- Capacity Intelligence
- Resource Health
- Coverage Safety
- Trust Hierarchy
- Bullpen Identity

V1 focuses on change detection. It emits meaningful team-level changes with a
change type, direction, summary, significance, confidence, and supporting facts.

The stored public dashboard contract exposes the frontend-safe projection under
`what_changed_since_yesterday`. That public contract includes a typed `state`
plus the existing `comparison`, `items`, `item_count`, `limitations`, and
`reason_codes` fields so a future renderer can distinguish:

- `state: changes_detected` — trusted comparison is available and at least one
  public-safe change item is present.
- `state: no_meaningful_changes` — trusted comparison is available, but no
  team-level bullpen movement cleared the public note threshold.
- `state: insufficient_context` — comparison is unavailable or withheld;
  `comparison.reason_codes`, top-level `reason_codes`, and `limitations`
  explain why without emitting partial diffs.

The dashboard stores this public contract for all three states. A quiet
comparable day is not omitted from the stored payload.

## What It Does

What Changed Since Yesterday V1 looks for meaningful movement in:

- rested options
- usable bullpen depth
- resource health state
- coverage safety label
- trusted-group size
- bullpen identity

Small count movement is intentionally suppressed unless it crosses an existing
structural boundary. The goal is to explain what matters, not to narrate every
minor fluctuation in the board.

## What It Does Not Do

This layer does not create new source data, project future performance, rank
relievers or teams, choose a pitcher, recommend bullpen usage, simulate a game,
or expose raw internal scores.

The payload preserves the existing governance posture:

```text
ranking_applied === false
selection_made === false
prediction_applied === false
```

## Why It Exists

BaseballOS already describes the current bullpen state. Retention-oriented story
surfaces also need memory: what changed since the last read, and why the current
story is different from yesterday's story.

This foundation gives future story or review surfaces a stable way to say that
capacity improved, coverage tightened, a trusted group widened, or the identity
shifted without turning that observation into tactical advice.

## Narrative Language Standard

Any user-facing summary or story derived from this layer must comply with
[`docs/product/BASEBALLOS_WRITING_RULES.md`](../product/BASEBALLOS_WRITING_RULES.md).
Change language should explain what moved, why that movement matters in baseball
terms, and how internal reads translate into bullpen reality before users see
them.

## Relationship To Role Change Detection

Role Change Detection V1 is about structural role movement and bullpen role
shape in dashboard snapshots. It answers whether the role/trust structure moved
in a way that matters.

What Changed Since Yesterday V1 is broader. It compares multiple existing
intelligence layers and emits a compact change ledger across capacity, resource
health, coverage, trust structure, and identity. It can use trust movement as
one input, but it does not replace Role Change Detection or assign pitcher roles.

In short:

- Role Change Detection explains role/trust structure movement.
- What Changed Since Yesterday explains the broader team-level intelligence
  delta across existing reads.
