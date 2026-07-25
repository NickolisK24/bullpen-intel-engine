# Progressive Team State Publication (Share Cards)

## Problem

Team State Share Artifact generation was coupled to the **league** dashboard
snapshot: the post-publication hook fired only when the whole-league snapshot
published, and that snapshot itself withholds until the ENTIRE required slate is
final (schedule finality + appearance ledger + publication-critical). Consequence: a
single late game between two other teams (e.g. a 10:15 PM ET Giants–Angels game) held
back Team State artifacts for every team whose game ended hours earlier. Production
run 469 / snapshot 272 exposed this — the league snapshot correctly stayed pending
(13 of 15 games not final), so no team received an artifact.

## Two publication authorities

1. **League snapshot — all-or-nothing (unchanged).** Used for league-wide aligned
   surfaces (bullpen board, league comparisons, synchronized stories). It still
   publishes only when the complete required slate passes every gate. **No league
   trust gate is weakened.** Snapshot 272 is untouched.

2. **Team-progressive — team-scoped and progressive (new).** An individual team's
   Team State artifact may publish after THAT team's own completed game and required
   evidence pass the canonical trust gates. A late unrelated game never blocks it.

## Team-scoped source authority

`models/team_progressive_publication.py` (new table `team_progressive_publications`,
migration `b3d9f1a7c2e5`) is an immutable per-team checkpoint that IS the trusted
source for a progressive artifact — it exists before any league snapshot for the
slate. Its `id` supplies the artifact's non-null `source_snapshot_id` (that column has
no FK to `dashboard_snapshots`; it records "the trusted source that authorized this
artifact"). It records team_id, trigger game_pk, official game date, data_through,
availability reference, source sync run, the fail-closed trust verdict
(`game_final` / `ledger_complete` / `evidence_complete` / `trusted` /
`unavailable_reason`), and an `evidence_revision` fingerprint. It exposes a
`TeamStateSnapshotAuthority`-compatible surface so the existing single-team path
consumes it unchanged.

## Durable source-authority discriminator (no id-collision)

`source_snapshot_id` alone is a bare integer, and a league `dashboard_snapshots.id`
and a `team_progressive_publications.id` share one integer space — they can collide.
The trusted-source TYPE must therefore be durable on the artifact itself, not inferred
from that id. Every progressive artifact stamps `subject_type='team_progressive'`
(and a self-describing `subject_key` = `team_progressive:{team_id}:{game_pk}:
{evidence_revision}`); a league artifact leaves `subject_type` NULL. `subject_type`
and `subject_key` are already part of the equivalence + integrity contract
(`build_equivalence_document`) and are frozen at publish, so the discriminator is
immutable, tamper-evident, and part of identity: a league artifact and a progressive
artifact can never dedup-collide even at the same numeric `source_snapshot_id`, and
`models/share_artifact.py::source_authority_type` reads the durable field (never the
id) to classify an artifact. Legacy and league artifacts keep their exact prior
identity (subject_type stays NULL), so no existing artifact is invalidated and no new
migration is needed for the discriminator.

## Finality / ledger contract (fail closed)

A checkpoint is `trusted` only when, for that team's triggering game: the game is
final under the canonical finality state, the box score / appearance ledger for the
game is committed (postgame marker fully processed), and both participating teams
resolve. Otherwise it is `withheld` with a governed reason (`game_not_final`,
`appearance_ledger_incomplete`, `participating_teams_unresolved`) and the team's
attempt refuses. Finality is necessary, not sufficient — SC-02 still evaluates the
team's own active-bullpen coverage downstream.

## Independent per-team evaluation

`services/team_progressive_publication.py::publish_team_state_for_final_game(game_pk)`
resolves the two participating teams and evaluates each INDEPENDENTLY through the exact
existing path — `resolve_team_readiness_payload` → `gather_team_state_source` →
`evaluate_team_state_eligibility` → `build_team_state_payload` → `publish_share_artifact`
— with the team checkpoint as `source_authority`. One team may publish while its
opponent refuses for a team-specific trust problem. No other (unfinished) game is
consulted. Accounting for one game: `attempted == accounted == 2`, `missing == 0`.

Reuse seams (no duplicated engine): `gather_team_state_source` and
`generate_team_state_artifact` gained a `source_authority` parameter; the readiness
freshness anchor (`readiness_snapshot_freshness`) duck-types a team-scoped authority's
own trust verdict. SC-02 eligibility, coverage thresholds, public state vocabulary
(Fresh/Stretched/Vulnerable), and the canonical public-copy authority are unchanged.

