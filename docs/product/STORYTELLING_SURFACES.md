# Storytelling Surfaces — June 2026

> Companion to [PRODUCT_AUDIT_JUNE_2026.md](PRODUCT_AUDIT_JUNE_2026.md).
> Central question: **Does BaseballOS generate baseball stories that people
> repeat, discuss, and share?**

---

## 0. The Core Insight

**A workload number is not a story. "Hader has thrown 4 days in a row and his
arm is on empty" is a story.** BaseballOS has spent its life perfecting the
number and almost no time turning the number into the sentence. Yet the sentence
is what travels — on Twitter/X, in group chats, in broadcast booths, in podcast
cold-opens. **The engine is a story factory that currently ships raw ore.**

This is, simultaneously, the project's biggest weakness *and* its single largest
opportunity. The fatigue/availability engine produces exactly the kind of
hidden, counter-intuitive, argument-settling facts that baseball people love to
share — *if* the product would surface them as narratives instead of cells in a
table.

---

## 1. Does BaseballOS Currently Generate Stories? Surface-by-Surface

For each major surface: **Does this create a compelling baseball story?**

| Surface | Story? | Assessment |
| --- | --- | --- |
| **Tonight's Storylines (Dashboard)** | ⚠️ Partly | The *only* real story surface today. "Cubs appear to have the most constrained bullpen tonight" is a story seed — but it's thin (max 4, no depth, no faces, no numbers, no share button). It's a headline with no article. |
| **Tonight's Bullpen Board** | ⚠️ Latent | A board where the closer is red and two arms are green *is* a story ("their pen is cooked"). But it's presented as a status list, not a narrative, and the all-`Monitor` live degeneracy flattens the story to nothing. |
| **Pitcher Detail + "Why?"** | ✅ Yes (per-pitcher) | "Hader is Limited because he threw 28 pitches across back-to-back nights" is a genuine, explained micro-story. The best story surface in the app — but it's one pitcher at a time and not shareable. |
| **Bullpen Comparison** | ⚠️ Latent | Comparison is *inherently* a story ("X's pen is gassed, Y's is rested before this series") but presented as a side-by-side data layout, not a narrative or a matchup angle. |
| **Pitcher Role / Usage** | ⚠️ Latent | "Who's actually pitching high-leverage for this team" is a discussion-starter, but it's buried as descriptive metadata. |
| **All Pitchers Table** | ❌ No | A filterable table. A tool, not a story. Raw engine output. |
| **Data & Trust console** | ❌ No (anti-story) | Freshness, confidence, governance metadata. Important for credibility, fatal for narrative. Technical-metadata overload. |
| **Recommendation V1/V2 panels** | ❌ No (anti-story) | A recommendation engine that shows no recommendation is the *opposite* of a story — it's an anti-climax with a governance footnote. |
| **Methodology** | ❌ No (by design) | Reference, not narrative. Correctly so. |
| **Observations (V5)** | ⚠️ Latent (sample only) | *Architecturally the future story engine* — it's literally built to emit descriptive observations — but it runs on sample data and is buried on the trust page in governance framing. |
| **Prospects** | ❌ No | Sample data; off-mission. |

**Verdict:** Of ~11 surfaces, **one** weakly generates stories, **five** *latently*
contain stories the product fails to surface, and **four** actively suppress
story with technical/governance overload. The story-generating potential is
enormous and almost entirely unrealized.

### What's pulling against story today
- **Raw engine outputs** (All-Pitchers table) presented as the analyst path.
- **Technical-metadata overload** (Data & Trust, confidence/freshness panels).
- **Governance-heavy workflows** (V2 panel, `ranking_applied === false`
  vocabulary, certification framing) — these are the loudest anti-story surfaces
  and they currently occupy prime real estate.

---

## 2. The Story Categories BaseballOS Can Own

The engine already computes the inputs for every one of these. They are listed
roughly in order of shareability.

1. **Bullpen Stress** — "The Phillies' pen is running on fumes: 4 of 7 arms
   Limited or worse, third straight high-stress night." The flagship story type.
   No mainstream site tells it. *This is the category to own.*
2. **Workload Trends** — "Edwin Díaz has thrown on 6 of the last 8 days — his
   heaviest stretch of the season." Time-series fatigue as narrative.
3. **Bullpen Recovery** — "Atlanta's pen is fully rested for the first time in two
   weeks heading into the Mets series." The mirror image of stress — equally
   shareable, more positive.
4. **Usage Patterns** — "This manager has used his closer in the 8th four times
   this week." Behavioral stories about how arms are deployed.
