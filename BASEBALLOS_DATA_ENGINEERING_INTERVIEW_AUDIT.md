# BaseballOS Data Engineering Interview Audit

Interview target: SEP Data Engineer, Wednesday, August 26, 2026, 4:00 PM ET  
Audit basis: current repository implementation on `main`, inspected August 24, 2026  
Claim rule: **Implemented** means executable code/schema plus corroborating tests where available. **Partial** means a real implemented substrate exists but the broader capability is not complete or not authoritative. **Documented/future only** is never presented as shipped.

## 1. Executive Interview Summary

### The defensible answer

BaseballOS demonstrates Data Engineering ability because it turns unreliable, revision-prone public MLB data into governed relational facts and reproducible read models. The strongest evidence is:

1. **Relational grain and integrity are explicit.** `pitchers.mlb_id` is unique; one pitcher can have many `game_logs`; `(pitcher_id, mlb_game_pk)` is the database-enforced natural key for an appearance; `(team_id, game_pk)` is the schedule grain; `(pitcher_id, snapshot_date)` is the roster-history grain. Constraints also prevent impossible innings, false team attribution, and optimistic completion markers. `backend/models/pitcher.py:L4-L34`; `backend/models/game_log.py:L40-L89`; `backend/models/scheduled_game.py:L13-L46`; `backend/models/roster_status_snapshot.py:L32-L60`; `backend/models/game_ingestion_work_item.py:L81-L126`
2. **Ingestion is incremental and idempotent.** The daily critical lane checkpoints work by MLB game, the postgame lane fetches only completed games not already fully processed, transaction ingestion uses a bounded date window and deterministic key, and replays classify rows as created/corrected/unchanged instead of blindly inserting. `backend/models/game_ingestion_work_item.py:L5-L22`; `backend/services/sync.py:L415-L453`; `backend/services/sync.py:L5763-L5781`; `backend/services/transaction_ingestion.py:L223-L239`; `backend/services/transaction_ingestion.py:L627-L669`
3. **Unknown is not silently converted to zero.** Missing pitches, hits, and walks remain nullable; exact zero remains a real value. That distinction is preserved through derived fatigue facts and public payloads. `backend/models/game_log.py:L98-L116`; `backend/services/sync.py:L519-L557`; `backend/models/fatigue_score.py:L24-L30`; `backend/tests/test_fatigue_pitch_null_persistence.py:L123-L167`
4. **Corrections carry provenance and invalidate dependent evidence.** Existing source facts are compared field-by-field; safe authoritative changes increment correction metadata and mark all registered downstream evidence families for recomputation. Unsafe corrections are dead-lettered. `backend/services/sync.py:L1123-L1259`; `backend/services/sync.py:L605-L675`
5. **Publication is a separate, transactional trust decision.** A sync can ingest useful data yet withhold a replacement snapshot. Snapshot and sync metadata commit together; on failure the transaction rolls back and the prior trusted snapshot continues serving. `backend/services/sync.py:L5529-L5609`; `backend/services/dashboard_snapshot.py:L328-L429`; `backend/tests/test_dashboard_snapshot.py:L1314-L1407`
6. **Historical state is preserved by value.** Published share artifacts freeze payload, trust metadata, evidence values, versions, source snapshot, and hashes; later changes supersede rather than rewrite them. `backend/models/share_artifact.py:L168-L239`; `backend/models/share_artifact.py:L318-L352`; `backend/models/share_artifact.py:L507-L568`
7. **Reliability is operational, not cosmetic.** The MLB client has timeouts, typed failures, capped exponential backoff with jitter, `Retry-After`, and endpoint metrics; poisoned records become durable dead letters; Postgres advisory locks prevent overlapping public writers. `backend/services/mlb_api.py:L103-L174`; `backend/services/mlb_api.py:L180-L303`; `backend/models/sync_failure.py:L5-L40`; `backend/services/sync_metadata.py:L292-L412`

### Best single example to lead with

Lead with the **canonical appearance ledger**: a mutable `Pitcher.team_id` represents current identity, while `GameLog.appearance_team_id` freezes the team represented in that game. Official game-side evidence resolves the historical team; disagreement becomes `conflict` with no team ID; the database constraint makes a silently selected team impossible. This combines modeling, identity resolution, temporal correctness, idempotency, provenance, and fail-closed behavior. `backend/models/game_log.py:L62-L78`; `backend/models/game_log.py:L135-L149`; `backend/services/sync.py:L4423-L4442`; `backend/tests/test_appearance_team_authority.py:L575-L644`

### Implementation status boundary

- **Implemented now:** PostgreSQL operational store, Alembic migrations, SQLAlchemy models/queries, MLB REST ingestion, daily and postgame scheduled pipelines, bounded transaction ingestion, roster and dashboard snapshots, durable sync metadata/dead letters, incremental checkpoints, publication gates, immutable share artifacts, correction/reconciliation services, and extensive data-contract tests. `backend/requirements.txt:L1-L9`; `.github/workflows/baseballos-sync.yml:L30-L42`; `backend/services/sync.py:L6490-L6505`
- **Partially implemented / evolving:** game-driven ingestion exists and is authoritative in the daily critical lane, while the postgame integration is explicitly observation-only because two writing paths cannot yet safely share that cycle; composed reads are persisted but their registered production classification remains internal-only. `backend/services/sync.py:L6710-L6759`; `backend/services/sync.py:L6108-L6158`; `backend/tests/test_composed_read_contract.py:L186-L207`
- **Not present as current architecture:** no Kafka, Spark, Airflow, dbt, warehouse, or distributed streaming layer is used by the implemented pipeline. Scheduling is GitHub Actions cron/manual dispatch plus Python runners; storage is the application PostgreSQL database. `.github/workflows/baseballos-sync.yml:L30-L44`; `backend/requirements.txt:L1-L9`

## 2. 15s / 60s / 3m BaseballOS Explanation

### 15-second version

“BaseballOS is an MLB bullpen intelligence platform. I built scheduled Python pipelines that ingest MLB API data into PostgreSQL, preserve canonical game, roster, and transaction history, derive workload and readiness facts, and publish versioned read models only when data-quality gates pass.” `backend/services/mlb_api.py:L467-L511`; `backend/services/mlb_api.py:L515-L634`; `backend/services/sync.py:L6490-L6503`; `backend/services/sync.py:L6885-L6956`

### 60-second version

“The operational source is the MLB Stats API. A resilient client fetches schedules, rosters, player game logs, transactions, and boxscores with timeouts and bounded retries. I normalize those responses into canonical PostgreSQL facts such as `pitchers`, `game_logs`, `scheduled_games`, `roster_status_snapshots`, and `player_transactions`. Natural keys and constraints enforce each table’s grain—for example, one pitching line per pitcher per MLB game.

“The daily pipeline refreshes roster authority and transactions, performs game-level incremental ingestion, applies safe source corrections, recalculates fatigue against one canonical reference date, and builds a dashboard snapshot. Postgame jobs sweep only newly final or retryable games. Publication is gated separately from calculation: incomplete finality, roster authority, or appearance coverage leaves the new snapshot pending and keeps the previous trusted snapshot serving. Sync runs, dead letters, source windows, correction counts, and immutable artifacts give me traceability and replayability.” `backend/services/sync.py:L6545-L6632`; `backend/services/sync.py:L6696-L6873`; `backend/services/dashboard_snapshot.py:L328-L371`; `backend/models/sync_run.py:L5-L46`; `backend/models/sync_failure.py:L5-L40`

### 3-minute version

“I think about BaseballOS as five data layers.

“First is **source acquisition**. `MLBApiClient` wraps the MLB Stats API and distinguishes a successful empty response from a failed fetch. Transient connection failures, timeouts, 429s, and 5xx responses retry with capped backoff; non-transient 4xx responses do not. Calls and retries are measured per endpoint. `backend/services/mlb_api.py:L103-L174`; `backend/services/mlb_api.py:L180-L303`

“Second is **canonical relational storage**. `Pitcher` is current identity keyed by unique MLB ID. `GameLog` is an appearance fact keyed by pitcher plus MLB game; it stores outs as the integer authority and constrains decimal innings to equal outs divided by three. Schedule rows use team plus game because one MLB game produces a home-team and away-team perspective. Roster snapshots use pitcher plus represented date. Transactions use a deterministic source ID or fallback digest. `backend/models/pitcher.py:L4-L34`; `backend/models/game_log.py:L40-L116`; `backend/models/scheduled_game.py:L5-L46`; `backend/models/player_transaction.py:L45-L121`

“Third is **normalization and reconciliation**. MLB fields are parsed into typed facts while missing values remain null. The writer produces a plan—insert, unchanged, correction, or blocked—then applies only approved changes. A pitcher’s current team is deliberately different from the team represented in a historical appearance. If official authorities disagree, the appearance remains unattributed rather than guessing. `backend/services/sync.py:L506-L566`; `backend/services/sync.py:L1123-L1259`; `backend/models/game_log.py:L135-L149`

“Fourth is **incremental derivation**. A durable game work item is the checkpoint for daily critical ingestion; postgame markers avoid refetching completed work. Fatigue facts are append-only score observations calculated over bounded windows against one canonical availability date. Transactions and roster evidence are bounded and batch-prefetched. `backend/models/game_ingestion_work_item.py:L5-L22`; `backend/services/sync.py:L415-L453`; `backend/services/sync.py:L4533-L4591`; `backend/services/transaction_ingestion.py:L281-L344`

“Fifth is **trusted publication**. The candidate dashboard is stored first as pending. It publishes only if slate and appearance-ledger gates pass. Publishing rotates the serving pointer but retains prior rows and their `published_at` proof for historical comparisons. Published share artifacts capture evidence by value and are immutable, so old output remains reproducible after upstream corrections. `backend/services/dashboard_snapshot.py:L263-L325`; `backend/services/dashboard_snapshot.py:L328-L429`; `backend/services/dashboard_snapshot.py:L928-L965`; `backend/models/share_artifact.py:L318-L352`

“The design is deliberately scheduled and incremental rather than streaming. MLB’s source cadence and the product’s daily/postgame needs do not justify Kafka or Spark today. The scaling work I would prioritize is set-based fatigue recomputation, a dedicated team dimension, partition/retention strategy for growing fact and snapshot tables, and stronger workload orchestration if the number of independent pipelines grows.” `backend/services/sync.py:L4557-L4591`; `backend/models/scheduled_game.py:L13-L15`

## 3. End-to-End Data Flow

