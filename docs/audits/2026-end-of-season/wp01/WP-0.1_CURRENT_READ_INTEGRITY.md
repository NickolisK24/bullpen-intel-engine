# WP-0.1: Current-Read Integrity

**Package:** Phase 0, WP-0.1 of `05_2027_OFFSEASON_ROADMAP.md`.
**Findings addressed:** EOS-001, EOS-002, EOS-003 (dry run only), EOS-004 (`03_FINDINGS_REGISTER.md`).
**Audit documents:** `docs/audits/2026-end-of-season/` on branch `audit/2026-end-of-season-platform-audit`; they are not on `main`, so references below name them without a path.
**Branch:** `fix/phase0-wp01-current-read-integrity`.
**Status:** Implementation. Nothing here changes product policy until the founder ledgers DEC-01 and DEC-02 (`06_DECISION_REGISTER.md`); see "Policy" below.

## Root causes, confirmed at `main` @ `3488addf6`

1. **Inactivity counted as constraint (EOS-001).**
   - `availability.py` returned `Monitor` for the `stale` data state, meaning no appearance in `ACTIVE_WINDOW_DAYS` (14).
   - `bullpen_readiness._team_state_partition` puts `Monitor` in the moderate bucket.
   - Contract A's margin floor (`clean_count <= 2`) then published Vulnerable.
   - The trust gate already accepted the same arm as valid observed rest, so a state was always published.
   - The coverage inventory also counted the arm as "missing workload", adding a spurious "incomplete readiness evidence" constraint.
   - A `missing` workload record (no evidence at all) was also `Monitor`, so unknown evidence was treated as a constraint.
2. **No club competition status (EOS-002).**
   - The availability reference date is league-wide.
   - Nothing in intelligence, publication, or the frontend knew that a club's season had ended.
   - Structurally, the mandatory pre-trust proof (`require_transactional_publication_proof`) raised if any of the 30 clubs was ineligible. So a club could not be withheld without blocking the whole publication, and every club had to receive a state.
3. **No plausibility gate (EOS-004).**
   - The only distribution check (`distribution_degenerate`) fired when zero clubs were Fresh.
   - It was advisory, and it lived on the proof-export path, which was skipped in production runs.
4. **Per-publication artifacts (EOS-003).** Each publication froze every club's read, so October's errors are now spread across about 1,500 immutable artifacts.

## What changed

| Area | Change |
|---|---|
| `services/availability.py` | `stale` → `Available`, medium confidence, reason "No appearances in the last 14 days", limitation "workload only, not physical or medical readiness". `AVAILABILITY_METHOD_VERSION = availability_rest_by_absence_v2`. Every real workload rule is unchanged |
| `services/availability_explanations.py` | New reason and limitation; the reason is categorised as rest |
| `api/team_operations.py` `_readiness_record` | A `stale` record counts as current workload evidence; a `missing` record lands in the Team State `unknown` bucket (never moderate) |
| `services/pitcher_public_labels.py` | A rested-by-absence arm (`stale` + `Available` + medium or higher confidence) reads Clean Option, consistent with the partition. `ARM_READ_METHOD_VERSION` → v2 |
| `services/bullpen_board.py` | `REST_STATUS_METHOD_VERSION` → `d055_rest_status_v2` (rest counts change for the same evidence) |
| `services/club_competition_status.py` (new) | Backend-owned per-club status (`active` / `season_complete` / `undetermined`) from stored `scheduled_games` and official `game_logs.win` decisions. Details below |
| `services/share_artifact_generation.py` | The production readiness resolver attaches `season_context` at the read's availability reference date |
| `services/team_state_public_vocabulary.py` | Two governed non-state outcomes, `season_complete` and `competition_status_unconfirmed`. `public_team_state()` applies them before any computed state |
| `services/team_state_eligibility.py` | New block `not_in_active_competition`: no current Team State artifact for a withheld club |
| `services/team_state_vnext_production_proof.py` | A competition withholding is a governed withholding, not a failure. Its receipt freezes the season non-state; the candidate entry uses the single public projection. Plausibility runs before the pointer moves; results and withheld clubs are recorded in the durable proof |
| `services/team_state_plausibility.py` (new) | Blocking and advisory checks (below) |
| `services/team_board_snapshot_team_state.py` | Receipts may freeze a competition withholding, and are stamped with the availability method. A Team State comparison across the method boundary is refused (`availability_method_boundary`) instead of reporting a change |
| `services/league_team_state_listing.py` | A club with no artifact shows its frozen season withholding, not a generic "artifact missing" |
| `services/team_story_previews.py` | A withheld club's static preview carries no current baseball point |
| `api/bullpen.py` | The dashboard payload is stamped with the availability method. A prior built under a different method is passed to Since Yesterday as no comparable prior, so the method change is withheld rather than reported as rested-option movement. The frozen `services/what_changed_since_yesterday.py` is unchanged |
| `explanations/availability.py` | A rested-by-absence arm's V4 explanation says it has not pitched in two weeks (a workload note, not a health read), not "a monitor arm", and carries no elevated-usage reason |
| `tests/freeze_policy.py` | Exact-path approval `WP01_CURRENT_READ_INTEGRITY_PATHS` for the three Team State modules, citing this record |
| `services/team_state_correction_manifest.py`, `scripts/build_team_state_correction_manifest.py` (new) | Read-only dry-run correction manifest |

**No frontend change.** The frontend already renders the backend's governed `unavailable_message` for any non-state outcome (`frontend/src/adapters/publicTeamState.js`).

## Club competition status

Evaluated at the read's availability reference date `R`, for `R`'s season, using only competitive game types (`R`, `F`, `D`, `L`, `W`). Spring, exhibition, and unknown types are ignored.

