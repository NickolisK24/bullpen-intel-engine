# Role Authority & Bullpen Population Truth Source — Investigation Report

> **Type:** Investigation and review only. No code, branches, commits, PRs, or
> documentation changes were made; no fixes or implementation plans are proposed.
> **Core question:** *What should BaseballOS use as the authoritative signal for
> "this pitcher is a bullpen arm" vs. "this pitcher is a starter"?*
> **Builds on:** the Bullpen Eligibility Accuracy Audit, which found role is
> inferred from innings-pitched heuristics with no authoritative starter/reliever
> signal.
>
> **Method & honest limitation.** The current role logic and data model are read
> directly from `origin/dev` and are **code-certain**. Claims about what the MLB
> Stats API exposes are from working knowledge of that API and are **verifiable
> against the live payload** — I flag confidence where it matters. No live DB or
> third-party API was queried.

---

## 1. Executive Summary

**The reframed question has a hopeful answer: an authoritative role signal *does*
exist, it is *free and official*, and part of it is *already flowing through
BaseballOS's own sync pipeline unused.* The defect is not missing authority — it
is that BaseballOS infers role from a lossy proxy (innings-pitched length) while
the authoritative bit sits one field away.**

The single most important finding of this investigation:

> **MLB's pitching gameLog `stat` object includes `gamesStarted` (0/1 per
> appearance). BaseballOS already parses that exact object — it reads
> `stat.get('saves')` and `stat.get('holds')` from it (`sync.py:135,139`) — but it
> never reads or stores `gamesStarted`. The `GameLog` model has no start flag at
> all. So the authoritative "did this pitcher start this game?" signal is present
> in data already ingested, and discarded.**

That single bit, plus its season aggregate (**GS / G**, games-started over
games-played — the canonical industry role classifier) and MLB's published
**probable-pitcher** designation, resolves the large majority of the errors the
prior audit found: long relievers mislabeled as starters, rehab/returning starters
mislabeled as relievers, and most rookies (via probables). What remains after that
is a genuinely hard tail — **openers, swingmen, and brand-new call-ups with no
start history** — that *no* signal fully resolves and that any honest system should
mark as ambiguous rather than guess.

**Bottom line:** BaseballOS does not need to buy a feed or scrape a competitor to
know who's in the bullpen. It needs to **use the authoritative start signal MLB
already gives it** instead of guessing from innings. The current approach is a
**foundational** problem (it is the substrate of every bullpen surface) but a
**tractable** one (the authority is largely already in hand). A pure
innings-heuristic approach is **not viable long-term**; the right category is a
**confidence-based hybrid role authority** with an explicit ambiguous/override
tail.

---

## 2. Current BaseballOS Role Determination Review

Tracing every role-relevant input in the shipped system:

| System | What it does | Authoritative? | Key limitation |
| --- | --- | --- | --- |
| **`position` field** | Stored role/position; default `'P'`, set from MLB `primaryPosition.abbreviation` | **No** | MLB returns generic `"P"` for pitchers; `SP`/`RP` branches in eligibility **never fire** in production. Dead signal. |
| **`bullpen_eligibility`** | Decides board membership | **No** | Once position is dead, this is **100% innings-length usage inference** (`start_like ≥3 IP`, `relief_like ≤2 IP`) plus save/hold context. |
| **`pitcher_role` (usage role)** | Describes role (late/setup/middle/long/low) from recent usage | **No** | Descriptive only; **does not gate** eligibility; also usage-derived. |
| **`roster_status`** | Active / IL / optioned / minors authority from MLB roster | **Yes (for activity)** | Authoritative for *availability/activity*, **not for SP/RP**. Passes `ACTIVE` and `UNKNOWN` to the board. |
| **`save` / `hold` / `save_situation`** | Captured per appearance | **Yes (relief-positive)** | Confirms "*is a reliever*" when present, but absence does not prove starter (middle relievers rarely get saves/holds). |
| **`gamesStarted`** | The authoritative start bit | **Yes** | **Not captured.** Absent from `GameLog`; not read by sync though it's in the parsed payload. |

**Inputs that exist today:** innings pitched per outing, pitches, saves/holds/
save-situation, win/loss, leverage, roster-activity status, recent appearance
dates. **A rich workload picture — but no start signal.**

**Inputs that are missing:** the per-appearance **start flag** (`gamesStarted`),
the season **GS/G** ratio, and any **probable-pitcher** (forward-looking start)
designation.

**Assumptions currently baked in:** (1) that innings-per-outing reliably proxies
role (it does not for long relievers, openers, rehab, rookies); (2) that absence of
an `SP` position label means "not definitely a starter" (it means nothing, because
the label is always `P`); (3) that a thin/ambiguous sample should **default toward
bullpen inclusion** (`limited_relief_sample`) — the opposite of conservative on a
trust-first surface.