```text
MLB Stats API (statsapi.mlb.com/api/v1)
    |
    +--> /teams + /teams/{id}/roster
    |       -> MLBApiClient
    |       -> build_run_roster_evidence / team_assignment_sync / roster_status_sync
    |       -> pitchers current identity + roster_status_snapshots history
    |
    +--> /schedule + /game/{gamePk}/boxscore + /people/{id}/stats?stats=gameLog
    |       -> schedule_ingestion / game-driven planner / sync_recent_logs
    |       -> finality + appearance-team authority + normalized pitching values
    |       -> game_logs + game_ingestion_work_items + postgame_processed_games
    |       -> team_game_pitching_splits / completed_game_contexts
    |
    +--> /transactions + /people batch + exact-date roster endpoints
            -> transaction participant qualification / canonical pitcher acquisition
            -> deterministic transaction key + exact roster alignment
            -> player_transactions + player_transaction_sync_windows

Canonical PostgreSQL facts
    |
    +--> calculate_fatigue / recalculate_all_fatigue
    |       -> fatigue_scores
    |
    +--> evidence builders + composed reads
    |       -> evidence_objects + evidence_citations
    |       -> composed_reads + composed_read_components
    |       -> composed_read_evidence_citations
    |
    +--> dashboard snapshot builder
            -> pending dashboard_snapshots candidate
            -> slate/finality + appearance-ledger + freshness/publication gates
            -> published dashboard snapshot OR prior trusted snapshot keeps serving
            -> immutable share_artifacts with evidence captured by value
            -> Flask API read models -> BaseballOS surfaces
```

Source methods and resilience: `backend/services/mlb_api.py:L103-L174`, `backend/services/mlb_api.py:L467-L634`. Daily composition: `backend/services/sync.py:L6545-L6632`, `backend/services/sync.py:L6696-L6873`. Publication: `backend/services/sync.py:L6885-L6956`, `backend/services/dashboard_snapshot.py:L328-L429`.

### One concrete row-level flow

1. The daily lane reads a pitcher’s `/people/{id}/stats` game-log splits or a completed-game boxscore. `backend/services/mlb_api.py:L515-L530`; `backend/services/mlb_api.py:L636-L639`
2. `_ingest_game_log_split` rejects missing keys and out-of-window/non-final games; statusless splits consult durable `scheduled_games` finality. `backend/services/sync.py:L4341-L4421`
3. Appearance team is resolved from official game-side evidence, never current `Pitcher.team_id`. `backend/services/sync.py:L4423-L4442`
4. `_game_log_values_from_stats` converts innings to outs, preserves unknown nullable inputs, and builds a typed fact dictionary. `backend/services/sync.py:L506-L566`
5. The canonical writer inserts, leaves unchanged, safely corrects with provenance, or blocks/dead-letters the mutation. `backend/services/sync.py:L1123-L1259`
6. A correction marks dependent evidence families for recomputation. `backend/services/sync.py:L605-L675`
7. Fatigue is recalculated from bounded recent `GameLog` rows against the canonical reference date and inserted as a new `FatigueScore`. `backend/services/sync.py:L4533-L4591`
8. A dashboard candidate is serialized and stored pending; trust gates decide whether it becomes the single served snapshot. `backend/services/dashboard_snapshot.py:L263-L325`; `backend/services/dashboard_snapshot.py:L328-L429`

## 4. Core Relational Model

### Important production tables/models

| Model / table | Grain and purpose | Keys, constraints, indexes | Relationships and pipeline role |
|---|---|---|---|
| `Pitcher` / `pitchers` | Current canonical player/pitcher identity and current team/roster cache | PK `id`; unique non-null `mlb_id`; `(team_id, active)` index; current `team_id` nullable because identity may be known while assignment is not | One-to-many to `GameLog` and `FatigueScore`, both delete-orphan. Entry point for current identity, not historical team truth. `backend/models/pitcher.py:L4-L34` |
| `GameLog` / `game_logs` | One pitcher’s official pitching appearance in one MLB game | PK `id`; unique `(pitcher_id, mlb_game_pk)`; FK `pitcher_id -> pitchers.id`; checks for nonnegative outs, decimal-innings equivalence, 0/1/null start flag, and valid appearance-team state; indexes on pitcher/date, game PK, game type, appearance team/date | Many-to-one pitcher. Central canonical workload fact. `pitches_thrown`, hits, walks, and several context fields remain nullable so unknown is not zero. `backend/models/game_log.py:L40-L116` |
| `ScheduledGame` / `scheduled_games` | One team’s perspective on one MLB game, including future games | PK `id`; unique `(team_id, game_pk)`; indexes `(team_id, game_date)`, date, normalized state, suspended/resumed links | Two rows per MLB game; no `teams` table, so team IDs are plain integers. Provides finality and calendar authority. `backend/models/scheduled_game.py:L5-L46`; `backend/models/scheduled_game.py:L48-L81` |
| `RosterStatusSnapshot` / `roster_status_snapshots` | Historical roster/position evidence for a pitcher on a represented date | PK `id`; FK `pitcher_id -> pitchers.id`; nullable FK `sync_run_id`; unique `(pitcher_id, snapshot_date)`; indexes team/date and MLB ID/date | Many snapshots per pitcher over time. Nullable booleans preserve unknown source state. Correction metadata records later source revisions. `backend/models/roster_status_snapshot.py:L5-L40`; `backend/models/roster_status_snapshot.py:L42-L70` |
| `PlayerTransaction` / `player_transactions` | Canonical structured MLB transaction fact with participant, chronology, classification, roster alignment, and provenance | PK `id`; unique non-null `transaction_key`; nullable FK `pitcher_id` because a source participant may not yet be a canonical pitcher; FK `sync_run_id`; indexes player/date, pitcher/date, destination team/date; checks constrain classification vocabularies | Many transactions can belong to one pitcher. Exists to explain roster changes without inventing linkage when participant/team/date authority is incomplete. `backend/models/player_transaction.py:L45-L121` |
| `PlayerTransactionSyncWindow` / `player_transaction_sync_windows` | Durable audit/checkpoint for each bounded transaction extraction window | PK `id`; FK `sync_run_id`; indexes end-date/attempt and status/attempt; stores fetched/created/corrected/unchanged/failure counts | Records extraction coverage independently from transaction rows, so “no data” and “fetch failed” are distinguishable. `backend/models/player_transaction.py:L174-L209` |
| `FatigueScore` / `fatigue_scores` | Derived point-in-time pitcher workload/readiness calculation | PK `id`; FK `pitcher_id`; index `(pitcher_id, calculated_at)` | Many score versions per pitcher. No uniqueness on pitcher: history is intentional. Nullable `pitches_last_7_days` and component scores preserve incomplete inputs. `backend/models/fatigue_score.py:L4-L33` |
| `SyncRun` / `sync_runs` | Durable pipeline run, stage, outcome, freshness anchors, counts, retry pressure, and publication pointer | PK `id`; indexes start time and `(status, completed_at)` | Parent FK target for snapshots, failures, roster snapshots, transactions, and evidence. Provides observability and publication provenance. `backend/models/sync_run.py:L5-L46` |
| `SyncFailure` / `sync_failures` | Dead-letter record for one failed entity or fetch | PK `id`; nullable FK `sync_run_id`; indexes resolved and run; non-null job/entity type/timestamp | Many failures per run. Nullable run FK permits recording a failure even if run-row persistence failed. Resolution keeps historical failure rows rather than deleting them. `backend/models/sync_failure.py:L5-L40` |
| `GameIngestionWorkItem` / `game_ingestion_work_items` | Daily game-level checkpoint and completion proof | PK `id`; unique `mlb_game_pk`; indexes status/date, date, criticality/status; checks constrain states/counts and require completed rows to have exact expected/reconciled counts | One work item per game; replay updates the checkpoint instead of creating another work identity. `backend/models/game_ingestion_work_item.py:L5-L22`; `backend/models/game_ingestion_work_item.py:L81-L126` |
| `PostgameProcessedGame` / `postgame_processed_games` | Postgame lane marker with attempt count and completion/failure detail | PK `id`; unique `mlb_game_pk`; FK `sync_run_id`; indexes date, processed time, status | One marker per game. Allows cheap resweeps and bounded retries. Separate from the daily lane’s checkpoint. `backend/models/postgame_processed_game.py:L5-L42` |
| `TeamGamePitchingSplit` / `team_game_pitching_splits` | Derived team-game starter/bullpen split and calendar context | PK `id`; unique `(team_id, mlb_game_pk)`; nullable FK `starter_pitcher_id`; indexes team/date, game, completeness states; constrained known/partial/unknown vocabularies | One team-game derived fact. Keeps starter, bullpen, and calendar completeness explicit. `backend/models/team_game_pitching_split.py:L5-L89`; `backend/models/team_game_pitching_split.py:L91-L114` |
| `DashboardSnapshot` / `dashboard_snapshots` | Persisted read-optimized dashboard payload and serving/publication state | PK `id`; nullable FK `sync_run_id`; check that published implies run provenance; indexes type/status/time, run, and serving lookup | Append-oriented snapshot history. Exactly one row is selected for serving; older trusted rows retain durable publication proof. `backend/models/dashboard_snapshot.py:L5-L39` |
| `EvidenceObject` / `evidence_objects` | Versioned derived claim with typed inputs, rule/version/hash, completeness, provenance, and recompute state | PK `id`; unique `evidence_key`; FK `sync_run_id`; self-FK `superseded_by_evidence_id`; indexes rule/version, subject/date, posture, recompute state | One-to-many `EvidenceCitation` with `selectin` loading. Makes derivation inspectable and correctable. `backend/models/evidence_contract.py:L5-L68`; `backend/models/evidence_contract.py:L70-L124` |
| `ComposedRead`, `ComposedReadComponent`, `ComposedReadEvidenceCitation` | Read model composed from multiple evidence objects | PKs on all; `read_key` unique; FKs component -> read and citation -> component/evidence; subject/date and recompute indexes | Read-to-component is one-to-many. Component-to-evidence is **many-to-many through the citation association table**: a component can cite many evidence objects and one evidence object can support many components. `selectin` prevents per-child lazy-load chatter. `backend/models/composed_read.py:L51-L124`; `backend/models/composed_read.py:L159-L190`; `backend/models/composed_read.py:L209-L238` |
| `ShareArtifact`, child evidence/assets, and relations | Immutable published output, evidence captured by value, and supersession graph | Unique `public_id`; equivalence/lifecycle indexes; child FKs; relation has two FKs to `share_artifacts`, unique `(source, target, relation_type)`, and no-self check | One-to-many evidence/assets; directed self-referential many-to-many graph through `ShareArtifactRelation`. Published substance cannot be updated/deleted. `backend/models/share_artifact.py:L168-L270`; `backend/models/share_artifact.py:L318-L352`; `backend/models/share_artifact.py:L425-L469` |

### Strongest relational-design examples

No core production relationship was identified as a strict one-to-one. The dominant shapes are one-to-many facts/history and explicit many-to-many association tables; do not invent a one-to-one example for the interview. `backend/models/pitcher.py:L23-L34`; `backend/models/composed_read.py:L209-L238`

1. **Appearance natural key and temporal ownership.** `(pitcher_id, mlb_game_pk)` matches baseball grain even for doubleheaders, while `appearance_team_id` stores historical ownership separately from mutable current identity. This prevents duplicates and avoids rewriting a traded pitcher’s past. `backend/models/game_log.py:L40-L65`; `backend/models/game_log.py:L135-L149`; `backend/tests/test_appearance_team_authority.py:L575-L644`
2. **Many-to-many evidence lineage.** `composed_read_evidence_citations` is a real junction table with FKs to both sides plus relationship loading. It exists because evidence is reusable: several read components can cite the same fact, and one component may require several facts. `backend/models/composed_read.py:L186-L238`; `backend/tests/test_composed_read_contract.py:L210-L277`
3. **Completion as a database invariant.** A game work item cannot be labeled `completed` unless it has a timestamp, a positive expected count, and exact reconciliation. This makes the checkpoint a proof, not an optimistic status string. `backend/models/game_ingestion_work_item.py:L111-L124`
4. **Immutable publication graph.** `ShareArtifactRelation` is a self-referential association table for `supersedes`, `derived_from`, and `variant_of`, with uniqueness and no-self constraints. This models history as new nodes and edges rather than destructive updates. `backend/models/share_artifact.py:L425-L469`