| Condition, in order | Status | Basis |
|---|---|---|
| No competitive rows for the club | undetermined | `no_competitive_schedule_evidence` |
| A World Series reached its clinching win count | season_complete (every club) | `world_series_decided` |
| The club's opponent reached a series' clinching win count | season_complete | `postseason_series_lost` |
| A pending game on or after `R` | active | `upcoming_scheduled_game` |
| The club won its latest series and the next round is not yet listed | active | `postseason_series_won_next_round_not_listed` |
| Club in the postseason, otherwise | undetermined | `competition_status_unresolved` |
| Postseason scheduled and the club is not in it | season_complete | `postseason_scheduled_without_club` |
| No postseason scheduled; last regular-season final within `ACTIVE_WINDOW_DAYS` | active | `regular_season_in_progress` |
| Otherwise | undetermined | `competition_status_unresolved` |
| The stored authority could not be read | undetermined | `competition_status_lookup_failed` (publication blocks) |

How the inputs are read:

- **Series decisions:**
  - Official decisions only: one credited winning club per final game.
  - The clinching count is `games_in_series // 2 + 1` from MLB's published series length.
  - Missing decisions never decide a series.
- **Pending games:**
  - `scheduled`, `suspended`, or live.
  - A cancelled or retired game (`schedule_absence`) is not pending.
- **Why no three-day heuristic is used:** stored series outcomes and the schedule authority settle the cases it was meant to cover. A pennant winner waiting six days for the World Series stays active, and a series loser is withheld the next day even before its unneeded games are retired.

## Plausibility checks (inside the pre-trust proof)

**Blocking.** The candidate is not published and the previous trusted snapshot keeps serving.

- `inactive_club_published_as_current`
- `inactivity_counted_as_constraint`: a stale arm reading Watch Arm or Limited Rest
- `competition_status_lookup_failed`
- `represented_date_contradiction`: a club's competition status was evaluated for a different date than the read it gates

**Advisory.** Recorded in the proof and surfaced as `PASS_WITH_INCONCLUSIVE`.

- `majority_vulnerable`: more than 50% of at least 8 published clubs
- `vulnerable_shift`: at least 50% of at least 8 comparable clubs worsened at once
- `arm_read_team_state_mismatch`
- `season_context_missing`
- `final_game_after_data_through`: normally ingestion lag, so it does not withhold the previous-day read

The distribution checks count only clubs that publish a current state, so a postseason publication with two clubs cannot trip them.

## Historical artifacts (EOS-003)

**No artifact was changed, superseded, or withdrawn.**

- **Inventory.** `team_state_artifact_inventory_2026-09-28_onward.csv` lists the 1,528 committed `team_state` share pages with data-through on or after 2026-09-28 (834 Vulnerable, 298 Stretched, 396 Fresh).
  - Generated offline from `frontend/public/share` at `main` @ `3488addf6`.
  - Entries digest: `sha256:5de64be692163986937e55f18b1d5dc6d7985f61c32c03c3da7b42c765cc5c85`.
  - Every row is `review_required`, because those pages do not carry the competition status or per-arm evidence a decision needs.
- **Authoritative classification: BLOCKED.** It needs a read-only run against production:

  ```
  python -m scripts.build_team_state_correction_manifest \
    --start 2026-09-28 --end 2026-10-31 \
    --output team_state_correction_manifest.json \
    --csv team_state_correction_manifest.csv
  ```

  For each published artifact it records:
  - the competition status at its reference date;
  - the corrected partition: idle arms re-counted clean, missing-evidence arms moved to unknown, using the per-arm data states and the thresholds frozen in that snapshot's durable proof;
  - the corrected public state;
  - one action: `propose_supersede_with_correction`, `retain`, or `review_required`.
- **Withdrawal is never proposed.** The claims were incorrect when published, so the correction is supersession with a public note.
- **Lifecycle sufficiency.** The existing `superseded_at` / `withdrawn_at` / `withdrawn_reason` lifecycle is enough to record supersession. A public correction note and its rendering on `/share/{id}` do not exist yet; they belong to WP-0.7.
- **Executing corrections is out of scope.** It needs explicit authorization (DEC-03).

## Policy

This package changes what a published label means in two places. Both are consistent with existing rules, but both need ledger entries:

- **Stale arm → Clean Option.**
  - Implements Standard 02:676 ("staleness … never silently degrades accuracy").
  - Matches 02's own definition of Available ("recent workload leaves the arm inside the normal availability range").
  - Needs DEC-02.
- **No current Team State for a club not in active competition.**
  - Implements 01:140 and 02:685.
  - Adds two governed non-state outcomes to Standard 02 §8. "No fourth Team State" is preserved: these are non-states like `data_limited`.
  - Needs DEC-01.

## Remaining dependencies

- **Full season-phase model (WP-1.1):** offseason, spring, opening, the champion, and a phase-aware league landscape.
  - The landscape (`public_landscape.py`) still requires 30 represented clubs, so it withholds while any club is out of competition. That is fail-closed, not wrong.
- **Postseason role evidence (EOS-006, WP-2.3).** Roles still use regular-season logs only.
- **Spring-training workload exclusion at ingestion (EOS-023).** Availability windows do not yet filter game types.
- **Reliever arm reads for a withheld club are still shown on the Team Board.**
  - The Team State slot now states that the club's workload is historical context, not a current pregame read.
  - Withholding or restyling the arm list is a frontend/board change for WP-1.3.
- **The board's On-Watch sentence still counts `missing` arms as On Watch.** The Team State partition no longer does (EOS-018, WP-3a.2).
- **Ingestion/series-decision completeness.** If postseason `win` decisions are missing, a series is never decided and the club becomes `undetermined` (withheld, fail-closed), not active.
