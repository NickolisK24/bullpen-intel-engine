# Today's Story Editorial Review Corpus - E2C-5G Live

Read-only export of the current stored homepage-visible Today's Story / completed-game story writer path after the E2C completed-game voice polish.

## Export Metadata

```json
{
  "artifact": "artifacts/todays_story_editorial_review_E2C5G_live.md",
  "completed_game_context_rows_reviewed": 30,
  "completed_game_fallback_or_unpublishable_rows": 5,
  "completed_game_publishable_stories": 25,
  "completed_game_rendered_drafts": 65,
  "generated_at": "2026-06-30T01:41:35.319078",
  "generation_path_used": [
    "services.todays_story_editorial_review.build_todays_story_editorial_review",
    "services.intelligence_surface_service.build_today_lead_story",
    "services.coin_story_inspection.inspect_team_story",
    "story_writers::{TeamStoryWriter, DashboardStoryWriter, MorningBriefWriter}"
  ],
  "homepage_candidates_considered": 30,
  "homepage_empty_reason": null,
  "homepage_errors": 0,
  "homepage_publishable_candidates": 25,
  "homepage_status": "ok",
  "live_data_error": null,
  "primary_story_distribution": {
    "bullpen_kept_team_alive": 2,
    "bullpen_overexposed": 6,
    "insufficient_context": 5,
    "lost_game_shape": 3,
    "protected_game_shape": 10,
    "starter_covered_bullpen": 4
  },
  "reference_date": "2026-06-28",
  "review_label": "E2C-5G Live",
  "snapshot_present_for_reference_date": true,
  "source_mode": "current stored DB data only; exporter starts no sync"
}
```

## Editorial Banned-Language Scan

Status: pass - no banned language violations found.

## Retired Phrase Scan

Status: pass - no retired phrase violations found.

## Impossible Innings Scan

Status: pass - no impossible innings notation violations found.

## Headline Reuse Summary

```json
{
  "headline_counts": {
    "Bullpen drew the long assignment": 3,
    "Bullpen finished the lead": 1,
    "Bullpen gave the comeback room": 2,
    "Bullpen had to cover": 2,
    "Bullpen held the finish": 1,
    "Bullpen note: Bullpen closed it down": 2,
    "Bullpen note: Bullpen finished the lead": 1,
    "Bullpen note: Bullpen kept it alive": 2,
    "Bullpen note: Late innings held firm": 1,
    "Bullpen note: Late lead closed out": 1,
    "Bullpen note: Late lead held": 2,
    "Bullpen note: Late lead slipped away": 2,
    "Bullpen note: Lead carried home": 1,
    "Bullpen note: Lead finished cleanly": 2,
    "Bullpen note: Lead surrendered late": 1,
    "Bullpen slammed the door": 2,
    "Bullpen stretched thin": 1,
    "Deep start kept the bullpen light": 1,
    "Deep start lightened the load": 2,
    "Late innings held firm": 2,
    "Late innings stayed quiet": 3,
    "Late lead closed out": 2,
    "Late lead held": 2,
    "Late lead slipped away": 1,
    "Lead carried home": 1,
    "Lead disappeared late": 3,
    "Lead finished cleanly": 1,
    "Lead protected": 3,
    "Lead surrendered late": 2,
    "Quiet finish from the pen": 2,
    "Relievers had to cover early": 2,
    "Relievers left room for the rally": 2,
    "Short start made it a bullpen finish": 1,
    "Short start stretched the bullpen": 3,
    "Starter carried the load": 1,
    "Starter covered the hard part": 1,
    "Starter spared the bullpen": 3
  },
  "max_reuse_count": 3,
  "reused_headlines": {
    "Bullpen drew the long assignment": 3,
    "Bullpen gave the comeback room": 2,
    "Bullpen had to cover": 2,
    "Bullpen note: Bullpen closed it down": 2,
    "Bullpen note: Bullpen kept it alive": 2,
    "Bullpen note: Late lead held": 2,
    "Bullpen note: Late lead slipped away": 2,
    "Bullpen note: Lead finished cleanly": 2,
    "Bullpen slammed the door": 2,
    "Deep start lightened the load": 2,
    "Late innings held firm": 2,
    "Late innings stayed quiet": 3,
    "Late lead closed out": 2,
    "Late lead held": 2,
    "Lead disappeared late": 3,
    "Lead protected": 3,
    "Lead surrendered late": 2,
    "Quiet finish from the pen": 2,
    "Relievers had to cover early": 2,
    "Relievers left room for the rally": 2,
    "Short start stretched the bullpen": 3,
    "Starter spared the bullpen": 3
  }
}
```

## Same-Beat Repetition / Swap-Test Summary

```json
{
  "beat_summaries": {
    "bullpen_kept_team_alive": {
      "duplicate_template_count": 0,
      "story_count": 2,
      "unique_template_count": 2
    },
    "bullpen_overexposed": {
      "duplicate_template_count": 0,
      "story_count": 6,
      "unique_template_count": 6
    },
    "lost_game_shape": {
      "duplicate_template_count": 0,
      "story_count": 3,
      "unique_template_count": 3
    },
    "protected_game_shape": {
      "duplicate_template_count": 0,
      "story_count": 10,
      "unique_template_count": 10
    },
    "starter_covered_bullpen": {
      "duplicate_template_count": 0,
      "story_count": 4,
      "unique_template_count": 4
    }
  },
  "duplicate_groups": [],
  "scope": "publishable team_story completed-game bodies, stripped names, numeric values, and common baseball number-words",
  "status": "pass"
}
```

## Starter-Covered Bullpen Specificity Check

```json
{
  "failure_count": 0,
  "failures": [],
  "rows_checked": [
    {
      "checks": {
        "bullpen_consequence_present": true,
        "innings_or_pitch_count_anchor_present": true,
        "old_nameless_sentence_absent": true,
        "starter_name_present": true
      },
      "game_pk": 822959,
      "headline": "Starter carried the load",
      "starter_ip": "6.0",
      "starter_name": "Merrill Kelly",
      "starter_pitch_count": 93,
      "team_id": 109
    },
    {
      "checks": {
        "bullpen_consequence_present": true,
        "innings_or_pitch_count_anchor_present": true,
        "old_nameless_sentence_absent": true,
        "starter_name_present": true
      },
      "game_pk": 823686,
      "headline": "Starter spared the bullpen",
      "starter_ip": "6.0",
      "starter_name": "Ryan Feltner",
      "starter_pitch_count": 82,
      "team_id": 115
    },
    {
      "checks": {
        "bullpen_consequence_present": true,
        "innings_or_pitch_count_anchor_present": true,
        "old_nameless_sentence_absent": true,
        "starter_name_present": true
      },
      "game_pk": 823204,
      "headline": "Starter covered the hard part",
      "starter_ip": "6.0",
      "starter_name": "Chris Sale",
      "starter_pitch_count": 94,
      "team_id": 144
    },
    {
      "checks": {
        "bullpen_consequence_present": true,
        "innings_or_pitch_count_anchor_present": true,
        "old_nameless_sentence_absent": true,
        "starter_name_present": true
      },
      "game_pk": 823037,
      "headline": "Starter spared the bullpen",
      "starter_ip": "7.1",
      "starter_name": "Tyler Phillips",
      "starter_pitch_count": 97,
      "team_id": 146
    }
  ],
  "scope": "publishable starter_covered_bullpen completed-game team-story drafts",
  "starter_covered_publishable_rows": 4,
  "status": "pass"
}
```

## Homepage Fallback Status

```json
{
  "candidates_considered": 30,
  "empty_reason": null,
  "errors": 0,
  "lead_rendered": true,
  "publishable_candidates": 25,
  "status": "ok"
}
```

## Completed-Game Fallback Status

```json
{
  "fallback_or_unpublishable_rows": 5,
  "fallback_rows": [
    {
      "confidence": "HIGH",
      "drafts_rendered": 0,
      "export_error": null,
      "game_pk": 823362,
      "publish_reason": "insufficient_confidence",
      "publishable": false,
      "story_type": "insufficient_context",
      "team_id": 113
    },
    {
      "confidence": "HIGH",
      "drafts_rendered": 0,
      "export_error": null,
      "game_pk": 824256,
      "publish_reason": "insufficient_confidence",
      "publishable": false,
      "story_type": "insufficient_context",
      "team_id": 117
    },
    {
      "confidence": "HIGH",
      "drafts_rendered": 0,
      "export_error": null,
      "game_pk": 824011,
      "publish_reason": "insufficient_confidence",
      "publishable": false,
      "story_type": "insufficient_context",
      "team_id": 133
    },
    {
      "confidence": "HIGH",
      "drafts_rendered": 0,
      "export_error": null,
      "game_pk": 822795,
      "publish_reason": "insufficient_confidence",
      "publishable": false,
      "story_type": "insufficient_context",
      "team_id": 141
    },
    {
      "confidence": "HIGH",
      "drafts_rendered": 0,
      "export_error": null,
      "game_pk": 824744,
      "publish_reason": "insufficient_confidence",
      "publishable": false,
      "story_type": "insufficient_context",
      "team_id": 147
    }
  ],
  "publishable_rows": 25,
  "rows_reviewed": 30,
  "status": "pass"
}
```

## Homepage Lead Story

### Lead Metadata

```json
{
  "beat": "lost_game_shape",
  "game_pk": 824256,
  "selection": {
    "confidence": "HIGH",
    "game_importance": "HIGH",
    "late_runs_allowed": 7,
    "primary_story": "lost_game_shape",
    "rank": 1,
    "reason": "critical_narrative",
    "story_priority": "CRITICAL",
    "swing": 4
  },
  "source_path": "current stored CompletedGameContext rows -> build_today_lead_story (on-demand, no snapshot write)",
  "story_type": "lost_game_shape",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 0,
      "context_available": false,
      "limited_arms_count": 0,
      "monitor_arms_count": 0,
      "optionality_band": "insufficient_data",
      "restricted_arms_count": 0,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [],
      "clean_options_count": 0,
      "context_available": false,
      "core_retention_count": 0,
      "depth_pressure_band": "insufficient_data",
      "inactive_bullpen_arms_count": 0,
      "optionality_band": "insufficient_data",
      "practical_close_game_paths_count": 0,
      "secondary_options": [],
      "secondary_options_count": 0,
      "stability_band": "insufficient_data"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 6,
      "bullpen_entry_score_against": 0,
      "bullpen_entry_score_for": 3,
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
      "generated_at": "2026-06-30T00:53:59.101365",
      "home_away": "home",
      "id": 7,
      "largest_deficit": 4,
      "largest_lead": 3,
      "late_runs_allowed": 7,
      "lead_lost": true,
      "lead_protected": false,
      "lead_when_bullpen_entered": 3,
      "opponent_name": "Houston Astros",
      "opponent_team_id": 117,
      "runs_allowed_innings_7_to_9": 3,
      "starter_exit_inning": 5,
      "starter_exit_score_against": 0,
      "starter_exit_score_for": 2,
      "starter_ip": 5.0,
      "starter_name": "Jack Flaherty",
      "starter_pitch_count": 94,
      "starter_player_id": 656427,
      "team_id": 116,
      "turning_inning": 10
    },
    "evidence_blocks": {
      "available_relievers": [],
      "bullpen_entry_situation": {
        "inning": 6,
        "lead_when_entered": 3,
        "score_against": 0,
        "score_for": 3
      },
      "bullpen_summary": {
        "available_count": 0,
        "comeback_completed": false,
        "late_runs_allowed": 7,
        "lead_lost": true,
        "lead_protected": false,
        "limited_count": 0,
        "monitor_count": 0,
        "optionality_band": "insufficient_data",
        "unavailable_count": 0
      },
      "clean_options": [],
      "coverage_depth": {
        "bullpen_coverage_ip_7d": 4.3,
        "clean_options_count": 0,
        "depth_pressure_band": "insufficient_data",
        "practical_close_game_paths_count": 0,
        "secondary_options_count": 0
      },
      "evidence_version": "evidence_v1",
      "key_relief_appearances": [],
      "largest_deficit": {
        "runs": 4
      },
      "largest_lead": {
        "runs": 3
      },
      "late_runs": {
        "late_runs_allowed": 7,
        "runs_allowed_innings_7_to_9": 3
      },
      "limited_relievers": [],
      "monitor_relievers": [],
      "starter_summary": {
        "exit_inning": 5,
        "exit_score_against": 0,
        "exit_score_for": 2,
        "game_shape_created": "normal_start",
        "innings": 5.0,
        "name": "Jack Flaherty",
        "pitch_count": 94
      },
      "story_evidence": {
        "primary_story": "lost_game_shape",
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
        ]
      },
      "turning_point": {
        "inning": 10
      },
      "unavailable_relievers": [],
      "workload_concentration": {
        "bullpen_workload_appearances_10d": 3,
        "bullpen_workload_total_10d": 76,
        "concentration_band": "narrow",
        "top_three_workload_share_10d": 100.0,
        "window_days": 10
      }
    },
    "narrative_context": {
      "confidence": "HIGH",
      "context_type": "completed_game",
      "game_importance": "HIGH",
      "game_pk": 824256,
      "generated_at": "2026-06-30T01:41:30.871766",
      "headline_key": "lost_game_shape",
      "primary_story": "lost_game_shape",
      "secondary_story": "late_pressure_accumulated",
      "story_priority": "CRITICAL",
      "story_version": "narrative_context_v1",
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
      "team_id": 116
    },
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": 4.3,
      "bullpen_workload_appearances_10d": 3,
      "bullpen_workload_total_10d": 76,
      "concentration_band": "narrow",
      "context_available": true,
      "early_bullpen_entry_rate": 0.0,
      "top_three_workload_share_10d": 100.0,
      "window_days": 10
    }
  },
  "team_id": 116
}
```

### Homepage Draft: team_story

Headline:
```
Lead disappeared late
```
Body:
```
After their most recent game, Jack Flaherty's five strong innings staked a three-run lead heading to the late innings. It didn't last. Seven late runs turned the game. That keeps the work gathered on a smaller group.
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
Lead disappeared late

After their most recent game, Jack Flaherty's five strong innings staked a three-run lead heading to the late innings. It didn't last. Seven late runs turned the game. That keeps the work gathered on a smaller group.

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

### Homepage Draft: dashboard

Headline:
```
Lead surrendered late
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

### Homepage Draft: morning_brief

Headline:
```
Bullpen note: Late lead slipped away
```
Body:
```
After their most recent game, the club carried a three-run lead into the late innings and let it get away on seven late runs. The late damage leaves the bullpen with less margin. That keeps the work gathered on a smaller group.
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
Bullpen note: Late lead slipped away

After their most recent game, the club carried a three-run lead into the late innings and let it get away on seven late runs. The late damage leaves the bullpen with less margin. That keeps the work gathered on a smaller group.

Evidence:
- Starter: Jack Flaherty, 5.0 IP, 94 pitches
- Largest lead: 3
- Bullpen entered in the 6th with a 3-run lead
- Turning point: 10th inning
- Late runs allowed: 7
```

## Completed-Game Story Corpus

This section contains 30 current stored completed-game contexts for 2026-06-28. Each row was rendered through inspect_team_story with the existing writer targets only.

## Completed-Game Story 1: Team 108 (108)

### Story Metadata

```json
{
  "beat": "protected_game_shape",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_or_unpublishable": false,
  "game_date": "2026-06-28",
  "game_importance": "HIGH",
  "game_pk": 824011,
  "opponent_name": "Athletics",
  "publish_reason": "high_priority_narrative",
  "publishable": true,
  "recommended_surface": "multiple",
  "safe_time_context": "AFTER_MOST_RECENT_GAME",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_priority": "HIGH",
  "story_type": "protected_game_shape",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 0,
      "context_available": false,
      "limited_arms_count": 0,
      "monitor_arms_count": 0,
      "optionality_band": "insufficient_data",
      "restricted_arms_count": 0,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [],
      "clean_options_count": 0,
      "context_available": false,
      "core_retention_count": 0,
      "depth_pressure_band": "insufficient_data",
      "inactive_bullpen_arms_count": 0,
      "optionality_band": "insufficient_data",
      "practical_close_game_paths_count": 0,
      "secondary_options": [],
      "secondary_options_count": 0,
      "stability_band": "insufficient_data"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 6,
      "bullpen_entry_score_against": 1,
      "bullpen_entry_score_for": 4,
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
      "generated_at": "2026-06-30T00:54:00.128206",
      "home_away": "home",
      "id": 23,
      "largest_deficit": 0,
      "largest_lead": 4,
      "late_runs_allowed": 0,
      "lead_lost": false,
      "lead_protected": true,
      "lead_when_bullpen_entered": 3,
      "opponent_name": "Athletics",
      "opponent_team_id": 133,
      "runs_allowed_innings_7_to_9": 0,
      "starter_exit_inning": 5,
      "starter_exit_score_against": 1,
      "starter_exit_score_for": 4,
      "starter_ip": 5.0,
      "starter_name": "Sam Aldegheri",
      "starter_pitch_count": 81,
      "starter_player_id": 691951,
      "team_id": 108,
      "turning_inning": null
    },
    "evidence_blocks": {
      "available_relievers": [],
      "bullpen_entry_situation": {
        "inning": 6,
        "lead_when_entered": 3,
        "score_against": 1,
        "score_for": 4
      },
      "bullpen_summary": {
        "available_count": 0,
        "comeback_completed": false,
        "late_runs_allowed": 0,
        "lead_lost": false,
        "lead_protected": true,
        "limited_count": 0,
        "monitor_count": 0,
        "optionality_band": "insufficient_data",
        "unavailable_count": 0
      },
      "clean_options": [],
      "coverage_depth": {
        "clean_options_count": 0,
        "depth_pressure_band": "insufficient_data",
        "practical_close_game_paths_count": 0,
        "secondary_options_count": 0
      },
      "evidence_version": "evidence_v1",
      "key_relief_appearances": [],
      "largest_deficit": {
        "runs": 0
      },
      "largest_lead": {
        "runs": 4
      },
      "late_runs": {
        "late_runs_allowed": 0,
        "runs_allowed_innings_7_to_9": 0
      },
      "limited_relievers": [],
      "monitor_relievers": [],
      "starter_summary": {
        "exit_inning": 5,
        "exit_score_against": 1,
        "exit_score_for": 4,
        "game_shape_created": "normal_start",
        "innings": 5.0,
        "name": "Sam Aldegheri",
        "pitch_count": 81
      },
      "story_evidence": {
        "primary_story": "protected_game_shape",
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
        ]
      },
      "turning_point": {},
      "unavailable_relievers": [],
      "workload_concentration": {
        "bullpen_workload_appearances_10d": 1,
        "bullpen_workload_total_10d": 19,
        "concentration_band": "narrow",
        "top_three_workload_share_10d": 100.0,
        "window_days": 10
      }
    },
    "narrative_context": {
      "confidence": "HIGH",
      "context_type": "completed_game",
      "game_importance": "HIGH",
      "game_pk": 824011,
      "generated_at": "2026-06-30T01:41:32.493559",
      "headline_key": "bullpen_stabilized",
      "primary_story": "protected_game_shape",
      "secondary_story": null,
      "story_priority": "HIGH",
      "story_version": "narrative_context_v1",
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
      "team_id": 108
    },
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": null,
      "bullpen_workload_appearances_10d": 1,
      "bullpen_workload_total_10d": 19,
      "concentration_band": "narrow",
      "context_available": true,
      "early_bullpen_entry_rate": null,
      "top_three_workload_share_10d": 100.0,
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
Lead finished cleanly
```
Body:
```
After their most recent game, Sam Aldegheri put a four-run lead in place over five innings, and the relievers carried it home. That keeps the workload from spreading across the full bullpen.
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
```
Exact rendered text:
```
Lead finished cleanly

After their most recent game, Sam Aldegheri put a four-run lead in place over five innings, and the relievers carried it home. That keeps the workload from spreading across the full bullpen.

Why BaseballOS sees it:
- The starter set the bullpen up to finish the game.
- The bullpen took over with a lead in hand.
- The relievers held the lead.

Evidence:
- Starter: Sam Aldegheri, 5.0 IP, 81 pitches
- Largest lead: 4
- Bullpen entered in the 6th with a 3-run lead
- Late runs allowed: 0
```

### Draft: dashboard

Headline:
```
Late innings stayed quiet
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
Late innings stayed quiet

The club protected a 4-run lead.

Evidence:
- Starter: Sam Aldegheri, 5.0 IP, 81 pitches
```

### Draft: morning_brief

Headline:
```
Bullpen note: Late innings held firm
```
Body:
```
After their most recent game, the club turned a four-run lead into a win the bullpen never let slip. That keeps the work gathered on a smaller group.
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
```
Exact rendered text:
```
Bullpen note: Late innings held firm

After their most recent game, the club turned a four-run lead into a win the bullpen never let slip. That keeps the work gathered on a smaller group.

Evidence:
- Starter: Sam Aldegheri, 5.0 IP, 81 pitches
- Largest lead: 4
- Bullpen entered in the 6th with a 3-run lead
- Late runs allowed: 0
```

## Completed-Game Story 2: Team 109 (109)

### Story Metadata