### Important caveat: no team dimension table

The repository deliberately has **no `teams` table**. `team_id` is an MLB integer repeated across facts and validated through source/product logic rather than a database FK. Do not claim referential integrity for teams. Honest framing: “I chose source IDs directly in the current operational model, but at larger scale I would add a conformed team dimension with season/organization history and FKs where the temporal semantics allow it.” `backend/models/scheduled_game.py:L13-L15`; `backend/models/game_log.py:L135-L140`; `backend/models/user.py:L51-L73`

## 5. Strongest SQL Examples

### 1. Latest derived score per pitcher using aggregate subquery + joins

- **Problem:** return exactly one latest `FatigueScore` per pitcher without loading every historical score and deduplicating in Python.
- **Pattern:** subquery groups by pitcher and selects `MAX(calculated_at)`; join back on pitcher and timestamp; join `Pitcher`; then filter/order/limit.
- **Why appropriate:** keeps latest-row selection set-based and supports team/risk filters on the joined canonical identity.
- **Correctness:** the optional `calculated_at <= served snapshot generation` boundary prevents a public response from mixing newer derived scores with an older published snapshot.
- **Evidence:** `backend/services/availability_snapshot.py:L120-L165`

### 2. Latest roster snapshot per pitcher using a window function

- **Problem:** fetch each pitcher’s authoritative latest roster row in one query with deterministic tie-breaking.
- **Pattern:** `ROW_NUMBER() OVER (PARTITION BY pitcher_id ORDER BY snapshot_date DESC, updated_at DESC, id DESC)`, then select rank 1 IDs.
- **Why appropriate:** avoids one query per pitcher and makes batch and single-pitcher recency semantics identical.
- **Correctness:** the explicit secondary/tertiary sort prevents nondeterminism when a date has corrected rows/timestamps.
- **Evidence:** `backend/services/roster_status_sync.py:L724-L774`

### 3. Fresh active population with `GROUP BY` + `HAVING`

- **Problem:** a pitcher should count as current only when their **most recent** appearance is within the active window.
- **Pattern:** group `game_logs` by pitcher and `HAVING MAX(game_date) >= cutoff`.
- **Why appropriate:** filtering individual rows before grouping could admit a pitcher whose authoritative latest-state logic is unclear; the aggregate expresses the intended entity-level rule.
- **Correctness:** old local data is not presented as current availability.
- **Evidence:** `backend/api/bullpen.py:L219-L244`

### 4. Conflict-safe bulk identity acquisition with PostgreSQL upsert semantics

- **Problem:** several transaction rows or concurrent work can discover the same missing pitcher.
- **Pattern:** one multi-row `INSERT ... ON CONFLICT DO NOTHING (mlb_id)`, flush, then one bounded `WHERE mlb_id IN (...)` refresh.
- **Why appropriate:** the database unique key arbitrates the race; no per-person query/commit loop is required.
- **Correctness:** repeated syncs and concurrent insert winners converge on one canonical pitcher.
- **Evidence:** `backend/services/canonical_transaction_pitcher_acquisition.py:L87-L133`

### 5. Bounded transaction dedup/upsert with correction provenance

- **Problem:** MLB transaction endpoints repeat records and later revise fields.
- **Pattern:** deterministic `transaction_key`; select existing by key; insert, field-by-field update, or unchanged; flush inside the caller’s transaction.
- **Why appropriate:** preserves a stable fact identity while permitting governed source corrections.
- **Correctness:** duplicates do not multiply; a changed source row increments correction metadata and invalidates affected evidence.
- **Evidence:** `backend/services/transaction_ingestion.py:L627-L669`; `backend/services/transaction_ingestion.py:L984-L999`

### 6. `EXISTS` for unresolved dead-letter deduplication

- **Problem:** recurring source failures should not create an unbounded duplicate dead letter for the same unresolved entity.
- **Pattern:** SQLAlchemy `EXISTS` with entity type/ref, job, and `resolved = false`.
- **Why appropriate:** asks the database only for existence, not a full row payload.
- **Correctness:** preserves one actionable unresolved condition while historical resolution remains queryable; query errors roll back and fail safely.
- **Evidence:** `backend/services/transaction_ingestion.py:L913-L929`

### 7. Set-based PostgreSQL repair with CTE + `CASE` + `UPDATE ... FROM`

- **Problem:** convert legacy baseball decimal innings (`1.0`, `1.1`, `1.2`) to canonical integer outs across many rows.
- **Pattern:** CTE classifies each row with `CASE`; one `UPDATE ... FROM` writes outs and derived decimal innings only when values differ (`IS DISTINCT FROM`).
- **Why appropriate:** a set-based repair is safer and faster than ORM row-by-row writes for a bulk backfill.
- **Correctness:** unrecognized decimals produce `NULL` in the CTE and are excluded; unchanged rows are not rewritten; commit is explicit.
- **Evidence:** `backend/services/innings_backfill.py:L172-L208`

### 8. Bounded bulk window load instead of N per-pitcher queries

- **Problem:** availability needs each pitcher’s recent logs, but evaluation dates may differ.
- **Pattern:** compute the earliest/latest needed dates, issue one `pitcher_id IN (...) AND game_date BETWEEN ...` query, order by pitcher/date, then group and apply exact per-pitcher windows in memory.
- **Why appropriate:** limits transferred rows while removing an N+1 query pattern.
- **Correctness:** the second exact window check prevents the coarse shared range from adding an out-of-window appearance to a pitcher.
- **Evidence:** `backend/services/availability_snapshot.py:L209-L245`

### 9. Counts and `COUNT(DISTINCT ...)` as observability contracts

- **Problem:** distinguish “no game-log facts,” “facts exist but no scores,” and filtered response emptiness.
- **Pattern:** `COUNT(game_logs.id)` and `COUNT(DISTINCT fatigue_scores.pitcher_id)` plus latest date.
- **Why appropriate:** entity counts and row counts answer different operational questions.
- **Correctness:** API metadata explains empty/degraded results rather than implying zero workload.
- **Evidence:** `backend/api/bullpen.py:L309-L334`

### 10. Bulk update during atomic snapshot rotation

- **Problem:** publish one new dashboard snapshot while ensuring there is only one active serving selector and sync pointers remain coherent.
- **Pattern:** select prior published IDs, bulk-update older `is_published` flags, mark candidate ready/published, bulk-update affected `SyncRun` pointers, then commit as one transaction.
- **Why appropriate:** serving selection and provenance move together.
- **Correctness:** a pre-commit failure rolls back the rotation; after commit, older rows still retain `status=ready` and `published_at` for historical comparison.
- **Evidence:** `backend/services/dashboard_snapshot.py:L373-L429`; `backend/services/dashboard_snapshot.py:L928-L965`

## 6. SQLAlchemy / Database Usage

### What is implemented

- Flask-SQLAlchemy models define FKs, unique/check constraints, indexes, relationships, cascades, and loading strategy; Alembic manages schema evolution. `backend/requirements.txt:L1-L9`; `backend/models/composed_read.py:L51-L124`
- Query construction uses aggregates, subqueries, joins/outer joins, `HAVING`, `IN`, `EXISTS`, window functions, ordering, limits, and bulk updates. `backend/api/bullpen.py:L225-L237`; `backend/services/availability_snapshot.py:L120-L165`; `backend/services/roster_status_sync.py:L737-L774`; `backend/services/transaction_ingestion.py:L913-L929`
- Session boundaries are deliberate: `flush()` obtains IDs/validates constraints without committing; larger callers own the transaction. Transaction ingestion is an example: individual upserts flush, and the bounded window commits once. `backend/services/transaction_ingestion.py:L627-L669`; `backend/services/transaction_ingestion.py:L448-L459`
- Snapshot publication deliberately supports `commit=False` so the completed `SyncRun`, candidate snapshot, serving rotation, and run pointer commit together; any exception rolls back and records a failed stage. `backend/services/sync.py:L5529-L5609`
- Per-game postgame writes commit before optional derived context. A context failure cannot undo canonical game logs; an individual game exception rolls back that game, records a dead letter, and commits the failure record. `backend/services/sync.py:L5927-L6037`
- PostgreSQL advisory locks prevent overlapping public writers; the lock is connection-scoped and always released. Non-Postgres tests/local execution use an in-process fallback. `backend/services/sync_metadata.py:L292-L412`
- `selectin` eager loading is used for composed-read components/citations and artifact children where serialized graphs would otherwise create N+1 reads. `backend/models/composed_read.py:L119-L124`; `backend/models/composed_read.py:L186-L190`; `backend/models/composed_read.py:L238-L238`; `backend/models/share_artifact.py:L244-L270`
- ORM events enforce immutable artifact lifecycle rules at flush time. `backend/models/share_artifact.py:L507-L568`

### “I used the ORM, but the problem was relational” examples

1. The ORM call `.filter_by(pitcher_id=..., mlb_game_pk=...)` is only safe because the schema declares the same composite natural key unique. `backend/models/game_log.py:L40-L46`; `backend/services/sync.py:L1138-L1142`
2. The roster “latest row” query requires understanding partitioned ordering and deterministic ties even though SQLAlchemy renders the SQL. `backend/services/roster_status_sync.py:L737-L774`
3. The composed-read citation model is a junction table with two FKs; `relationship()` does not choose the many-to-many grain or lineage semantics. `backend/models/composed_read.py:L209-L238`
4. Snapshot publishing is a multi-table transaction and serving-pointer rotation; ORM method calls do not remove the need to reason about atomicity and rollback. `backend/services/dashboard_snapshot.py:L373-L429`; `backend/services/sync.py:L5529-L5609`
5. `ON CONFLICT DO NOTHING` uses the database’s unique `mlb_id` to settle concurrent identity acquisition. The ORM is not the integrity boundary. `backend/models/pitcher.py:L10-L12`; `backend/services/canonical_transaction_pitcher_acquisition.py:L110-L127`

### Honest ORM caveat

Much production SQL is generated through SQLAlchemy rather than handwritten SQL. That is not lack of SQL reasoning: the repository uses real grouping, joins, window functions, subqueries, transactions, and Postgres-specific conflict handling. But say, “I am strongest at relational reasoning and can read/write practical SQL; I use the ORM for maintainability and drop to set-based/raw SQL when a migration or performance problem warrants it.” The innings backfill is the clearest raw-SQL example. `backend/services/innings_backfill.py:L172-L208`

## 7. Ingestion and Transformation Pipelines

### Daily / morning public sync — implemented and scheduled

