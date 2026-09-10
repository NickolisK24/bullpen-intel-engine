# BaseballOS Language Engine V1

> Companion to [STORYTELLING_SURFACES.md](STORYTELLING_SURFACES.md).
> Central problem: **the intelligence platform works, but BaseballOS stories
> sound like BaseballOS talking about BaseballOS.** This document is the audit
> of that language, the specification of the translation layer that fixes it,
> and the record of what V1 changed.

The test: when a baseball person reads the homepage, they should think
*"yeah, that's how we'd talk about it"* — not *"that's how a model would talk
about it."*

---

## 1. Architecture

The ontology is untouched. The fix is a translation layer between the
internal reads and the words on the page.

```
Internal Layer                       Language Layer                User-Facing Story
─────────────────                    ──────────────                ─────────────────
Recovery Window        = Wide    →   "fresh pen",              →  "The White Sox bring one of
Workload Concentration = High    →   "leaning on the               the freshest bullpens
Bullpen Pressure       = High    →    same arms",                  into today"
Clean Options          = Thin    →   "room to breathe",
(bullpenConcepts.js,                 (bullpenLanguage.js +         (homeIntelligenceView.js,
 teamBullpenScoring.js,               this spec)                    storiesFeedView.js,
 landscape counts)                                                  teamBullpenStoryView.js)
```

**Where each layer is allowed to speak:**

| Slot | Voice | Example |
| --- | --- | --- |
| Headlines, prose, bullets, "Why It Matters" | Baseball | "The Mets keep handing the ball to the same relievers" |
| Read chips, stat labels, fact labels, the Today's Bullpen Shape strip | Ontology (evidence) | `High Bullpen Pressure`, `Clean Options: 6 of 8` |
| Tooltips / explanations behind a chip | Counts | "3 of 8 arms need rest; 2 more on watch." |

Two rules govern every sentence the platform writes:

1. **Concepts never act.** "Workload Concentration stacks up quietly" is model
   voice — a concept doing a verb. "Heavy use on the same few arms stacks up
   quietly" is baseball. Concepts appear as *labels on evidence*, not as the
   subject of prose.
2. **No system verbs in prose.** Arms never "register as" anything, never
   "carry a signal," and are never "workload-restricted." They come in fresh,
   need a day, sit on the watch list, get the call.

Code home of the layer: `frontend/src/utils/bullpenLanguage.js`
(`SIGNAL_HEADLINES` — one headline pool per signal, keyed by the slot that
uses it, so a signal sounds like itself everywhere without repeating one
sentence verbatim).

---

## 2. Language Audit

Every phrase that read as mechanical, model-driven, internal, or unnatural,
grouped by surface. ❌ = replaced in V1, ⏳ = left for a later pass (see §6),
✅ = kept deliberately.

### 2.1 Homepage (`homeIntelligenceView.js`, `Home.jsx`)

