# User Habit Loop Analysis — June 2026

> Companion to [PRODUCT_AUDIT_JUNE_2026.md](PRODUCT_AUDIT_JUNE_2026.md).
> Central question: **Why would a user return tomorrow?**

---

## 0. The Blunt Answer

**Today, almost nothing brings a user back tomorrow.**

BaseballOS is a *reference tool*: you open it when you have a specific question
("can the Phillies use their closer tonight?"), you get an answer, and you
leave. Reference tools are valuable, but they don't form habits — you visit a
dictionary when you need a word, not every morning. The product has no saved
state, no personalization, no notification, no streak, no "what changed," and no
shareable artifact. The only thing that changes between visits is the underlying
data, and the product does nothing to *tell you it changed.*

A habit loop has four parts: **trigger → action → reward → investment.**
BaseballOS currently has a weak action and a weak reward, and is missing the
trigger and the investment entirely.

| Loop element | BaseballOS today | Status |
| --- | --- | --- |
| **Trigger** (what pulls you back) | None — no notification, email, or "your team" memory | ❌ Missing |
| **Action** (what you do) | Browse the board / look up a pitcher | ⚠️ Weak (manual) |
| **Reward** (what you get) | Workload data, an availability status | ⚠️ Real but flat (all-`Monitor` risk) |
| **Investment** (what makes it *yours*) | None — nothing is saved or personalized | ❌ Missing |

Fixing the trigger and the investment is the cheapest, highest-impact work
available to the project, because the action and reward already half-exist.

---

## 1. Current Reasons to Return (Honestly, Few)

1. **A live game tonight you care about.** If your team is playing extra innings,
   "who's left in the pen?" is a real recurring question. *This is the strongest
   existing pull* — but the product doesn't know which team is "yours," so the
   user does the work every time.
2. **You're an analyst tracking workload over a series.** "Has Hader thrown three
   straight days?" is a genuine repeat query. But the All-Pitchers table makes
   you reconstruct this manually each visit; the product remembers nothing.
3. **You're checking whether the data updated.** Almost no one does this for fun.

That's it. None of these are *automatic*. All require the user to remember
BaseballOS exists and to re-do their setup each visit. **A habit you have to
manually re-initiate every day is not a habit.**

---

## 2. Potential Future Reasons to Return (The Roadmap of Retention)

Ranked by how strongly they pull a user back:

1. **"Your team's bullpen changed overnight."** A notification or email: *"PHI:
   closer now Limited (28 pitches last night), 2 fresh arms for tonight."* This is
   the single most powerful retention mechanism available and the engine already
   computes everything needed.
2. **A daily storyline you don't want to miss.** "Tonight's bullpen stress
   leaders" / "most rested pens" as a daily-refreshing, opinionated feed — the
   baseball equivalent of checking standings.
3. **"What changed since yesterday" deltas.** Workload moves every night.
   Surfacing the *change* (not just the state) gives a fresh answer every single
   day — the core mechanic of a daily check-in.
4. **A streak / collection mechanic for engaged fans.** "You've checked your pen
   12 days straight"; seasonal workload journals per team.
5. **Shareable artifacts that pull you back to make more.** Once a user shares a
   bullpen-stress card and gets replies, they return to make the next one.
6. **Fantasy / DFS utility.** "Is my closer rested enough to get the save
   tonight?" is a daily, money-adjacent question for millions of fantasy players.

---

## 3. The Missing Habit Loops

Three loops are absent and each is buildable on the existing engine:

### Loop A — The "My Team" Loop (personalization → daily check-in)
*Pick your team once → the app opens to your bullpen forever → you check it like
you check the score.* **Missing entirely.** This is the foundational retention
loop and the cheapest to build: it's local state + a default route, no new
engine. Without it, every visit starts from zero and the product can never feel
like *yours*.

### Loop B — The "Did It Change?" Loop (delta → trigger → return)
*The app knows your team's bullpen state yesterday → computes the delta → tells
you what moved.* **Missing.** This converts a static reference into a living
feed. The data exists in the fatigue/availability history; only the comparison
and surfacing are missing.

