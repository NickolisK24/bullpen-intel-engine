# Today's Story Editorial Review Corpus - E2C-5A

Read-only export of the current homepage-visible Today's Story / completed-game story writer path before any migration of that surface.

## Export Metadata

```json
{
  "artifact": "artifacts/todays_story_editorial_review_E2C5A.md",
  "banned_language_scan_scope": "rendered public draft text only",
  "banned_language_violation_count": 0,
  "completed_game_context_rows_for_reference_date": 30,
  "completed_game_fallback_or_unpublishable_rows": 5,
  "completed_game_publishable_stories": 25,
  "completed_game_rendered_drafts": 65,
  "context_generated_at_max": "2026-06-29T03:03:18.964258",
  "context_generated_at_min": "2026-06-28T20:08:19.302262",
  "generation_path_used": [
    "backend/services/intelligence_surface_snapshot.py::serve_today_lead_story(persist=False)",
    "backend/services/intelligence_surface_service.py::build_today_lead_story",
    "backend/services/coin_story_inspection.py::inspect_team_story",
    "backend/story_writers::{TeamStoryWriter, DashboardStoryWriter, MorningBriefWriter}"
  ],
  "homepage_candidates_considered": 2,
  "homepage_empty_reason": null,
  "homepage_errors": 0,
  "homepage_fallback_used": false,
  "homepage_publishable_candidates": 2,
  "homepage_response_status": "ok",
  "notes": [
    "No examples were synthesized or seeded.",
    "Runtime package generated_at values from live inspection are omitted so this artifact stays stable when the stored data and code are unchanged.",
    "This surface renders headline, body, Why BaseballOS sees it, and Evidence sections. It does not currently render explicit What everyone saw, What BaseballOS noticed, Why it matters, or Why it matters tomorrow headings in these writer drafts."
  ],
  "primary_story_distribution": {
    "bullpen_kept_team_alive": 2,
    "bullpen_overexposed": 6,
    "insufficient_context": 5,
    "lost_game_shape": 3,
    "protected_game_shape": 10,
    "starter_covered_bullpen": 4
  },
  "reference_date": "2026-06-28",
  "required_bounded_audit_output": "%TEMP%/baseballos-todays-story-review.json",
  "snapshot_present_for_reference_date": true,
  "source_mode": "current stored DB data plus current intelligence surface snapshot when present",
  "writer_distribution": {
    "dashboard": 25,
    "morning_brief": 15,
    "team_story": 25
  }
}
```

## Editorial Banned-Language Scan

Status: pass - no editorial_voice_contract_v1 banned or discouraged language was found in rendered public draft text.

## Homepage Lead Story

Team: Tampa Bay Rays (TB, 139)
Game PK: 822959

### Lead Metadata

```json
{
  "beat": "protected_game_shape",
  "fallback_used": false,
  "selection": {
    "confidence": "HIGH",
    "game_importance": "HIGH",
    "late_runs_allowed": 1,
    "primary_story": "protected_game_shape",
    "rank": 1,
    "reason": "high_priority_narrative",
    "story_priority": "HIGH",
    "swing": 5
  },
  "severity": "HIGH",
  "source_path": "serve_today_lead_story -> stored snapshot response",
  "story_type": "protected_game_shape",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 2,
      "context_available": true,
      "limited_arms_count": 4,
      "monitor_arms_count": 2,
      "optionality_band": "narrow",
      "restricted_arms_count": 5,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [
        {
          "availability": "Available",
          "last_workload": "2 days ago",
          "name": "Cam Booser",
          "player_id": 592155,
          "recent_workload": "light"
        },
        {
          "availability": "Available",
          "last_workload": "3 days ago",
          "name": "Ian Seymour",
          "player_id": 693855,
          "recent_workload": "moderate"
        }
      ],
      "clean_options_count": 2,
      "context_available": true,
      "core_retention_count": 0,
      "depth_pressure_band": "heavy",
      "inactive_bullpen_arms_count": 14,
      "optionality_band": "narrow",
      "practical_close_game_paths_count": 3,
      "secondary_options": [
        {
          "availability": "Monitor",
          "name": "Bryan Baker",
          "player_id": 641329,
          "reason": "2 appearances in 5 days"
        },
        {
          "availability": "Monitor",
          "name": "Trevor Martin",
          "player_id": 694680,
          "reason": "No rest since last appearance"
        }
      ],
      "secondary_options_count": 2,
      "stability_band": "rebuilding"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 7,
      "bullpen_story_tag": "protected_game_shape",
      "comeback_completed": false,
      "confidence": "HIGH",
      "deficit_when_bullpen_entered": null,
      "final_score_against": 1,
      "final_score_for": 5,
      "game_date": "2026-06-28",
      "game_pk": 822959,
      "game_shape_created": "normal_start",
      "game_shape_protected": true,
      "generated_at": "2026-06-28T20:08:19.302262",
      "home_away": "home",
      "largest_deficit": 0,
      "largest_lead": 5,
      "late_runs_allowed": 1,
      "lead_lost": false,
      "lead_protected": true,
      "lead_when_bullpen_entered": 5,
      "opponent_name": "Arizona Diamondbacks",
      "runs_allowed_innings_7_to_9": 1,
      "starter_exit_inning": 6,
      "starter_ip": 6.0,
      "starter_name": "Drew Rasmussen",
      "starter_pitch_count": 99,
      "team_id": 139,
      "turning_inning": null
    },
    "confidence": "HIGH",
    "game_importance": "HIGH",
    "headline_key": "protected_game_shape",
    "primary_story": "protected_game_shape",
    "publish_reason": "high_priority_narrative",
    "publishable": true,
    "recommended_surface": "multiple",
    "safe_time_context": "AFTER_MOST_RECENT_GAME",
    "secondary_story": null,
    "story_priority": "HIGH",
    "summary_key": "game_shape_protected",
    "supporting_facts": {
      "bullpen_entry_inning": 7,
      "bullpen_entry_score_against": 0,
      "bullpen_entry_score_for": 5,
      "game_shape_created": "normal_start",
      "game_shape_protected": true,
      "largest_deficit": 0,
      "largest_lead": 5,
      "late_runs_allowed": 1,
      "lead_lost": false,
      "lead_protected": true,
      "runs_allowed_innings_7_to_9": 1,
      "starter_exit_score_against": 0,
      "starter_exit_score_for": 4
    },
    "supporting_observations": [
      "starter_created_game_shape",
      "deep_start",
      "lead_entering_bullpen",
      "bullpen_preserved_lead",
      "late_runs_allowed"
    ],
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": 4.3,
      "bullpen_workload_appearances_10d": 29,
      "bullpen_workload_total_10d": 484,
      "concentration_band": "balanced",
      "context_available": true,
      "early_bullpen_entry_rate": 36.4,
      "top_three_workload_share_10d": 45.9,
      "window_days": 10
    }
  }
}
```

### Homepage Draft: team_story

Headline:
```
Lead protected
```
Opening:
```
After their most recent game, Drew Rasmussen worked six innings and left with a five-run lead, and the bullpen brought it home.
```
Body:
```
After their most recent game, Drew Rasmussen worked six innings and left with a five-run lead, and the bullpen brought it home. The clean finish keeps the relief corps down to a short list of clean arms.
```
What BaseballOS noticed / observations:
```
- The starter went deep and set the bullpen up to finish the game.
- The bullpen took over with a lead in hand.
- The relievers held the lead.
- The damage came after the starter exited.
```
Evidence:
```
- Starter: Drew Rasmussen, 6.0 IP, 99 pitches
- Largest lead: 5
- Bullpen entered in the 7th with a 5-run lead
- Late runs allowed: 1
- Clean options: Cam Booser, Ian Seymour
```
Exact rendered text:
```
Lead protected

After their most recent game, Drew Rasmussen worked six innings and left with a five-run lead, and the bullpen brought it home. The clean finish keeps the relief corps down to a short list of clean arms.

Why BaseballOS sees it:
- The starter went deep and set the bullpen up to finish the game.
- The bullpen took over with a lead in hand.
- The relievers held the lead.
- The damage came after the starter exited.

Evidence:
- Starter: Drew Rasmussen, 6.0 IP, 99 pitches
- Largest lead: 5
- Bullpen entered in the 7th with a 5-run lead
- Late runs allowed: 1
- Clean options: Cam Booser, Ian Seymour
```

### Homepage Draft: dashboard

Headline:
```
Lead protected
```
Opening:
```
The club protected a 5-run lead.
```
Body:
```
The club protected a 5-run lead.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Drew Rasmussen, 6.0 IP, 99 pitches
```
Exact rendered text:
```
Lead protected

The club protected a 5-run lead.

Evidence:
- Starter: Drew Rasmussen, 6.0 IP, 99 pitches
```

### Homepage Draft: morning_brief

Headline:
```
Bullpen note: Lead protected
```
Opening:
```
After their most recent game, the club turned a five-run lead into a win the bullpen never let slip.
```
Body:
```
After their most recent game, the club turned a five-run lead into a win the bullpen never let slip. Available arms: Cam Booser, Ian Seymour. The relief corps is down to a short list of clean arms.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Drew Rasmussen, 6.0 IP, 99 pitches
- Largest lead: 5
- Bullpen entered in the 7th with a 5-run lead
- Late runs allowed: 1
- Clean options: Cam Booser, Ian Seymour
```
Exact rendered text:
```
Bullpen note: Lead protected

After their most recent game, the club turned a five-run lead into a win the bullpen never let slip. Available arms: Cam Booser, Ian Seymour. The relief corps is down to a short list of clean arms.

Evidence:
- Starter: Drew Rasmussen, 6.0 IP, 99 pitches
- Largest lead: 5
- Bullpen entered in the 7th with a 5-run lead
- Late runs allowed: 1
- Clean options: Cam Booser, Ian Seymour
```

## Completed-Game Story Corpus

This section contains 30 current stored completed-game contexts for 2026-06-28. Each row was rendered through inspect_team_story with the existing writer targets only.

## Completed-Game Story 1: Los Angeles Angels (LAA, 108)

### Story Metadata

```json
{
  "beat": "protected_game_shape",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_used": false,
  "game_date": "2026-06-28",
  "game_importance": "HIGH",
  "game_pk": 824011,
  "opponent_name": "Athletics",
  "publish_reason": "high_priority_narrative",
  "publishable": true,
  "recommended_surface": "multiple",
  "severity": "HIGH",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_type": "protected_game_shape",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 2,
      "context_available": true,
      "limited_arms_count": 4,
      "monitor_arms_count": 2,
      "optionality_band": "narrow",
      "restricted_arms_count": 5,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [
        {
          "availability": "Available",
          "last_workload": "4 days ago",
          "name": "Mitch Farris",
          "player_id": 815083,
          "recent_workload": "moderate"
        },
        {
          "availability": "Available",
          "last_workload": "5 days ago",
          "name": "Ryan Johnson",
          "player_id": 696270,
          "recent_workload": "none"
        }
      ],
      "clean_options_count": 2,
      "context_available": true,
      "core_retention_count": 1,
      "depth_pressure_band": "heavy",
      "inactive_bullpen_arms_count": 7,
      "optionality_band": "narrow",
      "practical_close_game_paths_count": 3,
      "secondary_options": [
        {
          "availability": "Monitor",
          "name": "Chase Silseth",
          "player_id": 681217,
          "reason": "2 appearances in 5 days"
        },
        {
          "availability": "Monitor",
          "name": "Samy Natera Jr.",
          "player_id": 696519,
          "reason": "2 appearances in 5 days"
        }
      ],
      "secondary_options_count": 2,
      "stability_band": "transitioning"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 6,
      "bullpen_story_tag": "protected_game_shape",
      "comeback_completed": false,
      "confidence": "HIGH",
      "deficit_when_bullpen_entered": null,
      "final_score_against": 1,
      "final_score_for": 4,
      "game_date": "2026-06-28",
      "game_pk": 824011,
      "game_shape_created": "normal_start",
      "game_shape_protected": true,
      "generated_at": "2026-06-28T22:47:36.618823",
      "home_away": "home",
      "largest_deficit": 0,
      "largest_lead": 4,
      "late_runs_allowed": 0,
      "lead_lost": false,
      "lead_protected": true,
      "lead_when_bullpen_entered": 3,
      "opponent_name": "Athletics",
      "runs_allowed_innings_7_to_9": 0,
      "starter_exit_inning": 5,
      "starter_ip": 5.0,
      "starter_name": "Sam Aldegheri",
      "starter_pitch_count": 81,
      "team_id": 108,
      "turning_inning": null
    },
    "confidence": "HIGH",
    "game_importance": "HIGH",
    "headline_key": "bullpen_stabilized",
    "primary_story": "protected_game_shape",
    "publish_reason": "high_priority_narrative",
    "publishable": true,
    "recommended_surface": "multiple",
    "safe_time_context": "AFTER_MOST_RECENT_GAME",
    "secondary_story": null,
    "story_priority": "HIGH",
    "summary_key": "game_shape_protected",
    "supporting_facts": {
      "bullpen_entry_inning": 6,
      "bullpen_entry_score_against": 1,
      "bullpen_entry_score_for": 4,
      "game_shape_created": "normal_start",
      "game_shape_protected": true,
      "largest_deficit": 0,
      "largest_lead": 4,
      "late_runs_allowed": 0,
      "lead_lost": false,
      "lead_protected": true,
      "runs_allowed_innings_7_to_9": 0,
      "starter_exit_score_against": 1,
      "starter_exit_score_for": 4
    },
    "supporting_observations": [
      "starter_created_game_shape",
      "lead_entering_bullpen",
      "bullpen_preserved_lead"
    ],
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": 4.4,
      "bullpen_workload_appearances_10d": 33,
      "bullpen_workload_total_10d": 643,
      "concentration_band": "balanced",
      "context_available": true,
      "early_bullpen_entry_rate": 46.2,
      "top_three_workload_share_10d": 44.5,
      "window_days": 10
    }
  },
  "team_id": 108,
  "writer_targets": [
    "team_story",
    "dashboard",
    "morning_brief"
  ]
}
```

### Draft: team_story

Headline:
```
Bullpen slammed the door
```
Opening:
```
After their most recent game, Sam Aldegheri worked five innings and left with a four-run lead, and the bullpen brought it home.
```
Body:
```
After their most recent game, Sam Aldegheri worked five innings and left with a four-run lead, and the bullpen brought it home. The clean finish keeps the relief corps down to a short list of clean arms.
```
What BaseballOS noticed / observations:
```
- The starter set the bullpen up to finish the game.
- The bullpen took over with a lead in hand.
- The relievers held the lead.
```
Evidence:
```
- Starter: Sam Aldegheri, 5.0 IP, 81 pitches
- Largest lead: 4
- Bullpen entered in the 6th with a 3-run lead
- Late runs allowed: 0
- Clean options: Mitch Farris, Ryan Johnson
```
Exact rendered text:
```
Bullpen slammed the door

After their most recent game, Sam Aldegheri worked five innings and left with a four-run lead, and the bullpen brought it home. The clean finish keeps the relief corps down to a short list of clean arms.

Why BaseballOS sees it:
- The starter set the bullpen up to finish the game.
- The bullpen took over with a lead in hand.
- The relievers held the lead.

Evidence:
- Starter: Sam Aldegheri, 5.0 IP, 81 pitches
- Largest lead: 4
- Bullpen entered in the 6th with a 3-run lead
- Late runs allowed: 0
- Clean options: Mitch Farris, Ryan Johnson
```


### Draft: dashboard

Headline:
```
Bullpen slammed the door
```
Opening:
```
The club protected a 4-run lead.
```
Body:
```
The club protected a 4-run lead.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Sam Aldegheri, 5.0 IP, 81 pitches
```
Exact rendered text:
```
Bullpen slammed the door

The club protected a 4-run lead.

Evidence:
- Starter: Sam Aldegheri, 5.0 IP, 81 pitches
```


### Draft: morning_brief

Headline:
```
Bullpen note: Bullpen slammed the door
```
Opening:
```
After their most recent game, the club turned a four-run lead into a win the bullpen never let slip.
```
Body:
```
After their most recent game, the club turned a four-run lead into a win the bullpen never let slip. Available arms: Mitch Farris, Ryan Johnson. The relief corps is down to a short list of clean arms.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Sam Aldegheri, 5.0 IP, 81 pitches
- Largest lead: 4
- Bullpen entered in the 6th with a 3-run lead
- Late runs allowed: 0
- Clean options: Mitch Farris, Ryan Johnson
```
Exact rendered text:
```
Bullpen note: Bullpen slammed the door

After their most recent game, the club turned a four-run lead into a win the bullpen never let slip. Available arms: Mitch Farris, Ryan Johnson. The relief corps is down to a short list of clean arms.

Evidence:
- Starter: Sam Aldegheri, 5.0 IP, 81 pitches
- Largest lead: 4
- Bullpen entered in the 6th with a 3-run lead
- Late runs allowed: 0
- Clean options: Mitch Farris, Ryan Johnson
```

## Completed-Game Story 2: Arizona Diamondbacks (AZ, 109)

### Story Metadata

```json
{
  "beat": "starter_covered_bullpen",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_used": false,
  "game_date": "2026-06-28",
  "game_importance": "LOW",
  "game_pk": 822959,
  "opponent_name": "Tampa Bay Rays",
  "publish_reason": "meets_confidence_threshold",
  "publishable": true,
  "recommended_surface": "dashboard",
  "severity": "MEDIUM",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_type": "starter_covered_bullpen",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 4,
      "context_available": true,
      "limited_arms_count": 0,
      "monitor_arms_count": 5,
      "optionality_band": "deep",
      "restricted_arms_count": 0,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [
        {
          "availability": "Available",
          "last_workload": "5 days ago",
          "name": "Brandyn Garcia",
          "player_id": 805299,
          "recent_workload": "none"
        },
        {
          "availability": "Available",
          "last_workload": "2 days ago",
          "name": "Juan Burgos",
          "player_id": 686228,
          "recent_workload": "light"
        },
        {
          "availability": "Available",
          "last_workload": "5 days ago",
          "name": "Paul Sewald",
          "player_id": 623149,
          "recent_workload": "none"
        },
        {
          "availability": "Available",
          "last_workload": "4 days ago",
          "name": "Ryan Thompson",
          "player_id": 657044,
          "recent_workload": "moderate"
        }
      ],
      "clean_options_count": 4,
      "context_available": true,
      "core_retention_count": 1,
      "depth_pressure_band": "heavy",
      "inactive_bullpen_arms_count": 12,
      "optionality_band": "deep",
      "practical_close_game_paths_count": 6,
      "secondary_options": [
        {
          "availability": "Monitor",
          "name": "Drey Jameson",
          "player_id": 686753,
          "reason": "2 appearances in 5 days"
        },
        {
          "availability": "Monitor",
          "name": "Jonathan Lo\u00e1isiga",
          "player_id": 642528,
          "reason": "2 appearances in 5 days"
        },
        {
          "availability": "Monitor",
          "name": "Juan Morillo",
          "player_id": 666661,
          "reason": "23 pitches yesterday"
        },
        {
          "availability": "Monitor",
          "name": "Kevin Ginkel",
          "player_id": 656464,
          "reason": "Only 1 day of rest"
        },
        {
          "availability": "Monitor",
          "name": "Taylor Clarke",
          "player_id": 664199,
          "reason": "2 appearances in 5 days"
        }
      ],
      "secondary_options_count": 5,
      "stability_band": "transitioning"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 7,
      "bullpen_story_tag": "starter_covered_bullpen",
      "comeback_completed": false,
      "confidence": "HIGH",
      "deficit_when_bullpen_entered": 5,
      "final_score_against": 5,
      "final_score_for": 1,
      "game_date": "2026-06-28",
      "game_pk": 822959,
      "game_shape_created": "normal_start",
      "game_shape_protected": null,
      "generated_at": "2026-06-28T20:08:19.302447",
      "home_away": "away",
      "largest_deficit": 5,
      "largest_lead": 0,
      "late_runs_allowed": 0,
      "lead_lost": null,
      "lead_protected": null,
      "lead_when_bullpen_entered": null,
      "opponent_name": "Tampa Bay Rays",
      "runs_allowed_innings_7_to_9": 0,
      "starter_exit_inning": 6,
      "starter_ip": 6.0,
      "starter_name": "Merrill Kelly",
      "starter_pitch_count": 93,
      "team_id": 109,
      "turning_inning": null
    },
    "confidence": "HIGH",
    "game_importance": "LOW",
    "headline_key": "starter_carried_game",
    "primary_story": "starter_covered_bullpen",
    "publish_reason": "meets_confidence_threshold",
    "publishable": true,
    "recommended_surface": "dashboard",
    "safe_time_context": "AFTER_MOST_RECENT_GAME",
    "secondary_story": null,
    "story_priority": "MEDIUM",
    "summary_key": "starter_limited_bullpen_exposure",
    "supporting_facts": {
      "bullpen_entry_inning": 7,
      "bullpen_entry_score_against": 5,
      "bullpen_entry_score_for": 0,
      "game_shape_created": "normal_start",
      "largest_deficit": 5,
      "largest_lead": 0,
      "late_runs_allowed": 0,
      "runs_allowed_innings_7_to_9": 0,
      "starter_exit_score_against": 5,
      "starter_exit_score_for": 0
    },
    "supporting_observations": [
      "starter_created_game_shape",
      "deep_start",
      "deficit_entering_bullpen"
    ],
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": 2.9,
      "bullpen_workload_appearances_10d": 28,
      "bullpen_workload_total_10d": 472,
      "concentration_band": "balanced",
      "context_available": true,
      "early_bullpen_entry_rate": 50.0,
      "top_three_workload_share_10d": 41.3,
      "window_days": 10
    }
  },
  "team_id": 109,
  "writer_targets": [
    "team_story",
    "dashboard"
  ]
}
```

### Draft: team_story

Headline:
```
Starter carried the load
```
Opening:
```
After their most recent game, the starter worked deep and kept the bullpen's exposure light.
```
Body:
```
After their most recent game, the starter worked deep and kept the bullpen's exposure light.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Merrill Kelly, 6.0 IP, 93 pitches
- Largest deficit: 5
- Bullpen entered in the 7th trailing by 5
- Late runs allowed: 0
- Clean options: Brandyn Garcia, Juan Burgos, Paul Sewald, Ryan Thompson
```
Exact rendered text:
```
Starter carried the load

After their most recent game, the starter worked deep and kept the bullpen's exposure light.

Evidence:
- Starter: Merrill Kelly, 6.0 IP, 93 pitches
- Largest deficit: 5
- Bullpen entered in the 7th trailing by 5
- Late runs allowed: 0
- Clean options: Brandyn Garcia, Juan Burgos, Paul Sewald, Ryan Thompson
```


### Draft: dashboard

Headline:
```
Starter carried the load
```
Opening:
```
The club barely used behind a deep start.
```
Body:
```
The club barely used behind a deep start.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Merrill Kelly, 6.0 IP, 93 pitches
```
Exact rendered text:
```
Starter carried the load

The club barely used behind a deep start.

Evidence:
- Starter: Merrill Kelly, 6.0 IP, 93 pitches
```

