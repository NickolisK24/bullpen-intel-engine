# 08 — Audit Evidence Index

This index maps the major findings and conclusions to their evidence, gives reproduction commands, and records which systems could not be accessed.

- **Repository state:** `main` @ `0c90be9b74c2d7603cf4a739f7986baad8265498` (shallow clone; 64 commits, 2026-10-02 → 10-28).
- **Other refs read:**
  - `origin/feat/sync-pipeline` @ `617ab650f`;
  - `origin/claude/baseballos-viability-audit-8ufhk9` @ `b9f092348`.

---

## 1. Finding → evidence map

| Finding | Primary evidence (file:line / artifact / runtime) | Class |
|---|---|---|
| EOS-001 Inactivity scored as constraint | `backend/services/availability.py:206-220` (stale), `:391-399` (stale → Monitor), `:367-375` (missing → Monitor); `backend/team_operations/bullpen_readiness.py:490-502` (partition), `:599` (clean ≤ 2 → Vulnerable); `backend/team_operations/contracts.py:67-78`; `backend/api/team_operations.py:509-523` (trust gate accepts old rest); team-page history `git log -- frontend/public/team/WSH/index.html` | Code + production artifact |
| EOS-002 No season or club status | `backend/services/availability_reference_date.py:99-143`; `services/slate_coverage.py:48`; `services/sync.py:7340-7349`; share artifact `frontend/public/share/178c7a7f812645e6b6d5126e06a92aab/index.html` ("after recent work", data through 2026-10-27, WSH) | Code + production artifact |
| EOS-003 Frozen artifacts carry errors | `frontend/public/share/*` scan (§2.3); `backend/models/share_artifact.py:98-119, 240-242` | Production artifact + code |
| EOS-004 Weak plausibility gate | `backend/services/team_state_vnext_production_proof.py:641-685`; `backend/scripts/validate_team_state_vnext_proof.py:163`; run 40656367563 step "Export durable Team State production proof: skipped"; `docs/governance/BASEBALLOS_FULL_PROGRAM_AUDIT_2026_06.md:39-41` | Code + runtime |
| EOS-005 Wrong cause in explanation | `backend/services/team_story_previews.py:256-263`; `services/bullpen_board.py:206, 236-242, 256-261`; MIL/TB team pages ("One reliever is Unavailable") | Code + production artifact |
| EOS-006 Postseason roles decay | `backend/services/pitcher_role_authority.py:76-109`; `pitcher_role.py:33, 157-158, 405-407`; `bullpen_eligibility.py:47-64, 107-122`; `availability_snapshot.py:195-245`; `role_movement.py:26, 133-135` | Code |
| EOS-007 Red-by-construction workflow | GitHub runs (§3); `backend/scripts/run_due_sync.py:77-84`; `backend/scripts/validate_game_driven_shadow_cycle.py:142-150, 532`; `backend/services/sync_metadata.py:69`; `.github/workflows/baseballos-sync.yml:718, 744-870` | Runtime + code |
| EOS-008 No alerting | grep: no Slack, PagerDuty, webhook or Sentry in `backend/`; `backend/scripts/check_scheduled_sync_health.py`; `.github/workflows/baseballos-scheduler-health.yml:3-5`; `frontend/src/utils/errorMonitoring.js:86`; `docs/current/SYNC_PIPELINE.md:74-81` | Code (absence) |
| EOS-009 Backups unproven | grep for `pg_dump`, `restore`, `PITR` in repo: none; `docs/current/PRODUCTION_MIGRATION_AUTHORITY.md:162-185` | Absence |
| EOS-010 Credential exposure | GitHub `list_branches` (`"protected": false` for every branch); workflow `env:` blocks (25 of 27 reference `secrets.DATABASE_URL`); `backend/config.py:157-160` | API + code |
| EOS-011 No rate limiting | `backend/api/auth.py:45-61`; `backend/services/audience_signup.py:86-126`; `backend/api/traffic.py:42-95`; `backend/scripts/render_start.sh:80-84`; `backend/api/bullpen.py:3758-3790` | Code |
| EOS-012 Router expiry | `docs/decisions/2026-08-13-react-router-v7-security-defer.md:4`; `.github/dependency-audit-accepted.json`; `backend/tests/test_dependency_audit_gate.py:54, 288`; `frontend/package.json:16`; `npm audit --omit=dev` | Code + tool |
| EOS-013 HTML in git | `git log --format='%an %s'` (47 of 64 automation commits); `git show --stat HEAD` (61 files); `du -sh frontend/public/share` (119 MB, 10,042 dirs); `frontend/vercel.json`; `.github/workflows/baseballos-generated-distribution.yml:52, 240-258` | Repository |
| EOS-014 Full-snapshot Board reads | `backend/api/team_board_v2.py:47-58`; `services/dashboard_snapshot.py:903-932, 1119-1126`; `services/public_serving_authority.py:863`; `services/team_board_delivery.py:153-163`; `docs/audits/daily-primary-memory-incident-2026-09-29.md:37` (16.5 MB) | Code + doc |
| EOS-015 No retention | grep: no delete paths for `dashboard_snapshots` and related tables; Snapshot-ID trailers increase ~31–33 per cycle | Code + git |
| EOS-016 Two unfinished pipelines | `git show origin/feat/sync-pipeline:docs/sync-pipeline/SYNC_PIPELINE_PRODUCTION_MANIFEST.md` (NO-GO, service table); `…/AUDIT-R3_PUBLICATION_INTEGRITY.md:20-216` (BLOCKED, F03); `…/SP-00_*.md` ("Contract proposal"); `git diff --stat main origin/feat/sync-pipeline -- backend` (304 files); `docs/current/CU_08S_*.md:241-246`; `CU_08U_*.md:13-20`; `docs/current/SYNC_PIPELINE.md` §15A–15D; `backend/services/continuous_execution.py:752-805` | Branch + docs + code |
| EOS-017 Inconsistent rules | `availability.py:109-120, 133-171`; `public_team_relief_work.py:72-73`; `workload_recovery_evidence.py:46-47`; `pitcher_role.py:51` | Code |
| EOS-018 Population and classifier mismatch | `bullpen_board.py:150-217, 256-261`; `bullpen_visibility.py:56-60`; `publication_truth_certification.py:544-568`; WSH team page ("Nineteen relievers") | Code + artifact |
| EOS-019 Frontend semantics | `frontend/src/adapters/operatingStateReadModel.js:9-14, 49-52, 200-248, 314-380`; `utils/pitcherLabels.js:17-60`; `utils/bullpenConcepts.js:83-180`; `utils/appearanceLanguage.js:185-196` | Code |
| EOS-020 Infrastructure language | `tonightsBullpenBoardView.js:668`; `tonightView.js:145`; `TeamBoardRolesDeployment.jsx:86`; `PublicShareArtifactPage.jsx:182`; `hooks/useFetch.js:54`; screenshots `stories-*.png`, `trust-*.png` | Code + local render |
| EOS-021 Bundle | `frontend/src/App.jsx:15-24, 50-54`; build log (707 kB / 193 kB gzipped) | Build |
| EOS-022 SEO | `frontend/public/team/NYY/index.html`; `frontend/public/robots.txt`; `frontend/public/sitemap.xml`; `frontend/index.html` | Repository |
| EOS-023 Game-type policy | `backend/services/mlb_api.py:562-577, 606, 621-641, 645`; `bullpen_capacity.py:159-160`; `role_stability_context.py:85`; `rotation_context.py:85`; `bullpen_concentration_context.py:84` | Code |
| EOS-024 Handedness gaps | WSH artifact `178c7a7f…` "4 active relievers are missing throwing-hand data"; `backend/models/pitcher.py:20` | Artifact |
| EOS-025 Auth hardening | `frontend/src/utils/api.js:22, 109-127`; `backend/api/auth.py:85`; `backend/app.py:85-88, 125-139`; `frontend/vercel.json` | Code |
| EOS-026 Non-hermetic tests | Local run log (shard 3); `backend/tests/test_postgame_lookback.py`; `tests/test_postgame_refresh.py:246-271`; py-spy stack `sync.py:6025 → team_assignment_sync.py:449 → mlb_api.py:555` | Test run |
| EOS-027 Enrichment near timeout | Run 40656367563 job `internal-enrichment` (08:23:40 → 08:42:07); run 40727951878 failure; `baseballos-sync.yml:871-950` | Runtime |
| EOS-028 Failure states | Screenshots `board-390.png` ("Teams unavailable" + "Pick a team"), `stories-*.png`, `trust-*.png` | Local render |
| EOS-029 Governance drift | `docs/canonical/05_PRODUCT_ROADMAP_DECISION_LEDGER.md:9, 76, 250-261, 541`; `docs/README.md:43`; `docs/current/CHANGELOG.md:7`; `docs/audits/tonight-v1-root-cutover-tn-10.md:3-5`; `docs/canonical/03…:124`; `07…:130`; `docs/decisions/2026-09-2*`, `2026-10-06-*`; prior audit branch | Docs |
| EOS-030 Infrastructure off-repo | No `render.yaml`; `docs/current/SYNC_PIPELINE.md:105-137` | Absence |
| EOS-031 Dead code | `ls backend/services/*_2026.py` (12 files, 12,296 lines); `.github/workflows/` (27); grep of `frontend/src` imports; route dump | Repository |
| EOS-032 Privacy | `backend/models/traffic_page_view.py:26-49`; migration `e5b9c3a7d1f4`; `backend/tests/test_sec01_supabase_rls.py:288` | Code |
| EOS-033 Timezone | `backend/api/bullpen.py:1243`; `services/roster_depth_evidence.py:643`; `services/game_change_detection.py:224` | Code |
| EOS-034 Accessibility coverage | `frontend/tests/browser/*` (axe on Tonight only); `frontend/src/components/RouteAccessibility.jsx:9-26` | Code |
| EOS-035 Doc count | `docs/canonical/README.md:8`; `docs/README.md:3`; `docs/REPOSITORY_DOCUMENTATION_MAP.md:20-27`; `docs/canonical/07…:26` | Docs |
| EOS-036 Prohibited vocabulary | `frontend/src/components/posts/privatePostsView.js:52`; `docs/canonical/06…:275` | Code + docs |
| Strength: ledger integrity | `backend/models/game_log.py:53-167` | Code |
| Strength: test suite | Local results: backend ~10,718/10,726; frontend 1,299/1,299 | Test run |
| Strength: publication cadence | 47 generated commits with monotone `Data-Through` (§2.1) | Git |
| Historical lead — Tonight DB timeout fixed | `backend/config.py:58-105`; `services/public_serving_authority.py:1457-1461` | Code |
| Historical lead — starter workload fixed | `services/game_shape.py:305`; `services/team_board_v2.py:95-106` | Code |

