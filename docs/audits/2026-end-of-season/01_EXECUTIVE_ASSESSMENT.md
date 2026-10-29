# 01 — Executive Assessment

**BaseballOS 2026 End-of-Season Platform Audit**
**Date:** 2026-10-29. The World Series (Milwaukee vs Tampa Bay) is in progress.
**Scope:**
- the repository (`main` @ `0c90be9b`, plus the `feat/sync-pipeline` branch and the unmerged 2026-09-24 viability-audit branch);
- production outputs committed to git by automation;
- the GitHub Actions run history for Oct 7–28;
- local test and build runs;
- web research on competitors.

**Not observable in this audit:** baseballos.app, the production API, the MLB Stats API, Render, Vercel, Supabase, analytics, Metricool. The session network policy blocked them; see `08` for the list.

Findings are cited by ID from `03_FINDINGS_REGISTER.md`.

---

## 1. Verdict

**Overall platform score: 39 / 100. The platform is not ready for offseason mode, and as of today it publishes false baseball claims.**

BaseballOS has a sound data backbone, and a strictly descriptive, citable positioning that no competitor occupies. It is also currently publishing that 28 of 30 MLB bullpens are "Vulnerable", during the World Series, for clubs that have not played in up to a month.

- **Cause:** the core classifier treats *a reliever who hasn't pitched* as *a reliever who is constrained* (EOS-001).
- **Missing model:** the product has no concept of a season ending, a club being eliminated, or a club having no next game (EOS-002).
- **No catch:** no gate caught it (EOS-004) and no alert fired (EOS-007, EOS-008).
- **Permanent record:** about 750 frozen "Vulnerable" share artifacts now carry the error (EOS-003).

This is not a cosmetic issue. It violates the Constitution's core promise: "quieter under uncertainty, never wronger" (01:140), and "A stale value is never presented as current" (02:685).

The good news is that the fix is small and well-located. The platform's problem is not a lack of engineering. Its problems are:

- a missing *season model*;
- two unfinished replacement pipelines (EOS-016);
- a deploy pipeline built on committing HTML to git (EOS-013);
- a governance system that no longer tracks reality (EOS-029);
- no measurement of whether anyone uses the product (EOS-M04).

## 2. Scorecard

The scoring method and confidence are explained in `02_FULL_PLATFORM_AUDIT.md` §16. Scores are capped where the evidence is UNVERIFIED.

| # | Category | Score | Confidence | One-line basis |
|---|---|---|---|---|
| 1 | Product identity and user value | 62 | Medium | The mission is unusually clear and differentiated. Current public output contradicts it |
| 2 | First-time user experience | 38 | Low | Home is Tonight; in the offseason it says "no games"; failure states leak errors. Live site BLOCKED |
| 3 | Team Board completeness | 55 | Medium | Rich (Team Board 2.0: 11 domains), but the headline state is wrong for idle clubs and the explanation names the wrong cause |
| 4 | Tonight and matchup experience | 45 | Low | Hardened read model; no offseason content; live behaviour BLOCKED |
| 5 | Pitcher intelligence | 50 | Medium | Rest/role separation is good. Postseason roles decay to Role Unclear (EOS-006) |
| 6 | Baseball intelligence quality | 34 | Medium | Deterministic and evidence-linked, but the decisive state is wrong outside daily play and rules disagree across modules |
| 7 | Data completeness and correctness | 58 | Medium | Strong appearance ledger and constraints. Handedness gaps; no game-type policy; pitch data only since Jul 4 |
| 8 | Sync pipeline and publication | 45 | Medium | Legacy writer publishes reliably about twice a day. Red-by-construction workflow; two unfinished rewrites; no plausibility gate |
| 9 | Database and backend architecture | 50 | Medium | Clean migration chain; good keys. A 16.5 MB snapshot per request; no retention; 163k-line services layer |
| 10 | Frontend engineering | 55 | High | 1,299 of 1,299 tests pass; responsive. One 707 kB chunk, admin code shipped, semantics derived client-side |
| 11 | Performance and reliability | 38 | Low | Latency never measured; publication OK but unmonitored; non-hermetic tests |
| 12 | Historical intelligence | 42 | Medium | Immutable artifacts and a Team State timeline exist, but the history now contains a month of wrong reads |
| 13 | Offseason and season transitions | 5 | High | Not modelled at all |
| 14 | Security and operations | 35 | Medium | Sound admin auth. Public repo with unprotected `main`, production DB secret in 25 workflows, no rate limiting, no backups, no alerting |
| 15 | Distribution and retention | 15 | Low | No usage number recorded anywhere; team pages not indexable; no Metricool or posting automation |
| 16 | Competitive differentiation | 48 | Medium | The only neutral, evidence-backed, citable bullpen product. The headline output currently undercuts it |
| 17 | Solo-founder maintainability | 22 | High | 223k backend lines, 420 docs, 27 workflows, three pipeline architectures, red CI as normal |
| | **Overall (unweighted mean)** | **39** | Medium | |

**Readiness assessments**