| Phrase (before) | Problem | Status |
| --- | --- | --- |
| "The Brewers **have baseball's most constrained bullpen** today" | "Constrained" is engine-state vocabulary in a flagship headline | ❌ |
| "The Blue Jays have baseball's **most concentrated bullpen workload** today" | A measurement, not a sentence anyone would say | ❌ |
| "The Nationals bring baseball's **widest Recovery Window** into today" | Ontology term as headline subject | ❌ |
| "relievers come in **with a limited Recovery Window**" | Concept used as a substance arms carry | ❌ |
| "relievers **register as Clean Options**" | System verb; arms don't "register" | ❌ |
| "**the cleanest availability context** in baseball" | Nobody in a clubhouse says "availability context" | ❌ |
| "**High Bullpen Pressure** narrows the late innings" (Why It Matters) | Concept as the actor of the sentence | ❌ |
| "**Workload Concentration** stacks up quietly" (Why It Matters) | Concept as the actor of the sentence | ❌ |
| Hero count chips labeled `Clean Options` / `Workload Concentration` / `Recovery Window` | Concept names pasted onto raw counts — and mislabeled (the "Recovery Window" chip counted *restricted* arms) | ❌ |
| "giving Stories another **Bullpen Pressure thread to unpack**" | Product talking about its own UI, concept as object | ❌ |
| "arms are **carrying Workload Concentration**" | The single worst offender — a concept as cargo | ❌ |
| "Recovery Window **is the counterweight to today's pressure**" | Concept-on-concept algebra | ❌ |
| "The watch list is not all at the top of the page" | Refers to the page layout, not baseball | ❌ |
| "Clean Options **still frame the league context**" | Concept as actor + "context" | ❌ |
| "so Workload Concentration **is not limited to the flagship club**" | Concept as a spreading condition | ❌ |
| League card: "More arms have a **limited Recovery Window** here than anywhere else" | Concept in prose slot | ❌ |
| League card title "Workload Concentration" over a team abbreviation | Reads as a grade stamped on a club | ❌ |
| "Depth Safety **is carrying more of the load** than usual today" | Concept as actor | ❌ |
| "managing **Recovery Window** as carefully as they manage innings" | Concept where "rest" belongs | ❌ |
| "The league **availability picture** moved overnight" | Internal noun phrase | ❌ |
| "Why It Matters", "What BaseballOS Sees Today", "Three Things To Watch" | Strong editorial framing | ✅ kept |
| "Built from completed games through Jun 5" (masthead) | Honest, plain | ✅ kept |

### 2.2 Stories Feed (`storiesFeedView.js`, `Stories.jsx`, story candidates)

| Phrase (before) | Problem | Status |
| --- | --- | --- |
| "Nobody brings a **wider Recovery Window** into today than the Nationals" | Ontology as headline subject | ❌ |
| "**Clean Options are stacked a little deeper** for the Giants" | Concept-led headline | ❌ |
| "**Coverage Safety is still part of today's league picture**" | Pure model voice, concept as subject | ❌ |
| "no standout **Workload Concentration signal** today" | "Signal" is engine vocabulary | ❌ |
| "**Depth Safety** is part of this pen's story" | Concept as character in the story | ❌ |
| "**Stories is watching** where **Bullpen Pressure** is obvious" | Product self-reference + concept as subject | ❌ |
| "it **gives the feed context** on both sides of the bullpen ledger" | Product talking about its feed | ❌ |
| "the heaviest **concentration of recent bullpen work**" | Measurement language in a body line | ❌ |
| Filter: "bullpens **carrying elevated workload strain**" | Clinical | ❌ |
| Filter: "bullpens entering the day with **cleaner availability**" | System noun | ❌ |
| Filter: "**workload patterns** are worth monitoring" | Model voice | ❌ |
| "N **active bullpen observations** across team, trend, and league **lanes**" | Internal taxonomy shown to the reader | ❌ |
| "The Blue Jays box score looks calm. The bullpen does not." | — | ✅ kept (the voice target) |
| "The Mets keep handing the ball to the same relievers" | — | ✅ kept |
| "A thin late-inning margin is forming for the Mets" | — | ✅ kept |
| "Observations, not predictions." (header chip) | Honest framing | ✅ kept |

### 2.3 Team Intelligence Panels (`teamBullpenStoryView.js`, `TeamBullpenStoryPanel.jsx`)