---

## 2. Reproduction procedures (run from the repo root; no network needed)

### 2.1 Publication timeline from commit trailers

```bash
git log --format='%ad|%(trailers:key=Snapshot-ID,valueonly,separator=)|%(trailers:key=Data-Through,valueonly,separator=)' \
  --date=iso -- frontend/public/team/NYY/index.html
```

### 2.2 League Team State distribution per publication

```bash
for c in $(git log --format=%h -- frontend/public/team/NYY/index.html); do
  dt=$(git show $c:frontend/public/team/NYY/index.html | grep -o 'data-through" content="[^"]*"' | sed 's/.*content="//;s/"//')
  f=0; s=0; v=0
  for t in $(ls -d frontend/public/team/*/ | xargs -n1 basename); do
    st=$(git show $c:frontend/public/team/$t/index.html 2>/dev/null | grep -o 'team-state" content="[^"]*"' | head -1 | sed 's/.*content="//;s/"//')
    case $st in Fresh) f=$((f+1));; Stretched) s=$((s+1));; Vulnerable) v=$((v+1));; esac
  done
  echo "$dt F=$f S=$s V=$v"
done | uniq
```

### 2.3 Share artifacts since 2026-09-29 by state

```bash
cd frontend/public/share && python3 - <<'EOF'
import re, os, collections
c = collections.Counter()
for d in os.listdir('.'):
    p = os.path.join(d, 'index.html')
    if not os.path.exists(p): continue
    s = open(p, errors='ignore').read()
    if 'artifact-type" content="team_state"' not in s: continue
    dt = re.search(r'data-through" content="([^"]*)"', s).group(1)
    st = re.search(r'team-state" content="([^"]*)"', s)
    if dt >= '2026-09-29': c[st.group(1) if st else '?'] += 1
print(sum(c.values()), c)   # audit result: 1436 {Vulnerable: 747, Fresh: 393, Stretched: 296}
EOF
```