## Team-scoped freshness

A progressive artifact anchors freshness to the team's completed-game `data_through`,
not the global `max(GameLog.game_date)`. A stale team source, a missing authority, or
a data_through outside `ACTIVE_WINDOW_DAYS` still fails closed. `ACTIVE_WINDOW_DAYS`
is unchanged; finality alone does not make a stale team current.

## Idempotency and corrections

The checkpoint is keyed on `(team_id, trigger_game_pk, evidence_revision)`, and that
key is enforced by a DB **unique constraint** (`uq_team_progressive_team_game_
revision`), not merely by a find-first query: two concurrent postgame runs racing to
publish the same final game cannot both insert — the loser trips the constraint inside
its SAVEPOINT, rolls back just that savepoint, and reuses the winner's checkpoint, so
no duplicate checkpoint (and therefore no duplicate artifact) is ever minted.

`evidence_revision` is a fingerprint of the game's committed appearance ledger, hashed
over the SORTED meaning-bearing pitching-line fields (pitcher, pitch count, recorded
outs, per-row stat-correction counter). It is therefore row-order independent (the DB
return order cannot change it) and correction sensitive (a genuine box-score
correction changes it even when the number of appearances is unchanged — a bare row
count would miss that). Re-running the same final-game evidence reuses the same
checkpoint id → the same artifact `equivalence_key` → dedup (no duplicate artifacts on
reconciliation reruns). A genuine authoritative correction changes `evidence_revision`
→ a new immutable checkpoint → a new immutable artifact (its `subject_key` carries the
new revision); the prior artifact is never rewritten. Doubleheader Game 1 and Game 2
have distinct `game_pk` values → distinct checkpoints → distinct artifacts. The
"latest team state" read orders by `product_date` first (baseball chronology), so a
later game's artifact is never shadowed by an earlier-day artifact that published
later; within one product date the later publication is the deterministic tie-break.

## Trigger

`services/sync.py` postgame per-game lane: after each game reaches full completion and
commits, its `game_pk` is collected and, at the end of the pass,
`_safe_run_progressive_team_publication` runs each through the progressive publisher.
It is gated by `SHARE_ARTIFACT_AUTOGENERATION_ENABLED` (same operator switch as the
league batch) and is fully exception-isolated — a progressive failure can never break
the postgame sync and never touches the league snapshot. No webhooks, queues, workers,
retry framework, or polling loops are added; it reuses the existing scheduled postgame
reconciliation (crons 02:00/04:00/06:00 UTC) which already runs during the active
slate and already knows the newly-final game_pks.

## League reconciliation (backstop, unchanged)

When the full slate later completes, the league snapshot publishes and the existing
all-team batch runs. Because a progressive artifact carries the durable
`subject_type='team_progressive'` discriminator (part of its equivalence identity), a
league-sourced artifact has a different identity and does not collide — even if the
checkpoint id and the league snapshot id happen to be the same integer. Progressive
artifacts are never deleted, and the morning league run remains the backstop for
missed events, corrections, and complete aligned league state.

## Operations / audit

The operations read is observability only. A progressive artifact's DURABLE source
type is its `subject_type` discriminator, read via `source_authority_type` — never
inferred from `source_snapshot_id`, never from an audit row. The league-scoped
coverage overview resolves the latest LEAGUE snapshot and, to stay collision-safe,
excludes the team-progressive scope by that durable discriminator: published-artifact
coverage excludes `subject_type='team_progressive'`, and the audit lane excludes
`request_source='progressive_game_final'`. So a checkpoint id that numerically equals
the league snapshot id can never inflate or corrupt league coverage. Every progressive
attempt is still recorded in the existing `share_artifact_generation_audits`
(request_source `progressive_game_final`) for traceability, and the operator
artifact/lifecycle projections surface `source_authority_type` so a team-progressive
event is visibly distinct from a league batch. No second operations dashboard is
added.

## Out of scope / preserved

SC-02 unchanged; no fourth public state; no `data_limited` publication; no renderer /
PNG / Open Graph; no share actions; no Product Intelligence; no league comparison
timestamp mixing; no threshold or active-bullpen scope change; no browser-triggered
generation; no manual publication of snapshot 272; existing immutable artifacts
(including the legacy Arizona artifact and all `team-state-1.1.0`) remain valid;
payload version unchanged (no payload schema change).

## SC-04B / SC-05

Unblocks SC-04B: a team can now receive a current, trustworthy Team State artifact
after its own game, independent of the league slate. SC-05 remains blocked and not
started.
