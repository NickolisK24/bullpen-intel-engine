# 05 — 2026–2027 Offseason Roadmap

**Status:** Proposal from the 2026 end-of-season audit. It becomes execution authority only when the founder adopts it into the canonical Roadmap & Decision Ledger (05). It does not supersede governing decisions; the decisions it depends on are in `06_DECISION_REGISTER.md`.

## Planning assumptions

- **Capacity:** one founder-engineer at about 25 focused hours a week, roughly 3 engineer-days.
- **Effort unit:** engineer-days (d) for that person, including tests and deployment, excluding waiting.
- **Opening Day 2027:** assumed late March 2027; the exact date is to be confirmed from the MLB schedule. Spring training games are assumed from late February.
- **Discipline:** **one active objective at a time** (Roadmap principle 12).
  - Each work package (WP) is an independently shippable vertical slice with its own acceptance test.
  - Date-bound exceptions may run in parallel only when they are mechanical: WP-0.4 (React Router, deadline 2026-11-13) and WP-0.5 (backup).
- **Gate references:** `G-x` refers to `07_VERIFICATION_AND_LAUNCH_GATES.md`; `EOS-x` refers to `03`.

## Sequencing correction relative to the requested phase order

The requested order is 0 → 1 → 2 → 3 → 4 → 5. The evidence requires three changes:

1. **Operational safety items move from Phase 3 into Phase 0:**
   - backup and restore (EOS-009);
   - a single alert (EOS-008);
   - branch protection and secrets (EOS-010);
   - React Router (EOS-012).

   Every season-close data change depends on a proven restore path. Every fix needs CI to work after 2026-11-13.
2. **The pipeline consolidation *decision* (DEC-04) moves before Phase 1.** The season-phase model touches publication. Building it into a pipeline that might be replaced wastes the offseason. The *execution* (shutting down shadow lanes, fence removal) stays in Phase 3, except stopping the 3-minute crons, which is trivial and goes in Phase 0.
3. **Phase 3 reliability items that Phase 2 depends on run first:** the Team Board per-team read model (EOS-014) and the unified workload rules (EOS-017). The Phase 2 Team Board redesign builds on them.

Effective order: **0 → 1 → 3a → 2 (with 3b interleaved) → 5**, with Phase 4 only as stretch.

## Critical path

```
WP-0.1 stop false reads ─┐
WP-0.5 backup/restore ───┼─> WP-0.6 season finalization ─> WP-1.1 phase model ─> WP-1.2 archive ─> WP-1.3 offseason home
WP-0.4 React Router ─────┘                                        │
                                                                  └─> WP-5.1 spring transition ─> WP-5.3 Opening Day rehearsal ─> LAUNCH
WP-3a.1 per-team board read model ─> WP-2.1 mobile Team Board ─> WP-2.2 named-arm What Changed ─────────┘
```

### Capacity tiers (the founder must choose one before Phase 0 exits)

Effort totals are summed from the WP tables below.

| Tier | Work packages | Effort | Fits before about 2027-03-25 at |
|---|---|---|---|
| **Minimum (safe launch)** | WP-0.1–0.7, WP-1.1, WP-1.3, WP-1.5, WP-3a.2, WP-2.1, WP-5.1, WP-5.3 | **46–62 d** | about 3 d/week (about 63 d available) |
| **Core (recommended)** | Minimum + WP-1.2, WP-1.6, WP-3a.1, WP-2.2, WP-2.4, WP-3b.1, WP-3b.2, WP-5.2 | **80–105 d** | about 5 d/week (about 105 d available) |
| **Full** | Every WP in Phases 0, 1, 3a, 2, 3b, 5 (adds WP-1.4, WP-2.3, WP-2.5, WP-3b.3–3b.5, WP-5.4) | **102–133 d** | Does not fit; the remainder rolls into in-season maintenance windows |
| Stretch | Phase 4 | 16–24 d | Only if ahead of plan |