- **Trigger:** `0 10 * * *` UTC (about 6 AM ET in daylight time); runner calls `run_daily_sync.py --days-back 7 --source github_actions --public-only`. `.github/workflows/baseballos-sync.yml:L30-L42`; `.github/workflows/baseballos-sync.yml:L109-L140`; `.github/workflows/baseballos-sync.yml:L177-L200`
- **Extract:** official roster views are fetched once per run and reused for team assignment and roster status; bounded transactions; schedule/finality; game-driven appearance ingestion; legacy per-pitcher game-log repair inside remaining budget. `backend/services/sync.py:L6561-L6615`; `backend/services/sync.py:L6616-L6686`; `backend/services/sync.py:L6710-L6759`
- **Transform/load:** roster facts and exact-date snapshots, normalized transaction rows, schedule/game facts, typed pitching values, safe correction plans, and game-level completion checkpoints. `backend/services/transaction_ingestion.py:L281-L415`; `backend/services/sync.py:L4341-L4489`
- **Derive:** all active pitchers are recalculated against one canonical availability reference date; score rows are appended. `backend/services/sync.py:L4533-L4591`
- **Publish:** compute publication-critical completeness, atomically finish the run and publish/withhold a dashboard snapshot, then run optional internal enrichment after publication. `backend/services/sync.py:L6885-L7019`
- **Failure boundary:** records can dead-letter and produce `partial`; critical or unknown-authority gaps withhold. A fatal stage records `failed_stage`. `backend/services/sync.py:L6885-L6956`; `backend/services/sync.py:L7023-L7052`

### Morning schedule-only correction — implemented and scheduled

- **Trigger:** `0 14 * * *` UTC.
- **Action:** `refresh_slate_schedule.py --source github_actions_morning` performs the rolling-window schedule upsert without a full data refresh.
- **Purpose:** correct time, date, doubleheader, and status changes cheaply after the daily baseline.
- **Evidence:** `.github/workflows/baseballos-sync.yml:L35-L38`; `.github/workflows/baseballos-sync.yml:L234-L251`

### Tonight / pregame refresh — implemented as a daily follow-on, not a separate cron

After the 10:00 UTC daily sync, the same workflow runs `run_tonight_refresh.py --source github_actions` to refresh the schedule and warm the Tonight read path. It has its own command and internal schedule/warm timeouts, but it is conditional on the daily trigger or manual daily mode; it is not an independent scheduled pipeline. `.github/workflows/baseballos-sync.yml:L202-L232`

### Postgame refresh — implemented and scheduled

- **Trigger:** `0 2,4,6 * * *` UTC (roughly 10 PM, midnight, 2 AM ET during daylight time). `.github/workflows/baseballos-sync.yml:L39-L42`
- **Runner:** `run_postgame_refresh.py --source github_actions --public-only`, with a 20-minute shell timeout. `.github/workflows/baseballos-sync.yml:L253-L297`
- **Extract/increment:** sweep primary and trailing slate dates oldest first; select completed games that lack a fully processed marker or have retryable incomplete markers; fetch only those boxscores. `backend/services/sync.py:L5763-L5781`; `backend/services/sync.py:L5894-L5919`
- **Load/failure isolation:** each game commits independently; derived context runs after that commit; failures roll back only the game attempt and become dead letters. `backend/services/sync.py:L5927-L6037`
- **Derive/publish:** changed logs trigger fatigue recalculation and exact-date roster-authority preparation. Per-team progressive artifacts can publish after a fully processed game; the league snapshot still follows league-wide gates. `backend/services/sync.py:L6160-L6279`
- **No-change behavior:** if no canonical logs change, expensive recalculation and replacement snapshot work are skipped. `backend/services/sync.py:L6160-L6261`

### Transaction ingestion — implemented in daily sync

- Bounded default window: `end_date - TRANSACTION_SYNC_WINDOW_DAYS` through `end_date`. `backend/services/transaction_ingestion.py:L223-L239`
- `/transactions` output is normalized into typed fields with query-window provenance. `backend/services/mlb_api.py:L599-L634`
- Participants are prefetched, batch-qualified through `/people`, conflict-safely acquired as canonical pitchers when appropriate, and aligned to exact-date roster evidence. `backend/services/transaction_ingestion.py:L281-L344`
- Each source row becomes ignored non-player context, a durable failure, or an idempotent insert/correction/unchanged fact. The sync window records coverage and counts. `backend/services/transaction_ingestion.py:L345-L459`

### Intraday transaction-roster repair — implemented, but manual-only/dormant

- The workflow has **no cron**; only `workflow_dispatch`. It invokes the preserved exact-date repair flag and shares the public sync concurrency group. `.github/workflows/baseballos-intraday-repair.yml:L1-L17`; `.github/workflows/baseballos-intraday-repair.yml:L39-L70`
- Candidate selection is restricted to the latest transaction sync window and transactions whose missing exact-date roster snapshot is the repairable blocker. It does not use nearest-date/current-team fallback. `backend/services/intraday_transaction_roster_repair.py:L1-L7`; `backend/services/intraday_transaction_roster_repair.py:L32-L82`
- Exact team/date pairs are deduplicated, roster endpoints are fetched in a bounded batch, snapshots are persisted only on unambiguous source matches, and transaction alignment is recalculated from the exact snapshot. `backend/services/intraday_transaction_roster_repair.py:L91-L198`
- **Do not say it runs intraday automatically in the current season.** The implementation is preserved for controlled manual use and requires a future re-audit before scheduling. `.github/workflows/baseballos-intraday-repair.yml:L1-L11`

### Internal enrichment/read composition — implemented but post-public and partly internal-only

Workload/evidence builders, composed reads, reconciliation audit, and backtest refresh run after the public snapshot has already committed, so an internal enrichment failure cannot revoke a valid public publication. `backend/services/sync.py:L6966-L7019`. The registered composed-read types are still classified internal-only, so do not describe them as a fully public semantic layer. `backend/tests/test_composed_read_contract.py:L186-L207`

## 8. Incremental Processing

| Mechanism | Evidence | Why incremental instead of full rescan |
|---|---|---|
| Game-level daily checkpoint | One `GameIngestionWorkItem` per game stores planned/in-progress/completed/retry state and source revision. `backend/models/game_ingestion_work_item.py:L5-L22` | A run resumes unresolved/corrected games instead of replaying a season; unit of completeness matches the source game/appearance set. |
| Postgame processed marker | Fully processed markers are excluded; incomplete markers retry only below the limit. `backend/services/sync.py:L349-L371`; `backend/services/sync.py:L415-L453` | Overnight sweeps become cheap and self-heal after interruption without refetching every completed game. |
| Bounded date windows | Daily game logs use a cutoff; transactions use a bounded source window; availability uses 4/14-day windows. `backend/services/sync.py:L3707-L3759`; `backend/services/transaction_ingestion.py:L223-L239`; `backend/services/availability_snapshot.py:L195-L245` | Product state depends on recent workload; bounded reads control API/database cost while separate repair lanes handle history. |
| Changed-row classification | Game and transaction writers return inserted/corrected/unchanged/blocked. `backend/services/sync.py:L1123-L1259`; `backend/services/transaction_ingestion.py:L627-L669` | Avoids rewriting identical facts, preserves correction provenance, and makes reruns measurable. |
| Affected-game recomputation | Changed GameLog rows collect affected game PKs; derived team-game splits recompute only those games. `backend/services/sync.py:L4049-L4067`; `backend/services/sync.py:L4162-L4169` | Prevents a league/season-wide derived rebuild after a small source correction. |
| Exact team/date batching | Intraday transaction repair deduplicates requested `(team, transaction_date)` pairs and excludes old/currently unrepairable rows. `backend/services/intraday_transaction_roster_repair.py:L32-L82`; `backend/tests/test_intraday_transaction_roster_repair.py:L211-L248` | A precise repair has lower source cost and lower blast radius than refetching all rosters or rewriting all transactions. |
| Cached per-run source evidence | Official roster evidence is fetched once and shared; boxscores/finality and existing GameLogs are cached/prefetched. `backend/services/sync.py:L6561-L6567`; `backend/services/sync.py:L3831-L3865` | Avoids repeated upstream calls and dominant per-split remote DB lookups while retaining fallback correctness. |
| Trusted adjacent snapshot lookup | Prior trusted snapshot query is date-bounded and ordered, not a rebuild of history. `backend/services/dashboard_snapshot.py:L928-L995` | Historical comparison reads durable versions rather than recomputing yesterday with today’s source state. |

### Tradeoff framing

“Incremental processing is appropriate because MLB data changes in bounded units—games, roster dates, and transaction windows—and most runs see a small delta. I still retain explicit backfill/reconciliation paths because upstream corrections can arrive late. The cost is more checkpoint and correction logic; the benefit is lower source load, shorter runs, and a smaller failure blast radius.” `backend/services/sync.py:L5769-L5781`; `backend/models/game_ingestion_work_item.py:L5-L22`

## 9. Data Quality / Correctness

### Strongest correctness rules

1. **Missing versus zero:** source parsers return `None` for omitted/malformed pitch, hit, and walk counts; an explicit zero remains zero. Derived fatigue preserves the distinction in storage and APIs. `backend/services/sync.py:L463-L470`; `backend/services/sync.py:L532-L545`; `backend/tests/test_fatigue_pitch_null_persistence.py:L123-L188`
2. **Duplicate appearances:** both application upsert logic and the database unique `(pitcher_id, mlb_game_pk)` enforce one row. `backend/models/game_log.py:L40-L46`; `backend/tests/test_game_driven_ingestion.py:L135-L205`
3. **Canonical innings:** integer outs are authoritative; decimal innings is derived and database-constrained, avoiding baseball-decimal arithmetic errors (`.1` means one out, not one tenth). `backend/models/game_log.py:L47-L54`; `backend/services/innings_backfill.py:L172-L208`
4. **Historical team correctness:** appearance team comes from official game-side evidence, never current pitcher team. Conflict/unresolved stores no fake team. `backend/models/game_log.py:L66-L78`; `backend/models/game_log.py:L135-L149`; `backend/tests/test_appearance_team_authority.py:L607-L644`
5. **Game finality:** statusless game-log splits resolve against the schedule ledger; unknown finality creates a dead letter rather than silently dropping or ingesting the appearance. `backend/services/sync.py:L4389-L4421`
6. **Transaction chronology and identity:** transaction rows retain source query bounds, transaction/effective/resolution/retroactive dates, participant authority, and exact-date roster alignment. Unknown categories remain explicit. `backend/models/player_transaction.py:L80-L125`
7. **Exact roster authority:** repair requires an exact transaction date and matching MLB organization. Source omission, endpoint conflict, wrong-team evidence, and old windows stay blocked. `backend/tests/test_intraday_transaction_roster_repair.py:L251-L344`
8. **Safe corrections only:** the reconciliation planner can block incomplete/unsafe updates; blocked attempts become dead letters. Approved corrections update provenance and invalidate every registered directly dependent evidence family. `backend/services/sync.py:L1123-L1259`; `backend/services/sync.py:L605-L675`
9. **Publication fails closed:** incomplete slate, appearance ledger, freshness, version, or provenance does not replace the serving snapshot. `backend/services/dashboard_snapshot.py:L222-L254`; `backend/services/dashboard_snapshot.py:L328-L371`
10. **Partial data remains visible:** a bad entity does not abort a whole batch, but the run records counts/status and the failure is durable/queryable/resolvable. `backend/models/sync_failure.py:L5-L40`; `backend/services/sync.py:L3733-L3737`; `backend/services/sync.py:L3952-L3977`