```json
{
  "beat": "starter_covered_bullpen",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_or_unpublishable": false,
  "game_date": "2026-06-28",
  "game_importance": "LOW",
  "game_pk": 822959,
  "opponent_name": "Tampa Bay Rays",
  "publish_reason": "meets_confidence_threshold",
  "publishable": true,
  "recommended_surface": "dashboard",
  "safe_time_context": "AFTER_MOST_RECENT_GAME",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_priority": "MEDIUM",
  "story_type": "starter_covered_bullpen",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 0,
      "context_available": false,
      "limited_arms_count": 0,
      "monitor_arms_count": 0,
      "optionality_band": "insufficient_data",
      "restricted_arms_count": 0,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [],
      "clean_options_count": 0,
      "context_available": false,
      "core_retention_count": 0,
      "depth_pressure_band": "insufficient_data",
      "inactive_bullpen_arms_count": 0,
      "optionality_band": "insufficient_data",
      "practical_close_game_paths_count": 0,
      "secondary_options": [],
      "secondary_options_count": 0,
      "stability_band": "insufficient_data"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 7,
      "bullpen_entry_score_against": 5,
      "bullpen_entry_score_for": 0,
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
      "generated_at": "2026-06-30T00:53:59.350326",
      "home_away": "away",
      "id": 12,
      "largest_deficit": 5,
      "largest_lead": 0,
      "late_runs_allowed": 0,
      "lead_lost": null,
      "lead_protected": null,
      "lead_when_bullpen_entered": null,
      "opponent_name": "Tampa Bay Rays",
      "opponent_team_id": 139,
      "runs_allowed_innings_7_to_9": 0,
      "starter_exit_inning": 6,
      "starter_exit_score_against": 5,
      "starter_exit_score_for": 0,
      "starter_ip": 6.0,
      "starter_name": "Merrill Kelly",
      "starter_pitch_count": 93,
      "starter_player_id": 518876,
      "team_id": 109,
      "turning_inning": null
    },
    "evidence_blocks": {
      "available_relievers": [],
      "bullpen_entry_situation": {
        "deficit_when_entered": 5,
        "inning": 7,
        "score_against": 5,
        "score_for": 0
      },
      "bullpen_summary": {
        "available_count": 0,
        "comeback_completed": false,
        "late_runs_allowed": 0,
        "limited_count": 0,
        "monitor_count": 0,
        "optionality_band": "insufficient_data",
        "unavailable_count": 0
      },
      "clean_options": [],
      "coverage_depth": {
        "clean_options_count": 0,
        "depth_pressure_band": "insufficient_data",
        "practical_close_game_paths_count": 0,
        "secondary_options_count": 0
      },
      "evidence_version": "evidence_v1",
      "key_relief_appearances": [],
      "largest_deficit": {
        "runs": 5
      },
      "largest_lead": {
        "runs": 0
      },
      "late_runs": {
        "late_runs_allowed": 0,
        "runs_allowed_innings_7_to_9": 0
      },
      "limited_relievers": [],
      "monitor_relievers": [],
      "starter_summary": {
        "exit_inning": 6,
        "exit_score_against": 5,
        "exit_score_for": 0,
        "game_shape_created": "normal_start",
        "innings": 6.0,
        "name": "Merrill Kelly",
        "pitch_count": 93
      },
      "story_evidence": {
        "primary_story": "starter_covered_bullpen",
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
        ]
      },
      "turning_point": {},
      "unavailable_relievers": [],
      "workload_concentration": {
        "bullpen_workload_appearances_10d": 0,
        "bullpen_workload_total_10d": 0,
        "concentration_band": "insufficient_data",
        "window_days": 10
      }
    },
    "narrative_context": {
      "confidence": "HIGH",
      "context_type": "completed_game",
      "game_importance": "LOW",
      "game_pk": 822959,
      "generated_at": "2026-06-30T01:41:32.561889",
      "headline_key": "starter_carried_game",
      "primary_story": "starter_covered_bullpen",
      "secondary_story": null,
      "story_priority": "MEDIUM",
      "story_version": "narrative_context_v1",
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
      "team_id": 109
    },
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": null,
      "bullpen_workload_appearances_10d": 0,
      "bullpen_workload_total_10d": 0,
      "concentration_band": "insufficient_data",
      "context_available": true,
      "early_bullpen_entry_rate": null,
      "top_three_workload_share_10d": null,
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
Body:
```
After their most recent game, Merrill Kelly worked 6.0 innings, keeping the relief workload short. That lets the bullpen spread the work across more arms.
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
```
Exact rendered text:
```
Starter carried the load

After their most recent game, Merrill Kelly worked 6.0 innings, keeping the relief workload short. That lets the bullpen spread the work across more arms.

Evidence:
- Starter: Merrill Kelly, 6.0 IP, 93 pitches
- Largest deficit: 5
- Bullpen entered in the 7th trailing by 5
- Late runs allowed: 0
```

### Draft: dashboard

Headline:
```
Starter spared the bullpen
```
Body:
```
The club kept the bullpen light after Merrill Kelly worked 6.0 innings.
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
Starter spared the bullpen

The club kept the bullpen light after Merrill Kelly worked 6.0 innings.

Evidence:
- Starter: Merrill Kelly, 6.0 IP, 93 pitches
```

## Completed-Game Story 3: Team 110 (110)

### Story Metadata

```json
{
  "beat": "bullpen_overexposed",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_or_unpublishable": false,
  "game_date": "2026-06-28",
  "game_importance": "LOW",
  "game_pk": 824821,
  "opponent_name": "Washington Nationals",
  "publish_reason": "meets_confidence_threshold",
  "publishable": true,
  "recommended_surface": "dashboard",
  "safe_time_context": "AFTER_MOST_RECENT_GAME",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_priority": "MEDIUM",
  "story_type": "bullpen_overexposed",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 0,
      "context_available": false,
      "limited_arms_count": 0,
      "monitor_arms_count": 0,
      "optionality_band": "insufficient_data",
      "restricted_arms_count": 0,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [],
      "clean_options_count": 0,
      "context_available": false,
      "core_retention_count": 0,
      "depth_pressure_band": "insufficient_data",
      "inactive_bullpen_arms_count": 0,
      "optionality_band": "insufficient_data",
      "practical_close_game_paths_count": 0,
      "secondary_options": [],
      "secondary_options_count": 0,
      "stability_band": "insufficient_data"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 5,
      "bullpen_entry_score_against": 3,
      "bullpen_entry_score_for": 2,
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
      "generated_at": "2026-06-30T00:53:58.724065",
      "home_away": "home",
      "id": 1,
      "largest_deficit": 4,
      "largest_lead": 2,
      "late_runs_allowed": 1,
      "lead_lost": null,
      "lead_protected": null,
      "lead_when_bullpen_entered": null,
      "opponent_name": "Washington Nationals",
      "opponent_team_id": 120,
      "runs_allowed_innings_7_to_9": 1,
      "starter_exit_inning": 5,
      "starter_exit_score_against": 3,
      "starter_exit_score_for": 2,
      "starter_ip": 4.0,
      "starter_name": "Kyle Bradish",
      "starter_pitch_count": 85,
      "starter_player_id": 680694,
      "team_id": 110,
      "turning_inning": 3
    },
    "evidence_blocks": {
      "available_relievers": [],
      "bullpen_entry_situation": {
        "deficit_when_entered": 1,
        "inning": 5,
        "score_against": 3,
        "score_for": 2
      },
      "bullpen_summary": {
        "available_count": 0,
        "comeback_completed": false,
        "late_runs_allowed": 1,
        "limited_count": 0,
        "monitor_count": 0,
        "optionality_band": "insufficient_data",
        "unavailable_count": 0
      },
      "clean_options": [],
      "coverage_depth": {
        "clean_options_count": 0,
        "depth_pressure_band": "insufficient_data",
        "practical_close_game_paths_count": 0,
        "secondary_options_count": 0
      },
      "evidence_version": "evidence_v1",
      "key_relief_appearances": [],
      "largest_deficit": {
        "runs": 4
      },
      "largest_lead": {
        "runs": 2
      },
      "late_runs": {
        "late_runs_allowed": 1,
        "runs_allowed_innings_7_to_9": 1
      },
      "limited_relievers": [],
      "monitor_relievers": [],
      "starter_summary": {
        "exit_inning": 5,
        "exit_score_against": 3,
        "exit_score_for": 2,
        "game_shape_created": "short_start",
        "innings": 4.0,
        "name": "Kyle Bradish",
        "pitch_count": 85
      },
      "story_evidence": {
        "primary_story": "bullpen_overexposed",
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
        ]
      },
      "turning_point": {
        "inning": 3
      },
      "unavailable_relievers": [],
      "workload_concentration": {
        "bullpen_workload_appearances_10d": 0,
        "bullpen_workload_total_10d": 0,
        "concentration_band": "insufficient_data",
        "window_days": 10
      }
    },
    "narrative_context": {
      "confidence": "HIGH",
      "context_type": "completed_game",
      "game_importance": "LOW",
      "game_pk": 824821,
      "generated_at": "2026-06-30T01:41:32.620282",
      "headline_key": "bullpen_overexposed",
      "primary_story": "bullpen_overexposed",
      "secondary_story": null,
      "story_priority": "MEDIUM",
      "story_version": "narrative_context_v1",
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
      "team_id": 110
    },
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": null,
      "bullpen_workload_appearances_10d": 0,
      "bullpen_workload_total_10d": 0,
      "concentration_band": "insufficient_data",
      "context_available": true,
      "early_bullpen_entry_rate": null,
      "top_three_workload_share_10d": null,
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
Relievers had to cover early
```
Body:
```
After their most recent game, Kyle Bradish's four-inning start pushed the rest of the game to the bullpen, including one late run.
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
Relievers had to cover early

After their most recent game, Kyle Bradish's four-inning start pushed the rest of the game to the bullpen, including one late run.

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
Bullpen drew the long assignment
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
Bullpen drew the long assignment

The club covered heavy innings on a short start.

Evidence:
- Starter: Kyle Bradish, 4.0 IP, 85 pitches
```

## Completed-Game Story 4: Team 111 (111)

### Story Metadata

```json
{
  "beat": "protected_game_shape",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_or_unpublishable": false,
  "game_date": "2026-06-28",
  "game_importance": "MEDIUM",
  "game_pk": 824744,
  "opponent_name": "New York Yankees",
  "publish_reason": "high_priority_narrative",
  "publishable": true,
  "recommended_surface": "multiple",
  "safe_time_context": "AFTER_MOST_RECENT_GAME",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_priority": "HIGH",
  "story_type": "protected_game_shape",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 0,
      "context_available": false,
      "limited_arms_count": 0,
      "monitor_arms_count": 0,
      "optionality_band": "insufficient_data",
      "restricted_arms_count": 0,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [],
      "clean_options_count": 0,
      "context_available": false,
      "core_retention_count": 0,
      "depth_pressure_band": "insufficient_data",
      "inactive_bullpen_arms_count": 0,
      "optionality_band": "insufficient_data",
      "practical_close_game_paths_count": 0,
      "secondary_options": [],
      "secondary_options_count": 0,
      "stability_band": "insufficient_data"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 8,
      "bullpen_entry_score_against": 0,
      "bullpen_entry_score_for": 2,
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
      "generated_at": "2026-06-30T00:54:00.600078",
      "home_away": "home",
      "id": 29,
      "largest_deficit": 2,
      "largest_lead": 2,
      "late_runs_allowed": 4,
      "lead_lost": false,
      "lead_protected": true,
      "lead_when_bullpen_entered": 2,
      "opponent_name": "New York Yankees",
      "opponent_team_id": 147,
      "runs_allowed_innings_7_to_9": 2,
      "starter_exit_inning": 8,
      "starter_exit_score_against": 0,
      "starter_exit_score_for": 2,
      "starter_ip": 7.333333333333333,
      "starter_name": "Sonny Gray",
      "starter_pitch_count": 97,
      "starter_player_id": 543243,
      "team_id": 111,
      "turning_inning": 10
    },
    "evidence_blocks": {
      "available_relievers": [],
      "bullpen_entry_situation": {
        "inning": 8,
        "lead_when_entered": 2,
        "score_against": 0,
        "score_for": 2
      },
      "bullpen_summary": {
        "available_count": 0,
        "comeback_completed": true,
        "late_runs_allowed": 4,
        "lead_lost": false,
        "lead_protected": true,
        "limited_count": 0,
        "monitor_count": 0,
        "optionality_band": "insufficient_data",
        "unavailable_count": 0
      },
      "clean_options": [],
      "coverage_depth": {
        "clean_options_count": 0,
        "depth_pressure_band": "insufficient_data",
        "practical_close_game_paths_count": 0,
        "secondary_options_count": 0
      },
      "evidence_version": "evidence_v1",
      "key_relief_appearances": [],
      "largest_deficit": {
        "runs": 2
      },
      "largest_lead": {
        "runs": 2
      },
      "late_runs": {
        "late_runs_allowed": 4,
        "runs_allowed_innings_7_to_9": 2
      },
      "limited_relievers": [],
      "monitor_relievers": [],
      "starter_summary": {
        "exit_inning": 8,
        "exit_score_against": 0,
        "exit_score_for": 2,
        "game_shape_created": "normal_start",
        "innings": 7.333333333333333,
        "name": "Sonny Gray",
        "pitch_count": 97
      },
      "story_evidence": {
        "primary_story": "protected_game_shape",
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
        ]
      },
      "turning_point": {
        "inning": 10
      },
      "unavailable_relievers": [],
      "workload_concentration": {
        "bullpen_workload_appearances_10d": 0,
        "bullpen_workload_total_10d": 0,
        "concentration_band": "insufficient_data",
        "window_days": 10
      }
    },
    "narrative_context": {
      "confidence": "HIGH",
      "context_type": "completed_game",
      "game_importance": "MEDIUM",
      "game_pk": 824744,
      "generated_at": "2026-06-30T01:41:32.678919",
      "headline_key": "protected_game_shape",
      "primary_story": "protected_game_shape",
      "secondary_story": "bullpen_kept_team_alive",
      "story_priority": "HIGH",
      "story_version": "narrative_context_v1",
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
      "team_id": 111
    },
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": null,
      "bullpen_workload_appearances_10d": 0,
      "bullpen_workload_total_10d": 0,
      "concentration_band": "insufficient_data",
      "context_available": true,
      "early_bullpen_entry_rate": null,
      "top_three_workload_share_10d": null,
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
Late lead closed out
```
Body:
```
After their most recent game, Sonny Gray reached the 8th with a two-run lead, and the bullpen finished it.
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
- Starter: Sonny Gray, 7.1 IP, 97 pitches
- Largest lead: 2
- Bullpen entered in the 8th with a 2-run lead
- Turning point: 10th inning
- Late runs allowed: 4
```
Exact rendered text:
```
Late lead closed out

After their most recent game, Sonny Gray reached the 8th with a two-run lead, and the bullpen finished it.

Why BaseballOS sees it:
- The starter went deep and set the bullpen up to finish the game.
- The bullpen took over with a lead in hand.
- The relievers held the lead.
- The damage came after the starter exited and piled up late.

Evidence:
- Starter: Sonny Gray, 7.1 IP, 97 pitches
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
- Starter: Sonny Gray, 7.1 IP, 97 pitches
```
Exact rendered text:
```
Lead protected

The club protected a 2-run lead.

Evidence:
- Starter: Sonny Gray, 7.1 IP, 97 pitches
```

### Draft: morning_brief

Headline:
```
Bullpen note: Late lead held
```
Body:
```
After their most recent game, the club turned a two-run lead into a win the bullpen never let slip.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Sonny Gray, 7.1 IP, 97 pitches
- Largest lead: 2
- Bullpen entered in the 8th with a 2-run lead
- Turning point: 10th inning
- Late runs allowed: 4
```
Exact rendered text:
```
Bullpen note: Late lead held

After their most recent game, the club turned a two-run lead into a win the bullpen never let slip.

Evidence:
- Starter: Sonny Gray, 7.1 IP, 97 pitches
- Largest lead: 2
- Bullpen entered in the 8th with a 2-run lead
- Turning point: 10th inning
- Late runs allowed: 4
```

## Completed-Game Story 5: Team 112 (112)

### Story Metadata

```json
{
  "beat": "bullpen_overexposed",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_or_unpublishable": false,
  "game_date": "2026-06-28",
  "game_importance": "MEDIUM",
  "game_pk": 823769,
  "opponent_name": "Milwaukee Brewers",
  "publish_reason": "meets_confidence_threshold",
  "publishable": true,
  "recommended_surface": "team_page",
  "safe_time_context": "AFTER_MOST_RECENT_GAME",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_priority": "MEDIUM",
  "story_type": "bullpen_overexposed",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 0,
      "context_available": false,
      "limited_arms_count": 0,
      "monitor_arms_count": 0,
      "optionality_band": "insufficient_data",
      "restricted_arms_count": 0,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [],
      "clean_options_count": 0,
      "context_available": false,
      "core_retention_count": 0,
      "depth_pressure_band": "insufficient_data",
      "inactive_bullpen_arms_count": 0,
      "optionality_band": "insufficient_data",
      "practical_close_game_paths_count": 0,
      "secondary_options": [],
      "secondary_options_count": 0,
      "stability_band": "insufficient_data"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 3,
      "bullpen_entry_score_against": 1,
      "bullpen_entry_score_for": 0,
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
      "generated_at": "2026-06-30T00:53:59.838945",
      "home_away": "away",
      "id": 20,
      "largest_deficit": 1,
      "largest_lead": 3,
      "late_runs_allowed": 2,
      "lead_lost": null,
      "lead_protected": null,
      "lead_when_bullpen_entered": null,
      "opponent_name": "Milwaukee Brewers",
      "opponent_team_id": 158,
      "runs_allowed_innings_7_to_9": 0,
      "starter_exit_inning": 2,
      "starter_exit_score_against": 1,
      "starter_exit_score_for": 0,
      "starter_ip": 2.0,
      "starter_name": "Ryan Rolison",
      "starter_pitch_count": 23,
      "starter_player_id": 669020,
      "team_id": 112,
      "turning_inning": 10
    },
    "evidence_blocks": {
      "available_relievers": [],
      "bullpen_entry_situation": {
        "deficit_when_entered": 1,
        "inning": 3,
        "score_against": 1,
        "score_for": 0
      },
      "bullpen_summary": {
        "available_count": 0,
        "comeback_completed": true,
        "late_runs_allowed": 2,
        "limited_count": 0,
        "monitor_count": 0,
        "optionality_band": "insufficient_data",
        "unavailable_count": 0
      },
      "clean_options": [],
      "coverage_depth": {
        "clean_options_count": 0,
        "depth_pressure_band": "insufficient_data",
        "practical_close_game_paths_count": 0,
        "secondary_options_count": 0
      },
      "evidence_version": "evidence_v1",
      "key_relief_appearances": [],
      "largest_deficit": {
        "runs": 1
      },
      "largest_lead": {
        "runs": 3
      },
      "late_runs": {
        "late_runs_allowed": 2,
        "runs_allowed_innings_7_to_9": 0
      },
      "limited_relievers": [],
      "monitor_relievers": [],
      "starter_summary": {
        "exit_inning": 2,
        "exit_score_against": 1,
        "exit_score_for": 0,
        "game_shape_created": "opener_bulk_game",
        "innings": 2.0,
        "name": "Ryan Rolison",
        "pitch_count": 23
      },
      "story_evidence": {
        "primary_story": "bullpen_overexposed",
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
        ]
      },
      "turning_point": {
        "inning": 10
      },
      "unavailable_relievers": [],
      "workload_concentration": {
        "bullpen_workload_appearances_10d": 4,
        "bullpen_workload_total_10d": 57,
        "concentration_band": "narrow",
        "top_three_workload_share_10d": 84.2,
        "window_days": 10
      }
    },
    "narrative_context": {
      "confidence": "HIGH",
      "context_type": "completed_game",
      "game_importance": "MEDIUM",
      "game_pk": 823769,
      "generated_at": "2026-06-30T01:41:32.766391",
      "headline_key": "bullpen_overexposed",
      "primary_story": "bullpen_overexposed",
      "secondary_story": "bullpen_kept_team_alive",
      "story_priority": "MEDIUM",
      "story_version": "narrative_context_v1",
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
      "team_id": 112
    },
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": null,
      "bullpen_workload_appearances_10d": 4,
      "bullpen_workload_total_10d": 57,
      "concentration_band": "narrow",
      "context_available": true,
      "early_bullpen_entry_rate": null,
      "top_three_workload_share_10d": 84.2,
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
Relievers had to cover early
```
Body:
```
After their most recent game, Ryan Rolison's two-inning start pushed the rest of the game to the bullpen, including two late runs.
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
Relievers had to cover early

After their most recent game, Ryan Rolison's two-inning start pushed the rest of the game to the bullpen, including two late runs.

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
Bullpen drew the long assignment
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
Bullpen drew the long assignment

The club covered heavy innings on a short start.

