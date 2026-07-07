# BaseballOS Product Vision Specification

Status: Permanent design document. Product architecture only — no implementation
direction. Future roadmap phases should read this before designing any surface.

---

## 1. Executive Product Philosophy

BaseballOS exists because bullpen state is the most consequential, least visible
context in baseball. Everyone can see the box score. Almost no one can see what
the box score did to tomorrow: which bullpen is walking into tonight with three
rested arms, which manager is one long inning away from using someone he does
not want to use, which "fully healthy" pen has quietly run its late innings
through the same two pitchers for a week.

BaseballOS makes that visible — and stops there.

The product's entire identity fits in one sentence: **BaseballOS is the trusted
public explanation layer for MLB bullpen state.** It tells you who is fresh, who
is stretched, who is carrying the unit, and why it matters tonight. It never
tells you what will happen, who will win, who to pick, or who is "best." The
moment it crosses that line it becomes one of a hundred prediction products and
loses the only position worth holding: the one source a fan, a writer, and a
skeptic can all cite without embarrassment.

Three commitments define every page:

1. **Answer the question before showing the data.** Every surface leads with a
   plain-baseball answer to a real baseball question, then shows the evidence
   underneath it. Data without a question is a spreadsheet; BaseballOS is not a
   spreadsheet.
2. **Every claim carries its receipt.** State → Why → Evidence → Freshness →
   Limitations is not a layout convention; it is the product's contract with
   the reader. Anything shown without its receipt within one click is a bug in
   the product's character, even if it renders perfectly.
3. **Honesty over completeness.** When BaseballOS cannot make a read, it says
   so, plainly, in the same visual voice it uses for confident reads. An empty
   answer stated honestly builds more trust than a full answer padded with
   guesses. The product's willingness to say "we can't see this" IS the
   product.

The finished BaseballOS should feel like a great beat writer's notebook made
public: current, plainspoken, sourced, humble about what it can't know, and
impossible to mistake for a tout sheet.

---

## 2. Product Architecture Principles

**One question per page.** Every public page owns exactly one user question and
answers it better than any other page in the product. If two pages can answer
the same question, one of them is wrong. The page map is the question map.

**One canonical home per fact.** Every read, count, definition, and disclaimer
lives in exactly one authoritative place. Other pages may *tease* it (a
one-line preview that hands off), *reference* it (a link), or *inherit* it (the
same words from the same source) — but never restate it in their own words.
Teasing is pointing; restating is competing.

**Altitude discipline.** The product has four altitudes, and every page sits at
exactly one: League (all thirty pens), Team (one pen), Arm (one reliever), and
Meta (how to read all of the above). Pages never mix altitudes in their primary
answer; they link across altitudes instead. Confusion in the current era of
sports products almost always comes from altitude mixing.

**Evidence is the destination, not the decoration.** The deepest layer of every
drill-down is actual baseball events — appearances, dates, pitch counts, rest
days. Not a number that summarizes them: the events themselves. A user who
keeps clicking "why?" must always bottom out at something that happened in a
real game, never at an unexplained value.

**The vocabulary is the interface.** BaseballOS speaks a small, fixed, public
dictionary: team states (Fresh / Stretched / Vulnerable), arm availability
(Available / On Watch / Limited / Unavailable), and a handful of named reads
(Bullpen Pressure, Recovery Window, Workload Concentration, Clean Options,
Coverage Safety, Trusted Arms). Every word in that dictionary is defined in one
line, in one place, and used identically everywhere. Growth of the dictionary is
a product decision, never a side effect.

**Freshness is ambient, not decorative.** The reader should never have to
wonder "as of when?" — the answer is always visible, in the same words, in the
same place on every surface. Time-honesty is a layout primitive on par with
typography.