## Completed-Game Story 3: Baltimore Orioles (BAL, 110)

### Story Metadata

```json
{
  "beat": "bullpen_overexposed",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_used": false,
  "game_date": "2026-06-28",
  "game_importance": "LOW",
  "game_pk": 824821,
  "opponent_name": "Washington Nationals",
  "publish_reason": "meets_confidence_threshold",
  "publishable": true,
  "recommended_surface": "dashboard",
  "severity": "MEDIUM",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_type": "bullpen_overexposed",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 1,
      "context_available": true,
      "limited_arms_count": 4,
      "monitor_arms_count": 2,
      "optionality_band": "thin",
      "restricted_arms_count": 5,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [
        {
          "availability": "Available",
          "last_workload": "4 days ago",
          "name": "Yennier Cano",
          "player_id": 666974,
          "recent_workload": "moderate"
        }
      ],
      "clean_options_count": 1,
      "context_available": true,
      "core_retention_count": 1,
      "depth_pressure_band": "heavy",
      "inactive_bullpen_arms_count": 13,
      "optionality_band": "thin",
      "practical_close_game_paths_count": 2,
      "secondary_options": [
        {
          "availability": "Monitor",
          "name": "Andrew Kittredge",
          "player_id": 552640,
          "reason": "2 appearances in 5 days"
        },
        {
          "availability": "Monitor",
          "name": "Rico Garcia",
          "player_id": 670329,
          "reason": "18 pitches yesterday"
        }
      ],
      "secondary_options_count": 2,
      "stability_band": "transitioning"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 5,
      "bullpen_story_tag": "bullpen_overexposed",
      "comeback_completed": false,
      "confidence": "HIGH",
      "deficit_when_bullpen_entered": 1,
      "final_score_against": 6,
      "final_score_for": 4,
      "game_date": "2026-06-28",
      "game_pk": 824821,
      "game_shape_created": "short_start",
      "game_shape_protected": null,
      "generated_at": "2026-06-28T22:47:16.168206",
      "home_away": "home",
      "largest_deficit": 4,
      "largest_lead": 2,
      "late_runs_allowed": 1,
      "lead_lost": null,
      "lead_protected": null,
      "lead_when_bullpen_entered": null,
      "opponent_name": "Washington Nationals",
      "runs_allowed_innings_7_to_9": 1,
      "starter_exit_inning": 5,
      "starter_ip": 4.0,
      "starter_name": "Kyle Bradish",
      "starter_pitch_count": 85,
      "team_id": 110,
      "turning_inning": 3
    },
    "confidence": "HIGH",
    "game_importance": "LOW",
    "headline_key": "bullpen_overexposed",
    "primary_story": "bullpen_overexposed",
    "publish_reason": "meets_confidence_threshold",
    "publishable": true,
    "recommended_surface": "dashboard",
    "safe_time_context": "AFTER_MOST_RECENT_GAME",
    "secondary_story": null,
    "story_priority": "MEDIUM",
    "summary_key": "bullpen_carried_heavy_load",
    "supporting_facts": {
      "bullpen_entry_inning": 5,
      "bullpen_entry_score_against": 3,
      "bullpen_entry_score_for": 2,
      "game_shape_created": "short_start",
      "largest_deficit": 4,
      "largest_lead": 2,
      "late_runs_allowed": 1,
      "runs_allowed_innings_7_to_9": 1,
      "starter_exit_score_against": 3,
      "starter_exit_score_for": 2,
      "turning_inning": 3
    },
    "supporting_observations": [
      "deficit_entering_bullpen",
      "late_runs_allowed",
      "bullpen_worked_long",
      "turning_point_identified"
    ],
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": 3.5,
      "bullpen_workload_appearances_10d": 29,
      "bullpen_workload_total_10d": 506,
      "concentration_band": "balanced",
      "context_available": true,
      "early_bullpen_entry_rate": 25.0,
      "top_three_workload_share_10d": 46.4,
      "window_days": 10
    }
  },
  "team_id": 110,
  "writer_targets": [
    "team_story",
    "dashboard"
  ]
}
```

### Draft: team_story

Headline:
```
Bullpen stretched thin
```
Opening:
```
After their most recent game, Kyle Bradish's four-inning start left the bullpen to cover the rest, including one late run.
```
Body:
```
After their most recent game, Kyle Bradish's four-inning start left the bullpen to cover the rest, including one late run.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Kyle Bradish, 4.0 IP, 85 pitches
- Largest lead: 2
- Bullpen entered in the 5th trailing by 1
- Turning point: 3rd inning
- Late runs allowed: 1
```
Exact rendered text:
```
Bullpen stretched thin

After their most recent game, Kyle Bradish's four-inning start left the bullpen to cover the rest, including one late run.

Evidence:
- Starter: Kyle Bradish, 4.0 IP, 85 pitches
- Largest lead: 2
- Bullpen entered in the 5th trailing by 1
- Turning point: 3rd inning
- Late runs allowed: 1
```


### Draft: dashboard

Headline:
```
Bullpen stretched thin
```
Opening:
```
The club covered heavy innings on a short start.
```
Body:
```
The club covered heavy innings on a short start.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Kyle Bradish, 4.0 IP, 85 pitches
```
Exact rendered text:
```
Bullpen stretched thin

The club covered heavy innings on a short start.

Evidence:
- Starter: Kyle Bradish, 4.0 IP, 85 pitches
```

## Completed-Game Story 4: Boston Red Sox (BOS, 111)

### Story Metadata

```json
{
  "beat": "protected_game_shape",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_used": false,
  "game_date": "2026-06-28",
  "game_importance": "MEDIUM",
  "game_pk": 824744,
  "opponent_name": "New York Yankees",
  "publish_reason": "high_priority_narrative",
  "publishable": true,
  "recommended_surface": "multiple",
  "severity": "HIGH",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_type": "protected_game_shape",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 3,
      "context_available": true,
      "limited_arms_count": 2,
      "monitor_arms_count": 2,
      "optionality_band": "flexible",
      "restricted_arms_count": 3,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [
        {
          "availability": "Available",
          "last_workload": "3 days ago",
          "name": "Greg Weissert",
          "player_id": 669711,
          "recent_workload": "moderate"
        },
        {
          "availability": "Available",
          "last_workload": "2 days ago",
          "name": "Ryan Watson",
          "player_id": 670245,
          "recent_workload": "light"
        },
        {
          "availability": "Available",
          "last_workload": "2 days ago",
          "name": "Tommy Kahnle",
          "player_id": 592454,
          "recent_workload": "moderate"
        }
      ],
      "clean_options_count": 3,
      "context_available": true,
      "core_retention_count": 1,
      "depth_pressure_band": "heavy",
      "inactive_bullpen_arms_count": 14,
      "optionality_band": "flexible",
      "practical_close_game_paths_count": 4,
      "secondary_options": [
        {
          "availability": "Monitor",
          "name": "Garrett Whitlock",
          "player_id": 676477,
          "reason": "2 appearances in 5 days"
        },
        {
          "availability": "Monitor",
          "name": "Tyron Guerrero",
          "player_id": 594027,
          "reason": "2 appearances in 5 days"
        }
      ],
      "secondary_options_count": 2,
      "stability_band": "transitioning"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 8,
      "bullpen_story_tag": "protected_game_shape",
      "comeback_completed": true,
      "confidence": "HIGH",
      "deficit_when_bullpen_entered": null,
      "final_score_against": 4,
      "final_score_for": 5,
      "game_date": "2026-06-28",
      "game_pk": 824744,
      "game_shape_created": "normal_start",
      "game_shape_protected": true,
      "generated_at": "2026-06-29T03:03:18.964062",
      "home_away": "home",
      "largest_deficit": 2,
      "largest_lead": 2,
      "late_runs_allowed": 4,
      "lead_lost": false,
      "lead_protected": true,
      "lead_when_bullpen_entered": 2,
      "opponent_name": "New York Yankees",
      "runs_allowed_innings_7_to_9": 2,
      "starter_exit_inning": 8,
      "starter_ip": 7.33333333333333,
      "starter_name": "Sonny Gray",
      "starter_pitch_count": 97,
      "team_id": 111,
      "turning_inning": 10
    },
    "confidence": "HIGH",
    "game_importance": "MEDIUM",
    "headline_key": "protected_game_shape",
    "primary_story": "protected_game_shape",
    "publish_reason": "high_priority_narrative",
    "publishable": true,
    "recommended_surface": "multiple",
    "safe_time_context": "AFTER_MOST_RECENT_GAME",
    "secondary_story": "bullpen_kept_team_alive",
    "story_priority": "HIGH",
    "summary_key": "game_shape_protected",
    "supporting_facts": {
      "bullpen_entry_inning": 8,
      "bullpen_entry_score_against": 0,
      "bullpen_entry_score_for": 2,
      "game_shape_created": "normal_start",
      "game_shape_protected": true,
      "largest_deficit": 2,
      "largest_lead": 2,
      "late_runs_allowed": 4,
      "lead_lost": false,
      "lead_protected": true,
      "runs_allowed_innings_7_to_9": 2,
      "starter_exit_score_against": 0,
      "starter_exit_score_for": 2,
      "turning_inning": 10
    },
    "supporting_observations": [
      "starter_created_game_shape",
      "deep_start",
      "lead_entering_bullpen",
      "bullpen_preserved_lead",
      "late_runs_allowed",
      "multiple_late_runs",
      "late_scoring_sequence",
      "comeback_completed",
      "turning_point_identified"
    ],
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": 2.3,
      "bullpen_workload_appearances_10d": 28,
      "bullpen_workload_total_10d": 374,
      "concentration_band": "balanced",
      "context_available": true,
      "early_bullpen_entry_rate": 15.4,
      "top_three_workload_share_10d": 51.1,
      "window_days": 10
    }
  },
  "team_id": 111,
  "writer_targets": [
    "team_story",
    "dashboard",
    "morning_brief"
  ]
}
```

### Draft: team_story

Headline:
```
Lead protected
```
Opening:
```
After their most recent game, Sonny Gray worked 7.3 innings and left with a two-run lead, and the bullpen brought it home.
```
Body:
```
After their most recent game, Sonny Gray worked 7.3 innings and left with a two-run lead, and the bullpen brought it home. The clean finish keeps the relief corps in good shape.
```
What BaseballOS noticed / observations:
```
- The starter went deep and set the bullpen up to finish the game.
- The bullpen took over with a lead in hand.
- The relievers held the lead.
- The damage came after the starter exited and piled up late.
```
Evidence:
```
- Starter: Sonny Gray, 7.3 IP, 97 pitches
- Largest lead: 2
- Bullpen entered in the 8th with a 2-run lead
- Turning point: 10th inning
- Late runs allowed: 4
```
Exact rendered text:
```
Lead protected

After their most recent game, Sonny Gray worked 7.3 innings and left with a two-run lead, and the bullpen brought it home. The clean finish keeps the relief corps in good shape.

Why BaseballOS sees it:
- The starter went deep and set the bullpen up to finish the game.
- The bullpen took over with a lead in hand.
- The relievers held the lead.
- The damage came after the starter exited and piled up late.

Evidence:
- Starter: Sonny Gray, 7.3 IP, 97 pitches
- Largest lead: 2
- Bullpen entered in the 8th with a 2-run lead
- Turning point: 10th inning
- Late runs allowed: 4
```


### Draft: dashboard

Headline:
```
Lead protected
```
Opening:
```
The club protected a 2-run lead.
```
Body:
```
The club protected a 2-run lead.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Sonny Gray, 7.3 IP, 97 pitches
```
Exact rendered text:
```
Lead protected

The club protected a 2-run lead.

Evidence:
- Starter: Sonny Gray, 7.3 IP, 97 pitches
```


### Draft: morning_brief

Headline:
```
Bullpen note: Lead protected
```
Opening:
```
After their most recent game, the club turned a two-run lead into a win the bullpen never let slip.
```
Body:
```
After their most recent game, the club turned a two-run lead into a win the bullpen never let slip. Available arms: Greg Weissert, Ryan Watson, Tommy Kahnle. The relief corps is in good shape.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Sonny Gray, 7.3 IP, 97 pitches
- Largest lead: 2
- Bullpen entered in the 8th with a 2-run lead
- Turning point: 10th inning
- Late runs allowed: 4
```
Exact rendered text:
```
Bullpen note: Lead protected

After their most recent game, the club turned a two-run lead into a win the bullpen never let slip. Available arms: Greg Weissert, Ryan Watson, Tommy Kahnle. The relief corps is in good shape.

Evidence:
- Starter: Sonny Gray, 7.3 IP, 97 pitches
- Largest lead: 2
- Bullpen entered in the 8th with a 2-run lead
- Turning point: 10th inning
- Late runs allowed: 4
```

## Completed-Game Story 5: Chicago Cubs (CHC, 112)

### Story Metadata

```json
{
  "beat": "bullpen_overexposed",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_used": false,
  "game_date": "2026-06-28",
  "game_importance": "MEDIUM",
  "game_pk": 823769,
  "opponent_name": "Milwaukee Brewers",
  "publish_reason": "meets_confidence_threshold",
  "publishable": true,
  "recommended_surface": "team_page",
  "severity": "MEDIUM",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_type": "bullpen_overexposed",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 0,
      "context_available": true,
      "limited_arms_count": 5,
      "monitor_arms_count": 2,
      "optionality_band": "thin",
      "restricted_arms_count": 7,
      "unavailable_arms_count": 2,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [],
      "clean_options_count": 0,
      "context_available": true,
      "core_retention_count": 1,
      "depth_pressure_band": "heavy",
      "inactive_bullpen_arms_count": 17,
      "optionality_band": "thin",
      "practical_close_game_paths_count": 1,
      "secondary_options": [
        {
          "availability": "Monitor",
          "name": "Jordan Wicks",
          "player_id": 696136,
          "reason": "No rest since last appearance"
        },
        {
          "availability": "Monitor",
          "name": "Ryan Rolison",
          "player_id": 669020,
          "reason": "2 appearances in 5 days"
        }
      ],
      "secondary_options_count": 2,
      "stability_band": "transitioning"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 3,
      "bullpen_story_tag": "bullpen_overexposed",
      "comeback_completed": true,
      "confidence": "HIGH",
      "deficit_when_bullpen_entered": 1,
      "final_score_against": 3,
      "final_score_for": 4,
      "game_date": "2026-06-28",
      "game_pk": 823769,
      "game_shape_created": "opener_bulk_game",
      "game_shape_protected": null,
      "generated_at": "2026-06-28T22:47:32.841324",
      "home_away": "away",
      "largest_deficit": 1,
      "largest_lead": 3,
      "late_runs_allowed": 2,
      "lead_lost": null,
      "lead_protected": null,
      "lead_when_bullpen_entered": null,
      "opponent_name": "Milwaukee Brewers",
      "runs_allowed_innings_7_to_9": 0,
      "starter_exit_inning": 2,
      "starter_ip": 2.0,
      "starter_name": "Ryan Rolison",
      "starter_pitch_count": 23,
      "team_id": 112,
      "turning_inning": 10
    },
    "confidence": "HIGH",
    "game_importance": "MEDIUM",
    "headline_key": "bullpen_overexposed",
    "primary_story": "bullpen_overexposed",
    "publish_reason": "meets_confidence_threshold",
    "publishable": true,
    "recommended_surface": "team_page",
    "safe_time_context": "AFTER_MOST_RECENT_GAME",
    "secondary_story": "bullpen_kept_team_alive",
    "story_priority": "MEDIUM",
    "summary_key": "bullpen_carried_heavy_load",
    "supporting_facts": {
      "bullpen_entry_inning": 3,
      "bullpen_entry_score_against": 1,
      "bullpen_entry_score_for": 0,
      "game_shape_created": "opener_bulk_game",
      "largest_deficit": 1,
      "largest_lead": 3,
      "late_runs_allowed": 2,
      "runs_allowed_innings_7_to_9": 0,
      "starter_exit_score_against": 1,
      "starter_exit_score_for": 0,
      "turning_inning": 10
    },
    "supporting_observations": [
      "starter_created_game_shape",
      "deficit_entering_bullpen",
      "late_runs_allowed",
      "comeback_completed",
      "bullpen_worked_long",
      "turning_point_identified"
    ],
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": 3.7,
      "bullpen_workload_appearances_10d": 35,
      "bullpen_workload_total_10d": 563,
      "concentration_band": "balanced",
      "context_available": true,
      "early_bullpen_entry_rate": 53.8,
      "top_three_workload_share_10d": 42.8,
      "window_days": 10
    }
  },
  "team_id": 112,
  "writer_targets": [
    "team_story",
    "dashboard"
  ]
}
```

### Draft: team_story

Headline:
```
Bullpen stretched thin
```
Opening:
```
After their most recent game, Ryan Rolison's two-inning start left the bullpen to cover the rest, including two late runs.
```
Body:
```
After their most recent game, Ryan Rolison's two-inning start left the bullpen to cover the rest, including two late runs.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Ryan Rolison, 2.0 IP, 23 pitches
- Largest lead: 3
- Bullpen entered in the 3rd trailing by 1
- Turning point: 10th inning
- Late runs allowed: 2
```
Exact rendered text:
```
Bullpen stretched thin

After their most recent game, Ryan Rolison's two-inning start left the bullpen to cover the rest, including two late runs.

Evidence:
- Starter: Ryan Rolison, 2.0 IP, 23 pitches
- Largest lead: 3
- Bullpen entered in the 3rd trailing by 1
- Turning point: 10th inning
- Late runs allowed: 2
```


### Draft: dashboard

Headline:
```
Bullpen stretched thin
```
Opening:
```
The club covered heavy innings on a short start.
```
Body:
```
The club covered heavy innings on a short start.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Ryan Rolison, 2.0 IP, 23 pitches
```
Exact rendered text:
```
Bullpen stretched thin

The club covered heavy innings on a short start.

Evidence:
- Starter: Ryan Rolison, 2.0 IP, 23 pitches
```

## Completed-Game Story 6: Cincinnati Reds (CIN, 113)

### Story Metadata

```json
{
  "beat": "insufficient_context",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_used": true,
  "game_date": "2026-06-28",
  "game_importance": "LOW",
  "game_pk": 823362,
  "opponent_name": "Pittsburgh Pirates",
  "publish_reason": "insufficient_confidence",
  "publishable": false,
  "recommended_surface": "none",
  "severity": "LOW",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_type": "insufficient_context",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 0,
      "context_available": true,
      "limited_arms_count": 4,
      "monitor_arms_count": 3,
      "optionality_band": "thin",
      "restricted_arms_count": 4,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [],
      "clean_options_count": 0,
      "context_available": true,
      "core_retention_count": 1,
      "depth_pressure_band": "heavy",
      "inactive_bullpen_arms_count": 10,
      "optionality_band": "thin",
      "practical_close_game_paths_count": 1,
      "secondary_options": [
        {
          "availability": "Monitor",
          "name": "Chase Petty",
          "player_id": 695534,
          "reason": "Only 1 day of rest"
        },
        {
          "availability": "Monitor",
          "name": "Sam Moll",
          "player_id": 594580,
          "reason": "20 pitches yesterday"
        },
        {
          "availability": "Monitor",
          "name": "Zach McCambley",
          "player_id": 685112,
          "reason": "No rest since last appearance"
        }
      ],
      "secondary_options_count": 3,
      "stability_band": "transitioning"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 5,
      "bullpen_story_tag": "insufficient_context",
      "comeback_completed": false,
      "confidence": "HIGH",
      "deficit_when_bullpen_entered": 1,
      "final_score_against": 9,
      "final_score_for": 4,
      "game_date": "2026-06-28",
      "game_pk": 823362,
      "game_shape_created": "short_start",
      "game_shape_protected": null,
      "generated_at": "2026-06-28T22:47:17.940169",
      "home_away": "away",
      "largest_deficit": 5,
      "largest_lead": 0,
      "late_runs_allowed": 4,
      "lead_lost": null,
      "lead_protected": null,
      "lead_when_bullpen_entered": null,
      "opponent_name": "Pittsburgh Pirates",
      "runs_allowed_innings_7_to_9": 4,
      "starter_exit_inning": 5,
      "starter_ip": 4.33333333333333,
      "starter_name": "Brady Singer",
      "starter_pitch_count": 98,
      "team_id": 113,
      "turning_inning": null
    },
    "confidence": "HIGH",
    "game_importance": "LOW",
    "headline_key": "insufficient_context",
    "primary_story": "insufficient_context",
    "publish_reason": "insufficient_confidence",
    "publishable": false,
    "recommended_surface": "none",
    "safe_time_context": "CURRENT_STATUS",
    "secondary_story": null,
    "story_priority": "LOW",
    "summary_key": "insufficient_context",
    "supporting_facts": {},
    "supporting_observations": [],
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": 3.2,
      "bullpen_workload_appearances_10d": 29,
      "bullpen_workload_total_10d": 467,
      "concentration_band": "balanced",
      "context_available": true,
      "early_bullpen_entry_rate": 41.7,
      "top_three_workload_share_10d": 47.8,
      "window_days": 10
    }
  },
  "team_id": 113,
  "writer_targets": []
}
```

No public drafts were rendered for this row by the existing writer targets.

## Completed-Game Story 7: Cleveland Guardians (CLE, 114)

### Story Metadata