### How BaseballOS prevents a wrong downstream claim

The governing pattern is: **classify source authority -> preserve uncertainty -> store canonical fact/provenance -> derive only from qualified facts -> publish only if the required evidence graph is complete**. When the system cannot prove a team, finality state, roster match, required input, or publication-critical classification, the result is `unknown`, `conflict`, `partial`, `pending`, or withheld—not a guessed value. `backend/models/evidence_contract.py:L36-L68`; `backend/services/publication_criticality.py:L56-L114`; `backend/services/dashboard_snapshot.py:L222-L254`

## 10. Historical Data / Reproducibility

### Why snapshots exist

Current tables answer “what does the system believe now?” They cannot reproduce “what did the product publish yesterday, using which inputs and method version?” BaseballOS therefore separates:

- current identity/cache (`pitchers`),
- event facts with correction provenance (`game_logs`, `player_transactions`),
- date-grained roster history (`roster_status_snapshots`),
- append-oriented derived score observations (`fatigue_scores`),
- read-optimized dashboard publications (`dashboard_snapshots`), and
- immutable public artifacts with evidence captured by value (`share_artifacts`, `share_artifact_evidence`).

Evidence: `backend/models/pitcher.py:L10-L30`; `backend/models/game_log.py:L129-L149`; `backend/models/roster_status_snapshot.py:L42-L70`; `backend/models/fatigue_score.py:L12-L33`; `backend/models/dashboard_snapshot.py:L20-L39`; `backend/models/share_artifact.py:L195-L239`; `backend/models/share_artifact.py:L318-L352`.

### Reproducibility mechanics

- Dashboard rows store payload version, `data_through`, availability reference date, generation time, source, publication timestamp, and sync-run provenance. `backend/models/dashboard_snapshot.py:L20-L39`
- Publishing rotates `is_published` (the serving selector) but keeps older ready rows and their `published_at` proof. Historical comparison explicitly queries prior published dates without requiring the row still be actively served. `backend/services/dashboard_snapshot.py:L373-L429`; `backend/services/dashboard_snapshot.py:L928-L965`
- Published artifacts freeze source snapshot/run, schema/render version, payload, trust metadata, equivalence key, integrity hash, timestamps, and evidence snapshots. `backend/models/share_artifact.py:L195-L239`; `backend/models/share_artifact.py:L318-L352`
- Source corrections create a new evidence revision/checkpoint rather than rewriting prior progressive publication authority. `backend/models/team_progressive_publication.py:L59-L72`; `backend/models/team_progressive_publication.py:L98-L105`
- ORM lifecycle events reject mutation/deletion of published substance. `backend/models/share_artifact.py:L507-L568`

### Current-state-only failure mode this avoids

If yesterday’s dashboard were rebuilt from today’s corrected roster and current `Pitcher.team_id`, a traded player or late source correction could change the historical story. The implementation instead freezes team-at-appearance on the event, keeps prior trusted snapshot payloads, and captures artifact evidence by value. `backend/models/game_log.py:L135-L149`; `backend/services/dashboard_snapshot.py:L928-L965`; `backend/models/share_artifact.py:L318-L352`

## 11. Scheduling / Orchestration

### Actual current schedules

| Workflow | Trigger | Responsibility / command | Failure behavior |
|---|---|---|---|
| `.github/workflows/baseballos-sync.yml` | Daily `0 10 * * *` UTC | `python backend/scripts/run_daily_sync.py --days-back 7 --source github_actions --public-only`; canonical morning ingestion, derivation, snapshot publish/withhold. `.github/workflows/baseballos-sync.yml:L30-L42`; `.github/workflows/baseballos-sync.yml:L109-L200` | Nonzero/timeout fails the step; downstream audit/cache proof is designed to expose publication deficits. Public writer uses durable stages and dead letters. `.github/workflows/baseballos-sync.yml:L177-L200`; `backend/services/sync.py:L7023-L7052` |
| Same workflow | Daily `0 14 * * *` UTC | `refresh_slate_schedule.py --source github_actions_morning`; schedule-only rolling-window correction. `.github/workflows/baseballos-sync.yml:L35-L38`; `.github/workflows/baseballos-sync.yml:L234-L251` | Five-minute timeout; no full sync or snapshot publication is implied. |
| Same workflow | Daily `0 2,4,6 * * *` UTC | `run_postgame_refresh.py --source github_actions --public-only`; newly completed/retryable games, fatigue/public-state refresh, progressive team publication, league snapshot gates. `.github/workflows/baseballos-sync.yml:L39-L42`; `.github/workflows/baseballos-sync.yml:L253-L297` | Per-game rollback/dead letter; incomplete markers retry within limits; a replacement snapshot may be withheld while earlier publication remains. `backend/services/sync.py:L5927-L6037`; `backend/services/sync.py:L6283-L6312` |
| Same workflow | Manual `workflow_dispatch` | `daily`, `postgame`, explicit-date `backfill`, or read-only `intraday` audit. Backfill requires a concrete date and is never scheduled. `.github/workflows/baseballos-sync.yml:L43-L66` | Shared concurrency group queues rather than cancels an active writer. `.github/workflows/baseballos-sync.yml:L68-L71` |

### Manual-only workflows—not schedules

- `baseballos-intraday-repair.yml`: manual-only preserved repair, no cron. It shares `baseballos-sync` concurrency and fails on withheld/incomplete repair. `.github/workflows/baseballos-intraday-repair.yml:L1-L17`; `.github/workflows/baseballos-intraday-repair.yml:L39-L70`
- `baseballos-production-maintenance.yml`: manual-only migration, ledger backfill, snapshot audit, or appearance-team audit; requires exact confirmation phrases and production secrets. `.github/workflows/baseballos-production-maintenance.yml:L1-L18`; `.github/workflows/baseballos-production-maintenance.yml:L60-L111`
- Numerous other workflow files are explicit diagnostics/backfills/proofs. Do not describe them as part of normal production cadence merely because they exist. The current automatic cadence is the cron block in `baseballos-sync.yml`. `.github/workflows/baseballos-sync.yml:L30-L42`

### Orchestration design explanation

The workflow uses one concurrency key (`baseballos-sync`) for daily, postgame, backfill, and schedule work so two public writers do not overlap at the Actions layer; the Python layer independently uses a PostgreSQL advisory lock. This is defense in depth across scheduler and database boundaries. `.github/workflows/baseballos-sync.yml:L68-L71`; `backend/services/sync_metadata.py:L330-L412`

## 12. Reliability / Failure Recovery

### Reliability mechanisms

- **Upstream retries:** timeouts, connection failures, 429, and 5xx retry with capped exponential backoff/jitter; 4xx and malformed JSON fail immediately as typed errors. `backend/services/mlb_api.py:L167-L303`
- **Dead letters:** failures store entity type/ref, retry payload, error, run, job, timestamps, and resolution status. `backend/models/sync_failure.py:L5-L40`
- **Partial progress:** per-entity and per-game failures do not erase successful work; run status becomes partial/failed according to scope. `backend/services/sync.py:L3733-L3737`; `backend/services/sync.py:L5927-L6037`
- **Atomic publication:** run completion and snapshot rotation commit together; rollback marks the dashboard stage failed. `backend/services/sync.py:L5529-L5609`
- **Stale serving:** failed recalculation/snapshot build leaves the previous trusted snapshot serving and exposes degradation reason codes. `backend/tests/test_dashboard_snapshot.py:L1314-L1407`
- **Writer exclusion:** Actions concurrency plus Postgres advisory locks prevent overlapping public mutations. `.github/workflows/baseballos-sync.yml:L68-L71`; `backend/services/sync_metadata.py:L330-L412`
- **Recovery/checkpoints:** unfinished game work is durable; postgame retries incomplete markers to a bounded limit; explicit recovery can reset selected failed markers only with a bounded date/game scope. `backend/models/game_ingestion_work_item.py:L27-L51`; `backend/services/sync.py:L349-L371`; `backend/scripts/run_postgame_refresh.py:L38-L60`
- **Criticality separation:** best-effort historical repair can remain incomplete without blocking a complete public critical path; active/unknown authority still fails closed. `backend/services/publication_criticality.py:L56-L114`; `backend/services/publication_criticality.py:L119-L157`

### Five production-grade reliability stories

1. **A single upstream timeout must not collapse the league.** Per-pitcher API errors exhaust bounded retries, become dead letters, and allow other entities to continue. The public decision then uses explicit criticality rather than treating every failure identically. `backend/services/mlb_api.py:L254-L303`; `backend/services/sync.py:L3952-L3977`; `backend/services/publication_criticality.py:L78-L114`
2. **A partially updated pipeline must not publish a mixed snapshot.** The sync and snapshot commit together; a failure rolls back publication, records the failed stage, and keeps the prior served row. `backend/services/sync.py:L5529-L5609`; `backend/tests/test_dashboard_snapshot.py:L1314-L1407`
3. **A crash overnight must not leave a permanent game hole.** The postgame lookback resweeps trailing dates, but completed markers make old work cheap; incomplete work retries within a limit. `backend/services/sync.py:L5769-L5781`; `backend/services/sync.py:L415-L453`
4. **A source correction must not leave derived evidence stale.** A safe GameLog correction records source/run/time and invokes all registered dependent-evidence invalidators; a registry audit guards against adding an untracked dependency. `backend/services/sync.py:L605-L675`; `backend/services/sync.py:L1234-L1259`
5. **Two schedulers must not become two writers.** Shared workflow concurrency queues jobs, and the database advisory lock is authoritative even for other entry paths. `.github/workflows/baseballos-sync.yml:L68-L71`; `backend/services/sync_metadata.py:L330-L412`

## 13. Performance / Query Efficiency

| Optimization | What becomes inefficient without it | Evidence |
|---|---|---|
| Composite indexes aligned to access paths | Latest pitcher workload, team/date history, game lookup, status queues, and serving snapshot lookup would degrade toward scans as facts grow. | `backend/models/game_log.py:L59-L65`; `backend/models/roster_status_snapshot.py:L32-L40`; `backend/models/game_ingestion_work_item.py:L81-L95`; `backend/models/dashboard_snapshot.py:L8-L18` |
| Latest-row aggregate/window queries | Loading all score/snapshot history and deduplicating in Python; or N latest-row queries. | `backend/services/availability_snapshot.py:L120-L165`; `backend/services/roster_status_sync.py:L737-L774` |
| Shared-window bulk GameLog load | One database query per pitcher for availability. | `backend/services/availability_snapshot.py:L209-L245` |
| Existing GameLog prefetch by canonical key | One remote DB lookup per split was the dominant cost; the writer now uses a prefetched map with a correctness-preserving miss fallback. | `backend/services/sync.py:L4363-L4370`; `backend/services/sync.py:L3839-L3855`; `backend/services/sync.py:L4469-L4489` |
| Per-run finality/boxscore caches | The same game appears across pitchers; without caching, one game could trigger repeated schedule/boxscore calls. | `backend/services/sync.py:L3831-L3838` |
| Conflict-safe bulk pitcher insert | Per-transaction participant SELECT/INSERT/commit loops and race failures. | `backend/services/canonical_transaction_pitcher_acquisition.py:L87-L127` |
| Bounded date windows and markers | Full-season/full-history API and table reads every run. | `backend/services/sync.py:L3707-L3759`; `backend/services/sync.py:L415-L453`; `backend/services/transaction_ingestion.py:L223-L239` |
| Read-optimized snapshots | Rebuilding dashboard output from normalized facts and expensive joins on every request. | `backend/models/dashboard_snapshot.py:L5-L39`; `backend/services/dashboard_snapshot.py:L214-L259` |
| PostgreSQL connection health/timeouts | Stale pooled sockets or stuck queries can consume web/job workers. | `backend/config.py:L54-L84` |
| `selectin` relationship loading | Serializing each read/artifact and lazily querying every child/citation. | `backend/models/composed_read.py:L119-L124`; `backend/models/composed_read.py:L186-L190`; `backend/models/share_artifact.py:L244-L270` |

