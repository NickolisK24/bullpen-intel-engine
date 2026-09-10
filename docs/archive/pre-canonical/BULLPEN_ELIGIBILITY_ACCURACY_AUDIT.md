# Bullpen Eligibility Accuracy Audit — Investigation Report

> **Type:** Investigation and review only. No code, branches, commits, PRs, or
> documentation changes were made; no fixes or implementation work are proposed.
> **Question:** Does BaseballOS's bullpen population accurately reflect real
> bullpen reality — i.e., *"Is BaseballOS actually showing the bullpen?"*
> **Trigger:** The Cincinnati Reds board surfaced apparent starters — Chase Burns,
> Nick Lodolo, Rhett Lowder, Chris Paddack — as bullpen options.
>
> **Method & honest limitation.** The **eligibility logic is read directly from the
> shipped code on `origin/dev` and is authoritative** — those findings are
> code-certain. I do **not** have access to the live production database or the
> live June-2026 MLB rosters/transactions, and my baseball-role knowledge predates
> the live data window. So **per-pitcher "this appeared/was missing" claims are
> reasoned inferences**, clearly flagged as such, while the **root-cause logic
> findings are certain.** Where I assert a player is a starter, that is
> pre-2026-cutoff role knowledge, not confirmation of their June-2026 usage.

---

## 1. Executive Summary

**The concern is valid, and the root cause is structural, singular, and
league-wide: BaseballOS has no authoritative starter/reliever (role/rotation)
signal. Bullpen membership is inferred almost entirely from recent innings-pitched
length, on top of a position field that is effectively always `"P"`.** That
inference is fragile precisely for the kinds of pitchers in the Reds example, and
the failure mode is systemic, not isolated to Cincinnati.

Two code-certain facts drive everything below:

1. **The `position` field is dead weight in production.** `Pitcher.position`
   defaults to `'P'` (`models/pitcher.py:16`) and is populated from MLB
   `primaryPosition.abbreviation` (`seed.py:88`), which for pitchers is the generic
   **`"P"`** — MLB does not encode SP vs. RP there. So in
   `evaluate_bullpen_eligibility`, the `pos == 'SP'` (starter-exclude) and
   `pos in {'RP','CL'}` (relief-include) branches **never fire**. **All
   discrimination therefore rests on IP-length usage heuristics.**
2. **The roster gate does not exclude starters.** `allows_default_board` returns
   true for both `ACTIVE` and `UNKNOWN` roster status (`roster_status.py:269-278`).
   Starters are legitimately on the active roster, so the only thing standing
   between a starter and the bullpen board is the usage heuristic.

The usage heuristic correctly excludes a *healthy, currently-rotating, well-logged*
starter (via the "last two outings ≥3 IP" rule). It **fails** — and lets starters
through — for exactly three populations: **(a) recently called-up rookie starters
with thin MLB samples (Burns, Lowder), (b) starters returning from the IL or with
an atypical short outing (plausibly Lodolo, Paddack), and (c) any starter whose
recent logs are sparse or partially synced.** A specific inclusion-biased rule —
`limited_relief_sample` — *actively includes* thin-sample pitchers as
bullpen-relevant, which is the wrong default for distinguishing a rookie starter
from a rookie reliever. The mirror-image error also exists: **multi-inning
relievers, long men, and swingmen who throw ≥3 IP in relief are mis-excluded as
"clear starters."**

**Severity: Trust Risk — and effectively Critical for the Bullpen Board and the new
Bullpen Stress surface specifically**, because both are *defined by* the bullpen
population. The fatigue/availability engines are sound; the **population feeding
them is contaminated at the top of the funnel**, so the error propagates into the
flagship board and the stress story computed from it. When a baseball-literate user
sees a team's rotation listed as bullpen options, the product's core claim — "this
is your bullpen tonight" — is visibly false.

