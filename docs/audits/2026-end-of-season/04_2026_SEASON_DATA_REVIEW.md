# 04 — 2026 Season Data Review

**Audit date:** 2026-10-29
**Access limit:** the production database and the MLB Stats API were **BLOCKED**. This review rests on:
- the code;
- production artifacts committed to git;
- the GitHub Actions history;
- documented incidents.

Every count that needs the database is written as an **executable check** (gate IDs refer to `07`), not as a claimed result.

---

## 1. Season data completeness

### 1.1 What the platform ingests

| Domain | Source endpoint | Store | Coverage (evidence) |
|---|---|---|---|
| Schedule (all game types) | `/schedule` (no `gameType` filter, `mlb_api.py:621`) | `scheduled_games` (unique `team_id, game_pk`) | Full 2026, including postseason and conditional games (`schedule_absence.py`) |
| Relief/starter appearance lines | Daily per-pitcher `/people/{id}/stats?stats=gameLog` (regular season; INFERRED API default), plus the postgame `/game/{pk}/boxscore` lane (all types) | `game_logs` (unique `pitcher_id, mlb_game_pk`) | Regular season, mostly through both lanes; postseason through the boxscore lane only |
| Play-by-play and pitch events | `/game/{pk}/playByPlay` | `game_play_by_play_events`, `game_pitch_events` | **Only games processed since about 2026-07-04** (migration `a2f4c6d8e9b1`) |
| Team pitching splits / completed-game context | Boxscore, linescore | `team_game_pitching_splits`, `completed_game_context` | Post-July foundation |
| Rosters / IL | `/teams/{id}/roster` (active, 40-man, full) | `roster_status_snapshots`, `pitchers.roster_status*` | Dated snapshots |
| Transactions | `/transactions` | `player_transactions` (versioned) | 2026 |
| Handedness | `/people/{id}` | `pitchers.throws` | **Incomplete:** "4 active relievers are missing throwing-hand data" (WSH artifact, 10-27; EOS-024) |

### 1.2 Known completeness incidents in 2026

From docs and decision records; each is a candidate for G-1 re-verification.

| Date | Incident | Recorded resolution |
|---|---|---|
| Jul 8 | Appearance-ledger restoration | `docs/audits/appearance-ledger-restoration-2026-07-08.md` |
| Jul 26–27 | Appearance team backfill and residual; unresolved appearance-team repair; opening-week schedule authority repair | Decisions 2026-07-26/27 |
| Jul 27–29 | Official pitching-line completeness and repair (including the Matt Festa earned-run correction) | Decisions 2026-07-27…29 |
| Jul 27 | Phantom game-log reconciliation | Decision plus guard workflow |
| Sep 10–21 | League publication stuck while freshness reported current (34-team universe) | Incident 2026-09-12; "Recovery is not yet proven" (:3, :59). **No closure recorded** |
| Sep 23 | Starter workload displayed as bullpen workload | Fixed in code (`game_shape.py:305`). Production confirmation UNVERIFIED |
| Sep 25, Oct 1 | Integration-runtime fences reverted `main` writes | `SYNC_PIPELINE.md` §15A–15D |
| Sep 27 | Cancelled-game slate coverage | Decision 2026-09-28 |
| Sep 29 | Daily Primary OOM (512 MiB) | `docs/audits/daily-primary-memory-incident-2026-09-29.md` |

### 1.3 Assessment

- **Regular season:** structurally complete, with repeated repairs. The repairs were governed and recorded, which is a strength. Final completeness is UNVERIFIED until G-1 runs.
- **Postseason:**
  - Workload rows exist (INFERRED from MIL/TB reads reacting to World Series usage).
  - Completeness depends on the boxscore lane alone, with a 2-day lookback. A missed postseason game beyond the lookback would be lost from the ledger (pipeline notes §4).
  - **Must be verified game by game** (G-1.3).
- **Pitch-level:** absent for about 3.5 months of the regular season. Recoverable from MLB play-by-play (EOS-M09).

