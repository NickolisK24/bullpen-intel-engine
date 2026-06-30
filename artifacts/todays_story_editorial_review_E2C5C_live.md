# Today's Story Editorial Review Corpus - E2C-5C Live

Read-only export of the current stored homepage-visible Today's Story / completed-game story writer path after the final E2C-5C polish pass.

## Export Metadata

```json
{
  "artifact": "artifacts/todays_story_editorial_review_E2C5C_live.md",
  "completed_game_context_rows_reviewed": 0,
  "completed_game_fallback_or_unpublishable_rows": 0,
  "completed_game_publishable_stories": 0,
  "completed_game_rendered_drafts": 0,
  "generated_at": "2026-06-30T00:39:07.044394",
  "generation_path_used": [
    "services.todays_story_editorial_review.build_todays_story_editorial_review",
    "services.intelligence_surface_service.build_today_lead_story",
    "services.coin_story_inspection.inspect_team_story",
    "story_writers::{TeamStoryWriter, DashboardStoryWriter, MorningBriefWriter}"
  ],
  "homepage_candidates_considered": 0,
  "homepage_empty_reason": "no_completed_game_contexts",
  "homepage_errors": 0,
  "homepage_publishable_candidates": 0,
  "homepage_status": "empty",
  "live_data_error": "ProgrammingError: (psycopg2.errors.UndefinedTable) relation \"completed_game_contexts\" does not exist",
  "primary_story_distribution": {},
  "reference_date": null,
  "snapshot_present_for_reference_date": false,
  "source_mode": "current stored DB data only; no sync started"
}
```

## Editorial Banned-Language Scan

Status: pass - no banned language violations found.

## Impossible Innings Scan

Status: pass - no impossible innings notation violations found.

## Headline Reuse Summary

```json
{
  "headline_counts": {},
  "max_reuse_count": 0,
  "reused_headlines": {}
}
```

## Same-Beat Repetition / Swap-Test Summary

```json
{
  "beat_summaries": {},
  "duplicate_groups": [],
  "scope": "publishable team_story completed-game bodies, stripped names/numbers",
  "status": "pass"
}
```

## Homepage Lead Story

No homepage lead story rendered.

## Completed-Game Story Corpus

This section contains 0 current stored completed-game contexts for an unresolved reference date. Each row was rendered through inspect_team_story with the existing writer targets only.
