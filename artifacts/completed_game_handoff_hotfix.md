# Completed-Game Handoff Trust Hotfix Review

Read-only focused excerpt from the current stored Today's Story / completed-game review export.

## Export Metadata

```json
{
  "completed_game_context_rows_reviewed": 26,
  "completed_game_fallback_or_unpublishable_rows": 4,
  "completed_game_publishable_stories": 22,
  "completed_game_rendered_drafts": 60,
  "generated_at": "2026-06-30T12:32:58.928712",
  "generation_path_used": [
    "services.todays_story_editorial_review.build_todays_story_editorial_review",
    "services.intelligence_surface_service.build_today_lead_story",
    "services.coin_story_inspection.inspect_team_story",
    "story_writers::{TeamStoryWriter, DashboardStoryWriter, MorningBriefWriter}"
  ],
  "reference_date": "2026-06-29",
  "source_mode": "current stored DB data only; exporter starts no sync"
}
```

## Scan Results

- Editorial banned-language scan: pass - no banned language violations found.
- Retired phrase scan: pass - no retired phrase violations found.
- Impossible innings scan: pass - no impossible innings notation violations found.

## White Sox / Sean Burke Row

```json
{
  "team_id": 145,
  "game_pk": 824822,
  "game_date": "2026-06-29",
  "bullpen_story_tag": "bullpen_kept_team_alive",
  "confidence": "HIGH",
  "starter_name": "Sean Burke",
  "starter_ip": 5.33333333333333,
  "starter_pitch_count": 89,
  "starter_exit_inning": 6,
  "starter_exit_score_for": 2,
  "starter_exit_score_against": 2,
  "bullpen_entry_inning": 6,
  "bullpen_entry_score_for": 2,
  "bullpen_entry_score_against": 2,
  "lead_when_bullpen_entered": null,
  "deficit_when_bullpen_entered": null,
  "largest_deficit": 1,
  "largest_lead": 6,
  "late_runs_allowed": 0
}
```

## Homepage Draft: team_story

Headline:

```text
Bullpen kept it alive
```

Body:

```text
After their most recent game, Sean Burke's 5.1 innings handed the bullpen a tied game, and the relievers held the line from there. The offense finished the rally. That leaves the late innings with more than one route through a tight game.
```

What BaseballOS noticed / observations:

```text
- The starter set the bullpen up to finish the game.
- The offense finished the comeback the bullpen kept alive.
- One late inning swung the game.
```

Evidence:

```text
- Starter: Sean Burke, 5.1 IP, 89 pitches
- Largest deficit: 1
- Bullpen entered in the 6th with the score tied
- Turning point: 3rd inning
- Late runs allowed: 0
```
Exact rendered text:

```text
Bullpen kept it alive

After their most recent game, Sean Burke's 5.1 innings handed the bullpen a tied game, and the relievers held the line from there. The offense finished the rally. That leaves the late innings with more than one route through a tight game.

Why BaseballOS sees it:
- The starter set the bullpen up to finish the game.
- The offense finished the comeback the bullpen kept alive.
- One late inning swung the game.

Evidence:
- Starter: Sean Burke, 5.1 IP, 89 pitches
- Largest deficit: 1
- Bullpen entered in the 6th with the score tied
- Turning point: 3rd inning
- Late runs allowed: 0
```

## Homepage Draft: dashboard

Headline:

```text
Relievers left room for the rally
```

Body:

```text
The club kept the comeback alive.
```

Evidence:

```text
- Starter: Sean Burke, 5.1 IP, 89 pitches
```

## Homepage Draft: morning_brief

Headline:

```text
Bullpen note: Bullpen gave the comeback room
```

Body:

```text
After their most recent game, the club broke through after the bullpen held a tied game. Available arms: Erick Fedde. That gives the bullpen more ways to cover the late innings.
```

Evidence:

```text
- Starter: Sean Burke, 5.1 IP, 89 pitches
- Largest deficit: 1
- Bullpen entered in the 6th with the score tied
- Turning point: 3rd inning
- Late runs allowed: 0
```
