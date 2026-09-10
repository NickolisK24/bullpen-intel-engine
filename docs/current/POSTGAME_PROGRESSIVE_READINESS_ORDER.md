# Postgame Progressive Readiness Order

## Problem (production run 471)

A completed game's two teams (117, 145) refused progressive Team State publication with
`data_state=missing / confidence=unknown / status_code=data_limited`, even though the
game was final, its appearance ledger was committed, and progressive accounting was clean
(attempted=2, accounted=2, missing=0). The postgame command also exited 1 solely because
the league snapshot was (correctly) still pending during an active slate.

## Proven root cause — the roster authority, not fatigue

The exact refusal triple is produced only by the active-bullpen **roster authority**
resolving zero arms (`team_readiness_coverage.assess_team_coverage` branch 1). Once a
game is final, the global availability reference date advances to the day AFTER it, while
that team's roster snapshot is dated at the slate day — so the authority is queried for a
date its snapshot does not cover and comes back empty. Reproduced exactly: roster absent
→ this signature; fatigue absent → a *different* signature; a slate-dated roster snapshot
→ both teams publish; and `_active_bullpen_membership` resolves a slate-dated snapshot
only at the slate reference date, not slate+1.

## Repair 1 — anchor the progressive read to the completed game's slate

`resolve_team_readiness_payload` now anchors the availability reference date to the
checkpoint's slate (`data_through`) whenever the read is produced from a team-progressive
checkpoint authority (`subject_type='team_progressive'`). The active-bullpen membership
and per-record availability classification are then evaluated as-of the exact slate the
checkpoint attests to, where the roster snapshot exists. It fails closed unchanged when
that slate genuinely has no roster snapshot (no manufactured readiness). League/global
reads are untouched (the anchor is gated on the team-progressive discriminator).

## Repair 2 — progressive after fatigue recalculation commits

The postgame lane now ingests → recalculates and **commits** fatigue/workload evidence →
publishes progressively. The newly-completed game_pks are collected during ingestion and
handed off to this later point unchanged. A fatigue recalculation failure fails the run
closed before progressive runs, so no team is ever published on partial evidence; the
completed-game ingestion commit is preserved and the game is recovered by the existing
league reconciliation backstop. Equivalent reruns remain idempotent (checkpoint identity
+ artifact equivalence are unchanged from the progressive-publication feature).

## Repair 3 — postgame job success vs league publication result

The postgame command's success and the LEAGUE snapshot's publication are two separate
results. The publication proof gains a `league_publication_status`:

- `published` — the candidate verified as serving;
- `expected_pending_active_slate` — the candidate is pending ONLY because non-final games
  remain, the schedule is known, and every final game is fully ingested (no
  failed/incomplete/missing markers). Judged from the DETAILED slate-coverage object, not
  the top-level reason string;
- `failed` — any genuine schedule/ingestion/marker/trust gap (fail closed).

The postgame command exits 0 when the sync succeeded and the league publication is either
verified or an expected active-slate pending; the proof still honestly reports
`verified=false` / `candidate_is_published=false`. The **daily sync is unchanged** — it
still requires a verified published trusted snapshot.

## Preserved / out of scope

League slate-coverage requirements, schedule finality, appearance-ledger authority,
publication-critical contract, serving-snapshot selection, the team-progressive
`subject_type` source identity, checkpoint uniqueness/evidence-revision, doubleheader
chronology, canonical Team Operations readiness, active-bullpen thresholds, SC-02, public
Team State mapping, `team-state-1.1.0` payload, artifact integrity, and the public
API/page are all unchanged. Snapshots 272 and 274 are not mutated or manually published.
No queue/worker/retry infrastructure and no schedule-polling changes are added. SC-05
remains blocked and not started.
