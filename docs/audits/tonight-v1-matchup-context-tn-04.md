# Tonight v1 matchup context sentence (TN-04)

Status: every tonight_v1 game card carries one short, descriptive,
backend-authored `context.sentence`. It is authored at build/publication time
from the two frozen TeamSides only. It is stored with the publication and
re-presented at serve time for the current game state. The default Tonight
response is still legacy `tonight_v5`, and the frontend is unchanged (TN-08).

## Authority

`tonight_read_model.build_matchup_context(away, home)` is pure. It reads only
the two TeamSide dicts already in the payload: Team State receipt, frozen rest
carrier, frozen 3-in-4 count, and frozen rotation. It does no database access
and no baseball derivation, and it reads no GameLog, FatigueScore or current
availability. There is no model, score or LLM. The TN-03 schedule overlay never
changes these facts; it only changes how the stored sentence is presented.

## Priority (first match wins; one reason; never concatenated)

Sides are always named away first, then home, using the TeamSide abbreviation.

| # | reason_code | Condition (frozen facts only) | Template |
| --- | --- | --- | --- |
| 1 | `team_state_vulnerable` | a side's available Team State is Vulnerable | `SEA enters tonight with a Vulnerable bullpen state, while HOU is Stretched.` / `SEA and HOU both enter tonight with Vulnerable bullpen states.` |
| 2 | `back_to_back_pressure` | available `rest.back_to_back_count >= 2` | `SEA has 3 bullpen arms coming off back-to-back usage.` / `…; HOU has 4.` |
| 3 | `three_in_four_pressure` | known `multi_day_usage.three_in_four_count >= 1` | `HOU has 1 reliever carrying a 3-in-4 workload pattern.` / `…; HOU has 3.` |
| 4 | `short_start_transfer` | `rotation.short_start_count >= 1` (status complete or partial) | `SEA's bullpen has absorbed 2 short starts in the recent rotation window.` |
| 5 | `team_state_contrast` | both Team States available and different | `SEA is Fresh entering tonight; HOU is Stretched.` |
| 6 | `rested_arm_snapshot` | both rest carriers available | `SEA has 6 rested bullpen arms; HOU has 1.` |

Other rules:

- If the opponent's Team State is unavailable, the Vulnerable line drops its
  "while …" clause.
- Singular and plural are handled: 1 reliever, 1 short start, 1 rested
  bullpen arm.
- `bullpen_innings` is not used.
- The contrast line states both labels and implies no advantage.

## Evidence rules

- A fact is used only when its TeamSide marks it available:
  - Team State needs `available: true` and a public label.
  - Rest needs `rest.available: true` and integer counts.
  - 3-in-4 needs a non-null integer count.
  - Rotation must be non-null.
- `None` is never read as zero.
- A side whose package is unavailable contributes nothing.

## `context.evidence_state`

This reuses the TN-01 `complete` / `withheld` vocabulary and adds `partial` and
`unavailable`.

| Value | Meaning |
| --- | --- |
| `complete` | A sentence; every fact read by it and by the higher-priority checks was available. |
| `partial` | A sentence, but either it uses a partial rotation fact, or an input of the selected or a higher-priority check was withheld on a side. The line is true, but it may not be the top condition. |
| `withheld` | No sentence. Some usable fact exists, but the facts a sentence needs were withheld. |
| `unavailable` | No sentence, and no usable fact on either side. |

With no sentence, `sentence` is `null` and `reason_codes` is `[]`. There is no
filler.

## Copy guard

- `CONTEXT_BANNED_TERMS`, scanned with the shared
  `editorial_voice_contract_v1.find_editorial_violations`, including plural
  variants: advantage, edge, favored, favorite, better spot, worse spot,
  should win, likely to win, likely, will, should, trouble, danger, exploit,
  target, fade, bet, betting, fantasy, pick, prediction, gassed, tired,
  exhausted.
- Every template also passes the shared default editorial list.
- Length: at most `CONTEXT_SENTENCE_MAX_CHARS = 160` characters and at most
  35 words. One sentence.

## Game-state presentation (`present_matchup_context`)

The build step applies this presentation to each game's state. Serving applies
it again inside the TN-03 overlay whenever the served state changes. It is pure
and idempotent, and it never changes `evidence_state`.

| Served state | Sentence | Marker appended to `reason_codes` |
| --- | --- | --- |
| scheduled, uncertain | shown unchanged | none |
| live | shown | `pregame_context` |
| final, postponed, suspended | hidden (`null`) | `pregame_context_hidden` |

A game already final, postponed or suspended at build time is stored with its
sentence hidden, so it is never shown later. There is no new field and no
migration.

## Stored vs served, ETag, queries

- `tonight_publications` rows are never updated.
- The served context is computed on a copy.
- When the served state changes the presentation, the TN-03 overlay identity
  entry carries the context marker. The composite ETag therefore changes for
  scheduled → live (pregame marker) and for live → final (sentence hidden).
  There is no second ETag system.
- An unchanged state keeps the served body equal to the stored body, so the
  ETag stays equal to `content_sha256`.
- Serving still issues 3 statements (0 on an off-day for schedule), with no
  GameLog or FatigueScore reads and no writes.
- The top-level summary is unchanged.

## Compatibility

- A tonight_v1 row built before TN-04 keeps its original empty context.
- Rebuilding that same publication identity would now produce different
  content, and TN-01 refuses that as a conflict. In production this shows up
  as a non-fatal, logged generation failure; the stored row stays served.
- New publications carry sentences.

## Verification

- `backend/tests/test_tonight_v1_read_model.py` covers:
  - every template (including singular and plural), the priority ladder, and
    no concatenation;
  - withheld and unknown facts never read as zero;
  - null rotation and partial rotation;
  - null context with `unavailable` evidence;
  - away/home ordering and the banned-language guard;
  - presentation by state and idempotence;
  - parity with the fixture's real frozen TeamSides;
  - a production-shaped Vulnerable matchup.
- `backend/tests/test_tonight_v1_serving.py` covers the served sentence per
  state, stored bytes unchanged, a distinct ETag per presentation, and at most
  3 queries with no reads of either table and no writes.
- `backend/tests/test_trusted_publication_rehearsal.py` has the rehearsal
  matchup store `three_in_four_pressure`. It checks the sentence is visible
  when scheduled, marked `pregame_context` when live and hidden when final,
  and that the stored row is unchanged.