Evidence:
- Starter: Ryan Rolison, 2.0 IP, 23 pitches
```

## Completed-Game Story 6: Team 113 (113)

### Story Metadata

```json
{
  "beat": "insufficient_context",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_or_unpublishable": true,
  "game_date": "2026-06-28",
  "game_importance": "LOW",
  "game_pk": 823362,
  "opponent_name": "Pittsburgh Pirates",
  "publish_reason": "insufficient_confidence",
  "publishable": false,
  "recommended_surface": "none",
  "safe_time_context": "CURRENT_STATUS",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_priority": "LOW",
  "story_type": "insufficient_context",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 0,
      "context_available": false,
      "limited_arms_count": 0,
      "monitor_arms_count": 0,
      "optionality_band": "insufficient_data",
      "restricted_arms_count": 0,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [],
      "clean_options_count": 0,
      "context_available": false,
      "core_retention_count": 0,
      "depth_pressure_band": "insufficient_data",
      "inactive_bullpen_arms_count": 0,
      "optionality_band": "insufficient_data",
      "practical_close_game_paths_count": 0,
      "secondary_options": [],
      "secondary_options_count": 0,
      "stability_band": "insufficient_data"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 5,
      "bullpen_entry_score_against": 5,
      "bullpen_entry_score_for": 4,
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
      "generated_at": "2026-06-30T00:53:58.832401",
      "home_away": "away",
      "id": 4,
      "largest_deficit": 5,
      "largest_lead": 0,
      "late_runs_allowed": 4,
      "lead_lost": null,
      "lead_protected": null,
      "lead_when_bullpen_entered": null,
      "opponent_name": "Pittsburgh Pirates",
      "opponent_team_id": 134,
      "runs_allowed_innings_7_to_9": 4,
      "starter_exit_inning": 5,
      "starter_exit_score_against": 5,
      "starter_exit_score_for": 4,
      "starter_ip": 4.333333333333333,
      "starter_name": "Brady Singer",
      "starter_pitch_count": 98,
      "starter_player_id": 663903,
      "team_id": 113,
      "turning_inning": null
    },
    "evidence_blocks": {
      "available_relievers": [],
      "bullpen_entry_situation": {
        "deficit_when_entered": 1,
        "inning": 5,
        "score_against": 5,
        "score_for": 4
      },
      "bullpen_summary": {
        "available_count": 0,
        "comeback_completed": false,
        "late_runs_allowed": 4,
        "limited_count": 0,
        "monitor_count": 0,
        "optionality_band": "insufficient_data",
        "unavailable_count": 0
      },
      "clean_options": [],
      "coverage_depth": {
        "clean_options_count": 0,
        "depth_pressure_band": "insufficient_data",
        "practical_close_game_paths_count": 0,
        "secondary_options_count": 0
      },
      "evidence_version": "evidence_v1",
      "key_relief_appearances": [],
      "largest_deficit": {
        "runs": 5
      },
      "largest_lead": {
        "runs": 0
      },
      "late_runs": {
        "late_runs_allowed": 4,
        "runs_allowed_innings_7_to_9": 4
      },
      "limited_relievers": [],
      "monitor_relievers": [],
      "starter_summary": {
        "exit_inning": 5,
        "exit_score_against": 5,
        "exit_score_for": 4,
        "game_shape_created": "short_start",
        "innings": 4.333333333333333,
        "name": "Brady Singer",
        "pitch_count": 98
      },
      "story_evidence": {
        "primary_story": "insufficient_context",
        "supporting_facts": {},
        "supporting_observations": []
      },
      "turning_point": {},
      "unavailable_relievers": [],
      "workload_concentration": {
        "bullpen_workload_appearances_10d": 2,
        "bullpen_workload_total_10d": 36,
        "concentration_band": "narrow",
        "top_three_workload_share_10d": 100.0,
        "window_days": 10
      }
    },
    "narrative_context": {
      "confidence": "HIGH",
      "context_type": "completed_game",
      "game_importance": "LOW",
      "game_pk": 823362,
      "generated_at": "2026-06-30T01:41:32.892231",
      "headline_key": "insufficient_context",
      "primary_story": "insufficient_context",
      "secondary_story": null,
      "story_priority": "LOW",
      "story_version": "narrative_context_v1",
      "summary_key": "insufficient_context",
      "supporting_facts": {},
      "supporting_observations": [],
      "team_id": 113
    },
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": null,
      "bullpen_workload_appearances_10d": 2,
      "bullpen_workload_total_10d": 36,
      "concentration_band": "narrow",
      "context_available": true,
      "early_bullpen_entry_rate": 100.0,
      "top_three_workload_share_10d": 100.0,
      "window_days": 10
    }
  },
  "team_id": 113,
  "writer_targets": []
}
```

No draft rendered.

## Completed-Game Story 7: Team 114 (114)

### Story Metadata

```json
{
  "beat": "bullpen_kept_team_alive",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_or_unpublishable": false,
  "game_date": "2026-06-28",
  "game_importance": "MEDIUM",
  "game_pk": 824422,
  "opponent_name": "Seattle Mariners",
  "publish_reason": "high_priority_narrative",
  "publishable": true,
  "recommended_surface": "multiple",
  "safe_time_context": "AFTER_MOST_RECENT_GAME",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_priority": "HIGH",
  "story_type": "bullpen_kept_team_alive",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 0,
      "context_available": false,
      "limited_arms_count": 0,
      "monitor_arms_count": 0,
      "optionality_band": "insufficient_data",
      "restricted_arms_count": 0,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [],
      "clean_options_count": 0,
      "context_available": false,
      "core_retention_count": 0,
      "depth_pressure_band": "insufficient_data",
      "inactive_bullpen_arms_count": 0,
      "optionality_band": "insufficient_data",
      "practical_close_game_paths_count": 0,
      "secondary_options": [],
      "secondary_options_count": 0,
      "stability_band": "insufficient_data"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 6,
      "bullpen_entry_score_against": 3,
      "bullpen_entry_score_for": 1,
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
      "generated_at": "2026-06-30T00:53:59.193808",
      "home_away": "home",
      "id": 9,
      "largest_deficit": 3,
      "largest_lead": 2,
      "late_runs_allowed": 1,
      "lead_lost": null,
      "lead_protected": null,
      "lead_when_bullpen_entered": null,
      "opponent_name": "Seattle Mariners",
      "opponent_team_id": 136,
      "runs_allowed_innings_7_to_9": 1,
      "starter_exit_inning": 5,
      "starter_exit_score_against": 3,
      "starter_exit_score_for": 0,
      "starter_ip": 5.0,
      "starter_name": "Gavin Williams",
      "starter_pitch_count": 103,
      "starter_player_id": 668909,
      "team_id": 114,
      "turning_inning": 8
    },
    "evidence_blocks": {
      "available_relievers": [],
      "bullpen_entry_situation": {
        "deficit_when_entered": 2,
        "inning": 6,
        "score_against": 3,
        "score_for": 1
      },
      "bullpen_summary": {
        "available_count": 0,
        "comeback_completed": true,
        "late_runs_allowed": 1,
        "limited_count": 0,
        "monitor_count": 0,
        "optionality_band": "insufficient_data",
        "unavailable_count": 0
      },
      "clean_options": [],
      "coverage_depth": {
        "clean_options_count": 0,
        "depth_pressure_band": "insufficient_data",
        "practical_close_game_paths_count": 0,
        "secondary_options_count": 0
      },
      "evidence_version": "evidence_v1",
      "key_relief_appearances": [],
      "largest_deficit": {
        "runs": 3
      },
      "largest_lead": {
        "runs": 2
      },
      "late_runs": {
        "late_runs_allowed": 1,
        "runs_allowed_innings_7_to_9": 1
      },
      "limited_relievers": [],
      "monitor_relievers": [],
      "starter_summary": {
        "exit_inning": 5,
        "exit_score_against": 3,
        "exit_score_for": 0,
        "game_shape_created": "normal_start",
        "innings": 5.0,
        "name": "Gavin Williams",
        "pitch_count": 103
      },
      "story_evidence": {
        "primary_story": "bullpen_kept_team_alive",
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
        ]
      },
      "turning_point": {
        "inning": 8
      },
      "unavailable_relievers": [],
      "workload_concentration": {
        "bullpen_workload_appearances_10d": 0,
        "bullpen_workload_total_10d": 0,
        "concentration_band": "insufficient_data",
        "window_days": 10
      }
    },
    "narrative_context": {
      "confidence": "HIGH",
      "context_type": "completed_game",
      "game_importance": "MEDIUM",
      "game_pk": 824422,
      "generated_at": "2026-06-30T01:41:32.951856",
      "headline_key": "bullpen_kept_team_alive",
      "primary_story": "bullpen_kept_team_alive",
      "secondary_story": null,
      "story_priority": "HIGH",
      "story_version": "narrative_context_v1",
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
      "team_id": 114
    },
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": null,
      "bullpen_workload_appearances_10d": 0,
      "bullpen_workload_total_10d": 0,
      "concentration_band": "insufficient_data",
      "context_available": true,
      "early_bullpen_entry_rate": null,
      "top_three_workload_share_10d": null,
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
Relievers left room for the rally
```
Body:
```
After their most recent game, Gavin Williams worked five innings before the bullpen entered in the 6th trailing by two, and the deficit held there. The offense finished the rally.
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
Relievers left room for the rally

After their most recent game, Gavin Williams worked five innings before the bullpen entered in the 6th trailing by two, and the deficit held there. The offense finished the rally.

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
Bullpen gave the comeback room
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
Bullpen gave the comeback room

The club kept the comeback alive.

Evidence:
- Starter: Gavin Williams, 5.0 IP, 103 pitches
```

### Draft: morning_brief

Headline:
```
Bullpen note: Bullpen kept it alive
```
Body:
```
After their most recent game, the club climbed out of a two-run hole the bullpen kept from growing.
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

After their most recent game, the club climbed out of a two-run hole the bullpen kept from growing.

Evidence:
- Starter: Gavin Williams, 5.0 IP, 103 pitches
- Largest deficit: 3
- Bullpen entered in the 6th trailing by 2
- Turning point: 8th inning
- Late runs allowed: 1
```

## Completed-Game Story 8: Team 115 (115)

### Story Metadata

```json
{
  "beat": "starter_covered_bullpen",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_or_unpublishable": false,
  "game_date": "2026-06-28",
  "game_importance": "LOW",
  "game_pk": 823686,
  "opponent_name": "Minnesota Twins",
  "publish_reason": "meets_confidence_threshold",
  "publishable": true,
  "recommended_surface": "dashboard",
  "safe_time_context": "AFTER_MOST_RECENT_GAME",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_priority": "MEDIUM",
  "story_type": "starter_covered_bullpen",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 0,
      "context_available": false,
      "limited_arms_count": 0,
      "monitor_arms_count": 0,
      "optionality_band": "insufficient_data",
      "restricted_arms_count": 0,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [],
      "clean_options_count": 0,
      "context_available": false,
      "core_retention_count": 0,
      "depth_pressure_band": "insufficient_data",
      "inactive_bullpen_arms_count": 0,
      "optionality_band": "insufficient_data",
      "practical_close_game_paths_count": 0,
      "secondary_options": [],
      "secondary_options_count": 0,
      "stability_band": "insufficient_data"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 7,
      "bullpen_entry_score_against": 2,
      "bullpen_entry_score_for": 2,
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
      "generated_at": "2026-06-30T00:53:59.636930",
      "home_away": "away",
      "id": 16,
      "largest_deficit": 1,
      "largest_lead": 1,
      "late_runs_allowed": 1,
      "lead_lost": null,
      "lead_protected": null,
      "lead_when_bullpen_entered": null,
      "opponent_name": "Minnesota Twins",
      "opponent_team_id": 142,
      "runs_allowed_innings_7_to_9": 1,
      "starter_exit_inning": 6,
      "starter_exit_score_against": 2,
      "starter_exit_score_for": 2,
      "starter_ip": 6.0,
      "starter_name": "Ryan Feltner",
      "starter_pitch_count": 82,
      "starter_player_id": 663372,
      "team_id": 115,
      "turning_inning": 4
    },
    "evidence_blocks": {
      "available_relievers": [],
      "bullpen_entry_situation": {
        "inning": 7,
        "score_against": 2,
        "score_for": 2
      },
      "bullpen_summary": {
        "available_count": 0,
        "comeback_completed": false,
        "late_runs_allowed": 1,
        "limited_count": 0,
        "monitor_count": 0,
        "optionality_band": "insufficient_data",
        "unavailable_count": 0
      },
      "clean_options": [],
      "coverage_depth": {
        "clean_options_count": 0,
        "depth_pressure_band": "insufficient_data",
        "practical_close_game_paths_count": 0,
        "secondary_options_count": 0
      },
      "evidence_version": "evidence_v1",
      "key_relief_appearances": [],
      "largest_deficit": {
        "runs": 1
      },
      "largest_lead": {
        "runs": 1
      },
      "late_runs": {
        "late_runs_allowed": 1,
        "runs_allowed_innings_7_to_9": 1
      },
      "limited_relievers": [],
      "monitor_relievers": [],
      "starter_summary": {
        "exit_inning": 6,
        "exit_score_against": 2,
        "exit_score_for": 2,
        "game_shape_created": "normal_start",
        "innings": 6.0,
        "name": "Ryan Feltner",
        "pitch_count": 82
      },
      "story_evidence": {
        "primary_story": "starter_covered_bullpen",
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
        ]
      },
      "turning_point": {
        "inning": 4
      },
      "unavailable_relievers": [],
      "workload_concentration": {
        "bullpen_workload_appearances_10d": 0,
        "bullpen_workload_total_10d": 0,
        "concentration_band": "insufficient_data",
        "window_days": 10
      }
    },
    "narrative_context": {
      "confidence": "HIGH",
      "context_type": "completed_game",
      "game_importance": "LOW",
      "game_pk": 823686,
      "generated_at": "2026-06-30T01:41:33.022491",
      "headline_key": "starter_carried_game",
      "primary_story": "starter_covered_bullpen",
      "secondary_story": null,
      "story_priority": "MEDIUM",
      "story_version": "narrative_context_v1",
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
      "team_id": 115
    },
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": null,
      "bullpen_workload_appearances_10d": 0,
      "bullpen_workload_total_10d": 0,
      "concentration_band": "insufficient_data",
      "context_available": true,
      "early_bullpen_entry_rate": null,
      "top_three_workload_share_10d": null,
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
Starter spared the bullpen
```
Body:
```
After their most recent game, Ryan Feltner worked 6.0 innings, before the bullpen took over for a shorter handoff. That lets the bullpen spread the work across more arms.
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
Starter spared the bullpen

After their most recent game, Ryan Feltner worked 6.0 innings, before the bullpen took over for a shorter handoff. That lets the bullpen spread the work across more arms.

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
Deep start lightened the load
```
Body:
```
The club kept the bullpen light after Ryan Feltner worked 6.0 innings.
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
Deep start lightened the load

The club kept the bullpen light after Ryan Feltner worked 6.0 innings.

Evidence:
- Starter: Ryan Feltner, 6.0 IP, 82 pitches
```

## Completed-Game Story 9: Team 116 (116)

### Story Metadata

```json
{
  "beat": "lost_game_shape",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_or_unpublishable": false,
  "game_date": "2026-06-28",
  "game_importance": "HIGH",
  "game_pk": 824256,
  "opponent_name": "Houston Astros",
  "publish_reason": "critical_narrative",
  "publishable": true,
  "recommended_surface": "multiple",
  "safe_time_context": "AFTER_MOST_RECENT_GAME",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_priority": "CRITICAL",
  "story_type": "lost_game_shape",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 0,
      "context_available": false,
      "limited_arms_count": 0,
      "monitor_arms_count": 0,
      "optionality_band": "insufficient_data",
      "restricted_arms_count": 0,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [],
      "clean_options_count": 0,
      "context_available": false,
      "core_retention_count": 0,
      "depth_pressure_band": "insufficient_data",
      "inactive_bullpen_arms_count": 0,
      "optionality_band": "insufficient_data",
      "practical_close_game_paths_count": 0,
      "secondary_options": [],
      "secondary_options_count": 0,
      "stability_band": "insufficient_data"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 6,
      "bullpen_entry_score_against": 0,
      "bullpen_entry_score_for": 3,
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
      "generated_at": "2026-06-30T00:53:59.101365",
      "home_away": "home",
      "id": 7,
      "largest_deficit": 4,
      "largest_lead": 3,
      "late_runs_allowed": 7,
      "lead_lost": true,
      "lead_protected": false,
      "lead_when_bullpen_entered": 3,
      "opponent_name": "Houston Astros",
      "opponent_team_id": 117,
      "runs_allowed_innings_7_to_9": 3,
      "starter_exit_inning": 5,
      "starter_exit_score_against": 0,
      "starter_exit_score_for": 2,
      "starter_ip": 5.0,
      "starter_name": "Jack Flaherty",
      "starter_pitch_count": 94,
      "starter_player_id": 656427,
      "team_id": 116,
      "turning_inning": 10
    },
    "evidence_blocks": {
      "available_relievers": [],
      "bullpen_entry_situation": {
        "inning": 6,
        "lead_when_entered": 3,
        "score_against": 0,
        "score_for": 3
      },
      "bullpen_summary": {
        "available_count": 0,
        "comeback_completed": false,
        "late_runs_allowed": 7,
        "lead_lost": true,
        "lead_protected": false,
        "limited_count": 0,
        "monitor_count": 0,
        "optionality_band": "insufficient_data",
        "unavailable_count": 0
      },
      "clean_options": [],
      "coverage_depth": {
        "bullpen_coverage_ip_7d": 4.3,
        "clean_options_count": 0,
        "depth_pressure_band": "insufficient_data",
        "practical_close_game_paths_count": 0,
        "secondary_options_count": 0
      },
      "evidence_version": "evidence_v1",
      "key_relief_appearances": [],
      "largest_deficit": {
        "runs": 4
      },
      "largest_lead": {
        "runs": 3
      },
      "late_runs": {
        "late_runs_allowed": 7,
        "runs_allowed_innings_7_to_9": 3
      },
      "limited_relievers": [],
      "monitor_relievers": [],
      "starter_summary": {
        "exit_inning": 5,
        "exit_score_against": 0,
        "exit_score_for": 2,
        "game_shape_created": "normal_start",
        "innings": 5.0,
        "name": "Jack Flaherty",
        "pitch_count": 94
      },
      "story_evidence": {
        "primary_story": "lost_game_shape",
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
        ]
      },
      "turning_point": {
        "inning": 10
      },
      "unavailable_relievers": [],
      "workload_concentration": {
        "bullpen_workload_appearances_10d": 3,
        "bullpen_workload_total_10d": 76,
        "concentration_band": "narrow",
        "top_three_workload_share_10d": 100.0,
        "window_days": 10
      }
    },
    "narrative_context": {
      "confidence": "HIGH",
      "context_type": "completed_game",
      "game_importance": "HIGH",
      "game_pk": 824256,
      "generated_at": "2026-06-30T01:41:33.124110",
      "headline_key": "lost_game_shape",
      "primary_story": "lost_game_shape",
      "secondary_story": "late_pressure_accumulated",
      "story_priority": "CRITICAL",
      "story_version": "narrative_context_v1",
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
      "team_id": 116
    },
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": 4.3,
      "bullpen_workload_appearances_10d": 3,
      "bullpen_workload_total_10d": 76,
      "concentration_band": "narrow",
      "context_available": true,
      "early_bullpen_entry_rate": 0.0,
      "top_three_workload_share_10d": 100.0,
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
Lead disappeared late
```
Body:
```
After their most recent game, Jack Flaherty's five strong innings staked a three-run lead heading to the late innings. It didn't last. Seven late runs turned the game. That keeps the work gathered on a smaller group.
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
Lead disappeared late

After their most recent game, Jack Flaherty's five strong innings staked a three-run lead heading to the late innings. It didn't last. Seven late runs turned the game. That keeps the work gathered on a smaller group.

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
Bullpen note: Late lead slipped away
```
Body:
```
After their most recent game, the club carried a three-run lead into the late innings and let it get away on seven late runs. The late damage leaves the bullpen with less margin. That keeps the work gathered on a smaller group.
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
Bullpen note: Late lead slipped away

After their most recent game, the club carried a three-run lead into the late innings and let it get away on seven late runs. The late damage leaves the bullpen with less margin. That keeps the work gathered on a smaller group.