### Loop C — The "Show a Friend" Loop (artifact → share → acquisition → return)
*You see a striking bullpen-stress fact → you export a clean card → a friend
sees it → they come check their team → they share theirs.* **Missing.** This is
both the growth loop *and* a retention loop (sharing pulls the sharer back). See
[STORYTELLING_SURFACES.md](STORYTELLING_SURFACES.md).

---

## 4. Value by Time Horizon

A durable product must deliver value on **daily**, **weekly**, and **seasonal**
cadences. Here is where BaseballOS stands on each, and where it could go.

### Daily Value
- **Today:** "Who can my team use tonight?" — real but manual, and undermined
  when the live engine classifies everyone as `Monitor`.
- **Potential:** Personalized morning bullpen report; overnight deltas; tonight's
  stress storylines; fantasy "is my closer rested?" check. **This is the richest
  untapped vein** because bullpen state genuinely changes every night.

### Weekly Value
- **Today:** Implicit only — an analyst can manually track a pitcher's week in the
  All-Pitchers table.
- **Potential:** "Most-overworked arms of the week," "pens trending toward a
  wall," workload-trend charts, a weekly team bullpen report. Weekly cadence is
  the natural home for *trend* storytelling and for creator/media content.

### Seasonal Value
- **Today:** None surfaced. The data spans seasons but the product never tells a
  season-long story.
- **Potential:** "Most-abused bullpen of 2026," per-pitcher seasonal workload
  journals, "this pen is on pace for a historic number of high-stress
  appearances." Seasonal value is what makes a fan adopt the product as *their*
  baseball home, and what gives media a recurring citation.

**The pattern:** the engine already holds daily, weekly, and seasonal signal. The
product surfaces only a sliver of the daily layer and none of the weekly or
seasonal layers. **Time-horizon storytelling is the largest unclaimed value in
the entire codebase.**

---

## 5. Recommendations, Ranked by Expected Impact

> Impact = effect on daily-active return. Effort = relative build cost on the
> existing engine. All are presentation/memory layers — none require new engines.

| # | Recommendation | Expected impact | Effort | Why |
| --- | --- | --- | --- | --- |
| 1 | **"Follow My Team" — pick once, app opens to your pen** | ★★★★★ | Low | The cheapest retention mechanism that exists; makes the product *yours* and removes per-visit setup. Foundational for every other loop. |
| 2 | **Fix the all-`Monitor` live signal so the board discriminates** | ★★★★★ | Med | A reward that's always the same color is no reward. Without discrimination, no other loop matters — there's nothing to come back *to*. |
| 3 | **Daily "what changed overnight" deltas for your team** | ★★★★☆ | Med | Converts reference tool → daily feed. Guarantees a different answer every day. |
| 4 | **Email / push: "your bullpen changed" digest** | ★★★★☆ | Med | The trigger the loop is missing. Brings users back without them remembering to visit. |
| 5 | **Shareable daily bullpen-stress card** | ★★★★☆ | Med | Doubles as the growth loop; sharing pulls the sharer back tomorrow. |
| 6 | **Tonight's storyline feed (deepened, opinionated)** | ★★★☆☆ | Low–Med | A daily-refreshing reason to look even when your team isn't playing. |
| 7 | **Weekly "overworked arms" digest** | ★★★☆☆ | Med | Adds the weekly cadence; natural creator/media content. |
| 8 | **Seasonal workload journals / leaderboards** | ★★★☆☆ | Med–High | Adds the seasonal cadence; cements the product as a fan's baseball home. |
| 9 | **Fantasy/DFS "is my closer rested?" view** | ★★★★☆ | Med | Opens a large, daily-habit, money-adjacent audience (see [MONETIZATION_AND_ADOPTION.md](MONETIZATION_AND_ADOPTION.md)). |

**If only one thing is built:** #1 (Follow My Team). It is low-effort, it is the
precondition for the trigger and delta loops, and it is the difference between a
tool a user *visits* and a product a user *opens*.

**If only two:** add #2 — because personalization pointing at a flat,
all-`Monitor` board still produces no reason to return. Memory plus a
discriminating signal is the minimum viable habit loop.