```json
{
  "beat": "bullpen_kept_team_alive",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_used": false,
  "game_date": "2026-06-28",
  "game_importance": "MEDIUM",
  "game_pk": 824422,
  "opponent_name": "Seattle Mariners",
  "publish_reason": "high_priority_narrative",
  "publishable": true,
  "recommended_surface": "multiple",
  "severity": "HIGH",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_type": "bullpen_kept_team_alive",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 1,
      "context_available": true,
      "limited_arms_count": 4,
      "monitor_arms_count": 2,
      "optionality_band": "thin",
      "restricted_arms_count": 5,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [
        {
          "availability": "Available",
          "last_workload": "2 days ago",
          "name": "Daniel Espino",
          "player_id": 682982,
          "recent_workload": "light"
        }
      ],
      "clean_options_count": 1,
      "context_available": true,
      "core_retention_count": 1,
      "depth_pressure_band": "heavy",
      "inactive_bullpen_arms_count": 7,
      "optionality_band": "thin",
      "practical_close_game_paths_count": 2,
      "secondary_options": [
        {
          "availability": "Monitor",
          "name": "Colin Holderman",
          "player_id": 670059,
          "reason": "2 appearances in 5 days"
        },
        {
          "availability": "Monitor",
          "name": "Erik Sabrowski",
          "player_id": 681870,
          "reason": "2 appearances in 5 days"
        }
      ],
      "secondary_options_count": 2,
      "stability_band": "transitioning"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 6,
      "bullpen_story_tag": "bullpen_kept_team_alive",
      "comeback_completed": true,
      "confidence": "HIGH",
      "deficit_when_bullpen_entered": 2,
      "final_score_against": 5,
      "final_score_for": 6,
      "game_date": "2026-06-28",
      "game_pk": 824422,
      "game_shape_created": "normal_start",
      "game_shape_protected": null,
      "generated_at": "2026-06-28T22:47:24.172535",
      "home_away": "home",
      "largest_deficit": 3,
      "largest_lead": 2,
      "late_runs_allowed": 1,
      "lead_lost": null,
      "lead_protected": null,
      "lead_when_bullpen_entered": null,
      "opponent_name": "Seattle Mariners",
      "runs_allowed_innings_7_to_9": 1,
      "starter_exit_inning": 5,
      "starter_ip": 5.0,
      "starter_name": "Gavin Williams",
      "starter_pitch_count": 103,
      "team_id": 114,
      "turning_inning": 8
    },
    "confidence": "HIGH",
    "game_importance": "MEDIUM",
    "headline_key": "bullpen_kept_team_alive",
    "primary_story": "bullpen_kept_team_alive",
    "publish_reason": "high_priority_narrative",
    "publishable": true,
    "recommended_surface": "multiple",
    "safe_time_context": "AFTER_MOST_RECENT_GAME",
    "secondary_story": null,
    "story_priority": "HIGH",
    "summary_key": "bullpen_preserved_comeback",
    "supporting_facts": {
      "bullpen_entry_inning": 6,
      "bullpen_entry_score_against": 3,
      "bullpen_entry_score_for": 1,
      "game_shape_created": "normal_start",
      "largest_deficit": 3,
      "largest_lead": 2,
      "late_runs_allowed": 1,
      "runs_allowed_innings_7_to_9": 1,
      "starter_exit_score_against": 3,
      "starter_exit_score_for": 0,
      "turning_inning": 8
    },
    "supporting_observations": [
      "starter_created_game_shape",
      "deficit_entering_bullpen",
      "late_runs_allowed",
      "comeback_completed",
      "turning_point_identified"
    ],
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": 2.8,
      "bullpen_workload_appearances_10d": 30,
      "bullpen_workload_total_10d": 459,
      "concentration_band": "balanced",
      "context_available": true,
      "early_bullpen_entry_rate": 25.0,
      "top_three_workload_share_10d": 51.6,
      "window_days": 10
    }
  },
  "team_id": 114,
  "writer_targets": [
    "team_story",
    "dashboard",
    "morning_brief"
  ]
}
```

### Draft: team_story

Headline:
```
Bullpen kept it alive
```
Opening:
```
After their most recent game, Gavin Williams's five innings left a two-run deficit to erase, but the bullpen kept it from growing.
```
Body:
```
After their most recent game, Gavin Williams's five innings left a two-run deficit to erase, but the bullpen kept it from growing. The offense finished the rally. The comeback leaned on the bullpen, and the relief corps is down to fewer rested options.
```
What BaseballOS noticed / observations:
```
- The starter set the bullpen up to finish the game.
- The bullpen took over while trailing.
- The damage came after the starter exited.
- The offense finished the comeback the bullpen kept alive.
```
Evidence:
```
- Starter: Gavin Williams, 5.0 IP, 103 pitches
- Largest deficit: 3
- Bullpen entered in the 6th trailing by 2
- Turning point: 8th inning
- Late runs allowed: 1
```
Exact rendered text:
```
Bullpen kept it alive

After their most recent game, Gavin Williams's five innings left a two-run deficit to erase, but the bullpen kept it from growing. The offense finished the rally. The comeback leaned on the bullpen, and the relief corps is down to fewer rested options.

Why BaseballOS sees it:
- The starter set the bullpen up to finish the game.
- The bullpen took over while trailing.
- The damage came after the starter exited.
- The offense finished the comeback the bullpen kept alive.

Evidence:
- Starter: Gavin Williams, 5.0 IP, 103 pitches
- Largest deficit: 3
- Bullpen entered in the 6th trailing by 2
- Turning point: 8th inning
- Late runs allowed: 1
```


### Draft: dashboard

Headline:
```
Bullpen kept it alive
```
Opening:
```
The club kept the comeback alive.
```
Body:
```
The club kept the comeback alive.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Gavin Williams, 5.0 IP, 103 pitches
```
Exact rendered text:
```
Bullpen kept it alive

The club kept the comeback alive.

Evidence:
- Starter: Gavin Williams, 5.0 IP, 103 pitches
```


### Draft: morning_brief

Headline:
```
Bullpen note: Bullpen kept it alive
```
Opening:
```
After their most recent game, the club climbed out of a two-run hole the bullpen kept from growing.
```
Body:
```
After their most recent game, the club climbed out of a two-run hole the bullpen kept from growing. Available arms: Daniel Espino. The relief corps is down to fewer rested options.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Gavin Williams, 5.0 IP, 103 pitches
- Largest deficit: 3
- Bullpen entered in the 6th trailing by 2
- Turning point: 8th inning
- Late runs allowed: 1
```
Exact rendered text:
```
Bullpen note: Bullpen kept it alive

After their most recent game, the club climbed out of a two-run hole the bullpen kept from growing. Available arms: Daniel Espino. The relief corps is down to fewer rested options.

Evidence:
- Starter: Gavin Williams, 5.0 IP, 103 pitches
- Largest deficit: 3
- Bullpen entered in the 6th trailing by 2
- Turning point: 8th inning
- Late runs allowed: 1
```

## Completed-Game Story 8: Colorado Rockies (COL, 115)

### Story Metadata

```json
{
  "beat": "starter_covered_bullpen",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_used": false,
  "game_date": "2026-06-28",
  "game_importance": "LOW",
  "game_pk": 823686,
  "opponent_name": "Minnesota Twins",
  "publish_reason": "meets_confidence_threshold",
  "publishable": true,
  "recommended_surface": "dashboard",
  "severity": "MEDIUM",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_type": "starter_covered_bullpen",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 0,
      "context_available": true,
      "limited_arms_count": 5,
      "monitor_arms_count": 2,
      "optionality_band": "thin",
      "restricted_arms_count": 5,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [],
      "clean_options_count": 0,
      "context_available": true,
      "core_retention_count": 1,
      "depth_pressure_band": "heavy",
      "inactive_bullpen_arms_count": 11,
      "optionality_band": "thin",
      "practical_close_game_paths_count": 1,
      "secondary_options": [
        {
          "availability": "Monitor",
          "name": "Antonio Senzatela",
          "player_id": 622608,
          "reason": "2 appearances in 5 days"
        },
        {
          "availability": "Monitor",
          "name": "Victor Vodnik",
          "player_id": 680767,
          "reason": "15 pitches yesterday"
        }
      ],
      "secondary_options_count": 2,
      "stability_band": "transitioning"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 7,
      "bullpen_story_tag": "starter_covered_bullpen",
      "comeback_completed": false,
      "confidence": "HIGH",
      "deficit_when_bullpen_entered": null,
      "final_score_against": 3,
      "final_score_for": 2,
      "game_date": "2026-06-28",
      "game_pk": 823686,
      "game_shape_created": "normal_start",
      "game_shape_protected": null,
      "generated_at": "2026-06-28T22:47:28.032879",
      "home_away": "away",
      "largest_deficit": 1,
      "largest_lead": 1,
      "late_runs_allowed": 1,
      "lead_lost": null,
      "lead_protected": null,
      "lead_when_bullpen_entered": null,
      "opponent_name": "Minnesota Twins",
      "runs_allowed_innings_7_to_9": 1,
      "starter_exit_inning": 6,
      "starter_ip": 6.0,
      "starter_name": "Ryan Feltner",
      "starter_pitch_count": 82,
      "team_id": 115,
      "turning_inning": 4
    },
    "confidence": "HIGH",
    "game_importance": "LOW",
    "headline_key": "starter_carried_game",
    "primary_story": "starter_covered_bullpen",
    "publish_reason": "meets_confidence_threshold",
    "publishable": true,
    "recommended_surface": "dashboard",
    "safe_time_context": "AFTER_MOST_RECENT_GAME",
    "secondary_story": null,
    "story_priority": "MEDIUM",
    "summary_key": "starter_limited_bullpen_exposure",
    "supporting_facts": {
      "bullpen_entry_inning": 7,
      "bullpen_entry_score_against": 2,
      "bullpen_entry_score_for": 2,
      "game_shape_created": "normal_start",
      "largest_deficit": 1,
      "largest_lead": 1,
      "late_runs_allowed": 1,
      "runs_allowed_innings_7_to_9": 1,
      "starter_exit_score_against": 2,
      "starter_exit_score_for": 2,
      "turning_inning": 4
    },
    "supporting_observations": [
      "starter_created_game_shape",
      "deep_start",
      "late_runs_allowed",
      "turning_point_identified"
    ],
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": 3.3,
      "bullpen_workload_appearances_10d": 23,
      "bullpen_workload_total_10d": 400,
      "concentration_band": "balanced",
      "context_available": true,
      "early_bullpen_entry_rate": 27.3,
      "top_three_workload_share_10d": 52.2,
      "window_days": 10
    }
  },
  "team_id": 115,
  "writer_targets": [
    "team_story",
    "dashboard"
  ]
}
```

### Draft: team_story

Headline:
```
Starter carried the load
```
Opening:
```
After their most recent game, the starter worked deep and kept the bullpen's exposure light.
```
Body:
```
After their most recent game, the starter worked deep and kept the bullpen's exposure light.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Ryan Feltner, 6.0 IP, 82 pitches
- Largest lead: 1
- Bullpen entered in the 7th
- Turning point: 4th inning
- Late runs allowed: 1
```
Exact rendered text:
```
Starter carried the load

After their most recent game, the starter worked deep and kept the bullpen's exposure light.

Evidence:
- Starter: Ryan Feltner, 6.0 IP, 82 pitches
- Largest lead: 1
- Bullpen entered in the 7th
- Turning point: 4th inning
- Late runs allowed: 1
```


### Draft: dashboard

Headline:
```
Starter carried the load
```
Opening:
```
The club barely used behind a deep start.
```
Body:
```
The club barely used behind a deep start.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Ryan Feltner, 6.0 IP, 82 pitches
```
Exact rendered text:
```
Starter carried the load

The club barely used behind a deep start.

Evidence:
- Starter: Ryan Feltner, 6.0 IP, 82 pitches
```

## Completed-Game Story 9: Detroit Tigers (DET, 116)

### Story Metadata

```json
{
  "beat": "lost_game_shape",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_used": false,
  "game_date": "2026-06-28",
  "game_importance": "HIGH",
  "game_pk": 824256,
  "opponent_name": "Houston Astros",
  "publish_reason": "critical_narrative",
  "publishable": true,
  "recommended_surface": "multiple",
  "severity": "CRITICAL",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_type": "lost_game_shape",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 0,
      "context_available": true,
      "limited_arms_count": 3,
      "monitor_arms_count": 4,
      "optionality_band": "thin",
      "restricted_arms_count": 3,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [],
      "clean_options_count": 0,
      "context_available": true,
      "core_retention_count": 2,
      "depth_pressure_band": "heavy",
      "inactive_bullpen_arms_count": 14,
      "optionality_band": "thin",
      "practical_close_game_paths_count": 2,
      "secondary_options": [
        {
          "availability": "Monitor",
          "name": "Drew Sommers",
          "player_id": 805427,
          "reason": "Only 1 day of rest"
        },
        {
          "availability": "Monitor",
          "name": "Kenley Jansen",
          "player_id": 445276,
          "reason": "2 appearances in 5 days"
        },
        {
          "availability": "Monitor",
          "name": "Kyle Finnegan",
          "player_id": 640448,
          "reason": "2 appearances in 5 days"
        },
        {
          "availability": "Monitor",
          "name": "Tyler Holton",
          "player_id": 663947,
          "reason": "2 appearances in 5 days"
        }
      ],
      "secondary_options_count": 4,
      "stability_band": "mostly_stable"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 6,
      "bullpen_story_tag": "lost_game_shape",
      "comeback_completed": false,
      "confidence": "HIGH",
      "deficit_when_bullpen_entered": null,
      "final_score_against": 7,
      "final_score_for": 5,
      "game_date": "2026-06-28",
      "game_pk": 824256,
      "game_shape_created": "normal_start",
      "game_shape_protected": false,
      "generated_at": "2026-06-28T22:47:22.005033",
      "home_away": "home",
      "largest_deficit": 4,
      "largest_lead": 3,
      "late_runs_allowed": 7,
      "lead_lost": true,
      "lead_protected": false,
      "lead_when_bullpen_entered": 3,
      "opponent_name": "Houston Astros",
      "runs_allowed_innings_7_to_9": 3,
      "starter_exit_inning": 5,
      "starter_ip": 5.0,
      "starter_name": "Jack Flaherty",
      "starter_pitch_count": 94,
      "team_id": 116,
      "turning_inning": 10
    },
    "confidence": "HIGH",
    "game_importance": "HIGH",
    "headline_key": "lost_game_shape",
    "primary_story": "lost_game_shape",
    "publish_reason": "critical_narrative",
    "publishable": true,
    "recommended_surface": "multiple",
    "safe_time_context": "AFTER_MOST_RECENT_GAME",
    "secondary_story": "late_pressure_accumulated",
    "story_priority": "CRITICAL",
    "summary_key": "game_shape_not_protected",
    "supporting_facts": {
      "bullpen_entry_inning": 6,
      "bullpen_entry_score_against": 0,
      "bullpen_entry_score_for": 3,
      "game_shape_created": "normal_start",
      "game_shape_protected": false,
      "largest_deficit": 4,
      "largest_lead": 3,
      "late_runs_allowed": 7,
      "lead_lost": true,
      "lead_protected": false,
      "runs_allowed_innings_7_to_9": 3,
      "starter_exit_score_against": 0,
      "starter_exit_score_for": 2,
      "turning_inning": 10
    },
    "supporting_observations": [
      "starter_created_game_shape",
      "lead_entering_bullpen",
      "bullpen_lost_lead",
      "late_runs_allowed",
      "multiple_late_runs",
      "late_scoring_sequence",
      "turning_point_identified"
    ],
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": 2.8,
      "bullpen_workload_appearances_10d": 29,
      "bullpen_workload_total_10d": 516,
      "concentration_band": "balanced",
      "context_available": true,
      "early_bullpen_entry_rate": 46.2,
      "top_three_workload_share_10d": 43.0,
      "window_days": 10
    }
  },
  "team_id": 116,
  "writer_targets": [
    "team_story",
    "dashboard",
    "morning_brief"
  ]
}
```

### Draft: team_story

Headline:
```
Lead surrendered late
```
Opening:
```
After their most recent game, Jack Flaherty's five strong innings staked a three-run lead heading to the late innings.
```
Body:
```
After their most recent game, Jack Flaherty's five strong innings staked a three-run lead heading to the late innings. It didn't last. Seven late runs turned the game. That late collapse leaves the relief corps down to fewer rested options.
```
What BaseballOS noticed / observations:
```
- The starter set the bullpen up to finish the game.
- The bullpen took over with a lead in hand.
- The relievers could not hold the lead.
- The damage came after the starter exited and piled up late.
```
Evidence:
```
- Starter: Jack Flaherty, 5.0 IP, 94 pitches
- Largest lead: 3
- Bullpen entered in the 6th with a 3-run lead
- Turning point: 10th inning
- Late runs allowed: 7
```
Exact rendered text:
```
Lead surrendered late

After their most recent game, Jack Flaherty's five strong innings staked a three-run lead heading to the late innings. It didn't last. Seven late runs turned the game. That late collapse leaves the relief corps down to fewer rested options.

Why BaseballOS sees it:
- The starter set the bullpen up to finish the game.
- The bullpen took over with a lead in hand.
- The relievers could not hold the lead.
- The damage came after the starter exited and piled up late.

Evidence:
- Starter: Jack Flaherty, 5.0 IP, 94 pitches
- Largest lead: 3
- Bullpen entered in the 6th with a 3-run lead
- Turning point: 10th inning
- Late runs allowed: 7
```


### Draft: dashboard

Headline:
```
Lead surrendered late
```
Opening:
```
The club blew a 3-run lead late.
```
Body:
```
The club blew a 3-run lead late.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Jack Flaherty, 5.0 IP, 94 pitches
```
Exact rendered text:
```
Lead surrendered late

The club blew a 3-run lead late.

Evidence:
- Starter: Jack Flaherty, 5.0 IP, 94 pitches
```


### Draft: morning_brief

Headline:
```
Bullpen note: Lead surrendered late
```
Opening:
```
After their most recent game, the club carried a three-run lead into the late innings and let it get away on seven late runs.
```
Body:
```
After their most recent game, the club carried a three-run lead into the late innings and let it get away on seven late runs. Available arms: 0. Yesterday's late damage leaves the relief corps down to fewer rested options.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Jack Flaherty, 5.0 IP, 94 pitches
- Largest lead: 3
- Bullpen entered in the 6th with a 3-run lead
- Turning point: 10th inning
- Late runs allowed: 7
```
Exact rendered text:
```
Bullpen note: Lead surrendered late

After their most recent game, the club carried a three-run lead into the late innings and let it get away on seven late runs. Available arms: 0. Yesterday's late damage leaves the relief corps down to fewer rested options.

Evidence:
- Starter: Jack Flaherty, 5.0 IP, 94 pitches
- Largest lead: 3
- Bullpen entered in the 6th with a 3-run lead
- Turning point: 10th inning
- Late runs allowed: 7
```

## Completed-Game Story 10: Houston Astros (HOU, 117)

### Story Metadata

```json
{
  "beat": "insufficient_context",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_used": true,
  "game_date": "2026-06-28",
  "game_importance": "LOW",
  "game_pk": 824256,
  "opponent_name": "Detroit Tigers",
  "publish_reason": "insufficient_confidence",
  "publishable": false,
  "recommended_surface": "none",
  "severity": "LOW",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_type": "insufficient_context",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 0,
      "context_available": true,
      "limited_arms_count": 6,
      "monitor_arms_count": 0,
      "optionality_band": "thin",
      "restricted_arms_count": 7,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [],
      "clean_options_count": 0,
      "context_available": true,
      "core_retention_count": 1,
      "depth_pressure_band": "heavy",
      "inactive_bullpen_arms_count": 9,
      "optionality_band": "thin",
      "practical_close_game_paths_count": 0,
      "secondary_options": [],
      "secondary_options_count": 0,
      "stability_band": "transitioning"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 7,
      "bullpen_story_tag": "insufficient_context",
      "comeback_completed": true,
      "confidence": "HIGH",
      "deficit_when_bullpen_entered": 1,
      "final_score_against": 5,
      "final_score_for": 7,
      "game_date": "2026-06-28",
      "game_pk": 824256,
      "game_shape_created": "normal_start",
      "game_shape_protected": null,
      "generated_at": "2026-06-28T22:47:22.005180",
      "home_away": "away",
      "largest_deficit": 3,
      "largest_lead": 4,
      "late_runs_allowed": 2,
      "lead_lost": null,
      "lead_protected": null,
      "lead_when_bullpen_entered": null,
      "opponent_name": "Detroit Tigers",
      "runs_allowed_innings_7_to_9": 0,
      "starter_exit_inning": 6,
      "starter_ip": 6.0,
      "starter_name": "Hunter Brown",
      "starter_pitch_count": 103,
      "team_id": 117,
      "turning_inning": 10
    },
    "confidence": "HIGH",
    "game_importance": "LOW",
    "headline_key": "insufficient_context",
    "primary_story": "insufficient_context",
    "publish_reason": "insufficient_confidence",
    "publishable": false,
    "recommended_surface": "none",
    "safe_time_context": "CURRENT_STATUS",
    "secondary_story": null,
    "story_priority": "LOW",
    "summary_key": "insufficient_context",
    "supporting_facts": {},
    "supporting_observations": [],
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": 4.5,
      "bullpen_workload_appearances_10d": 33,
      "bullpen_workload_total_10d": 591,
      "concentration_band": "balanced",
      "context_available": true,
      "early_bullpen_entry_rate": 53.8,
      "top_three_workload_share_10d": 50.8,
      "window_days": 10
    }
  },
  "team_id": 117,
  "writer_targets": []
}
```

No public drafts were rendered for this row by the existing writer targets.

## Completed-Game Story 11: Kansas City Royals (KC, 118)

### Story Metadata

```json
{
  "beat": "bullpen_overexposed",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_used": false,
  "game_date": "2026-06-28",
  "game_importance": "LOW",
  "game_pk": 824580,
  "opponent_name": "Chicago White Sox",
  "publish_reason": "meets_confidence_threshold",
  "publishable": true,
  "recommended_surface": "dashboard",
  "severity": "MEDIUM",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_type": "bullpen_overexposed",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 1,
      "context_available": true,
      "limited_arms_count": 5,
      "monitor_arms_count": 1,
      "optionality_band": "thin",
      "restricted_arms_count": 6,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [
        {
          "availability": "Available",
          "last_workload": "3 days ago",
          "name": "Connor Seabold",
          "player_id": 657756,
          "recent_workload": "moderate"
        }
      ],
      "clean_options_count": 1,
      "context_available": true,
      "core_retention_count": 1,
      "depth_pressure_band": "heavy",
      "inactive_bullpen_arms_count": 11,
      "optionality_band": "thin",
      "practical_close_game_paths_count": 1,
      "secondary_options": [
        {
          "availability": "Monitor",
          "name": "Matt Strahm",
          "player_id": 621381,
          "reason": "2 appearances in 5 days"
        }
      ],
      "secondary_options_count": 1,
      "stability_band": "transitioning"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 5,
      "bullpen_story_tag": "bullpen_overexposed",
      "comeback_completed": true,
      "confidence": "HIGH",
      "deficit_when_bullpen_entered": null,
      "final_score_against": 4,
      "final_score_for": 5,
      "game_date": "2026-06-28",
      "game_pk": 824580,
      "game_shape_created": "short_start",
      "game_shape_protected": null,
      "generated_at": "2026-06-28T22:47:30.530911",
      "home_away": "away",
      "largest_deficit": 1,
      "largest_lead": 1,
      "late_runs_allowed": 0,
      "lead_lost": false,
      "lead_protected": true,
      "lead_when_bullpen_entered": 1,
      "opponent_name": "Chicago White Sox",
      "runs_allowed_innings_7_to_9": 0,
      "starter_exit_inning": 4,
      "starter_ip": 4.0,
      "starter_name": "Luinder Avila",
      "starter_pitch_count": 86,
      "team_id": 118,
      "turning_inning": 4
    },
    "confidence": "HIGH",
    "game_importance": "LOW",
    "headline_key": "bullpen_overexposed",
    "primary_story": "bullpen_overexposed",
    "publish_reason": "meets_confidence_threshold",
    "publishable": true,
    "recommended_surface": "dashboard",
    "safe_time_context": "AFTER_MOST_RECENT_GAME",
    "secondary_story": "bullpen_kept_team_alive",
    "story_priority": "MEDIUM",
    "summary_key": "bullpen_carried_heavy_load",
    "supporting_facts": {
      "bullpen_entry_inning": 5,
      "bullpen_entry_score_against": 4,
      "bullpen_entry_score_for": 5,
      "game_shape_created": "short_start",
      "largest_deficit": 1,
      "largest_lead": 1,
      "late_runs_allowed": 0,
      "lead_lost": false,
      "lead_protected": true,
      "runs_allowed_innings_7_to_9": 0,
      "starter_exit_score_against": 4,
      "starter_exit_score_for": 5,
      "turning_inning": 4
    },
    "supporting_observations": [
      "lead_entering_bullpen",
      "bullpen_preserved_lead",
      "comeback_completed",
      "bullpen_worked_long",
      "turning_point_identified"
    ],
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": 2.7,
      "bullpen_workload_appearances_10d": 33,
      "bullpen_workload_total_10d": 603,
      "concentration_band": "balanced",
      "context_available": true,
      "early_bullpen_entry_rate": 61.5,
      "top_three_workload_share_10d": 43.4,
      "window_days": 10
    }
  },
  "team_id": 118,
  "writer_targets": [
    "team_story",
    "dashboard"
  ]
}
```