### 2.4 Washington's frozen reads across the season boundary

```bash
for dt in 2026-09-27 2026-10-01 2026-10-08 2026-10-12 2026-10-19 2026-10-27; do
  f=$(grep -l 'baseballos:team" content="WSH"' frontend/public/share/*/index.html \
      | xargs grep -l "data-through\" content=\"$dt\"" | head -1)
  echo "== $dt"
  sed 's/<[^>]*>/\n/g' "$f" | sed '/^\s*$/d' | grep -A1 -E 'Team State:|Historical snapshot|Evidence behind'
done
```

### 2.5 Shadow-validator mismatch (EOS-007)

```bash
sed -n 76,90p backend/scripts/run_due_sync.py
sed -n 138,152p backend/scripts/validate_game_driven_shadow_cycle.py
grep -n SUCCESSFUL_STATUSES backend/services/sync_metadata.py
```

### 2.6 Team State rule and stale handling (EOS-001)

```bash
sed -n 206,220p backend/services/availability.py
sed -n 391,399p backend/services/availability.py
sed -n 590,625p backend/team_operations/bullpen_readiness.py
sed -n 67,78p backend/team_operations/contracts.py
```

### 2.7 Test suites

- **Backend:**
  - Python 3.11 venv: `pip install -r backend/requirements-dev.txt`.
  - Local PostgreSQL 16 database named `*test*`, UTF8 encoding.
  - Full git history required for 6 vocabulary-baseline tests.
  - Run `python -m pytest backend/tests` per the CI shard matrix in `.github/workflows/ci.yml`.