**How the Minimum tier relaxes dependencies:**
- WP-2.1 ships on the existing read path. Board latency stays unaddressed: EOS-014 remains open and G-4 is waived.
- The full 2026 archive (WP-1.2) is replaced by the WP-1.3 season-complete state, which shows each club's final read and season totals.

**Recommendation: Core.** Under it, the launch answers the governing question:
- named-arm What Changed;
- indexable team pages;
- one pipeline;
- no HTML in git.

Under the Minimum tier BaseballOS is *correct* on Opening Day but not yet *preferred*.

**Calendar (Core tier, about 5 d/week):**

| Window | Phase |
|---|---|
| Oct 29 – Nov 21 | Phase 0 (20–28 d) |
| Nov 22 – Dec 19 | Phase 1 (20–25 d) |
| Dec 22 – Jan 9 | Phase 3a (10–13 d) |
| Jan 10 – Feb 13 | Phase 2 (21–27 d), interleaved with WP-3b.1 and WP-3b.2 |
| Feb 16 – Opening Day | Phase 5 (10–14 d) |

---

## Phase 0 — Critical production correctness and season-close integrity

**Objective:** BaseballOS stops publishing false claims; the 2026 record is safe, complete and closed; the founder gets told when things break.
**Window:** now → about 2026-11-21. **Total:** about 20–28 d.

| WP | Work package | Priority | Depends on | Files / systems likely affected | Effort |
|---|---|---|---|---|---|
| WP-0.1 | **Stop false current reads.** (a) Emergency per-club gate: publish a current Team State only for clubs with a final game in the last N days *or* a scheduled game in the next N days (N = 3), otherwise emit a `season_complete` read with the club's final game date. (b) The `stale`/`missing` data state never enters the moderate/severe partition (EOS-001). (c) The decisive rule becomes evidence #1 (EOS-005) | P0 | DEC-01 (interim), DEC-02 | `services/availability.py`, `team_operations/bullpen_readiness.py`, `team_operations/contracts.py`, `services/published_team_state.py`, `services/team_story_previews.py`, `services/bullpen_board.py`, frontend Team State rendering (render-only) | 5–7 d |
| WP-0.2 | **Plausibility gate plus alerting.** Block publication on the EOS-004 rules; one external check on served `data_through`, missed publications and API health → email/phone (EOS-008); backend Sentry | P0 | WP-0.1 | `services/dashboard_snapshot.py` (gate), new `scripts/check_public_freshness.py` + scheduled job or external monitor | 3 d |
| WP-0.3 | **Make red mean broken.** Remove or repair the `shadow-activation-health` job (EOS-007); stop the 3-minute shadow crons on Render (DEC-04); make internal enrichment skip on a no-op (EOS-027) | P0 | DEC-04 | `.github/workflows/baseballos-sync.yml`, `scripts/validate_game_driven_shadow_cycle.py`, Render dashboard | 1–2 d |
| WP-0.4 | **React Router v7 migration** before 2026-11-10 (EOS-012) | P0 (date-bound) | — | `frontend/package.json`, `src/App.jsx`, router imports; `.github/dependency-audit-accepted.json` | 2–3 d |
| WP-0.5 | **Backup and restore proof plus repository security.** Confirm PITR; off-provider dump; restore drill; protect `main` (bot allowlisted); production secrets moved to a `production` environment; distinct `USER_AUTH_SECRET`; read-only DB role for diagnostics; rate limits on auth/signup/traffic (EOS-009, EOS-010, EOS-011) | P0 | — | Supabase/Render consoles; GitHub settings; `backend/config.py`; `backend/api/auth.py`, `audience.py`, `traffic.py`; new `docs/current/RESTORE_RUNBOOK.md` | 4–5 d |
| WP-0.6 | **2026 season finalization** (`04` §7, F-0…F-4, F-7): reconcile all 2026 games including the postseason, fence audit, `season_closures` record | P0 | WP-0.5, World Series final | New `services/season_closure.py` + migration; `services/fence_audit.py`; G-1 SQL | 4–6 d |
| WP-0.7 | **Correct the record** (F-5): supersede the EOS-001-affected artifacts with a public correction note; re-export static pages; note on Data & Trust | P0 | WP-0.1, DEC-03 | `services/share_artifact_operations.py`, the artifact page template, Trust page | 1–2 d |