### Draft: team_story

Headline:
```
Bullpen stretched thin
```
Opening:
```
After their most recent game, Luinder Avila's four-inning start left the bullpen to cover the rest.
```
Body:
```
After their most recent game, Luinder Avila's four-inning start left the bullpen to cover the rest.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Luinder Avila, 4.0 IP, 86 pitches
- Largest lead: 1
- Bullpen entered in the 5th with a 1-run lead
- Turning point: 4th inning
- Late runs allowed: 0
```
Exact rendered text:
```
Bullpen stretched thin

After their most recent game, Luinder Avila's four-inning start left the bullpen to cover the rest.

Evidence:
- Starter: Luinder Avila, 4.0 IP, 86 pitches
- Largest lead: 1
- Bullpen entered in the 5th with a 1-run lead
- Turning point: 4th inning
- Late runs allowed: 0
```


### Draft: dashboard

Headline:
```
Bullpen stretched thin
```
Opening:
```
The club covered heavy innings on a short start.
```
Body:
```
The club covered heavy innings on a short start.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Luinder Avila, 4.0 IP, 86 pitches
```
Exact rendered text:
```
Bullpen stretched thin

The club covered heavy innings on a short start.

Evidence:
- Starter: Luinder Avila, 4.0 IP, 86 pitches
```

## Completed-Game Story 12: Los Angeles Dodgers (LAD, 119)

### Story Metadata

```json
{
  "beat": "protected_game_shape",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_used": false,
  "game_date": "2026-06-28",
  "game_importance": "MEDIUM",
  "game_pk": 823281,
  "opponent_name": "San Diego Padres",
  "publish_reason": "high_priority_narrative",
  "publishable": true,
  "recommended_surface": "multiple",
  "severity": "HIGH",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_type": "protected_game_shape",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 1,
      "context_available": true,
      "limited_arms_count": 3,
      "monitor_arms_count": 4,
      "optionality_band": "narrow",
      "restricted_arms_count": 3,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [
        {
          "availability": "Available",
          "last_workload": "2 days ago",
          "name": "Brock Stewart",
          "player_id": 592779,
          "recent_workload": "light"
        }
      ],
      "clean_options_count": 1,
      "context_available": true,
      "core_retention_count": 0,
      "depth_pressure_band": "heavy",
      "inactive_bullpen_arms_count": 19,
      "optionality_band": "narrow",
      "practical_close_game_paths_count": 3,
      "secondary_options": [
        {
          "availability": "Monitor",
          "name": "Jonathan Hern\u00e1ndez",
          "player_id": 642546,
          "reason": "30 pitches in 3 days"
        },
        {
          "availability": "Monitor",
          "name": "Kyle Hurt",
          "player_id": 669165,
          "reason": "19 pitches yesterday"
        },
        {
          "availability": "Monitor",
          "name": "Tanner Scott",
          "player_id": 656945,
          "reason": "2 appearances in 5 days"
        },
        {
          "availability": "Monitor",
          "name": "Will Klein",
          "player_id": 694361,
          "reason": "No rest since last appearance"
        }
      ],
      "secondary_options_count": 4,
      "stability_band": "rebuilding"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 6,
      "bullpen_story_tag": "protected_game_shape",
      "comeback_completed": false,
      "confidence": "HIGH",
      "deficit_when_bullpen_entered": null,
      "final_score_against": 2,
      "final_score_for": 4,
      "game_date": "2026-06-28",
      "game_pk": 823281,
      "game_shape_created": "normal_start",
      "game_shape_protected": true,
      "generated_at": "2026-06-28T23:33:23.053587",
      "home_away": "away",
      "largest_deficit": 0,
      "largest_lead": 3,
      "late_runs_allowed": 0,
      "lead_lost": false,
      "lead_protected": true,
      "lead_when_bullpen_entered": 3,
      "opponent_name": "San Diego Padres",
      "runs_allowed_innings_7_to_9": 0,
      "starter_exit_inning": 5,
      "starter_ip": 5.0,
      "starter_name": "Emmet Sheehan",
      "starter_pitch_count": 84,
      "team_id": 119,
      "turning_inning": null
    },
    "confidence": "HIGH",
    "game_importance": "MEDIUM",
    "headline_key": "bullpen_stabilized",
    "primary_story": "protected_game_shape",
    "publish_reason": "high_priority_narrative",
    "publishable": true,
    "recommended_surface": "multiple",
    "safe_time_context": "AFTER_MOST_RECENT_GAME",
    "secondary_story": null,
    "story_priority": "HIGH",
    "summary_key": "game_shape_protected",
    "supporting_facts": {
      "bullpen_entry_inning": 6,
      "bullpen_entry_score_against": 1,
      "bullpen_entry_score_for": 4,
      "game_shape_created": "normal_start",
      "game_shape_protected": true,
      "largest_deficit": 0,
      "largest_lead": 3,
      "late_runs_allowed": 0,
      "lead_lost": false,
      "lead_protected": true,
      "runs_allowed_innings_7_to_9": 0,
      "starter_exit_score_against": 1,
      "starter_exit_score_for": 4
    },
    "supporting_observations": [
      "starter_created_game_shape",
      "lead_entering_bullpen",
      "bullpen_preserved_lead"
    ],
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": 4.0,
      "bullpen_workload_appearances_10d": 29,
      "bullpen_workload_total_10d": 465,
      "concentration_band": "balanced",
      "context_available": true,
      "early_bullpen_entry_rate": 33.3,
      "top_three_workload_share_10d": 46.0,
      "window_days": 10
    }
  },
  "team_id": 119,
  "writer_targets": [
    "team_story",
    "dashboard",
    "morning_brief"
  ]
}
```

### Draft: team_story

Headline:
```
Bullpen slammed the door
```
Opening:
```
After their most recent game, Emmet Sheehan worked five innings and left with a three-run lead, and the bullpen brought it home.
```
Body:
```
After their most recent game, Emmet Sheehan worked five innings and left with a three-run lead, and the bullpen brought it home. The clean finish keeps the relief corps down to a short list of clean arms.
```
What BaseballOS noticed / observations:
```
- The starter set the bullpen up to finish the game.
- The bullpen took over with a lead in hand.
- The relievers held the lead.
```
Evidence:
```
- Starter: Emmet Sheehan, 5.0 IP, 84 pitches
- Largest lead: 3
- Bullpen entered in the 6th with a 3-run lead
- Late runs allowed: 0
- Clean options: Brock Stewart
```
Exact rendered text:
```
Bullpen slammed the door

After their most recent game, Emmet Sheehan worked five innings and left with a three-run lead, and the bullpen brought it home. The clean finish keeps the relief corps down to a short list of clean arms.

Why BaseballOS sees it:
- The starter set the bullpen up to finish the game.
- The bullpen took over with a lead in hand.
- The relievers held the lead.

Evidence:
- Starter: Emmet Sheehan, 5.0 IP, 84 pitches
- Largest lead: 3
- Bullpen entered in the 6th with a 3-run lead
- Late runs allowed: 0
- Clean options: Brock Stewart
```


### Draft: dashboard

Headline:
```
Bullpen slammed the door
```
Opening:
```
The club protected a 3-run lead.
```
Body:
```
The club protected a 3-run lead.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Emmet Sheehan, 5.0 IP, 84 pitches
```
Exact rendered text:
```
Bullpen slammed the door

The club protected a 3-run lead.

Evidence:
- Starter: Emmet Sheehan, 5.0 IP, 84 pitches
```


### Draft: morning_brief

Headline:
```
Bullpen note: Bullpen slammed the door
```
Opening:
```
After their most recent game, the club turned a three-run lead into a win the bullpen never let slip.
```
Body:
```
After their most recent game, the club turned a three-run lead into a win the bullpen never let slip. Available arms: Brock Stewart. The relief corps is down to a short list of clean arms.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Emmet Sheehan, 5.0 IP, 84 pitches
- Largest lead: 3
- Bullpen entered in the 6th with a 3-run lead
- Late runs allowed: 0
- Clean options: Brock Stewart
```
Exact rendered text:
```
Bullpen note: Bullpen slammed the door

After their most recent game, the club turned a three-run lead into a win the bullpen never let slip. Available arms: Brock Stewart. The relief corps is down to a short list of clean arms.

Evidence:
- Starter: Emmet Sheehan, 5.0 IP, 84 pitches
- Largest lead: 3
- Bullpen entered in the 6th with a 3-run lead
- Late runs allowed: 0
- Clean options: Brock Stewart
```

## Completed-Game Story 13: Washington Nationals (WSH, 120)

### Story Metadata

```json
{
  "beat": "protected_game_shape",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_used": false,
  "game_date": "2026-06-28",
  "game_importance": "HIGH",
  "game_pk": 824821,
  "opponent_name": "Baltimore Orioles",
  "publish_reason": "high_priority_narrative",
  "publishable": true,
  "recommended_surface": "multiple",
  "severity": "HIGH",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_type": "protected_game_shape",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 1,
      "context_available": true,
      "limited_arms_count": 2,
      "monitor_arms_count": 5,
      "optionality_band": "narrow",
      "restricted_arms_count": 4,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [
        {
          "availability": "Available",
          "last_workload": "2 days ago",
          "name": "Zak Kent",
          "player_id": 687849,
          "recent_workload": "moderate"
        }
      ],
      "clean_options_count": 1,
      "context_available": true,
      "core_retention_count": 2,
      "depth_pressure_band": "heavy",
      "inactive_bullpen_arms_count": 12,
      "optionality_band": "narrow",
      "practical_close_game_paths_count": 3,
      "secondary_options": [
        {
          "availability": "Monitor",
          "name": "Clayton Beeter",
          "player_id": 690925,
          "reason": "20 pitches yesterday"
        },
        {
          "availability": "Monitor",
          "name": "Justin Lawrence",
          "player_id": 664875,
          "reason": "15 pitches yesterday"
        },
        {
          "availability": "Monitor",
          "name": "Mitchell Parker",
          "player_id": 680730,
          "reason": "2 appearances in 5 days"
        },
        {
          "availability": "Monitor",
          "name": "Orlando Ribalta",
          "player_id": 687377,
          "reason": "2 appearances in 5 days"
        },
        {
          "availability": "Monitor",
          "name": "Richard Lovelady",
          "player_id": 663992,
          "reason": "2 appearances in 5 days"
        }
      ],
      "secondary_options_count": 5,
      "stability_band": "mostly_stable"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 6,
      "bullpen_story_tag": "protected_game_shape",
      "comeback_completed": true,
      "confidence": "HIGH",
      "deficit_when_bullpen_entered": null,
      "final_score_against": 4,
      "final_score_for": 6,
      "game_date": "2026-06-28",
      "game_pk": 824821,
      "game_shape_created": "normal_start",
      "game_shape_protected": true,
      "generated_at": "2026-06-28T22:47:16.168346",
      "home_away": "away",
      "largest_deficit": 2,
      "largest_lead": 4,
      "late_runs_allowed": 2,
      "lead_lost": false,
      "lead_protected": true,
      "lead_when_bullpen_entered": 3,
      "opponent_name": "Baltimore Orioles",
      "runs_allowed_innings_7_to_9": 2,
      "starter_exit_inning": 5,
      "starter_ip": 5.0,
      "starter_name": "Zack Littell",
      "starter_pitch_count": 82,
      "team_id": 120,
      "turning_inning": 3
    },
    "confidence": "HIGH",
    "game_importance": "HIGH",
    "headline_key": "protected_game_shape",
    "primary_story": "protected_game_shape",
    "publish_reason": "high_priority_narrative",
    "publishable": true,
    "recommended_surface": "multiple",
    "safe_time_context": "AFTER_MOST_RECENT_GAME",
    "secondary_story": "bullpen_kept_team_alive",
    "story_priority": "HIGH",
    "summary_key": "game_shape_protected",
    "supporting_facts": {
      "bullpen_entry_inning": 6,
      "bullpen_entry_score_against": 2,
      "bullpen_entry_score_for": 5,
      "game_shape_created": "normal_start",
      "game_shape_protected": true,
      "largest_deficit": 2,
      "largest_lead": 4,
      "late_runs_allowed": 2,
      "lead_lost": false,
      "lead_protected": true,
      "runs_allowed_innings_7_to_9": 2,
      "starter_exit_score_against": 2,
      "starter_exit_score_for": 5,
      "turning_inning": 3
    },
    "supporting_observations": [
      "starter_created_game_shape",
      "lead_entering_bullpen",
      "bullpen_preserved_lead",
      "late_runs_allowed",
      "multiple_late_runs",
      "late_scoring_sequence",
      "comeback_completed",
      "turning_point_identified"
    ],
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": 3.4,
      "bullpen_workload_appearances_10d": 32,
      "bullpen_workload_total_10d": 715,
      "concentration_band": "balanced",
      "context_available": true,
      "early_bullpen_entry_rate": 66.7,
      "top_three_workload_share_10d": 41.7,
      "window_days": 10
    }
  },
  "team_id": 120,
  "writer_targets": [
    "team_story",
    "dashboard",
    "morning_brief"
  ]
}
```

### Draft: team_story

Headline:
```
Lead protected
```
Opening:
```
After their most recent game, Zack Littell worked five innings and left with a four-run lead, and the bullpen brought it home.
```
Body:
```
After their most recent game, Zack Littell worked five innings and left with a four-run lead, and the bullpen brought it home. The clean finish keeps the relief corps down to a short list of clean arms.
```
What BaseballOS noticed / observations:
```
- The starter set the bullpen up to finish the game.
- The bullpen took over with a lead in hand.
- The relievers held the lead.
- The damage came after the starter exited and piled up late.
```
Evidence:
```
- Starter: Zack Littell, 5.0 IP, 82 pitches
- Largest lead: 4
- Bullpen entered in the 6th with a 3-run lead
- Turning point: 3rd inning
- Late runs allowed: 2
```
Exact rendered text:
```
Lead protected

After their most recent game, Zack Littell worked five innings and left with a four-run lead, and the bullpen brought it home. The clean finish keeps the relief corps down to a short list of clean arms.

Why BaseballOS sees it:
- The starter set the bullpen up to finish the game.
- The bullpen took over with a lead in hand.
- The relievers held the lead.
- The damage came after the starter exited and piled up late.

Evidence:
- Starter: Zack Littell, 5.0 IP, 82 pitches
- Largest lead: 4
- Bullpen entered in the 6th with a 3-run lead
- Turning point: 3rd inning
- Late runs allowed: 2
```


### Draft: dashboard

Headline:
```
Lead protected
```
Opening:
```
The club protected a 4-run lead.
```
Body:
```
The club protected a 4-run lead.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Zack Littell, 5.0 IP, 82 pitches
```
Exact rendered text:
```
Lead protected

The club protected a 4-run lead.

Evidence:
- Starter: Zack Littell, 5.0 IP, 82 pitches
```


### Draft: morning_brief

Headline:
```
Bullpen note: Lead protected
```
Opening:
```
After their most recent game, the club turned a four-run lead into a win the bullpen never let slip.
```
Body:
```
After their most recent game, the club turned a four-run lead into a win the bullpen never let slip. Available arms: Zak Kent. The relief corps is down to a short list of clean arms.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Zack Littell, 5.0 IP, 82 pitches
- Largest lead: 4
- Bullpen entered in the 6th with a 3-run lead
- Turning point: 3rd inning
- Late runs allowed: 2
```
Exact rendered text:
```
Bullpen note: Lead protected

After their most recent game, the club turned a four-run lead into a win the bullpen never let slip. Available arms: Zak Kent. The relief corps is down to a short list of clean arms.

Evidence:
- Starter: Zack Littell, 5.0 IP, 82 pitches
- Largest lead: 4
- Bullpen entered in the 6th with a 3-run lead
- Turning point: 3rd inning
- Late runs allowed: 2
```

## Completed-Game Story 14: New York Mets (NYM, 121)

### Story Metadata

```json
{
  "beat": "bullpen_overexposed",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_used": false,
  "game_date": "2026-06-28",
  "game_importance": "MEDIUM",
  "game_pk": 823608,
  "opponent_name": "Philadelphia Phillies",
  "publish_reason": "meets_confidence_threshold",
  "publishable": true,
  "recommended_surface": "team_page",
  "severity": "MEDIUM",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_type": "bullpen_overexposed",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 0,
      "context_available": true,
      "limited_arms_count": 8,
      "monitor_arms_count": 1,
      "optionality_band": "thin",
      "restricted_arms_count": 8,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [],
      "clean_options_count": 0,
      "context_available": true,
      "core_retention_count": 1,
      "depth_pressure_band": "heavy",
      "inactive_bullpen_arms_count": 10,
      "optionality_band": "thin",
      "practical_close_game_paths_count": 0,
      "secondary_options": [
        {
          "availability": "Monitor",
          "name": "A.J. Minter",
          "player_id": 621345,
          "reason": "22 pitches yesterday"
        }
      ],
      "secondary_options_count": 1,
      "stability_band": "transitioning"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 2,
      "bullpen_story_tag": "bullpen_overexposed",
      "comeback_completed": false,
      "confidence": "HIGH",
      "deficit_when_bullpen_entered": null,
      "final_score_against": 5,
      "final_score_for": 4,
      "game_date": "2026-06-28",
      "game_pk": 823608,
      "game_shape_created": "opener_bulk_game",
      "game_shape_protected": null,
      "generated_at": "2026-06-28T22:47:26.139656",
      "home_away": "home",
      "largest_deficit": 3,
      "largest_lead": 1,
      "late_runs_allowed": 2,
      "lead_lost": null,
      "lead_protected": null,
      "lead_when_bullpen_entered": null,
      "opponent_name": "Philadelphia Phillies",
      "runs_allowed_innings_7_to_9": 2,
      "starter_exit_inning": 1,
      "starter_ip": 1.0,
      "starter_name": "Cionel P\u00e9rez",
      "starter_pitch_count": 9,
      "team_id": 121,
      "turning_inning": 7
    },
    "confidence": "HIGH",
    "game_importance": "MEDIUM",
    "headline_key": "bullpen_overexposed",
    "primary_story": "bullpen_overexposed",
    "publish_reason": "meets_confidence_threshold",
    "publishable": true,
    "recommended_surface": "team_page",
    "safe_time_context": "AFTER_MOST_RECENT_GAME",
    "secondary_story": "late_pressure_accumulated",
    "story_priority": "MEDIUM",
    "summary_key": "bullpen_carried_heavy_load",
    "supporting_facts": {
      "bullpen_entry_inning": 2,
      "bullpen_entry_score_against": 0,
      "bullpen_entry_score_for": 0,
      "game_shape_created": "opener_bulk_game",
      "largest_deficit": 3,
      "largest_lead": 1,
      "late_runs_allowed": 2,
      "runs_allowed_innings_7_to_9": 2,
      "starter_exit_score_against": 0,
      "starter_exit_score_for": 0,
      "turning_inning": 7
    },
    "supporting_observations": [
      "starter_created_game_shape",
      "late_runs_allowed",
      "multiple_late_runs",
      "late_scoring_sequence",
      "bullpen_worked_long",
      "turning_point_identified"
    ],
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": 4.8,
      "bullpen_workload_appearances_10d": 26,
      "bullpen_workload_total_10d": 603,
      "concentration_band": "balanced",
      "context_available": true,
      "early_bullpen_entry_rate": 54.5,
      "top_three_workload_share_10d": 47.8,
      "window_days": 10
    }
  },
  "team_id": 121,
  "writer_targets": [
    "team_story",
    "dashboard"
  ]
}
```

### Draft: team_story

Headline:
```
Bullpen stretched thin
```
Opening:
```
After their most recent game, Cionel Pérez's one-inning start left the bullpen to cover the rest, including two late runs.
```
Body:
```
After their most recent game, Cionel Pérez's one-inning start left the bullpen to cover the rest, including two late runs.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Cionel Pérez, 1.0 IP, 9 pitches
- Largest lead: 1
- Bullpen entered in the 2nd
- Turning point: 7th inning
- Late runs allowed: 2
```
Exact rendered text:
```
Bullpen stretched thin

After their most recent game, Cionel Pérez's one-inning start left the bullpen to cover the rest, including two late runs.

Evidence:
- Starter: Cionel Pérez, 1.0 IP, 9 pitches
- Largest lead: 1
- Bullpen entered in the 2nd
- Turning point: 7th inning
- Late runs allowed: 2
```


### Draft: dashboard

Headline:
```
Bullpen stretched thin
```
Opening:
```
The club covered heavy innings on a short start.
```
Body:
```
The club covered heavy innings on a short start.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Cionel Pérez, 1.0 IP, 9 pitches
```
Exact rendered text:
```
Bullpen stretched thin

The club covered heavy innings on a short start.

Evidence:
- Starter: Cionel Pérez, 1.0 IP, 9 pitches
```

## Completed-Game Story 15: Athletics (ATH, 133)

### Story Metadata