- **Frontend:** `cd frontend && npm ci && npm test && npm run build`. Three tests read `../backend` and `../README.md`.

---

## 3. GitHub Actions runtime evidence (read through the GitHub API, 2026-10-29)

| Item | Value |
|---|---|
| Window | 2026-10-07T14:53Z → 2026-10-28T16:38Z (100 most recent runs) |
| BaseballOS Bullpen Sync (schedule) | 22 success / 43 failure |
| Generated Distribution Delivery (dispatch) | 32 success / 0 failure |
| CI | push 1 success; pull_request 1 success, 1 failure |
| Representative failed run | 40656367563: jobs `public-sync` ✅, `static-team-story-preview` ✅, `internal-enrichment` ✅ (18.5 min), **`shadow-activation-health` ❌** ("Activation health is FAILED (reason=validator_reported_failure) … observer health only") |
| Second failed run | 40727951878: `shadow-activation-health` ❌, `internal-enrichment` ❌ |
| Branch protection | `main` `protected: false` |
| Branches of note | `feat/sync-pipeline` (617ab650, 2026-09-19); `claude/baseballos-viability-audit-8ufhk9` (2026-09-24, unmerged); about 60 feature/fix branches not deleted |

---

## 4. External evidence

**Postseason context** (web search; mlb.com blocked):

| Fact | Source |
|---|---|
| World Series MIL–TB; Game 1 2026-10-23, MIL 3–2 | https://www.fox13news.com/news/world-series-2026-game-1 |
| NLCS: MIL over LAD 4–0 | https://www.baseball-reference.com/postseason/2026_NLCS.shtml |
| ALCS: TB over CLE 4–2 | https://www.baseball-reference.com/postseason/2026_ALCS.shtml |
| Bracket and schedule | https://www.cbssports.com/mlb/news/2026-mlb-playoff-bracket-schedule-scores-results-how-to-watch/ |

**Competitors.** Snippet-level only; the page fetches were blocked:

- FanGraphs / RosterResource:
  - https://fantasy.fangraphs.com/bullpen-report-august-6-2023/
  - https://blogs.fangraphs.com/get-to-know-leverage-index
  - https://fantasy.fangraphs.com/fresh-for-the-playoffs-pre-playoff-fatigue-units
  - https://blogs.fangraphs.com/about-that-dodger-bullpen-usage