**Isolated or systemic? Systemic.** The mechanism is league-wide; only the
*magnitude* varies by roster composition. An independent corroboration already
exists in this project's own history (see §4 / §10): the earlier *What Changed*
diagnosis found Yankees starters (Cole, Rodón, Schlittler) surfacing — a related
population-integrity failure on a different surface.

---

## 2. Cincinnati Reds Audit

**Named surfaced pitchers (all are starters by pre-2026 role knowledge):**

| Pitcher | Real role (pre-2026 knowledge) | Most likely reason it slipped through (logic-inferred) |
| --- | --- | --- |
| **Nick Lodolo** | Established LHP starter, top of rotation | Injury history; a recent **IL return or short outing** breaks the "last two ≥3 IP" exclusion, leaving a thin/low-`start_like` sample → caught by `limited_relief_sample` → eligible (low confidence). |
| **Chris Paddack** | Veteran RHP starter | Same pattern — a single short/return outing in the 21-day window, or a thin synced sample, evades `clear_starter` and trips the thin-sample inclusion. |
| **Chase Burns** | Rookie RHP starter (recent debut) | **Thin MLB sample** as a recent call-up; few logged outings, plausibly one ≤2 IP → `limited_relief_sample` (`start_like≤1, relief_like≥1, total≤3`) → **included**. |
| **Rhett Lowder** | Rookie RHP starter (recent debut) | Same recent-call-up thin-sample mechanism as Burns. |

**Why these four specifically are the visible canaries:** they are a cluster of
*young and/or recently-returned* starters — exactly the population where the
21-day, IP-length sample is smallest and least reliable, and where the
inclusion-biased `limited_relief_sample` rule does the most damage. An established
ace making four clean 6-IP starts in the window would be excluded; a rookie with
two MLB outings (one short) is included.

**Likely missing relievers (false negatives — archetype-level, not confirmed):**
- **Just-called-up relievers with zero logs in the window** → `STATUS_NO_USAGE` →
  excluded entirely.
- **Multi-inning / long relievers and swingmen** who recently threw ≥3 IP in relief
  → mis-classified `clear_starter` → excluded.
- **Relievers who haven't pitched in ~14–21 days** (e.g., a mop-up arm in a
  cold stretch) → dropped by the recency window.

**Reds verdict:** the board is plausibly showing **4+ rotation arms as bullpen
options while potentially omitting genuine relief depth** — a direct
misrepresentation of the bullpen on the flagship surface.

---

## 3. Arizona Diamondbacks Audit

**Status: logic-predicted exposure, not live-confirmed.** I cannot see Arizona's
June-2026 board. What the logic guarantees for *any* team with Arizona's archetype:

- **Predicted false positives:** any rotation starter who recently (a) returned
  from the IL, (b) had a rain/ejection/early-exit short start, or (c) was a recent
  call-up. Arizona has historically carried young, injury-variable starters, which
  is fertile ground for the thin-sample inclusion path.
- **Predicted false negatives:** their long/multi-inning relievers and swing
  pieces (a role Arizona uses) → excluded by the ≥3 IP "clear starter" rule.
- **What to check live:** for each name on the AZ board, read its
  `eligibility.status` + `eligibility.confidence`. Expect `bullpen_relevant` at
  **low** confidence with the `limited_relief_sample` reason on the
  mis-included starters.

---

## 4. New York Yankees Audit

**Status: strongest corroboration that the problem is real and systemic.** This
project has *already* observed Yankees starters leaking into a bullpen surface:
the earlier **What Changed anchor/eligibility diagnosis** found **Gerrit Cole,
Carlos Rodón, and Cam Schlittler** surfacing.

Two important clarifications so this is used honestly:
- That earlier leak was on the **What Changed** endpoint, which at the time
  **bypassed eligibility entirely** (a different, already-diagnosed defect). It is
  evidence that *starters reach users*, and that the Yankees' rotation names are
  the kind that surface — but it is **not** itself proof that the *board's*
  eligibility logic passed them.
- The **current** investigation is about surfaces that *do* run eligibility (the
  board) still admitting starters. The two failure modes share one root: **no
  authoritative role data.** One surface skipped the weak filter; the other has a
  filter too weak to catch thin-sample/returning starters.