| Phrase (before) | Problem | Status |
| --- | --- | --- |
| Label chip "**Constrained Pen**" | Engine health-state word | ❌ → "Short-Handed Pen" |
| "The X bring one of the **cleanest availability pictures** into today" | System noun phrase in the headline | ❌ |
| "Rest **is doing a lot of the work in this bullpen's story** today" | Story talking about itself | ❌ |
| "3 arms are **workload-restricted** after their recent use" | Hyphenated system status as a verb | ❌ |
| "nobody is **workload-restricted** yet" | Same | ❌ |
| "no extreme **bullpen signal** today" | Engine vocabulary | ❌ |
| "unavailable for roster or **data reasons**" | Half-system phrasing | ❌ |
| "How the **Monitor group's fatigue reads** compare with the rested arms" | Board taxonomy + engine noun in a watch bullet | ❌ |
| "**The work is concentrated** in a small group, and **that concentration is the story**" | Measurement restated as drama | ❌ |
| Section header "**What The Workload Shape Says**" | "Workload shape" is internal geometry | ❌ → "What The Recent Work Says" |
| Framing "Context from current workload and availability **signals**" | Engine noun | ❌ |
| "Why BaseballOS Is Watching This Pen" | Brand voice, works | ✅ kept |
| "Today's Bullpen Shape" strip with `High Bullpen Pressure` / `Thin Clean Options` etc. | This **is** the evidence layer | ✅ kept |
| "Not enough fresh data for a strong read on the X today" | Honest limitation, plain words | ✅ kept |

### 2.4 Bullpen Pages (board, availability surfaces — audit only, see §6)

| Phrase | Problem | Status |
| --- | --- | --- |
| "Workload **signals are inside normal public-data use ranges**" (availability tone line) | Pure engine voice | ⏳ |
| "Public workload **signals show meaningful recent-use risk**" | Same | ⏳ |
| "No arms are **workload-restricted** tonight" (board empty state) | System status as adjective | ⏳ |
| "**Workload-only signal before roster-status adjustment**" (pitcher summary) | Pipeline language on a player card | ⏳ |
| "Roster and workload **signals behind this final status**" | Same | ⏳ |
| "Chicago Cubs **appears to have the most constrained bullpen** tonight" (dashboard storyline) | "Constrained" again; hedge verb | ⏳ |
| Governed observation cards (trust/dashboard): "Availability inventory is constrained." | Intentionally system-voiced on governance surfaces; translated before reaching story surfaces | ✅ by design |

---

## 3. Translation Layer Specification

One entry per internal signal. **Internal vocabulary never changes** — these
are presentation pools. "In code" marks the variants V1 shipped
(`SIGNAL_HEADLINES` plus surface copy); the rest are approved alternates for
future rotation. `{Team}` = full club name.

### Recovery Window — Wide / deep Clean Options

*The pen is rested; most arms come in without restriction.*

| Slot | Headline |
| --- | --- |
| In code — hero | "The {Team} bring baseball's freshest bullpen into today" |
| In code — feed | "Nobody brings a fresher bullpen into today than the {Team}" |
| In code — feed depth | "The {Team} have fresh arms to spare today" |
| In code — team panel | "The {Team} bring one of the freshest bullpens into today" |
| Alternate | "The {Team} have room to breathe tonight" |
| Alternate | "Plenty of coverage tonight for the {Team}" |
| Alternate | "A full pen and a free hand for the {Team}" |

Inline phrases: *fresh pen · room to breathe · arms to spare · rested and
ready · the kind of depth that lets the late innings breathe.*

### Recovery Window — Narrow/Limited / High Bullpen Pressure

*The pen is short on rested arms after recent workload.*

| Slot | Headline |
| --- | --- |
| In code — hero | "The {Team} bullpen is stretched thinner than any in baseball today" |
| In code — feed | "A thin late-inning margin is forming for the {Team}" |
| In code — team panel | "The {Team} enter today with a thin late-inning margin" |
| Alternate | "The {Team} are short in the pen tonight" |
| Alternate | "Not many fresh arms left for the {Team}" |
| Alternate | "The late innings are getting tight for the {Team}" |

Inline phrases: *stretched thin · coming in short · needing rest / needing a
day · less room in the late innings · less margin than most.*

### Workload Concentration (and the reserved Leverage Concentration / Workload Accumulation)

*Recent work is clustered on a few arms instead of spread around.*

