# 07 — Verification and Launch Gates

Executable checks are preferred over declarations.

- **SQL** uses real table and column names from `backend/models/` (`game_logs`, `scheduled_games`, `share_artifacts`, `dashboard_snapshots`, `pitchers`). Run it **read-only** against production, or against a restored copy (preferred).
- **Assumption to confirm once:** `scheduled_games.team_id` and `game_logs.appearance_team_id` both carry MLB team IDs (`models/scheduled_game.py:45`, `models/game_log.py:155`).
- **Scripts** under "proposed" do not exist yet. Their contract is defined here and they are built in the referenced WP.
- **A gate passes only when every check in it passes.**

Status values: **PASS / FAIL / NOT RUN.** At audit time every gate is NOT RUN; the production database was unreachable.

---

## G-1 — 2026 data integrity (WP-0.6)

**G-1.0 Backup and restore proven (EOS-009).**
- Restore last night's off-provider dump into a scratch database.
- Run G-1.1–G-1.7 on *both* databases.
- The outputs must be identical.

**G-1.1 Every final 2026 game has appearance coverage for both clubs.**

```sql
SELECT sg.game_pk, sg.team_id, sg.game_date, sg.game_type
FROM scheduled_games sg
WHERE sg.game_date BETWEEN '2026-03-01' AND '2026-11-15'
  AND sg.game_type IN ('R','F','D','L','W')
  AND sg.status_state = 'final'
  AND NOT EXISTS (
        SELECT 1 FROM game_logs gl
        WHERE gl.mlb_game_pk = sg.game_pk
          AND gl.appearance_team_id = sg.team_id)
ORDER BY sg.game_date;
```

**Pass:** 0 rows. Each exception is resolved through the governed repair path or documented as a source anomaly.

**G-1.2 Game counts match the official schedule.**

```sql
SELECT game_type, count(DISTINCT game_pk)
FROM scheduled_games
WHERE game_date BETWEEN '2026-03-01' AND '2026-11-15'
  AND status_state = 'final'
GROUP BY game_type;
```

**Pass:**
- `R` = 2,430 minus terminal cancellations recorded under decision 2026-09-28.
- `F + D + L + W` equals the MLB postseason game count, verified once against `statsapi.mlb.com/api/v1/schedule?sportId=1&season=2026&gameType=F,D,L,W`.

**G-1.3 Postseason appearances present.**

```sql
SELECT gl.game_type, count(*) AS appearances, count(DISTINCT gl.mlb_game_pk) AS games
FROM game_logs gl
WHERE gl.game_date >= '2026-09-29'
GROUP BY gl.game_type;
```

**Pass:** the `games` value for postseason types equals G-1.2's postseason count.

**G-1.4 Exactly one starter per club per game.**

```sql
SELECT mlb_game_pk, appearance_team_id, sum(coalesce(games_started,0)) AS starters
FROM game_logs
WHERE game_date >= '2026-03-01'
GROUP BY 1,2
HAVING sum(coalesce(games_started,0)) <> 1;
```

**Pass:** 0 rows. Openers count as starters by the official record.

**G-1.5 Appearance-team authority resolved.**

```sql
SELECT appearance_team_status, count(*)
FROM game_logs
WHERE game_date >= '2026-03-01'
GROUP BY 1;
```

**Pass:** no unresolved or null status.

**G-1.6 Pitch-count completeness.**

```sql
SELECT count(*)
FROM game_logs
WHERE game_date >= '2026-03-01'
  AND pitches_thrown IS NULL;
```

**Pass:** 0, or each exception listed with a source reason.

**G-1.7 Sampled source agreement** (requires MLB API).
- Proposed script `backend/scripts/verify_appearance_sample.py --season 2026 --n 50 --strata postseason,doubleheader,traded`.
- It compares `pitches_thrown`, `innings_pitched_outs`, `batters_faced`, `earned_runs`, `inherited_runners` against `/game/{pk}/boxscore`.

**Pass:** 50 of 50 exact.

**G-1.8 No fence protects 2026 rows from `main` corrections (EOS-016).**
- Run `backend/services/fence_audit.py` read-only.

**Pass:** 0 rows owned by a non-`main` writer. Before WP-3b.1, any rows found must be listed explicitly with a remediation plan.

**G-1.9 Handedness complete (EOS-024).**

```sql
SELECT count(*)
FROM pitchers p
WHERE p.throws IS NULL
  AND EXISTS (
        SELECT 1 FROM game_logs g
        WHERE g.pitcher_id = p.id AND g.game_date >= '2026-03-01');
```

**Pass:** 0.

---

## G-2 — Offseason correctness: stop false reads (WP-0.1, WP-0.7)