**Net:** the system can *confirm* a reliever (save/hold) but must *guess* a starter
(innings length). The asymmetry is the whole problem.

---

## 3. MLB Authority Review

What MLB Stats API does and does not expose for role (verifiable against the live
payload):

**Exists and is authoritative / authoritative-derivable:**
- **`gamesStarted` per appearance** — in the pitching gameLog `stat` object
  (alongside the `saves`/`holds` BaseballOS already reads). The cleanest
  per-game truth: MLB credits the start.
- **Season `gamesStarted` / `gamesPlayed`** — the **GS/G ratio**, the canonical,
  league-standard role classifier (≈1.0 = pure starter, ≈0.0 = pure reliever,
  middle = swing). Free, official, stable.
- **`gamesFinished`, `saves`, `holds`, `saveOpportunities`** — relief-positive
  confirmations (BaseballOS captures saves/holds already).
- **Probable pitchers** — via the schedule endpoint's `probablePitcher` hydration:
  MLB-published "starting this game" designations. The authoritative
  *forward-looking* start signal, and the best resolver for **rookies/call-ups with
  no GS history**.
- **Boxscore / live feed** — identifies the starting pitcher per game directly.

**Does NOT exist (cleanly) in MLB data:**
- A direct **SP/RP label** on the player record — `primaryPosition` is generic
  `"P"`. (This is the gap the prior audit correctly flagged.)
- A reliable, structured **depth-chart "rotation vs. bullpen" membership** object.
  A `rosterType=depthChart` view exists but is inconsistent for pitcher role and is
  not trustworthy SP/RP authority.
- A **transactions** role tag — `/transactions` reports moves (recalled, optioned,
  IL) but never "added as a reliever."

**What can be trusted:** `gamesStarted` (per-game and season GS/G) and
probable-pitcher designations — these are official and stable.
**What cannot:** the generic position label and any inferred depth-chart role.

**Key correction to the prior framing:** "MLB has no role signal" is *half* true —
MLB has **no role *label***, but it has an authoritative role *derivation*
(`gamesStarted` / probables) that the industry universally relies on. BaseballOS is
not blocked by MLB; it is under-using MLB.

---

## 4. Alternative Authority Review

| Source | Strengths | Weaknesses | Maintenance | Trust | Sustainability |
| --- | --- | --- | --- | --- | --- |
| **MLB Stats API (`gamesStarted`/GS-G/probables)** | Official, free, already partly ingested, real-time | No clean SP/RP label (derive from GS) | Low (already integrated) | **High** | **High** |
| **FanGraphs (RosterResource)** | Explicit SP/RP + rotation/bullpen roles, expert-maintained | No official API; scraping vs. ToS; structure can change | Med–High | High (content) | **Low–Med** (ToS/fragility) |
| **Baseball Reference** | Role/usage context, deep | Sports-Reference ToS discourages scraping | Med–High | High | **Low–Med** |
| **Retrosheet** | Authoritative historical event data | Historical, not current-roster role; lag | Med | High (history) | Med (not for "today") |
| **Statcast / Baseball Savant** | Pitch-level truth | No role label; role still derived from GS/context | Med | High (data) | Med |
| **Commercial depth charts (Rotowire, etc.)** | Explicit roles, human-curated | Licensed/paid; dependency | Low–Med | High | **Med** (cost/lock-in) |
| **Roster transaction history** | Move signals | No role tag | Med | Med | Med |
| **Appearance history (GS/G derived)** | Free, official, already flowing | Lags fast role changes; opener/swing edge cases | Low | **High** | **High** |
| **Hybrid (authority + usage + override)** | Best accuracy + honest on tail | More moving parts conceptually | Med | **Highest** | **High** |

**Reading:** the **sustainable, trustworthy, low-maintenance** authority is the one
BaseballOS already touches — **MLB `gamesStarted`/GS-G/probables**. Third-party
role labels (FanGraphs/BR) are *higher-resolution* but carry ToS, fragility, and
maintenance risk that conflict with a trust-first, durable product. They are at
best a *supplement* for the hard tail, never the foundation.

---

## 5. Usage Heuristic Review

Where role-from-usage works and where it fails:

| Usage signal | Works for | Fails for |
| --- | --- | --- |
| **GS / G ratio** (authoritative-derived) | Nearly everyone with a modest sample; the canonical classifier | Brand-new call-ups (no history); openers (credited a start); swingmen (genuinely ~0.5) |
| **Innings per outing** (current BaseballOS) | Clean, healthy, currently-rotating starters; pure 1-inning relievers | **Long/multi-inning relievers (≥3 IP → false "starter")**, **openers (1–2 IP → false "reliever")**, **rehab/short starts**, **thin rookie samples** |
| **Saves / holds** (captured) | Confirming a *reliever* | Silent for middle relievers; never indicates a starter |
| **Appearance cadence / rest** | Weak corroboration (starters ~every 5 days) | Noisy; disrupted by IL, doubleheaders, bullpen games |
| **Opener detection** | — | Pure IP can't; even GS mislabels (opener = credited start but is a reliever by role) |
| **Bulk/long relief** | — | IP labels them starters; GS=0 correctly labels them relievers |