**Predicted board exposure:** established aces (Cole, Rodón) should normally be
*excluded* by the "last two ≥3 IP" rule **when healthy and well-logged** — so on
the Yankees, the board is the *least* likely of the five teams to show top
starters, *unless* one is freshly off the IL or thinly logged (e.g., a returning
arm, or a rookie like Schlittler with a short sample). The Yankees case mainly
confirms the **mechanism and the stakes**, less so a high board false-positive
rate for healthy veterans.

---

## 5. Houston Astros Audit

**Status: logic-predicted exposure, not live-confirmed.**

- **Predicted false positives:** Houston's pattern risk is the **returning starter**
  (they routinely cycle starters through the IL) and any **opener/piggyback** usage,
  both of which produce sub-3-IP outings that defeat the starter-exclusion and trip
  thin-sample inclusion.
- **Predicted false negatives:** multi-inning relievers (a role Houston leans on)
  classified as starters and excluded.
- **What to check live:** any starter on the HOU board will carry low-confidence
  `bullpen_relevant`; any long reliever *missing* from the board will, if inspected,
  show `clear_starter` from ≥3 IP relief outings.

---

## 6. Chicago White Sox Audit

**Status: logic-predicted exposure, not live-confirmed.** The White Sox archetype
*maximizes* the bug's surface area:

- A rebuilding roster means **frequent call-ups, optionals, and roster churn** —
  the highest concentration of thin-sample pitchers, where `limited_relief_sample`
  inclusion and `STATUS_NO_USAGE` exclusion both fire most often.
- **Predicted false positives:** rookie/spot starters with 1–3 logged outings.
- **Predicted false negatives:** newly-recalled relievers with no in-window logs
  (excluded as `no_current_bullpen_relevance`), and swing arms used for length.
- Expect the **noisiest, least stable** bullpen population of the five teams here.

---

## 7. Eligibility Logic Review (Intended vs. Actual)

**Trace of the decision path** (board → `eligible_bullpen_pitcher_contexts` →
`evaluate_bullpen_eligibility`):

1. **Roster gate** — `classify_roster_status` → `allows_default_board`.
   *Intended:* drop IL/optioned/minors/DFA/non-roster.
   *Actual:* drops those, but **passes `ACTIVE` and `UNKNOWN`** — so a rostered
   starter passes, and an unknown-status pitcher passes "data-limited." No starter
   exclusion here, by design.
2. **Local-active gate** — only when roster status is **non-authoritative**
   (`respect_local_active = not is_authoritative`). When MLB roster status is
   stored, the local `active` flag is ignored.
3. **Position gate** — *Intended:* `SP` excluded, `RP/CL` included.
   *Actual:* **never fires** — production position is `'P'` (generic). `'P'` is in
   `PITCHING_POSITIONS`, so it neither excludes nor includes. **Dead branch.**
4. **Usage inference** (the only live discriminator) over the recent sample
   (regular-season-preferred, last 10, within a 21-day window):
   - Relief context (save/hold) → include (high conf).
   - Recent relief streak overriding old starts → include.
   - `clear_starter` if `pos=='SP'` *(dead)* **or last two outings ≥3 IP** or
     `start_like≥3 & ≥50%` or `start_like≥2 & avg≥3 IP` → exclude.
   - `strong_relief_pattern` → include.
   - **`limited_relief_sample`** (`start_like≤1 & relief_like≥1 & total≤3`) →
     **include (low conf)** ← the inclusion-biased thin-sample rule.
   - else `uncertain` → exclude.

**Role classifier (`pitcher_role.py`)** is **descriptive only** and **does not gate
eligibility** (`bullpen.py:859` attaches role for display after the decision). So
even a "long_multi_inning" or starter-like role read never removes a pitcher.