---

## 2. Game / appearance / roster reconciliation

These checks define the reconciliation contract. Run them read-only against production; the SQL is in `07` G-1.

1. **Final-game coverage.** Every `scheduled_games` row with `game_date` in 2026, `game_type` in (`R`,`F`,`D`,`L`,`W`) and a final status has at least one `game_logs` row for each participating club. Doubleheaders and suspended/resumed games are handled through `resumed_from_game_pk` / `resumed_to_game_pk`.
2. **Expected totals.**
   - Regular season: 2,430 games, minus any cancelled-and-not-made-up games recorded under the 2026-09-28 terminality decision.
   - Postseason: Wild Card + Division Series + LCS + World Series game count, from the MLB schedule.
3. **Outs reconciliation.** For each final game and club, `SUM(innings_pitched_outs)` across that club's pitchers equals the club's defensive outs (27 for a 9-inning road win, etc.), checked against the stored linescore / `completed_game_context`. Mismatches are listed and resolved per game.
4. **Starter uniqueness.** Exactly one `games_started = 1` per club per game.
5. **Appearance-team authority.** Zero `game_logs` with `appearance_team_status` unresolved for 2026.
6. **Sampled source agreement.** For 50 randomly sampled 2026 relief appearances, stratified across postseason, doubleheaders and traded pitchers:
   - pitches, outs, BF and ER match the MLB boxscore exactly;
   - this needs MLB API access.
7. **Roster reconciliation.** For each club's final game date, the active-bullpen population recorded in that day's published snapshot equals the MLB active roster for that date (`/teams/{id}/roster?date=`), restricted to pitchers. This also verifies EOS-018: Washington's 19 "On Watch".

---

## 3. Historical snapshot quality

| Period | Quality | Evidence |
|---|---|---|
| Through ~Aug 13 | Not visible in this clone | — |
| Aug 13 – Sep 9 | Non-degenerate; high churn (15.6/30 clubs per snapshot) | Prior audit F-06 |
| Sep 10 – Sep 21 | **Stale publication presented as current** | Incident 2026-09-12 |
| Sep 22 – Oct 9 | Plausible in-season and early postseason distributions (for example 10-01: 25 Fresh / 5 Stretched / 0 Vulnerable) | Committed team pages |
| **Oct 10 – present** | **Systematically wrong for non-playing clubs** (EOS-001/002). By data-through 10-11, 19 clubs read Vulnerable; by 10-27, 28 | Committed team pages, §5 of `02` |

**Immutable artifacts affected:**
- 1,436 `team_state` share artifacts carry data-through ≥ 2026-09-29: 747 Vulnerable, 393 Fresh, 296 Stretched.
- The subset that is wrong is every artifact for a club *not active* on that artifact's product date whose decisive inputs were majority `stale`. G-2.3 computes the exact list.

**Duplicate artifacts:**
- Artifacts are generated per publication, not per change (EOS-013).
- For an idle club, October produced about 2 identical artifacts a day.
- Their historical meaning is identical, so the archive should cite one canonical artifact per club per distinct read.

---

## 4. Postseason handling

| Requirement | Current behaviour | Status | Fix |
|---|---|---|---|
| Classify regular vs postseason games | `game_type` stored per game and log; readers default unknown to `R` in 4 modules | Partial | Phase allowlist; no defaulting (EOS-023) |
| Postseason roster | Active-roster flag only | Partial | Club-status model (EOS-M01) |
| Postseason workload | Counted | OK | — |
| Postseason roles | Excluded → Role Unclear | **Defect** (EOS-006) | Phase-scoped evidence |
| Postseason performance | Excluded from season ERA/WHIP | OK per 02:269 | Archive may show a separate postseason line |
| Rolling windows across the season boundary | Continuous across 09-27 → October | OK for workload; wrong for roles | Phase boundaries for role evidence |
| Eliminated clubs | Published as current | **Defect** (EOS-002) | Season-complete state |
| Fewer than 30 clubs active | The proof requires exactly 30 Team States | **Defect** (design) | Proof requires one read per *active* club and one archive record per inactive club |
| Final game handling / conditional games | Conditional-game retirement implemented | OK | — |
| Champion and final standings | Not stored or shown | Missing | Season closure record |