### Current performance limitation to acknowledge

`recalculate_all_fatigue` still queries recent logs once per active pitcher after loading the pitcher list, so it contains an N+1-shaped database access path. At current scale it is workable, but a scaling improvement would bulk-load all needed logs once, group by pitcher, and bulk-insert scores—similar to `logs_for_availability_windows`. `backend/services/sync.py:L4557-L4591`; `backend/services/availability_snapshot.py:L209-L245`

## 14. Tests as Data Contracts

These are the strongest interview tests because they prove database/data behavior rather than UI rendering.

| Contract | What it proves | Evidence |
|---|---|---|
| Replay idempotency and unique appearance grain | Same game replays to zero inserts/updates; DB rejects duplicate `(pitcher, game)`. | `backend/tests/test_game_driven_ingestion.py:L135-L205` |
| Transaction exact-date repair | One candidate produces one exact snapshot/correction without changing current pitcher team. | `backend/tests/test_intraday_transaction_roster_repair.py:L161-L208` |
| Batching and idempotent retry | Two transactions sharing a team/date make one bounded source batch; second repair has zero candidates. | `backend/tests/test_intraday_transaction_roster_repair.py:L211-L248` |
| Source ambiguity fails closed | Missing/failing roster source or matches on both teams creates no snapshot/correction. | `backend/tests/test_intraday_transaction_roster_repair.py:L251-L295` |
| Wrong-team/history exclusion | Wrong-team snapshot, unknown transaction, and old window are not repair candidates. | `backend/tests/test_intraday_transaction_roster_repair.py:L298-L344` |
| Null versus legitimate zero | Unknown pitch volume remains null through calculation, persistence, and API; real zero remains zero. | `backend/tests/test_fatigue_pitch_null_persistence.py:L123-L188` |
| Historical team immutability | Trades/current team changes do not rewrite prior appearance team; doubleheaders remain distinct by game PK. | `backend/tests/test_appearance_team_authority.py:L575-L644` |
| Published snapshot recovery | Recalc or snapshot failure keeps the prior trusted snapshot and records the failed stage. | `backend/tests/test_dashboard_snapshot.py:L1314-L1407` |
| Pending is not served | A pending candidate does not advance the served pointer. | `backend/tests/test_dashboard_snapshot.py:L1409-L1444` |
| API retry contract | Four-attempt exhaustion, no 4xx retry, `Retry-After`, and cap are explicit. | `backend/tests/test_mlb_api_client.py:L107-L197` |
| Many-to-many evidence round trip | Components, citations, summary, and provenance reconstruct; citation FKs/types are validated. | `backend/tests/test_composed_read_contract.py:L210-L277`; `backend/tests/test_composed_read_contract.py:L470-L545` |
| Immutable/deduplicated publication | Equivalent artifacts converge; published payload/trust/version/team cannot mutate. | `backend/tests/test_share_artifact_domain.py:L310-L350`; `backend/tests/test_share_artifact_domain.py:L364-L393` |
| Appearance ledger publication gate | Incomplete ledger blocks publication and keeps previous snapshot; complete ledger passes. | `backend/tests/test_appearance_ledger.py:L252-L310` |
| Publication-critical scope | Best-effort-only partial work may publish; unknown/finality gaps still withhold. | `backend/tests/test_daily_sync_publication_budget.py:L82-L114`; `backend/tests/test_daily_sync_publication_budget.py:L187-L202` |

## 15. Best Production STAR Stories

These stories use repository history and current regression coverage. Avoid adding production counts unless you independently verify them before the interview.

### Story 1 — Historical appearances changed when a pitcher changed teams

**Situation**  
A model that joins historical appearances to mutable current `Pitcher.team_id` can attribute old workload to a player’s new team.

**Task**  
Preserve the team actually represented in each game, including trades, releases, and doubleheaders.

**Action**  
Added `appearance_team_id/source/status/reason` to `GameLog`; resolved it from official game-side evidence; enforced resolved/unresolved/conflict combinations with a database check; indexed team/date queries. Current identity remains separate.

**Result**  
Historical appearances remain frozen to the represented team after current team changes. Conflicts carry no fake team and fail closed.

**Data Engineering Concepts**  
Temporal modeling, slowly changing identity, source authority, composite grain, constraints, provenance, idempotency.

**Evidence**  
`backend/models/game_log.py:L62-L78`; `backend/models/game_log.py:L135-L149`; `backend/services/sync.py:L4423-L4442`; `backend/tests/test_appearance_team_authority.py:L575-L644`

### Story 2 — One unreliable player endpoint blocked trusted publication

**Situation**  
The legacy repair loop includes every locally active tracked player, including position players with legitimate historical pitching rows. A repeated `/people/{id}/stats` timeout could be treated as publication-critical even when the player could not be part of the current bullpen population.

**Task**  
Keep real current bullpen failures fail-closed while preventing irrelevant legacy repair from poisoning an otherwise complete publication.

**Action**  
Kept the bounded retry/dead-letter behavior, added one canonical `criticality_for_player` classifier, made explicit non-pitcher positions best-effort, and left missing/unknown position or roster authority fail-closed.

**Result**  
Best-effort shortfalls remain visible and retryable without automatically blocking a complete public critical path; active pitchers and unknown authority still withhold.

**Data Engineering Concepts**  
Failure-domain classification, optional versus critical data, fail-closed gates, dead letters, graceful degradation.

**Evidence**  
`backend/services/mlb_api.py:L167-L303`; `backend/services/publication_criticality.py:L34-L91`; `backend/services/publication_criticality.py:L94-L157`; `backend/tests/test_mlb_api_client.py:L107-L130`; `backend/tests/test_publication_criticality.py:L18-L90`

### Story 3 — Missing transaction roster evidence required a bounded repair

**Situation**  
Canonical transactions existed, but some could not support downstream roster explanations because an exact-date roster snapshot was missing.

**Task**  
Repair only cases that could be proven from the exact transaction date and exact MLB team without rewriting unrelated identity/history.

**Action**  
Selected candidates only from the latest successful source window, deduplicated team/date fetches, queried official roster variants, persisted only unambiguous exact matches, then recalculated only three alignment facts with correction provenance.

**Result**  
Safe matches become eligible; source omissions, both-team conflicts, wrong-team snapshots, unknown events, and older windows remain blocked. Reruns converge to no candidates.

**Data Engineering Concepts**  
Bounded replay, exact temporal join, batch deduplication, idempotency, correction provenance, conservative reconciliation.

**Evidence**  
`backend/services/intraday_transaction_roster_repair.py:L1-L82`; `backend/services/intraday_transaction_roster_repair.py:L91-L198`; `backend/tests/test_intraday_transaction_roster_repair.py:L161-L344`

### Story 4 — Partial pipeline failure must not publish mixed state

**Situation**  
Canonical ingestion could succeed and a later fatigue or snapshot phase could fail, risking a public payload that mixed old and new state.

**Task**  
Ensure publication advances only when a complete, provenance-linked candidate commits.

**Action**  
Made sync completion and snapshot publish one transaction, persisted candidates as pending, gated them on slate/ledger authority, rolled back on failure, and retained the previous serving pointer.

**Result**  
Failed downstream phases are recorded on `SyncRun`; the prior trusted snapshot continues serving until a new candidate passes.

**Data Engineering Concepts**  
Atomicity, transaction boundaries, materialized/read models, stale serving, recovery, observability.

**Evidence**  
`backend/services/sync.py:L5529-L5609`; `backend/services/dashboard_snapshot.py:L263-L429`; `backend/tests/test_dashboard_snapshot.py:L1314-L1444`

### Story 5 — Decimal baseball innings were the wrong canonical numeric type

**Situation**  
MLB notation such as `1.1` means one inning plus one out, not 1.1 mathematical innings. Treating decimal notation as the authority risks incorrect aggregates and correction comparisons.

**Task**  
Choose a lossless canonical representation and repair legacy data safely.

**Action**  
Made integer outs authoritative, derived decimal innings, added database equivalence/nonnegative checks, and implemented a Postgres set-based CTE/`CASE` backfill that excludes anomalies and updates only differences.

**Result**  
Stored innings have an exact additive unit; invalid companions cannot be committed; replays converge.

**Data Engineering Concepts**  
Canonical units, domain modeling, check constraints, CTE, `CASE`, set-based migration, idempotent repair.

**Evidence**  
`backend/models/game_log.py:L47-L54`; `backend/services/innings_backfill.py:L172-L208`; `backend/tests/test_canonical_innings_reconciliation.py:L431-L482`

### Story 6 — Daily ingestion exceeded its useful runtime budget

**Situation**  
Upstream phases and a shared ingestion pool could leave too little governed time for the legacy GameLog writer; a hard timeout mid-transaction would obscure what remained.

**Task**  
Finish cleanly, preserve time for publication/finalization, and make deferred work/criticality measurable.

**Action**  
Separated total budget, final-phase reserve, combined ingestion pool, lane allocation, actual lane elapsed time, and remaining writer budget. Critical work is ordered first; a budget cutoff batches one dead letter with remaining identities and returns a partial result rather than being killed.

**Result**  
Runs expose the exact shortfall, reserve finalization time, and distinguish publication-critical/unknown/best-effort deferred work.

**Data Engineering Concepts**  
Batch runtime governance, backpressure, resumability, observability, critical-path prioritization.

**Evidence**  
`backend/services/sync.py:L3511-L3570`; `backend/services/sync.py:L3888-L3950`; `.github/workflows/baseballos-sync.yml:L137-L176`; `backend/tests/test_daily_sync_runtime.py:L902-L1060`

### Story 7 — Corrections could make derived evidence stale

**Situation**  
An official GameLog correction changes workload and multiple evidence families; updating only the canonical row would leave derived claims internally inconsistent.

**Task**  
Make correction propagation exhaustive and auditable.

**Action**  
Defined the exact direct-dependent evidence registry, planned safe changes through one comparator, recorded correction source/run/time, and marked every family for recomputation before commit. Unsafe or incomplete corrections are blocked/dead-lettered.

**Result**  
Canonical facts and dependent evidence cannot silently diverge; adding a new direct dependency requires registry/test alignment.

**Data Engineering Concepts**  
Data lineage, invalidation, dependency graph, source corrections, consistency, repair orchestration.