5. **Team Comparisons / Matchup Angles** — "Heading into this series, the Dodgers'
   pen is rested and the Padres' is gassed." Pre-game narrative gold for media.
6. **Leverage / Constraint Concerns** — "If this game goes extras, the Mets have
   exactly one available high-leverage arm." Tension stories tied to tonight.

Each maps directly to an engine output that already exists (fatigue trend,
availability distribution, role classification, bullpen health, comparison). The
gap is purely presentational.

---

## 3. Recommended New Storytelling Surfaces

Designed for **shareability, discussion, creator usefulness, and media
usefulness** — the four lenses the audit prioritizes.

### S1 — The Daily Bullpen Stress Card *(highest priority)*
A single, auto-generated, screenshot-ready image per team per day. Team mark,
"Bullpen Stress: HIGH (3rd straight day)," a 5-arm availability strip with faces/
colors, one plain-language line ("closer unavailable, 2 fresh arms left"), and a
date + source watermark.
- **Shareability:** ★★★★★ — built to be screenshotted into a tweet.
- **Creator/media use:** ★★★★★ — a beat writer or content creator drops it into a
  pre-game post verbatim.
- **Why:** This is the atomic unit of the entire growth strategy. One artifact
  that travels does more for adoption than ten internal panels.

### S2 — "Tonight Around the League" Story Feed
The Dashboard storylines, deepened into a real feed: 8–12 opinionated,
numbers-backed bullpen storylines refreshed daily, each with a face, a number,
and a share button. "Most cooked pen," "most rested pen," "arm to watch,"
"manager riding his closer hard."
- **Shareability:** ★★★★☆ · **Media use:** ★★★★★ (a daily citation source).
- **Why:** Gives a reason to look even when your team isn't playing; becomes the
  "standings page" of bullpen workload.

### S3 — Workload Trend Story (per pitcher)
Turn the existing fatigue-trend chart into a narrated mini-story: "Díaz: 6 of
last 8 days · heaviest stretch of 2026 · now Limited," with a clean shareable
chart card.
- **Shareability:** ★★★★☆ · **Discussion:** ★★★★★ (settles "is he being
  overused?" arguments).
- **Why:** Converts the per-pitcher detail (already the best surface) into
  something that leaves the app.

### S4 — Series Matchup Bullpen Preview
Before a series, auto-generate a two-team bullpen comparison framed as a story:
"Rested vs. Gassed: Dodgers' pen enters this series fresh; Padres' pen is on its
third hard week."
- **Media use:** ★★★★★ — exactly the angle a broadcast or preview article wants.
- **Why:** Reframes the underexploited Compare view as recurring, timely content.

### S5 — Weekly "Most Overworked Arms" Leaderboard
A weekly, shareable list of the league's most-stressed bullpens and arms.
- **Shareability:** ★★★★☆ · **Creator use:** ★★★★★ (a weekly content template).
- **Why:** Establishes the weekly cadence (see
  [USER_HABIT_LOOP_ANALYSIS.md](USER_HABIT_LOOP_ANALYSIS.md)) and a recurring
  media hook.

### S6 — Seasonal Bullpen Journal / "Most Abused Pen of 2026"
Season-long workload narratives and leaderboards.
- **Media use:** ★★★★★ (the kind of stat a national writer cites in October).
- **Why:** Cements seasonal value and long-term authority on the topic.

---

## 4. Design Principles for Story Surfaces (Without Breaking Trust)

The product's governance discipline is a *strength* and storytelling must not
sacrifice it. Stories can be vivid **and** honest:

1. **Describe, don't predict.** "Threw 4 of 5 days, now Limited" is descriptive
   and shareable. "Will blow the save tonight" is prediction — forbidden, and
   rightly so. Every recommended surface stays descriptive.
2. **Faces and numbers, not metadata.** A story needs a pitcher, a number, and a
   plain sentence — not a confidence enum or a `ranking_applied` flag. Keep
   governance in the API; keep it off the card.
3. **The freshness/source watermark IS a trust feature.** Putting "BaseballOS ·
   data through Jun 7" on every shareable card turns honesty into branding and
   makes each share a marketing impression.
4. **Opinionated framing, defensible substance.** "Cooked," "gassed," "rested"
   are vivid and *accurate* descriptions of workload — they are not predictions.
   Lean into voice; the data backs it.

---

## 5. Bottom Line

BaseballOS sits on the best raw material for baseball stories that no mainstream
site is mining — and ships it as a spreadsheet. **The single highest-leverage
product move available is to put a "share this story" surface on top of the
engine that already exists.** Build the Daily Bullpen Stress Card first; it is
the artifact that turns a private tool into a public habit and an acquisition
engine in one stroke.