```json
{
  "beat": "insufficient_context",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_used": true,
  "game_date": "2026-06-28",
  "game_importance": "LOW",
  "game_pk": 824011,
  "opponent_name": "Los Angeles Angels",
  "publish_reason": "insufficient_confidence",
  "publishable": false,
  "recommended_surface": "none",
  "severity": "LOW",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_type": "insufficient_context",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 0,
      "context_available": true,
      "limited_arms_count": 2,
      "monitor_arms_count": 4,
      "optionality_band": "thin",
      "restricted_arms_count": 3,
      "unavailable_arms_count": 1,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [],
      "clean_options_count": 0,
      "context_available": true,
      "core_retention_count": 1,
      "depth_pressure_band": "heavy",
      "inactive_bullpen_arms_count": 11,
      "optionality_band": "thin",
      "practical_close_game_paths_count": 2,
      "secondary_options": [
        {
          "availability": "Monitor",
          "name": "Hogan Harris",
          "player_id": 663687,
          "reason": "2 appearances in 5 days"
        },
        {
          "availability": "Monitor",
          "name": "Jos\u00e9 Suarez",
          "player_id": 660761,
          "reason": "No rest since last appearance"
        },
        {
          "availability": "Monitor",
          "name": "Luis Medina",
          "player_id": 665622,
          "reason": "38 pitches in 3 days"
        },
        {
          "availability": "Monitor",
          "name": "Mason Barnett",
          "player_id": 686930,
          "reason": "2 appearances in 5 days"
        }
      ],
      "secondary_options_count": 4,
      "stability_band": "transitioning"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 6,
      "bullpen_story_tag": "insufficient_context",
      "comeback_completed": false,
      "confidence": "HIGH",
      "deficit_when_bullpen_entered": 3,
      "final_score_against": 4,
      "final_score_for": 1,
      "game_date": "2026-06-28",
      "game_pk": 824011,
      "game_shape_created": "normal_start",
      "game_shape_protected": null,
      "generated_at": "2026-06-28T22:47:36.618944",
      "home_away": "away",
      "largest_deficit": 4,
      "largest_lead": 0,
      "late_runs_allowed": 0,
      "lead_lost": null,
      "lead_protected": null,
      "lead_when_bullpen_entered": null,
      "opponent_name": "Los Angeles Angels",
      "runs_allowed_innings_7_to_9": 0,
      "starter_exit_inning": 5,
      "starter_ip": 5.0,
      "starter_name": "Aaron Civale",
      "starter_pitch_count": 90,
      "team_id": 133,
      "turning_inning": null
    },
    "confidence": "HIGH",
    "game_importance": "LOW",
    "headline_key": "insufficient_context",
    "primary_story": "insufficient_context",
    "publish_reason": "insufficient_confidence",
    "publishable": false,
    "recommended_surface": "none",
    "safe_time_context": "CURRENT_STATUS",
    "secondary_story": null,
    "story_priority": "LOW",
    "summary_key": "insufficient_context",
    "supporting_facts": {},
    "supporting_observations": [],
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": 3.2,
      "bullpen_workload_appearances_10d": 21,
      "bullpen_workload_total_10d": 383,
      "concentration_band": "normal",
      "context_available": true,
      "early_bullpen_entry_rate": 46.2,
      "top_three_workload_share_10d": 59.8,
      "window_days": 10
    }
  },
  "team_id": 133,
  "writer_targets": []
}
```

No public drafts were rendered for this row by the existing writer targets.

## Completed-Game Story 16: Pittsburgh Pirates (PIT, 134)

### Story Metadata

```json
{
  "beat": "protected_game_shape",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_used": false,
  "game_date": "2026-06-28",
  "game_importance": "HIGH",
  "game_pk": 823362,
  "opponent_name": "Cincinnati Reds",
  "publish_reason": "high_priority_narrative",
  "publishable": true,
  "recommended_surface": "multiple",
  "severity": "HIGH",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_type": "protected_game_shape",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 1,
      "context_available": true,
      "limited_arms_count": 6,
      "monitor_arms_count": 1,
      "optionality_band": "thin",
      "restricted_arms_count": 6,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [
        {
          "availability": "Available",
          "last_workload": "2 days ago",
          "name": "Brandan Bidois",
          "player_id": 684049,
          "recent_workload": "light"
        }
      ],
      "clean_options_count": 1,
      "context_available": true,
      "core_retention_count": 1,
      "depth_pressure_band": "heavy",
      "inactive_bullpen_arms_count": 8,
      "optionality_band": "thin",
      "practical_close_game_paths_count": 1,
      "secondary_options": [
        {
          "availability": "Monitor",
          "name": "Evan Sisk",
          "player_id": 681895,
          "reason": "2 appearances in 5 days"
        }
      ],
      "secondary_options_count": 1,
      "stability_band": "transitioning"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 7,
      "bullpen_story_tag": "protected_game_shape",
      "comeback_completed": false,
      "confidence": "HIGH",
      "deficit_when_bullpen_entered": null,
      "final_score_against": 4,
      "final_score_for": 9,
      "game_date": "2026-06-28",
      "game_pk": 823362,
      "game_shape_created": "normal_start",
      "game_shape_protected": true,
      "generated_at": "2026-06-28T22:47:17.940036",
      "home_away": "home",
      "largest_deficit": 0,
      "largest_lead": 5,
      "late_runs_allowed": 0,
      "lead_lost": false,
      "lead_protected": true,
      "lead_when_bullpen_entered": 1,
      "opponent_name": "Cincinnati Reds",
      "runs_allowed_innings_7_to_9": 0,
      "starter_exit_inning": 6,
      "starter_ip": 6.0,
      "starter_name": "Mitch Keller",
      "starter_pitch_count": 79,
      "team_id": 134,
      "turning_inning": null
    },
    "confidence": "HIGH",
    "game_importance": "HIGH",
    "headline_key": "bullpen_stabilized",
    "primary_story": "protected_game_shape",
    "publish_reason": "high_priority_narrative",
    "publishable": true,
    "recommended_surface": "multiple",
    "safe_time_context": "AFTER_MOST_RECENT_GAME",
    "secondary_story": "starter_covered_bullpen",
    "story_priority": "HIGH",
    "summary_key": "game_shape_protected",
    "supporting_facts": {
      "bullpen_entry_inning": 7,
      "bullpen_entry_score_against": 4,
      "bullpen_entry_score_for": 5,
      "game_shape_created": "normal_start",
      "game_shape_protected": true,
      "largest_deficit": 0,
      "largest_lead": 5,
      "late_runs_allowed": 0,
      "lead_lost": false,
      "lead_protected": true,
      "runs_allowed_innings_7_to_9": 0,
      "starter_exit_score_against": 4,
      "starter_exit_score_for": 5
    },
    "supporting_observations": [
      "starter_created_game_shape",
      "deep_start",
      "lead_entering_bullpen",
      "bullpen_preserved_lead"
    ],
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": 3.8,
      "bullpen_workload_appearances_10d": 25,
      "bullpen_workload_total_10d": 526,
      "concentration_band": "balanced",
      "context_available": true,
      "early_bullpen_entry_rate": 50.0,
      "top_three_workload_share_10d": 50.8,
      "window_days": 10
    }
  },
  "team_id": 134,
  "writer_targets": [
    "team_story",
    "dashboard",
    "morning_brief"
  ]
}
```

### Draft: team_story

Headline:
```
Bullpen slammed the door
```
Opening:
```
After their most recent game, Mitch Keller worked six innings and left with a five-run lead, and the bullpen brought it home.
```
Body:
```
After their most recent game, Mitch Keller worked six innings and left with a five-run lead, and the bullpen brought it home. The clean finish keeps the relief corps down to fewer rested options.
```
What BaseballOS noticed / observations:
```
- The starter went deep and set the bullpen up to finish the game.
- The bullpen took over with a lead in hand.
- The relievers held the lead.
```
Evidence:
```
- Starter: Mitch Keller, 6.0 IP, 79 pitches
- Largest lead: 5
- Bullpen entered in the 7th with a 1-run lead
- Late runs allowed: 0
- Clean options: Brandan Bidois
```
Exact rendered text:
```
Bullpen slammed the door

After their most recent game, Mitch Keller worked six innings and left with a five-run lead, and the bullpen brought it home. The clean finish keeps the relief corps down to fewer rested options.

Why BaseballOS sees it:
- The starter went deep and set the bullpen up to finish the game.
- The bullpen took over with a lead in hand.
- The relievers held the lead.

Evidence:
- Starter: Mitch Keller, 6.0 IP, 79 pitches
- Largest lead: 5
- Bullpen entered in the 7th with a 1-run lead
- Late runs allowed: 0
- Clean options: Brandan Bidois
```


### Draft: dashboard

Headline:
```
Bullpen slammed the door
```
Opening:
```
The club protected a 5-run lead.
```
Body:
```
The club protected a 5-run lead.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Mitch Keller, 6.0 IP, 79 pitches
```
Exact rendered text:
```
Bullpen slammed the door

The club protected a 5-run lead.

Evidence:
- Starter: Mitch Keller, 6.0 IP, 79 pitches
```


### Draft: morning_brief

Headline:
```
Bullpen note: Bullpen slammed the door
```
Opening:
```
After their most recent game, the club turned a five-run lead into a win the bullpen never let slip.
```
Body:
```
After their most recent game, the club turned a five-run lead into a win the bullpen never let slip. Available arms: Brandan Bidois. The relief corps is down to fewer rested options.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Mitch Keller, 6.0 IP, 79 pitches
- Largest lead: 5
- Bullpen entered in the 7th with a 1-run lead
- Late runs allowed: 0
- Clean options: Brandan Bidois
```
Exact rendered text:
```
Bullpen note: Bullpen slammed the door

After their most recent game, the club turned a five-run lead into a win the bullpen never let slip. Available arms: Brandan Bidois. The relief corps is down to fewer rested options.

Evidence:
- Starter: Mitch Keller, 6.0 IP, 79 pitches
- Largest lead: 5
- Bullpen entered in the 7th with a 1-run lead
- Late runs allowed: 0
- Clean options: Brandan Bidois
```

## Completed-Game Story 17: San Diego Padres (SD, 135)

### Story Metadata

```json
{
  "beat": "bullpen_overexposed",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_used": false,
  "game_date": "2026-06-28",
  "game_importance": "LOW",
  "game_pk": 823281,
  "opponent_name": "Los Angeles Dodgers",
  "publish_reason": "meets_confidence_threshold",
  "publishable": true,
  "recommended_surface": "dashboard",
  "severity": "MEDIUM",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_type": "bullpen_overexposed",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 2,
      "context_available": true,
      "limited_arms_count": 3,
      "monitor_arms_count": 1,
      "optionality_band": "thin",
      "restricted_arms_count": 5,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [
        {
          "availability": "Available",
          "last_workload": "2 days ago",
          "name": "Adrian Morejon",
          "player_id": 670970,
          "recent_workload": "light"
        },
        {
          "availability": "Available",
          "last_workload": "5 days ago",
          "name": "Mason Miller",
          "player_id": 695243,
          "recent_workload": "none"
        }
      ],
      "clean_options_count": 2,
      "context_available": true,
      "core_retention_count": 1,
      "depth_pressure_band": "heavy",
      "inactive_bullpen_arms_count": 12,
      "optionality_band": "thin",
      "practical_close_game_paths_count": 2,
      "secondary_options": [
        {
          "availability": "Monitor",
          "name": "David Morgan",
          "player_id": 688158,
          "reason": "17 pitches yesterday"
        }
      ],
      "secondary_options_count": 1,
      "stability_band": "transitioning"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 5,
      "bullpen_story_tag": "bullpen_overexposed",
      "comeback_completed": false,
      "confidence": "HIGH",
      "deficit_when_bullpen_entered": 3,
      "final_score_against": 4,
      "final_score_for": 2,
      "game_date": "2026-06-28",
      "game_pk": 823281,
      "game_shape_created": "short_start",
      "game_shape_protected": null,
      "generated_at": "2026-06-28T23:33:23.053394",
      "home_away": "home",
      "largest_deficit": 3,
      "largest_lead": 0,
      "late_runs_allowed": 0,
      "lead_lost": null,
      "lead_protected": null,
      "lead_when_bullpen_entered": null,
      "opponent_name": "Los Angeles Dodgers",
      "runs_allowed_innings_7_to_9": 0,
      "starter_exit_inning": 5,
      "starter_ip": 4.33333333333333,
      "starter_name": "Michael King",
      "starter_pitch_count": 90,
      "team_id": 135,
      "turning_inning": null
    },
    "confidence": "HIGH",
    "game_importance": "LOW",
    "headline_key": "bullpen_overexposed",
    "primary_story": "bullpen_overexposed",
    "publish_reason": "meets_confidence_threshold",
    "publishable": true,
    "recommended_surface": "dashboard",
    "safe_time_context": "AFTER_MOST_RECENT_GAME",
    "secondary_story": null,
    "story_priority": "MEDIUM",
    "summary_key": "bullpen_carried_heavy_load",
    "supporting_facts": {
      "bullpen_entry_inning": 5,
      "bullpen_entry_score_against": 4,
      "bullpen_entry_score_for": 1,
      "game_shape_created": "short_start",
      "largest_deficit": 3,
      "largest_lead": 0,
      "late_runs_allowed": 0,
      "runs_allowed_innings_7_to_9": 0,
      "starter_exit_score_against": 4,
      "starter_exit_score_for": 1
    },
    "supporting_observations": [
      "deficit_entering_bullpen",
      "bullpen_worked_long"
    ],
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": 4.8,
      "bullpen_workload_appearances_10d": 31,
      "bullpen_workload_total_10d": 630,
      "concentration_band": "balanced",
      "context_available": true,
      "early_bullpen_entry_rate": 55.6,
      "top_three_workload_share_10d": 44.0,
      "window_days": 10
    }
  },
  "team_id": 135,
  "writer_targets": [
    "team_story",
    "dashboard"
  ]
}
```

### Draft: team_story

Headline:
```
Bullpen stretched thin
```
Opening:
```
After their most recent game, Michael King's 4.3-inning start left the bullpen to cover the rest.
```
Body:
```
After their most recent game, Michael King's 4.3-inning start left the bullpen to cover the rest.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Michael King, 4.3 IP, 90 pitches
- Largest deficit: 3
- Bullpen entered in the 5th trailing by 3
- Late runs allowed: 0
- Clean options: Adrian Morejon, Mason Miller
```
Exact rendered text:
```
Bullpen stretched thin

After their most recent game, Michael King's 4.3-inning start left the bullpen to cover the rest.

Evidence:
- Starter: Michael King, 4.3 IP, 90 pitches
- Largest deficit: 3
- Bullpen entered in the 5th trailing by 3
- Late runs allowed: 0
- Clean options: Adrian Morejon, Mason Miller
```


### Draft: dashboard

Headline:
```
Bullpen stretched thin
```
Opening:
```
The club covered heavy innings on a short start.
```
Body:
```
The club covered heavy innings on a short start.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Michael King, 4.3 IP, 90 pitches
```
Exact rendered text:
```
Bullpen stretched thin

The club covered heavy innings on a short start.

Evidence:
- Starter: Michael King, 4.3 IP, 90 pitches
```

## Completed-Game Story 18: Seattle Mariners (SEA, 136)

### Story Metadata

```json
{
  "beat": "lost_game_shape",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_used": false,
  "game_date": "2026-06-28",
  "game_importance": "MEDIUM",
  "game_pk": 824422,
  "opponent_name": "Cleveland Guardians",
  "publish_reason": "critical_narrative",
  "publishable": true,
  "recommended_surface": "multiple",
  "severity": "CRITICAL",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_type": "lost_game_shape",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 2,
      "context_available": true,
      "limited_arms_count": 2,
      "monitor_arms_count": 3,
      "optionality_band": "narrow",
      "restricted_arms_count": 2,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [
        {
          "availability": "Available",
          "last_workload": "2 days ago",
          "name": "Andr\u00e9s Mu\u00f1oz",
          "player_id": 662253,
          "recent_workload": "light"
        },
        {
          "availability": "Available",
          "last_workload": "4 days ago",
          "name": "Nick Davila",
          "player_id": 689546,
          "recent_workload": "moderate"
        }
      ],
      "clean_options_count": 2,
      "context_available": true,
      "core_retention_count": 1,
      "depth_pressure_band": "heavy",
      "inactive_bullpen_arms_count": 8,
      "optionality_band": "narrow",
      "practical_close_game_paths_count": 3,
      "secondary_options": [
        {
          "availability": "Monitor",
          "name": "Eduard Bazardo",
          "player_id": 660825,
          "reason": "2 appearances in 5 days"
        },
        {
          "availability": "Monitor",
          "name": "Josh Simpson",
          "player_id": 681006,
          "reason": "No rest since last appearance"
        },
        {
          "availability": "Monitor",
          "name": "Michael Rucker",
          "player_id": 621074,
          "reason": "2 appearances in 5 days"
        }
      ],
      "secondary_options_count": 3,
      "stability_band": "transitioning"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 6,
      "bullpen_story_tag": "lost_game_shape",
      "comeback_completed": false,
      "confidence": "HIGH",
      "deficit_when_bullpen_entered": null,
      "final_score_against": 6,
      "final_score_for": 5,
      "game_date": "2026-06-28",
      "game_pk": 824422,
      "game_shape_created": "normal_start",
      "game_shape_protected": false,
      "generated_at": "2026-06-28T22:47:24.172675",
      "home_away": "away",
      "largest_deficit": 2,
      "largest_lead": 3,
      "late_runs_allowed": 5,
      "lead_lost": true,
      "lead_protected": false,
      "lead_when_bullpen_entered": 3,
      "opponent_name": "Cleveland Guardians",
      "runs_allowed_innings_7_to_9": 5,
      "starter_exit_inning": 6,
      "starter_ip": 5.66666666666667,
      "starter_name": "Emerson Hancock",
      "starter_pitch_count": 98,
      "team_id": 136,
      "turning_inning": 8
    },
    "confidence": "HIGH",
    "game_importance": "MEDIUM",
    "headline_key": "lost_game_shape",
    "primary_story": "lost_game_shape",
    "publish_reason": "critical_narrative",
    "publishable": true,
    "recommended_surface": "multiple",
    "safe_time_context": "AFTER_MOST_RECENT_GAME",
    "secondary_story": "late_pressure_accumulated",
    "story_priority": "CRITICAL",
    "summary_key": "game_shape_not_protected",
    "supporting_facts": {
      "bullpen_entry_inning": 6,
      "bullpen_entry_score_against": 1,
      "bullpen_entry_score_for": 4,
      "game_shape_created": "normal_start",
      "game_shape_protected": false,
      "largest_deficit": 2,
      "largest_lead": 3,
      "late_runs_allowed": 5,
      "lead_lost": true,
      "lead_protected": false,
      "runs_allowed_innings_7_to_9": 5,
      "starter_exit_score_against": 1,
      "starter_exit_score_for": 4,
      "turning_inning": 8
    },
    "supporting_observations": [
      "starter_created_game_shape",
      "lead_entering_bullpen",
      "bullpen_lost_lead",
      "late_runs_allowed",
      "multiple_late_runs",
      "late_scoring_sequence",
      "turning_point_identified"
    ],
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": 2.7,
      "bullpen_workload_appearances_10d": 25,
      "bullpen_workload_total_10d": 406,
      "concentration_band": "balanced",
      "context_available": true,
      "early_bullpen_entry_rate": 41.7,
      "top_three_workload_share_10d": 41.4,
      "window_days": 10
    }
  },
  "team_id": 136,
  "writer_targets": [
    "team_story",
    "dashboard",
    "morning_brief"
  ]
}
```

### Draft: team_story

Headline:
```
Lead surrendered late
```
Opening:
```
After their most recent game, Emerson Hancock's 5.7 strong innings staked a three-run lead heading to the late innings.
```
Body:
```
After their most recent game, Emerson Hancock's 5.7 strong innings staked a three-run lead heading to the late innings. It didn't last. Five late runs turned the game. That late collapse leaves the relief corps down to a short list of clean arms.
```
What BaseballOS noticed / observations:
```
- The starter set the bullpen up to finish the game.
- The bullpen took over with a lead in hand.
- The relievers could not hold the lead.
- The damage came after the starter exited and piled up late.
```
Evidence:
```
- Starter: Emerson Hancock, 5.7 IP, 98 pitches
- Largest lead: 3
- Bullpen entered in the 6th with a 3-run lead
- Turning point: 8th inning
- Late runs allowed: 5
```
Exact rendered text:
```
Lead surrendered late

After their most recent game, Emerson Hancock's 5.7 strong innings staked a three-run lead heading to the late innings. It didn't last. Five late runs turned the game. That late collapse leaves the relief corps down to a short list of clean arms.

Why BaseballOS sees it:
- The starter set the bullpen up to finish the game.
- The bullpen took over with a lead in hand.
- The relievers could not hold the lead.
- The damage came after the starter exited and piled up late.

Evidence:
- Starter: Emerson Hancock, 5.7 IP, 98 pitches
- Largest lead: 3
- Bullpen entered in the 6th with a 3-run lead
- Turning point: 8th inning
- Late runs allowed: 5
```


### Draft: dashboard

Headline:
```
Lead surrendered late
```
Opening:
```
The club blew a 3-run lead late.
```
Body:
```
The club blew a 3-run lead late.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Emerson Hancock, 5.7 IP, 98 pitches
```
Exact rendered text:
```
Lead surrendered late

The club blew a 3-run lead late.

Evidence:
- Starter: Emerson Hancock, 5.7 IP, 98 pitches
```


### Draft: morning_brief

Headline:
```
Bullpen note: Lead surrendered late
```
Opening:
```
After their most recent game, the club carried a three-run lead into the late innings and let it get away on five late runs.
```
Body:
```
After their most recent game, the club carried a three-run lead into the late innings and let it get away on five late runs. Available arms: Andrés Muñoz, Nick Davila. Yesterday's late damage leaves the relief corps down to a short list of clean arms.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Emerson Hancock, 5.7 IP, 98 pitches
- Largest lead: 3
- Bullpen entered in the 6th with a 3-run lead
- Turning point: 8th inning
- Late runs allowed: 5
```
Exact rendered text:
```
Bullpen note: Lead surrendered late

After their most recent game, the club carried a three-run lead into the late innings and let it get away on five late runs. Available arms: Andrés Muñoz, Nick Davila. Yesterday's late damage leaves the relief corps down to a short list of clean arms.

Evidence:
- Starter: Emerson Hancock, 5.7 IP, 98 pitches
- Largest lead: 3
- Bullpen entered in the 6th with a 3-run lead
- Turning point: 8th inning
- Late runs allowed: 5
```

## Completed-Game Story 19: San Francisco Giants (SF, 137)

### Story Metadata

```json
{
  "beat": "protected_game_shape",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_used": false,
  "game_date": "2026-06-28",
  "game_importance": "MEDIUM",
  "game_pk": 823204,
  "opponent_name": "Atlanta Braves",
  "publish_reason": "high_priority_narrative",
  "publishable": true,
  "recommended_surface": "multiple",
  "severity": "HIGH",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_type": "protected_game_shape",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 1,
      "context_available": true,
      "limited_arms_count": 5,
      "monitor_arms_count": 1,
      "optionality_band": "thin",
      "restricted_arms_count": 5,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [
        {
          "availability": "Available",
          "last_workload": "8 days ago",
          "name": "JT Brubaker",
          "player_id": 664141,
          "recent_workload": "none"
        }
      ],
      "clean_options_count": 1,
      "context_available": true,
      "core_retention_count": 1,
      "depth_pressure_band": "heavy",
      "inactive_bullpen_arms_count": 14,
      "optionality_band": "thin",
      "practical_close_game_paths_count": 1,
      "secondary_options": [
        {
          "availability": "Monitor",
          "name": "Caleb Kilian",
          "player_id": 668873,
          "reason": "2 appearances in 5 days"
        }
      ],
      "secondary_options_count": 1,
      "stability_band": "transitioning"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 9,
      "bullpen_story_tag": "protected_game_shape",
      "comeback_completed": false,
      "confidence": "HIGH",
      "deficit_when_bullpen_entered": null,
      "final_score_against": 2,
      "final_score_for": 3,
      "game_date": "2026-06-28",
      "game_pk": 823204,
      "game_shape_created": "normal_start",
      "game_shape_protected": true,
      "generated_at": "2026-06-28T22:47:38.378323",
      "home_away": "home",
      "largest_deficit": 0,
      "largest_lead": 3,
      "late_runs_allowed": 2,
      "lead_lost": false,
      "lead_protected": true,
      "lead_when_bullpen_entered": 2,
      "opponent_name": "Atlanta Braves",
      "runs_allowed_innings_7_to_9": 2,
      "starter_exit_inning": 8,
      "starter_ip": 8.0,
      "starter_name": "Robbie Ray",
      "starter_pitch_count": 95,
      "team_id": 137,
      "turning_inning": null
    },
    "confidence": "HIGH",
    "game_importance": "MEDIUM",
    "headline_key": "protected_game_shape",
    "primary_story": "protected_game_shape",
    "publish_reason": "high_priority_narrative",
    "publishable": true,
    "recommended_surface": "multiple",
    "safe_time_context": "AFTER_MOST_RECENT_GAME",
    "secondary_story": "late_pressure_accumulated",
    "story_priority": "HIGH",
    "summary_key": "game_shape_protected",
    "supporting_facts": {
      "bullpen_entry_inning": 9,
      "bullpen_entry_score_against": 1,
      "bullpen_entry_score_for": 3,
      "game_shape_created": "normal_start",
      "game_shape_protected": true,
      "largest_deficit": 0,
      "largest_lead": 3,
      "late_runs_allowed": 2,
      "lead_lost": false,
      "lead_protected": true,
      "runs_allowed_innings_7_to_9": 2,
      "starter_exit_score_against": 1,
      "starter_exit_score_for": 3
    },
    "supporting_observations": [
      "starter_created_game_shape",
      "deep_start",
      "lead_entering_bullpen",
      "bullpen_preserved_lead",
      "late_runs_allowed",
      "multiple_late_runs",
      "late_scoring_sequence"
    ],
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": 2.2,
      "bullpen_workload_appearances_10d": 23,
      "bullpen_workload_total_10d": 370,
      "concentration_band": "balanced",
      "context_available": true,
      "early_bullpen_entry_rate": 20.0,
      "top_three_workload_share_10d": 45.1,
      "window_days": 10
    }
  },
  "team_id": 137,
  "writer_targets": [
    "team_story",
    "dashboard",
    "morning_brief"
  ]
}
```