**Evidence**  
`backend/services/sync.py:L605-L675`; `backend/services/sync.py:L1123-L1259`; `backend/tests/test_gamelog_field_authority.py:L188-L195`; `backend/tests/test_gamelog_field_authority.py:L815-L815`

## 16. Likely Interview Questions + Talking Points

Use these as reasoning prompts, not scripts.

### 1. Tell me about BaseballOS.

- **Strong claim:** A scheduled MLB data platform that ingests public source data, maintains canonical relational facts, derives bullpen workload/readiness, and publishes trusted read models. `backend/services/sync.py:L6490-L6505`
- **Nuance:** Operational analytics application, not a warehouse or distributed streaming platform.
- **Evidence:** `backend/services/mlb_api.py:L467-L634`; `backend/models/game_log.py:L40-L116`; `backend/models/dashboard_snapshot.py:L5-L39`

### 2. Walk me through your data pipeline.

- **Strong claim:** resilient API extraction -> source normalization/identity -> canonical facts/checkpoints -> bounded derivation -> snapshot trust gates -> read APIs.
- **Nuance:** Daily and postgame lanes have different units and failure boundaries; postgame is targeted, not a second full daily scan.
- **Evidence:** `backend/services/sync.py:L6545-L6873`; `backend/services/sync.py:L5763-L5781`

### 3. How is your database structured?

- **Strong claim:** PostgreSQL operational model centered on pitchers, game appearances, schedules, roster snapshots, transactions, derived scores, sync metadata/dead letters, evidence/read composition, and immutable publications.
- **Nuance:** Team IDs are source integers; there is no `teams` dimension/FK today.
- **Evidence:** `backend/models/pitcher.py:L4-L34`; `backend/models/game_log.py:L40-L149`; `backend/models/scheduled_game.py:L13-L46`

### 4. Tell me about a many-to-many relationship you modeled.

- **Strong claim:** A composed read component can cite many evidence objects, and the same evidence object can support many components; `composed_read_evidence_citations` is the association table with two FKs and citation attributes.
- **Nuance:** The baseball core is mostly one-to-many/event grain; this many-to-many belongs to lineage/read composition.
- **Evidence:** `backend/models/composed_read.py:L186-L238`; `backend/tests/test_composed_read_contract.py:L210-L277`

### 5. How do you handle duplicate data?

- **Strong claim:** deterministic natural keys + database unique constraints + idempotent writers. Game appearance: `(pitcher_id, mlb_game_pk)`; roster: `(pitcher_id, snapshot_date)`; transaction: deterministic `transaction_key`.
- **Nuance:** Application checks improve behavior/metrics, but the DB constraint is the race-safe backstop.
- **Evidence:** `backend/models/game_log.py:L40-L46`; `backend/models/roster_status_snapshot.py:L32-L40`; `backend/services/transaction_ingestion.py:L984-L999`

### 6. How do you handle missing/null data?

- **Strong claim:** Preserve unknown as null when zero would imply authority; downstream facts and public payloads retain the distinction.
- **Nuance:** Not every numeric field is nullable; the choice depends on whether source omission changes semantic meaning.
- **Evidence:** `backend/services/sync.py:L532-L545`; `backend/tests/test_fatigue_pitch_null_persistence.py:L123-L188`

### 7. How do you ensure data quality?

- **Strong claim:** typed normalization, natural-key uniqueness, check constraints, explicit source authority, correction provenance, data-contract tests, and fail-closed publication.
- **Nuance:** Quality is domain-specific, not a single score.
- **Evidence:** `backend/models/game_log.py:L40-L78`; `backend/services/dashboard_snapshot.py:L222-L254`

### 8. How do you handle unreliable upstream APIs?

- **Strong claim:** per-request timeout, capped retry/backoff/jitter, `Retry-After`, typed error classification, endpoint metrics, dead letters, partial progress.
- **Nuance:** Retries only address transient errors; persistent gaps become explicit incomplete state rather than invented data.
- **Evidence:** `backend/services/mlb_api.py:L103-L174`; `backend/services/mlb_api.py:L180-L303`

### 9. How do you make pipelines idempotent?

- **Strong claim:** stable work/fact identity, upsert classification, unchanged detection, correction fingerprints, and completed markers.
- **Nuance:** Idempotent does not mean immutable source facts; a genuine authoritative correction produces a governed update/new revision.
- **Evidence:** `backend/tests/test_game_driven_ingestion.py:L135-L184`; `backend/models/team_progressive_publication.py:L59-L102`

### 10. Incremental versus full recomputation?

- **Strong claim:** increment source facts by game/date/window; recompute only affected derivatives when dependencies are local; use full recomputation when a global reference date changes every pitcher’s availability.
- **Nuance:** Current fatigue recalculation is league-wide after changed workloads because its reference date is shared.
- **Evidence:** `backend/services/sync.py:L4049-L4169`; `backend/services/sync.py:L4533-L4591`

### 11. Tell me about a production data issue you debugged.

- **Strong claim:** Use the stale current-team versus historical appearance story, the timeout/criticality story, or exact-date transaction repair.
- **Nuance:** Explain causal chain and invariant; do not invent volume/latency improvement.
- **Evidence:** STAR Stories 1–3 above.

### 12. How do you manage historical data?

- **Strong claim:** event facts with correction provenance, dated roster snapshots, append-oriented scores/dashboard snapshots, immutable publications.
- **Nuance:** Not a general temporal database; historical handling is explicit per domain.
- **Evidence:** `backend/models/roster_status_snapshot.py:L42-L70`; `backend/models/share_artifact.py:L168-L239`

### 13. How do old publications remain reproducible?

- **Strong claim:** store payload/version/source dates/run and capture artifact evidence by value; never recompute yesterday from current identity.
- **Nuance:** Dashboard rows retain proof, while immutable artifact guarantees are stronger and enforced at ORM flush.
- **Evidence:** `backend/services/dashboard_snapshot.py:L928-L965`; `backend/models/share_artifact.py:L318-L352`; `backend/models/share_artifact.py:L507-L568`

### 14. What SQL patterns do you use most?

- **Strong claim:** joins, grouped aggregates, latest-row subqueries/windows, bounded date predicates, `IN`, `EXISTS`, ordering/limits, upserts, and transactional bulk updates.
- **Nuance:** Mostly expressed through SQLAlchemy; raw SQL is used selectively.
- **Evidence:** `backend/services/availability_snapshot.py:L120-L245`; `backend/services/roster_status_sync.py:L737-L774`; `backend/services/innings_backfill.py:L172-L208`

### 15. How do you improve query performance?

- **Strong claim:** indexes matching predicates/order, set-based latest-row queries, prefetch/group, batching, per-run caches, bounded windows, and read-model snapshots.
- **Nuance:** I would next eliminate the fatigue N+1 path and validate improvements with `EXPLAIN ANALYZE`/production query telemetry.
- **Evidence:** `backend/services/sync.py:L3831-L3865`; `backend/services/sync.py:L4557-L4591`

### 16. How do you test data pipelines?

- **Strong claim:** tests assert grain/constraints, idempotent replay, source ambiguity, null semantics, failure rollback, publication gates, and historical immutability.
- **Nuance:** SQLite-compatible tests are useful, but PostgreSQL-specific behavior also needs Postgres execution (upsert/advisory locks/raw SQL).
- **Evidence:** Section 14; `backend/services/canonical_transaction_pitcher_acquisition.py:L110-L125`

### 17. How do you recover from partial failures?

- **Strong claim:** commit at safe boundaries, dead-letter failed entities, keep durable checkpoints, retry bounded incomplete work, and keep prior trusted reads serving.
- **Nuance:** Some failed markers require explicit bounded operator reset rather than infinite automatic retry.
- **Evidence:** `backend/services/sync.py:L5927-L6037`; `backend/scripts/run_postgame_refresh.py:L38-L60`

### 18. How do scheduled workflows fit together?

- **Strong claim:** morning daily baseline, later schedule-only correction, three targeted postgame passes; all share concurrency and publication contracts.
- **Nuance:** intraday repair is manual-only, and backfills are explicit-date manual operations.
- **Evidence:** `.github/workflows/baseballos-sync.yml:L30-L71`; `.github/workflows/baseballos-intraday-repair.yml:L1-L17`

### 19. What is the hardest data problem?

- **Strong claim:** determining what is authoritative “now” versus “at the time of the event” when MLB data is incomplete and revised.
- **Nuance:** It combines identity, chronology, finality, corrections, and publication—not just parsing.
- **Evidence:** `backend/models/game_log.py:L135-L149`; `backend/models/player_transaction.py:L80-L125`

### 20. What would you improve at significant scale?

- **Strong claim:** conformed team/player dimensions, set-based fatigue derivation, bulk writes, table partition/retention, query plans/metrics, and a stronger orchestrator if DAG complexity warrants it.
- **Nuance:** Do not prescribe Kafka/Spark automatically; choose them only if source volume/latency/consumer needs justify distributed processing.
- **Evidence for current limit:** `backend/services/sync.py:L4557-L4591`; `backend/models/scheduled_game.py:L13-L15`

### 21. How comfortable are you with SQL?

- **Strong claim:** “Comfortable with relational modeling, query reading/composition, joins/aggregates/windows, constraints, transactions, and debugging. I may check exact syntax for uncommon operations.”
- **Nuance:** Do not claim expert memorization of every dialect feature.
- **Evidence:** `backend/services/roster_status_sync.py:L737-L774`; `backend/services/innings_backfill.py:L172-L208`

### 22. Why Data Engineering?

- **Strong claim:** The work you repeatedly chose in BaseballOS is defining canonical truth, modeling relationships, making pipelines resumable, and preventing incorrect downstream claims.
- **Nuance:** Ground the answer in how you work, not buzzwords.
- **Evidence:** `backend/models/game_ingestion_work_item.py:L5-L22`; `backend/services/dashboard_snapshot.py:L328-L429`

### 23. What best demonstrates Data Engineering ability?

- **Strong claim:** The appearance-ledger + publication system: canonical event grain, temporal team authority, reconciliation, correction lineage, incremental checkpoints, and fail-closed materialized publication.
- **Nuance:** It is an operational application pipeline, not a petabyte warehouse.
- **Evidence:** `backend/models/game_log.py:L40-L149`; `backend/services/sync.py:L1123-L1259`; `backend/services/dashboard_snapshot.py:L328-L429`

## 17. SQL Quick Reference

Patterns below are present in current implementation; syntax is simplified to show the underlying SQL.