**G-2.1 No current read for a non-active club.**
- Proposed script `backend/scripts/check_active_club_reads.py --snapshot latest`.
- For each club in the published snapshot carrying a Team State, assert *either*:
  - a final game in the 3 days before `availability_reference_date`; *or*
  - a scheduled game in the 3 days after it.

**Pass:** 0 violations. Run against snapshot 5656 inputs, the post-fix code yields exactly MIL and TB as active.

**G-2.2 Inactivity never constrains.**

```bash
python -m pytest backend/tests -k "stale and team_state" -q
```

The test must exist (WP-0.1). It builds clubs idle for 15, 30 and 150 days and asserts no Monitor / Limited / Avoid / Unavailable comes from the `stale` data state, and no Vulnerable or Stretched state.

**G-2.3 The affected-artifact list is computed and fully superseded.**

```sql
SELECT sa.public_id, sa.team_id, sa.product_date, sa.lifecycle_state
FROM share_artifacts sa
WHERE sa.artifact_type = 'team_state'
  AND sa.product_date >= '2026-09-28'
  AND NOT EXISTS (
        SELECT 1 FROM scheduled_games sg
        WHERE sg.team_id = sa.team_id
          AND sg.status_state = 'final'
          AND sg.game_date BETWEEN sa.product_date - 3 AND sa.product_date)
ORDER BY sa.product_date;
```

**Pass:** every row has `lifecycle_state = 'superseded'` with `superseded_at` set, *and* the static page shows a correction banner. Spot-check 10 with `curl`.

**G-2.4 Plausibility gate replay.**
- Feed the published snapshots for data-through 2026-10-10 … 2026-10-27 (IDs 4731 … 5656) through the new gate (WP-0.2).

**Pass:** the gate blocks or alerts on every one.

**G-2.5 Public-page regression from committed artifacts.** This runs today, with no database needed:

```bash
for t in frontend/public/team/*/; do
  grep -o 'team-state" content="[^"]*"' "$t/index.html"
done | sort | uniq -c
```

**Pass after WP-0.1:** during the offseason, no team page carries a current `team-state` meta. Pages show `season-complete` with the club's final game date.

---

## G-3 — Offseason product (Phase 1)

| ID | Check | Pass |
|---|---|---|
| G-3.1 | `GET /api/season/state` | `phase = "OFFSEASON"`, champion set, every club `status ∈ {eliminated, not_qualified, champion}`, `final_game_date` per club |
| G-3.2 | Phase transitions unit test: synthetic schedules for 09-27 (regular end), 10-19 (LCS end), WS final, first spring game, Opening Day | Each transition fires on the correct date and per-club status is correct |
| G-3.3 | Archive coverage: `GET /api/teams/{id}/season/2026` for all 30 | 30 × 200; every payload includes relief IP, pitches, appearances, multi-day pattern counts, role timeline, corrected Team State timeline |
| G-3.4 | Archive reproducibility: rebuild the archive twice from the restored DB | Byte-identical payload hashes |
| G-3.5 | No current-read language in offseason HTML | Playwright: `/`, `/dashboard`, `/team/NYY`, `/bullpen?team=NYY` contain none of "tonight's", "today", "after recent work", "available now" |
| G-3.6 | Transactions feed: a known 2026-11 reliever transaction appears within 24 h | Manual check against the MLB transactions page |

---

## G-4 — Team Board performance (WP-3a.1)

| ID | Check | Pass |
|---|---|---|
| G-4.1 | Proposed `scripts/measure_board_latency.py --base https://<api> --teams all --runs 5`, reporting server-timing p50/p95 cold and warm | p95 warm < 300 ms; p95 cold < 1.5 s |
| G-4.2 | Memory: one board request does not load the full league snapshot (code assertion test: a query-count / loaded-bytes guard) | Loaded payload < 1 MB per request |
| G-4.3 | Frontend time-to-useful-content on a throttled mobile profile (Playwright + CPU 4× / Fast 3G), first reliever row visible | < 3.0 s on a production URL |

---

## G-5 — API, publication and historical reproducibility

| ID | Check | Pass |
|---|---|---|
| G-5.1 | Rule single-sourcing: a grep test fails if any numeric workload threshold appears outside `services/workload_rules.py` (allowlist for tests) | 0 hits |
| G-5.2 | Board/Team State consistency: for every club in the latest snapshot, the board On-Watch count equals the Team State moderate count, and the evidence item #1 key equals the decisive rule | 30/30 (or all active clubs) |
| G-5.3 | Historical reproducibility: re-render 20 random 2026 share artifacts from stored payloads | Integrity hashes match |
| G-5.4 | Publication atomicity: kill the publisher mid-run in a scratch DB | The previous snapshot still serves; no partial pointer |
| G-5.5 | Contract test: the real `run_due_sync.py` summary shape is accepted by every consumer (EOS-007) | Green |