Evidence:
- Starter: Jack Flaherty, 5.0 IP, 94 pitches
- Largest lead: 3
- Bullpen entered in the 6th with a 3-run lead
- Turning point: 10th inning
- Late runs allowed: 7
```

## Completed-Game Story 10: Team 117 (117)

### Story Metadata

```json
{
  "beat": "insufficient_context",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_or_unpublishable": true,
  "game_date": "2026-06-28",
  "game_importance": "LOW",
  "game_pk": 824256,
  "opponent_name": "Detroit Tigers",
  "publish_reason": "insufficient_confidence",
  "publishable": false,
  "recommended_surface": "none",
  "safe_time_context": "CURRENT_STATUS",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_priority": "LOW",
  "story_type": "insufficient_context",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 0,
      "context_available": false,
      "limited_arms_count": 0,
      "monitor_arms_count": 0,
      "optionality_band": "insufficient_data",
      "restricted_arms_count": 0,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [],
      "clean_options_count": 0,
      "context_available": false,
      "core_retention_count": 0,
      "depth_pressure_band": "insufficient_data",
      "inactive_bullpen_arms_count": 0,
      "optionality_band": "insufficient_data",
      "practical_close_game_paths_count": 0,
      "secondary_options": [],
      "secondary_options_count": 0,
      "stability_band": "insufficient_data"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 7,
      "bullpen_entry_score_against": 3,
      "bullpen_entry_score_for": 2,
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
      "generated_at": "2026-06-30T00:53:59.101938",
      "home_away": "away",
      "id": 8,
      "largest_deficit": 3,
      "largest_lead": 4,
      "late_runs_allowed": 2,
      "lead_lost": null,
      "lead_protected": null,
      "lead_when_bullpen_entered": null,
      "opponent_name": "Detroit Tigers",
      "opponent_team_id": 116,
      "runs_allowed_innings_7_to_9": 0,
      "starter_exit_inning": 6,
      "starter_exit_score_against": 3,
      "starter_exit_score_for": 0,
      "starter_ip": 6.0,
      "starter_name": "Hunter Brown",
      "starter_pitch_count": 103,
      "starter_player_id": 686613,
      "team_id": 117,
      "turning_inning": 10
    },
    "evidence_blocks": {
      "available_relievers": [],
      "bullpen_entry_situation": {
        "deficit_when_entered": 1,
        "inning": 7,
        "score_against": 3,
        "score_for": 2
      },
      "bullpen_summary": {
        "available_count": 0,
        "comeback_completed": true,
        "late_runs_allowed": 2,
        "limited_count": 0,
        "monitor_count": 0,
        "optionality_band": "insufficient_data",
        "unavailable_count": 0
      },
      "clean_options": [],
      "coverage_depth": {
        "clean_options_count": 0,
        "depth_pressure_band": "insufficient_data",
        "practical_close_game_paths_count": 0,
        "secondary_options_count": 0
      },
      "evidence_version": "evidence_v1",
      "key_relief_appearances": [],
      "largest_deficit": {
        "runs": 3
      },
      "largest_lead": {
        "runs": 4
      },
      "late_runs": {
        "late_runs_allowed": 2,
        "runs_allowed_innings_7_to_9": 0
      },
      "limited_relievers": [],
      "monitor_relievers": [],
      "starter_summary": {
        "exit_inning": 6,
        "exit_score_against": 3,
        "exit_score_for": 0,
        "game_shape_created": "normal_start",
        "innings": 6.0,
        "name": "Hunter Brown",
        "pitch_count": 103
      },
      "story_evidence": {
        "primary_story": "insufficient_context",
        "supporting_facts": {},
        "supporting_observations": []
      },
      "turning_point": {
        "inning": 10
      },
      "unavailable_relievers": [],
      "workload_concentration": {
        "bullpen_workload_appearances_10d": 0,
        "bullpen_workload_total_10d": 0,
        "concentration_band": "insufficient_data",
        "window_days": 10
      }
    },
    "narrative_context": {
      "confidence": "HIGH",
      "context_type": "completed_game",
      "game_importance": "LOW",
      "game_pk": 824256,
      "generated_at": "2026-06-30T01:41:33.198548",
      "headline_key": "insufficient_context",
      "primary_story": "insufficient_context",
      "secondary_story": null,
      "story_priority": "LOW",
      "story_version": "narrative_context_v1",
      "summary_key": "insufficient_context",
      "supporting_facts": {},
      "supporting_observations": [],
      "team_id": 117
    },
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": null,
      "bullpen_workload_appearances_10d": 0,
      "bullpen_workload_total_10d": 0,
      "concentration_band": "insufficient_data",
      "context_available": true,
      "early_bullpen_entry_rate": null,
      "top_three_workload_share_10d": null,
      "window_days": 10
    }
  },
  "team_id": 117,
  "writer_targets": []
}
```

No draft rendered.

## Completed-Game Story 11: Team 118 (118)

### Story Metadata

```json
{
  "beat": "bullpen_overexposed",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_or_unpublishable": false,
  "game_date": "2026-06-28",
  "game_importance": "LOW",
  "game_pk": 824580,
  "opponent_name": "Chicago White Sox",
  "publish_reason": "meets_confidence_threshold",
  "publishable": true,
  "recommended_surface": "dashboard",
  "safe_time_context": "AFTER_MOST_RECENT_GAME",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_priority": "MEDIUM",
  "story_type": "bullpen_overexposed",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 0,
      "context_available": false,
      "limited_arms_count": 0,
      "monitor_arms_count": 0,
      "optionality_band": "insufficient_data",
      "restricted_arms_count": 0,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [],
      "clean_options_count": 0,
      "context_available": false,
      "core_retention_count": 0,
      "depth_pressure_band": "insufficient_data",
      "inactive_bullpen_arms_count": 0,
      "optionality_band": "insufficient_data",
      "practical_close_game_paths_count": 0,
      "secondary_options": [],
      "secondary_options_count": 0,
      "stability_band": "insufficient_data"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 5,
      "bullpen_entry_score_against": 4,
      "bullpen_entry_score_for": 5,
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
      "generated_at": "2026-06-30T00:53:59.727789",
      "home_away": "away",
      "id": 18,
      "largest_deficit": 1,
      "largest_lead": 1,
      "late_runs_allowed": 0,
      "lead_lost": false,
      "lead_protected": true,
      "lead_when_bullpen_entered": 1,
      "opponent_name": "Chicago White Sox",
      "opponent_team_id": 145,
      "runs_allowed_innings_7_to_9": 0,
      "starter_exit_inning": 4,
      "starter_exit_score_against": 4,
      "starter_exit_score_for": 5,
      "starter_ip": 4.0,
      "starter_name": "Luinder Avila",
      "starter_pitch_count": 86,
      "starter_player_id": 679883,
      "team_id": 118,
      "turning_inning": 4
    },
    "evidence_blocks": {
      "available_relievers": [],
      "bullpen_entry_situation": {
        "inning": 5,
        "lead_when_entered": 1,
        "score_against": 4,
        "score_for": 5
      },
      "bullpen_summary": {
        "available_count": 0,
        "comeback_completed": true,
        "late_runs_allowed": 0,
        "lead_lost": false,
        "lead_protected": true,
        "limited_count": 0,
        "monitor_count": 0,
        "optionality_band": "insufficient_data",
        "unavailable_count": 0
      },
      "clean_options": [],
      "coverage_depth": {
        "clean_options_count": 0,
        "depth_pressure_band": "insufficient_data",
        "practical_close_game_paths_count": 0,
        "secondary_options_count": 0
      },
      "evidence_version": "evidence_v1",
      "key_relief_appearances": [],
      "largest_deficit": {
        "runs": 1
      },
      "largest_lead": {
        "runs": 1
      },
      "late_runs": {
        "late_runs_allowed": 0,
        "runs_allowed_innings_7_to_9": 0
      },
      "limited_relievers": [],
      "monitor_relievers": [],
      "starter_summary": {
        "exit_inning": 4,
        "exit_score_against": 4,
        "exit_score_for": 5,
        "game_shape_created": "short_start",
        "innings": 4.0,
        "name": "Luinder Avila",
        "pitch_count": 86
      },
      "story_evidence": {
        "primary_story": "bullpen_overexposed",
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
        ]
      },
      "turning_point": {
        "inning": 4
      },
      "unavailable_relievers": [],
      "workload_concentration": {
        "bullpen_workload_appearances_10d": 0,
        "bullpen_workload_total_10d": 0,
        "concentration_band": "insufficient_data",
        "window_days": 10
      }
    },
    "narrative_context": {
      "confidence": "HIGH",
      "context_type": "completed_game",
      "game_importance": "LOW",
      "game_pk": 824580,
      "generated_at": "2026-06-30T01:41:33.272983",
      "headline_key": "bullpen_overexposed",
      "primary_story": "bullpen_overexposed",
      "secondary_story": "bullpen_kept_team_alive",
      "story_priority": "MEDIUM",
      "story_version": "narrative_context_v1",
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
      "team_id": 118
    },
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": null,
      "bullpen_workload_appearances_10d": 0,
      "bullpen_workload_total_10d": 0,
      "concentration_band": "insufficient_data",
      "context_available": true,
      "early_bullpen_entry_rate": null,
      "top_three_workload_share_10d": null,
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
Bullpen drew the long assignment
```
Body:
```
After their most recent game, Luinder Avila's four-inning start brought the bullpen in by the 5th with a one-run lead.
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
Bullpen drew the long assignment

After their most recent game, Luinder Avila's four-inning start brought the bullpen in by the 5th with a one-run lead.

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
Short start made it a bullpen finish
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
Short start made it a bullpen finish

The club covered heavy innings on a short start.

Evidence:
- Starter: Luinder Avila, 4.0 IP, 86 pitches
```

## Completed-Game Story 12: Team 119 (119)

### Story Metadata

```json
{
  "beat": "protected_game_shape",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_or_unpublishable": false,
  "game_date": "2026-06-28",
  "game_importance": "MEDIUM",
  "game_pk": 823281,
  "opponent_name": "San Diego Padres",
  "publish_reason": "high_priority_narrative",
  "publishable": true,
  "recommended_surface": "multiple",
  "safe_time_context": "AFTER_MOST_RECENT_GAME",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_priority": "HIGH",
  "story_type": "protected_game_shape",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 0,
      "context_available": false,
      "limited_arms_count": 0,
      "monitor_arms_count": 0,
      "optionality_band": "insufficient_data",
      "restricted_arms_count": 0,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [],
      "clean_options_count": 0,
      "context_available": false,
      "core_retention_count": 0,
      "depth_pressure_band": "insufficient_data",
      "inactive_bullpen_arms_count": 0,
      "optionality_band": "insufficient_data",
      "practical_close_game_paths_count": 0,
      "secondary_options": [],
      "secondary_options_count": 0,
      "stability_band": "insufficient_data"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 6,
      "bullpen_entry_score_against": 1,
      "bullpen_entry_score_for": 4,
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
      "generated_at": "2026-06-30T00:54:00.415638",
      "home_away": "away",
      "id": 28,
      "largest_deficit": 0,
      "largest_lead": 3,
      "late_runs_allowed": 0,
      "lead_lost": false,
      "lead_protected": true,
      "lead_when_bullpen_entered": 3,
      "opponent_name": "San Diego Padres",
      "opponent_team_id": 135,
      "runs_allowed_innings_7_to_9": 0,
      "starter_exit_inning": 5,
      "starter_exit_score_against": 1,
      "starter_exit_score_for": 4,
      "starter_ip": 5.0,
      "starter_name": "Emmet Sheehan",
      "starter_pitch_count": 84,
      "starter_player_id": 686218,
      "team_id": 119,
      "turning_inning": null
    },
    "evidence_blocks": {
      "available_relievers": [],
      "bullpen_entry_situation": {
        "inning": 6,
        "lead_when_entered": 3,
        "score_against": 1,
        "score_for": 4
      },
      "bullpen_summary": {
        "available_count": 0,
        "comeback_completed": false,
        "late_runs_allowed": 0,
        "lead_lost": false,
        "lead_protected": true,
        "limited_count": 0,
        "monitor_count": 0,
        "optionality_band": "insufficient_data",
        "unavailable_count": 0
      },
      "clean_options": [],
      "coverage_depth": {
        "bullpen_coverage_ip_7d": 4.0,
        "clean_options_count": 0,
        "depth_pressure_band": "insufficient_data",
        "practical_close_game_paths_count": 0,
        "secondary_options_count": 0
      },
      "evidence_version": "evidence_v1",
      "key_relief_appearances": [],
      "largest_deficit": {
        "runs": 0
      },
      "largest_lead": {
        "runs": 3
      },
      "late_runs": {
        "late_runs_allowed": 0,
        "runs_allowed_innings_7_to_9": 0
      },
      "limited_relievers": [],
      "monitor_relievers": [],
      "starter_summary": {
        "exit_inning": 5,
        "exit_score_against": 1,
        "exit_score_for": 4,
        "game_shape_created": "normal_start",
        "innings": 5.0,
        "name": "Emmet Sheehan",
        "pitch_count": 84
      },
      "story_evidence": {
        "primary_story": "protected_game_shape",
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
        ]
      },
      "turning_point": {},
      "unavailable_relievers": [],
      "workload_concentration": {
        "bullpen_workload_appearances_10d": 4,
        "bullpen_workload_total_10d": 62,
        "concentration_band": "narrow",
        "top_three_workload_share_10d": 82.3,
        "window_days": 10
      }
    },
    "narrative_context": {
      "confidence": "HIGH",
      "context_type": "completed_game",
      "game_importance": "MEDIUM",
      "game_pk": 823281,
      "generated_at": "2026-06-30T01:41:33.383532",
      "headline_key": "bullpen_stabilized",
      "primary_story": "protected_game_shape",
      "secondary_story": null,
      "story_priority": "HIGH",
      "story_version": "narrative_context_v1",
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
      "team_id": 119
    },
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": 4.0,
      "bullpen_workload_appearances_10d": 4,
      "bullpen_workload_total_10d": 62,
      "concentration_band": "narrow",
      "context_available": true,
      "early_bullpen_entry_rate": 0.0,
      "top_three_workload_share_10d": 82.3,
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
Late innings stayed quiet
```
Body:
```
After their most recent game, Emmet Sheehan put a three-run lead in place over five innings, and the relievers carried it home. That keeps the work gathered on a smaller group.
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
```
Exact rendered text:
```
Late innings stayed quiet

After their most recent game, Emmet Sheehan put a three-run lead in place over five innings, and the relievers carried it home. That keeps the work gathered on a smaller group.

Why BaseballOS sees it:
- The starter set the bullpen up to finish the game.
- The bullpen took over with a lead in hand.
- The relievers held the lead.

Evidence:
- Starter: Emmet Sheehan, 5.0 IP, 84 pitches
- Largest lead: 3
- Bullpen entered in the 6th with a 3-run lead
- Late runs allowed: 0
```

### Draft: dashboard

Headline:
```
Late innings held firm
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
Late innings held firm

The club protected a 3-run lead.

Evidence:
- Starter: Emmet Sheehan, 5.0 IP, 84 pitches
```

### Draft: morning_brief

Headline:
```
Bullpen note: Bullpen closed it down
```
Body:
```
After their most recent game, the club turned a three-run lead into a win the bullpen never let slip. That keeps the work gathered on a smaller group.
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
```
Exact rendered text:
```
Bullpen note: Bullpen closed it down

After their most recent game, the club turned a three-run lead into a win the bullpen never let slip. That keeps the work gathered on a smaller group.

Evidence:
- Starter: Emmet Sheehan, 5.0 IP, 84 pitches
- Largest lead: 3
- Bullpen entered in the 6th with a 3-run lead
- Late runs allowed: 0
```

## Completed-Game Story 13: Team 120 (120)

### Story Metadata

```json
{
  "beat": "protected_game_shape",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_or_unpublishable": false,
  "game_date": "2026-06-28",
  "game_importance": "HIGH",
  "game_pk": 824821,
  "opponent_name": "Baltimore Orioles",
  "publish_reason": "high_priority_narrative",
  "publishable": true,
  "recommended_surface": "multiple",
  "safe_time_context": "AFTER_MOST_RECENT_GAME",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_priority": "HIGH",
  "story_type": "protected_game_shape",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 0,
      "context_available": false,
      "limited_arms_count": 0,
      "monitor_arms_count": 0,
      "optionality_band": "insufficient_data",
      "restricted_arms_count": 0,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [],
      "clean_options_count": 0,
      "context_available": false,
      "core_retention_count": 0,
      "depth_pressure_band": "insufficient_data",
      "inactive_bullpen_arms_count": 0,
      "optionality_band": "insufficient_data",
      "practical_close_game_paths_count": 0,
      "secondary_options": [],
      "secondary_options_count": 0,
      "stability_band": "insufficient_data"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 6,
      "bullpen_entry_score_against": 2,
      "bullpen_entry_score_for": 5,
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
      "generated_at": "2026-06-30T00:53:58.724449",
      "home_away": "away",
      "id": 2,
      "largest_deficit": 2,
      "largest_lead": 4,
      "late_runs_allowed": 2,
      "lead_lost": false,
      "lead_protected": true,
      "lead_when_bullpen_entered": 3,
      "opponent_name": "Baltimore Orioles",
      "opponent_team_id": 110,
      "runs_allowed_innings_7_to_9": 2,
      "starter_exit_inning": 5,
      "starter_exit_score_against": 2,
      "starter_exit_score_for": 5,
      "starter_ip": 5.0,
      "starter_name": "Zack Littell",
      "starter_pitch_count": 82,
      "starter_player_id": 641793,
      "team_id": 120,
      "turning_inning": 3
    },
    "evidence_blocks": {
      "available_relievers": [],
      "bullpen_entry_situation": {
        "inning": 6,
        "lead_when_entered": 3,
        "score_against": 2,
        "score_for": 5
      },
      "bullpen_summary": {
        "available_count": 0,
        "comeback_completed": true,
        "late_runs_allowed": 2,
        "lead_lost": false,
        "lead_protected": true,
        "limited_count": 0,
        "monitor_count": 0,
        "optionality_band": "insufficient_data",
        "unavailable_count": 0
      },
      "clean_options": [],
      "coverage_depth": {
        "clean_options_count": 0,
        "depth_pressure_band": "insufficient_data",
        "practical_close_game_paths_count": 0,
        "secondary_options_count": 0
      },
      "evidence_version": "evidence_v1",
      "key_relief_appearances": [],
      "largest_deficit": {
        "runs": 2
      },
      "largest_lead": {
        "runs": 4
      },
      "late_runs": {
        "late_runs_allowed": 2,
        "runs_allowed_innings_7_to_9": 2
      },
      "limited_relievers": [],
      "monitor_relievers": [],
      "starter_summary": {
        "exit_inning": 5,
        "exit_score_against": 2,
        "exit_score_for": 5,
        "game_shape_created": "normal_start",
        "innings": 5.0,
        "name": "Zack Littell",
        "pitch_count": 82
      },
      "story_evidence": {
        "primary_story": "protected_game_shape",
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
        ]
      },
      "turning_point": {
        "inning": 3
      },
      "unavailable_relievers": [],
      "workload_concentration": {
        "bullpen_workload_appearances_10d": 0,
        "bullpen_workload_total_10d": 0,
        "concentration_band": "insufficient_data",
        "window_days": 10
      }
    },
    "narrative_context": {
      "confidence": "HIGH",
      "context_type": "completed_game",
      "game_importance": "HIGH",
      "game_pk": 824821,
      "generated_at": "2026-06-30T01:41:33.459085",
      "headline_key": "protected_game_shape",
      "primary_story": "protected_game_shape",
      "secondary_story": "bullpen_kept_team_alive",
      "story_priority": "HIGH",
      "story_version": "narrative_context_v1",
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
      "team_id": 120
    },
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": null,
      "bullpen_workload_appearances_10d": 0,
      "bullpen_workload_total_10d": 0,
      "concentration_band": "insufficient_data",
      "context_available": true,
      "early_bullpen_entry_rate": null,
      "top_three_workload_share_10d": null,
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
Late lead held
```
Body:
```
After their most recent game, Zack Littell gave the bullpen five innings and a three-run lead to carry home.
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
Late lead held

After their most recent game, Zack Littell gave the bullpen five innings and a three-run lead to carry home.

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
Bullpen finished the lead
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
Bullpen finished the lead

The club protected a 4-run lead.

Evidence:
- Starter: Zack Littell, 5.0 IP, 82 pitches
```

### Draft: morning_brief

Headline:
```
Bullpen note: Lead carried home
```
Body:
```
After their most recent game, the club turned a four-run lead into a win the bullpen never let slip.
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
Bullpen note: Lead carried home

After their most recent game, the club turned a four-run lead into a win the bullpen never let slip.

Evidence:
- Starter: Zack Littell, 5.0 IP, 82 pitches
- Largest lead: 4
- Bullpen entered in the 6th with a 3-run lead
- Turning point: 3rd inning
- Late runs allowed: 2
```

## Completed-Game Story 14: Team 121 (121)

### Story Metadata

```json
{
  "beat": "bullpen_overexposed",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_or_unpublishable": false,
  "game_date": "2026-06-28",
  "game_importance": "MEDIUM",
  "game_pk": 823608,
  "opponent_name": "Philadelphia Phillies",
  "publish_reason": "meets_confidence_threshold",
  "publishable": true,
  "recommended_surface": "team_page",
  "safe_time_context": "AFTER_MOST_RECENT_GAME",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_priority": "MEDIUM",
  "story_type": "bullpen_overexposed",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 0,
      "context_available": false,
      "limited_arms_count": 0,
      "monitor_arms_count": 0,
      "optionality_band": "insufficient_data",
      "restricted_arms_count": 0,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [],
      "clean_options_count": 0,
      "context_available": false,
      "core_retention_count": 0,
      "depth_pressure_band": "insufficient_data",
      "inactive_bullpen_arms_count": 0,
      "optionality_band": "insufficient_data",
      "practical_close_game_paths_count": 0,
      "secondary_options": [],
      "secondary_options_count": 0,
      "stability_band": "insufficient_data"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 2,
      "bullpen_entry_score_against": 0,
      "bullpen_entry_score_for": 0,
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
      "generated_at": "2026-06-30T00:53:59.549019",
      "home_away": "home",
      "id": 13,
      "largest_deficit": 3,
      "largest_lead": 1,
      "late_runs_allowed": 2,
      "lead_lost": null,
      "lead_protected": null,
      "lead_when_bullpen_entered": null,
      "opponent_name": "Philadelphia Phillies",
      "opponent_team_id": 143,
      "runs_allowed_innings_7_to_9": 2,
      "starter_exit_inning": 1,
      "starter_exit_score_against": 0,
      "starter_exit_score_for": 0,
      "starter_ip": 1.0,
      "starter_name": "Cionel Pérez",
      "starter_pitch_count": 9,
      "starter_player_id": 672335,
      "team_id": 121,
      "turning_inning": 7
    },
    "evidence_blocks": {
      "available_relievers": [],
      "bullpen_entry_situation": {
        "inning": 2,
        "score_against": 0,
        "score_for": 0
      },
      "bullpen_summary": {
        "available_count": 0,
        "comeback_completed": false,
        "late_runs_allowed": 2,
        "limited_count": 0,
        "monitor_count": 0,
        "optionality_band": "insufficient_data",
        "unavailable_count": 0
      },
      "clean_options": [],
      "coverage_depth": {
        "clean_options_count": 0,
        "depth_pressure_band": "insufficient_data",
        "practical_close_game_paths_count": 0,
        "secondary_options_count": 0
      },
      "evidence_version": "evidence_v1",
      "key_relief_appearances": [],
      "largest_deficit": {
        "runs": 3
      },
      "largest_lead": {
        "runs": 1
      },
      "late_runs": {
        "late_runs_allowed": 2,
        "runs_allowed_innings_7_to_9": 2
      },
      "limited_relievers": [],
      "monitor_relievers": [],
      "starter_summary": {
        "exit_inning": 1,
        "exit_score_against": 0,
        "exit_score_for": 0,
        "game_shape_created": "opener_bulk_game",
        "innings": 1.0,
        "name": "Cionel Pérez",
        "pitch_count": 9
      },
      "story_evidence": {
        "primary_story": "bullpen_overexposed",
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
        ]
      },
      "turning_point": {
        "inning": 7
      },
      "unavailable_relievers": [],
      "workload_concentration": {
        "bullpen_workload_appearances_10d": 3,
        "bullpen_workload_total_10d": 154,
        "concentration_band": "narrow",
        "top_three_workload_share_10d": 100.0,
        "window_days": 10
      }
    },
    "narrative_context": {
      "confidence": "HIGH",
      "context_type": "completed_game",
      "game_importance": "MEDIUM",
      "game_pk": 823608,
      "generated_at": "2026-06-30T01:41:33.559696",
      "headline_key": "bullpen_overexposed",
      "primary_story": "bullpen_overexposed",
      "secondary_story": "late_pressure_accumulated",
      "story_priority": "MEDIUM",
      "story_version": "narrative_context_v1",
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
      "team_id": 121
    },
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": null,
      "bullpen_workload_appearances_10d": 3,
      "bullpen_workload_total_10d": 154,
      "concentration_band": "narrow",
      "context_available": true,
      "early_bullpen_entry_rate": null,
      "top_three_workload_share_10d": 100.0,
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
Short start stretched the bullpen
```
Body:
```
After their most recent game, Cionel Pérez's one-inning start pushed the rest of the game to the bullpen, including two late runs.
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
Short start stretched the bullpen