| Slot | Headline |
| --- | --- |
| In code — hero | "The {Team} are leaning on the same arms more than anyone in baseball today" |
| In code — feed | "The {Team} keep handing the ball to the same relievers" |
| In code — feed hidden | "The {Team} box score looks calm. The bullpen does not." |
| In code — team panel | "The {Team} look calm on the surface — the workload underneath is worth watching" |
| Alternate | "The {Team} keep leaning on the same arms" |
| Alternate | "Heavy usage is falling on a small group" |
| Alternate | "Late innings are running through the same relievers" |
| Alternate | "The same names every night for the {Team}" |

Inline phrases: *leaning on the same arms · the same arms keep getting the
call · heavy work falling on a small group · carrying the heavy lifting ·
stacks up quietly.*

### Clean Options — Thin/Very Thin

*Few arms enter without a workload flag.*

| Slot | Headline |
| --- | --- |
| In code — observation card | "Fresh arms are harder to find in a few pens today" |
| In code — observation card | "A few late-inning margins are getting thin" |
| Alternate | "Fewer fresh arms than the {Team} would like" |
| Alternate | "One long night from real trouble" |

Inline phrases: *fewer fresh arms than they would like · almost nobody fresh ·
the margin for a long night is thin.*

### Bullpen Dependency (reserved — concept live in ontology, no surface yet)

| Slot | Headline |
| --- | --- |
| Reserved | "This pen relies on its core arms" |
| Reserved | "Few relievers carry most of the load" |
| Reserved | "Take away two arms and this pen changes shape" |

### Coverage Safety / Depth Safety

*How much length and fallback the pen has behind its primary arms.*

| Slot | Headline |
| --- | --- |
| In code — feed (league) | "Most of the league still has fresh arms to call on" |
| Reserved | "Somebody has to cover the middle innings" |
| Reserved | "The back of this pen is doing real work" |

Inline phrases: *the back of the bullpen is carrying more of the load · fresh
depth beyond the arms the club trusts most.* Labels (`Strong Coverage
Safety`, `Thin Depth Safety`…) stay on the shape strip as evidence.

### Bullpen State / Bullpen Identity / Bullpen Resilience (reserved)

No live surfaces yet. When they arrive: State → "where this pen is today";
Identity → "how this pen is built / how this club uses its pen"; Resilience →
"how fast this pen bounces back". Same two rules apply.

### Limited Read (trust tier)

Honesty beats fluency — limitation copy stays plain and is **not** dressed
up: "Not enough fresh data for a strong read on the {Team} today." The label
`Limited Read` keeps its name everywhere.

---

## 4. Before / After (V1 as shipped)