### Draft: team_story

Headline:
```
Lead protected
```
Opening:
```
After their most recent game, Robbie Ray worked eight innings and left with a three-run lead, and the bullpen brought it home.
```
Body:
```
After their most recent game, Robbie Ray worked eight innings and left with a three-run lead, and the bullpen brought it home. The clean finish keeps the relief corps down to fewer rested options.
```
What BaseballOS noticed / observations:
```
- The starter went deep and set the bullpen up to finish the game.
- The bullpen took over with a lead in hand.
- The relievers held the lead.
- The damage came after the starter exited and piled up late.
```
Evidence:
```
- Starter: Robbie Ray, 8.0 IP, 95 pitches
- Largest lead: 3
- Bullpen entered in the 9th with a 2-run lead
- Late runs allowed: 2
- Clean options: JT Brubaker
```
Exact rendered text:
```
Lead protected

After their most recent game, Robbie Ray worked eight innings and left with a three-run lead, and the bullpen brought it home. The clean finish keeps the relief corps down to fewer rested options.

Why BaseballOS sees it:
- The starter went deep and set the bullpen up to finish the game.
- The bullpen took over with a lead in hand.
- The relievers held the lead.
- The damage came after the starter exited and piled up late.

Evidence:
- Starter: Robbie Ray, 8.0 IP, 95 pitches
- Largest lead: 3
- Bullpen entered in the 9th with a 2-run lead
- Late runs allowed: 2
- Clean options: JT Brubaker
```


### Draft: dashboard

Headline:
```
Lead protected
```
Opening:
```
The club protected a 3-run lead.
```
Body:
```
The club protected a 3-run lead.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Robbie Ray, 8.0 IP, 95 pitches
```
Exact rendered text:
```
Lead protected

The club protected a 3-run lead.

Evidence:
- Starter: Robbie Ray, 8.0 IP, 95 pitches
```


### Draft: morning_brief

Headline:
```
Bullpen note: Lead protected
```
Opening:
```
After their most recent game, the club turned a three-run lead into a win the bullpen never let slip.
```
Body:
```
After their most recent game, the club turned a three-run lead into a win the bullpen never let slip. Available arms: JT Brubaker. The relief corps is down to fewer rested options.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Robbie Ray, 8.0 IP, 95 pitches
- Largest lead: 3
- Bullpen entered in the 9th with a 2-run lead
- Late runs allowed: 2
- Clean options: JT Brubaker
```
Exact rendered text:
```
Bullpen note: Lead protected

After their most recent game, the club turned a three-run lead into a win the bullpen never let slip. Available arms: JT Brubaker. The relief corps is down to fewer rested options.

Evidence:
- Starter: Robbie Ray, 8.0 IP, 95 pitches
- Largest lead: 3
- Bullpen entered in the 9th with a 2-run lead
- Late runs allowed: 2
- Clean options: JT Brubaker
```

## Completed-Game Story 20: St. Louis Cardinals (STL, 138)

### Story Metadata

```json
{
  "beat": "protected_game_shape",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_used": false,
  "game_date": "2026-06-28",
  "game_importance": "MEDIUM",
  "game_pk": 823037,
  "opponent_name": "Miami Marlins",
  "publish_reason": "high_priority_narrative",
  "publishable": true,
  "recommended_surface": "multiple",
  "severity": "HIGH",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_type": "protected_game_shape",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 1,
      "context_available": true,
      "limited_arms_count": 3,
      "monitor_arms_count": 3,
      "optionality_band": "thin",
      "restricted_arms_count": 3,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [
        {
          "availability": "Available",
          "last_workload": "4 days ago",
          "name": "Gordon Graceffo",
          "player_id": 700669,
          "recent_workload": "moderate"
        }
      ],
      "clean_options_count": 1,
      "context_available": true,
      "core_retention_count": 1,
      "depth_pressure_band": "heavy",
      "inactive_bullpen_arms_count": 7,
      "optionality_band": "thin",
      "practical_close_game_paths_count": 2,
      "secondary_options": [
        {
          "availability": "Monitor",
          "name": "Matt Svanson",
          "player_id": 694335,
          "reason": "Only 1 day of rest"
        },
        {
          "availability": "Monitor",
          "name": "Riley O'Brien",
          "player_id": 676617,
          "reason": "No rest since last appearance"
        },
        {
          "availability": "Monitor",
          "name": "Ryne Stanek",
          "player_id": 592773,
          "reason": "No rest since last appearance"
        }
      ],
      "secondary_options_count": 3,
      "stability_band": "transitioning"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 6,
      "bullpen_story_tag": "protected_game_shape",
      "comeback_completed": false,
      "confidence": "HIGH",
      "deficit_when_bullpen_entered": null,
      "final_score_against": 1,
      "final_score_for": 2,
      "game_date": "2026-06-28",
      "game_pk": 823037,
      "game_shape_created": "normal_start",
      "game_shape_protected": true,
      "generated_at": "2026-06-28T22:47:34.670544",
      "home_away": "home",
      "largest_deficit": 0,
      "largest_lead": 2,
      "late_runs_allowed": 0,
      "lead_lost": false,
      "lead_protected": true,
      "lead_when_bullpen_entered": 1,
      "opponent_name": "Miami Marlins",
      "runs_allowed_innings_7_to_9": 0,
      "starter_exit_inning": 5,
      "starter_ip": 5.0,
      "starter_name": "Kyle Leahy",
      "starter_pitch_count": 87,
      "team_id": 138,
      "turning_inning": null
    },
    "confidence": "HIGH",
    "game_importance": "MEDIUM",
    "headline_key": "bullpen_stabilized",
    "primary_story": "protected_game_shape",
    "publish_reason": "high_priority_narrative",
    "publishable": true,
    "recommended_surface": "multiple",
    "safe_time_context": "AFTER_MOST_RECENT_GAME",
    "secondary_story": null,
    "story_priority": "HIGH",
    "summary_key": "game_shape_protected",
    "supporting_facts": {
      "bullpen_entry_inning": 6,
      "bullpen_entry_score_against": 1,
      "bullpen_entry_score_for": 2,
      "game_shape_created": "normal_start",
      "game_shape_protected": true,
      "largest_deficit": 0,
      "largest_lead": 2,
      "late_runs_allowed": 0,
      "lead_lost": false,
      "lead_protected": true,
      "runs_allowed_innings_7_to_9": 0,
      "starter_exit_score_against": 1,
      "starter_exit_score_for": 2
    },
    "supporting_observations": [
      "starter_created_game_shape",
      "lead_entering_bullpen",
      "bullpen_preserved_lead"
    ],
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": 2.8,
      "bullpen_workload_appearances_10d": 25,
      "bullpen_workload_total_10d": 421,
      "concentration_band": "balanced",
      "context_available": true,
      "early_bullpen_entry_rate": 41.7,
      "top_three_workload_share_10d": 54.4,
      "window_days": 10
    }
  },
  "team_id": 138,
  "writer_targets": [
    "team_story",
    "dashboard",
    "morning_brief"
  ]
}
```

### Draft: team_story

Headline:
```
Bullpen slammed the door
```
Opening:
```
After their most recent game, Kyle Leahy worked five innings and left with a two-run lead, and the bullpen brought it home.
```
Body:
```
After their most recent game, Kyle Leahy worked five innings and left with a two-run lead, and the bullpen brought it home. The clean finish keeps the relief corps down to fewer rested options.
```
What BaseballOS noticed / observations:
```
- The starter set the bullpen up to finish the game.
- The bullpen took over with a lead in hand.
- The relievers held the lead.
```
Evidence:
```
- Starter: Kyle Leahy, 5.0 IP, 87 pitches
- Largest lead: 2
- Bullpen entered in the 6th with a 1-run lead
- Late runs allowed: 0
- Clean options: Gordon Graceffo
```
Exact rendered text:
```
Bullpen slammed the door

After their most recent game, Kyle Leahy worked five innings and left with a two-run lead, and the bullpen brought it home. The clean finish keeps the relief corps down to fewer rested options.

Why BaseballOS sees it:
- The starter set the bullpen up to finish the game.
- The bullpen took over with a lead in hand.
- The relievers held the lead.

Evidence:
- Starter: Kyle Leahy, 5.0 IP, 87 pitches
- Largest lead: 2
- Bullpen entered in the 6th with a 1-run lead
- Late runs allowed: 0
- Clean options: Gordon Graceffo
```


### Draft: dashboard

Headline:
```
Bullpen slammed the door
```
Opening:
```
The club protected a 2-run lead.
```
Body:
```
The club protected a 2-run lead.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Kyle Leahy, 5.0 IP, 87 pitches
```
Exact rendered text:
```
Bullpen slammed the door

The club protected a 2-run lead.

Evidence:
- Starter: Kyle Leahy, 5.0 IP, 87 pitches
```


### Draft: morning_brief

Headline:
```
Bullpen note: Bullpen slammed the door
```
Opening:
```
After their most recent game, the club turned a two-run lead into a win the bullpen never let slip.
```
Body:
```
After their most recent game, the club turned a two-run lead into a win the bullpen never let slip. Available arms: Gordon Graceffo. The relief corps is down to fewer rested options.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Kyle Leahy, 5.0 IP, 87 pitches
- Largest lead: 2
- Bullpen entered in the 6th with a 1-run lead
- Late runs allowed: 0
- Clean options: Gordon Graceffo
```
Exact rendered text:
```
Bullpen note: Bullpen slammed the door

After their most recent game, the club turned a two-run lead into a win the bullpen never let slip. Available arms: Gordon Graceffo. The relief corps is down to fewer rested options.

Evidence:
- Starter: Kyle Leahy, 5.0 IP, 87 pitches
- Largest lead: 2
- Bullpen entered in the 6th with a 1-run lead
- Late runs allowed: 0
- Clean options: Gordon Graceffo
```

## Completed-Game Story 21: Tampa Bay Rays (TB, 139)

### Story Metadata

```json
{
  "beat": "protected_game_shape",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_used": false,
  "game_date": "2026-06-28",
  "game_importance": "HIGH",
  "game_pk": 822959,
  "opponent_name": "Arizona Diamondbacks",
  "publish_reason": "high_priority_narrative",
  "publishable": true,
  "recommended_surface": "multiple",
  "severity": "HIGH",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_type": "protected_game_shape",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 2,
      "context_available": true,
      "limited_arms_count": 4,
      "monitor_arms_count": 2,
      "optionality_band": "narrow",
      "restricted_arms_count": 5,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [
        {
          "availability": "Available",
          "last_workload": "2 days ago",
          "name": "Cam Booser",
          "player_id": 592155,
          "recent_workload": "light"
        },
        {
          "availability": "Available",
          "last_workload": "3 days ago",
          "name": "Ian Seymour",
          "player_id": 693855,
          "recent_workload": "moderate"
        }
      ],
      "clean_options_count": 2,
      "context_available": true,
      "core_retention_count": 0,
      "depth_pressure_band": "heavy",
      "inactive_bullpen_arms_count": 14,
      "optionality_band": "narrow",
      "practical_close_game_paths_count": 3,
      "secondary_options": [
        {
          "availability": "Monitor",
          "name": "Bryan Baker",
          "player_id": 641329,
          "reason": "2 appearances in 5 days"
        },
        {
          "availability": "Monitor",
          "name": "Trevor Martin",
          "player_id": 694680,
          "reason": "No rest since last appearance"
        }
      ],
      "secondary_options_count": 2,
      "stability_band": "rebuilding"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 7,
      "bullpen_story_tag": "protected_game_shape",
      "comeback_completed": false,
      "confidence": "HIGH",
      "deficit_when_bullpen_entered": null,
      "final_score_against": 1,
      "final_score_for": 5,
      "game_date": "2026-06-28",
      "game_pk": 822959,
      "game_shape_created": "normal_start",
      "game_shape_protected": true,
      "generated_at": "2026-06-28T20:08:19.302262",
      "home_away": "home",
      "largest_deficit": 0,
      "largest_lead": 5,
      "late_runs_allowed": 1,
      "lead_lost": false,
      "lead_protected": true,
      "lead_when_bullpen_entered": 5,
      "opponent_name": "Arizona Diamondbacks",
      "runs_allowed_innings_7_to_9": 1,
      "starter_exit_inning": 6,
      "starter_ip": 6.0,
      "starter_name": "Drew Rasmussen",
      "starter_pitch_count": 99,
      "team_id": 139,
      "turning_inning": null
    },
    "confidence": "HIGH",
    "game_importance": "HIGH",
    "headline_key": "protected_game_shape",
    "primary_story": "protected_game_shape",
    "publish_reason": "high_priority_narrative",
    "publishable": true,
    "recommended_surface": "multiple",
    "safe_time_context": "AFTER_MOST_RECENT_GAME",
    "secondary_story": null,
    "story_priority": "HIGH",
    "summary_key": "game_shape_protected",
    "supporting_facts": {
      "bullpen_entry_inning": 7,
      "bullpen_entry_score_against": 0,
      "bullpen_entry_score_for": 5,
      "game_shape_created": "normal_start",
      "game_shape_protected": true,
      "largest_deficit": 0,
      "largest_lead": 5,
      "late_runs_allowed": 1,
      "lead_lost": false,
      "lead_protected": true,
      "runs_allowed_innings_7_to_9": 1,
      "starter_exit_score_against": 0,
      "starter_exit_score_for": 4
    },
    "supporting_observations": [
      "starter_created_game_shape",
      "deep_start",
      "lead_entering_bullpen",
      "bullpen_preserved_lead",
      "late_runs_allowed"
    ],
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": 4.3,
      "bullpen_workload_appearances_10d": 29,
      "bullpen_workload_total_10d": 484,
      "concentration_band": "balanced",
      "context_available": true,
      "early_bullpen_entry_rate": 36.4,
      "top_three_workload_share_10d": 45.9,
      "window_days": 10
    }
  },
  "team_id": 139,
  "writer_targets": [
    "team_story",
    "dashboard",
    "morning_brief"
  ]
}
```

### Draft: team_story

Headline:
```
Lead protected
```
Opening:
```
After their most recent game, Drew Rasmussen worked six innings and left with a five-run lead, and the bullpen brought it home.
```
Body:
```
After their most recent game, Drew Rasmussen worked six innings and left with a five-run lead, and the bullpen brought it home. The clean finish keeps the relief corps down to a short list of clean arms.
```
What BaseballOS noticed / observations:
```
- The starter went deep and set the bullpen up to finish the game.
- The bullpen took over with a lead in hand.
- The relievers held the lead.
- The damage came after the starter exited.
```
Evidence:
```
- Starter: Drew Rasmussen, 6.0 IP, 99 pitches
- Largest lead: 5
- Bullpen entered in the 7th with a 5-run lead
- Late runs allowed: 1
- Clean options: Cam Booser, Ian Seymour
```
Exact rendered text:
```
Lead protected

After their most recent game, Drew Rasmussen worked six innings and left with a five-run lead, and the bullpen brought it home. The clean finish keeps the relief corps down to a short list of clean arms.

Why BaseballOS sees it:
- The starter went deep and set the bullpen up to finish the game.
- The bullpen took over with a lead in hand.
- The relievers held the lead.
- The damage came after the starter exited.

Evidence:
- Starter: Drew Rasmussen, 6.0 IP, 99 pitches
- Largest lead: 5
- Bullpen entered in the 7th with a 5-run lead
- Late runs allowed: 1
- Clean options: Cam Booser, Ian Seymour
```


### Draft: dashboard

Headline:
```
Lead protected
```
Opening:
```
The club protected a 5-run lead.
```
Body:
```
The club protected a 5-run lead.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Drew Rasmussen, 6.0 IP, 99 pitches
```
Exact rendered text:
```
Lead protected

The club protected a 5-run lead.

Evidence:
- Starter: Drew Rasmussen, 6.0 IP, 99 pitches
```


### Draft: morning_brief

Headline:
```
Bullpen note: Lead protected
```
Opening:
```
After their most recent game, the club turned a five-run lead into a win the bullpen never let slip.
```
Body:
```
After their most recent game, the club turned a five-run lead into a win the bullpen never let slip. Available arms: Cam Booser, Ian Seymour. The relief corps is down to a short list of clean arms.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Drew Rasmussen, 6.0 IP, 99 pitches
- Largest lead: 5
- Bullpen entered in the 7th with a 5-run lead
- Late runs allowed: 1
- Clean options: Cam Booser, Ian Seymour
```
Exact rendered text:
```
Bullpen note: Lead protected

After their most recent game, the club turned a five-run lead into a win the bullpen never let slip. Available arms: Cam Booser, Ian Seymour. The relief corps is down to a short list of clean arms.

Evidence:
- Starter: Drew Rasmussen, 6.0 IP, 99 pitches
- Largest lead: 5
- Bullpen entered in the 7th with a 5-run lead
- Late runs allowed: 1
- Clean options: Cam Booser, Ian Seymour
```

## Completed-Game Story 22: Texas Rangers (TEX, 140)

### Story Metadata

```json
{
  "beat": "protected_game_shape",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_used": false,
  "game_date": "2026-06-28",
  "game_importance": "MEDIUM",
  "game_pk": 822795,
  "opponent_name": "Toronto Blue Jays",
  "publish_reason": "high_priority_narrative",
  "publishable": true,
  "recommended_surface": "multiple",
  "severity": "HIGH",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_type": "protected_game_shape",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 0,
      "context_available": true,
      "limited_arms_count": 5,
      "monitor_arms_count": 1,
      "optionality_band": "thin",
      "restricted_arms_count": 7,
      "unavailable_arms_count": 1,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [],
      "clean_options_count": 0,
      "context_available": true,
      "core_retention_count": 0,
      "depth_pressure_band": "heavy",
      "inactive_bullpen_arms_count": 12,
      "optionality_band": "thin",
      "practical_close_game_paths_count": 0,
      "secondary_options": [
        {
          "availability": "Monitor",
          "name": "Cole Winn",
          "player_id": 668390,
          "reason": "2 appearances in 5 days"
        }
      ],
      "secondary_options_count": 1,
      "stability_band": "rebuilding"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 7,
      "bullpen_story_tag": "protected_game_shape",
      "comeback_completed": false,
      "confidence": "HIGH",
      "deficit_when_bullpen_entered": null,
      "final_score_against": 2,
      "final_score_for": 3,
      "game_date": "2026-06-28",
      "game_pk": 822795,
      "game_shape_created": "normal_start",
      "game_shape_protected": true,
      "generated_at": "2026-06-28T22:47:19.701606",
      "home_away": "away",
      "largest_deficit": 0,
      "largest_lead": 2,
      "late_runs_allowed": 2,
      "lead_lost": false,
      "lead_protected": true,
      "lead_when_bullpen_entered": 2,
      "opponent_name": "Toronto Blue Jays",
      "runs_allowed_innings_7_to_9": 2,
      "starter_exit_inning": 6,
      "starter_ip": 6.0,
      "starter_name": "Kumar Rocker",
      "starter_pitch_count": 92,
      "team_id": 140,
      "turning_inning": null
    },
    "confidence": "HIGH",
    "game_importance": "MEDIUM",
    "headline_key": "protected_game_shape",
    "primary_story": "protected_game_shape",
    "publish_reason": "high_priority_narrative",
    "publishable": true,
    "recommended_surface": "multiple",
    "safe_time_context": "AFTER_MOST_RECENT_GAME",
    "secondary_story": "late_pressure_accumulated",
    "story_priority": "HIGH",
    "summary_key": "game_shape_protected",
    "supporting_facts": {
      "bullpen_entry_inning": 7,
      "bullpen_entry_score_against": 0,
      "bullpen_entry_score_for": 2,
      "game_shape_created": "normal_start",
      "game_shape_protected": true,
      "largest_deficit": 0,
      "largest_lead": 2,
      "late_runs_allowed": 2,
      "lead_lost": false,
      "lead_protected": true,
      "runs_allowed_innings_7_to_9": 2,
      "starter_exit_score_against": 0,
      "starter_exit_score_for": 2
    },
    "supporting_observations": [
      "starter_created_game_shape",
      "deep_start",
      "lead_entering_bullpen",
      "bullpen_preserved_lead",
      "late_runs_allowed",
      "multiple_late_runs",
      "late_scoring_sequence"
    ],
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": 3.8,
      "bullpen_workload_appearances_10d": 28,
      "bullpen_workload_total_10d": 498,
      "concentration_band": "normal",
      "context_available": true,
      "early_bullpen_entry_rate": 45.5,
      "top_three_workload_share_10d": 55.8,
      "window_days": 10
    }
  },
  "team_id": 140,
  "writer_targets": [
    "team_story",
    "dashboard",
    "morning_brief"
  ]
}
```

### Draft: team_story

