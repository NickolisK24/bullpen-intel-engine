# Bullpen Identity V1

Bullpen Identity V1 is a deterministic backend layer that describes the
structural personality of a bullpen: who the bullpen is, not only what condition
exists tonight.

It consumes existing backend-authored intelligence only:

- Capacity Intelligence
- Resource Health
- Trust Hierarchy
- Coverage Safety
- existing availability and workload context already present in those reads

It emits a compact identity payload with an identity key, label, summary,
supporting traits, caveats, and confidence. V1 identities include
Trust-Concentrated Bullpen, Depth-Driven Bullpen, Flexible Distribution Bullpen,
Leverage-Heavy Bullpen, Fragile Coverage Bullpen, Resource-Strained Bullpen,
and Unknown / Insufficient Context.

## Boundary

Bullpen Identity V1 does not create a new data source, choose a pitcher, rank
relievers or teams, project future performance, create matchup advice, or
authorize usage instructions. It also does not expose raw internal scoring.

The identity payload preserves the existing governance posture:

```text
ranking_applied === false
selection_made === false
prediction_applied === false
```

## Difference From Coverage Safety

Coverage Safety answers whether the bullpen has enough room if the game needs
multiple relief innings. It is closer to a current coverage read.

Bullpen Identity answers what structural shape the bullpen appears to have
across capacity, resource health, trust hierarchy, and coverage. It is intended
to be more stable than one day of workload. A single heavy night should not
fully redefine a bullpen unless the existing intelligence inputs also show a
clear structural change.

## Why It Exists

Daily stories need memory and recognizability. Two teams can both have thin
coverage tonight, but one may be thin because the resource pool is strained and
another may be thin because the bullpen is built around a narrow trusted lane.

Bullpen Identity gives future story surfaces a stable baseball descriptor they
can use for memorability without adding tactical advice or expanding the public
contract beyond the existing governed intelligence layers.

## Story Integration V1

Identity-aware story integration uses Bullpen Identity only as supporting
texture inside the backend narrative renderer. It can add one public-safe
sentence that makes a story feel more aware of the bullpen's structural shape,
but it does not expose raw identity labels in story copy.

The integration is passive. It does not change story rule selection, feed
ordering, lead selection, story strength, reliever ordering, recommendations,
predictions, or public UI surfaces. Unknown or low-confidence identity reads
fail closed and do not add identity-driven language.