**Net intended behavior:** "explicit relief positions and relief-length usage are
included; clear starters and inactive records are excluded."
**Net actual behavior:** "position is ignored; *healthy, well-logged* starters are
excluded by IP length, but *thin-sample, returning, or short-outing* starters are
**included** at low confidence, and *long relievers* are **excluded**." The system
is conservative for the easy cases and wrong for the hard ones — and the hard cases
are exactly the visible ones.

---

## 8. False-Positive Analysis (starters/non-relievers included)

**Patterns, by how they reach `eligible: True`:**

1. **Thin-sample inclusion (dominant).** Recent call-ups and returning starters
   with ≤3 logged outings, ≤1 of start length, ≥1 short outing → `limited_relief_sample`.
   *Examples (inferred):* Burns, Lowder (rookies); plausibly Lodolo, Paddack
   (returning/short outing).
2. **Broken "last-two" exclusion.** A starter whose most recent outing was <3 IP
   (IL return, shelling, rain, opener, piggyback) fails `latest_two_start_like`; if
   `start_like` is also low, none of the other `clear_starter` clauses trip.
3. **Generic position.** Because `pos=='P'`, the cheapest correct signal (SP →
   exclude) is unavailable, so #1–#2 are never backstopped by a role label.
4. **Unknown roster status passes.** `UNKNOWN` → `allows_default_board` true, so a
   data-gap pitcher (incl. a starter) is admitted "data-limited."

**Common thread:** false positives are **thin-evidence pitchers** where the
heuristic lacks the data to assert "starter" and the design **defaults toward
inclusion**.

---

## 9. False-Negative Analysis (real relievers excluded)

**Patterns, by how they reach `eligible: False` or get filtered out:**

1. **Long/multi-inning relievers & swingmen** with recent ≥3 IP relief outings →
   `clear_starter` (`latest_two_start_like` or `start_like` clauses) → excluded.
   The heuristic cannot tell a 3-IP *relief* outing from a 3-IP *start*.
2. **Just-recalled relievers with no in-window logs** → `STATUS_NO_USAGE`
   (eligible:false) → excluded until they accumulate logs.
3. **Cold-stretch relievers** with no appearance in ~14–21 days → dropped by the
   recency window (`usage_logs_by_pitcher` / board `_recent_pitcher_ids_subquery`).
4. **Authoritative-status edge:** a reliever mis-stored as IL/optioned (stale roster
   sync) → excluded by `allows_default_board`.

**Common thread:** false negatives are **length-of-outing** and **recency/zero-log**
artifacts — the IP heuristic punishes relief length and demands recent logs.

---

## 10. Root-Cause Assessment

**Primary root cause (code-certain): absence of an authoritative starter/reliever
role signal.** The product never ingests rotation/role/depth-chart authority;
`position` is generically `'P'`; therefore role is *inferred* solely from recent
IP length. Inference from IP length is structurally unable to distinguish:
(a) a short-outing/returning/rookie **starter** from a **reliever**, and
(b) a **multi-inning reliever** from a **starter**.

**Contributing factors:**
- **Inclusion-biased thin-sample rule.** `limited_relief_sample` admits ≤3-outing
  pitchers as bullpen-relevant — the wrong default for ambiguous evidence on a
  trust-first surface.
- **Generic position field.** Kills the only cheap authoritative-ish discriminator.
- **`UNKNOWN` roster status is board-eligible.** Reasonable for uptime, but it means
  data gaps fail *open* (admit) rather than closed for bullpen membership.
- **Role classifier is non-gating.** A descriptive "looks like a starter" read is
  computed but never used to filter.
- **Possible data-quality amplifier (unconfirmed):** if game-log sync is partial or
  delayed for some pitchers, the IP sample is itself unreliable, compounding the
  logic weakness. I cannot confirm sync completeness without the live DB, but it is
  a plausible amplifier and should be checked.

**Is it data quality or logic quality?** **Primarily logic/データ-model quality (no
role authority + inclusion-biased inference), with data quality as a possible
amplifier.** It is *not* primarily an MLB-source problem: MLB simply doesn't encode
SP/RP in `primaryPosition`, and the system has no secondary role source to
compensate. So the gap is in **what BaseballOS ingests and how it infers**, not in
MLB being wrong.