After their most recent game, Cionel Pérez's one-inning start pushed the rest of the game to the bullpen, including two late runs.

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
Bullpen had to cover
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
Bullpen had to cover

The club covered heavy innings on a short start.

Evidence:
- Starter: Cionel Pérez, 1.0 IP, 9 pitches
```

## Completed-Game Story 15: Team 133 (133)

### Story Metadata

```json
{
  "beat": "insufficient_context",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_or_unpublishable": true,
  "game_date": "2026-06-28",
  "game_importance": "LOW",
  "game_pk": 824011,
  "opponent_name": "Los Angeles Angels",
  "publish_reason": "insufficient_confidence",
  "publishable": false,
  "recommended_surface": "none",
  "safe_time_context": "CURRENT_STATUS",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_priority": "LOW",
  "story_type": "insufficient_context",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 0,
      "context_available": false,
      "limited_arms_count": 0,
      "monitor_arms_count": 0,
      "optionality_band": "insufficient_data",
      "restricted_arms_count": 0,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [],
      "clean_options_count": 0,
      "context_available": false,
      "core_retention_count": 0,
      "depth_pressure_band": "insufficient_data",
      "inactive_bullpen_arms_count": 0,
      "optionality_band": "insufficient_data",
      "practical_close_game_paths_count": 0,
      "secondary_options": [],
      "secondary_options_count": 0,
      "stability_band": "insufficient_data"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 6,
      "bullpen_entry_score_against": 4,
      "bullpen_entry_score_for": 1,
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
      "generated_at": "2026-06-30T00:54:00.128409",
      "home_away": "away",
      "id": 24,
      "largest_deficit": 4,
      "largest_lead": 0,
      "late_runs_allowed": 0,
      "lead_lost": null,
      "lead_protected": null,
      "lead_when_bullpen_entered": null,
      "opponent_name": "Los Angeles Angels",
      "opponent_team_id": 108,
      "runs_allowed_innings_7_to_9": 0,
      "starter_exit_inning": 5,
      "starter_exit_score_against": 4,
      "starter_exit_score_for": 1,
      "starter_ip": 5.0,
      "starter_name": "Aaron Civale",
      "starter_pitch_count": 90,
      "starter_player_id": 650644,
      "team_id": 133,
      "turning_inning": null
    },
    "evidence_blocks": {
      "available_relievers": [],
      "bullpen_entry_situation": {
        "deficit_when_entered": 3,
        "inning": 6,
        "score_against": 4,
        "score_for": 1
      },
      "bullpen_summary": {
        "available_count": 0,
        "comeback_completed": false,
        "late_runs_allowed": 0,
        "limited_count": 0,
        "monitor_count": 0,
        "optionality_band": "insufficient_data",
        "unavailable_count": 0
      },
      "clean_options": [],
      "coverage_depth": {
        "clean_options_count": 0,
        "depth_pressure_band": "insufficient_data",
        "practical_close_game_paths_count": 0,
        "secondary_options_count": 0
      },
      "evidence_version": "evidence_v1",
      "key_relief_appearances": [],
      "largest_deficit": {
        "runs": 4
      },
      "largest_lead": {
        "runs": 0
      },
      "late_runs": {
        "late_runs_allowed": 0,
        "runs_allowed_innings_7_to_9": 0
      },
      "limited_relievers": [],
      "monitor_relievers": [],
      "starter_summary": {
        "exit_inning": 5,
        "exit_score_against": 4,
        "exit_score_for": 1,
        "game_shape_created": "normal_start",
        "innings": 5.0,
        "name": "Aaron Civale",
        "pitch_count": 90
      },
      "story_evidence": {
        "primary_story": "insufficient_context",
        "supporting_facts": {},
        "supporting_observations": []
      },
      "turning_point": {},
      "unavailable_relievers": [],
      "workload_concentration": {
        "bullpen_workload_appearances_10d": 2,
        "bullpen_workload_total_10d": 18,
        "concentration_band": "narrow",
        "top_three_workload_share_10d": 100.0,
        "window_days": 10
      }
    },
    "narrative_context": {
      "confidence": "HIGH",
      "context_type": "completed_game",
      "game_importance": "LOW",
      "game_pk": 824011,
      "generated_at": "2026-06-30T01:41:33.750444",
      "headline_key": "insufficient_context",
      "primary_story": "insufficient_context",
      "secondary_story": null,
      "story_priority": "LOW",
      "story_version": "narrative_context_v1",
      "summary_key": "insufficient_context",
      "supporting_facts": {},
      "supporting_observations": [],
      "team_id": 133
    },
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": null,
      "bullpen_workload_appearances_10d": 2,
      "bullpen_workload_total_10d": 18,
      "concentration_band": "narrow",
      "context_available": true,
      "early_bullpen_entry_rate": 0.0,
      "top_three_workload_share_10d": 100.0,
      "window_days": 10
    }
  },
  "team_id": 133,
  "writer_targets": []
}
```

No draft rendered.

## Completed-Game Story 16: Team 134 (134)

### Story Metadata

```json
{
  "beat": "protected_game_shape",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_or_unpublishable": false,
  "game_date": "2026-06-28",
  "game_importance": "HIGH",
  "game_pk": 823362,
  "opponent_name": "Cincinnati Reds",
  "publish_reason": "high_priority_narrative",
  "publishable": true,
  "recommended_surface": "multiple",
  "safe_time_context": "AFTER_MOST_RECENT_GAME",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_priority": "HIGH",
  "story_type": "protected_game_shape",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 0,
      "context_available": false,
      "limited_arms_count": 0,
      "monitor_arms_count": 0,
      "optionality_band": "insufficient_data",
      "restricted_arms_count": 0,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [],
      "clean_options_count": 0,
      "context_available": false,
      "core_retention_count": 0,
      "depth_pressure_band": "insufficient_data",
      "inactive_bullpen_arms_count": 0,
      "optionality_band": "insufficient_data",
      "practical_close_game_paths_count": 0,
      "secondary_options": [],
      "secondary_options_count": 0,
      "stability_band": "insufficient_data"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 7,
      "bullpen_entry_score_against": 4,
      "bullpen_entry_score_for": 5,
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
      "generated_at": "2026-06-30T00:53:58.832178",
      "home_away": "home",
      "id": 3,
      "largest_deficit": 0,
      "largest_lead": 5,
      "late_runs_allowed": 0,
      "lead_lost": false,
      "lead_protected": true,
      "lead_when_bullpen_entered": 1,
      "opponent_name": "Cincinnati Reds",
      "opponent_team_id": 113,
      "runs_allowed_innings_7_to_9": 0,
      "starter_exit_inning": 6,
      "starter_exit_score_against": 4,
      "starter_exit_score_for": 5,
      "starter_ip": 6.0,
      "starter_name": "Mitch Keller",
      "starter_pitch_count": 79,
      "starter_player_id": 656605,
      "team_id": 134,
      "turning_inning": null
    },
    "evidence_blocks": {
      "available_relievers": [],
      "bullpen_entry_situation": {
        "inning": 7,
        "lead_when_entered": 1,
        "score_against": 4,
        "score_for": 5
      },
      "bullpen_summary": {
        "available_count": 0,
        "comeback_completed": false,
        "late_runs_allowed": 0,
        "lead_lost": false,
        "lead_protected": true,
        "limited_count": 0,
        "monitor_count": 0,
        "optionality_band": "insufficient_data",
        "unavailable_count": 0
      },
      "clean_options": [],
      "coverage_depth": {
        "clean_options_count": 0,
        "depth_pressure_band": "insufficient_data",
        "practical_close_game_paths_count": 0,
        "secondary_options_count": 0
      },
      "evidence_version": "evidence_v1",
      "key_relief_appearances": [],
      "largest_deficit": {
        "runs": 0
      },
      "largest_lead": {
        "runs": 5
      },
      "late_runs": {
        "late_runs_allowed": 0,
        "runs_allowed_innings_7_to_9": 0
      },
      "limited_relievers": [],
      "monitor_relievers": [],
      "starter_summary": {
        "exit_inning": 6,
        "exit_score_against": 4,
        "exit_score_for": 5,
        "game_shape_created": "normal_start",
        "innings": 6.0,
        "name": "Mitch Keller",
        "pitch_count": 79
      },
      "story_evidence": {
        "primary_story": "protected_game_shape",
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
        ]
      },
      "turning_point": {},
      "unavailable_relievers": [],
      "workload_concentration": {
        "bullpen_workload_appearances_10d": 0,
        "bullpen_workload_total_10d": 0,
        "concentration_band": "insufficient_data",
        "window_days": 10
      }
    },
    "narrative_context": {
      "confidence": "HIGH",
      "context_type": "completed_game",
      "game_importance": "HIGH",
      "game_pk": 823362,
      "generated_at": "2026-06-30T01:41:33.863242",
      "headline_key": "bullpen_stabilized",
      "primary_story": "protected_game_shape",
      "secondary_story": "starter_covered_bullpen",
      "story_priority": "HIGH",
      "story_version": "narrative_context_v1",
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
      "team_id": 134
    },
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": null,
      "bullpen_workload_appearances_10d": 0,
      "bullpen_workload_total_10d": 0,
      "concentration_band": "insufficient_data",
      "context_available": true,
      "early_bullpen_entry_rate": null,
      "top_three_workload_share_10d": null,
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
Late innings stayed quiet
```
Body:
```
After their most recent game, Mitch Keller gave the bullpen a five-run lead after six innings, and the late innings held.
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
```
Exact rendered text:
```
Late innings stayed quiet

After their most recent game, Mitch Keller gave the bullpen a five-run lead after six innings, and the late innings held.

Why BaseballOS sees it:
- The starter went deep and set the bullpen up to finish the game.
- The bullpen took over with a lead in hand.
- The relievers held the lead.

Evidence:
- Starter: Mitch Keller, 6.0 IP, 79 pitches
- Largest lead: 5
- Bullpen entered in the 7th with a 1-run lead
- Late runs allowed: 0
```

### Draft: dashboard

Headline:
```
Late innings held firm
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
Late innings held firm

The club protected a 5-run lead.

Evidence:
- Starter: Mitch Keller, 6.0 IP, 79 pitches
```

### Draft: morning_brief

Headline:
```
Bullpen note: Bullpen closed it down
```
Body:
```
After their most recent game, the club turned a five-run lead into a win the bullpen never let slip.
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
```
Exact rendered text:
```
Bullpen note: Bullpen closed it down

After their most recent game, the club turned a five-run lead into a win the bullpen never let slip.

Evidence:
- Starter: Mitch Keller, 6.0 IP, 79 pitches
- Largest lead: 5
- Bullpen entered in the 7th with a 1-run lead
- Late runs allowed: 0
```

## Completed-Game Story 17: Team 135 (135)

### Story Metadata

```json
{
  "beat": "bullpen_overexposed",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_or_unpublishable": false,
  "game_date": "2026-06-28",
  "game_importance": "LOW",
  "game_pk": 823281,
  "opponent_name": "Los Angeles Dodgers",
  "publish_reason": "meets_confidence_threshold",
  "publishable": true,
  "recommended_surface": "dashboard",
  "safe_time_context": "AFTER_MOST_RECENT_GAME",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_priority": "MEDIUM",
  "story_type": "bullpen_overexposed",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 0,
      "context_available": false,
      "limited_arms_count": 0,
      "monitor_arms_count": 0,
      "optionality_band": "insufficient_data",
      "restricted_arms_count": 0,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [],
      "clean_options_count": 0,
      "context_available": false,
      "core_retention_count": 0,
      "depth_pressure_band": "insufficient_data",
      "inactive_bullpen_arms_count": 0,
      "optionality_band": "insufficient_data",
      "practical_close_game_paths_count": 0,
      "secondary_options": [],
      "secondary_options_count": 0,
      "stability_band": "insufficient_data"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 5,
      "bullpen_entry_score_against": 4,
      "bullpen_entry_score_for": 1,
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
      "generated_at": "2026-06-30T00:54:00.415236",
      "home_away": "home",
      "id": 27,
      "largest_deficit": 3,
      "largest_lead": 0,
      "late_runs_allowed": 0,
      "lead_lost": null,
      "lead_protected": null,
      "lead_when_bullpen_entered": null,
      "opponent_name": "Los Angeles Dodgers",
      "opponent_team_id": 119,
      "runs_allowed_innings_7_to_9": 0,
      "starter_exit_inning": 5,
      "starter_exit_score_against": 4,
      "starter_exit_score_for": 1,
      "starter_ip": 4.333333333333333,
      "starter_name": "Michael King",
      "starter_pitch_count": 90,
      "starter_player_id": 650633,
      "team_id": 135,
      "turning_inning": null
    },
    "evidence_blocks": {
      "available_relievers": [],
      "bullpen_entry_situation": {
        "deficit_when_entered": 3,
        "inning": 5,
        "score_against": 4,
        "score_for": 1
      },
      "bullpen_summary": {
        "available_count": 0,
        "comeback_completed": false,
        "late_runs_allowed": 0,
        "limited_count": 0,
        "monitor_count": 0,
        "optionality_band": "insufficient_data",
        "unavailable_count": 0
      },
      "clean_options": [],
      "coverage_depth": {
        "clean_options_count": 0,
        "depth_pressure_band": "insufficient_data",
        "practical_close_game_paths_count": 0,
        "secondary_options_count": 0
      },
      "evidence_version": "evidence_v1",
      "key_relief_appearances": [],
      "largest_deficit": {
        "runs": 3
      },
      "largest_lead": {
        "runs": 0
      },
      "late_runs": {
        "late_runs_allowed": 0,
        "runs_allowed_innings_7_to_9": 0
      },
      "limited_relievers": [],
      "monitor_relievers": [],
      "starter_summary": {
        "exit_inning": 5,
        "exit_score_against": 4,
        "exit_score_for": 1,
        "game_shape_created": "short_start",
        "innings": 4.333333333333333,
        "name": "Michael King",
        "pitch_count": 90
      },
      "story_evidence": {
        "primary_story": "bullpen_overexposed",
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
        ]
      },
      "turning_point": {},
      "unavailable_relievers": [],
      "workload_concentration": {
        "bullpen_workload_appearances_10d": 0,
        "bullpen_workload_total_10d": 0,
        "concentration_band": "insufficient_data",
        "window_days": 10
      }
    },
    "narrative_context": {
      "confidence": "HIGH",
      "context_type": "completed_game",
      "game_importance": "LOW",
      "game_pk": 823281,
      "generated_at": "2026-06-30T01:41:33.978544",
      "headline_key": "bullpen_overexposed",
      "primary_story": "bullpen_overexposed",
      "secondary_story": null,
      "story_priority": "MEDIUM",
      "story_version": "narrative_context_v1",
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
      "team_id": 135
    },
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": null,
      "bullpen_workload_appearances_10d": 0,
      "bullpen_workload_total_10d": 0,
      "concentration_band": "insufficient_data",
      "context_available": true,
      "early_bullpen_entry_rate": null,
      "top_three_workload_share_10d": null,
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
Body:
```
After their most recent game, Michael King's 4.1-inning start brought the bullpen in by the 5th already trailing by three.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Michael King, 4.1 IP, 90 pitches
- Largest deficit: 3
- Bullpen entered in the 5th trailing by 3
- Late runs allowed: 0
```
Exact rendered text:
```
Bullpen stretched thin

After their most recent game, Michael King's 4.1-inning start brought the bullpen in by the 5th already trailing by three.

Evidence:
- Starter: Michael King, 4.1 IP, 90 pitches
- Largest deficit: 3
- Bullpen entered in the 5th trailing by 3
- Late runs allowed: 0
```

### Draft: dashboard

Headline:
```
Short start stretched the bullpen
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
- Starter: Michael King, 4.1 IP, 90 pitches
```
Exact rendered text:
```
Short start stretched the bullpen

The club covered heavy innings on a short start.

Evidence:
- Starter: Michael King, 4.1 IP, 90 pitches
```

## Completed-Game Story 18: Team 136 (136)

### Story Metadata

```json
{
  "beat": "lost_game_shape",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_or_unpublishable": false,
  "game_date": "2026-06-28",
  "game_importance": "MEDIUM",
  "game_pk": 824422,
  "opponent_name": "Cleveland Guardians",
  "publish_reason": "critical_narrative",
  "publishable": true,
  "recommended_surface": "multiple",
  "safe_time_context": "AFTER_MOST_RECENT_GAME",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_priority": "CRITICAL",
  "story_type": "lost_game_shape",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 0,
      "context_available": false,
      "limited_arms_count": 0,
      "monitor_arms_count": 0,
      "optionality_band": "insufficient_data",
      "restricted_arms_count": 0,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [],
      "clean_options_count": 0,
      "context_available": false,
      "core_retention_count": 0,
      "depth_pressure_band": "insufficient_data",
      "inactive_bullpen_arms_count": 0,
      "optionality_band": "insufficient_data",
      "practical_close_game_paths_count": 0,
      "secondary_options": [],
      "secondary_options_count": 0,
      "stability_band": "insufficient_data"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 6,
      "bullpen_entry_score_against": 1,
      "bullpen_entry_score_for": 4,
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
      "generated_at": "2026-06-30T00:53:59.194103",
      "home_away": "away",
      "id": 10,
      "largest_deficit": 2,
      "largest_lead": 3,
      "late_runs_allowed": 5,
      "lead_lost": true,
      "lead_protected": false,
      "lead_when_bullpen_entered": 3,
      "opponent_name": "Cleveland Guardians",
      "opponent_team_id": 114,
      "runs_allowed_innings_7_to_9": 5,
      "starter_exit_inning": 6,
      "starter_exit_score_against": 1,
      "starter_exit_score_for": 4,
      "starter_ip": 5.666666666666667,
      "starter_name": "Emerson Hancock",
      "starter_pitch_count": 98,
      "starter_player_id": 676106,
      "team_id": 136,
      "turning_inning": 8
    },
    "evidence_blocks": {
      "available_relievers": [],
      "bullpen_entry_situation": {
        "inning": 6,
        "lead_when_entered": 3,
        "score_against": 1,
        "score_for": 4
      },
      "bullpen_summary": {
        "available_count": 0,
        "comeback_completed": false,
        "late_runs_allowed": 5,
        "lead_lost": true,
        "lead_protected": false,
        "limited_count": 0,
        "monitor_count": 0,
        "optionality_band": "insufficient_data",
        "unavailable_count": 0
      },
      "clean_options": [],
      "coverage_depth": {
        "clean_options_count": 0,
        "depth_pressure_band": "insufficient_data",
        "practical_close_game_paths_count": 0,
        "secondary_options_count": 0
      },
      "evidence_version": "evidence_v1",
      "key_relief_appearances": [],
      "largest_deficit": {
        "runs": 2
      },
      "largest_lead": {
        "runs": 3
      },
      "late_runs": {
        "late_runs_allowed": 5,
        "runs_allowed_innings_7_to_9": 5
      },
      "limited_relievers": [],
      "monitor_relievers": [],
      "starter_summary": {
        "exit_inning": 6,
        "exit_score_against": 1,
        "exit_score_for": 4,
        "game_shape_created": "normal_start",
        "innings": 5.666666666666667,
        "name": "Emerson Hancock",
        "pitch_count": 98
      },
      "story_evidence": {
        "primary_story": "lost_game_shape",
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
        ]
      },
      "turning_point": {
        "inning": 8
      },
      "unavailable_relievers": [],
      "workload_concentration": {
        "bullpen_workload_appearances_10d": 0,
        "bullpen_workload_total_10d": 0,
        "concentration_band": "insufficient_data",
        "window_days": 10
      }
    },
    "narrative_context": {
      "confidence": "HIGH",
      "context_type": "completed_game",
      "game_importance": "MEDIUM",
      "game_pk": 824422,
      "generated_at": "2026-06-30T01:41:34.114222",
      "headline_key": "lost_game_shape",
      "primary_story": "lost_game_shape",
      "secondary_story": "late_pressure_accumulated",
      "story_priority": "CRITICAL",
      "story_version": "narrative_context_v1",
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
      "team_id": 136
    },
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": null,
      "bullpen_workload_appearances_10d": 0,
      "bullpen_workload_total_10d": 0,
      "concentration_band": "insufficient_data",
      "context_available": true,
      "early_bullpen_entry_rate": null,
      "top_three_workload_share_10d": null,
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
Lead disappeared late
```
Body:
```
After their most recent game, Emerson Hancock's 5.2 strong innings staked a three-run lead heading to the late innings. It didn't last. Five late runs turned the game.
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
- Starter: Emerson Hancock, 5.2 IP, 98 pitches
- Largest lead: 3
- Bullpen entered in the 6th with a 3-run lead
- Turning point: 8th inning
- Late runs allowed: 5
```
Exact rendered text:
```
Lead disappeared late

After their most recent game, Emerson Hancock's 5.2 strong innings staked a three-run lead heading to the late innings. It didn't last. Five late runs turned the game.

Why BaseballOS sees it:
- The starter set the bullpen up to finish the game.
- The bullpen took over with a lead in hand.
- The relievers could not hold the lead.
- The damage came after the starter exited and piled up late.

Evidence:
- Starter: Emerson Hancock, 5.2 IP, 98 pitches
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
- Starter: Emerson Hancock, 5.2 IP, 98 pitches
```
Exact rendered text:
```
Lead surrendered late

The club blew a 3-run lead late.

Evidence:
- Starter: Emerson Hancock, 5.2 IP, 98 pitches
```