**No dead ends, no loops.** Every page has an obvious next step deeper (toward
evidence) and an obvious step back up (toward the day's picture). No page links
sideways to a page that answers the same question. Navigation should feel like
a funnel with a wide daily mouth and evidence at the bottom.

---

## 3. Vision for Every Public Page

### 3.1 Today — the Daily Edition

**Mission.** Be the page a bullpen-curious fan opens at 4pm every day, the way
they'd open a newspaper's front page. Today is not a portal, a dashboard, or a
menu — it is an *edition*: dated, curated, finite, and readable top to bottom
in about ninety seconds.

**The one question.** *"What is the bullpen story today, and what should I
watch tonight?"*

**First-time visitor feeling.** "Oh — someone is actually watching this for me."
The page should feel authored, not generated: one confident lead, a few watch
items, a clean handoff to depth. A first-timer should leave able to repeat one
bullpen fact to a friend that night.

**Returning-user value.** Ritual. The page changes meaningfully every day, takes
the same short time to read, and rewards the habit: yesterday's watch item pays
off ("the pen we flagged got exposed in the eighth"). Returning users come for
continuity — what changed since yesterday — not for raw coverage.

**Most visual emphasis.** The lead read of the day: one team, one situation, one
plainly stated reason it matters tonight. Second: tonight's two-or-three watch
cards. Everything else is subordinate.

**Supporting context.** A slim league teaser (one standout per lane) pointing to
the Dashboard; the date and freshness stamp; a quiet on-ramp to the learning
pages for newcomers.

**Never on this page.** Full league tables. Complete team rosters. More than a
handful of items of anything. Scores or model artifacts of any kind. A second
voice — Today speaks once, in one editorial register. Anything a user must
scroll past daily without reading.

**Relationships.** Today is the mouth of the funnel: it hands league curiosity
to the Dashboard, team curiosity to the Team Board, narrative appetite to
Stories, and skepticism to Data & Trust. Nothing hands off *to* Today except
the logo.

**Twice as large?** Add tonight's slate with a one-line bullpen note per game
(who's compromised on each side), and a short "since yesterday" strip — three
factual movements across the league. Both deepen the edition without changing
its character.

**Half as large?** The lead read and the tonight watch cards survive. Nothing
else is essential. That is the correct stress test: Today is those two things.

**Finished looks like.** A dated daily page a beat writer would not be
embarrassed to have written: one lead, a few watch items, receipts one click
away, and a reader who checks it as reflexively as the standings.

---

### 3.2 Dashboard — the League Board

**Mission.** Be the single full-league surface: all thirty bullpens' state, in
baseball language, scannable in one screen. The Dashboard is the establishing
shot; every other page is a close-up.

**The one question.** *"Across the whole league, whose pen is fresh, whose is
stretched, and where do I look closer?"*

**First-time visitor feeling.** Command. The sensation of seeing the entire
league's late-inning landscape at once — something no box score, standings
page, or broadcast provides.

**Returning-user value.** Sweep efficiency. An analyst or writer starting a
league-wide question (planning a column, prepping a broadcast, checking a
narrative) should finish their first pass here in under a minute and know
exactly which two or three team boards to open.

**Most visual emphasis.** The landscape itself — every team, grouped by state,
each row carrying its counts and one-word situation. The board is the page;
everything else orbits it.

**Supporting context.** One league-level state read (a single sentence on the
overall bullpen weather); roster/IL context (how much of the league's relief
depth is unavailable for roster reasons, kept visibly separate from workload);
the freshness line.

**Never on this page.** A second league summary in a different vocabulary.
Team-level detail (that is the Team Board's job). Any column a reader could
sort into a leaderboard of quality. Navigation tiles, orientation copy, or
anything that explains the product instead of the league.

**Relationships.** Receives the curious from Today's teaser; hands every row to
the Team Board. It should never need to link "up" — it is the top of the
league altitude.

**Twice as large?** Full thirty-team coverage in every lane (not just
standouts), a compact per-division view, and a "movement" annotation — which
pens changed state since yesterday, stated factually. All depth, same question.

**Half as large?** The landscape survives, alone. Correct.

**Finished looks like.** The page a national writer screenshots when making a
league-wide bullpen point — with the freshness stamp visible in the screenshot,
because the layout made cropping it out unnatural.

---

### 3.3 Bullpen Team Board — the Team Page

**Mission.** Be the definitive public page for one team's bullpen — the page a
fan of that team bookmarks, and the page every other surface deep-links into.
This is the product's center of gravity: if BaseballOS is remembered for one
page, it should be this one.

**The one question.** *"Who in this bullpen can pitch tonight, who can't, and
why?"*

**First-time visitor feeling.** Recognition — "this is my team's pen, told
straight." A fan should see their own intuition ("we've been riding Suarez too
hard") confirmed or corrected with receipts within ten seconds.

**Returning-user value.** The nightly pre-game check. Before first pitch, a
returning fan reads: the state line, who moved between groups since yesterday,
and whether the arm they're worried about is rested. Under thirty seconds.

**Most visual emphasis.** The availability board — the arms, grouped
Available / On Watch / Limited / Unavailable — with one team-state line above
it. The names ARE the content; a fan comes to see names, not abstractions.

**Supporting context.** One consolidated team-state read (state, plain-language
why, supporting reads); the recent relief-work evidence (who actually pitched,
when, how much — the receipts for everything above it); roster context (who is
off the active roster, kept separate from workload); a single team note and
game context, at the bottom.

**Never on this page.** A second summary of availability in different words.
League content. Rankings of the team's arms against each other. Any number
that cannot be explained by pointing at the recent-work evidence below it.
Controls that require instructions.

**Relationships.** The destination of nearly every deep link in the product
(Today cards, Dashboard rows, Stories CTAs, Compare links, share pages). Hands
individual arms to Pitcher Detail. Its upward link is the Dashboard.

**Twice as large?** A short factual "what changed since the last game" strip
(two or three movements with dates), starter-length context (how deep this
team's starters have been going, since that drives pen load), and richer
per-arm recent-work summaries inline. All evidence, no new abstraction.

**Half as large?** State line + availability groups + freshness. The evidence
panel becomes a click. Still the same page.

**Finished looks like.** When a broadcaster says "their bullpen's in trouble
tonight," viewers open this page to see if it's true — and can tell in one
glance, with the receipts one scroll below.

---

### 3.4 Compare Bullpens — the Matchup Lens

**Mission.** Answer the most natural fan question in baseball — "my team plays
yours tonight; whose pen is in better shape?" — descriptively, without ever
crowning a winner.

**The one question.** *"Between these two pens, tonight, who has more left —
and why?"*

**First-time visitor feeling.** Fairness. The page compares without picking: it
states observable differences ("Team A has five rested arms; Team B's last
three wins ran through the same two relievers") and lets the reader conclude.
A first-timer should notice — and respect — that the page refused to declare a
verdict.

**Returning-user value.** Pre-game ritual for rivalry and series nights;
material for group-chat arguments, with citable facts.

**Most visual emphasis.** The side-by-side state: two team-state lines facing
each other, then the availability counts aligned for comparison.

**Supporting context.** Two or three factual observations naming the actual
difference; per-team freshness; links into both full team boards.

**Never on this page.** Embedded full team pages. A composite "who wins the
bullpen battle" verdict, score, or lean — in any wording. Head-to-head
historical records (that is prediction bait). More than one screen of content.

**Relationships.** Fed by tonight's slate (eventually auto-paired with the
evening's games); exits into both Team Boards. It is a lens, not a library.

**Twice as large?** Tonight's-slate pairing (pick a game, get the comparison),
late-inning depth comparison (each team's rested trusted arms, named), and
starter-length context for both sides. Still descriptive, still two teams.

**Half as large?** Two state lines and the counts. Done.

**Finished looks like.** The page fans open during the seventh inning of a
close game to see which manager is about to run out of good options — and
argue about what it means, because BaseballOS deliberately didn't tell them.

---

### 3.5 Pitcher Detail — the Arm's Story

**Mission.** Tell one reliever's current story in evidence: his availability,
the actual week of work behind it, and what that workload means in plain
baseball terms. This page should be the product's purest expression of
evidence-first — and in the finished product, it contains no naked numbers
that summarize a model.

**The one question.** *"Can this arm pitch tonight, and what has his recent
work actually looked like?"*

**First-time visitor feeling.** Intimacy with the evidence. "He threw 28 pitches
Tuesday, 19 Wednesday, and sat yesterday — so 'On Watch' makes sense." The
reader should feel they could have reached the label themselves from the facts
shown. That feeling is the entire trust proposition at the arm level.

**Returning-user value.** Following an arm through a stretch — the closer on
fumes during a playoff push, the rookie earning late innings. Returners come to
see the story advance appearance by appearance.

**Most visual emphasis.** The availability status and the recent appearance log
— dates, pitches, innings, rest — presented as the star of the page, not a
footnote beneath a big number.

**Supporting context.** The one-line "why this availability" explanation; role
context (what usage pattern this arm shows); quick workload facts in baseball
units (pitches over 7 days, appearances, rest days); freshness and
limitations.

**Never on this page.** A large unexplained index number as the visual lead.
Model internals presented as truth: factor weights, radar shapes, threshold
lines. Performance judgment (ERA-as-verdict), injury insinuation, or any
next-outing implication. Comparison to other pitchers (that is a ranking in
disguise).

**Relationships.** Reached from everywhere an arm's name appears (board cards,
tables, search); exits back to the arm's team board. It is the bottom of the
funnel — the receipts layer — so it links down only to nothing and up to
everything.

**Twice as large?** A longer appearance history with game context (score state,
inning entered), season workload rhythm (busy and quiet stretches, shown as
events, not curves against thresholds), and role evolution over the year told
in appearances.

**Half as large?** Status, why-line, last five appearances, freshness. Whole
story intact.

**Finished looks like.** A page where the label and the log are so obviously
connected that removing the label would barely hurt — the reader would infer
it from the evidence. That is the standard: the read is a courtesy summary of
visible facts, never a verdict from a hidden machine.

---

### 3.6 All Pitchers — the Reference Table

**Mission.** Be the fast, unglamorous utility for finding any reliever and
scanning objective workload facts. A phone book, proudly.

**The one question.** *"Where do I find a specific reliever — or filter a set
of them — and see their current workload facts?"*

**First-time visitor feeling.** Nothing, ideally. This page is for people who
arrived with a name in mind. Its virtue is disappearing behind its task.

**Returning-user value.** Speed. Type, filter, click, done.

**Most visual emphasis.** The search box and the table rows.

**Supporting context.** Availability badges; baseball-unit columns (pitches/7d,
appearances/7d, rest days); team filter.

**Never on this page.** Sortable score columns (a sortable score is a
leaderboard, whatever it's named). Risk-tier vocabulary as the primary filter.
Editorial content of any kind. Team-level panels.

**Relationships.** A utility spoke off the Bullpen area: rows open Pitcher
Detail, team filters suggest the Team Board. No page depends on it; it exists
for the user who knows what they want.

**Twice as large?** More filters (role, handedness, recent usage), and a saved
shortlist for users who track a set of arms. Utility depth only.

**Half as large?** Search plus name/team/availability. Still a phone book.

**Finished looks like.** The fastest way on the public internet to answer "has
this middle reliever pitched three days in a row?" — and nothing more.

---

### 3.7 Stories — the Feed

**Mission.** Hold everything BaseballOS is noticing that didn't make the front
page: the browseable layer of team observations, trend notes, and watch items,
each one checkable and shareable. If Today is the front page, Stories is the
rest of the paper.

**The one question.** *"Beyond today's headline, what bullpen storylines are
live right now?"*

**First-time visitor feeling.** Abundance with standards. Many stories, but
every one carries the same disciplined skeleton — what everyone saw, what
BaseballOS noticed, the evidence, why it matters — so browsing feels like
reading a well-edited section, not scrolling a machine's output.

**Returning-user value.** The deep-cut habit: creators and hardcore fans mining
material, following a storyline across days via continuity notes ("this is the
third straight day the eighth inning ran through the same arm").

**Most visual emphasis.** The story cards' headlines and their
"what BaseballOS noticed" turn — the insight is the product; the lanes and
filters are furniture.

**Supporting context.** Lane filters (pressure / watch / rest / league); the
trust strip (data through, live vs review); share affordances; team-board CTAs.

**Never on this page.** The league landscape or any state summary (altitude
violation). Stories without evidence attached. Machine-voice or process
language visible to readers. Endless-scroll padding — a light day should look
light, honestly.

**Relationships.** Teased by Today (one lead there, the rest here); every story
exits to its team board. Stories is the narrative sibling of the Dashboard:
same league, told in words instead of a board.

**Twice as large?** Story continuity ("developments" threading a storyline
across days), a light archive (what BaseballOS said about this team last
week — accountability as a feature), and per-team story history on handoff to
team boards.

**Half as large?** The feed with its skeleton cards. Filters can go before a
single card loses its evidence.

**Finished looks like.** A feed a baseball editor would ship: every item
sourced, no item hedged into mush, and quiet days honestly quiet.

---

### 3.8 Methodology — the Open Kitchen

**Mission.** Show the skeptical reader exactly how every public read is built —
inputs, windows, and definitions — and state plainly what BaseballOS refuses
to claim. This page converts skeptics; it is written for the reader who
arrived to catch the product lying.

**The one question.** *"How does BaseballOS actually compute what it shows me?"*

**First-time visitor feeling.** Disarmament. "They actually explain it — and
they list what they can't know without me forcing it out of them."

**Returning-user value.** A citation target. Writers and researchers link to it
when they use BaseballOS reads in their own work.

**Most visual emphasis.** How the availability labels and team states are
derived, in the same public vocabulary the product speaks — because those are
the claims readers encounter most.

**Supporting context.** Data sources; the named reads' derivations; the
exploratory study, fenced clearly as exploratory; the known-limitations
statement in the canonical boundary language.

**Never on this page.** Live data (that is Data & Trust's job — Methodology
explains the recipe, Trust shows today's kitchen inspection). Internal system
vocabulary of any kind. Accuracy claims. Defensive over-explaining — state the
method once, confidently.

**Relationships.** Linked from every "how is this computed?" affordance in the
product; defers all live reliability to Data & Trust; shares its definitions
with How to Read from the same canonical dictionary (How to Read is the
one-line version; Methodology is the full recipe).

**Twice as large?** Worked examples: one real (anonymized-date) bullpen walked
from raw appearances to its labels, step by step. Nothing persuades like a
traced example.

**Half as large?** Label derivations, sources, limitations. The exploratory
study can leave before any of those.

**Finished looks like.** The page a rival analyst reads intending to write a
takedown — and comes away citing instead.

---

### 3.9 Data & Trust — the Receipts Page

**Mission.** Show, with live data, that BaseballOS deserves the trust the rest
of the product asks for: how fresh everything is, whether updates are arriving,
and whether the labels have matched what actually happened on the field. This
is the only page whose content is *about the product* rather than about
baseball — and it must still read like a public page, never an internal
console.

**The one question.** *"Is what I'm reading current — and do the labels hold up
against reality?"*

**First-time visitor feeling.** Surprise, then respect. Most products hide this
page. Finding a public usage check — observed next-day usage rates by
availability tier, with sample sizes — should feel like finding a restaurant
that posts its health inspections on the front door.

**Returning-user value.** Periodic reassurance, and ammunition: the link you
send someone who says "how do you know this thing isn't making it up?"

**Most visual emphasis.** Two artifacts: the freshness/update status (is the
data current right now) and the usage check (have the tiers matched
completed-game reality).

**Supporting context.** Coverage notes; plain-language description of the
update rhythm; a pointer to Methodology for the recipes.

**Never on this page.** Operator language — retries, fetches, pipelines,
job names. Accuracy or prediction framing of the usage check (it is a
consistency check, not a scorecard). Unbounded system detail; the page shows
health, not the machine room.

**Relationships.** Linked from every freshness stamp in the product; pairs with
Methodology (recipe ↔ inspection); linked from the footer everywhere.

**Twice as large?** A public change log of trust-relevant events ("data delayed
Tuesday morning; published view held at Monday"), and a plain-language history
of the usage check over time. Accountability as content.

**Half as large?** Freshness status and the usage check. That pair is the page.

**Finished looks like.** The page BaseballOS links proudly in its bio — and the
page that makes the "descriptive, trust-first" claim legible to someone who
has never read a line of the marketing.

---

### 3.10 About — the Sixty-Second Pitch

**Mission.** Tell a stranger what BaseballOS is, why it exists, and what it
refuses to be, in under a minute.

**The one question.** *"What is this, and can I trust it?"*

**First-time visitor feeling.** Clarity and character. The boundaries — no
picks, no predictions, no betting advice — should read as identity, not as
legal hedging. Stated once, confidently, and then the page moves on.

**Returning-user value.** Minimal by design; it is the page users send to other
people.

**Most visual emphasis.** The one-sentence identity, then the does/does-not
pairing.

**Never on this page.** Product data. Repeated disclaimers. A second tagline.
Anything a reader must scroll to trust.

**Relationships.** Linked from the footer and the front door's learning row;
exits to How to Read (learn the words), Methodology (see the recipes), and
Data & Trust (check the receipts). About is the cover letter for those three.

**Twice / half as large?** It should never be twice as large. Half as large is
probably the finished version: identity, boundaries, three links.

**Finished looks like.** Short enough that people actually read it; distinct
enough that they remember one line of it.

---

### 3.11 How to Read — the Glossary

**Mission.** Define every word BaseballOS uses, in one line each, from the one
canonical dictionary. This page is the product's contract that its vocabulary
is small, stable, and learnable.

**The one question.** *"What does this label mean?"*

**First-time visitor feeling.** Relief. The whole language fits on one page;
nothing requires a statistics degree; every term is one plain sentence.

**Returning-user value.** Rare direct visits, frequent arrivals via label
links: every term anywhere in the product should link here to its own entry.

**Most visual emphasis.** The definitions themselves, grouped by kind (team
states, arm availability, named reads, freshness labels).

**Never on this page.** Definitions that exist nowhere else in the product's
canonical dictionary. Duplicated or paraphrased entries. Methodology-depth
explanation (one line here; the recipe lives in Methodology).

**Relationships.** The glossary endpoint for every term-level "?" in the
product; siblings with About; sourced from the same dictionary Methodology
elaborates.

**Twice / half as large?** It grows only when the dictionary grows — which is a
deliberate product decision, never page filler. Halved, it keeps team states
and arm availability; those two vocabularies carry 80% of comprehension.

**Finished looks like.** A fan quotes a BaseballOS term in an argument, someone
asks what it means, and the answer is one link and one sentence.

---

### 3.12 Pages that should exist, change, or not exist

**Merge candidate: About + How to Read → "Start Here."** They serve the same
visitor at the same moment (first contact) and are both intentionally small.
A single Start Here page — identity, boundaries, then the glossary — would
serve newcomers better than two stops. Recommended as the eventual end state;
not urgent.

**Missing page (future): the Game page.** Once a reliable slate exists, a page
per game — both pens' state, both managers' realistic late-inning options,
factual watch points — is the most natural unit of fan attention BaseballOS
does not yet serve. It is the Compare lens anchored to a real event, and it is
the page most likely to be shared on game day. It must be built descriptive
(no winner, no lean) or not at all.

**Missing artifact (not a page): the shareable team card.** A canonical,
freshness-stamped snapshot of one team's bullpen state designed to be embedded
and screenshotted. It is an artifact of the Team Board, not a new destination,
and it is how BaseballOS travels to where fans already argue.

**Should not exist as public pages:** internal drafting or operator consoles of
any kind. Whatever internal tooling the product needs must live behind real
access control, invisible to the public product. The public page map is the
eleven pages above (trending toward ten with the Start Here merge, and toward
eleven again with Games).

---

## 4. Cross-Page Relationships

The product is a funnel with four altitudes:

    TODAY (the edition — daily entry)
      │  league curiosity            narrative appetite
      ▼                                   ▼
    DASHBOARD (league altitude)       STORIES (league, in words)
      │  one team                          │  one story's team
      ▼                                   ▼
    TEAM BOARD (team altitude)  ◄── COMPARE (two-team lens) ◄── [GAMES, future]
      │  one arm
      ▼
    PITCHER DETAIL (arm altitude — the receipts)

    Meta layer, reachable from everywhere, feeding nothing back:
    START HERE (About + glossary) · METHODOLOGY · DATA & TRUST
    Utility spoke: ALL PITCHERS → Pitcher Detail

Every page has a unique job (Section 3), and after the clarity work, no two
pages compete: Today teases the league, the Dashboard owns it; Stories narrates
the league, the Dashboard states it; Compare borrows two teams, the Team Board
owns each. The one structural watch item is Stories vs Today — both are
editorial voices, and they stay distinct only if Today remains strictly *one
lead plus tonight* while Stories remains *everything else*. The moment Today
grows a feed or Stories grows a headline slot, they collide.

What's missing is covered in 3.12: the Game page (eventually), and the
shareable artifact layer. Nothing else is missing; the temptation to add pages
should be treated as a temptation to dilute.

At a million monthly users this architecture holds, because it maps to how
attention actually arrives at that scale: most of it lands on team boards and
(eventually) game pages via shares and search — and both are built to be
landed on cold, carrying their own context, freshness, and receipts. The
edition serves the habitual core; the league pages serve the analytical few;
the meta pages serve the skeptical minority whose approval the whole product
borrows. Scale changes the traffic mix, not the map.

---

## 5. Information Hierarchy Across BaseballOS

One hierarchy governs every surface, top to bottom:

1. **The answer** — the state, in dictionary vocabulary, plainly stated.
2. **The why** — one or two sentences of plain baseball explaining it.
3. **The evidence** — the events: appearances, dates, pitches, rest.
4. **The freshness** — as-of date and update recency, in canonical words.
5. **The limitations** — what this read cannot see, stated without cringing.

Three rules bind it:

- **Nothing outranks its own answer.** Evidence never appears above the state
  it supports; freshness never dominates the read it stamps; chrome never
  outranks content.
- **Each layer is one gesture from the next.** Answer visible; why adjacent;
  evidence one click or one scroll; never further.
- **Emphasis is earned by answering, not by being numeric.** Numbers render in
  supporting weight unless the number IS the answer (a count of rested arms
  may lead; an index never does).

Across pages, the hierarchy also ranks the product's altitudes: the day's
answer (Today) over the league's (Dashboard) over a team's (Team Board) over
an arm's (Pitcher Detail) — matching how a reader's attention naturally
narrows.

---

## 6. Navigation Philosophy

Navigation should tell the product's story in its resting state: **Today,
League, Teams, Stories, then the trust spine (Methodology, Data & Trust)** —
read top to bottom, that list *is* the pitch: "every day, the whole league,
your team, the storylines — and here's why you can believe it."

Principles:

- **Six primary destinations, no more.** Support pages (Start Here) live in the
  footer and in contextual on-ramps, not the primary rail. A product about
  clarity cannot have a cluttered menu.
- **Labels are nouns from the product's own vocabulary.** No cleverness. A
  first-time visitor should predict each page's content from its label alone.
- **Deep links are first-class citizens.** Most future arrivals will not enter
  through navigation at all — they'll land mid-funnel from a share or a search.
  Every page must orient a cold visitor: whose page, what question, as of when,
  where to go up or down.
- **The funnel is the back button.** Every page exposes its upward altitude
  (arm → team → league → today) as a visible path, so exploration never
  strands anyone.
- **Freshness travels with navigation.** The ambient freshness signal lives in
  the persistent chrome, so no route change ever loses the answer to
  "as of when?"

---

## 7. What Makes BaseballOS Feel Cohesive

Cohesion is the sensation that every page was written by the same person on the
same day. Five threads create it:

1. **One voice.** Plain, confident, baseball-native declarative sentences.
   Never hype, never hedge-walls, never machine diction. The same voice writes
   a headline, an empty state, and a limitation.
2. **One dictionary.** The same term means the same thing with the same one-line
   definition everywhere — and no surface invents synonyms. Vocabulary drift is
   how products dissolve; the fixed dictionary is how this one doesn't.
3. **One contract.** State → Why → Evidence → Freshness → Limitations, on every
   claim-bearing surface, in that order, at every altitude. A reader who learns
   to read one BaseballOS card can read them all.
4. **One clock.** Freshness expressed in identical words and placement
   product-wide. Time-honesty repeated identically is a signature.
5. **One refusal.** Every page declines the same things — picks, predictions,
   rankings, verdicts — and the refusal is visible in structure, not just
   stated in policy: no page has a slot where a verdict could go.

Cohesion is also what's absent: no page has two voices, two summaries of the
same fact, or two ways of saying "as of." The clarity initiative earned this;
the vision's job is to keep it.

---

## 8. Long-Term Product Evolution

Identity is fixed; each phase deepens, never redefines. A page evolves
correctly if its one question never changes.

**Phase 1 — The Daily Edition matures.** Today becomes genuinely daily-edition
quality: a true lead story chosen with editorial confidence, tonight's slate
with per-game bullpen notes, and factual "since yesterday" movement built on
trusted day-over-day comparison. Dashboard gains full-coverage lanes and
factual movement annotations. Stories gains continuity threading. Team Board
gains its "since the last game" strip. Compare gains slate-pairing. Pitcher
Detail completes its evidence-first turn: the appearance log becomes the star
and the last naked index retires. Meta pages absorb the mature vocabulary.

**Phase 2 — The product learns who you are (without changing what it says).**
Follow-your-team arrives: Today greets the returning fan with their pen first;
the Team Board becomes a true home page with notification-worthy factual
changes ("two arms returned to Available today"); Stories filters to followed
teams. Personalization reorders — it never re-scores, never recommends, never
predicts. Every reader still sees the same facts; theirs simply come first.

**Phase 3 — The product travels.** Shareable, freshness-stamped team and game
cards carry BaseballOS into feeds and group chats with receipts attached; the
Game page ships as the shareable unit of game-day attention; a daily digest
delivers the edition to inboxes. Data & Trust grows its public accountability
log, because at travel-scale, trust becomes the product's most attacked and
most valuable surface. Nothing about the pages' questions changes — Phase 3 is
distribution of answers the product already knows how to give honestly.

Throughout all phases, three standing constraints: the dictionary grows only by
deliberate decision; no phase introduces a slot where a verdict could live; and
every new surface is born already carrying the five-layer contract.

---

## 9. Product Design Principles

1. **Answer first, data second.** Every surface leads with a sentence a fan
   could repeat aloud tonight.
2. **Receipts within one gesture.** No claim sits more than one click or scroll
   from the events that justify it.
3. **Say "we can't see that" in a full voice.** Limitations render with the
   same typographic confidence as findings. Honesty is not fine print.
4. **Small dictionary, spoken perfectly.** Fewer terms, defined once, used
   identically — comprehension over comprehensiveness.
5. **Baseball units or nothing.** Pitches, innings, appearances, rest days.
   If a value can't be expressed in units a dugout uses, it isn't public.
6. **Describe the past, illuminate tonight, never touch tomorrow.** The product
   ends its sentences before the next pitch is thrown.
7. **Never build a slot a verdict could fill.** Rankings, grades, picks, and
   leans are excluded structurally, not editorially.
8. **Empty is a valid answer.** Quiet days look quiet. Padding is a lie told
   with layout.
9. **Time is part of every truth.** No fact without its as-of; no page without
   its clock.
10. **One home per fact.** Tease, reference, or inherit — never restate.
11. **The skeptic is the design persona.** Every page must survive a hostile
    reader looking for the trick. There must be no trick to find.
12. **Boring beats clever wherever trust is at stake.** Predictable layouts,
    stable vocabulary, unchanging contracts — novelty budget is spent on
    insight, never on structure.

---

## 10. The Definition of "Finished"

BaseballOS is finished — as a product identity, not as a roadmap — when all of
the following are true:

**The habit test.** A meaningful population of fans opens Today unprompted
every afternoon, the way they check standings — and can retell the day's lead
read from memory.

**The citation test.** Writers and broadcasters reference BaseballOS reads by
name ("BaseballOS has them Stretched tonight") — and link to the team board,
because it's the credible source, not merely a convenient one.

**The stranger test.** A first-time visitor, landing cold on any page from a
share, understands within ten seconds whose page it is, what it claims, as of
when, and where the receipts are — without reading any help content.

**The skeptic test.** A hostile reader who tours Methodology and Data & Trust
intending to write a debunking finds the recipe, the inspection, and the
limitations already published — and has nothing left to expose.

**The vocabulary test.** The product's terms escape the product: fans use
"Clean Options" and "Stretched" in arguments the way they use "quality start"
— words that carry their definitions with them.

**The refusal test.** After meaningful scale, no reasonable person can describe
BaseballOS as a picks product, a model, or a ranking site — because there is
literally nowhere on any page where such an output could appear.

**The single-glance test.** Each page answers its one question within one
glance for a fluent user: Today's story, the league's shape, a team's night, an
arm's week — each in seconds, each with receipts one gesture away.

**The stewardship test.** New surfaces and phases get built by people who never
met the original product — and come out sounding like it, because this
document, the dictionary, and the five-layer contract made the identity
inheritable.

Finished, for BaseballOS, does not mean no more work. It means the product has
become what it set out to be — the clearest trusted public explanation layer
for MLB bullpen state — and every future phase makes it deeper without making
it different.