Headline:
```
Lead protected
```
Opening:
```
After their most recent game, Kumar Rocker worked six innings and left with a two-run lead, and the bullpen brought it home.
```
Body:
```
After their most recent game, Kumar Rocker worked six innings and left with a two-run lead, and the bullpen brought it home. The clean finish keeps the relief corps down to fewer rested options.
```
What BaseballOS noticed / observations:
```
- The starter went deep and set the bullpen up to finish the game.
- The bullpen took over with a lead in hand.
- The relievers held the lead.
- The damage came after the starter exited and piled up late.
```
Evidence:
```
- Starter: Kumar Rocker, 6.0 IP, 92 pitches
- Largest lead: 2
- Bullpen entered in the 7th with a 2-run lead
- Late runs allowed: 2
```
Exact rendered text:
```
Lead protected

After their most recent game, Kumar Rocker worked six innings and left with a two-run lead, and the bullpen brought it home. The clean finish keeps the relief corps down to fewer rested options.

Why BaseballOS sees it:
- The starter went deep and set the bullpen up to finish the game.
- The bullpen took over with a lead in hand.
- The relievers held the lead.
- The damage came after the starter exited and piled up late.

Evidence:
- Starter: Kumar Rocker, 6.0 IP, 92 pitches
- Largest lead: 2
- Bullpen entered in the 7th with a 2-run lead
- Late runs allowed: 2
```


### Draft: dashboard

Headline:
```
Lead protected
```
Opening:
```
The club protected a 2-run lead.
```
Body:
```
The club protected a 2-run lead.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Kumar Rocker, 6.0 IP, 92 pitches
```
Exact rendered text:
```
Lead protected

The club protected a 2-run lead.

Evidence:
- Starter: Kumar Rocker, 6.0 IP, 92 pitches
```


### Draft: morning_brief

Headline:
```
Bullpen note: Lead protected
```
Opening:
```
After their most recent game, the club turned a two-run lead into a win the bullpen never let slip.
```
Body:
```
After their most recent game, the club turned a two-run lead into a win the bullpen never let slip. Available arms: 0. The relief corps is down to fewer rested options.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Kumar Rocker, 6.0 IP, 92 pitches
- Largest lead: 2
- Bullpen entered in the 7th with a 2-run lead
- Late runs allowed: 2
```
Exact rendered text:
```
Bullpen note: Lead protected

After their most recent game, the club turned a two-run lead into a win the bullpen never let slip. Available arms: 0. The relief corps is down to fewer rested options.

Evidence:
- Starter: Kumar Rocker, 6.0 IP, 92 pitches
- Largest lead: 2
- Bullpen entered in the 7th with a 2-run lead
- Late runs allowed: 2
```

## Completed-Game Story 23: Toronto Blue Jays (TOR, 141)

### Story Metadata

```json
{
  "beat": "insufficient_context",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_used": true,
  "game_date": "2026-06-28",
  "game_importance": "LOW",
  "game_pk": 822795,
  "opponent_name": "Texas Rangers",
  "publish_reason": "insufficient_confidence",
  "publishable": false,
  "recommended_surface": "none",
  "severity": "LOW",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_type": "insufficient_context",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 0,
      "context_available": true,
      "limited_arms_count": 2,
      "monitor_arms_count": 5,
      "optionality_band": "thin",
      "restricted_arms_count": 3,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [],
      "clean_options_count": 0,
      "context_available": true,
      "core_retention_count": 1,
      "depth_pressure_band": "heavy",
      "inactive_bullpen_arms_count": 12,
      "optionality_band": "thin",
      "practical_close_game_paths_count": 2,
      "secondary_options": [
        {
          "availability": "Monitor",
          "name": "Braydon Fisher",
          "player_id": 680755,
          "reason": "Only 1 day of rest"
        },
        {
          "availability": "Monitor",
          "name": "Mason Fluharty",
          "player_id": 689254,
          "reason": "2 appearances in 5 days"
        },
        {
          "availability": "Monitor",
          "name": "Spencer Miles",
          "player_id": 693686,
          "reason": "35 pitches in 3 days"
        },
        {
          "availability": "Monitor",
          "name": "Tommy Nance",
          "player_id": 667297,
          "reason": "2 appearances in 5 days"
        },
        {
          "availability": "Monitor",
          "name": "Tyler Rogers",
          "player_id": 643511,
          "reason": "22 pitches yesterday"
        }
      ],
      "secondary_options_count": 5,
      "stability_band": "transitioning"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 6,
      "bullpen_story_tag": "insufficient_context",
      "comeback_completed": false,
      "confidence": "HIGH",
      "deficit_when_bullpen_entered": 1,
      "final_score_against": 3,
      "final_score_for": 2,
      "game_date": "2026-06-28",
      "game_pk": 822795,
      "game_shape_created": "normal_start",
      "game_shape_protected": null,
      "generated_at": "2026-06-28T22:47:19.701480",
      "home_away": "home",
      "largest_deficit": 2,
      "largest_lead": 0,
      "late_runs_allowed": 1,
      "lead_lost": null,
      "lead_protected": null,
      "lead_when_bullpen_entered": null,
      "opponent_name": "Texas Rangers",
      "runs_allowed_innings_7_to_9": 1,
      "starter_exit_inning": 6,
      "starter_ip": 5.33333333333333,
      "starter_name": "Shane Bieber",
      "starter_pitch_count": 92,
      "team_id": 141,
      "turning_inning": null
    },
    "confidence": "HIGH",
    "game_importance": "LOW",
    "headline_key": "insufficient_context",
    "primary_story": "insufficient_context",
    "publish_reason": "insufficient_confidence",
    "publishable": false,
    "recommended_surface": "none",
    "safe_time_context": "CURRENT_STATUS",
    "secondary_story": null,
    "story_priority": "LOW",
    "summary_key": "insufficient_context",
    "supporting_facts": {},
    "supporting_observations": [],
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": 4.3,
      "bullpen_workload_appearances_10d": 33,
      "bullpen_workload_total_10d": 683,
      "concentration_band": "balanced",
      "context_available": true,
      "early_bullpen_entry_rate": 72.7,
      "top_three_workload_share_10d": 38.4,
      "window_days": 10
    }
  },
  "team_id": 141,
  "writer_targets": []
}
```

No public drafts were rendered for this row by the existing writer targets.

## Completed-Game Story 24: Minnesota Twins (MIN, 142)

### Story Metadata

```json
{
  "beat": "bullpen_kept_team_alive",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_used": false,
  "game_date": "2026-06-28",
  "game_importance": "LOW",
  "game_pk": 823686,
  "opponent_name": "Colorado Rockies",
  "publish_reason": "high_priority_narrative",
  "publishable": true,
  "recommended_surface": "multiple",
  "severity": "HIGH",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_type": "bullpen_kept_team_alive",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 2,
      "context_available": true,
      "limited_arms_count": 2,
      "monitor_arms_count": 2,
      "optionality_band": "narrow",
      "restricted_arms_count": 4,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [
        {
          "availability": "Available",
          "last_workload": "2 days ago",
          "name": "Eric Orze",
          "player_id": 679358,
          "recent_workload": "light"
        },
        {
          "availability": "Available",
          "last_workload": "5 days ago",
          "name": "Travis Adams",
          "player_id": 701519,
          "recent_workload": "none"
        }
      ],
      "clean_options_count": 2,
      "context_available": true,
      "core_retention_count": 2,
      "depth_pressure_band": "heavy",
      "inactive_bullpen_arms_count": 9,
      "optionality_band": "narrow",
      "practical_close_game_paths_count": 3,
      "secondary_options": [
        {
          "availability": "Monitor",
          "name": "Taylor Rogers",
          "player_id": 573124,
          "reason": "Only 1 day of rest"
        },
        {
          "availability": "Monitor",
          "name": "Yoendrys G\u00f3mez",
          "player_id": 672782,
          "reason": "2 appearances in 5 days"
        }
      ],
      "secondary_options_count": 2,
      "stability_band": "mostly_stable"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 7,
      "bullpen_story_tag": "bullpen_kept_team_alive",
      "comeback_completed": true,
      "confidence": "HIGH",
      "deficit_when_bullpen_entered": null,
      "final_score_against": 2,
      "final_score_for": 3,
      "game_date": "2026-06-28",
      "game_pk": 823686,
      "game_shape_created": "normal_start",
      "game_shape_protected": null,
      "generated_at": "2026-06-28T22:47:28.032762",
      "home_away": "home",
      "largest_deficit": 1,
      "largest_lead": 1,
      "late_runs_allowed": 0,
      "lead_lost": null,
      "lead_protected": null,
      "lead_when_bullpen_entered": null,
      "opponent_name": "Colorado Rockies",
      "runs_allowed_innings_7_to_9": 0,
      "starter_exit_inning": 6,
      "starter_ip": 6.0,
      "starter_name": "Connor Prielipp",
      "starter_pitch_count": 93,
      "team_id": 142,
      "turning_inning": 4
    },
    "confidence": "HIGH",
    "game_importance": "LOW",
    "headline_key": "bullpen_kept_team_alive",
    "primary_story": "bullpen_kept_team_alive",
    "publish_reason": "high_priority_narrative",
    "publishable": true,
    "recommended_surface": "multiple",
    "safe_time_context": "AFTER_MOST_RECENT_GAME",
    "secondary_story": "starter_covered_bullpen",
    "story_priority": "HIGH",
    "summary_key": "bullpen_preserved_comeback",
    "supporting_facts": {
      "bullpen_entry_inning": 7,
      "bullpen_entry_score_against": 2,
      "bullpen_entry_score_for": 2,
      "game_shape_created": "normal_start",
      "largest_deficit": 1,
      "largest_lead": 1,
      "late_runs_allowed": 0,
      "runs_allowed_innings_7_to_9": 0,
      "starter_exit_score_against": 2,
      "starter_exit_score_for": 2,
      "turning_inning": 4
    },
    "supporting_observations": [
      "starter_created_game_shape",
      "deep_start",
      "comeback_completed",
      "turning_point_identified"
    ],
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": 3.2,
      "bullpen_workload_appearances_10d": 27,
      "bullpen_workload_total_10d": 439,
      "concentration_band": "balanced",
      "context_available": true,
      "early_bullpen_entry_rate": 36.4,
      "top_three_workload_share_10d": 44.4,
      "window_days": 10
    }
  },
  "team_id": 142,
  "writer_targets": [
    "team_story",
    "dashboard",
    "morning_brief"
  ]
}
```

### Draft: team_story

Headline:
```
Bullpen kept it alive
```
Opening:
```
After their most recent game, Connor Prielipp's six innings left a one-run deficit to erase, but the bullpen kept it from growing.
```
Body:
```
After their most recent game, Connor Prielipp's six innings left a one-run deficit to erase, but the bullpen kept it from growing. The offense finished the rally. The comeback leaned on the bullpen, and the relief corps is down to a short list of clean arms.
```
What BaseballOS noticed / observations:
```
- The starter went deep and set the bullpen up to finish the game.
- The offense finished the comeback the bullpen kept alive.
- One late inning swung the game.
```
Evidence:
```
- Starter: Connor Prielipp, 6.0 IP, 93 pitches
- Largest deficit: 1
- Bullpen entered in the 7th
- Turning point: 4th inning
- Late runs allowed: 0
```
Exact rendered text:
```
Bullpen kept it alive

After their most recent game, Connor Prielipp's six innings left a one-run deficit to erase, but the bullpen kept it from growing. The offense finished the rally. The comeback leaned on the bullpen, and the relief corps is down to a short list of clean arms.

Why BaseballOS sees it:
- The starter went deep and set the bullpen up to finish the game.
- The offense finished the comeback the bullpen kept alive.
- One late inning swung the game.

Evidence:
- Starter: Connor Prielipp, 6.0 IP, 93 pitches
- Largest deficit: 1
- Bullpen entered in the 7th
- Turning point: 4th inning
- Late runs allowed: 0
```


### Draft: dashboard

Headline:
```
Bullpen kept it alive
```
Opening:
```
The club kept the comeback alive.
```
Body:
```
The club kept the comeback alive.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Connor Prielipp, 6.0 IP, 93 pitches
```
Exact rendered text:
```
Bullpen kept it alive

The club kept the comeback alive.

Evidence:
- Starter: Connor Prielipp, 6.0 IP, 93 pitches
```


### Draft: morning_brief

Headline:
```
Bullpen note: Bullpen kept it alive
```
Opening:
```
After their most recent game, the club climbed out of a one-run hole the bullpen kept from growing.
```
Body:
```
After their most recent game, the club climbed out of a one-run hole the bullpen kept from growing. Available arms: Eric Orze, Travis Adams. The relief corps is down to a short list of clean arms.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Connor Prielipp, 6.0 IP, 93 pitches
- Largest deficit: 1
- Bullpen entered in the 7th
- Turning point: 4th inning
- Late runs allowed: 0
```
Exact rendered text:
```
Bullpen note: Bullpen kept it alive

After their most recent game, the club climbed out of a one-run hole the bullpen kept from growing. Available arms: Eric Orze, Travis Adams. The relief corps is down to a short list of clean arms.

Evidence:
- Starter: Connor Prielipp, 6.0 IP, 93 pitches
- Largest deficit: 1
- Bullpen entered in the 7th
- Turning point: 4th inning
- Late runs allowed: 0
```

## Completed-Game Story 25: Philadelphia Phillies (PHI, 143)

### Story Metadata

```json
{
  "beat": "protected_game_shape",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_used": false,
  "game_date": "2026-06-28",
  "game_importance": "MEDIUM",
  "game_pk": 823608,
  "opponent_name": "New York Mets",
  "publish_reason": "high_priority_narrative",
  "publishable": true,
  "recommended_surface": "multiple",
  "severity": "HIGH",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_type": "protected_game_shape",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 0,
      "context_available": true,
      "limited_arms_count": 4,
      "monitor_arms_count": 2,
      "optionality_band": "thin",
      "restricted_arms_count": 7,
      "unavailable_arms_count": 1,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [],
      "clean_options_count": 0,
      "context_available": true,
      "core_retention_count": 0,
      "depth_pressure_band": "heavy",
      "inactive_bullpen_arms_count": 8,
      "optionality_band": "thin",
      "practical_close_game_paths_count": 1,
      "secondary_options": [
        {
          "availability": "Monitor",
          "name": "Jonathan Bowlan",
          "player_id": 680742,
          "reason": "2 appearances in 5 days"
        },
        {
          "availability": "Monitor",
          "name": "Seth Johnson",
          "player_id": 686751,
          "reason": "16 pitches yesterday"
        }
      ],
      "secondary_options_count": 2,
      "stability_band": "rebuilding"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 6,
      "bullpen_story_tag": "protected_game_shape",
      "comeback_completed": true,
      "confidence": "HIGH",
      "deficit_when_bullpen_entered": null,
      "final_score_against": 4,
      "final_score_for": 5,
      "game_date": "2026-06-28",
      "game_pk": 823608,
      "game_shape_created": "normal_start",
      "game_shape_protected": true,
      "generated_at": "2026-06-28T22:47:26.139791",
      "home_away": "away",
      "largest_deficit": 1,
      "largest_lead": 3,
      "late_runs_allowed": 0,
      "lead_lost": false,
      "lead_protected": true,
      "lead_when_bullpen_entered": 2,
      "opponent_name": "New York Mets",
      "runs_allowed_innings_7_to_9": 0,
      "starter_exit_inning": 5,
      "starter_ip": 5.0,
      "starter_name": "Jes\u00fas Luzardo",
      "starter_pitch_count": 96,
      "team_id": 143,
      "turning_inning": 7
    },
    "confidence": "HIGH",
    "game_importance": "MEDIUM",
    "headline_key": "bullpen_stabilized",
    "primary_story": "protected_game_shape",
    "publish_reason": "high_priority_narrative",
    "publishable": true,
    "recommended_surface": "multiple",
    "safe_time_context": "AFTER_MOST_RECENT_GAME",
    "secondary_story": "bullpen_kept_team_alive",
    "story_priority": "HIGH",
    "summary_key": "game_shape_protected",
    "supporting_facts": {
      "bullpen_entry_inning": 6,
      "bullpen_entry_score_against": 1,
      "bullpen_entry_score_for": 3,
      "game_shape_created": "normal_start",
      "game_shape_protected": true,
      "largest_deficit": 1,
      "largest_lead": 3,
      "late_runs_allowed": 0,
      "lead_lost": false,
      "lead_protected": true,
      "runs_allowed_innings_7_to_9": 0,
      "starter_exit_score_against": 1,
      "starter_exit_score_for": 3,
      "turning_inning": 7
    },
    "supporting_observations": [
      "starter_created_game_shape",
      "lead_entering_bullpen",
      "bullpen_preserved_lead",
      "comeback_completed",
      "turning_point_identified"
    ],
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": 4.7,
      "bullpen_workload_appearances_10d": 30,
      "bullpen_workload_total_10d": 478,
      "concentration_band": "balanced",
      "context_available": true,
      "early_bullpen_entry_rate": 36.4,
      "top_three_workload_share_10d": 52.3,
      "window_days": 10
    }
  },
  "team_id": 143,
  "writer_targets": [
    "team_story",
    "dashboard",
    "morning_brief"
  ]
}
```

### Draft: team_story

Headline:
```
Bullpen slammed the door
```
Opening:
```
After their most recent game, Jesús Luzardo worked five innings and left with a three-run lead, and the bullpen brought it home.
```
Body:
```
After their most recent game, Jesús Luzardo worked five innings and left with a three-run lead, and the bullpen brought it home. The clean finish keeps the relief corps down to fewer rested options.
```
What BaseballOS noticed / observations:
```
- The starter set the bullpen up to finish the game.
- The bullpen took over with a lead in hand.
- The relievers held the lead.
- The offense finished the comeback the bullpen kept alive.
```
Evidence:
```
- Starter: Jesús Luzardo, 5.0 IP, 96 pitches
- Largest lead: 3
- Bullpen entered in the 6th with a 2-run lead
- Turning point: 7th inning
- Late runs allowed: 0
```
Exact rendered text:
```
Bullpen slammed the door

After their most recent game, Jesús Luzardo worked five innings and left with a three-run lead, and the bullpen brought it home. The clean finish keeps the relief corps down to fewer rested options.

Why BaseballOS sees it:
- The starter set the bullpen up to finish the game.
- The bullpen took over with a lead in hand.
- The relievers held the lead.
- The offense finished the comeback the bullpen kept alive.

Evidence:
- Starter: Jesús Luzardo, 5.0 IP, 96 pitches
- Largest lead: 3
- Bullpen entered in the 6th with a 2-run lead
- Turning point: 7th inning
- Late runs allowed: 0
```


### Draft: dashboard

Headline:
```
Bullpen slammed the door
```
Opening:
```
The club protected a 3-run lead.
```
Body:
```
The club protected a 3-run lead.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Jesús Luzardo, 5.0 IP, 96 pitches
```
Exact rendered text:
```
Bullpen slammed the door

The club protected a 3-run lead.

Evidence:
- Starter: Jesús Luzardo, 5.0 IP, 96 pitches
```


### Draft: morning_brief

Headline:
```
Bullpen note: Bullpen slammed the door
```
Opening:
```
After their most recent game, the club turned a three-run lead into a win the bullpen never let slip.
```
Body:
```
After their most recent game, the club turned a three-run lead into a win the bullpen never let slip. Available arms: 0. The relief corps is down to fewer rested options.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Jesús Luzardo, 5.0 IP, 96 pitches
- Largest lead: 3
- Bullpen entered in the 6th with a 2-run lead
- Turning point: 7th inning
- Late runs allowed: 0
```
Exact rendered text:
```
Bullpen note: Bullpen slammed the door

After their most recent game, the club turned a three-run lead into a win the bullpen never let slip. Available arms: 0. The relief corps is down to fewer rested options.

Evidence:
- Starter: Jesús Luzardo, 5.0 IP, 96 pitches
- Largest lead: 3
- Bullpen entered in the 6th with a 2-run lead
- Turning point: 7th inning
- Late runs allowed: 0
```

## Completed-Game Story 26: Atlanta Braves (ATL, 144)

### Story Metadata

```json
{
  "beat": "starter_covered_bullpen",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_used": false,
  "game_date": "2026-06-28",
  "game_importance": "LOW",
  "game_pk": 823204,
  "opponent_name": "San Francisco Giants",
  "publish_reason": "meets_confidence_threshold",
  "publishable": true,
  "recommended_surface": "dashboard",
  "severity": "MEDIUM",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_type": "starter_covered_bullpen",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 2,
      "context_available": true,
      "limited_arms_count": 3,
      "monitor_arms_count": 2,
      "optionality_band": "narrow",
      "restricted_arms_count": 3,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [
        {
          "availability": "Available",
          "last_workload": "4 days ago",
          "name": "James Karinchak",
          "player_id": 675916,
          "recent_workload": "light"
        },
        {
          "availability": "Available",
          "last_workload": "2 days ago",
          "name": "Raisel Iglesias",
          "player_id": 628452,
          "recent_workload": "light"
        }
      ],
      "clean_options_count": 2,
      "context_available": true,
      "core_retention_count": 1,
      "depth_pressure_band": "heavy",
      "inactive_bullpen_arms_count": 12,
      "optionality_band": "narrow",
      "practical_close_game_paths_count": 3,
      "secondary_options": [
        {
          "availability": "Monitor",
          "name": "Dylan Dodd",
          "player_id": 689266,
          "reason": "2 appearances in 5 days"
        },
        {
          "availability": "Monitor",
          "name": "Tyler Kinley",
          "player_id": 641755,
          "reason": "2 appearances in 5 days"
        }
      ],
      "secondary_options_count": 2,
      "stability_band": "transitioning"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 7,
      "bullpen_story_tag": "starter_covered_bullpen",
      "comeback_completed": false,
      "confidence": "HIGH",
      "deficit_when_bullpen_entered": 2,
      "final_score_against": 3,
      "final_score_for": 2,
      "game_date": "2026-06-28",
      "game_pk": 823204,
      "game_shape_created": "normal_start",
      "game_shape_protected": null,
      "generated_at": "2026-06-28T22:47:38.378437",
      "home_away": "away",
      "largest_deficit": 3,
      "largest_lead": 0,
      "late_runs_allowed": 1,
      "lead_lost": null,
      "lead_protected": null,
      "lead_when_bullpen_entered": null,
      "opponent_name": "San Francisco Giants",
      "runs_allowed_innings_7_to_9": 1,
      "starter_exit_inning": 6,
      "starter_ip": 6.0,
      "starter_name": "Chris Sale",
      "starter_pitch_count": 94,
      "team_id": 144,
      "turning_inning": null
    },
    "confidence": "HIGH",
    "game_importance": "LOW",
    "headline_key": "starter_carried_game",
    "primary_story": "starter_covered_bullpen",
    "publish_reason": "meets_confidence_threshold",
    "publishable": true,
    "recommended_surface": "dashboard",
    "safe_time_context": "AFTER_MOST_RECENT_GAME",
    "secondary_story": null,
    "story_priority": "MEDIUM",
    "summary_key": "starter_limited_bullpen_exposure",
    "supporting_facts": {
      "bullpen_entry_inning": 7,
      "bullpen_entry_score_against": 2,
      "bullpen_entry_score_for": 0,
      "game_shape_created": "normal_start",
      "largest_deficit": 3,
      "largest_lead": 0,
      "late_runs_allowed": 1,
      "runs_allowed_innings_7_to_9": 1,
      "starter_exit_score_against": 2,
      "starter_exit_score_for": 0
    },
    "supporting_observations": [
      "starter_created_game_shape",
      "deep_start",
      "deficit_entering_bullpen",
      "late_runs_allowed"
    ],
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": 3.8,
      "bullpen_workload_appearances_10d": 25,
      "bullpen_workload_total_10d": 499,
      "concentration_band": "balanced",
      "context_available": true,
      "early_bullpen_entry_rate": 45.5,
      "top_three_workload_share_10d": 38.3,
      "window_days": 10
    }
  },
  "team_id": 144,
  "writer_targets": [
    "team_story",
    "dashboard"
  ]
}
```

