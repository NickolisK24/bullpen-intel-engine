# Decision: Team Board Performance Intelligence

- **Date:** August 21, 2026
- **Owner:** Nickolis Kacludis
- **Status:** Adopted
- **Scope:** Team Board current-state supporting context

## Decision

The Team Board may publish M-001 Active Bullpen ERA through the existing
Current Active-Pen Performance authority. This opens M-001 only for the Team
Board public reader. Team State and Share Artifact performance gates remain
blocked.

The public group is the represented Team Board's default-visible current active
bullpen. The performance sample is all qualifying official completed regular-
season relief appearances through the represented date made for that team by
those pitchers. Historical ownership remains `GameLog.appearance_team_id`; a
pitcher's current team never reassigns an old appearance.

The existing M-001 decisions remain unchanged:

- formula: earned runs times 27 divided by integer recorded outs;
- minimum sample: 108 recorded outs (36.0 innings);
- precision: two decimal places with one `ROUND_HALF_UP` operation;
- below-sample wording: `Not Enough Innings Yet`;
- zero denominator, invalid row, unprovable finality, unresolved team ownership,
  and unresolved starter/relief identity fail closed.

The Team Board carries the metric, current active-arm count, contributing-arm
count, qualifying relief appearances, innings, season window, represented date,
method version, limitation, and the existing four-level evidence object. The
frontend renders this backend-authored read and performs no baseball arithmetic.

## Unsupported metrics

WHIP and HR/9 have source components but no approved public metric/sample
contract. K-BB% additionally requires complete publication-critical batters-
faced authority. Inherited-runner outcomes remain incomplete. They are not
published or represented as zero. The Team Board exposes a concise limitation
and keeps the supported M-001 read independently usable.

## Why the window is not 14 days

The governing performance-family default is the current regular season. The
14-day workload and deployment windows answer different questions and do not
authorize a performance-window change. This package preserves the established
season window rather than creating a second M-001 definition.

## Boundaries

This decision does not:

- change Team State, arm reads, workload, Rest Status, or deployment;
- create a score, grade, ranking, quality label, or future-performance claim;
- publish WHIP, K-BB%, HR/9, or inherited-runner values;
- add a historical performance comparison or mutate a publication;
- open performance authority for Share Artifacts or any non-Team-Board surface.
