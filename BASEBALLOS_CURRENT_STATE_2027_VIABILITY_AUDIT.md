# BaseballOS Current-State & 2027 Viability Audit

**Date:** 2026-09-24 (last week of the 2026 regular season)
**Repository state audited:** `main` @ `7e1ae4646` (merge of PR #875), full history of 2,584 commits since 2026-03-14
**Mode:** Read-only. No production data, configuration, branches, or deployments were touched. Local test runs used disposable SQLite/PostgreSQL instances only.

---

## 0. How to read this report (and what it could not see)

**Critical limitation — production was not directly observable.** The audit environment's network egress policy denied every connection to `baseballos.app`, `www.baseballos.app`, `baseballos-api.onrender.com`, and `statsapi.mlb.com` (HTTP 403 at the proxy; also blocked for server-side fetch). Competitor sites (FanGraphs, RotoWire, InsidethePen, etc.) were also blocked for page fetches; competitive research relies on search-engine results and snippets.

Production reality was therefore reconstructed from the strongest available indirect evidence:

1. **Automated production distribution commits.** `BaseballOS Automation <baseballoshq@gmail.com>` commits generated `/team/{ABBR}` and `/share/{id}` pages to `main` from each trusted published snapshot, with trailers such as `Snapshot-ID: 3521`, `Data-Through: 2026-09-23`. These are production outputs committed to git, and 37 of them span 2026-08-13 → 2026-09-24.
2. **The production incident record** (`docs/incidents/2026-09-12-daily-publication.md`), which quotes production snapshot IDs, Render cron instance IDs, GitHub run IDs, and served API values.
3. **Commit messages that describe observed production states** (e.g. `3f041b15` citing snapshot 3435 output).
4. **Local builds and renders** of the frontend (Playwright, with the repo's own fixtures and with the API forced down).

Where this report says **PROVEN**, it means directly observed in those artifacts or reproduced locally. Nothing about live latency, live page rendering, or live traffic could be measured. Those are marked **UNKNOWN**, and Section 29 lists the exact checks the founder can run in minutes to close them.

**Evidence classes:** PROVEN · SUPPORTED · INDICATIVE · UNKNOWN · PLANNED ONLY
**Severity:** P0 (integrity/security, immediate) · P1 (blocks core utility, reliability, or 2027 viability) · P2 (meaningful weakness) · P3 (polish)

**Lenses used throughout:** *Intent* (what BaseballOS says it is) · *Implementation* (what the repo contains) · *Production reality* (what a visitor gets) · *Market value* (whether anyone has a reason to care).

---

## 1. Executive Assessment

**What BaseballOS actually is today, in plain English:**
BaseballOS is a free website that, once a day, publishes for all 30 MLB teams a snapshot of each bullpen:
- which relievers are active;
- how much each has pitched recently (pitches yesterday and over the last 3, 5, and 7 days; consecutive days);
- a rule-based rest label for each reliever (Clean Option / Watch Arm / Limited Rest / Unavailable);
- a usage-based role label (Trusted / Setup / Coverage / Middle Relief);
- a three-level team label (Fresh / Stretched / Vulnerable);
- some context on starter length, roster moves, and performance;
- a comparison with the previous published day.

Every label is produced by deterministic, published rules from box-score data. There is no machine learning, no LLM, and no prediction.

**The central tension:** the product underneath is small, the machinery around it is enormous, and the demand evidence is almost nonexistent.

- The rules that produce the core value fit in a few hundred lines (`services/availability.py`, `team_operations/contracts.py`).
- Around them sit:
  - 215,171 lines of non-test backend Python, tripled from ~73,000 at the end of June 2026;
  - 208,117 lines of backend tests;
  - ~120,000 lines of documentation in 400 files;
  - 25 GitHub workflows (7,927 lines of YAML);
  - a publication/"trust authority" apparatus that consumed roughly half of recent engineering.
- The repository does not record a single user, visitor, return, or citation number anywhere. The instrumentation to answer that question exists (`backend/services/traffic_reporting.py`, admin page `/admin/product-intelligence`), but its output has never been written into any decision.

**Honest summary of the three questions that matter:**

| Question | Answer | Evidence |
|---|---|---|
| Is there a real recurring problem? | **Yes, narrowly.** "Who in this bullpen is rested/taxed tonight?" is a real daily question for engaged team fans, writers, and broadcasters. Its existence is proven by the number of competitors who answer it. | SUPPORTED |
| Is BaseballOS's answer differentiated? | **Partly.** Raw workload grids are a commodity (FanGraphs, RotoWire, Razzball, FantraxHQ, InsidethePen, ESPN all offer free versions). The differentiated pieces are: a structured *day-over-day change* view, *rotation-transfer* context, *full-active-bullpen* role labels, and *strictly descriptive* team state. Those pieces are partially built and not yet the product's front door. | SUPPORTED |
| Is anyone using it? | **Unknown.** No usage evidence exists in the repository. The site is invisible in web search. Given zero discoverability, no recorded distribution results, and a 13-day publication outage in September that no one outside the founder appears to have reported, the most likely state is very low usage. That is INDICATIVE, not proven. | UNKNOWN / INDICATIVE |

**Bottom line:** BaseballOS has a legitimate kernel and an unusually strong data-integrity backbone. It is at genuine risk of becoming dead content. Its infrastructure is not bad; the risk has three causes:
1. What users see day to day overlaps heavily with free tools that already exist.
2. Its most distinctive signal (Team State) turns over for about half the league every day, so it behaves like a yesterday-usage readout rather than a "state".
3. Engineering effort has gone overwhelmingly into proving the correctness of publications that no one has yet demonstrated they want.

This is fixable, but only by redirecting effort from infrastructure to measured user behavior before Opening Day 2027.

---

## 2. Current Product Reality

### What is genuinely working in production

| Capability | Status | Evidence |
|---|---|---|
| Daily ingestion of MLB appearances, pitch counts, rosters, transactions for 30 clubs | Working most days | PROVEN via 26 distinct `Data-Through` dates in automation commits, 2026-08-13 → 09-23 |
| Per-reliever rest label from explicit pitch/day thresholds | Working, non-degenerate | PROVEN. Rules at `backend/services/availability.py:205-255`; distributions vary daily |
| Team State (Fresh/Stretched/Vulnerable) for all 30 clubs | Working, non-degenerate | PROVEN. Snapshot 3521: 8 Fresh / 15 Stretched / 7 Vulnerable. Earlier snapshots range from 3–14 Fresh. The June "everything is Monitor" failure (`docs/governance/BASEBALLOS_FULL_PROGRAM_AUDIT_2026_06.md`) no longer applies |
| Team Board 2.0 (summary, active bullpen, what changed, recent usage, rest, workload, roles, performance, rotation impact, roster, recent relief work) | Merged Sep 17–23; exercised on production snapshots 3435/3521 | SUPPORTED. Commit `3f041b15` describes snapshot-3435 output |
| Per-team crawler/preview pages and 7,873 immutable share pages | Working | PROVEN (`frontend/public/team/*`, `frontend/public/share/*`) |
| Fail-closed publication (a bad snapshot is not published) | Working as designed | PROVEN. The Sep 12 incident shows the 30-team proof rejecting a 34-team universe |

### What is not working, or not proven, in production

| Item | Status | Evidence |
|---|---|---|
| **Currentness.** Distribution pages exist for only 26 of the 42 days from 08-13 to 09-23. Missing: 08-16, 08-19, 08-21, 08-25, and **09-10 through 09-21 (12 consecutive days)** | Publication gaps | PROVEN for distribution pages; SUPPORTED for the database publication (the incident doc confirms the league snapshot stuck at data-through 09-10) |
| **Freshness honesty during the outage.** The Dashboard reported `is_current=true`, age 0, while serving Sep 10 data; the frozen Team Board omitted the failure warning | Trust-signal failure | SUPPORTED (incident doc, "Observed blast radius") |
| **Correctness of bullpen workload display.** Until Sep 23, starters' conventional starts were displayed as bullpen work for mixed-usage arms (e.g. SF Perdomo 1/83, Marte 1/97, Molina 2/167 in snapshot 3435) | Fixed Sep 23 | PROVEN (commit `3f041b15` message) |
| **Tonight v1 (TN-00/01/02)** | Merged today; not consumed by the frontend; 0 production rows at merge | See Section 13 |
| **Usage** | Instrumented; results never recorded | UNKNOWN |
| **Live performance** | Not measurable from this environment | UNKNOWN |

---

## 3. Intent vs Reality

| Area | Intended | Actual | Gap | Consequence |
|---|---|---|---|---|
| Mission | "The first place baseball people check to understand what is happening in MLB bullpens today" (Constitution l.28) | Not findable by searching "BaseballOS". No evidence of external citation | Total | The mission is aspirational only |
| Primary hierarchy (Tonight → League → Team Board → Pitcher → History) | The canonical Product Experience Standard names **Today / Slate**, not "Tonight". The live nav is Today, League Board, Team Bullpens, Compare Bullpens, Search, Stories, How to Read, Methodology, Data & Trust, About (`frontend/src/utils/navigation.js:15-27`) | Tonight exists only as an API contract and code term. 10 nav items vs a 5-level hierarchy | Vocabulary drift and nav bloat | Users meet three "home-like" surfaces (Today, League Board, Stories) |
| Team Board = deepest, most important surface | Team Board 2.0 exists with 13 sections | At 390px the first viewport shows no reliever names or numbers; the page is ~6,500px tall with *one* fixture reliever (PROVEN, local render) | Depth exists; above-the-fold answer does not | The "who's rested" answer requires scrolling on the primary device |
| Tonight = daily habit loop | Roadmap says "Today/Tonight … CORE COMPLETE" | Today renders legacy `tonight_v5`. The trusted `tonight_v1` contract is merged but unused (`frontend/src/utils/api.js:658`, `IntelligenceSurface.jsx:2665`) | "Complete" in docs ≠ delivered | The habit loop is not the product that was hardened |
| What Changed = returning-user value | Governed, backend-computed comparison between trusted publications | Exists on Team Board and as a separate "Since Yesterday" ledger inside the 2,693-line `IntelligenceSurface.jsx`. No interaction tracking. Team State changes for ~52% of teams every day | Two representations, no measurement, and a noisy underlying signal | Cannot tell whether it creates return visits |
| Descriptive, not predictive | Constitution guardrails | Rules are descriptive. Some June story outputs implied prediction ("The next tight inning still points back toward…") | Mostly honored | Low risk; keep policing copy |
| History / memory | "Build authority through memory" (Constitution §16) | `/history/team/:abbr` is a log of past labels. Only 2026 in-season data; no season-over-season view | Early | History has little reason to be revisited yet |
| Founder-operable | "Scope must survive a full-time job, family responsibilities, and limited weekly hours" (Constitution l.168) | Commits on 111 of 116 days since June 1, at every hour including 00:00–03:00 (~250 commits between midnight and 3am); 849 merge commits since June 1 | Severe | The stated constraint is not being honored by the development pattern |
| Success metrics | Weekly return, Today→Team Board handoff, team-page return, citations (Roadmap §12) | Named with no baselines or targets; "increase only after trust gates hold". Phase 6 "Growth and Validation" = Not started | No demand gate | Engineering can continue indefinitely without ever encountering a stop signal |
| Distribution | Editorial standard: ≤3 social posts/week, newsletter, creator outreach | Private posting board exists (`/posts-bpen-7f3d9c`). No recorded results; @baseballoshq not found by search | Unknown execution | Unknown awareness |

---

## 4. First-Time User Audit

*Method: local renders of the production frontend at 390px and 1280px using the repo's fixture data, plus the text of real production preview pages. Evidence class: SUPPORTED for layout and copy; UNKNOWN for live data density.*

**Casual baseball fan.**
- **What they see:** the homepage headline "See which bullpens are fresh, stretched, or vulnerable", followed by "Descriptive only — no picks, no predictions", then a Daily Edition story card.
- **What works:** the pitch is clear in five seconds.
- **The problem:** "why would I use it?" is not answered. A casual fan has no standing need to know bullpen state, and nothing on the first screen creates curiosity with a named player or a surprising fact.
- **Would they return tomorrow?** Very unlikely. This is not the right first audience, and the Constitution's choice of "daily fan on a phone" as audience #1 is not supported by any evidence.

**Serious team fan.**
- **Is it useful before tonight's game?** Potentially yes. A team board that shows, per reliever, pitches yesterday, 3-day load, consecutive days, and a rest label answers exactly "who's probably down tonight?".
- **Current friction:**
  - reaching their team takes a select box;
  - on mobile, the reliever rows sit below a header, tabs, team picker, History link, state chip, sentence, data-through line, and methodology link;
  - the fan must scroll past chrome to get the answer.
- **Versus FanGraphs' Closer Depth Chart:** that page answers the same question in one scroll for the top ~6 arms, with pitch counts for 6 days and explicit "High Usage Alert" tags (https://blogs.fangraphs.com/fangraphs-feature-focus-closer-depth-chart/).
- **Where BaseballOS is better:** it covers the whole active bullpen and adds rotation-length context and "what changed".
- **Verdict:** better-assembled for a devoted team fan, but not dramatically enough to break an existing habit without a push.

**Creator / writer / broadcaster.**
- **Can they find an observation quickly?** Sometimes. Story cards and What Changed produce sentences.
- **Can they trust and cite it?** Mostly yes:
  - evidence links, data-through dates, and immutable share URLs are genuinely good for citation;
  - but the September outage (12 days stale while claiming currentness) is the kind of event that ends a writer's trust permanently if they are burned once.
- **Does it save research time?** For "who's been worked hard" across a whole pen, yes versus Baseball-Reference. It does not beat FanGraphs RosterResource, which writers already use.
- **Does it surface anything they'd miss?** Rotation-transfer (short starts pushing load to the pen) and change-since-yesterday are the two candidates. The June editorial artifacts show generated prose that is sometimes wrong in baseball terms, e.g. starters named as "the important-outs route" (`artifacts/four_beat_real_quality_audit_v1.json`); whether current copy still does this is UNKNOWN.

**Baseball analyst.**
- **Would they see it as additive?** Only marginally. They will see through the vocabulary quickly:
  - Team State is a headcount of relievers labelled Available against thresholds (`team_operations/contracts.py:67-79`), with every arm weighted equally; a closer and a mop-up man are interchangeable;
  - roles come from saves/holds shares (`services/pitcher_role.py`);
  - leverage index is effectively unused, and pitch-level data (velocity, spin) is parsed but never used in any derivation;
  - there is no outcome validation, and the one correlational study (`analysis/fatigue_era_results.json`) has a LOW tier with zero appearances by construction.
- **Verdict:** they will respect the transparency and determinism, and find the synthesis thin.

**Industry evaluator (club, media, or sports-data company).**
- **Seriousness:** yes, it looks serious. The engineering discipline would stand out in any interview: fail-closed publication proofs, advisory-lock writer fencing, immutable fingerprinted corrections, a clean `pip-audit`, zero TODOs, and 1,272/1,272 frontend tests passing.
- **Domain understanding:** present, but conservative and shallow on analytics.
- **What they would want for their own organization:** probably the *pipeline pattern* (canonical appearance ledger, correction policy registry, publication gates), not the product.
- **Verdict:** portfolio value is high; product value is not yet demonstrated.

---

## 5. Ten-Second Surface Audit

*Layout and copy: SUPPORTED (local renders). Live timing: UNKNOWN.*

| Surface | Primary question | Answer in 10s | Strongest element | Biggest confusion | Reason to continue | Reason to leave | Creates return? |
|---|---|---|---|---|---|---|---|
| Today `/` | What's the bullpen picture today? | The product pitch plus one story card. No league picture above the fold at 390px | Honest hero copy | Internal publication IDs shown publicly (`daily-edition-2026-09-03-…`); three competing sections (Daily Edition, Since Yesterday, Tonight's Watch) | A named team story | No immediate personal relevance | Weak |
| League Board `/dashboard` | Which bullpens are fresh/stretched/vulnerable? | Yes: a 30-team state landscape | One-screen league state | Overlaps Today; the state changes for about half the teams daily | Click into a Vulnerable team | The label alone is not actionable | Weak–moderate |
| Team Board `/bullpen?team=X` | Who in my team's pen is rested/taxed? | Desktop: yes (state chip, summary strip). Mobile: state chip only; arms below the fold | Active Bullpen rows with 7d appearances/pitches and last outing | 13 sections; chrome-heavy first viewport; "Team Bullpens" nav name vs "Team Board" | The actual rest table | Length and density | **Strongest candidate** |
| Pitcher `/pitcher/:id` | How has this arm been used? | Recent work and label | Recent-work panel | Raw "Failed to fetch" when the API is down | Game log | Commodity vs Baseball-Reference/Savant | Low |
| Matchup / Compare | How do two pens compare tonight? | Side-by-side state | Pairing | Two routes for similar answers | Pre-game curiosity | Adds little beyond two team boards | Low |
| What Changed (Team Board section / Since Yesterday) | What's different since yesterday? | Count deltas ("rested options moved from 3 to 6") | Only product in the market doing this structurally | Explains counts, not names; much of it is calendar effects (off days) | Genuinely new info daily | Often reads as noise | **Potentially high; unproven** |
| History `/history/team/:abbr` | How did we get here? | A log of past labels | Continuity | With a mean state run length of 1.85 days, history looks like noise | None strong | Nothing to conclude | Low |
| Search | Find a team or pitcher | Works | – | Separate page for a header-level function | – | – | None |
| Stories `/stories` | What else is interesting? | Templated recaps | Box-score game-shape recaps | Redundant with Today; empty-state renders "0" counts | A good recap | Templated voice | Low |
| Methodology / Trust / How to Read / About | Can I trust this? | Yes: unusually transparent | Thresholds published | Four pages for one purpose. Methodology says Stretched means "narrowed the clean **late-inning** options" (`Methodology.jsx:44`); the backend has no late-inning element | Credibility | – | None (by design) |

---

## 6. Daily Habit & Retention Audit

**What actually changes every day (measured).**
- I reconstructed Team State for all 30 teams from the 26 production snapshots committed between 2026-08-13 and 09-23 (750 team-to-next-snapshot transitions).

| Measure | Value |
|---|---|
| Teams changing state per snapshot | mean **15.6 of 30** (range 10–22) |
| Fresh → still Fresh next snapshot | **35%** (42 of 120) |
| Stretched → Stretched | 52% |
| Vulnerable → Vulnerable | 49% |
| Mean run length of a state | **1.85 snapshots** |
| Direct Fresh↔Vulnerable jumps | 5% of transitions |

- **Interpretation (PROVEN measurement; interpretation SUPPORTED):**
  - Team State is essentially a re-rendering of *yesterday's usage*. It changes constantly, which superficially supports "come back tomorrow".
  - But it also means the label carries little information a fan couldn't infer from "did the pen throw a lot last night?".
  - A signal that flips for half the league daily is not a "state" in the sense users will assume from the word. It is a day-after usage indicator.
  - This undermines Team State both as a headline and as history ("How did we get here?" becomes "it alternated").

**What changes after games:** pitch counts, rest labels, consecutive-day flags. This is the real daily value, and it is exactly what the free competitor grids also update.

**What changes during a series:** cumulative workload. The product shows 3/5/7-day windows, which is good.

**What changes when rosters move:**
- Transactions are ingested, and the Team Board has a Roster & Transactions section.
- InsidethePen (https://insidethepen.com/bullpen-roster-moves.html) and FanGraphs (https://www.fangraphs.com/roster-resource/transaction-tracker) already offer filterable pitcher transaction feeds.

**Is the change visible without rereading?**
- Partially. The What Changed section and Since Yesterday exist.
- But the June real-data review (`artifacts/what_changed_since_yesterday_review.json`) showed 15 of 17 teams receiving "more room" headlines on one day — a schedule off-day effect presented as news.
- Items are framed as count deltas ("rested options moved from 3 to 6"), not as named-arm facts ("Hader and Abreu are now back after two days off").
- Whether the current Team Board 2.0 What Changed (merged Sep 22) fixed this is UNKNOWN.

**Does What Changed produce retention value today?**
- **UNKNOWN, and structurally unmeasurable right now.**
- Only a page view with `entry_source=since_yesterday` is recorded. In-page What Changed interactions are not tracked.
- The one piece of retention data that does exist (browser-identity returning visitors) has never been reported in the repository.

**Why daily return value is weak (SUPPORTED):**
1. The core daily answer is also free elsewhere.
2. The distinctive signal is dominated by calendar and usage noise.
3. What Changed speaks in counts, not names.
4. There is no follow/notification mechanism; it was parked "until demand", and demand is never measured.
5. The site went stale for 12 days in September. Any nascent habit formed in August would have been broken.

---

## 7. Dead-Content Risk

This is the most important section. The question: *will BaseballOS be technically impressive but behaviorally irrelevant by Opening Day 2027?*

### Warning signs present (with evidence)

1. **Data users can already get elsewhere, as easily or more easily.** (SUPPORTED)
   Pitches-yesterday and recent-days workload grids are offered free by:
   - FanGraphs Closer Depth Chart (6 days, High Usage Alerts);
   - RotoWire Bullpen Usage (5 days, per team: https://www.rotowire.com/baseball/bullpen-usage.php);
   - Razzball Bullpen Chart (7 days with entry inning: https://razzball.com/bullpen-chart/);
   - FantraxHQ (adjustable window: https://fantraxhq.com/bullpen-usage-chart/);
   - ESPN reliever depth chart with "tired" rules;
   - InsidethePen, a free, bullpen-only 2026 entrant with daily usage, availability, team pages, roster moves, and closers (https://insidethepen.com/bullpen-usage.html).

   BaseballOS's per-arm rest table is *better-assembled* than most, not unique.

2. **Derived labels users may not need.** (SUPPORTED)
   - Four label families (Team State; arm reads; roles; and earlier identity/"trust hierarchy") plus an older "Available / On Watch / Limited" catalog that still exists in the canonical standard.
   - The June editorial artifacts contain phrases like "Flexible Distribution Bullpen: active capacity, clean options, and trusted-group breadth point to a bullpen with several usable lanes" (`artifacts/bullpen_identity_distribution_review.json`). That is internal jargon posing as insight.

3. **Infrastructure growing faster than user value.** (PROVEN)

   | Measure | End of June | Now |
   |---|---|---|
   | Non-test backend LOC | 73,050 | 215,171 |
   | Markdown files | 268 | 450 |
   | `frontend/src` | – | 29k lines; changed by only +12.9k/−6.8k in the last 60 days |

   Over the same 60 days: backend tests +135.7k, services +68.9k, scripts +33.7k, docs +37.6k lines.

4. **Sophisticated backend capability that does not change the product.** (PROVEN)
   - 68k lines of backend code are reachable only from scripts (repairs, audits, proofs), never from the web app.
   - The pipeline also builds evidence objects no API serves: `entry_band_usage_evidence.py`, `roster_depth_evidence.py`, and `team_relief_composition_evidence.py` (~7.9k lines combined).
   - Six recommendation-engine modules (4.3k lines) have no frontend consumer.
   - `/prospects/*` (6 routes) has no UI.
   - Tonight v1 (4 PRs, ~3.7k lines) is not consumed.

5. **Features built because they were architecturally possible.** (SUPPORTED)
   - Consequence intelligence, bullpen identity, trust hierarchy, four-beat story intelligence, and context explanations.
   - The intelligence audit rated all of these "Theater": they re-count the same Available/Monitor/Limited statuses and wrap them in rotating synonyms.

6. **Daily pages that change but don't *mean* more.** (PROVEN measurement) Team State churn of ~52% per day (Section 6).

7. **Content that loses relevance quickly without creating a historical reason to revisit.** (SUPPORTED)
   - 7,873 immutable share pages (93 MB in git) of frozen daily states.
   - Their historical value is limited because the underlying label turns over every ~2 days.
   - None has a per-team image, and the sitemap does not list them.

8. **Concepts that require explanation before they are useful.** (SUPPORTED) Four trust/explanation pages exist because the vocabulary needs them. "Watch Arm", "Coverage Arm", and "Limited Read" are not baseball vernacular.

9. **Usefulness that depends on already believing in BaseballOS.** (SUPPORTED)
   - The product's differentiator is framed as *trust* ("Trust is the foundation").
   - A new visitor cannot perceive trust gates; they perceive answers.
   - The trust machinery is invisible to exactly the people who would need convincing.

10. **Postseason blackout at peak bullpen attention.** (SUPPORTED)
    - The Bullpen Intelligence Standard excludes postseason game types (`docs/canonical/02…:269`).
    - At least 9 derivation modules filter `game_type == 'R'`.
    - The pitcher gameLog fetch (`services/mlb_api.py:526-535`) passes no `gameType`, so it returns regular-season logs by default.
    - Consequence: in October, when bullpens are most discussed nationally, BaseballOS will freeze on the final regular-season day or go quiet. No test covers postseason behavior (`grep` finds one incidental reference).

11. **Engineering-as-avoidance pattern.** (SUPPORTED — stated with evidence, not as a character judgment)
    - The June 2026 program audit already said "Stop adding certified surfaces… the project has accreted an enormous governance/certification apparatus… Much of this is ceremony, not capability."
    - Three months later:
      - docs grew from ~268 to 450 Markdown files;
      - backend code tripled;
      - the roadmap file grew to 125.6 KB with 65 revisions (36 versions in 28 days, Jul 29–Aug 26);
      - in the last 60 merged PRs, ~28% were user-facing and ~54% were trust/publication/infra;
      - Phase 6 "Growth and Validation" remains "Not started";
      - the traffic dashboard built on 2026-07-14 has never had a result written down.
    - The pattern of perfecting publication correctness while leaving demand unmeasured fits the definition of avoidance, whatever its cause.

### Evidence against the dead-content hypothesis

1. **The core question is real.** At least 10 products (fantasy, betting, and fan-oriented) answer "who's rested in this pen", which proves recurring demand for the *question*. (SUPPORTED)
2. **No competitor offers a structured day-over-day bullpen diff.** InsidethePen's "Biggest Movers" is a weekly article; Closer Monkey alerts cover closers only. (SUPPORTED; competitor UIs unverified)
3. **Rotation-transfer context is not productized anywhere else**; today it requires manual FanGraphs leaderboard work. (SUPPORTED)
4. **Every competitor team-level "fatigue score" is sold as betting or predictive input** (CLEATZ, Tony's Picks, InsidethePen Snapshot rankings, DeepMetric). A strictly descriptive, citable team-state receipt is distinctive for media use. (SUPPORTED)
5. **The labels are non-degenerate and data flows daily** when the pipeline is healthy. (PROVEN)
6. **Citable immutable URLs with data-through dates** are exactly what a writer needs to cite something. (PROVEN)
7. **The data layer is accumulating real, reusable assets** (Section 11). (PROVEN)

**Net judgement:** the dead-content risk is **high but not yet realized**. It is driven by product focus and distribution, not by engineering quality. The strongest predictor of failure visible today is not a bug. It is that BaseballOS can currently continue indefinitely without ever encountering evidence about whether anyone uses it.

---

## 8. Unique Value & Differentiation

**Unique today** (meaningfully differentiated, in production):
- *A strictly descriptive, reproducible team-level bullpen condition with a public rulebook, citable immutable URLs, and a data-through stamp.* Unique in combination (SUPPORTED). Caveat: the label's daily volatility limits its value.
- *Structured day-over-day comparison between two trusted publications.* Unique as a product (SUPPORTED), though currently framed as count deltas.

**Better assembled today** (the information exists elsewhere, but BaseballOS makes it easier):
- The full active bullpen in one table with per-arm 7-day appearances/pitches, last outing, and rest label. FanGraphs covers only the top ~6 arms; RotoWire and Razzball are raw grids.
- Starter-length pressure (Rotation Support Pressure: 7-day window; short start <15 outs; heavy if starter average <4.5 IP or ≥50% short, per `rotation_support_pressure.py:43-71`).
- Box-score game-shape recaps (lead protected/lost, starter covered the pen, etc.).

**Potentially unique** (the data foundation could support it; the product has not realized it):
- **Named-arm change feeds:** "X is back after two days off; Y threw 38 pitches on back-to-back days; Z was optioned and W recalled."
- **Entry-band deployment** (entry inning × run margin). Built in `entry_band_usage_evidence.py`, consumed by nothing. This is a much better role signal than saves/holds, and no free tool productizes it.
- **Multi-season usage history** from a clean canonical appearance ledger, e.g. "how did this manager deploy his pen in September last year?".
- **Leverage and handedness-aware coverage**, if LI and handedness are completed. Currently "Partial" per the Intelligence Standard.
- **Pitch-level fatigue signals** (velocity drop after back-to-backs). Pitch data is parsed in `play_by_play_foundation.py:709-735`, never used.

**Commodity** (little defensible differentiation):
- Pitches yesterday / last 3 / 5 / 7 days; consecutive-day flags; days of rest.
- Roles from saves/holds shares.
- Season ERA/WHIP of the active bullpen.
- Roster transaction lists.
- Pitcher game logs.
- The 0–100 fatigue score (also rated Theater: arbitrary weights, and it can never read LOW on an appearance day).

---

## 9. Competitive Reality

*All competitor details come from search results and snippets; page fetches were blocked. Treat UI specifics as unverified.*

| Product | What it answers | Cost | Clicks to "who's unavailable tonight for team X" | Predictive? |
|---|---|---|---|---|
| **InsidethePen** (https://insidethepen.com/) | Usage, "Available/Likely Rest", fatigue number, team pages, roster moves, closers, power rankings | Free (unverified) | 1–2 | Yes ("Likely to Pitch", forward-looking rankings) |
| **FanGraphs RosterResource Closer Depth Chart** (https://www.fangraphs.com/roster-resource/closer-depth-chart) | 6-day usage for ~6 arms/team, High Usage Alert (20+ pitches previous day, 2 straight days, or 3 of last 4), hot seat / on the rise | Free with ads | 1–2 | No (editorial role judgement) |
| **RotoWire** Bullpen Usage / Reliever Usage (https://www.rotowire.com/baseball/bullpen-usage.php) | 5-day usage per team; list of relievers on consecutive days | Unverified | 1 | Fantasy framing |
| **Razzball** Bullpen Chart / Autopen (https://razzball.com/bullpen-chart/) | 7-day calendar with pitches, entry inning, decision; role codes | Likely free | 1 (+scroll) | Autopen projects |
| **FantraxHQ** (https://fantraxhq.com/bullpen-usage-chart/) | Adjustable-window usage chart | Free | 1 | No |
| **ESPN reliever depth chart** (https://www.espn.com/fantasy/baseball/flb/story?page=REcloserorgchart) | Closer hierarchy with "tired" flags (2 of: 25+ pitches yesterday, 35+ over 3 days, both prior 2 days) | Free | 1 | "Next in line" |
| **Closer Monkey** (https://closermonkey.com/) | Closer depth chart and fatigue; instant email on closer change | $30/season premium | 1 | Closer-centric |
| **DeepMetric** (https://deepmetricanalytics.com/mlb/bullpen-tracker) | Availability ratings from 2- and 5-day load | Free (betting site) | 1 | Yes |
| **CLEATZ / Tony's Picks** | Team fatigue scores for bettors | Free | 1 | Yes (betting) |
| **Baseball-Reference / Stathead** | Game logs per pitcher | Free / paid | 5+ | No |
| **Baseball Savant** | Statcast; no availability view | Free | n/a | No |

**Question-by-question comparison:**

| Question | Best competitor today | BaseballOS position |
|---|---|---|
| Who threw heavily yesterday? | FanGraphs / InsidethePen | **Roughly equivalent** (full pen vs top 6) |
| Who pitched on consecutive days? | RotoWire Reliever Usage (league-wide list) | **Equivalent per team; weaker league-wide** (no league list of back-to-back arms) |
| Bullpen workload last 7 days | Razzball / FantraxHQ | **Stronger** (assembled, labelled, team total) |
| Has a reliever's role changed? | Closer Monkey (instant, closers) / FanGraphs tags | **Weaker.** Saves/holds-based roles are slow and noisy; "role movement" inherits rest churn |
| Has the active bullpen changed? | InsidethePen roster feed / FanGraphs Transaction Tracker | **Equivalent** |
| Has the rotation transferred workload to the pen? | Nobody (manual FanGraphs) | **Clearly stronger; barely addressed elsewhere** |
| What materially changed since yesterday? | Nobody as a product | **Clearly stronger in concept.** Execution (count deltas) is weak |
| What is the bullpen picture entering tonight? | InsidethePen (predictive) | **Equivalent, and strictly descriptive**, which matters to media and not to bettors |

**Discoverability (PROVEN):** web searches for `"BaseballOS" bullpen MLB`, `baseballos.app bullpen`, and `baseballoshq` returned no BaseballOS pages (only the GitHub repository for one query). InsidethePen ranks for most bullpen queries. For a product whose competitors are one search away, this is currently the single largest competitive weakness.

---

## 10. Intelligence Quality

All derivations are deterministic Python with no LLM (`story_reasoning_engine_v1.py:22`: "Deterministic and LLM-free").

| Capability | Input trustworthy | Reproducible | Baseball meaning defensible | Understandable | Real user question | Better than raw stats | Descriptive | Frontend faithful | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| **Arm reads** (`availability.py:205-255`) | Yes (box-score pitches/dates) | Yes | Mostly. Caveat: any back-to-back anywhere in the 5-day window forces ≥ Limited (`availability.py:109-111, 240`), so Mon+Tue usage still reads "Limited Rest" on Friday after two days off; many clubs would call that arm fresh. Limited and Avoid collapse to one public label | Yes | Yes | Modestly (saves mental arithmetic) | Yes | Yes (chips pass through) | **Better-assembled** |
| **Fatigue 0–100** (`fatigue.py`) | Yes | Yes | No. Arbitrary weights; the 7-day window spans 8 days; appearances double-counted; unknown pitch counts add 0; never LOW on an appearance day | Numeric, but meaningless | No | No | Yes | n/a | **Theater** (should not be public) |
| **Team State** (`contracts.py:67-79`) | Yes | Yes (exact fractions) | Weak. Equal-weight headcount; ignores role, handedness, off days | Yes | Partly | Little beyond "X of N rested" | Yes | **No.** Methodology says "late-inning" (not in the backend); `operatingStateReadModel.js:351` prints Avoid+Unavailable as "Unavailable"; the chip shows Avoid as "Limited Rest". **One status, three public groupings** | **Relabel**, with a volatility problem (Section 6) |
| **Roles** (`pitcher_role.py`) | Saves/holds (noisy) | Yes | Low bar (2 holds in 13 appearances → "Setup Arm"); entry inning and games finished unused | Yes | Yes | No (= SV/HLD columns) | Yes | Yes | **Relabel** |
| **Workload windows** | Yes | Yes | Yes | Yes | Yes | Assembly value | Yes | Yes | **Better-assembled** |
| **Workload concentration** (`workload_concentration.py`) | Yes | Yes | Weak (a top-3 share ≥62% is normal) | Moderate | Rarely | No | Yes | Yes | **Relabel** |
| **Rotation Support Pressure** | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | **Better-assembled; closest to additive** |
| **Schedule / recovery context** (`schedule_context.py`) | Yes | Yes | Would be | – | Yes | – | – | Not integrated | **Built, unused** |
| **Roster / relief composition evidence** | Yes | Yes | – | – | – | – | – | No API consumer | **Internal only** |
| **Trust hierarchy / identity** | Yes | Yes | No. Anchors must also be Clean Option that day, so "trust structure" moves with rest | Jargon | No | No | Yes | – | **Theater** |
| **Role movement** | Inherits | Yes | No (rest churn) | – | Yes | No | Yes | – | **Theater** until roles decouple from rest |
| **What Changed** (`what_changed_since_yesterday.py`, TB delta) | Yes | Yes | Counts, often calendar effects; selection basis literally `first_non_tiny_meaningful_change_in_engine_order_not_ranked` | Yes | **Yes** | Potentially | Yes | Two frontend representations | **Relabel today; highest potential** |
| **Stories / consequence clauses** | Box score | Yes (sha256-picked template variants) | Recaps yes; consequence clauses sometimes wrong (June: "relievers carried it home" citing the largest lead, not the lead at handoff; starters named as "the important-outs route"; "starters are averaging 2.4 innings", implausible) | Yes | Some | Recaps yes | Mostly | – | Recaps **Better-assembled**; consequence and four-beat **Theater** |
| **Historical context** | Yes | Yes | Log of labels | Yes | Rarely | No | Yes | – | **Relabel** |
| **Matchup context** | – | – | No platoon or handedness use | – | – | – | – | – | **Absent** |

**Validation gap (PROVEN):**
- No derivation is validated against outcomes.
- Availability threshold changes were tuned to the *shape of the label distribution* (`reports/availability_threshold_adoption_candidate_c.md`), not to whether "Unavailable" arms actually didn't pitch.
- The cheapest high-value validation — "how often did an arm labelled Unavailable pitch that night?" — has not been run. It uses only data BaseballOS already has.

**Editorial QA gap (SUPPORTED):** the automated "editorial review" artifacts check wording and vocabulary compliance, not baseball correctness. They passed outputs a knowledgeable fan would immediately flag.

---

## 11. Data Moat / Intellectual Property

**If the frontend disappeared tomorrow, would the data and modeling layer still be valuable?** Yes, modestly: as a clean, correction-tracked, reproducible 2026 (plus seeded 2024–25) MLB reliever-usage dataset and a proven ingestion pattern. It is not a moat. Every input comes from the public MLB Stats API, and a competent engineer could rebuild the raw data in weeks. The defensible part is the *accumulated, corrected, versioned daily record*, and that is only valuable if it keeps accumulating and someone uses it.

| Asset | Classification | Notes |
|---|---|---|
| Canonical appearance ledger with finality classification, dead-lettering, and the 10-day completeness publish gate | **Durable** | Protect it (PROVEN: `game_finality.py:69-117`, `dashboard_snapshot.py:351-373`) |
| Field-level correction policy registry and fingerprint-locked historical repairs (675-action official pitching line repair) | **Durable, expensive** | High integrity; not reusable across correction classes |
| Roster membership intervals, transaction history, 30-club canonical registry | **Durable** | Affiliate pollution filtered at consumers, not cleaned at source |
| Immutable daily published snapshots (league + 30 frozen team packages) | **Durable** | A daily memory of what was published; unique over time. No retention policy |
| Share artifacts (7,873) | **Reproducible derived** | Could be regenerated; do not belong in git |
| Arm reads, Team State, roles | **Reproducible derived** | Rules are simple and public |
| Play-by-play foundation (pitch speed, spin, type) | **Strategically valuable, unused** | The only path to non-commodity fatigue signals |
| Entry-band usage (inning × margin) | **Strategically valuable, unused** | The only path to defensible role modeling |
| Leverage index | **Partial / contradictory** | `sync.py:514-522` reads it; `fatigue.py:12-18` says it is unavailable |
| Pitcher logs, ERA/WHIP, schedule | **Commodity** | |
| Publication proof, trusted-serving authority, shadow continuous execution, incremental read models | **Optionality plus maintenance burden** | Strong guarantees, but a very high carrying cost for one founder |

---

## 12. Production Data & Sync Health

**Lifecycle as implemented (PROVEN from code):**
1. MLB Stats API.
2. Daily, postgame, and morning lanes via **Render Cron** (`5 10 * * *`, `5 2,4,6 * * *`, `5 14 * * *` UTC), with a GitHub Actions fallback 6–18 minutes later (`.github/workflows/baseballos-sync.yml:30-41`). A 3-minute shadow continuous cycle runs with publication disabled.
3. Canonical game logs, finality, roster snapshots, and transactions.
4. Fatigue and availability.
5. Candidate dashboard snapshot (full JSON), then gates: slate coverage → appearance ledger → comparison identity → Daily Edition → exact-30-team Team State proof.
6. A single transaction flips `is_published`.
7. Post-commit hooks: share artifacts and the Tonight v1 projection.
8. Request-time projection from frozen packages, served with ETag/304 and `max-age=0`.
9. Daily static distribution commits.

**Strengths (PROVEN):**
- Session-level PostgreSQL advisory writer lock, with abandoned-run reclamation.
- Due-window idempotency (`sync_schedule_attempts`).
- Shared GitHub concurrency group.
- Database triggers fencing legacy writers.
- Fail-closed finality.
- Dead-letter table.
- Transactional publication with rollback.
- The test harness refuses non-local or non-"test" databases (`tests/db_config.py:74-83`).

**Weaknesses:**
- **P1 — No alerting** (PROVEN).
  - `/api/health` is static and never touches the database.
  - `check_scheduled_sync_health.py` exists, but "alert routing remains an external configuration task" (`docs/current/SYNC_PIPELINE.md:73-77`).
  - The scheduler-health workflow is manual-only. There is no Sentry DSN by default and no Slack, PagerDuty, or uptime check in the repo.
  - A 12-day outage was possible because nothing paged anyone.
- **P1 — Recurrence of the same failure class** (PROVEN).
  - Affiliate team IDs (484, 531, 534, 5434) broke publication on Sep 11–12.
  - The fix (#838) filtered consumers.
  - The same class recurred in the Team Board 2.0 package path and needed six fixes on Sep 22–23 (#865–#870).
  - The source-level roster isolation (PR 831) landed on an integration branch, not `main` (INDICATIVE).
- **P1 — Freshness truthfulness** (SUPPORTED). During the outage the Dashboard reported `is_current=true`, age 0. Whether this is fixed is not proven.
- **P2 — No automatic retry.** The GitHub fallback only helps if the primary did not record the window. On Sep 12 the fallback ran 3h20m late (PROVEN, incident doc).
- **P2 — Boot depends on publication.** `render_start.sh` runs `prepare_daily_edition_snapshot` under `set -euo pipefail` before starting gunicorn, so a failure in that step can keep the API from booting (PROVEN code; runtime behavior UNKNOWN).
- **P2 — Uniqueness of the published snapshot is not enforced by the database** (non-unique index on `is_published`); it relies on the advisory lock alone (INDICATIVE).
- **P2 — No retention.**
  - Every candidate snapshot stores full JSON.
  - The shadow cron adds ~480 SyncRuns/day.
  - No pruning exists for snapshots, sync runs, observations, or proofs.
  - A "Supabase egress P0" fix already shipped on Sep 13 (#845) with no incident write-up (INDICATIVE of growing cost pressure).
- **Correction path** (PROVEN).
  - Safe, but each correction class is a bespoke 2,000–2,700-line planner/apply/closeout program with its own workflow.
  - A single-player repair module exists (`official_pitching_line_matt_festa_apply_2026.py`, 1,373 lines).

---

## 13. TN-00 / TN-01 / TN-02 Verification Status

All three, plus the rehearsal certification, merged to `main` on 2026-09-24 (PRs #872–#875). Test results come from this audit's local runs.

| Item | What it does | Implemented | Tested | Merged | Deployed | Naturally exercised | Verified in production | Uncertain |
|---|---|---|---|---|---|---|---|---|
| **TN-00** `1749d0e4` harden Tonight publication authority | Intraday repairs publish, prove serving, then rebuild Tonight; uniform Tonight response shell; rotation sidecar from the same snapshot | PROVEN | PROVEN (passes) | PROVEN | UNKNOWN (Render auto-deploy from `main` is SUPPORTED) | **Unlikely.** The intraday repair lanes it protects are manual-only and "retired for remainder of 2026" | No | Whether the code path will ever run in 2026 |
| **TN-01** `77b5f741` trusted Tonight v1 read model | New `tonight_publications` table (additive migration `c3e7a1d9f5b2`); post-commit projection hook; flag `TONIGHT_V1_PROJECTION` defaults **on**; immutability enforced by an ORM event only (no DB trigger) | PROVEN | PROVEN | PROVEN | SUPPORTED only by the TN-02 doc's claim that the table exists at head | UNKNOWN. Requires a trusted publication after deploy | No | Whether the migration applied; whether rows are being written |
| **TN-02** `521b81b1` serve trusted Tonight v1 | `?contract=tonight_v1` serves the stored row; fails closed with no-store; no fallback to v5 | PROVEN | PROVEN | PROVEN | SUPPORTED (doc) | **No at merge**: the doc records **0 rows** and `tonight_v1_publication_missing` | No | Everything post-merge |
| **Rehearsal** `6e44e215` | 3 new PostgreSQL rehearsal tests: publication → one immutable row matching the snapshot; Tonight team data matches Team Board for 4 clubs; 2 SQL statements; 304 on ETag; projection failure does not invalidate publication | – | PROVEN locally | PROVEN | n/a (test-only) | n/a | Local only | – |

**Test evidence (PROVEN):**
- The TN-00/01/02 test files pass on SQLite.
- `test_trusted_publication_rehearsal.py` fails 5 tests on SQLite by design (it asserts a PostgreSQL URL).
- All four files run on local PostgreSQL 16: **85 passed in 120s**.

**Frontend consumption (PROVEN): none.**
- `getTonightIntelligence({})` requests the default legacy `tonight_v5`.
- There is no frontend flag and no server-side switch to make v1 the default.
- The TN-02 doc names this as future work (TN-08). The canonical Roadmap does not mention TN at all and still says "No active implementation package".

**Conclusion:** TN-00/01/02 are **implemented, tested, and merged; deployment is probable but unproven; natural production exercise and production verification have not occurred; and their user-facing effect today is zero.** They should not be counted as delivered value until (a) a production row exists for a real trusted publication, (b) the served v1 payload has been compared against Team Board for all 30 teams on a real day, and (c) the frontend consumes it.

---

## 14. Architecture

**Protect:**
- Deterministic, backend-owned derivations with public vocabulary centralized (`pitcher_public_labels.py`, `team_state_public_vocabulary.py`). The frontend mostly passes labels through, enforced by `publicCopyPassThrough` tests.
- The appearance ledger and finality model; the dead-letter-don't-drop policy.
- Advisory-lock writer fencing and due-window idempotency.
- Immutable published snapshots with identity headers (`X-BaseballOS-Snapshot-ID`, `Data-Through`).
- Flask + Postgres + Vercel + Render cron: an appropriately simple stack. **Do not add queues, streaming, microservices, or Kubernetes.** No requirement demonstrates a need.

**Overengineered for current needs (SUPPORTED):**
- **Publication indirection.** 34 services with publication/snapshot/artifact/serving/delivery in the name (17.8k LOC), 11 `*authority*` services, 20 `*evidence*` services. A new surface (Tonight) needed four PRs: authority, read model, serving, and certification.
- **Shadow continuous execution** (every 3 minutes, publication disabled) and **incremental read-model rebuilds**, for a product that publishes once or twice a day to an unmeasured audience.
- **Two recommendation engines** with no UI; prospects API; observations/explanations layers with no consumer.
- **One-off 2026 repair programs living in `services/`** beside runtime code, sharing models; 68k LOC reachable only from scripts.

**Underengineered (SUPPORTED):**
- Alerting and monitoring (none).
- Rate limiting (none; see Section 18).
- Data retention (none).
- Source-level team-scope isolation (filtering at consumers instead).
- Code splitting (a single 747 KB bundle).
- Local development (Windows/PowerShell-specific; no containerized setup; the full suite needs Postgres).

**Hidden coupling / duplicated truth (PROVEN):**
- Avoid is grouped three different ways (chip, Team State, concern card).
- Methodology copy defines Stretched with a "late-inning" concept the backend lacks.
- Two What Changed UIs.
- Frontend role vocabulary lives in `utils/pitcherLabels.js`, `bullpenConcepts.js`, and `appearanceLanguage.js`.
- The founder's private posting board (`privatePostsView.js:461-560`) makes its own baseball threshold judgements in the browser.

**God modules (PROVEN):**
- `services/sync.py`: 7,379 lines, 134 functions, touched in 72 commits in 90 days.
- `api/bullpen.py`: 3,750 lines, 34 routes, mixing public, diagnostic, and open MLB-proxy routes.
- `services/intraday_reconcile.py`: 3,581 lines.

---

## 15. Performance

**Live measurements: UNKNOWN.** Production TTFB, API latency, cold-start behavior, and Core Web Vitals could not be measured (egress blocked). This is a material gap; see Section 29 for the checks to run.

**Measured locally (PROVEN):**

| Measure | Value | Assessment |
|---|---|---|
| Production build | Vite 5, 10s; **one JS chunk 747 KB (203 KB gzip)** plus 65 KB CSS; Vite chunk-size warning | P3. No code splitting; admin, private-posts (~2k lines), auth, and share-ops code ship to every visitor |
| Fonts | 4 Google font families, render-blocking (`index.html:23-25`) | P3 |
| `dist/` size | 94 MB, almost all `public/share` | P3 (deploy weight) |
| API calls per page | Home: 4 parallel. **Team Board: 3 serial** (`/bullpen/teams` → `/board-v2/core` → `/board-v2/details`). Dashboard: 1. Pitcher: 1–2. Compare: 2. Every page also POSTs a traffic event | Team Board waterfall = 3 round trips before the answer. On a cold Render instance this compounds (UNKNOWN magnitude) |
| Caching | In-flight GET dedupe plus in-memory TTL for 4 projection endpoints; ETag/304 server-side; no polling | Reasonable |
| Server config | gunicorn 2 workers, 60s timeout, 15s DB statement timeout (`render_start.sh`) | Adequate at low traffic. A past incident documented Tonight 503s from synchronous request-time assembly |
| Backend CI | ~36 minutes serial across 4 Postgres shards | P2 (developer velocity) |

**Loading, stale, and partial states (PROVEN, local):** thorough. Per-section failure with "Try again", `StaleDataNotice`, `staleWithError`. Exceptions: the Pitcher page shows raw "Failed to fetch", and the Team Board shows "Teams unavailable" with no explanation when the teams list fails.

---

## 16. Mobile & UX

*Local renders at 390px and 1280px with fixtures (SUPPORTED); screenshots were captured during the audit but are not committed.*

- **No horizontal overflow** at 390px on any captured page (PROVEN). Tables sit in `overflow-x-auto`, and 248 truncation/min-width usages handle long names.
- **Navigation:** the sidebar collapses to a hamburger below `xl`. There are 10 nav items, which is too many for mobile.
- **Team Board first viewport at 390px** (PROVEN): header, three tabs (Team Board / Compare Bullpens / Reliever Finder), team select, "View History", "Team State: Fresh" chip, one sentence, data-through, "Why this read?". **Zero reliever rows.** The Bullpen Summary starts at the bottom edge.
- **Team Board length** (PROVEN): 6,486px with one fixture reliever, across 13 sections (Summary → Active Bullpen → What Changed → Recent Usage → Rest Status → Workload Overview → Seven-day pitch contributors → Roles & Deployment → Performance → Rotation Impact → Roster & Transactions → Recent Relief Work → Share). Several sections restate the same 7-day workload in different cuts.
- **Home at 390px:** hero plus one story card that shows an internal publication ID and a "Generated" timestamp to the public.
- **Verdict:** on mobile, the experience is **responsibly compressed rather than intentionally designed** for the core job. The answer the user came for is not in the first screen.

---

## 17. Information Architecture

| Route / section | Classification | Rationale |
|---|---|---|
| Team Board (`/bullpen?view=board&team=X`) | **Essential** | This is the product |
| Team Board → Active Bullpen, What Changed, Recent Relief Work, Rotation Impact | **Essential** | The core answer plus the two differentiators |
| Team Board → Recent Usage, Rest Status, Workload Overview, Seven-day contributors | **Redundant** | Four cuts of the same 7-day workload. Merge into the Active Bullpen table |
| Team Board → Roles & Deployment, Performance, Roster & Transactions | **Supporting** | Collapse by default |
| Today `/` | **Essential, overloaded** | Merge in League Board's 30-team landscape; drop duplicate ledgers |
| League Board `/dashboard` | **Merge** into Today | Two "league picture" homes |
| Stories `/stories` | **Should disappear** (or fold into Today) | Redundant; templated; empty state looks broken |
| Compare (`?view=compare`) and Matchup (`/matchup/:id`) | **Merge** | Two surfaces for "two pens side by side" |
| Reliever Finder (`?view=pitchers`) | **Premature** | No evidence of need |
| Pitcher `/pitcher/:id` | **Supporting** | A necessary deep link |
| History `/history/team/:abbr` | **Premature** | Label log with ~2-day state runs |
| Search `/search` | **Should merge** into a header control | |
| How to Read / Methodology / Data & Trust / About | **Merge** into 1–2 pages | Four pages for one purpose |
| `/team/{ABBR}` static stubs | **Confusing** | JS redirect with `source=share` (misattributes organic visits as share landings); canonical conflict with the destination; no SPA route (client-side navigation 404s) |
| `/share/{id}` (7,873 pages) | **Supporting** | Good for citations; should not live in git |
| `/signin`, `/auth/verify`, follow-team API | **Premature** | No UI uses follow; accounts gated on unproven retention |
| `/prospects/*`, `/recommendations/*`, `/observations/*`, `/team-operations/*`, v1 `/board`, 29 unused `api.js` helpers | **Obsolete** | No consumers |
| `/posts-bpen-7f3d9c`, `/admin/product-intelligence` | **Internal, keep** | Properly auth-gated server-side (the obscure path is cosmetic; listing it in `robots.txt` advertises it) |

**Old concepts surviving beside new ones (PROVEN):**
- `BullpenBoardView.jsx` is unreachable but kept alive by 18 test files.
- The legacy `teamBoardV2` adapter is still reachable via test-injection props in production code.
- Three adapters exist for team state.
- The arm-availability catalog (Available / On Watch / Limited / Unavailable) coexists with the Pitcher Current Read labels (Clean Option / Watch Arm / …).
- The "Today" vs "Tonight" vs "The Slate" naming is unresolved across the canonical docs.

**Simplification counts as progress here.** Roughly half the routes can merge or disappear without losing any answer the product currently gives.

---

## 18. Codebase Health

| Dimension | Finding | Evidence | Matters for 2027? |
|---|---|---|---|
| Size | 574 non-test backend files, 215k LOC; `services/` is flat with 275 modules | PROVEN | **Yes.** Navigation cost |
| Runtime vs script-only | 138k LOC reachable from `app.py`; **68k reachable only from scripts**; 1.5k unreachable | PROVEN (AST import graph) | **Yes.** Every model change must keep the one-off programs compiling |
| Audit/repair/proof code by name | 117 files, 55.6k LOC (25.8%) | PROVEN | Yes |
| Backend tests | 428 files, 8,289 test functions, 208k LOC. Local sharded run: ~6,390 passed, 22+ failed (environmental: SQLite vs Postgres, missing git SHAs in clone), one shard hung | PROVEN | **Yes** |
| Test brittleness | 129 test files read source as text; 23 diff-guard against `origin/main`; module-digest pins; 2 tests depend on specific git objects | PROVEN | **Yes.** Every change pays this tax |
| Test cost from one-off tooling | 79 test files target audit/repair tooling = **~40% of CI shard time** | PROVEN (`tests/ci_shard_manifest.json`) | **Yes.** The cheapest large velocity win |
| Frontend tests | 110 files; `npm test` **1,272/1,272 passed** in 192s; 72 files assert on source text | PROVEN | Moderate |
| Dead code | ~2.3k frontend lines unreachable; 29 unused `api.js` exports; `recalculate_fatigue.py`, `analysis/`, `story_orchestrator/`, `story_writers/`, `recommendation/` have no runtime consumer | PROVEN | Low to moderate |
| TODO/FIXME | 0 backend, 0 frontend | PROVEN | Positive |
| Dependencies | `pip-audit`: clean. `npm audit`: 11 (mostly dev); prod: 2 moderate (react-router). **Accepted-risk entries expire 2026-11-13**, after which CI fails until the router v7 migration lands | PROVEN (`.github/dependency-audit-accepted.json`) | **Yes, a hard deadline** |
| Security | No hardcoded secrets; production fails fast on missing `SECRET_KEY`/`DATABASE_URL`/`ADMIN_API_TOKEN`; constant-time admin token; CORS allowlisted; private routes gated server-side. **Gaps: no rate limiting anywhere** (magic-link email `POST /auth/request-link`, `/audience/signup`, `/traffic/*` are unauthenticated); **open `/mlb/*` proxy routes** to the MLB API; three unauthenticated `*/diagnostic` GETs | PROVEN | P2 before any growth push |
| Deploy reproducibility | No `render.yaml`; Render cron and environment config live only in the dashboard | PROVEN | Yes. Single point of knowledge |
| Repo weight | `frontend/public` holds 7,913 generated files; `public/share` added ~695k lines in 60 days | PROVEN | Low for code, high for clone/deploy size |
| Documentation | 400 docs files, 120k lines; archive alone 68k lines; roadmap 125.6 KB, 65 revisions; canonical docs disagree with each other and with code (6 vs 7 authorities; Today vs Tonight; History status; the roadmap omits TN and CU work) | PROVEN | **Yes.** It costs founder hours and obscures state |

**Cleanup that matters:**
1. Archive completed 2026 repair/audit programs, their workflows, and their tests. This removes ~40% of CI time and 68k LOC of coupling.
2. Collapse the publication "authority" layering where there is one caller.
3. Split `sync.py` and `api/bullpen.py` along lane/route-group seams.
4. Add retention.
5. Complete the router v7 migration before 2026-11-13.

**Cleanup that is merely aesthetic:** commit-prefix consistency, docs tidying beyond deleting the archive, `COIN_Philosophy.md`, small dead helpers.

---

## 19. Founder Sustainability

**Could one developer operate this through the 2027 season while improving the product? Not in its current form.** (SUPPORTED)

What prevents it:
1. **Silent failure.** With no alerting, the founder must personally check Render and GitHub daily. In 2026 a 12-day staleness window occurred anyway.
2. **The recurring firefighting class.** Team-universe and publication-accounting failures recurred 11 days after the incident fix. There were fix clusters on Sep 2–4 and Sep 22–23, Aug 6 (runtime budget), and Jul 4–8 (missing appearances). That averages roughly one significant publication incident every 2–4 weeks in-season.
3. **Manual recovery.** 24 of 25 workflows are manual `workflow_dispatch`. Recovery requires diagnosis, a patch, a deploy, and dispatching `recovery_daily` with the confirmation phrase `RECOVER`.
4. **Correction cost.** Each new class of historical correction is a bespoke multi-thousand-line program.
5. **Test tax.** A ~36-minute CI run plus brittle source/digest/freeze-guard tests on every change.
6. **Dashboard-only configuration.** Render cron schedules and environment variables are not in code.
7. **Cost trajectory.** No retention; a 3-minute shadow cron; full-JSON snapshots; a Supabase egress P0 already hit. Hosting cost is UNKNOWN but trending upward (INDICATIVE).
8. **Pace.** Commits on 111 of 116 days since June 1, at every hour of the day (≈250 commits between 00:00 and 03:00 local time). The Constitution itself says scope "must survive a full-time job, family responsibilities, and limited weekly hours". The current operating model does not meet the founder's own constraint (SUPPORTED).
9. **Season rollover risk.** 65 service modules reference 2026 explicitly; several hardcode `DEFAULT_SEASON = 2026`. The offseason→spring→regular-season transition, including the 40-man/26-man roster reset and spring-training game types, is untested (INDICATIVE).

What would make it operable:
- Alerting on publication age (a single external uptime check on a DB-backed freshness endpoint).
- Archiving one-off programs.
- A written, short weekly-ops budget.
- Reducing the publication pipeline to the minimum needed for correctness.

---

## 20. Offseason Survival

- **Regular season ends ~2026-09-27.** The postseason is excluded by design (Section 7, item 10). From then until ~Feb 2027 spring training, Tonight, Team State, arm reads, What Changed, and Rotation Impact produce nothing new. `slate_coverage.py:41` treats only Nov–Feb as offseason, so October behavior (postseason games that are not ingested as bullpen workload) is UNKNOWN.
- **Features that die completely:** Today/Tonight, Team State, arm reads, What Changed, Since Yesterday, Stories, Matchup, share generation.
- **Features with durable offseason value (if built):**
  - Season retrospectives per team: usage concentration, how often the pen was Vulnerable, back-to-back counts per arm, and entry-band deployment.
  - Reliever usage leaderboards (most back-to-backs, highest 3-day loads).
  - Roster/transaction continuity into 2027.
  - Spring roster construction ("who's competing for the last bullpen spots").
  - Evergreen methodology content for search.

  **None of these exist today** (PLANNED ONLY or absent).
- **Retention cliff: yes, total.** With no accounts, no follows, no email list evidence, and no search presence, there is no channel to bring anyone back in March 2027. Any audience built in 2026 (size UNKNOWN) will have to be re-acquired.
- **Opportunity:** the offseason is the cheapest time to (a) run outcome validation on 2026 data, (b) publish evergreen season retrospectives that earn search traffic, and (c) simplify the codebase without in-season firefighting.

---

## 21. Most Plausible 2027 Users

*No persona below is validated; the repository contains no user evidence. The ranking uses job-to-be-done fit plus the competitive gaps found.*

**1. Beat writers, team-site bloggers, and team podcasters (SUPPORTED as best fit).**

| Aspect | Assessment |
|---|---|
| Job to be done | Before writing a game preview or recap, or before recording: "who's down tonight, why is the pen taxed, what changed?" |
| Current workaround | FanGraphs Closer Depth Chart plus Baseball-Reference game logs plus memory |
| BaseballOS advantage | Full active pen in one table; rotation-transfer context; a citable, dated, immutable receipt; strictly descriptive (safe to quote); change since yesterday |
| Frequency and trigger | Daily in-season; triggered by the pregame writing window |
| Why they'd return | It saves 5–10 minutes and gives a citable line |
| Why they'd stop | One stale or wrong day; the answer not above the fold; label jargon they can't quote without explaining |

**2. Highly engaged single-team fans (INDICATIVE).**

| Aspect | Assessment |
|---|---|
| Job to be done | "Is the closer available tonight? Why did the manager use X?" |
| Current workaround | Team subreddits, X beat writers, FanGraphs |
| BaseballOS advantage | One URL per team; What Changed |
| Frequency | Daily, but only if something pushes them (a notification, a subreddit link) |
| Why they'd stop | No push mechanism; the same info is on free grids |

**3. Broadcast research staff (INDICATIVE, high value, small N).** A pregame notes packet needs bullpen availability. They have internal club information, so BaseballOS is a cross-check at best, but the descriptive-only posture is attractive.

**4. Fantasy and betting users (explicitly out of scope).** They are the largest existing demand for "who's available tonight", served by InsidethePen, Closer Monkey, RotoWire, DeepMetric, and CLEATZ. BaseballOS's guardrails intentionally forgo them. That is a legitimate choice, but it removes the biggest existing audience for this exact question. The founder should make that trade-off consciously, with numbers.

**5. Professional baseball personnel.** Clubs have far richer private data. BaseballOS's value to them is as a *hiring portfolio*, not a tool.

---

## 22. Opening Day 2027 Scenarios

**Realistic capacity:**
- The period between now and Opening Day (~late March 2027) is ~26 weeks.
- In-season firefighting ends this week, which frees capacity.
- But the router v7 deadline (Nov 13), season rollover, and any 2027-specific source changes will consume a meaningful share.
- Realistic new product capacity: **a handful of focused changes**, not the roadmap.

### A. BaseballOS compounds

- **The smallest plausible version:** a fast, mobile-first per-team board where the first screen lists every active reliever with a one-word rest label and the receipt (pitches yesterday, 3-day total, consecutive days). Directly under it: "Since yesterday", in *named-arm* terms. One league page shows 30 teams, plus the rotation-pressure flag.
- **What creates the habit:** a daily, reliable, sub-second answer plus a "since yesterday" line worth reading, delivered to where writers and fans already are (X/Bluesky/Reddit replies with the team link; an optional morning email per team).
- **Who adopts first:** 10–30 team-specific writers and podcasters who find it saves time and is safe to cite.
- **What makes them return:** it is right every day, it is first on the question, and it names arms.
- **Observable by May 2027:** a few hundred weekly returning browser identities, concentrated on team boards, with external citations.

### B. BaseballOS remains technically strong but niche

- **Likely state if engineering continues and distribution stays modest:**
  - a correct, well-proven daily pipeline;
  - a dense Team Board visited by the founder and a few dozen people;
  - no search presence;
  - share pages generated daily and rarely opened;
  - the roadmap still expanding.
- **Does this still have value?** Yes, substantial *portfolio and professional* value: the engineering evidence (publication proofs, correction policy, fencing, test discipline) is credible in interviews at sports-data companies, media tech, or club R&D engineering. Acquisition value is negligible without users; the data is rebuildable from public sources.

### C. BaseballOS becomes dead content

- **What it looks like:** the site loads, publishes daily, and is correct. Team pages flip between Fresh and Stretched every other day, and nobody notices. The founder spends in-season weeks fixing publication accounting. Visitors arrive from occasional social posts, bounce after one page, and don't return. By June the founder is maintaining a pipeline for an audience of one.
- **Warning signs already visible today that would have predicted it:**
  - zero search visibility;
  - no recorded usage numbers despite existing instrumentation;
  - Growth/Validation phase "Not started" at season end;
  - ~54% of recent PRs going to trust/publication machinery;
  - a 12-day outage with freshness still reporting "current";
  - the headline signal turning over for half the league daily;
  - the core table duplicating free tools;
  - the retention levers (follow and notification) parked "until demand" while demand is never measured.

---

## 23. Missing Capabilities

**Missing and existential**
1. **Demand measurement that is actually looked at.** A written weekly readout from the existing traffic dashboard, plus interaction events for What Changed and Team Board depth, plus a fix for the `source=share` misattribution on `/team/{ABBR}`.
2. **Operational alerting on publication age.** An external check that fails if the served `Data-Through` is older than expected, routed to the founder's phone.
3. **Discoverability.** Server-rendered, indexable team pages with real content (the static stubs already contain it but JS-redirect away), real per-page titles, sitemap `lastmod`, and a search-console property. Right now nobody can find the product.
4. **An above-the-fold mobile answer on Team Board.** The active bullpen table first.

**Missing and high leverage**
1. **Named-arm What Changed** ("back after 2 days off", "3rd appearance in 4 days", "optioned/recalled"), replacing count deltas.
2. **Outcome validation** of arm reads: how often labelled-Unavailable arms pitched; how often Clean Options were used in high-leverage spots. This turns "trust" from process into evidence.
3. **Role from entry-band deployment** (already computed) instead of saves/holds.
4. **Team State stabilization or reframing**: either weight arms by role, or present it honestly as "after last night" rather than as a state.
5. **Distribution to writers.** Per-team morning snapshot email or post; a copy-ready citation line.
6. **Offseason retrospectives** built from the 2026 ledger.

**Valuable later**
- Postseason coverage (high attention, small window; needs game-type work).
- Pitch-level fatigue signals (velocity after back-to-backs).
- Handedness/leverage-aware coverage.
- Follow My Team and notifications (only after return behavior is observed).
- Multi-season history views.

**Attractive distractions**
- More trust UI, certification, rehearsal suites, or proof lifecycles.
- Continuous (every-3-minute) publication.
- Recommendation engines, identity labels, consequence copy, four-beat stories.
- Accounts before retention; embeds/API/monetization before users.
- Reliever Finder, Compare, and Matchup polish.
- Further documentation restructuring.

---

## 24. What BaseballOS Should Stop Doing

1. **Stop adding publication/authority/proof layers.** In the last 60 merged PRs, 13 were trust/publication and 19 infra/reliability versus 17 user-facing. The existing gates already fail closed; the marginal user value of another proof is near zero. (SUPPORTED)
2. **Stop building contracts nobody consumes.** Tonight v1 is the current example: four PRs, a table, and a certification suite, with no frontend consumer. Before starting TN-03…TN-08, decide whether Tonight is the habit loop at all. (PROVEN)
3. **Stop writing prose-generation layers** (consequence intelligence, identity, four-beat, context explanations). Stop presenting the 0–100 fatigue score. (SUPPORTED)
4. **Stop documentation churn.** 125.6 KB roadmap, 65 revisions; 183 docs commits in 90 days; 68k-line archive. One page of current state and one decision log are enough for one founder. (PROVEN)
5. **Stop fixing symptoms of the affiliate team scope at each consumer.** Fix it once at the source (roster/team assignment), or accept a single canonical filter at ingestion. (PROVEN recurrence)
6. **Stop keeping one-off 2026 repair programs in `services/` with CI tests.** Archive them after closeout. (PROVEN)
7. **Stop committing generated share HTML to git.** Serve it from storage or the database. (PROVEN)
8. **Stop deferring growth measurement behind "trust gates hold".** Trust gates have held for most days since August; the gate has become an indefinite deferral. (SUPPORTED)

The avoidance concern (Section 7, item 11) is stated with evidence, not as a verdict on motive: the June audit named this pattern, and the three months since have amplified it.

---

## 25. What BaseballOS Must Protect

1. **The canonical appearance ledger and finality/dead-letter policy.** It is the reason BaseballOS's numbers can be trusted, and the durable asset (Section 11).
2. **Backend-owned, deterministic, public-rule labels.** This is the credibility differentiator versus black-box "fatigue ratings" and betting tools.
3. **Immutable, dated, citable publications with identity headers.** This is exactly what writers need to cite something; no competitor offers it.
4. **Fail-closed publication**, simplified: keep the 30-team proof and appearance-ledger gate; drop redundant layers.
5. **The advisory-lock writer fence and due-window idempotency.** Small, correct, and cheap.
6. **The descriptive-only posture**, at least for the media/fan segment. It is the one positioning no competitor occupies.
7. **The first-party privacy-bounded traffic measurement.** It already answers the most important question; it only needs to be read.
8. **The rotation-support-pressure and What Changed concepts.** These are the two most differentiated ideas.
9. **The 2026 season record itself** (snapshots, rosters, transactions). A second season of it in 2027 enables year-over-year context no one else has in this form.

---

## 26. Five-Capability Product Reduction

If BaseballOS could ship only five capabilities for Opening Day 2027:

1. **Team Board: the active bullpen answer.** Every active reliever, one rest label each, with the receipt inline (pitches yesterday, 3-day pitches, consecutive days, days since last outing). Mobile-first, above the fold, <1s on a warm cache.
2. **Since yesterday, in named-arm terms,** per team and league-wide. Who became unavailable or available, who joined or left the active pen, notable usage (back-to-backs, 30+ pitch outings).
3. **Rotation pressure.** Has short starting pushed unusual load onto the pen this week, with the starts listed.
4. **League one-screen.** 30 teams with one-line "why" and the rotation flag, linking to boards. This merges Today and League Board.
5. **Permanent, citable daily record.** An immutable dated URL for every team-day, with a copy-ready citation line. This is the memory and receipt.

**What could be deleted without destroying the value proposition:**
- Stories.
- Four-beat and consequence copy.
- Identity and trust hierarchy.
- The public fatigue score.
- Compare, Matchup, Reliever Finder, and the History page (keep the data).
- Search as a page.
- Three of the four trust pages.
- Accounts and follow endpoints.
- Prospects, recommendations, and observations APIs.
- Shadow continuous execution.
- Tonight v1 as a separate contract, unless it becomes the carrier for #4.

**BaseballOS in one sentence after the reduction:**
> *BaseballOS is a free, daily MLB bullpen board for every team that shows who is rested, who is taxed, and exactly what changed since yesterday — with the box-score receipt and a citable link for every label.*

That sentence is the real product. Nearly everything else in the repository is either in service of it or not needed.

---

## 27. Kill Criteria

These are **proposed** thresholds for the founder to adopt, adjust, and write down *before* the 2027 season. They are judgement calls, not derived facts. Their purpose is to make a future stop/reduce decision mechanical rather than emotional. All can be measured with the existing traffic instrumentation plus the two missing interaction events.

| # | Condition (measured over the stated window) | Why it matters |
|---|---|---|
| K1 | After a deliberate awareness effort that produces **≥2,000 external visitors in April 2027**, fewer than **10%** of them return on a different day within 14 days | Awareness adequate; value insufficient |
| K2 | By **June 1, 2027**, fewer than **50 browser identities** are active on **≥8 distinct days** in any 30-day window | No habit has formed |
| K3 | Fewer than **25 identities** open the **same team's** board on ≥10 days in May 2027 | The Team Board is not a repeat destination |
| K4 | In a structured creator trial (**15–20** targeted beat writers/podcasters, 30 days), fewer than **3** cite or link BaseballOS **≥3 times** | The strongest-fit segment rejects it |
| K5 | What Changed / Since Yesterday is opened in fewer than **5%** of Team Board sessions after 30 days of instrumentation, *and* named-arm redesign does not lift it | The returning-user mechanism does not work |
| K6 | In a side-by-side task test (10 users × 5 bullpen questions) against FanGraphs Closer Depth Chart and InsidethePen, BaseballOS is **not faster or preferred** on at least 3 of 5 questions | No workflow advantage |
| K7 | Outcome validation shows labelled-**Unavailable** arms pitch at a rate **not materially lower** than labelled-Clean arms (e.g. less than a 3× difference) | The core label is not informative |
| K8 | Over any 4-week in-season window, **>50%** of founder engineering hours go to pipeline/publication repair, **or** there are **≥2 incidents of >48h staleness** in the first 60 days of 2027 | Unsustainable to operate |

**Rational response if K1–K3 are met:** stop major investment in the public product. Keep the pipeline running at minimal cost as a portfolio asset and data record, or open-source it.
**Rational response if only K8 is met:** simplify operations before any new feature work.

---

## 28. Findings Register

| ID | Severity | Evidence | Area | Finding | User consequence | Recommended action |
|---|---|---|---|---|---|---|
| F-01 | P1 | PROVEN | Demand | No usage, return, or citation numbers exist anywhere in the repo, though first-party traffic reporting (returning visitors, sessions, entry sources) has existed since 2026-07-14 | Investment decisions are made blind | Pull 30/90/all-time numbers from `/admin/product-intelligence` now; write a weekly readout |
| F-02 | P1 | PROVEN | Distribution | "BaseballOS" is not findable by web search; team pages are JS-redirect stubs with conflicting canonicals; sitemap has no `lastmod` | New users cannot find it | Make `/team/{ABBR}` real server-rendered pages; Search Console; sitemap `lastmod` |
| F-03 | P1 | SUPPORTED | Reliability / trust | Sep 10–21: league publication stuck while Dashboard reported `is_current=true`, age 0; the Team Board omitted the failure warning | Users see stale data labelled current; trust damage | Verify the freshness fields are now derived from the served snapshot versus today's slate; add a regression test |
| F-04 | P1 | PROVEN | Operations | No alerting; `/api/health` is static; scheduler health check is manual | Multi-day outages go unnoticed | External check on served `Data-Through` age → phone alert |
| F-05 | P1 | PROVEN | Reliability | The affiliate team-universe failure recurred (Sep 12 → Sep 22–23, six fixes); fixed by filtering consumers, not at source | Recurring publication failures | Single canonical team-scope filter at ingestion/roster authority |
| F-06 | P1 | PROVEN (measured) | Intelligence | Team State changes for 15.6/30 teams per snapshot; mean run 1.85; Fresh persists 35% | The headline label reads as noise; history is uninformative | Reframe as "after last night", or weight by role / smooth; validate |
| F-07 | P1 | SUPPORTED | Strategy | ~54% of the last 60 PRs went to trust/publication/infra; backend LOC tripled since June; Growth/Validation phase not started | Engineering does not convert to user value | Freeze infrastructure work; set a demand gate (Section 27) |
| F-08 | P1 | SUPPORTED | Product scope | Postseason game types are excluded; the gameLog fetch defaults to the regular season; no tests | Product goes quiet at peak bullpen attention | Decide explicitly: either a "season complete" state with retrospectives, or scoped postseason support |
| F-09 | P1 | PROVEN | Mobile UX | Team Board first viewport at 390px shows no reliever rows; 13 sections; ~6.5k px with one arm | The core answer requires scrolling on the primary device | Active bullpen table first; collapse the rest |
| F-10 | P2 | PROVEN | Intelligence / consistency | Avoid shows as "Limited Rest" (chip), "severe" (Team State), and "Unavailable" (concern card); Methodology defines Stretched with a "late-inning" element the backend lacks | Users see contradictory statements | One public mapping; fix the Methodology copy |
| F-11 | P2 | PROVEN | Intelligence | Any back-to-back in the 5-day window forces ≥ Limited even after 2+ days off | Over-conservative labels; fewer Clean Options; inflates Stretched/Vulnerable | Restrict the back-to-back rule to the last 2–3 days, or require recent pitches |
| F-12 | P2 | PROVEN | Intelligence | The 0–100 fatigue score has arbitrary weights, double counting, and can never read LOW on an appearance day | Misleading if exposed | Remove from public surfaces; keep internal or delete |
| F-13 | P2 | SUPPORTED | Intelligence | Roles come from saves/holds shares; entry-band deployment is computed but unused; LI handling contradictory | Roles are commodity and noisy | Use entry-band plus games finished |
| F-14 | P2 | SUPPORTED (June artifacts) | Editorial | Generated stories contained baseball errors (largest lead vs handoff lead; starters as the late-inning "route"; implausible 2.4-IP rotation); automated review checks wording only | Credibility damage with knowledgeable readers | Cut generated consequence/four-beat copy; keep factual recaps |
| F-15 | P2 | PROVEN | Delivery | Tonight v1 (TN-00/01/02) merged; frontend still uses v5; 0 production rows at merge | Zero user effect from recent work | Verify rows exist; decide whether to wire it or stop |
| F-16 | P2 | PROVEN | Analytics | `/team/{ABBR}` redirect adds `source=share`, so organic and search visits count as share landings; What Changed interactions untracked; `/search`, `/matchup`, `/history` not tracked | Share and retention metrics are distorted | Fix entry source; add 2–3 interaction events |
| F-17 | P2 | PROVEN | Security | No rate limiting (magic-link email, signup, traffic POSTs); open `/mlb/*` proxy; unauthenticated diagnostics | Email abuse and sender-reputation risk; resource abuse | Add basic rate limits; remove the proxy/diagnostic routes |
| F-18 | P2 | PROVEN | Dependencies | react-router accepted-risk entries expire 2026-11-13; CI will fail after that | Forced migration under deadline | Schedule the router v7 migration in October |
| F-19 | P2 | PROVEN | Velocity | 208k test LOC; ~40% of CI time on one-off tooling tests; source/digest/freeze-guard brittleness; tests depend on git objects | Every change is slower | Archive one-off tooling and its tests |
| F-20 | P2 | PROVEN | Architecture | 68k LOC reachable only from scripts sits in `services/`; god modules (`sync.py` 7.4k, `api/bullpen.py` 3.75k) | Model changes are costly | Archive; split along seams |
| F-21 | P2 | INDICATIVE | Cost / ops | No retention for snapshots, sync runs, or proofs; 3-minute shadow cron; Supabase egress P0 (#845) without an incident write-up | Rising cost; slower queries | Retention policy; disable the shadow cron in the offseason |
| F-22 | P2 | PROVEN | Architecture | API boot runs `prepare_daily_edition_snapshot` under `set -e` before gunicorn | Publication-state problems can block the API | Make it non-fatal for serving |
| F-23 | P2 | INDICATIVE | Integrity | `is_published` uniqueness is not DB-enforced (non-unique index); relies on the advisory lock | Theoretical double-publish | Partial unique index |
| F-24 | P2 | PROVEN | IA | Three home-like surfaces; four trust pages; Compare and Matchup overlap; 10 nav items | Diluted first impression | Merge per Section 17 |
| F-25 | P2 | SUPPORTED | Founder sustainability | Commits on 111/116 days, all hours; the manual recovery path; config only in the Render dashboard | Burnout; single point of knowledge | Ops budget; `render.yaml`; alerting |
| F-26 | P2 | PROVEN (fixed) | Correctness history | Until Sep 23, starters' starts were displayed as bullpen workload for mixed-usage arms | Wrong numbers were shown | Add a validation check comparing displayed bullpen workload to relief-only totals |
| F-27 | P3 | PROVEN | Performance | Single 747 KB JS chunk; 4 render-blocking font families; Team Board 3-call waterfall | Slower mobile first load | Route splitting; font trim; combine board calls |
| F-28 | P3 | PROVEN | Repo hygiene | 7,873 generated share pages (93 MB) committed to git | Repo/deploy bloat | Move to object storage/DB |
| F-29 | P3 | PROVEN | Docs | Canonical docs disagree (6 vs 7 authorities; Today/Tonight/Slate; History status; roadmap omits TN and CU work; launch doc says no tracking exists) | Founder time; confusion | Replace with one current-state page and one decision log |
| F-30 | P3 | PROVEN | Dead code | ~2.3k unreachable frontend lines; 29 unused API helpers; recommendation, prospects, observations routes without consumers | Maintenance drag | Delete |
| F-31 | UNKNOWN | UNKNOWN | Performance | Live TTFB/API latency/cold starts not measurable from the audit environment | Habit may fail on slowness | Run the Section 29 checks |

---

## 29. 2027 Decision Framework

### Evidence that BaseballOS has a legitimate future
- The core question ("who's rested/taxed in this pen tonight?") has proven recurring demand: at least 10 products serve it. (SUPPORTED)
- Two genuine gaps exist in the market — structured day-over-day change and rotation-transfer context — and BaseballOS is the only product with both partially built. (SUPPORTED)
- A strictly descriptive, citable, dated bullpen record fits media use better than the betting/fantasy-framed alternatives. (SUPPORTED)
- The data backbone is correct, fail-closed, and accumulating a daily record that becomes more valuable in year two. (PROVEN)
- The labels are non-degenerate on live data, and data flows most days. (PROVEN)
- The engineering quality would be credible to any professional evaluator. (PROVEN)

### Evidence that BaseballOS could fail despite strong engineering
- No demand evidence has ever been recorded, and nothing in the operating system forces it to be. (PROVEN)
- The product is invisible to search; the leading free competitor is not. (PROVEN)
- The everyday answer overlaps heavily with free, established tools. (SUPPORTED)
- The distinctive headline label turns over daily for about half the league. (PROVEN)
- A 12-day stale period with "current" freshness signals, and the same failure class recurred. (PROVEN/SUPPORTED)
- Engineering allocation has consistently favored proof and infrastructure over user-facing work, three months after being warned. (SUPPORTED)
- Total offseason cliff with no channel to re-engage users. (SUPPORTED)
- The founder's working pattern conflicts with the founder's own stated constraints. (SUPPORTED)

### Questions that remain unresolved
1. How many external browser identities visited in the last 30/90 days, and what share returned on a different day? *(Answerable today from `/admin/product-intelligence`, or with a read-only query on `traffic_page_views`: distinct `visitor_id` with ≥2 distinct `date(occurred_at)`, excluding `traffic_internal_visitors` and `is_bot`.)*
2. Which surfaces do returning visitors actually open (the `surface` / `team_ref` distribution for returning identities)?
3. Did the social posting board produce any site sessions (`utm_source` / `referrer_domain`)?
4. Is the Sep 12 freshness misreport fixed? Does the served `Data-Through` currently match yesterday?
5. Do production `tonight_publications` rows exist, and does the v1 payload match Team Board for all 30 teams?
6. What are live Team Board TTFB and full-load time on a cold Render instance on a phone?
7. How often did arms labelled Unavailable pitch that night in 2026?
8. What is the monthly hosting cost, and how is it trending?

### What must become true before Opening Day 2027
1. A written demand baseline from 2026 data (questions 1–3 above), plus adopted kill criteria.
2. Alerting on publication age that reaches the founder within hours.
3. Team pages that search engines can index and that rank for "[team] bullpen" queries; at least a Search Console property with impressions.
4. A Team Board whose first mobile screen is the active bullpen table.
5. What Changed expressed in named arms, with interaction tracking.
6. One validated claim about label accuracy from 2026 data (the K7 test).
7. Completed 2026 one-off programs archived; CI time roughly halved; router v7 migration done.
8. An explicit decision on postseason and offseason behavior (a retrospective state, not silent staleness).
9. A short list of 15–20 named writers/podcasters recruited for a 30-day structured trial starting Opening Day.

### What evidence to collect in the first 30 days of the 2027 season
- Daily: external visitors, returning visitors (different-day), Team Board opens by team, What Changed opens.
- Weekly: identities active on ≥3 days; top returning teams; entry sources; share → landing conversion.
- Creator trial: citations/links per participant; qualitative "what did you use it for?" notes.
- Reliability: days with on-time publication (target: 30/30); staleness incidents; founder hours on ops versus product.
- Label validation: rolling "Unavailable pitched anyway" rate.
- Compare against K1–K8 on day 30 and day 60, and decide.

---

## 30. Final Assessment

**Is BaseballOS solving a real recurring problem?**
Yes, narrowly. Knowing which relievers are rested or taxed before tonight's game is a real daily need for engaged fans, writers, and broadcasters, as the number of competitors shows. "Understanding the bullpen's state" in a broader sense is a much weaker need than the documents assume.

**Is the problem important enough?**
Important enough for a small, durable niche (team-focused media and devoted fans), probably not for a mass audience. The largest existing demand for this exact question comes from fantasy and betting, which BaseballOS deliberately excludes. That can be the right call, but it caps the addressable audience, and the founder should accept that consciously.

**Is the current product differentiated?**
Partially. The core table is better-assembled than free alternatives but not unique. Day-over-day change, rotation-transfer context, full-pen coverage, and strictly descriptive, citable publication are differentiated in concept. In current execution, What Changed speaks in counts and Team State is too volatile to carry meaning.

**Does the underlying platform create a defensible advantage?**
Not a moat. Inputs are public and rebuildable. The advantage is operational: a correct, corrected, daily-published record with receipts. That becomes more valuable with each season accumulated, but only if someone uses it.

**Is current engineering effort translating into user value?**
Mostly no, recently. Backend code tripled and documentation nearly doubled in three months, while frontend change was modest, the newest hardened contract (Tonight v1) has no consumer, and demand has never been measured. The June audit named this pattern; it intensified.

**Is BaseballOS building durable assets or transient dashboards?**
Both. The appearance ledger, roster history, correction record, and immutable daily snapshots are durable. The public surfaces are largely transient dashboards with a label that turns over every ~2 days, plus thousands of frozen share pages few will revisit.

**What is the largest existential risk?**
Continuing to perfect a publication system for an audience that has not been shown to exist, until the product becomes dead content: correct, current most days, and unvisited. Beneath that risk sits a second: invisibility. The product cannot be found.

**What is the strongest reason the project could work?**
The market has an open lane: a free, trustworthy, strictly descriptive, per-team bullpen board that tells you *what changed since yesterday* in named arms, with a citable receipt. No one owns that position, and BaseballOS already has the data backbone to occupy it.

**What would need to be demonstrably true by Opening Day 2027?**
- A measured 2026 baseline and pre-committed kill criteria.
- An alerting pipeline.
- Indexable team pages.
- A mobile Team Board whose first screen is the answer.
- A named-arm What Changed.
- One outcome validation of the labels.
- A recruited creator trial ready to start.

None of these requires new infrastructure. All of them require the founder to shift from proving publications to proving usefulness.

**What would justify substantially reducing or ending investment?**
- Meeting K1–K3: adequate awareness without repeat visits; no team-board repeat destinations.
- Or K4 plus K6: the best-fit users reject it and competitors answer faster.
- Or K8 persisting: operations consume the founder.

If those conditions are met by June 2027, the rational move is to keep the pipeline as a low-cost portfolio asset and data record, and stop major product investment.

**Direct assessment:** BaseballOS is not yet a product with demonstrated users. It is a well-engineered data platform wrapped around a thin, partially differentiated answer. Its survival does not depend on more engineering; it depends on whether, within the next season, a small group of people can be shown to return to it because it answers the bullpen question faster and more trustworthily than what they use now. That is testable, cheaply, starting now.

---

### Appendix A — Key evidence locations

- Availability rules: `backend/services/availability.py:109-111, 205-255`
- Team State contract: `backend/team_operations/contracts.py:67-79`
- Public label mapping: `backend/services/pitcher_public_labels.py:245-262`
- Roles: `backend/services/pitcher_role.py`
- Rotation support pressure: `backend/services/rotation_support_pressure.py:43-71`
- Frontend grouping inconsistency: `frontend/src/adapters/operatingStateReadModel.js:13, 330, 351`; `frontend/src/components/methodology/Methodology.jsx:44`
- Traffic measurement: `backend/models/traffic_page_view.py`, `backend/services/traffic_reporting.py`, `frontend/src/utils/trafficMeasurement.js`
- Incident: `docs/incidents/2026-09-12-daily-publication.md`
- Prior audit: `docs/governance/BASEBALLOS_FULL_PROGRAM_AUDIT_2026_06.md`
- Tonight: `docs/audits/tonight-authority-hardening-tn-00.md`, `tonight-v1-read-model-tn-01.md`, `tonight-v1-serving-tn-02.md`; `frontend/src/utils/api.js:658`
- Boot: `backend/scripts/render_start.sh`
- Scheduling: `.github/workflows/baseballos-sync.yml:30-41`; `docs/current/SYNC_PIPELINE.md:73-77, 105-140`
- Accepted risk deadline: `.github/dependency-audit-accepted.json`
- Postseason exclusion: `docs/canonical/02_BULLPEN_INTELLIGENCE_STANDARD.md:269`; `backend/services/mlb_api.py:526-535`
- Production distribution history: `git log --author=Automation` (Snapshot-ID / Data-Through trailers)

### Appendix B — Reproducing the Team State churn measurement

For each `BaseballOS Automation` commit, read `frontend/public/team/*/index.html` at that commit, extract `Team State: <label>`, key by the `Data-Through` trailer, and compare consecutive dates team-by-team. 26 dates (2026-08-13 → 09-23), 750 transitions:

| From \ To | Fresh | Stretched | Vulnerable |
|---|---|---|---|
| Fresh | 42 | 59 | 19 |
| Stretched | 67 | 187 | 109 |
| Vulnerable | 19 | 118 | 130 |

Note: consecutive snapshots are not always consecutive calendar days, because of publication gaps, including the 09-09 → 09-22 gap.

### Appendix C — Competitor sources
- InsidethePen: https://insidethepen.com/bullpen-usage.html · https://insidethepen.com/bullpen-availability-today.html · https://insidethepen.com/bullpen-roster-moves.html · https://insidethepen.com/bullpen-rankings.html
- FanGraphs: https://www.fangraphs.com/roster-resource/closer-depth-chart · https://blogs.fangraphs.com/fangraphs-feature-focus-closer-depth-chart/ · https://www.fangraphs.com/roster-resource/transaction-tracker
- RotoWire: https://www.rotowire.com/baseball/bullpen-usage.php · https://www.rotowire.com/baseball/reliever-usage.php
- Razzball: https://razzball.com/bullpen-chart/ · https://razzball.com/autopen/
- FantraxHQ: https://fantraxhq.com/bullpen-usage-chart/
- ESPN: https://www.espn.com/fantasy/baseball/flb/story?page=REcloserorgchart
- Closer Monkey: https://closermonkey.com/
- DeepMetric: https://deepmetricanalytics.com/mlb/bullpen-tracker
- CLEATZ: https://cleatz.com/mlb-bullpen-fatigue/
- EVAnalytics: https://evanalytics.com/mlb/leaderboards/team-bullpen-rankings
- Covers: https://www.covers.com/sport/baseball/mlb/statistics/team-bullpenera/2026