**User benefit:** no false claims; corrections visible; a safe 2026 record.

**Acceptance tests:**
- G-2.1 … G-2.4 (offseason correctness);
- G-1.0 … G-1.8 (2026 integrity);
- G-8.1 … G-8.4 (operational);
- CI passes with the clock at 2026-11-14.

**Exit criteria:**
1. No current Team State for a non-active club in the published snapshot.
2. 7 consecutive green scheduled runs.
3. An alert fired in a drill.
4. A restore drill reproduced the canonical counts.
5. The `season_closures` 2026 record exists.
6. All affected artifacts superseded.

**Deferred out of Phase 0:**
- the full phase state machine (Phase 1);
- fence *removal* (Phase 3b; Phase 0 only audits);
- deleting workflows (Phase 3b; Phase 0 only removes production secrets from them).

---

## Phase 1 — Offseason state and historical product continuity

**Objective:** a correct, useful offseason product that preserves 2026 meaning and is ready to turn into 2027.
**Window:** about 2026-11-22 → 12-19. **Total:** about 20–25 d.

| WP | Work package | Priority | Depends on | Files / systems | Effort |
|---|---|---|---|---|---|
| WP-1.1 | **Season-phase and club-status model** (EOS-M01; DEC-01): `REGULAR_SEASON / POSTSEASON / SEASON_COMPLETE / OFFSEASON / SPRING_TRAINING / OPENING`; per-club `active / eliminated / not_qualified / champion`; game-type allowlist per phase (EOS-023); served at `GET /api/season/state`; replaces the WP-0.1 interim gate | P0 | WP-0.1, DEC-01 | New `services/season_phase.py`; `availability_reference_date.py` (per-club reference); `mlb_api.py` (season from the schedule, not the clock); `slate_coverage.py` (remove the month heuristic); frontend render-only | 5–6 d |
| WP-1.2 | **2026 archive read models and pages** (EOS-M03): per-club season summary, reliever season pages, corrected Team State timeline, postseason line | P0 | WP-0.6, WP-1.1 | `services/team_state_history.py`, new `services/season_archive.py`, `api/team_history.py`, `frontend/src/components/history/*` | 7–9 d |
| WP-1.3 | **Offseason home and `/team/{ABBR}` offseason state**: "2026 season complete", the champion, the 30-club archive strip, next-season dates; Tonight / League Board show the phase instead of "no games" | P0 | WP-1.1, WP-1.2 | `components/tonight/*`, `components/dashboard/*`, `public_team_distribution.py` | 3–4 d |
| WP-1.4 | **Offseason bullpen transactions feed**: signings, DFAs, trades, non-tenders involving relievers on 40-man rosters | P1 | WP-1.1 | `services/public_recent_transactions.py`, `transaction_ingestion.py` | 2–3 d |
| WP-1.5 | **Demand baseline** (EOS-M04) and kill criteria (DEC-09): a readout of 2026 external visitors, different-day returners and team-board repeat visits | P0 (decision input) | — | `services/traffic_reporting.py` (read-only query), new `docs/audits/2026-demand-baseline.md` | 1 d |
| WP-1.6 | **Label outcome validation** (EOS-M05): did Unavailable / Limited Rest arms pitch less often the next day than Clean Options in 2026? | P1 | WP-0.6 | Read-only analysis script under `backend/scripts/` | 2 d |

**User benefit:**
- Fans and creators get a 2026 bullpen season record for every club, a clear season status, and offseason roster context.
- No false current reads.