**The core failure example:** a long reliever throws 3.1 IP in relief. BaseballOS's
`clear_starter` rule (`latest_two_start_like` / `start_like` on ≥3 IP) **excludes
him as a starter** — a false negative. His `gamesStarted` for that game is **0** —
the authoritative bit gets it right. Conversely, a rehabbing ace throws 2 IP in his
first start back: IP says "reliever" (false positive into the pen); his
`gamesStarted` is **1** — again the authoritative bit is correct and the IP proxy is
wrong. **Every marquee failure in the prior audit is a case where `gamesStarted`
disagrees with innings length, and `gamesStarted` is right.**

**Where usage still helps:** *recency-weighted* GS captures genuine role
**conversions** (a starter moved to the pen) faster than a flat season ratio, and
saves/holds confirm relief. So usage is the right *secondary/smoothing* layer — not
the primary truth.

---

## 6. Special-Case Analysis

Ranked from "authority resolves it" to "nothing fully resolves it":

| Case | Hardness | Resolver |
| --- | --- | --- |
| **Long / multi-inning relievers** | Easy (currently broken) | `gamesStarted = 0` fixes the current false negative outright. |
| **Rehab / injured starters returning** | Easy–Med | Season GS history + probables say "starter" despite a short outing. |
| **Converted starter→reliever / reliever→starter** | Med | Recency-weighted GS; saves/holds; lags only briefly. |
| **Rookie starters / recent call-ups** | Med | **Probable-pitcher** designation resolves "starting tonight" with no GS history — exactly where the IP heuristic fails worst. |
| **Bullpen games** | Med–Hard | The nominal opener gets `gamesStarted = 1`; the bulk arm gets 0 — mostly correct, but role-misleading for the opener. |
| **Openers** | **Hard** | MLB credits the opener a *start* (GS=1) though he is a reliever by role. **No signal cleanly resolves**; needs an explicit "opener/ambiguous" treatment. |
| **Swingmen** | **Hardest** | Genuinely dual-role (GS/G ≈ 0.3–0.7); any binary SP/RP label is wrong. Needs a *swing/ambiguous* state, not a guess. |

**The honest tail:** openers, swingmen, and zero-history call-ups are *irreducibly*
ambiguous. The correct behavior is to **mark them ambiguous with low confidence**
(and allow correction), not to force a binary and be confidently wrong. The current
system has no ambiguous state for role — it forces inclusion/exclusion.

---

## 7. Trust Implications

**If BaseballOS keeps the current innings heuristic:**
- **How often:** errors are *structural and recurring*, not rare. Every team
  carries long relievers, rehabbing starters, rookies, and swing arms — the exact
  failure set. Expect visible errors on most teams at most times, concentrated on
  young/injury-heavy/rebuilding rosters.
- **Who notices:** **precisely the target audience** — baseball-literate fans,
  analysts, and creators who recognize a rotation on sight. The people most likely
  to adopt and evangelize are the people most likely to catch the error.
- **How damaging:** for a *trust-first* product, listing the rotation as the
  bullpen is maximally damaging — it reads as "this tool doesn't know baseball,"
  which discredits the genuinely-good fatigue/availability work underneath.

**If BaseballOS uses authoritative GS/probables (+ usage smoothing):**
- Errors collapse to the **defensible tail** (openers/swingmen/no-history rookies),
  which even experts find ambiguous and which a confidence flag makes honest.

**Severity of the *status quo*: Trust Risk, escalating to Critical** for every
population-defined surface (Board, Bullpen Stress, What Changed, Follow My Team).

---

## 8. Root Problem Assessment

**Root problem (code-certain): BaseballOS determines role from a lossy proxy
(innings-pitched length) while the authoritative signal (`gamesStarted`
per-appearance, season GS/G, probable-pitcher) exists in MLB data — and is partly
already parsed by the sync pipeline — and is unused.**

It decomposes into:
1. **A data-capture gap (primary):** `gamesStarted` is in the gameLog `stat`
   payload BaseballOS reads, but the `GameLog` model has no start field and sync
   never stores it. The truth is discarded at ingestion.
2. **A signal-choice gap:** with the start bit absent, eligibility leans on IP
   length, which cannot distinguish relief length from start length.
3. **A missing forward signal:** probable-pitcher data (the resolver for
   no-history rookies) is not ingested.