### Draft: morning_brief

Headline:
```
Bullpen note: Late lead slipped away
```
Body:
```
After their most recent game, the club carried a three-run lead into the late innings and let it get away on five late runs.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Emerson Hancock, 5.2 IP, 98 pitches
- Largest lead: 3
- Bullpen entered in the 6th with a 3-run lead
- Turning point: 8th inning
- Late runs allowed: 5
```
Exact rendered text:
```
Bullpen note: Late lead slipped away

After their most recent game, the club carried a three-run lead into the late innings and let it get away on five late runs.

Evidence:
- Starter: Emerson Hancock, 5.2 IP, 98 pitches
- Largest lead: 3
- Bullpen entered in the 6th with a 3-run lead
- Turning point: 8th inning
- Late runs allowed: 5
```

## Completed-Game Story 19: Team 137 (137)

### Story Metadata

```json
{
  "beat": "protected_game_shape",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_or_unpublishable": false,
  "game_date": "2026-06-28",
  "game_importance": "MEDIUM",
  "game_pk": 823204,
  "opponent_name": "Atlanta Braves",
  "publish_reason": "high_priority_narrative",
  "publishable": true,
  "recommended_surface": "multiple",
  "safe_time_context": "AFTER_MOST_RECENT_GAME",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_priority": "HIGH",
  "story_type": "protected_game_shape",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 0,
      "context_available": false,
      "limited_arms_count": 0,
      "monitor_arms_count": 0,
      "optionality_band": "insufficient_data",
      "restricted_arms_count": 0,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [],
      "clean_options_count": 0,
      "context_available": false,
      "core_retention_count": 0,
      "depth_pressure_band": "insufficient_data",
      "inactive_bullpen_arms_count": 0,
      "optionality_band": "insufficient_data",
      "practical_close_game_paths_count": 0,
      "secondary_options": [],
      "secondary_options_count": 0,
      "stability_band": "insufficient_data"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 9,
      "bullpen_entry_score_against": 1,
      "bullpen_entry_score_for": 3,
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
      "generated_at": "2026-06-30T00:54:00.233549",
      "home_away": "home",
      "id": 25,
      "largest_deficit": 0,
      "largest_lead": 3,
      "late_runs_allowed": 2,
      "lead_lost": false,
      "lead_protected": true,
      "lead_when_bullpen_entered": 2,
      "opponent_name": "Atlanta Braves",
      "opponent_team_id": 144,
      "runs_allowed_innings_7_to_9": 2,
      "starter_exit_inning": 8,
      "starter_exit_score_against": 1,
      "starter_exit_score_for": 3,
      "starter_ip": 8.0,
      "starter_name": "Robbie Ray",
      "starter_pitch_count": 95,
      "starter_player_id": 592662,
      "team_id": 137,
      "turning_inning": null
    },
    "evidence_blocks": {
      "available_relievers": [],
      "bullpen_entry_situation": {
        "inning": 9,
        "lead_when_entered": 2,
        "score_against": 1,
        "score_for": 3
      },
      "bullpen_summary": {
        "available_count": 0,
        "comeback_completed": false,
        "late_runs_allowed": 2,
        "lead_lost": false,
        "lead_protected": true,
        "limited_count": 0,
        "monitor_count": 0,
        "optionality_band": "insufficient_data",
        "unavailable_count": 0
      },
      "clean_options": [],
      "coverage_depth": {
        "clean_options_count": 0,
        "depth_pressure_band": "insufficient_data",
        "practical_close_game_paths_count": 0,
        "secondary_options_count": 0
      },
      "evidence_version": "evidence_v1",
      "key_relief_appearances": [],
      "largest_deficit": {
        "runs": 0
      },
      "largest_lead": {
        "runs": 3
      },
      "late_runs": {
        "late_runs_allowed": 2,
        "runs_allowed_innings_7_to_9": 2
      },
      "limited_relievers": [],
      "monitor_relievers": [],
      "starter_summary": {
        "exit_inning": 8,
        "exit_score_against": 1,
        "exit_score_for": 3,
        "game_shape_created": "normal_start",
        "innings": 8.0,
        "name": "Robbie Ray",
        "pitch_count": 95
      },
      "story_evidence": {
        "primary_story": "protected_game_shape",
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
        ]
      },
      "turning_point": {},
      "unavailable_relievers": [],
      "workload_concentration": {
        "bullpen_workload_appearances_10d": 0,
        "bullpen_workload_total_10d": 0,
        "concentration_band": "insufficient_data",
        "window_days": 10
      }
    },
    "narrative_context": {
      "confidence": "HIGH",
      "context_type": "completed_game",
      "game_importance": "MEDIUM",
      "game_pk": 823204,
      "generated_at": "2026-06-30T01:41:34.213591",
      "headline_key": "protected_game_shape",
      "primary_story": "protected_game_shape",
      "secondary_story": "late_pressure_accumulated",
      "story_priority": "HIGH",
      "story_version": "narrative_context_v1",
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
      "team_id": 137
    },
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": null,
      "bullpen_workload_appearances_10d": 0,
      "bullpen_workload_total_10d": 0,
      "concentration_band": "insufficient_data",
      "context_available": true,
      "early_bullpen_entry_rate": null,
      "top_three_workload_share_10d": null,
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
Lead carried home
```
Body:
```
After their most recent game, Robbie Ray put a three-run lead in place over eight innings, and the relievers carried it home.
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
```
Exact rendered text:
```
Lead carried home

After their most recent game, Robbie Ray put a three-run lead in place over eight innings, and the relievers carried it home.

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
```

### Draft: dashboard

Headline:
```
Bullpen held the finish
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
Bullpen held the finish

The club protected a 3-run lead.

Evidence:
- Starter: Robbie Ray, 8.0 IP, 95 pitches
```

### Draft: morning_brief

Headline:
```
Bullpen note: Late lead closed out
```
Body:
```
After their most recent game, the club turned a three-run lead into a win the bullpen never let slip.
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
```
Exact rendered text:
```
Bullpen note: Late lead closed out

After their most recent game, the club turned a three-run lead into a win the bullpen never let slip.

Evidence:
- Starter: Robbie Ray, 8.0 IP, 95 pitches
- Largest lead: 3
- Bullpen entered in the 9th with a 2-run lead
- Late runs allowed: 2
```

## Completed-Game Story 20: Team 138 (138)

### Story Metadata

```json
{
  "beat": "protected_game_shape",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_or_unpublishable": false,
  "game_date": "2026-06-28",
  "game_importance": "MEDIUM",
  "game_pk": 823037,
  "opponent_name": "Miami Marlins",
  "publish_reason": "high_priority_narrative",
  "publishable": true,
  "recommended_surface": "multiple",
  "safe_time_context": "AFTER_MOST_RECENT_GAME",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_priority": "HIGH",
  "story_type": "protected_game_shape",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 0,
      "context_available": false,
      "limited_arms_count": 0,
      "monitor_arms_count": 0,
      "optionality_band": "insufficient_data",
      "restricted_arms_count": 0,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [],
      "clean_options_count": 0,
      "context_available": false,
      "core_retention_count": 0,
      "depth_pressure_band": "insufficient_data",
      "inactive_bullpen_arms_count": 0,
      "optionality_band": "insufficient_data",
      "practical_close_game_paths_count": 0,
      "secondary_options": [],
      "secondary_options_count": 0,
      "stability_band": "insufficient_data"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 6,
      "bullpen_entry_score_against": 1,
      "bullpen_entry_score_for": 2,
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
      "generated_at": "2026-06-30T00:54:00.029242",
      "home_away": "home",
      "id": 21,
      "largest_deficit": 0,
      "largest_lead": 2,
      "late_runs_allowed": 0,
      "lead_lost": false,
      "lead_protected": true,
      "lead_when_bullpen_entered": 1,
      "opponent_name": "Miami Marlins",
      "opponent_team_id": 146,
      "runs_allowed_innings_7_to_9": 0,
      "starter_exit_inning": 5,
      "starter_exit_score_against": 1,
      "starter_exit_score_for": 2,
      "starter_ip": 5.0,
      "starter_name": "Kyle Leahy",
      "starter_pitch_count": 87,
      "starter_player_id": 681517,
      "team_id": 138,
      "turning_inning": null
    },
    "evidence_blocks": {
      "available_relievers": [],
      "bullpen_entry_situation": {
        "inning": 6,
        "lead_when_entered": 1,
        "score_against": 1,
        "score_for": 2
      },
      "bullpen_summary": {
        "available_count": 0,
        "comeback_completed": false,
        "late_runs_allowed": 0,
        "lead_lost": false,
        "lead_protected": true,
        "limited_count": 0,
        "monitor_count": 0,
        "optionality_band": "insufficient_data",
        "unavailable_count": 0
      },
      "clean_options": [],
      "coverage_depth": {
        "bullpen_coverage_ip_7d": 4.0,
        "clean_options_count": 0,
        "depth_pressure_band": "insufficient_data",
        "practical_close_game_paths_count": 0,
        "secondary_options_count": 0
      },
      "evidence_version": "evidence_v1",
      "key_relief_appearances": [],
      "largest_deficit": {
        "runs": 0
      },
      "largest_lead": {
        "runs": 2
      },
      "late_runs": {
        "late_runs_allowed": 0,
        "runs_allowed_innings_7_to_9": 0
      },
      "limited_relievers": [],
      "monitor_relievers": [],
      "starter_summary": {
        "exit_inning": 5,
        "exit_score_against": 1,
        "exit_score_for": 2,
        "game_shape_created": "normal_start",
        "innings": 5.0,
        "name": "Kyle Leahy",
        "pitch_count": 87
      },
      "story_evidence": {
        "primary_story": "protected_game_shape",
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
        ]
      },
      "turning_point": {},
      "unavailable_relievers": [],
      "workload_concentration": {
        "bullpen_workload_appearances_10d": 4,
        "bullpen_workload_total_10d": 54,
        "concentration_band": "narrow",
        "top_three_workload_share_10d": 81.5,
        "window_days": 10
      }
    },
    "narrative_context": {
      "confidence": "HIGH",
      "context_type": "completed_game",
      "game_importance": "MEDIUM",
      "game_pk": 823037,
      "generated_at": "2026-06-30T01:41:34.337372",
      "headline_key": "bullpen_stabilized",
      "primary_story": "protected_game_shape",
      "secondary_story": null,
      "story_priority": "HIGH",
      "story_version": "narrative_context_v1",
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
      "team_id": 138
    },
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": 4.0,
      "bullpen_workload_appearances_10d": 4,
      "bullpen_workload_total_10d": 54,
      "concentration_band": "narrow",
      "context_available": true,
      "early_bullpen_entry_rate": 0.0,
      "top_three_workload_share_10d": 81.5,
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
Quiet finish from the pen
```
Body:
```
After their most recent game, Kyle Leahy handed off after five innings with a two-run lead, and the bullpen finished it. That keeps the workload from spreading across the full bullpen.
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
```
Exact rendered text:
```
Quiet finish from the pen

After their most recent game, Kyle Leahy handed off after five innings with a two-run lead, and the bullpen finished it. That keeps the workload from spreading across the full bullpen.

Why BaseballOS sees it:
- The starter set the bullpen up to finish the game.
- The bullpen took over with a lead in hand.
- The relievers held the lead.

Evidence:
- Starter: Kyle Leahy, 5.0 IP, 87 pitches
- Largest lead: 2
- Bullpen entered in the 6th with a 1-run lead
- Late runs allowed: 0
```

### Draft: dashboard

Headline:
```
Bullpen slammed the door
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
Bullpen note: Lead finished cleanly
```
Body:
```
After their most recent game, the club turned a two-run lead into a win the bullpen never let slip. That leaves the meaningful innings concentrated around the same arms.
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
```
Exact rendered text:
```
Bullpen note: Lead finished cleanly

After their most recent game, the club turned a two-run lead into a win the bullpen never let slip. That leaves the meaningful innings concentrated around the same arms.

Evidence:
- Starter: Kyle Leahy, 5.0 IP, 87 pitches
- Largest lead: 2
- Bullpen entered in the 6th with a 1-run lead
- Late runs allowed: 0
```

## Completed-Game Story 21: Team 139 (139)

### Story Metadata

```json
{
  "beat": "protected_game_shape",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_or_unpublishable": false,
  "game_date": "2026-06-28",
  "game_importance": "HIGH",
  "game_pk": 822959,
  "opponent_name": "Arizona Diamondbacks",
  "publish_reason": "high_priority_narrative",
  "publishable": true,
  "recommended_surface": "multiple",
  "safe_time_context": "AFTER_MOST_RECENT_GAME",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_priority": "HIGH",
  "story_type": "protected_game_shape",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 0,
      "context_available": false,
      "limited_arms_count": 0,
      "monitor_arms_count": 0,
      "optionality_band": "insufficient_data",
      "restricted_arms_count": 0,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [],
      "clean_options_count": 0,
      "context_available": false,
      "core_retention_count": 0,
      "depth_pressure_band": "insufficient_data",
      "inactive_bullpen_arms_count": 0,
      "optionality_band": "insufficient_data",
      "practical_close_game_paths_count": 0,
      "secondary_options": [],
      "secondary_options_count": 0,
      "stability_band": "insufficient_data"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 7,
      "bullpen_entry_score_against": 0,
      "bullpen_entry_score_for": 5,
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
      "generated_at": "2026-06-30T00:53:59.350042",
      "home_away": "home",
      "id": 11,
      "largest_deficit": 0,
      "largest_lead": 5,
      "late_runs_allowed": 1,
      "lead_lost": false,
      "lead_protected": true,
      "lead_when_bullpen_entered": 5,
      "opponent_name": "Arizona Diamondbacks",
      "opponent_team_id": 109,
      "runs_allowed_innings_7_to_9": 1,
      "starter_exit_inning": 6,
      "starter_exit_score_against": 0,
      "starter_exit_score_for": 4,
      "starter_ip": 6.0,
      "starter_name": "Drew Rasmussen",
      "starter_pitch_count": 99,
      "starter_player_id": 656876,
      "team_id": 139,
      "turning_inning": null
    },
    "evidence_blocks": {
      "available_relievers": [],
      "bullpen_entry_situation": {
        "inning": 7,
        "lead_when_entered": 5,
        "score_against": 0,
        "score_for": 5
      },
      "bullpen_summary": {
        "available_count": 0,
        "comeback_completed": false,
        "late_runs_allowed": 1,
        "lead_lost": false,
        "lead_protected": true,
        "limited_count": 0,
        "monitor_count": 0,
        "optionality_band": "insufficient_data",
        "unavailable_count": 0
      },
      "clean_options": [],
      "coverage_depth": {
        "clean_options_count": 0,
        "depth_pressure_band": "insufficient_data",
        "practical_close_game_paths_count": 0,
        "secondary_options_count": 0
      },
      "evidence_version": "evidence_v1",
      "key_relief_appearances": [],
      "largest_deficit": {
        "runs": 0
      },
      "largest_lead": {
        "runs": 5
      },
      "late_runs": {
        "late_runs_allowed": 1,
        "runs_allowed_innings_7_to_9": 1
      },
      "limited_relievers": [],
      "monitor_relievers": [],
      "starter_summary": {
        "exit_inning": 6,
        "exit_score_against": 0,
        "exit_score_for": 4,
        "game_shape_created": "normal_start",
        "innings": 6.0,
        "name": "Drew Rasmussen",
        "pitch_count": 99
      },
      "story_evidence": {
        "primary_story": "protected_game_shape",
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
        ]
      },
      "turning_point": {},
      "unavailable_relievers": [],
      "workload_concentration": {
        "bullpen_workload_appearances_10d": 0,
        "bullpen_workload_total_10d": 0,
        "concentration_band": "insufficient_data",
        "window_days": 10
      }
    },
    "narrative_context": {
      "confidence": "HIGH",
      "context_type": "completed_game",
      "game_importance": "HIGH",
      "game_pk": 822959,
      "generated_at": "2026-06-30T01:41:34.417109",
      "headline_key": "protected_game_shape",
      "primary_story": "protected_game_shape",
      "secondary_story": null,
      "story_priority": "HIGH",
      "story_version": "narrative_context_v1",
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
      "team_id": 139
    },
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": null,
      "bullpen_workload_appearances_10d": 0,
      "bullpen_workload_total_10d": 0,
      "concentration_band": "insufficient_data",
      "context_available": true,
      "early_bullpen_entry_rate": null,
      "top_three_workload_share_10d": null,
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
Body:
```
After their most recent game, Drew Rasmussen left the bullpen a five-run lead in the 7th, and the relievers protected it.
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
```
Exact rendered text:
```
Lead protected

After their most recent game, Drew Rasmussen left the bullpen a five-run lead in the 7th, and the relievers protected it.

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
```

### Draft: dashboard

Headline:
```
Late lead held
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
Late lead held

The club protected a 5-run lead.

Evidence:
- Starter: Drew Rasmussen, 6.0 IP, 99 pitches
```

### Draft: morning_brief

Headline:
```
Bullpen note: Bullpen finished the lead
```
Body:
```
After their most recent game, the club turned a five-run lead into a win the bullpen never let slip.
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
```
Exact rendered text:
```
Bullpen note: Bullpen finished the lead

After their most recent game, the club turned a five-run lead into a win the bullpen never let slip.

Evidence:
- Starter: Drew Rasmussen, 6.0 IP, 99 pitches
- Largest lead: 5
- Bullpen entered in the 7th with a 5-run lead
- Late runs allowed: 1
```

## Completed-Game Story 22: Team 140 (140)

### Story Metadata

```json
{
  "beat": "protected_game_shape",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_or_unpublishable": false,
  "game_date": "2026-06-28",
  "game_importance": "MEDIUM",
  "game_pk": 822795,
  "opponent_name": "Toronto Blue Jays",
  "publish_reason": "high_priority_narrative",
  "publishable": true,
  "recommended_surface": "multiple",
  "safe_time_context": "AFTER_MOST_RECENT_GAME",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_priority": "HIGH",
  "story_type": "protected_game_shape",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 0,
      "context_available": false,
      "limited_arms_count": 0,
      "monitor_arms_count": 0,
      "optionality_band": "insufficient_data",
      "restricted_arms_count": 0,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [],
      "clean_options_count": 0,
      "context_available": false,
      "core_retention_count": 0,
      "depth_pressure_band": "insufficient_data",
      "inactive_bullpen_arms_count": 0,
      "optionality_band": "insufficient_data",
      "practical_close_game_paths_count": 0,
      "secondary_options": [],
      "secondary_options_count": 0,
      "stability_band": "insufficient_data"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 7,
      "bullpen_entry_score_against": 0,
      "bullpen_entry_score_for": 2,
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
      "generated_at": "2026-06-30T00:53:58.989784",
      "home_away": "away",
      "id": 6,
      "largest_deficit": 0,
      "largest_lead": 2,
      "late_runs_allowed": 2,
      "lead_lost": false,
      "lead_protected": true,
      "lead_when_bullpen_entered": 2,
      "opponent_name": "Toronto Blue Jays",
      "opponent_team_id": 141,
      "runs_allowed_innings_7_to_9": 2,
      "starter_exit_inning": 6,
      "starter_exit_score_against": 0,
      "starter_exit_score_for": 2,
      "starter_ip": 6.0,
      "starter_name": "Kumar Rocker",
      "starter_pitch_count": 92,
      "starter_player_id": 677958,
      "team_id": 140,
      "turning_inning": null
    },
    "evidence_blocks": {
      "available_relievers": [],
      "bullpen_entry_situation": {
        "inning": 7,
        "lead_when_entered": 2,
        "score_against": 0,
        "score_for": 2
      },
      "bullpen_summary": {
        "available_count": 0,
        "comeback_completed": false,
        "late_runs_allowed": 2,
        "lead_lost": false,
        "lead_protected": true,
        "limited_count": 0,
        "monitor_count": 0,
        "optionality_band": "insufficient_data",
        "unavailable_count": 0
      },
      "clean_options": [],
      "coverage_depth": {
        "clean_options_count": 0,
        "depth_pressure_band": "insufficient_data",
        "practical_close_game_paths_count": 0,
        "secondary_options_count": 0
      },
      "evidence_version": "evidence_v1",
      "key_relief_appearances": [],
      "largest_deficit": {
        "runs": 0
      },
      "largest_lead": {
        "runs": 2
      },
      "late_runs": {
        "late_runs_allowed": 2,
        "runs_allowed_innings_7_to_9": 2
      },
      "limited_relievers": [],
      "monitor_relievers": [],
      "starter_summary": {
        "exit_inning": 6,
        "exit_score_against": 0,
        "exit_score_for": 2,
        "game_shape_created": "normal_start",
        "innings": 6.0,
        "name": "Kumar Rocker",
        "pitch_count": 92
      },
      "story_evidence": {
        "primary_story": "protected_game_shape",
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
        ]
      },
      "turning_point": {},
      "unavailable_relievers": [],
      "workload_concentration": {
        "bullpen_workload_appearances_10d": 0,
        "bullpen_workload_total_10d": 0,
        "concentration_band": "insufficient_data",
        "window_days": 10
      }
    },
    "narrative_context": {
      "confidence": "HIGH",
      "context_type": "completed_game",
      "game_importance": "MEDIUM",
      "game_pk": 822795,
      "generated_at": "2026-06-30T01:41:34.492016",
      "headline_key": "protected_game_shape",
      "primary_story": "protected_game_shape",
      "secondary_story": "late_pressure_accumulated",
      "story_priority": "HIGH",
      "story_version": "narrative_context_v1",
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
      "team_id": 140
    },
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": null,
      "bullpen_workload_appearances_10d": 0,
      "bullpen_workload_total_10d": 0,
      "concentration_band": "insufficient_data",
      "context_available": true,
      "early_bullpen_entry_rate": null,
      "top_three_workload_share_10d": null,
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
Late lead closed out
```
Body:
```
After their most recent game, Kumar Rocker covered six innings before the bullpen took a two-run lead to the finish.
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
Late lead closed out