- Baseball Savant: https://baseballsavant.mlb.com/
- Baseball Reference:
  - https://baseballreplayjournal.substack.com/p/baseball-reference-and-pitching
  - https://baseball-reference.com/blog/archives/10071.html
- Inside the Pen:
  - https://insidethepen.com/articles/did-you-know.html
  - https://insidethepen.com/closers-by-team.html
- RotoWire Closer Grid: https://commish.rotowire.com/baseball/closers.php
- Tony's Picks bullpen fatigue (betting): https://www.tonyspicks.com/2026/07/19/mlb-bullpen-fatigue-report-7-19-26/
- FantraxHQ usage chart: https://fantraxhq.com/?p=17148
- ESPN closer org chart / tired-reliever rule: https://global.espn.com/fantasy/baseball/flb/story/_/page/REcloserorgchart
- RotoBaller / FantasyPros closer rankings:
  - https://www.rotoballer.com/closer-fantasy-baseball-rankings-waiver-wire-adds-breakouts-week-14-2026/1882154
  - https://fantasypros.com/content/closer-report/
- Pitcher List: https://pitcherlist.com/relief-pitcher-streamer-rankings-fantasy-baseball-7-22/
- Beat-writer "unavailable" reporting:
  - https://www.mlb.com/news/soriano-robertson-unavailable-saturday/c-38837018
  - https://masnsports.com/blog/o-day-among-the-unavailable-relievers

**Prior audit:** `origin/claude/baseballos-viability-audit-8ufhk9:BASEBALLOS_CURRENT_STATE_2027_VIABILITY_AUDIT.md` (2026-09-24). Its findings F-02, F-04, F-08, F-16, F-17, F-18 and F-28 were rechecked and remain open.

---

## 5. Inaccessible systems and required follow-up verification

| System | Status | What it blocks | Follow-up (owner: founder) |
|---|---|---|---|
| https://baseballos.app (frontend) | BLOCKED (session network policy: DNS / proxy denied) | Live UX, first-load timing, live copy, persona journeys, back-button behaviour, live SEO | G-6, G-10.2–10.3; Lighthouse mobile run; manual persona walk-through on a phone |
| Production API (Render) | BLOCKED | Latency (EOS-014), live payloads, `/api/health` | G-4.1; `curl -w` timings for 30 boards |
| Production PostgreSQL (Supabase, INFERRED) | BLOCKED (no credentials; deliberately not sought) | All of G-1, G-2.3, roster population (EOS-018), RLS state, DB size, backups | G-1.0–G-1.9 read-only; PITR tier confirmation; `pg_database_size` |
| statsapi.mlb.com | BLOCKED | Case reconciliation against authoritative boxscores; API default game type for gameLog | G-1.7; one call to confirm the gameLog `gameType` default |
| Render dashboard | No access | Cron inventory, whether the `feat/sync-pipeline` shadow service still runs, auto-deploy on HTML commits, memory | G-8.8; screenshot inventory into the repo |
| Vercel dashboard | No access | Deploy count, file-count limits, build minutes, `VITE_SENTRY_DSN` | Check deploy history for October; limits for 10k+ files |
| Analytics (`/admin/product-intelligence`) | No access | Usage baseline (EOS-M04) | WP-1.5 readout |
| Metricool | Not connected; no reference in repo | Social distribution performance | Export October follower and click data into the WP-1.5 readout, if used |
| Competitor sites (FanGraphs, Inside the Pen, RotoWire, mlb.com) | BLOCKED for fetch | Workflow-level comparison beyond snippets | A 30-minute manual side-by-side using the 5-question task test (prior audit K6) |
| Full git history | Shallow clone | 6 vocabulary-baseline tests; history-dependent claims before 2026-10-02 | Run in CI (full history) |

**To enable these from a future audit session:** allow `baseballos.app`, the API host, and `statsapi.mlb.com` in the cloud environment's network settings (https://code.claude.com/docs/en/cloud-environments#network-access). Then provide a **read-only** database URL for production or a restored copy.