4. **A design bias:** ambiguous/thin evidence defaults to *inclusion*
   (`limited_relief_sample`) and there is **no "ambiguous role" state** — so the
   irreducible tail is forced into a confident wrong answer.

**This is not an MLB-data-availability problem and not an engine problem.** Fatigue
and availability are sound. The gap is in **what BaseballOS ingests and which signal
it trusts** for population membership.

---

## 9. Conceptual Solution Categories (conceptual only)

Naming the *category* of solution, not a design:

1. **Authoritative-derived role signal** — treat MLB `gamesStarted` (per-appearance
   + season GS/G) and probable-pitcher as the primary truth for SP vs. RP. *The
   foundation.*
2. **Hybrid authority + usage** — authoritative GS/probables as primary, with
   recency-weighted usage and saves/holds as a smoothing/confirmation layer to catch
   role *transitions* quickly. *The accuracy layer.*
3. **Confidence-based role model** — explicit role **confidence** and an
   **ambiguous / swing / opener** state, so the irreducible tail is surfaced
   honestly instead of guessed. *The trust layer.*
4. **Manual override layer** — a small curated correction path for the genuinely
   ambiguous or fast-breaking cases (opener tonight, just-announced role change).
   *The escape hatch.*

The shape these point to (conceptually): **a confidence-based hybrid role authority
— MLB-derived primary, usage secondary, with an explicit ambiguous state and a thin
override path.** Notably, a *pure external feed* (FanGraphs/BR/commercial) is **not**
the indicated foundation — it adds fragility/cost for a problem MLB's own data
largely solves; it belongs, if anywhere, only as a tail supplement.

---

## 10. Severity Assessment

**Foundational, not surface-level — but tractable.**

- **Foundational:** role/population membership is the substrate beneath the Board,
  Bullpen Stress, What Changed, and Follow My Team. Every current and planned
  bullpen surface inherits it. An error here is an error everywhere, including in the
  most shareable artifacts on the roadmap.
- **Tractable (the honest counterweight):** the authority largely **already exists
  in hand** (`gamesStarted` in the ingested payload; GS/G and probables one endpoint
  away). This is not an unsolvable data desert — it is a substrate that is wrong for
  a *correctable* reason.
- **Net severity of the status quo: Critical for population-defined surfaces**,
  because the defect is visible to the core audience and propagates into the
  storytelling layer being built now.

---

## 11. Founder Guidance (brutally honest)

**1. Is the current bullpen population trustworthy?**
**No.** It is directionally right for clean, healthy, established staffs and
*structurally wrong* for the cases a knowledgeable user notices first — long
relievers (wrongly excluded), and rehabbing/rookie/short-outing starters (wrongly
included). On a trust-first product, that is a serious, visible credibility hole.

**2. What is the biggest flaw?**
**Role is guessed from innings-pitched length when the authoritative answer
(`gamesStarted`) is already flowing through the sync pipeline unused.** The product
discards the truth at ingestion and then infers a worse version of it.

**3. Is there an authoritative source available?**
**Yes — and it's free and official.** MLB's `gamesStarted` (per appearance + season
GS/G) and **probable-pitcher** designations. There is no clean SP/RP *label* in MLB
data, but the authoritative *derivation* exists, is industry-standard, and is partly
already ingested. No scraping or paid feed is required for the foundation.

**4. Is a pure heuristic approach viable long-term?**
**No.** Innings-length heuristics will *always* misfire on long relievers, openers,
rehab returns, rookies, and swingmen — these are permanent roster realities, not
edge cases. (Note: a GS-*derived* classifier is still a "derivation," but from an
authoritative input rather than a proxy — that distinction is the whole game.)

**5. What category of solution appears most promising?**
**A confidence-based hybrid role authority:** MLB-derived start signal as primary,
recency-weighted usage + saves/holds as secondary, an explicit **ambiguous/swing/
opener** state, and a thin manual override for the irreducible tail. *Not* a pure
heuristic; *not* a pure external feed.

**6. Does this block future roadmap work?**
**Yes — it should gate further amplification of the bullpen population.** Bullpen
Stress, Daily Stress Reports, and shareable cards all multiply this population's
visibility. Baking a known, visible population error into the most shareable
surfaces is the worst possible place for it. Stabilize the truth source before
amplifying it.

**7. Is this a foundational issue or a surface-level issue?**
**Foundational** — it defines *who is in the bullpen*, beneath every surface — **but
tractable**, because the authoritative signal is largely already available and
partly already ingested. It is the kind of foundational issue that is cheap to be
right about and expensive to keep being wrong about.

---

*Report only. No code, branches, commits, PRs, or documentation changes were made;
no fixes or implementation plans are proposed. Current-system findings are read from
`origin/dev`; MLB-API capability claims are verifiable against the live payload and
are flagged accordingly.*
