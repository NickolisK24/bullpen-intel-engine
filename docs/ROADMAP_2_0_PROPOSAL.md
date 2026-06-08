# Roadmap 2.0 Proposal — June 2026

> Companion to [PRODUCT_AUDIT_JUNE_2026.md](PRODUCT_AUDIT_JUNE_2026.md).
> This roadmap is **planning context, not implementation authorization.** It
> proposes direction; it does not modify code, APIs, schemas, or governance.
>
> **Organizing thesis:** the engine is built; the product is not. Every item
> below is judged by one test — *does it move BaseballOS from "an engine a few
> admire" to "a product fans open daily and share"?* Items that don't are
> demoted or cut.

For each item: **rationale · expected impact · effort · risk.**
Impact and effort on ★ (1–5). Risk = Low / Med / High.

---

## DO NEXT — Highest-Value (the next ~one quarter)

> Theme: **Finish the product on top of the engine that exists.** Not one of
> these requires a new engine. All are presentation, memory, and proof.

### N1 — Make the live Bullpen Board actually discriminate
- **Rationale:** The flagship surface historically classifies nearly all arms
  `Monitor` on live data (`backend/reports/availability_threshold_audit.md`). A
  board that's all one color tells no story and proves nothing. Every other item
  depends on this.
- **Impact:** ★★★★★ · **Effort:** ★★★☆☆ · **Risk:** Med (threshold tuning must
  stay honest, not engineered for drama).

### N2 — "Follow My Team" personalization
- **Rationale:** Cheapest retention mechanism in existence; makes the product
  *yours* and removes per-visit setup. Foundation for deltas and alerts.
- **Impact:** ★★★★★ · **Effort:** ★★☆☆☆ · **Risk:** Low.

### N3 — Daily Bullpen Stress Card (shareable artifact)
- **Rationale:** The atomic unit of growth. One watermarked, screenshot-ready
  card per team per day that travels on social and pulls in new users. The growth
  loop the product completely lacks. See
  [STORYTELLING_SURFACES.md](STORYTELLING_SURFACES.md) S1.
- **Impact:** ★★★★★ · **Effort:** ★★★☆☆ · **Risk:** Low.

### N4 — "What changed overnight" deltas for your team
- **Rationale:** Converts a reference tool into a daily feed by guaranteeing a
  different answer each day. The reason to return tomorrow.
- **Impact:** ★★★★☆ · **Effort:** ★★★☆☆ · **Risk:** Low.

### N5 — Fix the freshness/sync-status seam
- **Rationale:** The trust page has reported `never` on fresh data (sync metadata
  in a git-ignored file). A trust-first product whose trust indicator is wrong is
  self-defeating. Cheap, mandatory.
- **Impact:** ★★★★☆ · **Effort:** ★★☆☆☆ · **Risk:** Low.

### N6 — Align all public "production" claims with live-data reality
- **Rationale:** Documentation-only, but trust-critical. Mark V5/observations as
  "sample-state," not "production approved." One skeptic who catches the gap
  discounts every honest claim. (This audit is part of that correction.)
- **Impact:** ★★★★☆ · **Effort:** ★☆☆☆☆ · **Risk:** Low.

### N7 — De-jargon the user-facing surfaces
- **Rationale:** Strip `ranking_applied === false` and contract vocabulary from
  what users see; keep it in API metadata. Governance language is anti-product on
  a fan surface.
- **Impact:** ★★★☆☆ · **Effort:** ★★☆☆☆ · **Risk:** Low.

---

## DO LATER — Valuable, Not Urgent (the following ~two quarters)

> Theme: **Deepen the habit and open the funnel** once the daily loop works.

### L1 — Daily "Around the League" story feed
- **Rationale:** A reason to look even when your team isn't playing; the
  "standings page" of bullpen workload; a daily media-citation source.
- **Impact:** ★★★★☆ · **Effort:** ★★★☆☆ · **Risk:** Low.

### L2 — Email / push "your bullpen changed" digest
- **Rationale:** The trigger the habit loop is missing — brings users back without
  them remembering to visit. Also the natural first paid (fantasy) feature.
- **Impact:** ★★★★☆ · **Effort:** ★★★☆☆ · **Risk:** Med (deliverability, opt-in
  discipline).

### L3 — Series Matchup Bullpen Preview
- **Rationale:** Reframes the underexploited Compare view as recurring, timely,
  media-ready content ("rested vs. gassed").
- **Impact:** ★★★☆☆ · **Effort:** ★★★☆☆ · **Risk:** Low.

### L4 — Fantasy/DFS "is my closer rested?" view + Pro-for-Fantasy tier
- **Rationale:** Opens the largest reachable *paying* audience on the same honest
  data. See [MONETIZATION_AND_ADOPTION.md](MONETIZATION_AND_ADOPTION.md).
- **Impact:** ★★★★☆ · **Effort:** ★★★★☆ · **Risk:** Med.