**Acceptance tests:**
- G-3.1 … G-3.6 (offseason correctness);
- G-5.3 (history reproducibility);
- G-6.1 (archive pages, mobile/a11y).

**Exit criteria:**
1. `GET /api/season/state` returns `OFFSEASON` with the champion set.
2. All 30 archive pages render at 390 px with no current-read language.
3. The demand baseline is committed.
4. Kill criteria are adopted.

**Deferred:** archive visual polish; year-over-year comparisons (Phase 4); pitch-quality archive views (Phase 4).

---

## Phase 3a — Performance and rules foundations (pulled forward)

**Objective:** give the Phase 2 Team Board work a fast, single-source foundation.
**Window:** about 2026-12-22 → 2027-01-09. **Total:** about 10–13 d.

| WP | Work package | Priority | Depends on | Files / systems | Effort |
|---|---|---|---|---|---|
| WP-3a.1 | **Per-team Team Board read model** (EOS-014): serve from a per-team row (`team_public_publications`) or a JSON-path projection; server-timing headers; p95 budget | P0 | — | `api/team_board_v2.py`, `services/team_board_delivery.py`, `services/dashboard_snapshot.py`, `services/public_serving_authority.py` | 5–6 d |
| WP-3a.2 | **One workload-rules module** (EOS-017) consumed by availability, public copy, methodology and the API; one population and one classifier (EOS-018); remove frontend-derived semantics (EOS-019) | P0 | WP-0.1 | New `services/workload_rules.py`; `availability.py`, `public_team_relief_work.py`, `workload_recovery_evidence.py`, `pitcher_role.py`, `bullpen_board.py`; `frontend/src/adapters/operatingStateReadModel.js`, `utils/pitcherLabels.js`, `utils/bullpenConcepts.js` | 5–7 d |

**Acceptance tests:**
- G-4.1 … G-4.3 (Team Board performance);
- G-5.1 (rule single-sourcing).

**Exit criteria:**
1. Board API p95 under 300 ms warm on production-size data.
2. One definition per rule.
3. The On-Watch count equals the partition's moderate count.

---

## Phase 2 — Core product experience and intelligence gaps

**Objective:** a serious baseball person prefers the Team Board to their box score + RosterResource + game-log routine.
**Window:** about 2027-01-10 → 02-13. **Total:** about 21–27 d.