| Assessment | Verdict |
|---|---|
| Technical readiness | **Not ready.** The core correctness defect and missing operational safety nets (backups, alerting, branch protection) must be fixed first |
| Product readiness | **Not ready.** No offseason product; the public state is wrong |
| 2027 launch readiness | **Achievable but at risk.** A *correct* launch (Minimum tier) is 46–62 engineer-days. A launch a serious user would *prefer* (Core tier) is 80–105 engineer-days, about 5 days a week from now to Opening Day (`05`). The main risk is the offseason being consumed by infrastructure (the SP rewrite, more proof layers) instead of season modelling, the archive and usefulness |

## 3. Top 10 strengths

1. **Clear, differentiated mission.** Descriptive, evidence-backed bullpen intelligence with no betting, fantasy or prediction. Every dedicated competitor is fantasy- or betting-framed (`02` §13).
2. **Canonical appearance ledger with real integrity:**
   - `game_logs` unique on `(pitcher_id, mlb_game_pk)`, with check constraints;
   - an `appearance_team_*` provenance;
   - `source_*` lineage columns (`backend/models/game_log.py:53-167`).
3. **Fail-closed publication with immutable, dated share artifacts.** These carry a snapshot ID, sync run, data-through date, and integrity hash, plus a supersede/withdraw lifecycle (`models/share_artifact.py:195-242`).
4. **Role separated from current workload.** A Trusted Arm can have Limited Rest. Role movement has strong evidence gates: ≥3 appearances per window and refusal to compare across phases (`services/role_movement.py`).
5. **Large, mostly passing test suite.** About 10,718 of 10,726 backend tests and 1,299 of 1,299 frontend tests pass locally. The failures are environmental.
6. **A publisher that actually publishes.** The legacy writer has delivered about two trusted publications a day since at least Oct 2 (47 automation commits), and data-through tracked game days correctly, including the Oct 20–22 off-days.
7. **Postseason games are ingested into workload**, through the postgame boxscore lane. The World Series clubs' workload is reflected.
8. **Privacy-bounded first-party analytics:** no IP or user-agent storage (`models/traffic_page_view.py`).
9. **Pitch-level data retained since 2026-07-04:** velocity, spin, movement, location. A durable asset for future workload-quality work.
10. **Sound basic security engineering:**
    - constant-time admin token comparison;
    - production refuses to boot without a token;
    - no secrets in the visible history;
    - no workflow script injection.

## 4. Top 10 weaknesses

1. **EOS-001:** inactivity is scored as constraint, so idle clubs read Vulnerable.
2. **EOS-002:** there is no season or club-status model; eliminated clubs get "current" reads.
3. **EOS-004 / EOS-008 / EOS-007:** no plausibility gate, no alerting, and a workflow that is red by construction. Nobody is told when the product is wrong or down.
4. **EOS-009:** backups and restore are unproven; there is one production database and no staging.
5. **EOS-010 / EOS-011:**
   - a public repository with an unprotected `main`;
   - the production DB credential in 25 workflows;
   - open email-sending endpoints with no rate limits.
6. **EOS-013:** about 60 HTML files a day are committed to `main`, and 119 MB of share pages redeploy twice daily.
7. **EOS-016:** two unfinished replacement pipelines and permanent DB fences inherited from an unmerged branch.
8. **EOS-014:** the Team Board loads the whole league snapshot per request; latency has never been measured.
9. **EOS-M04 / EOS-022:**
   - no recorded usage evidence;
   - team pages are redirect stubs and cannot rank in search.
10. **EOS-029:** governance stopped tracking reality on Sep 4. 420 docs, and the prior audit's P1 actions were not executed.

## 5. Most dangerous hidden risks

1. **Opening Day 2027 repeats EOS-001 at league scale.** On 2027-03-25 (or whenever the season opens) every reliever's last *regular-season* appearance will be about 6 months old. Unless spring games leak in (EOS-023), every arm would be "stale" → On Watch → every club Vulnerable on Opening Day.
2. **Unrecoverable data loss.** A single database, no proven backups, write-capable credentials spread across 25 workflows on a public repository with an unprotected `main` (EOS-009, EOS-010).
3. **Silent fences veto corrections.** The `e3f6a9b2c5d8` triggers revert `main`'s writes to rows the abandoned integration runtime adopted (EOS-016). Season-close reconciliation could appear to succeed while not changing data.
4. **CI lockout on 2026-11-13** (EOS-012). This lands in the middle of the Phase 0 fixes.
5. **A credibility debt in the permanent record.** About 750 frozen artifacts say rested bullpens were vulnerable. Anyone who cited them was misinformed (EOS-003).

## 6. Competitive positioning

**Where BaseballOS stands relative to each competitor type:**