---

## 5. Data preservation risks

| Risk | Likelihood | Impact | Mitigation | Phase |
|---|---|---|---|---|
| Loss of the production DB (no proven backup) | Low | **Catastrophic** (the 2026 record is the year-two asset) | Off-provider dump plus PITR confirmation plus a restore drill (EOS-009) | 0 |
| Credential misuse via the public repo / unprotected `main` | Low–Medium | Catastrophic | EOS-010 | 0 |
| Fences block corrections of rows the integration runtime adopted | Medium | Silent wrong history | Fence audit and removal (EOS-016) | 0 (audit), 3 (removal) |
| Postseason game missed beyond the 2-day lookback | Low–Medium | Permanent ledger gap | G-1.1 now, while the season is fresh | 0 |
| Perishable probables history | Certain (not stored) | Lost context | Store daily from 2027 (EOS-M08) | 5 |
| Raw payloads not archived | Certain | Re-derivation depends on MLB keeping the data | Archive final boxscore/PBP JSON (EOS-M08) | 3 |
| Snapshot growth forces ad-hoc deletion later | Medium | An unplanned purge could remove published history | Retention policy that keeps all published snapshots (EOS-015) | 3 |
| Wrong October reads cited externally | Already happened (unknown reach) | Credibility | Correction notices (EOS-003) | 0 |

---

## 6. Correction and archival requirements

1. **Correct, don't erase.**
   - Under the Constitution, published artifacts are superseded or withdrawn, never edited.
   - Use `share_artifacts.superseded_at` / `withdrawn_reason`, with a public correction note:
     > "This read treated relievers without recent appearances as constrained. The club's season had ended on <date>. Corrected <date>."
2. **A season-closure record per club**, frozen and hashed:
   - final game date and type;
   - final active bullpen;
   - season totals (relief IP, pitches, appearances);
   - multi-day pattern counts;
   - observed role timeline;
   - the corrected Team State timeline;
   - postseason workload.
3. **Corrected Team State timeline.** For dates when a club was not active, the timeline shows "season complete", not a state. For dates when it was active, it keeps the original published state unless it was affected by EOS-001. For in-season stale arms (for example an injured-list return), re-derive the state and mark it "restated".
4. **The archive is versioned:** `season_archive_version`, with the rule version that produced it.

---

## 7. End-of-season finalization process

To run after the World Series final, and repeat each year.

| Step | Action | Executable check |
|---|---|---|
| F-0 | Freeze: disable game-day crons (postgame, continuous, shadow); keep the daily roster/transaction sync | Render inventory shows only the offseason jobs (EOS-030) |
| F-1 | Back up: off-provider dump of the canonical tables plus a restore drill | G-1.0 |
| F-2 | Reconcile: run G-1.1 … G-1.7; repair through the governed path; re-run until green | All G-1 queries return 0 exceptions |
| F-3 | Fence audit: confirm no 2026 row is protected from `main` corrections | G-1.8 |
| F-4 | Close: write a `season_closures` record (counts plus content hash) for the league and each club, including the champion | Record exists; its hash is reproducible from the tables |
| F-5 | Correct: issue supersession notices for EOS-001-affected artifacts | G-2.3 list fully superseded |
| F-6 | Archive publish: generate the season-summary read models; switch the phase to `OFFSEASON` | G-3 offseason checks pass |
| F-7 | Record: ledger entry in Roadmap 05 plus a one-page closeout in `docs/audits/` | File present |

The order matters. F-1 precedes any data-touching step. F-2 precedes F-4. F-5 and F-6 need the EOS-001/EOS-002 code fixes deployed first.