After their most recent game, Kumar Rocker covered six innings before the bullpen took a two-run lead to the finish.

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
Bullpen note: Late lead held
```
Body:
```
After their most recent game, the club turned a two-run lead into a win the bullpen never let slip.
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
Bullpen note: Late lead held

After their most recent game, the club turned a two-run lead into a win the bullpen never let slip.

Evidence:
- Starter: Kumar Rocker, 6.0 IP, 92 pitches
- Largest lead: 2
- Bullpen entered in the 7th with a 2-run lead
- Late runs allowed: 2
```

## Completed-Game Story 23: Team 141 (141)

### Story Metadata

```json
{
  "beat": "insufficient_context",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_or_unpublishable": true,
  "game_date": "2026-06-28",
  "game_importance": "LOW",
  "game_pk": 822795,
  "opponent_name": "Texas Rangers",
  "publish_reason": "insufficient_confidence",
  "publishable": false,
  "recommended_surface": "none",
  "safe_time_context": "CURRENT_STATUS",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_priority": "LOW",
  "story_type": "insufficient_context",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 0,
      "context_available": false,
      "limited_arms_count": 0,
      "monitor_arms_count": 0,
      "optionality_band": "insufficient_data",
      "restricted_arms_count": 0,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [],
      "clean_options_count": 0,
      "context_available": false,
      "core_retention_count": 0,
      "depth_pressure_band": "insufficient_data",
      "inactive_bullpen_arms_count": 0,
      "optionality_band": "insufficient_data",
      "practical_close_game_paths_count": 0,
      "secondary_options": [],
      "secondary_options_count": 0,
      "stability_band": "insufficient_data"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 6,
      "bullpen_entry_score_against": 1,
      "bullpen_entry_score_for": 0,
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
      "generated_at": "2026-06-30T00:53:58.989589",
      "home_away": "home",
      "id": 5,
      "largest_deficit": 2,
      "largest_lead": 0,
      "late_runs_allowed": 1,
      "lead_lost": null,
      "lead_protected": null,
      "lead_when_bullpen_entered": null,
      "opponent_name": "Texas Rangers",
      "opponent_team_id": 140,
      "runs_allowed_innings_7_to_9": 1,
      "starter_exit_inning": 6,
      "starter_exit_score_against": 1,
      "starter_exit_score_for": 0,
      "starter_ip": 5.333333333333333,
      "starter_name": "Shane Bieber",
      "starter_pitch_count": 92,
      "starter_player_id": 669456,
      "team_id": 141,
      "turning_inning": null
    },
    "evidence_blocks": {
      "available_relievers": [],
      "bullpen_entry_situation": {
        "deficit_when_entered": 1,
        "inning": 6,
        "score_against": 1,
        "score_for": 0
      },
      "bullpen_summary": {
        "available_count": 0,
        "comeback_completed": false,
        "late_runs_allowed": 1,
        "limited_count": 0,
        "monitor_count": 0,
        "optionality_band": "insufficient_data",
        "unavailable_count": 0
      },
      "clean_options": [],
      "coverage_depth": {
        "clean_options_count": 0,
        "depth_pressure_band": "insufficient_data",
        "practical_close_game_paths_count": 0,
        "secondary_options_count": 0
      },
      "evidence_version": "evidence_v1",
      "key_relief_appearances": [],
      "largest_deficit": {
        "runs": 2
      },
      "largest_lead": {
        "runs": 0
      },
      "late_runs": {
        "late_runs_allowed": 1,
        "runs_allowed_innings_7_to_9": 1
      },
      "limited_relievers": [],
      "monitor_relievers": [],
      "starter_summary": {
        "exit_inning": 6,
        "exit_score_against": 1,
        "exit_score_for": 0,
        "game_shape_created": "normal_start",
        "innings": 5.333333333333333,
        "name": "Shane Bieber",
        "pitch_count": 92
      },
      "story_evidence": {
        "primary_story": "insufficient_context",
        "supporting_facts": {},
        "supporting_observations": []
      },
      "turning_point": {},
      "unavailable_relievers": [],
      "workload_concentration": {
        "bullpen_workload_appearances_10d": 0,
        "bullpen_workload_total_10d": 0,
        "concentration_band": "insufficient_data",
        "window_days": 10
      }
    },
    "narrative_context": {
      "confidence": "HIGH",
      "context_type": "completed_game",
      "game_importance": "LOW",
      "game_pk": 822795,
      "generated_at": "2026-06-30T01:41:34.568499",
      "headline_key": "insufficient_context",
      "primary_story": "insufficient_context",
      "secondary_story": null,
      "story_priority": "LOW",
      "story_version": "narrative_context_v1",
      "summary_key": "insufficient_context",
      "supporting_facts": {},
      "supporting_observations": [],
      "team_id": 141
    },
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": null,
      "bullpen_workload_appearances_10d": 0,
      "bullpen_workload_total_10d": 0,
      "concentration_band": "insufficient_data",
      "context_available": true,
      "early_bullpen_entry_rate": null,
      "top_three_workload_share_10d": null,
      "window_days": 10
    }
  },
  "team_id": 141,
  "writer_targets": []
}
```

No draft rendered.

## Completed-Game Story 24: Team 142 (142)

### Story Metadata

```json
{
  "beat": "bullpen_kept_team_alive",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_or_unpublishable": false,
  "game_date": "2026-06-28",
  "game_importance": "LOW",
  "game_pk": 823686,
  "opponent_name": "Colorado Rockies",
  "publish_reason": "high_priority_narrative",
  "publishable": true,
  "recommended_surface": "multiple",
  "safe_time_context": "AFTER_MOST_RECENT_GAME",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_priority": "HIGH",
  "story_type": "bullpen_kept_team_alive",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 0,
      "context_available": false,
      "limited_arms_count": 0,
      "monitor_arms_count": 0,
      "optionality_band": "insufficient_data",
      "restricted_arms_count": 0,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [],
      "clean_options_count": 0,
      "context_available": false,
      "core_retention_count": 0,
      "depth_pressure_band": "insufficient_data",
      "inactive_bullpen_arms_count": 0,
      "optionality_band": "insufficient_data",
      "practical_close_game_paths_count": 0,
      "secondary_options": [],
      "secondary_options_count": 0,
      "stability_band": "insufficient_data"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 7,
      "bullpen_entry_score_against": 2,
      "bullpen_entry_score_for": 2,
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
      "generated_at": "2026-06-30T00:53:59.636743",
      "home_away": "home",
      "id": 15,
      "largest_deficit": 1,
      "largest_lead": 1,
      "late_runs_allowed": 0,
      "lead_lost": null,
      "lead_protected": null,
      "lead_when_bullpen_entered": null,
      "opponent_name": "Colorado Rockies",
      "opponent_team_id": 115,
      "runs_allowed_innings_7_to_9": 0,
      "starter_exit_inning": 6,
      "starter_exit_score_against": 2,
      "starter_exit_score_for": 2,
      "starter_ip": 6.0,
      "starter_name": "Connor Prielipp",
      "starter_pitch_count": 93,
      "starter_player_id": 687570,
      "team_id": 142,
      "turning_inning": 4
    },
    "evidence_blocks": {
      "available_relievers": [],
      "bullpen_entry_situation": {
        "inning": 7,
        "score_against": 2,
        "score_for": 2
      },
      "bullpen_summary": {
        "available_count": 0,
        "comeback_completed": true,
        "late_runs_allowed": 0,
        "limited_count": 0,
        "monitor_count": 0,
        "optionality_band": "insufficient_data",
        "unavailable_count": 0
      },
      "clean_options": [],
      "coverage_depth": {
        "clean_options_count": 0,
        "depth_pressure_band": "insufficient_data",
        "practical_close_game_paths_count": 0,
        "secondary_options_count": 0
      },
      "evidence_version": "evidence_v1",
      "key_relief_appearances": [],
      "largest_deficit": {
        "runs": 1
      },
      "largest_lead": {
        "runs": 1
      },
      "late_runs": {
        "late_runs_allowed": 0,
        "runs_allowed_innings_7_to_9": 0
      },
      "limited_relievers": [],
      "monitor_relievers": [],
      "starter_summary": {
        "exit_inning": 6,
        "exit_score_against": 2,
        "exit_score_for": 2,
        "game_shape_created": "normal_start",
        "innings": 6.0,
        "name": "Connor Prielipp",
        "pitch_count": 93
      },
      "story_evidence": {
        "primary_story": "bullpen_kept_team_alive",
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
        ]
      },
      "turning_point": {
        "inning": 4
      },
      "unavailable_relievers": [],
      "workload_concentration": {
        "bullpen_workload_appearances_10d": 0,
        "bullpen_workload_total_10d": 0,
        "concentration_band": "insufficient_data",
        "window_days": 10
      }
    },
    "narrative_context": {
      "confidence": "HIGH",
      "context_type": "completed_game",
      "game_importance": "LOW",
      "game_pk": 823686,
      "generated_at": "2026-06-30T01:41:34.637816",
      "headline_key": "bullpen_kept_team_alive",
      "primary_story": "bullpen_kept_team_alive",
      "secondary_story": "starter_covered_bullpen",
      "story_priority": "HIGH",
      "story_version": "narrative_context_v1",
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
      "team_id": 142
    },
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": null,
      "bullpen_workload_appearances_10d": 0,
      "bullpen_workload_total_10d": 0,
      "concentration_band": "insufficient_data",
      "context_available": true,
      "early_bullpen_entry_rate": null,
      "top_three_workload_share_10d": null,
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
Relievers left room for the rally
```
Body:
```
After their most recent game, Connor Prielipp's six innings left a one-run deficit, and the bullpen kept it close from the 7th on. The offense finished the rally.
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
Relievers left room for the rally

After their most recent game, Connor Prielipp's six innings left a one-run deficit, and the bullpen kept it close from the 7th on. The offense finished the rally.

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
Bullpen gave the comeback room
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
Bullpen gave the comeback room

The club kept the comeback alive.

Evidence:
- Starter: Connor Prielipp, 6.0 IP, 93 pitches
```

### Draft: morning_brief

Headline:
```
Bullpen note: Bullpen kept it alive
```
Body:
```
After their most recent game, the club climbed out of a one-run hole the bullpen kept from growing.
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

After their most recent game, the club climbed out of a one-run hole the bullpen kept from growing.

Evidence:
- Starter: Connor Prielipp, 6.0 IP, 93 pitches
- Largest deficit: 1
- Bullpen entered in the 7th
- Turning point: 4th inning
- Late runs allowed: 0
```

## Completed-Game Story 25: Team 143 (143)

### Story Metadata

```json
{
  "beat": "protected_game_shape",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_or_unpublishable": false,
  "game_date": "2026-06-28",
  "game_importance": "MEDIUM",
  "game_pk": 823608,
  "opponent_name": "New York Mets",
  "publish_reason": "high_priority_narrative",
  "publishable": true,
  "recommended_surface": "multiple",
  "safe_time_context": "AFTER_MOST_RECENT_GAME",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_priority": "HIGH",
  "story_type": "protected_game_shape",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 0,
      "context_available": false,
      "limited_arms_count": 0,
      "monitor_arms_count": 0,
      "optionality_band": "insufficient_data",
      "restricted_arms_count": 0,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [],
      "clean_options_count": 0,
      "context_available": false,
      "core_retention_count": 0,
      "depth_pressure_band": "insufficient_data",
      "inactive_bullpen_arms_count": 0,
      "optionality_band": "insufficient_data",
      "practical_close_game_paths_count": 0,
      "secondary_options": [],
      "secondary_options_count": 0,
      "stability_band": "insufficient_data"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 6,
      "bullpen_entry_score_against": 1,
      "bullpen_entry_score_for": 3,
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
      "generated_at": "2026-06-30T00:53:59.549340",
      "home_away": "away",
      "id": 14,
      "largest_deficit": 1,
      "largest_lead": 3,
      "late_runs_allowed": 0,
      "lead_lost": false,
      "lead_protected": true,
      "lead_when_bullpen_entered": 2,
      "opponent_name": "New York Mets",
      "opponent_team_id": 121,
      "runs_allowed_innings_7_to_9": 0,
      "starter_exit_inning": 5,
      "starter_exit_score_against": 1,
      "starter_exit_score_for": 3,
      "starter_ip": 5.0,
      "starter_name": "Jesús Luzardo",
      "starter_pitch_count": 96,
      "starter_player_id": 666200,
      "team_id": 143,
      "turning_inning": 7
    },
    "evidence_blocks": {
      "available_relievers": [],
      "bullpen_entry_situation": {
        "inning": 6,
        "lead_when_entered": 2,
        "score_against": 1,
        "score_for": 3
      },
      "bullpen_summary": {
        "available_count": 0,
        "comeback_completed": true,
        "late_runs_allowed": 0,
        "lead_lost": false,
        "lead_protected": true,
        "limited_count": 0,
        "monitor_count": 0,
        "optionality_band": "insufficient_data",
        "unavailable_count": 0
      },
      "clean_options": [],
      "coverage_depth": {
        "bullpen_coverage_ip_7d": 4.0,
        "clean_options_count": 0,
        "depth_pressure_band": "insufficient_data",
        "practical_close_game_paths_count": 0,
        "secondary_options_count": 0
      },
      "evidence_version": "evidence_v1",
      "key_relief_appearances": [],
      "largest_deficit": {
        "runs": 1
      },
      "largest_lead": {
        "runs": 3
      },
      "late_runs": {
        "late_runs_allowed": 0,
        "runs_allowed_innings_7_to_9": 0
      },
      "limited_relievers": [],
      "monitor_relievers": [],
      "starter_summary": {
        "exit_inning": 5,
        "exit_score_against": 1,
        "exit_score_for": 3,
        "game_shape_created": "normal_start",
        "innings": 5.0,
        "name": "Jesús Luzardo",
        "pitch_count": 96
      },
      "story_evidence": {
        "primary_story": "protected_game_shape",
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
        ]
      },
      "turning_point": {
        "inning": 7
      },
      "unavailable_relievers": [],
      "workload_concentration": {
        "bullpen_workload_appearances_10d": 6,
        "bullpen_workload_total_10d": 114,
        "concentration_band": "normal",
        "top_three_workload_share_10d": 62.3,
        "window_days": 10
      }
    },
    "narrative_context": {
      "confidence": "HIGH",
      "context_type": "completed_game",
      "game_importance": "MEDIUM",
      "game_pk": 823608,
      "generated_at": "2026-06-30T01:41:34.797778",
      "headline_key": "bullpen_stabilized",
      "primary_story": "protected_game_shape",
      "secondary_story": "bullpen_kept_team_alive",
      "story_priority": "HIGH",
      "story_version": "narrative_context_v1",
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
      "team_id": 143
    },
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": 4.0,
      "bullpen_workload_appearances_10d": 6,
      "bullpen_workload_total_10d": 114,
      "concentration_band": "normal",
      "context_available": true,
      "early_bullpen_entry_rate": 0.0,
      "top_three_workload_share_10d": 62.3,
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
Quiet finish from the pen
```
Body:
```
After their most recent game, Jesús Luzardo gave the bullpen a three-run lead after five innings, and the late innings held.
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
Quiet finish from the pen

After their most recent game, Jesús Luzardo gave the bullpen a three-run lead after five innings, and the late innings held.

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
Bullpen note: Lead finished cleanly
```
Body:
```
After their most recent game, the club turned a three-run lead into a win the bullpen never let slip.
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
Bullpen note: Lead finished cleanly

After their most recent game, the club turned a three-run lead into a win the bullpen never let slip.

Evidence:
- Starter: Jesús Luzardo, 5.0 IP, 96 pitches
- Largest lead: 3
- Bullpen entered in the 6th with a 2-run lead
- Turning point: 7th inning
- Late runs allowed: 0
```

## Completed-Game Story 26: Team 144 (144)

### Story Metadata

```json
{
  "beat": "starter_covered_bullpen",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_or_unpublishable": false,
  "game_date": "2026-06-28",
  "game_importance": "LOW",
  "game_pk": 823204,
  "opponent_name": "San Francisco Giants",
  "publish_reason": "meets_confidence_threshold",
  "publishable": true,
  "recommended_surface": "dashboard",
  "safe_time_context": "AFTER_MOST_RECENT_GAME",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_priority": "MEDIUM",
  "story_type": "starter_covered_bullpen",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 0,
      "context_available": false,
      "limited_arms_count": 0,
      "monitor_arms_count": 0,
      "optionality_band": "insufficient_data",
      "restricted_arms_count": 0,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [],
      "clean_options_count": 0,
      "context_available": false,
      "core_retention_count": 0,
      "depth_pressure_band": "insufficient_data",
      "inactive_bullpen_arms_count": 0,
      "optionality_band": "insufficient_data",
      "practical_close_game_paths_count": 0,
      "secondary_options": [],
      "secondary_options_count": 0,
      "stability_band": "insufficient_data"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 7,
      "bullpen_entry_score_against": 2,
      "bullpen_entry_score_for": 0,
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
      "generated_at": "2026-06-30T00:54:00.234004",
      "home_away": "away",
      "id": 26,
      "largest_deficit": 3,
      "largest_lead": 0,
      "late_runs_allowed": 1,
      "lead_lost": null,
      "lead_protected": null,
      "lead_when_bullpen_entered": null,
      "opponent_name": "San Francisco Giants",
      "opponent_team_id": 137,
      "runs_allowed_innings_7_to_9": 1,
      "starter_exit_inning": 6,
      "starter_exit_score_against": 2,
      "starter_exit_score_for": 0,
      "starter_ip": 6.0,
      "starter_name": "Chris Sale",
      "starter_pitch_count": 94,
      "starter_player_id": 519242,
      "team_id": 144,
      "turning_inning": null
    },
    "evidence_blocks": {
      "available_relievers": [],
      "bullpen_entry_situation": {
        "deficit_when_entered": 2,
        "inning": 7,
        "score_against": 2,
        "score_for": 0
      },
      "bullpen_summary": {
        "available_count": 0,
        "comeback_completed": false,
        "late_runs_allowed": 1,
        "limited_count": 0,
        "monitor_count": 0,
        "optionality_band": "insufficient_data",
        "unavailable_count": 0
      },
      "clean_options": [],
      "coverage_depth": {
        "clean_options_count": 0,
        "depth_pressure_band": "insufficient_data",
        "practical_close_game_paths_count": 0,
        "secondary_options_count": 0
      },
      "evidence_version": "evidence_v1",
      "key_relief_appearances": [],
      "largest_deficit": {
        "runs": 3
      },
      "largest_lead": {
        "runs": 0
      },
      "late_runs": {
        "late_runs_allowed": 1,
        "runs_allowed_innings_7_to_9": 1
      },
      "limited_relievers": [],
      "monitor_relievers": [],
      "starter_summary": {
        "exit_inning": 6,
        "exit_score_against": 2,
        "exit_score_for": 0,
        "game_shape_created": "normal_start",
        "innings": 6.0,
        "name": "Chris Sale",
        "pitch_count": 94
      },
      "story_evidence": {
        "primary_story": "starter_covered_bullpen",
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
        ]
      },
      "turning_point": {},
      "unavailable_relievers": [],
      "workload_concentration": {
        "bullpen_workload_appearances_10d": 0,
        "bullpen_workload_total_10d": 0,
        "concentration_band": "insufficient_data",
        "window_days": 10
      }
    },
    "narrative_context": {
      "confidence": "HIGH",
      "context_type": "completed_game",
      "game_importance": "LOW",
      "game_pk": 823204,
      "generated_at": "2026-06-30T01:41:34.874705",
      "headline_key": "starter_carried_game",
      "primary_story": "starter_covered_bullpen",
      "secondary_story": null,
      "story_priority": "MEDIUM",
      "story_version": "narrative_context_v1",
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
      "team_id": 144
    },
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": null,
      "bullpen_workload_appearances_10d": 0,
      "bullpen_workload_total_10d": 0,
      "concentration_band": "insufficient_data",
      "context_available": true,
      "early_bullpen_entry_rate": null,
      "top_three_workload_share_10d": null,
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
Starter covered the hard part
```
Body:
```
After their most recent game, Chris Sale worked 6.0 innings, keeping the relief workload short. That creates room for the workload to move beyond the usual pocket.
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
```
Exact rendered text:
```
Starter covered the hard part

After their most recent game, Chris Sale worked 6.0 innings, keeping the relief workload short. That creates room for the workload to move beyond the usual pocket.

Evidence:
- Starter: Chris Sale, 6.0 IP, 94 pitches
- Largest deficit: 3
- Bullpen entered in the 7th trailing by 2
- Late runs allowed: 1
```

### Draft: dashboard

Headline:
```
Deep start kept the bullpen light
```
Body:
```
The club kept the bullpen light after Chris Sale worked 6.0 innings.
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
Deep start kept the bullpen light

The club kept the bullpen light after Chris Sale worked 6.0 innings.