---

## G-6 — Mobile UX and accessibility

| ID | Check | Pass |
|---|---|---|
| G-6.1 | Playwright at 390 / 768 / 1440 px on `/`, `/dashboard`, `/team/MIL`, a pitcher page, `/methodology`, `/trust`, a share page | No horizontal overflow; one H1 each |
| G-6.2 | axe-core on the same routes | 0 serious or critical violations |
| G-6.3 | First screen at 390 px on `/team/<club>` in season (replayed date) | ≥ 8 named relievers with yesterday's pitches, 3-day pitches and rest read, without scrolling |
| G-6.4 | API-down render | Each route shows the designed unavailable state; no raw "API 500", "sync", "snapshot" or "publication" text |
| G-6.5 | Forbidden public terms in the built public entry chunk | 0 occurrences of the forbidden list |

---

## G-7 — All-30-team coverage

| ID | Check | Pass |
|---|---|---|
| G-7.1 | In season: every active club has exactly one Team State or a fail-closed `data_limited` with a stated reason | 30/30 on 7 consecutive replayed dates |
| G-7.2 | The team universe is exactly the 30 MLB clubs (no affiliates) in rosters, publications and the sitemap | Exactly 30 |
| G-7.3 | Each club's active bullpen population equals the MLB active-roster pitchers minus starters per the rotation authority, for a sampled date (MLB API) | 30/30 match, or each difference explained |

---

## G-8 — Operational reliability

| ID | Check | Pass |
|---|---|---|
| G-8.1 | Scheduled workflow health: last 14 scheduled runs | ≥ 13/14 green; any red has a real public-sync cause |
| G-8.2 | Alert drill: simulate a stale `data_through` / missed publication | Founder notified within 6 h |
| G-8.3 | `main` protection: attempt a direct push from a non-allowlisted token | Rejected |
| G-8.4 | Secrets scope: a workflow on a non-`main` branch echoes whether `DATABASE_URL` is set (masked) | Not set |
| G-8.5 | Rate limit: 10 `request-link` calls for one email in 1 minute | 429 after the limit; no `users` row before verification |
| G-8.6 | CI with the clock set to 2026-11-14 | Green |
| G-8.7 | Backend suite with outbound network denied | Green |
| G-8.8 | Infrastructure inventory: `render.yaml` or inventory doc matches the Render dashboard | Manual sign-off |
| G-8.9 | Workflow count and secret holders | ≤ 8 workflows; only the sync, distribution and maintenance workflows reference production secrets |

---

## G-9 — 2027 preseason transition (WP-5.1–5.3)

| ID | Check | Pass |
|---|---|---|
| G-9.1 | Spring games never enter workload: replay 2026-02-20 … 03-25 | 0 workload rows from `game_type IN ('S','E')` contribute to availability |
| G-9.2 | Phase flips to `SPRING_TRAINING` on the first spring game and to `OPENING` on the first regular-season date | Correct dates in replay |
| G-9.3 | Opening Day semantics: on day 1 every active reliever is "rested by absence"; Team State reflects roster composition only | No Vulnerable or Stretched caused by inactivity, for all 30 clubs |
| G-9.4 | Day-2 behaviour: after Opening Day games, the arms that pitched carry correct workload; the rest stay rested | Matches the boxscores for 5 sampled clubs |
| G-9.5 | In-season jobs restarted; the offseason-only jobs stopped | Render inventory |
| G-9.6 | Full rehearsal: restore backup → replay 2026-03-26 … 04-05 → all G-2, G-5, G-7 checks pass | All green |

---

## G-10 — Opening Day readiness (go/no-go, 7 days before)

| ID | Check | Pass |
|---|---|---|
| G-10.1 | G-1 through G-9 | All PASS |
| G-10.2 | Live smoke on production: `/`, `/team/<each of 30>`, `/share/<10 random>` return 200 and correct Open Graph metadata; unfurl verified in one third-party client | 100% |
| G-10.3 | `/team/NYY` without JavaScript shows club, phase, date and named arms; canonical is self | Yes |
| G-10.4 | Demand baseline committed; kill criteria adopted; creator-trial list (≥15 names) ready | Yes |
| G-10.5 | Restore drill repeated within 30 days of Opening Day | Yes |
| G-10.6 | Founder ops budget agreed (for example, ≤ 20% of hours on operations in April) and the alert route tested | Yes |

**No-go rule:** any FAIL in G-2, G-8.1–8.4 or G-9.3 blocks launch publication. BaseballOS then runs in archive mode until it is fixed. The Constitution prefers silence to a wrong read.
