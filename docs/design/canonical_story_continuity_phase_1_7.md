# Canonical Story Continuity — Phase 1.7 (June 2026)

**Companion docs:** `story_coverage_audit_june_2026.md`, `positive_depth_story_beat_phase_1_5.md`, `quiet_day_strategy_phase_1_6.md`
**Scope:** Backend-only. No frontend changes. No legacy story engine removed. No UI migrated (Home, Stories, Team Board untouched).

---

## What changed

Each canonical story item (and the league context) now carries **`continuity`** metadata so a future Home UI can show whether a story is new, ongoing, changed, unchanged, resolved, or unavailable — **without running client-side story generation**.

| File | Change |
|---|---|
| `services/story_feed.py` | Added `build_story_continuity`, `_league_continuity`, continuity-state constants. Each feed item gets `continuity`; `build_league_context` gets a `continuity`. `build_canonical_story_feed` accepts `prior_stories` and `prior_league_context`. |
| `api/bullpen.py` | Hoisted the prior-snapshot fetch (now shared by continuity and "what changed"), added `_canonical_prior_story_items` / `_canonical_prior_league_context`, and passes the prior canonical stories + league context into the feed. |

This **reuses existing infrastructure** (the dashboard snapshot history, which already stores prior canonical feeds since Phase 1) rather than building a second continuity engine. The legacy flagship `story_continuity.py` is untouched; it keys to a flagship signature, whereas canonical continuity keys to canonical **story identity** (per the requirement).

---

## How prior context is determined

- The dashboard already fetches the latest prior snapshot (for "what changed"). That fetch is hoisted so it runs once and feeds both surfaces.
- `prior_stories` = the prior snapshot's `payload['stories']['items']` (the canonical feed from the previous day). `prior_league_context` = the prior `payload['stories']['league_context']`.
- Continuity compares today's canonical story to the prior story **for the same team** (matched by `team_id`; `story_id` is `team_id:date`, stable by team/date).
- If the prior snapshot predates the canonical feed (no `stories` key) or none exists, `prior_stories` is empty and continuity falls back to a truthful "no prior story" read (`compared: false`). As post‑Phase‑1 snapshots accumulate, continuity becomes meaningful.

**Prose independence:** the core state depends only on **structured fields** — `story_type` and whether the story published — so it does not flip on prose rewording. The `unchanged` vs `ongoing` split uses the deterministic, engine-authored `headline` as a secondary signal only.

---

## Continuity contract

Per story item — `stories.items[].continuity`:

```jsonc
{
  "state": "ongoing",                  // new | ongoing | changed | unchanged | resolved | unavailable
  "reason": "story_type_persisted",    // finer reason code (see states)
  "previous_story_id": "137:2026-06-21",
  "previous_story_type": "coverage_pressure",
  "previous_headline": "…prior headline…",
  "changed_since": "2026-06-21",       // prior story's date (comparison baseline)
  "compared": true,                    // whether a prior canonical story existed for this team
  "evidence": {
    "today_publishable": true,
    "prior_publishable": true,
    "prior_present": true,
    "story_type_changed": false
  }
}
```

League context — `stories.league_context.continuity`:

```jsonc
{ "state": "unchanged", "reason": "league_mode_persisted", "previous_mode": "broadly_stable", "changed_since": "2026-06-21" }
```

### Supported states

| State | When | Reason codes |
|---|---|---|
| `new` | publishable today, no publishable prior | `no_prior_canonical_story`, `prior_story_was_suppressed` |
| `ongoing` | publishable today and prior, same `story_type`, headline moved | `story_type_persisted` |
| `unchanged` | publishable today and prior, same `story_type` and same headline | `story_unchanged` |
| `changed` | publishable today and prior, different `story_type` | `story_type_changed` |
| `resolved` | suppressed today, but prior **was** publishable | `prior_story_no_longer_publishes` |
| `unavailable` | suppressed today, no publishable prior | `no_publishable_story_today`, `no_prior_canonical_story` |

A suppressed/neutral story always lands in `resolved` or `unavailable` — it never claims a story continued when it was suppressed.

---

## Tests

`tests/test_story_feed.py` (`TestStoryContinuity`): new (no prior / prior suppressed), ongoing, unchanged, changed, resolved, unavailable (both suppressed / no prior), suppressed-never-claims-continuation, determinism, and feed-level continuity (new without prior, ongoing with prior, resolved when suppressed) plus league-context continuity. `tests/test_bullpen_dashboard.py` asserts every canonical item and the league context carry a continuity `state`. Legacy fields remain asserted present; frontend is untouched.

---

## Limitations

- **Single-day baseline.** Continuity compares against the **immediate** prior snapshot only (not a multi-day chain), so `ongoing`/`unchanged` mean "vs the previous snapshot," and `changed_since` is the prior snapshot's date — not a first-seen date. A multi-day streak count is a possible future enhancement.
- **Bootstrapping.** Until post‑Phase‑1 snapshots exist for consecutive days, continuity reports `new`/`unavailable` with `compared: false`. This is honest, not a bug.
- **Per-team identity.** Continuity matches by `team_id` (consistent with `story_id`). It does not attempt cross-team or league-note continuity beyond the single league `mode` comparison.

---

## Relationship to Home migration

This closes the **last Home-specific blocker** from the coverage audit. Home can now render new/ongoing/returning-style continuity badges directly from `stories.items[].continuity` (and a league continuity from `stories.league_context.continuity`) — sourced from the backend, with no client-side story generation.

Combined with Phase 1.5 (positive depth/rest beat) and Phase 1.6 (quiet-day/league context), the canonical feed now supplies everything Home needs: **team stories, positive stories, a quiet-day/league fallback, and continuity**. 

**Next: Phase 2 — Home migration** (behind a feature flag), rendering `stories` for the hero, "Three Things To Watch," the feed, the league/quiet read, and continuity badges, with the legacy client path as fallback. Optional polish: wire a real day-over-day `availability_trend` into the league signal; add a multi-day continuity streak count.