### Draft: team_story

Headline:
```
Starter carried the load
```
Opening:
```
After their most recent game, the starter worked deep and kept the bullpen's exposure light.
```
Body:
```
After their most recent game, the starter worked deep and kept the bullpen's exposure light.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Chris Sale, 6.0 IP, 94 pitches
- Largest deficit: 3
- Bullpen entered in the 7th trailing by 2
- Late runs allowed: 1
- Clean options: James Karinchak, Raisel Iglesias
```
Exact rendered text:
```
Starter carried the load

After their most recent game, the starter worked deep and kept the bullpen's exposure light.

Evidence:
- Starter: Chris Sale, 6.0 IP, 94 pitches
- Largest deficit: 3
- Bullpen entered in the 7th trailing by 2
- Late runs allowed: 1
- Clean options: James Karinchak, Raisel Iglesias
```


### Draft: dashboard

Headline:
```
Starter carried the load
```
Opening:
```
The club barely used behind a deep start.
```
Body:
```
The club barely used behind a deep start.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Chris Sale, 6.0 IP, 94 pitches
```
Exact rendered text:
```
Starter carried the load

The club barely used behind a deep start.

Evidence:
- Starter: Chris Sale, 6.0 IP, 94 pitches
```

## Completed-Game Story 27: Chicago White Sox (CWS, 145)

### Story Metadata

```json
{
  "beat": "bullpen_overexposed",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_used": false,
  "game_date": "2026-06-28",
  "game_importance": "LOW",
  "game_pk": 824580,
  "opponent_name": "Kansas City Royals",
  "publish_reason": "meets_confidence_threshold",
  "publishable": true,
  "recommended_surface": "dashboard",
  "severity": "MEDIUM",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_type": "bullpen_overexposed",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 0,
      "context_available": true,
      "limited_arms_count": 4,
      "monitor_arms_count": 5,
      "optionality_band": "thin",
      "restricted_arms_count": 4,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [],
      "clean_options_count": 0,
      "context_available": true,
      "core_retention_count": 2,
      "depth_pressure_band": "heavy",
      "inactive_bullpen_arms_count": 14,
      "optionality_band": "thin",
      "practical_close_game_paths_count": 2,
      "secondary_options": [
        {
          "availability": "Monitor",
          "name": "Brandon Eisert",
          "player_id": 685126,
          "reason": "2 appearances in 5 days"
        },
        {
          "availability": "Monitor",
          "name": "Bryan Hudson",
          "player_id": 663542,
          "reason": "No rest since last appearance"
        },
        {
          "availability": "Monitor",
          "name": "Chris Murphy",
          "player_id": 669684,
          "reason": "2 appearances in 5 days"
        },
        {
          "availability": "Monitor",
          "name": "Grant Taylor",
          "player_id": 691799,
          "reason": "19 pitches yesterday"
        },
        {
          "availability": "Monitor",
          "name": "Seranthony Dom\u00ednguez",
          "player_id": 622554,
          "reason": "No rest since last appearance"
        }
      ],
      "secondary_options_count": 5,
      "stability_band": "mostly_stable"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 4,
      "bullpen_story_tag": "bullpen_overexposed",
      "comeback_completed": false,
      "confidence": "HIGH",
      "deficit_when_bullpen_entered": 1,
      "final_score_against": 5,
      "final_score_for": 4,
      "game_date": "2026-06-28",
      "game_pk": 824580,
      "game_shape_created": "short_start",
      "game_shape_protected": null,
      "generated_at": "2026-06-28T22:47:30.530776",
      "home_away": "home",
      "largest_deficit": 1,
      "largest_lead": 1,
      "late_runs_allowed": 0,
      "lead_lost": null,
      "lead_protected": null,
      "lead_when_bullpen_entered": null,
      "opponent_name": "Kansas City Royals",
      "runs_allowed_innings_7_to_9": 0,
      "starter_exit_inning": 4,
      "starter_ip": 3.66666666666667,
      "starter_name": "Anthony Kay",
      "starter_pitch_count": 73,
      "team_id": 145,
      "turning_inning": 4
    },
    "confidence": "HIGH",
    "game_importance": "LOW",
    "headline_key": "bullpen_overexposed",
    "primary_story": "bullpen_overexposed",
    "publish_reason": "meets_confidence_threshold",
    "publishable": true,
    "recommended_surface": "dashboard",
    "safe_time_context": "AFTER_MOST_RECENT_GAME",
    "secondary_story": null,
    "story_priority": "MEDIUM",
    "summary_key": "bullpen_carried_heavy_load",
    "supporting_facts": {
      "bullpen_entry_inning": 4,
      "bullpen_entry_score_against": 5,
      "bullpen_entry_score_for": 4,
      "game_shape_created": "short_start",
      "largest_deficit": 1,
      "largest_lead": 1,
      "late_runs_allowed": 0,
      "runs_allowed_innings_7_to_9": 0,
      "starter_exit_score_against": 5,
      "starter_exit_score_for": 4,
      "turning_inning": 4
    },
    "supporting_observations": [
      "deficit_entering_bullpen",
      "bullpen_worked_long",
      "turning_point_identified"
    ],
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": 4.2,
      "bullpen_workload_appearances_10d": 29,
      "bullpen_workload_total_10d": 567,
      "concentration_band": "balanced",
      "context_available": true,
      "early_bullpen_entry_rate": 44.4,
      "top_three_workload_share_10d": 45.3,
      "window_days": 10
    }
  },
  "team_id": 145,
  "writer_targets": [
    "team_story",
    "dashboard"
  ]
}
```

### Draft: team_story

Headline:
```
Bullpen stretched thin
```
Opening:
```
After their most recent game, Anthony Kay's 3.7-inning start left the bullpen to cover the rest.
```
Body:
```
After their most recent game, Anthony Kay's 3.7-inning start left the bullpen to cover the rest.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Anthony Kay, 3.7 IP, 73 pitches
- Largest lead: 1
- Bullpen entered in the 4th trailing by 1
- Turning point: 4th inning
- Late runs allowed: 0
```
Exact rendered text:
```
Bullpen stretched thin

After their most recent game, Anthony Kay's 3.7-inning start left the bullpen to cover the rest.

Evidence:
- Starter: Anthony Kay, 3.7 IP, 73 pitches
- Largest lead: 1
- Bullpen entered in the 4th trailing by 1
- Turning point: 4th inning
- Late runs allowed: 0
```


### Draft: dashboard

Headline:
```
Bullpen stretched thin
```
Opening:
```
The club covered heavy innings on a short start.
```
Body:
```
The club covered heavy innings on a short start.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Anthony Kay, 3.7 IP, 73 pitches
```
Exact rendered text:
```
Bullpen stretched thin

The club covered heavy innings on a short start.

Evidence:
- Starter: Anthony Kay, 3.7 IP, 73 pitches
```

## Completed-Game Story 28: Miami Marlins (MIA, 146)

### Story Metadata

```json
{
  "beat": "starter_covered_bullpen",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_used": false,
  "game_date": "2026-06-28",
  "game_importance": "LOW",
  "game_pk": 823037,
  "opponent_name": "St. Louis Cardinals",
  "publish_reason": "meets_confidence_threshold",
  "publishable": true,
  "recommended_surface": "dashboard",
  "severity": "MEDIUM",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_type": "starter_covered_bullpen",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 2,
      "context_available": true,
      "limited_arms_count": 1,
      "monitor_arms_count": 5,
      "optionality_band": "flexible",
      "restricted_arms_count": 1,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [
        {
          "availability": "Available",
          "last_workload": "2 days ago",
          "name": "Calvin Faucher",
          "player_id": 676534,
          "recent_workload": "light"
        },
        {
          "availability": "Available",
          "last_workload": "4 days ago",
          "name": "Pete Fairbanks",
          "player_id": 664126,
          "recent_workload": "light"
        }
      ],
      "clean_options_count": 2,
      "context_available": true,
      "core_retention_count": 2,
      "depth_pressure_band": "heavy",
      "inactive_bullpen_arms_count": 10,
      "optionality_band": "flexible",
      "practical_close_game_paths_count": 4,
      "secondary_options": [
        {
          "availability": "Monitor",
          "name": "Anthony Bender",
          "player_id": 669622,
          "reason": "20 pitches yesterday"
        },
        {
          "availability": "Monitor",
          "name": "Cade Gibson",
          "player_id": 806188,
          "reason": "No rest since last appearance"
        },
        {
          "availability": "Monitor",
          "name": "John King",
          "player_id": 667463,
          "reason": "2 appearances in 5 days"
        },
        {
          "availability": "Monitor",
          "name": "Michael Petersen",
          "player_id": 656848,
          "reason": "2 appearances in 5 days"
        },
        {
          "availability": "Monitor",
          "name": "Tyler Zuber",
          "player_id": 676604,
          "reason": "Only 1 day of rest"
        }
      ],
      "secondary_options_count": 5,
      "stability_band": "mostly_stable"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 8,
      "bullpen_story_tag": "starter_covered_bullpen",
      "comeback_completed": false,
      "confidence": "HIGH",
      "deficit_when_bullpen_entered": 1,
      "final_score_against": 2,
      "final_score_for": 1,
      "game_date": "2026-06-28",
      "game_pk": 823037,
      "game_shape_created": "normal_start",
      "game_shape_protected": null,
      "generated_at": "2026-06-28T22:47:34.670650",
      "home_away": "away",
      "largest_deficit": 2,
      "largest_lead": 0,
      "late_runs_allowed": 0,
      "lead_lost": null,
      "lead_protected": null,
      "lead_when_bullpen_entered": null,
      "opponent_name": "St. Louis Cardinals",
      "runs_allowed_innings_7_to_9": 0,
      "starter_exit_inning": 8,
      "starter_ip": 7.33333333333333,
      "starter_name": "Tyler Phillips",
      "starter_pitch_count": 97,
      "team_id": 146,
      "turning_inning": null
    },
    "confidence": "HIGH",
    "game_importance": "LOW",
    "headline_key": "starter_carried_game",
    "primary_story": "starter_covered_bullpen",
    "publish_reason": "meets_confidence_threshold",
    "publishable": true,
    "recommended_surface": "dashboard",
    "safe_time_context": "AFTER_MOST_RECENT_GAME",
    "secondary_story": null,
    "story_priority": "MEDIUM",
    "summary_key": "starter_limited_bullpen_exposure",
    "supporting_facts": {
      "bullpen_entry_inning": 8,
      "bullpen_entry_score_against": 2,
      "bullpen_entry_score_for": 1,
      "game_shape_created": "normal_start",
      "largest_deficit": 2,
      "largest_lead": 0,
      "late_runs_allowed": 0,
      "runs_allowed_innings_7_to_9": 0,
      "starter_exit_score_against": 2,
      "starter_exit_score_for": 1
    },
    "supporting_observations": [
      "starter_created_game_shape",
      "deep_start",
      "deficit_entering_bullpen"
    ],
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": 3.1,
      "bullpen_workload_appearances_10d": 33,
      "bullpen_workload_total_10d": 502,
      "concentration_band": "balanced",
      "context_available": true,
      "early_bullpen_entry_rate": 58.3,
      "top_three_workload_share_10d": 41.6,
      "window_days": 10
    }
  },
  "team_id": 146,
  "writer_targets": [
    "team_story",
    "dashboard"
  ]
}
```

### Draft: team_story

Headline:
```
Starter carried the load
```
Opening:
```
After their most recent game, the starter worked deep and kept the bullpen's exposure light.
```
Body:
```
After their most recent game, the starter worked deep and kept the bullpen's exposure light.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Tyler Phillips, 7.3 IP, 97 pitches
- Largest deficit: 2
- Bullpen entered in the 8th trailing by 1
- Late runs allowed: 0
- Clean options: Calvin Faucher, Pete Fairbanks
```
Exact rendered text:
```
Starter carried the load

After their most recent game, the starter worked deep and kept the bullpen's exposure light.

Evidence:
- Starter: Tyler Phillips, 7.3 IP, 97 pitches
- Largest deficit: 2
- Bullpen entered in the 8th trailing by 1
- Late runs allowed: 0
- Clean options: Calvin Faucher, Pete Fairbanks
```


### Draft: dashboard

Headline:
```
Starter carried the load
```
Opening:
```
The club barely used behind a deep start.
```
Body:
```
The club barely used behind a deep start.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Tyler Phillips, 7.3 IP, 97 pitches
```
Exact rendered text:
```
Starter carried the load

The club barely used behind a deep start.

Evidence:
- Starter: Tyler Phillips, 7.3 IP, 97 pitches
```

## Completed-Game Story 29: New York Yankees (NYY, 147)

### Story Metadata

```json
{
  "beat": "insufficient_context",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_used": true,
  "game_date": "2026-06-28",
  "game_importance": "LOW",
  "game_pk": 824744,
  "opponent_name": "Boston Red Sox",
  "publish_reason": "insufficient_confidence",
  "publishable": false,
  "recommended_surface": "none",
  "severity": "LOW",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_type": "insufficient_context",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 1,
      "context_available": true,
      "limited_arms_count": 3,
      "monitor_arms_count": 4,
      "optionality_band": "narrow",
      "restricted_arms_count": 3,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [
        {
          "availability": "Available",
          "last_workload": "3 days ago",
          "name": "Tim Hill",
          "player_id": 657612,
          "recent_workload": "light"
        }
      ],
      "clean_options_count": 1,
      "context_available": true,
      "core_retention_count": 0,
      "depth_pressure_band": "heavy",
      "inactive_bullpen_arms_count": 9,
      "optionality_band": "narrow",
      "practical_close_game_paths_count": 3,
      "secondary_options": [
        {
          "availability": "Monitor",
          "name": "Brent Headrick",
          "player_id": 687396,
          "reason": "17 pitches yesterday"
        },
        {
          "availability": "Monitor",
          "name": "Camilo Doval",
          "player_id": 666808,
          "reason": "2 appearances in 5 days"
        },
        {
          "availability": "Monitor",
          "name": "David Bednar",
          "player_id": 670280,
          "reason": "33 pitches in 3 days"
        },
        {
          "availability": "Monitor",
          "name": "Fernando Cruz",
          "player_id": 518585,
          "reason": "2 appearances in 5 days"
        }
      ],
      "secondary_options_count": 4,
      "stability_band": "rebuilding"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 6,
      "bullpen_story_tag": "insufficient_context",
      "comeback_completed": false,
      "confidence": "HIGH",
      "deficit_when_bullpen_entered": 2,
      "final_score_against": 5,
      "final_score_for": 4,
      "game_date": "2026-06-28",
      "game_pk": 824744,
      "game_shape_created": "normal_start",
      "game_shape_protected": null,
      "generated_at": "2026-06-29T03:03:18.964258",
      "home_away": "away",
      "largest_deficit": 2,
      "largest_lead": 2,
      "late_runs_allowed": 3,
      "lead_lost": null,
      "lead_protected": null,
      "lead_when_bullpen_entered": null,
      "opponent_name": "Boston Red Sox",
      "runs_allowed_innings_7_to_9": 0,
      "starter_exit_inning": 5,
      "starter_ip": 5.0,
      "starter_name": "Carlos Rod\u00f3n",
      "starter_pitch_count": 96,
      "team_id": 147,
      "turning_inning": 10
    },
    "confidence": "HIGH",
    "game_importance": "LOW",
    "headline_key": "insufficient_context",
    "primary_story": "insufficient_context",
    "publish_reason": "insufficient_confidence",
    "publishable": false,
    "recommended_surface": "none",
    "safe_time_context": "CURRENT_STATUS",
    "secondary_story": null,
    "story_priority": "LOW",
    "summary_key": "insufficient_context",
    "supporting_facts": {},
    "supporting_observations": [],
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": 2.9,
      "bullpen_workload_appearances_10d": 31,
      "bullpen_workload_total_10d": 486,
      "concentration_band": "balanced",
      "context_available": true,
      "early_bullpen_entry_rate": 38.5,
      "top_three_workload_share_10d": 47.3,
      "window_days": 10
    }
  },
  "team_id": 147,
  "writer_targets": []
}
```

No public drafts were rendered for this row by the existing writer targets.

## Completed-Game Story 30: Milwaukee Brewers (MIL, 158)

### Story Metadata

```json
{
  "beat": "lost_game_shape",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_used": false,
  "game_date": "2026-06-28",
  "game_importance": "MEDIUM",
  "game_pk": 823769,
  "opponent_name": "Chicago Cubs",
  "publish_reason": "critical_narrative",
  "publishable": true,
  "recommended_surface": "multiple",
  "severity": "CRITICAL",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_type": "lost_game_shape",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 0,
      "context_available": true,
      "limited_arms_count": 6,
      "monitor_arms_count": 1,
      "optionality_band": "thin",
      "restricted_arms_count": 7,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [],
      "clean_options_count": 0,
      "context_available": true,
      "core_retention_count": 3,
      "depth_pressure_band": "heavy",
      "inactive_bullpen_arms_count": 10,
      "optionality_band": "thin",
      "practical_close_game_paths_count": 0,
      "secondary_options": [
        {
          "availability": "Monitor",
          "name": "Jared Koenig",
          "player_id": 657649,
          "reason": "15 pitches yesterday"
        }
      ],
      "secondary_options_count": 1,
      "stability_band": "stable"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 6,
      "bullpen_story_tag": "lost_game_shape",
      "comeback_completed": false,
      "confidence": "HIGH",
      "deficit_when_bullpen_entered": null,
      "final_score_against": 4,
      "final_score_for": 3,
      "game_date": "2026-06-28",
      "game_pk": 823769,
      "game_shape_created": "normal_start",
      "game_shape_protected": false,
      "generated_at": "2026-06-28T22:47:32.841192",
      "home_away": "home",
      "largest_deficit": 3,
      "largest_lead": 1,
      "late_runs_allowed": 4,
      "lead_lost": true,
      "lead_protected": false,
      "lead_when_bullpen_entered": 1,
      "opponent_name": "Chicago Cubs",
      "runs_allowed_innings_7_to_9": 1,
      "starter_exit_inning": 6,
      "starter_ip": 5.66666666666667,
      "starter_name": "Brandon Woodruff",
      "starter_pitch_count": 84,
      "team_id": 158,
      "turning_inning": 10
    },
    "confidence": "HIGH",
    "game_importance": "MEDIUM",
    "headline_key": "lost_game_shape",
    "primary_story": "lost_game_shape",
    "publish_reason": "critical_narrative",
    "publishable": true,
    "recommended_surface": "multiple",
    "safe_time_context": "AFTER_MOST_RECENT_GAME",
    "secondary_story": null,
    "story_priority": "CRITICAL",
    "summary_key": "game_shape_not_protected",
    "supporting_facts": {
      "bullpen_entry_inning": 6,
      "bullpen_entry_score_against": 0,
      "bullpen_entry_score_for": 1,
      "game_shape_created": "normal_start",
      "game_shape_protected": false,
      "largest_deficit": 3,
      "largest_lead": 1,
      "late_runs_allowed": 4,
      "lead_lost": true,
      "lead_protected": false,
      "runs_allowed_innings_7_to_9": 1,
      "starter_exit_score_against": 0,
      "starter_exit_score_for": 1,
      "turning_inning": 10
    },
    "supporting_observations": [
      "starter_created_game_shape",
      "lead_entering_bullpen",
      "bullpen_lost_lead",
      "late_runs_allowed",
      "turning_point_identified"
    ],
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": 3.7,
      "bullpen_workload_appearances_10d": 28,
      "bullpen_workload_total_10d": 529,
      "concentration_band": "balanced",
      "context_available": true,
      "early_bullpen_entry_rate": 33.3,
      "top_three_workload_share_10d": 52.7,
      "window_days": 10
    }
  },
  "team_id": 158,
  "writer_targets": [
    "team_story",
    "dashboard",
    "morning_brief"
  ]
}
```

### Draft: team_story

Headline:
```
Lead surrendered late
```
Opening:
```
After their most recent game, Brandon Woodruff's 5.7 strong innings staked a one-run lead heading to the late innings.
```
Body:
```
After their most recent game, Brandon Woodruff's 5.7 strong innings staked a one-run lead heading to the late innings. It didn't last. Four late runs turned the game. That late collapse leaves the relief corps down to fewer rested options.
```
What BaseballOS noticed / observations:
```
- The starter set the bullpen up to finish the game.
- The bullpen took over with a lead in hand.
- The relievers could not hold the lead.
- The damage came after the starter exited.
```
Evidence:
```
- Starter: Brandon Woodruff, 5.7 IP, 84 pitches
- Largest lead: 1
- Bullpen entered in the 6th with a 1-run lead
- Turning point: 10th inning
- Late runs allowed: 4
```
Exact rendered text:
```
Lead surrendered late

After their most recent game, Brandon Woodruff's 5.7 strong innings staked a one-run lead heading to the late innings. It didn't last. Four late runs turned the game. That late collapse leaves the relief corps down to fewer rested options.

Why BaseballOS sees it:
- The starter set the bullpen up to finish the game.
- The bullpen took over with a lead in hand.
- The relievers could not hold the lead.
- The damage came after the starter exited.

Evidence:
- Starter: Brandon Woodruff, 5.7 IP, 84 pitches
- Largest lead: 1
- Bullpen entered in the 6th with a 1-run lead
- Turning point: 10th inning
- Late runs allowed: 4
```


### Draft: dashboard

Headline:
```
Lead surrendered late
```
Opening:
```
The club blew a 1-run lead late.
```
Body:
```
The club blew a 1-run lead late.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Brandon Woodruff, 5.7 IP, 84 pitches
```
Exact rendered text:
```
Lead surrendered late

The club blew a 1-run lead late.

Evidence:
- Starter: Brandon Woodruff, 5.7 IP, 84 pitches
```


### Draft: morning_brief

Headline:
```
Bullpen note: Lead surrendered late
```
Opening:
```
After their most recent game, the club carried a one-run lead into the late innings and let it get away on four late runs.
```
Body:
```
After their most recent game, the club carried a one-run lead into the late innings and let it get away on four late runs. Available arms: 0. Yesterday's late damage leaves the relief corps down to fewer rested options.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Brandon Woodruff, 5.7 IP, 84 pitches
- Largest lead: 1
- Bullpen entered in the 6th with a 1-run lead
- Turning point: 10th inning
- Late runs allowed: 4
```
Exact rendered text:
```
Bullpen note: Lead surrendered late

After their most recent game, the club carried a one-run lead into the late innings and let it get away on four late runs. Available arms: 0. Yesterday's late damage leaves the relief corps down to fewer rested options.

Evidence:
- Starter: Brandon Woodruff, 5.7 IP, 84 pitches
- Largest lead: 1
- Bullpen entered in the 6th with a 1-run lead
- Turning point: 10th inning
- Late runs allowed: 4
```