| Competitor | What it is | How BaseballOS compares |
|---|---|---|
| FanGraphs / RosterResource | The incumbent for bullpen workload: a closer depth chart with six-day usage grids and "High Usage Alert" | Answers "who's closing?" more directly than BaseballOS |
| Baseball Savant | Owns pitch quality | Has no availability or workload view |
| Baseball Reference | Owns history and game logs | No "bullpen right now" view |
| Dedicated trackers (Inside the Pen, RotoWire Closer Grid, Tony's Picks fatigue report) | Per-arm usage grids | Fantasy- or betting-framed and predictive |

**BaseballOS's genuine lane is the only neutral, descriptive, dated, evidence-linked, citable team bullpen state.** That is what broadcasters, beat writers and outlets that cannot cite betting sites need.

**Where it is weaker today:**
- There is no descriptive answer to "who has been closing?" (EOS-M07).
- It has no search presence (EOS-022).
- The October output undermines the trust advantage it depends on.

Competitor claims rest on search-result snippets (sites blocked); see `02` §13 and `08` for sources.

## 7. What should stop immediately

1. **Stop publishing current Team State for clubs with no game context.** Even before the code fix, consider pausing automated distribution after the World Series final (DEC-01, WP-0.1).
2. **Stop the shadow-activation health job**, or fix its validator. Red must mean broken (EOS-007).
3. **Stop generating a new share artifact for every club on every publication.** Generate one only when a read changes (EOS-013).
4. **Stop work on the `feat/sync-pipeline` (SP) rewrite and the CU shadow lanes for the offseason.** Shut down their 3-minute crons (EOS-016, DEC-04).
5. **Stop adding proof, authority or certification layers** before the product's basic baseball semantics (season, idle, eliminated) are correct. Prior audits made the same call in June and September.
6. **Stop running one-off 2026 repair workflows** with production write credentials. Archive them (EOS-010, EOS-031).

## 8. What must be preserved

1. The descriptive-only product contract and the public vocabulary: Fresh/Stretched/Vulnerable; the arm reads; the role labels.
2. The canonical appearance ledger, its constraints, and its provenance columns.
3. Immutable share artifacts and their supersede/withdraw lifecycle, used to *correct* October, not to erase it.
4. The role/workload separation and the role-movement evidence gates.
5. The legacy daily/postgame writer as the single production authority, with its advisory lock and due-window idempotency.
6. The complete 2026 season record, including the postseason. Back it up before touching anything.
7. The founder's sustainability as a binding constraint (Constitution 01:169).

## 9. Is BaseballOS ready for offseason mode?

**No.**

- There is no offseason mode. The system keeps calculating rest and freshness against a league-wide calendar date and publishing them as current.
- The smallest correct offseason product (§12 of `02`; Phase 1 of `05`) is:
  1. a backend season-phase contract;
  2. a "2026 season complete" home that leads into the archive;
  3. per-club season-in-review pages built from data that already exists;
  4. an offseason transactions feed.
- No current Team State until spring rosters plus 2027 regular-season games make one meaningful.

## 10. What would prevent a successful 2027 launch

1. Shipping Opening Day without the season-phase model and the idle-arm fix (risk §5.1).
2. Spending the offseason finishing the SP/CU pipeline rewrite instead of the season model, the archive, the Team Board mobile answer and indexable team pages.
3. No proven backup before offseason refactors touch production data.
4. No usage baseline or kill criteria, so 2027 decisions are made blind (EOS-M04, DEC-09).
5. CI blocked from 2026-11-13 (EOS-012), which stalls every fix.

## 11. Answer to the governing question

> *If we were launching BaseballOS for the first time on Opening Day 2027, what would we need to fix, finish, simplify, or build during the offseason so that a serious baseball person would genuinely prefer using it over their existing bullpen research workflow?*

**Fix:**
- Make Team State mean what it says. Absence of work is rest, not stress (EOS-001).
- A club with no game context gets no current read (EOS-002).
- The explanation must name the rule that decided the state, with named arms (EOS-005).
- One definition per workload rule (EOS-017).
- Correct the October record (EOS-003).

**Finish:**
- A season-phase model, from spring through the World Series to the offseason.
- A 2026 season close (EOS-M01, EOS-M02, EOS-M06).
- Postseason-aware roles (EOS-006).

**Simplify:**
- One pipeline (DEC-04).
- No HTML in git (DEC-05).
- One current-state document instead of 420 (DEC-08).
- Delete about 20 workflows and about 15k lines of one-off code (EOS-031).

**Build:**
- A mobile Team Board whose first screen is the active bullpen, with inline receipts (EOS-I01).
- A named-arm What Changed (EOS-I02).
- A descriptive "who has been finishing games" hierarchy (EOS-M07).
- Indexable `/team/{ABBR}` pages (EOS-022).
- A citation line for creators (EOS-I03).
- A 2026 archive (EOS-M03).
- A usage baseline with kill criteria (EOS-M04).

**The test, with evidence rather than ambition:**
- A beat writer opens `/team/MIL` on a 2027 game day.
- In one mobile screen they see which relievers worked yesterday and over the last 3 days, with pitch counts. They see who has been finishing games, and what changed since yesterday.
- They see a citable dated link, and nothing on the screen is wrong.

That replaces three steps in the incumbent workflow: box score, RosterResource grid, game logs. Today, none of those screens can be trusted to be right in October.