| Pattern | Plain-English meaning | BaseballOS use | Evidence |
|---|---|---|---|
| `FROM a JOIN b ON ...` | Keep rows with a match on both sides. | Join latest fatigue timestamps back to scores, then pitchers. | `backend/services/availability_snapshot.py:L132-L149` |
| `FROM a LEFT JOIN b ON ...` | Keep the left entity even when optional right-side data is missing. | Bullpen queries outer-join latest fatigue rows so pitchers can remain visible without a score. | `backend/api/bullpen.py:L1050-L1071` |
| `GROUP BY entity_id` | Collapse rows into entity groups for aggregates. | Group GameLogs by pitcher for latest appearance date. | `backend/services/availability_snapshot.py:L182-L192` |
| `GROUP BY ... HAVING condition` | Filter groups after aggregation. | Keep pitchers whose `MAX(game_date)` is inside the active window. | `backend/api/bullpen.py:L225-L237` |
| `COUNT(*)` / `COUNT(id)` | Count rows. | Count canonical GameLogs and operational marker/event rows. | `backend/api/bullpen.py:L318-L324`; `backend/services/source_readiness.py:L588-L600` |
| `COUNT(DISTINCT x)` | Count unique entities, not facts. | Count pitchers with any fatigue score. | `backend/api/bullpen.py:L321-L324` |
| `CASE WHEN condition THEN value ELSE value END` | Map source values into conditional results. | Convert MLB decimal innings to integer outs in a repair CTE. | `backend/services/innings_backfill.py:L176-L205` |
| `COALESCE(a, fallback)` | Substitute the first non-null expression. | Aggregate readiness counts default null sums/max to zero. | `backend/services/source_readiness.py:L601-L620` |
| `ORDER BY column DESC` | Define deterministic order/recency. | Roster latest authority orders date, correction time, then ID. | `backend/services/roster_status_sync.py:L724-L755` |
| `LIMIT n` | Bound result size. | Availability/list readers and recompute queues use bounded results. | `backend/services/availability_snapshot.py:L156-L165`; `backend/services/team_daily_read.py:L208-L209` |
| `WITH name AS (...) SELECT/UPDATE ...` | Name an intermediate relation for one statement. | Classify legacy innings and update from the classified set. | `backend/services/innings_backfill.py:L172-L208` |
| `WHERE EXISTS (SELECT 1 ...)` | Ask whether any matching row exists. | Avoid duplicate unresolved transaction dead letters. | `backend/services/transaction_ingestion.py:L913-L929` |
| `WHERE x IN (...)` | Match a bounded set. | Bulk-load pitchers/snapshots/logs by prefetched IDs/dates. | `backend/services/availability_snapshot.py:L182-L190`; `backend/services/roster_status_sync.py:L762-L772` |
| `FROM (SELECT ...) AS latest` | Use one query result as an input relation. | Latest fatigue timestamp per pitcher. | `backend/services/availability_snapshot.py:L127-L149` |
| `ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ...)` | Rank rows while retaining row identity. | Select one deterministic latest roster snapshot per pitcher. | `backend/services/roster_status_sync.py:L737-L774` |
| `INSERT INTO ...` / `UPDATE ... SET ...` | Add facts or change governed current/corrected state. | GameLog writer inserts or applies only planned fields; snapshot publication bulk-updates serving flags/pointers. | `backend/services/sync.py:L1158-L1259`; `backend/services/dashboard_snapshot.py:L387-L418` |
| `INSERT ... ON CONFLICT (...) DO NOTHING` | Let a unique key settle duplicate/concurrent inserts. | Bulk canonical pitcher acquisition uses `ON CONFLICT DO NOTHING (mlb_id)`. | `backend/services/canonical_transaction_pitcher_acquisition.py:L110-L127` |
| `BEGIN; ... COMMIT` / `ROLLBACK` | Make a set of writes succeed/fail together. | Sync completion + dashboard publication commit atomically; exception rolls back. | `backend/services/sync.py:L5529-L5609` |
| Self-join | Join a table to itself. | **Not found / not relied upon as a meaningful current production query pattern.** Self-referential FKs/relations exist, but that is a model relationship, not evidence of a current self-join query. | `backend/models/share_artifact.py:L425-L469` |

## 18. What Not to Overstate

| Do not say | Honest framing |
|---|---|
| “I built a distributed streaming pipeline.” | “BaseballOS uses scheduled incremental batch pipelines because MLB source cadence and the product’s morning/postgame needs do not justify streaming complexity.” `.github/workflows/baseballos-sync.yml:L30-L42` |
| “I use Kafka/Spark/Airflow/dbt.” | “The current stack is Python, SQLAlchemy/Alembic, PostgreSQL, Flask, and GitHub Actions orchestration.” `backend/requirements.txt:L1-L9`; `.github/workflows/baseballos-sync.yml:L30-L44` |
| “I built a warehouse.” | “I built an operational PostgreSQL data model plus read-optimized snapshots and evidence/read models.” `backend/models/dashboard_snapshot.py:L5-L39`; `backend/models/evidence_contract.py:L5-L124` |
| “The schema has full team referential integrity.” | “Team IDs are MLB source integers; there is no `teams` table. That is a clear scale/design improvement area.” `backend/models/scheduled_game.py:L13-L15` |
| “All pipelines are game-driven and authoritative.” | “The daily critical lane is game-driven; the postgame game-driven integration remains observation-only while the established postgame writer is authoritative.” `backend/services/sync.py:L6710-L6759`; `backend/services/sync.py:L6108-L6158` |
| “Intraday repair runs throughout the day.” | “The exact-date repair implementation exists but its workflow is manual-only/dormant for the remainder of 2026.” `.github/workflows/baseballos-intraday-repair.yml:L1-L11` |
| “Everything is immutable.” | “Canonical current/cache tables are mutable; event corrections are governed and provenance-bearing; published share artifacts are immutable.” `backend/services/sync.py:L1123-L1259`; `backend/models/share_artifact.py:L507-L568` |
| “Every query is optimized.” | “There are strong indexes, batching, windows, and caches; fatigue recalculation still has an N+1-shaped log query and is a scale target.” `backend/services/sync.py:L4557-L4591` |
| “I write all SQL by hand.” | “Most queries use SQLAlchemy, but the underlying design uses real relational concepts; I use raw Postgres SQL selectively for set-based repair.” `backend/services/innings_backfill.py:L172-L208` |
| “The platform has proven enterprise scale.” | “It is a founder-operated system with production reliability patterns; the repository does not establish high-volume multi-tenant scale.” |
| “Composed reads are a complete public semantic layer.” | “The relational/evidence substrate is implemented; registered production read types are currently internal-only.” `backend/tests/test_composed_read_contract.py:L186-L207` |
| “A green workflow proves all data is correct.” | “The pipeline persists run stages/counts and separately gates snapshot publication; data proof comes from durable facts and publication status.” `backend/models/sync_run.py:L13-L46`; `backend/services/dashboard_snapshot.py:L222-L254` |

### About authorship/tooling

The repository establishes implementation and test evidence, not how much syntax was typed from memory or which development tools helped. Frame yourself as the sole creator/maintainer who owns the system decisions and can trace the code and data. Do not speculate about mechanics the repository cannot prove.

## 19. Top 15 Facts to Memorize

1. `GameLog` grain is **one pitcher + one MLB game**; unique constraint `(pitcher_id, mlb_game_pk)`. `backend/models/game_log.py:L40-L46`
2. Integer `innings_pitched_outs` is canonical; decimal innings is derived and constrained. `backend/models/game_log.py:L47-L54`
3. Current `Pitcher.team_id` is not historical appearance team. `backend/models/game_log.py:L135-L149`
4. There is no `teams` table; MLB team IDs are plain integers. `backend/models/scheduled_game.py:L13-L15`
5. Roster history grain is `(pitcher_id, snapshot_date)`. `backend/models/roster_status_snapshot.py:L32-L46`
6. Transaction identity uses a source transaction ID or deterministic fallback digest. `backend/services/transaction_ingestion.py:L984-L999`
7. The many-to-many example is read components <-> evidence objects through `composed_read_evidence_citations`. `backend/models/composed_read.py:L209-L238`
8. Daily critical ingestion checkpoints by **game**, not pitcher. `backend/models/game_ingestion_work_item.py:L5-L22`
9. Postgame fetches only unprocessed/retryable completed games and commits per game. `backend/services/sync.py:L415-L453`; `backend/services/sync.py:L5927-L6037`
10. Missing pitch/hit/walk data remains null; zero is authoritative only when supplied. `backend/services/sync.py:L532-L545`
11. Latest roster snapshot batching uses `ROW_NUMBER() OVER (PARTITION BY ...)`. `backend/services/roster_status_sync.py:L737-L774`
12. Snapshot publication is separate from calculation and commits atomically with run completion. `backend/services/sync.py:L5529-L5609`
13. Failed candidate publication leaves the previous trusted snapshot serving. `backend/tests/test_dashboard_snapshot.py:L1314-L1407`
14. Current automatic cron lanes are daily 10:00 UTC, schedule-only 14:00 UTC, and postgame 02:00/04:00/06:00 UTC. `.github/workflows/baseballos-sync.yml:L30-L42`
15. Intraday exact-date repair exists but is manual-only. `.github/workflows/baseballos-intraday-repair.yml:L1-L11`

## 20. Top 10 Repository Files to Know

1. **`backend/models/game_log.py`** — canonical appearance grain, keys, constraints, nullable semantics, historical team authority. `backend/models/game_log.py:L40-L149`
2. **`backend/services/sync.py`** — daily/postgame orchestration, normalization, reconciliation, dead letters, incremental work, derivation, and publication transaction. `backend/services/sync.py:L6490-L7052`
3. **`backend/services/mlb_api.py`** — upstream endpoints, typed extraction, retries, timeouts, and metrics. `backend/services/mlb_api.py:L103-L303`; `backend/services/mlb_api.py:L467-L639`
4. **`backend/services/dashboard_snapshot.py`** — materialized read model, trust gates, serving rotation, and trusted historical lookup. `backend/services/dashboard_snapshot.py:L222-L429`; `backend/services/dashboard_snapshot.py:L928-L995`
5. **`backend/services/transaction_ingestion.py`** — bounded extraction, participant resolution, deterministic identity, correction/upsert, and window metadata. `backend/services/transaction_ingestion.py:L223-L459`; `backend/services/transaction_ingestion.py:L627-L669`
6. **`backend/models/game_ingestion_work_item.py`** — resumable game-level critical checkpoint and completion invariant. `backend/models/game_ingestion_work_item.py:L5-L126`
7. **`backend/models/roster_status_snapshot.py`** — date-grained roster authority, natural key, source/correction provenance. `backend/models/roster_status_snapshot.py:L5-L70`
8. **`backend/models/composed_read.py`** — read/component/evidence relational design and many-to-many junction example. `backend/models/composed_read.py:L51-L124`; `backend/models/composed_read.py:L159-L238`
9. **`backend/models/share_artifact.py`** — immutable/versioned publication, evidence captured by value, self-referential relation graph. `backend/models/share_artifact.py:L168-L270`; `backend/models/share_artifact.py:L318-L469`; `backend/models/share_artifact.py:L507-L568`
10. **`.github/workflows/baseballos-sync.yml`** — actual production cadence, runner commands, timeouts, concurrency, and proof steps. `.github/workflows/baseballos-sync.yml:L30-L95`; `.github/workflows/baseballos-sync.yml:L109-L329`

---

### Final interview calibration

The strongest defensible statement is:

> “BaseballOS shows that I can define relational grain, preserve source uncertainty, build idempotent incremental pipelines, reason about transaction and failure boundaries, and publish reproducible data products without making claims the source cannot support.”

The most useful follow-up habit is to explain **why** each boundary exists: unique keys protect grain, null protects uncertainty, checkpoints protect resumability, provenance protects correction history, and publication gates protect users from mixed or unsupported state.