| Surface | Before | After |
| --- | --- | --- |
| Hero (stress) | "The Brewers have baseball's most constrained bullpen today" | "The Brewers bullpen is stretched thinner than any in baseball today" |
| Hero (concentration) | "The Blue Jays have baseball's most concentrated bullpen workload today" | "The Blue Jays are leaning on the same arms more than anyone in baseball today" |
| Hero (rest) | "The Nationals bring baseball's widest Recovery Window into today" | "The Nationals bring baseball's freshest bullpen into today" |
| Hero observation | "…relievers register as Clean Options — the cleanest availability context in baseball today." | "…relievers come in rested and ready to go — no pen in baseball has more fresh arms to call on today." |
| Why It Matters | "High Bullpen Pressure narrows the late innings." | "A stretched pen narrows the late innings." |
| Why It Matters | "Workload Concentration stacks up quietly." | "Heavy use on the same few arms stacks up quietly." |
| Watch item | "The watch list is not all at the top of the page" | "Another club keeps going to the same arms" |
| Watch item | "Recovery Window is the counterweight to today's pressure" | "At least one pen comes in with room to breathe" |
| Watch item body | "…are carrying Workload Concentration, a quieter signal worth a second look." | "…have been carrying the heavy work lately — quiet so far, worth a second look." |
| League context | "9 tracked arms have a limited Recovery Window… and 38 register as Clean Options." | "Around the league, 9 tracked arms need rest after recent work… and 38 come in fresh." |
| League card | "More arms have a limited Recovery Window here than anywhere else in baseball." | "More arms need a day here than anywhere else in baseball." |
| Story card | "Nobody brings a wider Recovery Window into today than the Nationals" | "Nobody brings a fresher bullpen into today than the Nationals" |
| Story card | "Clean Options are stacked a little deeper for the Giants" | "The Giants have fresh arms to spare today" |
| Story card | "Coverage Safety is still part of today's league picture" | "Most of the league still has fresh arms to call on" |
| Story body | "…Stories is watching where Bullpen Pressure is obvious and where it is still quiet." | "…Some of that work is obvious, some is still quiet — and the quiet kind is usually where the next story starts." |
| Feed filter | "Stories involving bullpens carrying elevated workload strain." | "Pens that have been worked hard and are short on rest." |
| Team panel (rested) | "The White Sox bring one of the cleanest availability pictures into today" | "The White Sox bring one of the freshest bullpens into today" |
| Team panel summary | "Rest is doing a lot of the work in this bullpen's story today." | "This pen has room to breathe today." |
| Team panel bullet | "3 arms are workload-restricted after their recent use." | "3 arms have earned a rest day after the work they have carried." |
| Team panel summary | "The work is concentrated in a small group, and that concentration is the story." | "The heavy work keeps falling on the same small group, and that is the story." |
| Panel section | "What The Workload Shape Says" | "What The Recent Work Says" |
| Panel label | "Constrained Pen" | "Short-Handed Pen" |
| Panel headline (balanced) | "…come in steady — no extreme bullpen signal today" | "…come in steady — nothing tilting the pen either way today" |

Ontology untouched and still on the page: the hero read chip
(`High Bullpen Pressure` + count tooltip), feed card read tags
(`Concentrated Workload`, `Wide Recovery Window`), League Context fact labels
(`Bullpen Pressure` / `Workload Concentration` / `Clean Options`), the full
Today's Bullpen Shape strip (`Trust Arm Availability`, `Clean Options`,
`Bullpen Pressure`, `Coverage Safety`, `Depth Safety`), and every label tier
in `teamBullpenScoring.js` and `bullpenConcepts.js`.

---

## 5. Enforcement

- `tests/homeIntelligence.test.mjs`, `tests/storiesFeed.test.mjs`,
  `tests/teamBullpenStoryPanel.test.mjs` pin the new copy and now also ban
  the mechanical patterns in prose: `register as`, `workload-restricted`,
  `availability context`, `availability picture`, `limited recovery window`,
  `carrying workload concentration`.
- Existing guardrails (no predictions, no rankings, no advice, no betting/
  injury language, no raw governance vocabulary) all still hold.

## 6. Remaining Areas That Still Feel Mechanical

Out of V1 scope (V1 = homepage, stories, team intelligence). Next passes, in
rough priority order:

1. **Availability tone lines** (`availabilityView.js`, also surfaced on
   pitcher cards and the board legend): "Workload signals are inside normal
   public-data use ranges." → e.g. "Normal recent workload — nothing holding
   this arm back."
2. **Tonight's Bullpen Board empty states** (`tonightsBullpenBoardView.js`):
   "No arms are workload-restricted tonight."
3. **Pitcher availability summary** (`AvailabilitySummary.jsx`):
   "Workload-only signal before roster-status adjustment." is pipeline
   language on a player card.
4. **Dashboard storylines** (`bullpenLandscapeView.js`): "appears to have the
   most constrained bullpen tonight", "shows the highest concentration of
   Monitor arms."
5. **Comparison view** (`teamBullpenComparisonView.js`): carries little prose
   of its own but inherits the availability badge/tone lines, so fixing (1)
   fixes it.
6. **Governed observation surfaces** (trust page, dashboard intelligence
   panel): deliberately system-voiced today; decide whether deeper surfaces
   ever adopt the language layer or stay raw as the audit trail.