Evidence:
- Starter: Chris Sale, 6.0 IP, 94 pitches
```

## Completed-Game Story 27: Team 145 (145)

### Story Metadata

```json
{
  "beat": "bullpen_overexposed",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_or_unpublishable": false,
  "game_date": "2026-06-28",
  "game_importance": "LOW",
  "game_pk": 824580,
  "opponent_name": "Kansas City Royals",
  "publish_reason": "meets_confidence_threshold",
  "publishable": true,
  "recommended_surface": "dashboard",
  "safe_time_context": "AFTER_MOST_RECENT_GAME",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_priority": "MEDIUM",
  "story_type": "bullpen_overexposed",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 0,
      "context_available": false,
      "limited_arms_count": 0,
      "monitor_arms_count": 0,
      "optionality_band": "insufficient_data",
      "restricted_arms_count": 0,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [],
      "clean_options_count": 0,
      "context_available": false,
      "core_retention_count": 0,
      "depth_pressure_band": "insufficient_data",
      "inactive_bullpen_arms_count": 0,
      "optionality_band": "insufficient_data",
      "practical_close_game_paths_count": 0,
      "secondary_options": [],
      "secondary_options_count": 0,
      "stability_band": "insufficient_data"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 4,
      "bullpen_entry_score_against": 5,
      "bullpen_entry_score_for": 4,
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
      "generated_at": "2026-06-30T00:53:59.727589",
      "home_away": "home",
      "id": 17,
      "largest_deficit": 1,
      "largest_lead": 1,
      "late_runs_allowed": 0,
      "lead_lost": null,
      "lead_protected": null,
      "lead_when_bullpen_entered": null,
      "opponent_name": "Kansas City Royals",
      "opponent_team_id": 118,
      "runs_allowed_innings_7_to_9": 0,
      "starter_exit_inning": 4,
      "starter_exit_score_against": 5,
      "starter_exit_score_for": 4,
      "starter_ip": 3.6666666666666665,
      "starter_name": "Anthony Kay",
      "starter_pitch_count": 73,
      "starter_player_id": 641743,
      "team_id": 145,
      "turning_inning": 4
    },
    "evidence_blocks": {
      "available_relievers": [],
      "bullpen_entry_situation": {
        "deficit_when_entered": 1,
        "inning": 4,
        "score_against": 5,
        "score_for": 4
      },
      "bullpen_summary": {
        "available_count": 0,
        "comeback_completed": false,
        "late_runs_allowed": 0,
        "limited_count": 0,
        "monitor_count": 0,
        "optionality_band": "insufficient_data",
        "unavailable_count": 0
      },
      "clean_options": [],
      "coverage_depth": {
        "clean_options_count": 0,
        "depth_pressure_band": "insufficient_data",
        "practical_close_game_paths_count": 0,
        "secondary_options_count": 0
      },
      "evidence_version": "evidence_v1",
      "key_relief_appearances": [],
      "largest_deficit": {
        "runs": 1
      },
      "largest_lead": {
        "runs": 1
      },
      "late_runs": {
        "late_runs_allowed": 0,
        "runs_allowed_innings_7_to_9": 0
      },
      "limited_relievers": [],
      "monitor_relievers": [],
      "starter_summary": {
        "exit_inning": 4,
        "exit_score_against": 5,
        "exit_score_for": 4,
        "game_shape_created": "short_start",
        "innings": 3.6666666666666665,
        "name": "Anthony Kay",
        "pitch_count": 73
      },
      "story_evidence": {
        "primary_story": "bullpen_overexposed",
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
        ]
      },
      "turning_point": {
        "inning": 4
      },
      "unavailable_relievers": [],
      "workload_concentration": {
        "bullpen_workload_appearances_10d": 0,
        "bullpen_workload_total_10d": 0,
        "concentration_band": "insufficient_data",
        "window_days": 10
      }
    },
    "narrative_context": {
      "confidence": "HIGH",
      "context_type": "completed_game",
      "game_importance": "LOW",
      "game_pk": 824580,
      "generated_at": "2026-06-30T01:41:34.949186",
      "headline_key": "bullpen_overexposed",
      "primary_story": "bullpen_overexposed",
      "secondary_story": null,
      "story_priority": "MEDIUM",
      "story_version": "narrative_context_v1",
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
      "team_id": 145
    },
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": null,
      "bullpen_workload_appearances_10d": 0,
      "bullpen_workload_total_10d": 0,
      "concentration_band": "insufficient_data",
      "context_available": true,
      "early_bullpen_entry_rate": null,
      "top_three_workload_share_10d": null,
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
Short start stretched the bullpen
```
Body:
```
After their most recent game, Anthony Kay's 3.2-inning start pushed the rest of the game to the bullpen.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Anthony Kay, 3.2 IP, 73 pitches
- Largest lead: 1
- Bullpen entered in the 4th trailing by 1
- Turning point: 4th inning
- Late runs allowed: 0
```
Exact rendered text:
```
Short start stretched the bullpen

After their most recent game, Anthony Kay's 3.2-inning start pushed the rest of the game to the bullpen.

Evidence:
- Starter: Anthony Kay, 3.2 IP, 73 pitches
- Largest lead: 1
- Bullpen entered in the 4th trailing by 1
- Turning point: 4th inning
- Late runs allowed: 0
```

### Draft: dashboard

Headline:
```
Bullpen had to cover
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
- Starter: Anthony Kay, 3.2 IP, 73 pitches
```
Exact rendered text:
```
Bullpen had to cover

The club covered heavy innings on a short start.

Evidence:
- Starter: Anthony Kay, 3.2 IP, 73 pitches
```

## Completed-Game Story 28: Team 146 (146)

### Story Metadata

```json
{
  "beat": "starter_covered_bullpen",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_or_unpublishable": false,
  "game_date": "2026-06-28",
  "game_importance": "LOW",
  "game_pk": 823037,
  "opponent_name": "St. Louis Cardinals",
  "publish_reason": "meets_confidence_threshold",
  "publishable": true,
  "recommended_surface": "dashboard",
  "safe_time_context": "AFTER_MOST_RECENT_GAME",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_priority": "MEDIUM",
  "story_type": "starter_covered_bullpen",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 0,
      "context_available": false,
      "limited_arms_count": 0,
      "monitor_arms_count": 0,
      "optionality_band": "insufficient_data",
      "restricted_arms_count": 0,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [],
      "clean_options_count": 0,
      "context_available": false,
      "core_retention_count": 0,
      "depth_pressure_band": "insufficient_data",
      "inactive_bullpen_arms_count": 0,
      "optionality_band": "insufficient_data",
      "practical_close_game_paths_count": 0,
      "secondary_options": [],
      "secondary_options_count": 0,
      "stability_band": "insufficient_data"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 8,
      "bullpen_entry_score_against": 2,
      "bullpen_entry_score_for": 1,
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
      "generated_at": "2026-06-30T00:54:00.029493",
      "home_away": "away",
      "id": 22,
      "largest_deficit": 2,
      "largest_lead": 0,
      "late_runs_allowed": 0,
      "lead_lost": null,
      "lead_protected": null,
      "lead_when_bullpen_entered": null,
      "opponent_name": "St. Louis Cardinals",
      "opponent_team_id": 138,
      "runs_allowed_innings_7_to_9": 0,
      "starter_exit_inning": 8,
      "starter_exit_score_against": 2,
      "starter_exit_score_for": 1,
      "starter_ip": 7.333333333333333,
      "starter_name": "Tyler Phillips",
      "starter_pitch_count": 97,
      "starter_player_id": 663969,
      "team_id": 146,
      "turning_inning": null
    },
    "evidence_blocks": {
      "available_relievers": [],
      "bullpen_entry_situation": {
        "deficit_when_entered": 1,
        "inning": 8,
        "score_against": 2,
        "score_for": 1
      },
      "bullpen_summary": {
        "available_count": 0,
        "comeback_completed": false,
        "late_runs_allowed": 0,
        "limited_count": 0,
        "monitor_count": 0,
        "optionality_band": "insufficient_data",
        "unavailable_count": 0
      },
      "clean_options": [],
      "coverage_depth": {
        "clean_options_count": 0,
        "depth_pressure_band": "insufficient_data",
        "practical_close_game_paths_count": 0,
        "secondary_options_count": 0
      },
      "evidence_version": "evidence_v1",
      "key_relief_appearances": [],
      "largest_deficit": {
        "runs": 2
      },
      "largest_lead": {
        "runs": 0
      },
      "late_runs": {
        "late_runs_allowed": 0,
        "runs_allowed_innings_7_to_9": 0
      },
      "limited_relievers": [],
      "monitor_relievers": [],
      "starter_summary": {
        "exit_inning": 8,
        "exit_score_against": 2,
        "exit_score_for": 1,
        "game_shape_created": "normal_start",
        "innings": 7.333333333333333,
        "name": "Tyler Phillips",
        "pitch_count": 97
      },
      "story_evidence": {
        "primary_story": "starter_covered_bullpen",
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
        ]
      },
      "turning_point": {},
      "unavailable_relievers": [],
      "workload_concentration": {
        "bullpen_workload_appearances_10d": 0,
        "bullpen_workload_total_10d": 0,
        "concentration_band": "insufficient_data",
        "window_days": 10
      }
    },
    "narrative_context": {
      "confidence": "HIGH",
      "context_type": "completed_game",
      "game_importance": "LOW",
      "game_pk": 823037,
      "generated_at": "2026-06-30T01:41:35.026551",
      "headline_key": "starter_carried_game",
      "primary_story": "starter_covered_bullpen",
      "secondary_story": null,
      "story_priority": "MEDIUM",
      "story_version": "narrative_context_v1",
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
      "team_id": 146
    },
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": null,
      "bullpen_workload_appearances_10d": 0,
      "bullpen_workload_total_10d": 0,
      "concentration_band": "insufficient_data",
      "context_available": true,
      "early_bullpen_entry_rate": null,
      "top_three_workload_share_10d": null,
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
Starter spared the bullpen
```
Body:
```
After their most recent game, Tyler Phillips worked 7.1 innings, so the bullpen only had to finish the shorter piece. That lets the bullpen spread the work across more arms.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Tyler Phillips, 7.1 IP, 97 pitches
- Largest deficit: 2
- Bullpen entered in the 8th trailing by 1
- Late runs allowed: 0
```
Exact rendered text:
```
Starter spared the bullpen

After their most recent game, Tyler Phillips worked 7.1 innings, so the bullpen only had to finish the shorter piece. That lets the bullpen spread the work across more arms.

Evidence:
- Starter: Tyler Phillips, 7.1 IP, 97 pitches
- Largest deficit: 2
- Bullpen entered in the 8th trailing by 1
- Late runs allowed: 0
```

### Draft: dashboard

Headline:
```
Deep start lightened the load
```
Body:
```
The club kept the bullpen light after Tyler Phillips worked 7.1 innings.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Tyler Phillips, 7.1 IP, 97 pitches
```
Exact rendered text:
```
Deep start lightened the load

The club kept the bullpen light after Tyler Phillips worked 7.1 innings.

Evidence:
- Starter: Tyler Phillips, 7.1 IP, 97 pitches
```

## Completed-Game Story 29: Team 147 (147)

### Story Metadata

```json
{
  "beat": "insufficient_context",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_or_unpublishable": true,
  "game_date": "2026-06-28",
  "game_importance": "LOW",
  "game_pk": 824744,
  "opponent_name": "Boston Red Sox",
  "publish_reason": "insufficient_confidence",
  "publishable": false,
  "recommended_surface": "none",
  "safe_time_context": "CURRENT_STATUS",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_priority": "LOW",
  "story_type": "insufficient_context",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 0,
      "context_available": false,
      "limited_arms_count": 0,
      "monitor_arms_count": 0,
      "optionality_band": "insufficient_data",
      "restricted_arms_count": 0,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [],
      "clean_options_count": 0,
      "context_available": false,
      "core_retention_count": 0,
      "depth_pressure_band": "insufficient_data",
      "inactive_bullpen_arms_count": 0,
      "optionality_band": "insufficient_data",
      "practical_close_game_paths_count": 0,
      "secondary_options": [],
      "secondary_options_count": 0,
      "stability_band": "insufficient_data"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 6,
      "bullpen_entry_score_against": 2,
      "bullpen_entry_score_for": 0,
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
      "generated_at": "2026-06-30T00:54:00.600286",
      "home_away": "away",
      "id": 30,
      "largest_deficit": 2,
      "largest_lead": 2,
      "late_runs_allowed": 3,
      "lead_lost": null,
      "lead_protected": null,
      "lead_when_bullpen_entered": null,
      "opponent_name": "Boston Red Sox",
      "opponent_team_id": 111,
      "runs_allowed_innings_7_to_9": 0,
      "starter_exit_inning": 5,
      "starter_exit_score_against": 2,
      "starter_exit_score_for": 0,
      "starter_ip": 5.0,
      "starter_name": "Carlos Rodón",
      "starter_pitch_count": 96,
      "starter_player_id": 607074,
      "team_id": 147,
      "turning_inning": 10
    },
    "evidence_blocks": {
      "available_relievers": [],
      "bullpen_entry_situation": {
        "deficit_when_entered": 2,
        "inning": 6,
        "score_against": 2,
        "score_for": 0
      },
      "bullpen_summary": {
        "available_count": 0,
        "comeback_completed": false,
        "late_runs_allowed": 3,
        "limited_count": 0,
        "monitor_count": 0,
        "optionality_band": "insufficient_data",
        "unavailable_count": 0
      },
      "clean_options": [],
      "coverage_depth": {
        "bullpen_coverage_ip_7d": 4.3,
        "clean_options_count": 0,
        "depth_pressure_band": "insufficient_data",
        "practical_close_game_paths_count": 0,
        "secondary_options_count": 0
      },
      "evidence_version": "evidence_v1",
      "key_relief_appearances": [],
      "largest_deficit": {
        "runs": 2
      },
      "largest_lead": {
        "runs": 2
      },
      "late_runs": {
        "late_runs_allowed": 3,
        "runs_allowed_innings_7_to_9": 0
      },
      "limited_relievers": [],
      "monitor_relievers": [],
      "starter_summary": {
        "exit_inning": 5,
        "exit_score_against": 2,
        "exit_score_for": 0,
        "game_shape_created": "normal_start",
        "innings": 5.0,
        "name": "Carlos Rodón",
        "pitch_count": 96
      },
      "story_evidence": {
        "primary_story": "insufficient_context",
        "supporting_facts": {},
        "supporting_observations": []
      },
      "turning_point": {
        "inning": 10
      },
      "unavailable_relievers": [],
      "workload_concentration": {
        "bullpen_workload_appearances_10d": 3,
        "bullpen_workload_total_10d": 57,
        "concentration_band": "narrow",
        "top_three_workload_share_10d": 100.0,
        "window_days": 10
      }
    },
    "narrative_context": {
      "confidence": "HIGH",
      "context_type": "completed_game",
      "game_importance": "LOW",
      "game_pk": 824744,
      "generated_at": "2026-06-30T01:41:35.130858",
      "headline_key": "insufficient_context",
      "primary_story": "insufficient_context",
      "secondary_story": null,
      "story_priority": "LOW",
      "story_version": "narrative_context_v1",
      "summary_key": "insufficient_context",
      "supporting_facts": {},
      "supporting_observations": [],
      "team_id": 147
    },
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": 4.3,
      "bullpen_workload_appearances_10d": 3,
      "bullpen_workload_total_10d": 57,
      "concentration_band": "narrow",
      "context_available": true,
      "early_bullpen_entry_rate": 0.0,
      "top_three_workload_share_10d": 100.0,
      "window_days": 10
    }
  },
  "team_id": 147,
  "writer_targets": []
}
```

No draft rendered.

## Completed-Game Story 30: Team 158 (158)

### Story Metadata

```json
{
  "beat": "lost_game_shape",
  "confidence": "HIGH",
  "export_error": null,
  "fallback_or_unpublishable": false,
  "game_date": "2026-06-28",
  "game_importance": "MEDIUM",
  "game_pk": 823769,
  "opponent_name": "Chicago Cubs",
  "publish_reason": "critical_narrative",
  "publishable": true,
  "recommended_surface": "multiple",
  "safe_time_context": "AFTER_MOST_RECENT_GAME",
  "source_path": "CompletedGameContext row -> inspect_team_story -> existing story writers",
  "story_priority": "CRITICAL",
  "story_type": "lost_game_shape",
  "supporting_context_values": {
    "availability_snapshot": {
      "available_arms_count": 0,
      "context_available": false,
      "limited_arms_count": 0,
      "monitor_arms_count": 0,
      "optionality_band": "insufficient_data",
      "restricted_arms_count": 0,
      "unavailable_arms_count": 0,
      "unknown_status_count": 0
    },
    "bullpen_snapshot": {
      "clean_options": [],
      "clean_options_count": 0,
      "context_available": false,
      "core_retention_count": 0,
      "depth_pressure_band": "insufficient_data",
      "inactive_bullpen_arms_count": 0,
      "optionality_band": "insufficient_data",
      "practical_close_game_paths_count": 0,
      "secondary_options": [],
      "secondary_options_count": 0,
      "stability_band": "insufficient_data"
    },
    "completed_game_context": {
      "bullpen_entry_inning": 6,
      "bullpen_entry_score_against": 0,
      "bullpen_entry_score_for": 1,
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
      "generated_at": "2026-06-30T00:53:59.838741",
      "home_away": "home",
      "id": 19,
      "largest_deficit": 3,
      "largest_lead": 1,
      "late_runs_allowed": 4,
      "lead_lost": true,
      "lead_protected": false,
      "lead_when_bullpen_entered": 1,
      "opponent_name": "Chicago Cubs",
      "opponent_team_id": 112,
      "runs_allowed_innings_7_to_9": 1,
      "starter_exit_inning": 6,
      "starter_exit_score_against": 0,
      "starter_exit_score_for": 1,
      "starter_ip": 5.666666666666667,
      "starter_name": "Brandon Woodruff",
      "starter_pitch_count": 84,
      "starter_player_id": 605540,
      "team_id": 158,
      "turning_inning": 10
    },
    "evidence_blocks": {
      "available_relievers": [],
      "bullpen_entry_situation": {
        "inning": 6,
        "lead_when_entered": 1,
        "score_against": 0,
        "score_for": 1
      },
      "bullpen_summary": {
        "available_count": 0,
        "comeback_completed": false,
        "late_runs_allowed": 4,
        "lead_lost": true,
        "lead_protected": false,
        "limited_count": 0,
        "monitor_count": 0,
        "optionality_band": "insufficient_data",
        "unavailable_count": 0
      },
      "clean_options": [],
      "coverage_depth": {
        "clean_options_count": 0,
        "depth_pressure_band": "insufficient_data",
        "practical_close_game_paths_count": 0,
        "secondary_options_count": 0
      },
      "evidence_version": "evidence_v1",
      "key_relief_appearances": [],
      "largest_deficit": {
        "runs": 3
      },
      "largest_lead": {
        "runs": 1
      },
      "late_runs": {
        "late_runs_allowed": 4,
        "runs_allowed_innings_7_to_9": 1
      },
      "limited_relievers": [],
      "monitor_relievers": [],
      "starter_summary": {
        "exit_inning": 6,
        "exit_score_against": 0,
        "exit_score_for": 1,
        "game_shape_created": "normal_start",
        "innings": 5.666666666666667,
        "name": "Brandon Woodruff",
        "pitch_count": 84
      },
      "story_evidence": {
        "primary_story": "lost_game_shape",
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
        ]
      },
      "turning_point": {
        "inning": 10
      },
      "unavailable_relievers": [],
      "workload_concentration": {
        "bullpen_workload_appearances_10d": 0,
        "bullpen_workload_total_10d": 0,
        "concentration_band": "insufficient_data",
        "window_days": 10
      }
    },
    "narrative_context": {
      "confidence": "HIGH",
      "context_type": "completed_game",
      "game_importance": "MEDIUM",
      "game_pk": 823769,
      "generated_at": "2026-06-30T01:41:35.208029",
      "headline_key": "lost_game_shape",
      "primary_story": "lost_game_shape",
      "secondary_story": null,
      "story_priority": "CRITICAL",
      "story_version": "narrative_context_v1",
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
      "team_id": 158
    },
    "workload_snapshot": {
      "bullpen_coverage_ip_7d": null,
      "bullpen_workload_appearances_10d": 0,
      "bullpen_workload_total_10d": 0,
      "concentration_band": "insufficient_data",
      "context_available": true,
      "early_bullpen_entry_rate": null,
      "top_three_workload_share_10d": null,
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
Late lead slipped away
```
Body:
```
After their most recent game, Brandon Woodruff worked 5.2 innings before a one-run lead reached the bullpen. It didn't last. Four late runs turned the game.
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
- Starter: Brandon Woodruff, 5.2 IP, 84 pitches
- Largest lead: 1
- Bullpen entered in the 6th with a 1-run lead
- Turning point: 10th inning
- Late runs allowed: 4
```
Exact rendered text:
```
Late lead slipped away

After their most recent game, Brandon Woodruff worked 5.2 innings before a one-run lead reached the bullpen. It didn't last. Four late runs turned the game.

Why BaseballOS sees it:
- The starter set the bullpen up to finish the game.
- The bullpen took over with a lead in hand.
- The relievers could not hold the lead.
- The damage came after the starter exited.

Evidence:
- Starter: Brandon Woodruff, 5.2 IP, 84 pitches
- Largest lead: 1
- Bullpen entered in the 6th with a 1-run lead
- Turning point: 10th inning
- Late runs allowed: 4
```

### Draft: dashboard

Headline:
```
Lead disappeared late
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
- Starter: Brandon Woodruff, 5.2 IP, 84 pitches
```
Exact rendered text:
```
Lead disappeared late

The club blew a 1-run lead late.

Evidence:
- Starter: Brandon Woodruff, 5.2 IP, 84 pitches
```

### Draft: morning_brief

Headline:
```
Bullpen note: Lead surrendered late
```
Body:
```
After their most recent game, the club carried a one-run lead into the late innings and let it get away on four late runs.
```
What BaseballOS noticed / observations:
```
(none)
```
Evidence:
```
- Starter: Brandon Woodruff, 5.2 IP, 84 pitches
- Largest lead: 1
- Bullpen entered in the 6th with a 1-run lead
- Turning point: 10th inning
- Late runs allowed: 4
```
Exact rendered text:
```
Bullpen note: Lead surrendered late

After their most recent game, the club carried a one-run lead into the late innings and let it get away on four late runs.

Evidence:
- Starter: Brandon Woodruff, 5.2 IP, 84 pitches
- Largest lead: 1
- Bullpen entered in the 6th with a 1-run lead
- Turning point: 10th inning
- Late runs allowed: 4
```