| WP | Work package | Priority | Depends on | Files / systems | Effort |
|---|---|---|---|---|---|
| WP-2.1 | **Mobile-first Team Board** (EOS-I01): the first 390 px screen is the active bullpen table with inline receipts (yesterday's pitches, 3-day pitches, consecutive days, days since last outing, rest read, role); everything else collapses below | P0 | WP-3a.1, WP-3a.2 | `frontend/src/components/team/*`, `adapters/teamBoardV2.js` | 6–8 d |
| WP-2.2 | **Named-arm What Changed** (EOS-I02): "<arm> → Limited Rest after 31 pitches Monday"; roster moves; league-wide version on home | P0 | WP-3a.2 | `services/what_changed_since_yesterday*.py`, `team_board_what_changed.py`, frontend | 4–5 d |
| WP-2.3 | **Postseason-aware roles and a descriptive late-inning hierarchy** (EOS-006, EOS-M07): phase-scoped role evidence; "finishing games / 8th-or-later entries, last 14 days" with counts and dates (resolves O-004/O-009 descriptively) | P1 | WP-1.1 | `services/pitcher_role_authority.py`, `pitcher_role.py`, `role_movement.py`, `bullpen_eligibility.py` | 5–6 d |
| WP-2.4 | **Indexable `/team/{ABBR}`** (EOS-022): real canonical route, prerendered summary (phase, state or archive, key named arms, date), sitemap `lastmod`, no `source=share` on organic visits | P1 | WP-1.3 | `frontend/public/team/*` generator → prerender/edge; `vercel.json`; `public_team_distribution.py` | 4–5 d |
| WP-2.5 | **Public copy cleanup and designed failure states** (EOS-020, EOS-028): forbidden-term test; one unavailable-state component; navigation reduced to ≤6 lanes | P1 | — | Frontend copy and components; `hooks/useFetch.js` | 2–3 d |

**User benefit:** the core answer is on one phone screen, with "what changed" in names and a citable, findable team URL.

**Acceptance tests:** G-6.1 … G-6.5 (mobile UX, a11y); G-4.x; G-5.2.

**Exit criteria:**
1. On a 390 px viewport, the first screen of `/team/MIL` (replaying a 2026 date) shows ≥ 8 named relievers with receipts.
2. What Changed names arms.
3. `/team/NYY` is crawlable without JavaScript.

**Deferred:** Compare redesign; Stories rework (demote); Matchup polish.

---

## Phase 3b — Reliability and maintainability

**Objective:** an operable platform for one person.
**Window:** WP-3b.1/3b.2 interleaved with Phase 2 (Core tier); WP-3b.3–3b.5 are Full-tier and run in post-launch maintenance windows if not reached. **Total:** about 21–26 d.

| WP | Work package | Priority | Depends on | Files / systems | Effort |
|---|---|---|---|---|---|
| WP-3b.1 | **Pipeline consolidation execution** (DEC-04; EOS-016): archive the `feat/sync-pipeline` branch (tag plus summary doc); delete its Render service; remove the fence triggers after audit; freeze or remove the CU shadow code paths and workflows; one documented writer; commit `render.yaml` (EOS-030) | P0 | DEC-04, WP-0.6 | Migrations (drop triggers), `services/fence_audit.py`, `services/continuous_*.py`, `game_driven_*.py`, workflows, Render | 5–7 d |
| WP-3b.2 | **Distribution out of git** (DEC-05; EOS-013): artifacts only on change (`equivalence_key`); `/share/{id}` and `/team/{ABBR}` metadata served by API or edge; historical pages to object storage; stop bot commits; then require PRs on `main` | P0 | WP-2.4, DEC-05 | `services/distribution_delivery.py`, `share_artifact_previews.py`, `baseballos-generated-distribution.yml`, `vercel.json` | 5–6 d |
| WP-3b.3 | **Retention and hygiene** (EOS-015, EOS-031): retention job (keep all published), indexes, `jsonb`; archive 12 `*_2026.py` modules and about 20 workflows; delete unused routes and frontend modules; code-split admin routes (EOS-021) | P1 | WP-3b.1 | `backend/services/*_2026.py`, `.github/workflows/*`, `api/bullpen.py`, `frontend/src/App.jsx` | 5–6 d |
| WP-3b.4 | **Hermetic tests and auth hardening** (EOS-026, EOS-025, EOS-033): network-deny fixture, frozen clock, single-use links, token revocation, security headers, fail-closed `APP_ENV`, product-clock module | P1 | — | `backend/tests/conftest.py`, `api/auth.py`, `vercel.json`, `app.py` | 4–5 d |
| WP-3b.5 | **Governance reduction** (DEC-08; EOS-029, EOS-035): ledger D-059+, amend 02/03/04 for the phase model, Tonight-as-home and Render; move `CU_*` reports to audits; one `CURRENT_STATE.md` | P1 | Decisions taken | `docs/canonical/*`, `docs/current/*` | 2 d |

**Acceptance tests:** G-8.x (operations), G-5.x, the backend suite green with the network blocked, workflow count ≤ 8.

**Exit criteria:**
1. One production writer.
2. Zero data commits to `main` for 14 days.
3. `main` protected without exceptions.
4. Docs describe production.

**Deferred:** a TypeScript migration (not recommended); a full `sync.py` split (only extract what WP-1.1 touches).

---

## Phase 4 — Advanced differentiation and historical depth (stretch)

**Objective:** depth that no competitor offers descriptively, *only if* Phases 0–3 exit on time.
**Total:** about 16–24 d.

| WP | Work package | Priority | Depends on | Effort |
|---|---|---|---|---|
| WP-4.1 | Pitch-level backfill for 2026-03-26 → 07-03 (EOS-M09), then a "velocity under workload" descriptive context on pitcher pages (EOS-I07) | P2 | WP-3b.1 | 8–12 d |
| WP-4.2 | Creator tools: a copy-ready citation line, an embeddable team card, a share-artifact "cite" button (EOS-I03) | P2 | WP-3b.2 | 3–4 d |
| WP-4.3 | Consecutive-games-without-off-day and schedule-density context | P2 | WP-3a.2 | 2–3 d |
| WP-4.4 | Optional 2025 appearance-ledger backfill for year-over-year context | P3 | WP-0.5 | 3–5 d |

**Deferred to the 2027 season or later:** leverage-weighted analytics beyond descriptive entry context; any new intelligence domain without a stated baseball question.

---

## Phase 5 — Spring training and Opening Day 2027 readiness

**Objective:** a correct, rehearsed transition from offseason to live reads, with the first-30-day measurement plan ready.
**Window:** about 2027-02-16 → Opening Day. **Total:** about 10–14 d.

| WP | Work package | Priority | Depends on | Effort |
|---|---|---|---|---|
| WP-5.1 | **Spring-training transition** (EOS-M06): roster and transaction context; spring games never counted as workload; phase switches automatically from the schedule; the "rested by absence" semantics verified on day 1 | P0 | WP-1.1 | 3–4 d |
| WP-5.2 | Restart in-season jobs (postgame, morning) with the phase switch; store daily probables (EOS-M08); archive final boxscore JSON | P0 | WP-3b.1 | 2–3 d |
| WP-5.3 | **Opening Day rehearsal:** replay 2026-03-26 → 04-05 through the phase model and gates in a scratch database restored from backup; all G-9 gates pass | P0 | WP-5.1, WP-0.5 | 3–4 d |
| WP-5.4 | Creator trial recruitment (15–20 named beat writers and podcasters), the measurement plan (DEC-09), and a post schedule within Standard 06's 3-a-week ceiling | P1 | WP-1.5 | 2–3 d |

**Acceptance tests:** G-9.1 … G-9.6 (preseason), G-10.1 … G-10.6 (Opening Day).

**Exit criteria:** every G-9 and G-10 gate is green 7 days before Opening Day.

---

## Work that should not be done this offseason

| Not doing | Why |
|---|---|
| Finishing the SP-00…SP-14 rewrite or activating CU write authority | No user-visible benefit; NO-GO and BLOCKED today; the founder's offseason is the scarcest resource (DEC-04) |
| New proof, certification or authority layers | Gates already fail closed; the October failure was semantic, not a missing proof |
| Microservices, streaming, queues, new hosting | No measured need; data volume is small |
| TypeScript migration | Contract tests cover payloads; poor value for the offseason |
| Prediction, betting or "likely to pitch" features | Constitution |
| More posting volume or automation | No evidence yet of usefulness or conversion (DEC-09) |
| Rebuilding Stories / narrative generation | Low value; credibility risk (prior audit F-14) |

## Mandatory vs stretch summary

| Class | Definition | Effort (d) |
|---|---|---|
| **Mandatory for any 2027 launch** | Minimum tier | 46–62 |
| **Mandatory for the governing question ("preferred")** | Core tier | 80–105 |
| **Full** | All of Phases 0, 1, 3a, 2, 3b, 5 | 102–133 |
| **Stretch** | Phase 4 | 16–24 |

**Fallback order if the schedule slips:**
1. Drop Phase 4.
2. Drop the Full-only WPs.
3. Drop WP-2.4.
4. Drop WP-1.2 (WP-1.3 shows final reads).
5. Drop WP-2.2.

**Never drop:** WP-0.x, WP-1.1, WP-5.1 or WP-5.3.