### L5 — Collapse Recommendation V1/V2 into the board
- **Rationale:** Two engines that decline to recommend confuse users and cost
  maintenance. Fold their useful context into the board as plain-language reasons;
  retire the standalone panels.
- **Impact:** ★★★☆☆ · **Effort:** ★★★☆☆ · **Risk:** Med (governance boundaries
  must be preserved in the merge).

### L6 — Wire the V5 Observation engine to live data
- **Rationale:** It's architecturally the story engine; on live data it can power
  the feed (L1) and cards (N3) natively instead of sample fixtures.
- **Impact:** ★★★★☆ · **Effort:** ★★★☆☆ · **Risk:** Med.

### L7 — Mobile polish pass
- **Rationale:** Fantasy/casual checking is a phone behavior. The daily loop lives
  on mobile or it doesn't live.
- **Impact:** ★★★☆☆ · **Effort:** ★★★☆☆ · **Risk:** Low.

### L8 — Public data/API + CSV export for analysts
- **Rationale:** Inspectable data is the ultimate trust signal and seeds
  derivative content/evangelism.
- **Impact:** ★★★☆☆ · **Effort:** ★★★☆☆ · **Risk:** Low.

---

## DO MUCH LATER — Future Opportunities (post-traction)

### M1 — Weekly & seasonal leaderboards / journals ("Most Abused Pen of 2026")
- **Rationale:** Establishes weekly + seasonal cadence and long-term authority;
  national-writer citation bait. Worth more once a daily audience exists to anchor
  it.
- **Impact:** ★★★★☆ (later) · **Effort:** ★★★☆☆ · **Risk:** Low.

### M2 — Creator/media licensing & white-label embeds
- **Rationale:** Monetize institutions while turning their reach into validation.
  Requires an established artifact + audience first.
- **Impact:** ★★★★☆ (later) · **Effort:** ★★★★☆ · **Risk:** Med.

### M3 — Transaction-lineage / workload history persistence
- **Rationale:** Already a noted limitation; enables richer trend stories and
  audit trails. Real value, but not what wins the first 1,000 WAU.
- **Impact:** ★★★☆☆ · **Effort:** ★★★★☆ · **Risk:** Med.

### M4 — Pro / baseball-operations tier
- **Rationale:** Highest contract value, highest credibility bar. Should emerge
  *organically* from proven public accuracy, never be chased early (chasing it
  resurrects the governance-theater failure mode).
- **Impact:** ★★★★★ (someday) · **Effort:** ★★★★★ · **Risk:** High.

### M5 — Adjacent expansion (starter workload, rest-of-roster availability)
- **Rationale:** Only after bullpen availability is fully owned. Breadth is the
  *reward* for winning the niche, not the path to it.
- **Impact:** ★★★☆☆ · **Effort:** ★★★★☆ · **Risk:** Med.

---

## NEVER DO — Would Dilute the Product

### X1 — A sixth engine version / new certification phase before the product ships
- **Rationale:** This is the project's signature failure mode — answering product
  problems with more engine and more ceremony. Six more months of this yields a
  more-certified product with zero daily users. **The single most important
  "never."**

### X2 — Predictions, rankings, "best arm," or pick-a-pitcher selection
- **Rationale:** Detonates the trust thesis that is the entire differentiator.
  Descriptive-and-honest is the moat; predictive-and-confident is a commodity that
  invites being wrong in public.

### X3 — Betting / odds integration
- **Rationale:** Directly contradicts the stated identity and trades the trust
  brand for short-term revenue. Permanently off the table.

### X4 — Pay-to-influence anything in the availability model
- **Rationale:** Selling a "better" availability score, or sponsored placement in
  judgments, tells users the free/honest answer is compromised. Corrupts the one
  asset that matters.

### X5 — Chasing FanGraphs/Savant/Reference on breadth
- **Rationale:** Unwinnable and off-strategy. Depth in one unclaimed category
  beats shallow parity across four claimed ones. See
  [COMPETITIVE_ANALYSIS_JUNE_2026.md](COMPETITIVE_ANALYSIS_JUNE_2026.md).

### X6 — Expanding the governance/certification documentation corpus
- **Rationale:** ~147 docs already obscure the product more than they protect it.
  More phase docs raise maintenance cost and scare off collaborators. Consolidate;
  do not grow.

---

## The Roadmap in One Paragraph

**Do Next:** make the board discriminate, make it personal, make it shareable,
make it honest. **Do Later:** turn that into a daily feed, an alert, a fantasy
product, and an open API. **Do Much Later:** leaderboards, licensing, history, and
— only once you've earned it — a pro tier and adjacent expansion. **Never:**
build another engine version, predict, rank, take bets, sell the honesty, or grow
the doc pile. The hard part is finished. What remains is the part that turns an
engine into a product people genuinely care about — and it is weeks of focused,
honest work, not another year of certification.