**Single mechanism, many symptoms:** every per-team prediction above reduces to "IP
length is a weak proxy for role, and the proxy is the only thing we have."

---

## 11. Severity Assessment

**Rating: TRUST RISK — escalating to CRITICAL for the Bullpen Board and Bullpen
Stress surfaces specifically.**

Justification:
- **Visible and self-evident to the target user.** A baseball-literate fan
  immediately recognizes a team's rotation; seeing Lodolo/Paddack/Burns/Lowder as
  "bullpen options" reads as the product not knowing baseball — the most damaging
  possible impression for a *trust-first* tool.
- **It hits the flagship surface and propagates.** The Bullpen Board *is* the
  product, and the new **Bullpen Stress MVP is computed from this exact
  population.** A contaminated population means the stress story (counts, condition,
  "available depth") is computed over the wrong arms — the error flows downstream
  into the storytelling layer just built.
- **It is bidirectional.** Both false positives (starters in) and false negatives
  (relievers out) occur, so a user cannot even mentally correct by "ignore the
  obvious starters" — the *missing* arms are invisible.
- **Why not flatly "Critical" for the whole product:** the fatigue scoring,
  availability classification, freshness, and What-Changed logic are sound; a
  pitcher's *availability* is correct *given* he's on the board. The defect is
  **population membership**, not per-pitcher computation. But because membership is
  the board's entire premise, the practical user-facing severity on that surface is
  at the Critical boundary.

---

## 12. Founder Guidance (brutally honest)

**1. Is the bullpen population trustworthy today?**
**No — not on its own terms.** It is *directionally* right for healthy,
well-established, currently-rotating staffs, but it visibly mislabels the exact
pitchers a knowledgeable user will notice first (rookie/returning starters in;
long relievers out). For a product whose entire pitch is "trust," a board that
lists the rotation as the bullpen is a serious credibility problem.

**2. Is this isolated or systemic?**
**Systemic.** One root cause (no role authority + IP-length inference + generic
position) applies to all 30 teams. The Reds are a *visible* instance, not a special
one; rebuilding/young/injury-heavy rosters (White Sox, Arizona) will be worse, and
the project's own earlier Yankees observation independently corroborates that
starters reach users.

**3. What is the single biggest concern?**
**There is no authoritative starter/reliever signal — role is guessed from innings
pitched.** Everything else is a symptom of that one gap.

**4. What should the founder pay attention to?**
The **integrity of the population at the top of the funnel.** Every downstream
surface — board, What Changed, Bullpen Stress, future Daily Stress Report — inherits
this population. Watch specifically: thin-sample/recently-recalled pitchers, IL
returns, and multi-inning relievers. And confirm whether game-log sync is complete,
since partial logs amplify the inference error.

**5. Does this need immediate action before future roadmap work?**
**Yes.** This should be treated as a **blocking trust issue ahead of further
storytelling/stress expansion.** Building more surfaces (Daily Stress Report,
shareable cards) on top of a contaminated population *multiplies* the visible error
and bakes it into the most shareable artifacts — the worst place for it to live. The
population must be trustworthy before it is amplified.

**6. If action is needed, what category of issue is it?**
**Primarily a data-model / eligibility-logic issue — specifically the absence of
role (starter/reliever) authority — with a secondary roster-status fail-open
(`UNKNOWN` admitted) and a possible data-quality (log-completeness) amplifier.** It
is **not** primarily an MLB-source-data problem and **not** a fatigue/availability
engine problem. In one line: *the system needs a real role signal; it is currently
inferring role from innings pitched, and that inference is the defect.*

---

*Report only. No code, branches, commits, PRs, or documentation changes were made;
no fixes or implementation work are proposed. Logic findings are read directly from
`origin/dev`; per-pitcher and per-team specifics are reasoned inferences, explicitly
flagged, pending confirmation against the live database and current MLB rosters.*
