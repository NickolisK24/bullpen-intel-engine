# Context Explanation Editorial Review Corpus - E2D-5 Context Explanation Final Copy Polish

Read-only export of current Pitcher Context and Team Context explanation copy for E2 Editorial Voice review.

## Export Metadata

```json
{
  "artifact": "artifacts/context_explanation_editorial_review_E2D5.md",
  "before_after_summary": {
    "current_banned_language_status": "pass",
    "current_capitalization_sentence_status": "pass",
    "current_circular_meta_status": "pass",
    "current_disclaimer_repetition_status": "pass",
    "current_raw_count_formula_status": "pass",
    "current_retired_phrase_status": "pass",
    "current_weighting_scoring_status": "pass",
    "disclaimer_preservation_status": "pass",
    "prior_artifact": "artifacts\\context_explanation_editorial_review_E2D1.md",
    "prior_artifact_string_counts": {
      "circular_meta_examples": 93,
      "formula_term_examples": 118,
      "raw_arithmetic_examples": 33
    }
  },
  "capitalization_sentence_scan": {
    "patterns": {
      "lowercase_sentence_start": "(?<=[.!?])\\s+([a-z])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "data_notes": [
    "Deterministic fixture examples use existing backend test fixture shapes and production helper paths; they are labeled separately from stored data."
  ],
  "disclaimer_repetition_scan": {
    "disclaimer": "This is a data-limited note, not a statement about injury status or manager intent.",
    "per_card_limit": 1,
    "scope": "Team bullpen shape rendered public copy",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "example_count": 43,
  "generated_at": "2026-06-30T10:38:30.110487",
  "generation_path_used": [
    "services.context_explanation_editorial_review.build_context_explanation_editorial_review",
    "api.bullpen.get_pitcher_fatigue",
    "api.explanations._availability_explanation_payload",
    "services.pitcher_public_labels.build_pitcher_labels",
    "api.bullpen._build_team_board",
    "services.team_bullpen_shape.build_team_bullpen_shape",
    "api.explanations._team_readiness_payload_from_request",
    "explanations.readiness.serialize_readiness_explanation"
  ],
  "review_label": "E2D-5 Context Explanation Final Copy Polish",
  "source_mode": "current stored DB data first; deterministic fixtures fill uncaptured healthy-state categories; exporter starts no sync",
  "team_ids_reviewed": [
    108,
    109,
    110,
    111,
    112,
    113,
    114,
    115,
    116,
    117,
    118,
    119,
    120,
    121,
    133,
    134,
    135,
    136,
    137,
    138,
    139,
    140,
    141,
    142,
    143,
    144,
    145,
    146,
    147,
    158
  ],
  "weighting_scoring_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "raw score",
      "scoring weight",
      "weighted pressure"
    ],
    "violation_count": 0,
    "violations": []
  }
}
```

## Inventoried Context Surfaces

```json
[
  {
    "helpers": [
      "services.availability.classify_availability",
      "services.availability_explanations",
      "services.roster_status"
    ],
    "source_path": "api.bullpen.get_pitcher_fatigue",
    "surface": "Pitcher Context modal/detail route"
  },
  {
    "helpers": [
      "explanations.availability.serialize_availability_explanation",
      "services.availability.classify_availability"
    ],
    "source_path": "api.explanations._availability_explanation_payload",
    "surface": "Pitcher V4 availability explanation"
  },
  {
    "helpers": [
      "services.pitcher_public_labels._role_label",
      "services.pitcher_public_labels._read_label"
    ],
    "source_path": "services.pitcher_public_labels.build_pitcher_labels",
    "surface": "Pitcher public role/read labels"
  },
  {
    "helpers": [
      "services.bullpen_board.build_board_payload",
      "services.bullpen_board.build_team_context"
    ],
    "source_path": "api.bullpen._build_team_board",
    "surface": "Team bullpen board context"
  },
  {
    "helpers": [
      "services.team_bullpen_shape._trust_availability",
      "services.team_bullpen_shape._clean_options",
      "services.team_bullpen_shape._bullpen_pressure",
      "services.team_bullpen_shape._workload_concentration",
      "services.team_bullpen_shape._depth_safety"
    ],
    "source_path": "services.team_bullpen_shape.build_team_bullpen_shape",
    "surface": "Team bullpen shape explanations"
  },
  {
    "helpers": [
      "team_operations.assemble_bullpen_readiness",
      "explanations.readiness.serialize_readiness_explanation"
    ],
    "source_path": "api.explanations._team_readiness_payload_from_request",
    "surface": "Team Operations readiness V4 explanation"
  }
]
```

## Coverage And Missing Categories

```json
{
  "board_card_groups_found": {
    "Available": 13,
    "Avoid": 2,
    "Limited": 5,
    "Monitor": 10,
    "Unavailable": 2
  },
  "examples_by_source": {
    "deterministic fixture example": 18,
    "stored-data example": 25
  },
  "examples_exported": 43,
  "fixture_backed_examples": 18,
  "missing_categories": {},
  "pitcher_availability_statuses_found": [
    "Available",
    "Avoid",
    "Limited",
    "Monitor",
    "Unavailable"
  ],
  "pitcher_context_statuses_found": [
    "Available",
    "Avoid",
    "Limited",
    "Monitor",
    "Unavailable"
  ],
  "read_labels_found": [
    "Limited Read",
    "Rest-Restricted",
    "Rested",
    "Unavailable",
    "Watch Arm"
  ],
  "role_labels_found": [
    "Bridge Arm",
    "Coverage Arm",
    "Depth Arm",
    "Limited Read",
    "Trust Arm"
  ],
  "stored_data_examples": 25,
  "team_readiness_states_found": [
    "data_limited",
    "operationally_constrained",
    "operationally_stable",
    "operationally_stressed",
    "refused"
  ],
  "team_shape_read_labels_found": [
    "Elevated Late-Inning Pressure",
    "Healthy Rested Bullpen",
    "Heavily Concentrated Workload",
    "High Late-Inning Pressure",
    "Limited Coverage Safety",
    "Limited Depth Safety",
    "No Workload Concentration",
    "Stable Coverage Safety",
    "Stable Late-Inning Availability",
    "Thin Coverage Safety",
    "Thin Depth Safety",
    "Thin Late-Inning Availability",
    "Thin Rested Bullpen",
    "Very Thin Rested Bullpen"
  ]
}
```

## Before / After Summary

```json
{
  "current_banned_language_status": "pass",
  "current_capitalization_sentence_status": "pass",
  "current_circular_meta_status": "pass",
  "current_disclaimer_repetition_status": "pass",
  "current_raw_count_formula_status": "pass",
  "current_retired_phrase_status": "pass",
  "current_weighting_scoring_status": "pass",
  "disclaimer_preservation_status": "pass",
  "prior_artifact": "artifacts\\context_explanation_editorial_review_E2D1.md",
  "prior_artifact_string_counts": {
    "circular_meta_examples": 93,
    "formula_term_examples": 118,
    "raw_arithmetic_examples": 33
  }
}
```

## Editorial Banned-Language Scan

Status: pass - no banned language violations found.

## Retired Phrase Scan

Status: pass - no retired phrase violations found.

## Raw-Count / Formula Scan

Status: pass - no raw-count or formula violations found.

## Weighting / Scoring Narration Scan

Status: pass - no weighting or scoring narration violations found.

## Circular-Meta Scan

Status: pass - no circular-meta violations found.

## Capitalization / Sentence-Join Scan

Status: pass - no lowercase sentence-start violations found.

## Disclaimer Repetition Scan

Status: pass - no repeated disclaimer violations found.

## Disclaimer Preservation Check

```json
{
  "missing_disclaimers": [],
  "required_disclaimers": [
    "Readiness is based on public workload data, not private team information.",
    "Readiness is not injury or medical information.",
    "Readiness is not a performance forecast.",
    "Manager intent and bullpen warm-up state are not available."
  ],
  "scope": "Team Operations readiness V4 rendered public copy",
  "status": "pass"
}
```

## Fallbacks Found

```json
{
  "fallback_counts": {
    "data_limited": 5,
    "data_stale": 1,
    "freshness_stale": 1,
    "limited_role_context": 6,
    "rendered": 30
  },
  "fallback_rows": [
    {
      "fallback_status": "limited_role_context",
      "pitcher": "Brent Suter",
      "status": "Available",
      "surface_name": "Pitcher public role/read labels",
      "team": "Los Angeles Angels (LAA, 108)"
    },
    {
      "fallback_status": "freshness_stale",
      "pitcher": "Caden Dana",
      "status": "Monitor",
      "surface_name": "Pitcher V4 availability explanation",
      "team": "Los Angeles Angels (LAA, 108)"
    },
    {
      "fallback_status": "data_stale",
      "pitcher": "Caden Dana",
      "status": "Unavailable",
      "surface_name": "Pitcher Context modal/detail route",
      "team": "Los Angeles Angels (LAA, 108)"
    },
    {
      "fallback_status": "limited_role_context",
      "pitcher": "Caden Dana",
      "status": "Unavailable",
      "surface_name": "Pitcher public role/read labels",
      "team": "Los Angeles Angels (LAA, 108)"
    },
    {
      "fallback_status": "limited_role_context",
      "pitcher": "José Fermin",
      "status": "Monitor",
      "surface_name": "Pitcher public role/read labels",
      "team": "Los Angeles Angels (LAA, 108)"
    },
    {
      "fallback_status": "limited_role_context",
      "pitcher": "Kirby Yates",
      "status": "Limited",
      "surface_name": "Pitcher public role/read labels",
      "team": "Los Angeles Angels (LAA, 108)"
    },
    {
      "fallback_status": "data_limited",
      "pitcher": null,
      "status": "data_limited",
      "surface_name": "Team Operations readiness V4 explanation",
      "team": "Los Angeles Angels (LAA, 108)"
    },
    {
      "fallback_status": "data_limited",
      "pitcher": null,
      "status": "elevated",
      "surface_name": "Team Operations readiness V4 explanation",
      "team": "Los Angeles Angels (LAA, 108)"
    },
    {
      "fallback_status": "data_limited",
      "pitcher": null,
      "status": "workload:partial;handedness:covered",
      "surface_name": "Team Operations readiness V4 explanation",
      "team": "Los Angeles Angels (LAA, 108)"
    },
    {
      "fallback_status": "data_limited",
      "pitcher": null,
      "status": "current",
      "surface_name": "Team Operations readiness V4 explanation",
      "team": "Los Angeles Angels (LAA, 108)"
    },
    {
      "fallback_status": "data_limited",
      "pitcher": null,
      "status": "limited",
      "surface_name": "Team Operations readiness V4 explanation",
      "team": "Los Angeles Angels (LAA, 108)"
    },
    {
      "fallback_status": "limited_role_context",
      "pitcher": "Deterministic fixture pitcher - Limited Read",
      "status": "Unavailable",
      "surface_name": "Pitcher public role/read labels",
      "team": "Deterministic Context Fixture (FIX, fixture-context)"
    },
    {
      "fallback_status": "limited_role_context",
      "pitcher": "Deterministic fixture pitcher - Limited Read label",
      "status": "Monitor",
      "surface_name": "Pitcher public role/read labels",
      "team": "Deterministic Context Fixture (FIX, fixture-context)"
    }
  ]
}
```

## Surface Summary

```json
{
  "examples_by_surface": {
    "Pitcher Context modal/detail route": 6,
    "Pitcher V4 availability explanation": 5,
    "Pitcher public role/read labels": 10,
    "Team Operations readiness V4 explanation": 9,
    "Team bullpen board card labels": 5,
    "Team bullpen board context": 4,
    "Team bullpen shape explanations": 4
  },
  "statuses_by_surface": {
    "Pitcher Context modal/detail route": {
      "Available": 1,
      "Avoid": 1,
      "Limited": 1,
      "Monitor": 1,
      "Unavailable": 2
    },
    "Pitcher V4 availability explanation": {
      "Available": 1,
      "Avoid": 1,
      "Limited": 1,
      "Monitor": 1,
      "Unavailable": 1
    },
    "Pitcher public role/read labels": {
      "Available": 2,
      "Avoid": 1,
      "Limited": 2,
      "Monitor": 3,
      "Unavailable": 2
    },
    "Team Operations readiness V4 explanation": {
      "current": 1,
      "data_limited": 1,
      "elevated": 1,
      "limited": 1,
      "operationally_constrained": 1,
      "operationally_stable": 1,
      "operationally_stressed": 1,
      "refused": 1,
      "workload:partial;handedness:covered": 1
    },
    "Team bullpen board card labels": {
      "Available": 1,
      "Avoid": 1,
      "Limited": 1,
      "Monitor": 1,
      "Unavailable": 1
    },
    "Team bullpen board context": {
      "elevated": 2,
      "manageable": 1,
      "monitoring": 1
    },
    "Team bullpen shape explanations": {
      "team_shape": 4
    }
  }
}
```

## Context Explanation Examples

### Example 1: Pitcher V4 availability explanation

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "capitalization_sentence_scan": {
    "patterns": {
      "lowercase_sentence_start": "(?<=[.!?])\\s+([a-z])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "circular_meta_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "explanation confidence mirrors",
      "confidence mirrors",
      "visibility reflects existing availability confidence",
      "governed availability evidence",
      "state reflects",
      "explained state",
      "trust metadata",
      "readiness explanation confidence"
    ],
    "violation_count": 0,
    "violations": []
  },
  "disclaimer_repetition_scan": {
    "disclaimer": "This is a data-limited note, not a statement about injury status or manager intent.",
    "per_card_limit": 1,
    "scope": "Team bullpen shape rendered public copy",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "example_source": "stored-data example",
  "fallback_status": "rendered",
  "pitcher": "Brent Suter",
  "raw_count_formula_scan": {
    "patterns": {
      "jargon_coupled_raw_count": "(?<![\\w-])\\d+\\s+of\\s+\\d+\\s+(?:trust|bridge|coverage|depth)\\s+arms?\\b",
      "parenthetical_raw_basis": "\\(\\s*\\d+\\s+of\\s+\\d+\\s*\\)",
      "parenthetical_unknown_formula": "\\([^)]*\\bunknown\\b[^)]*\\)",
      "raw_empty_arithmetic": "(?<![\\w-])\\d+\\s+of\\s+\\d+(?![\\w-])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "length option",
      "length options",
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "classified available",
      "0 of 0",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "trust metadata",
      "explained state",
      "availability read",
      "bullpen planning read",
      "explanation confidence mirrors",
      "confidence mirrors",
      "governed availability evidence",
      "state reflects",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "role_or_classification": {
    "scope": "availability_state",
    "subject_type": "pitcher"
  },
  "source_path": "api.explanations._availability_explanation_payload -> explanations.availability.serialize_availability_explanation",
  "status": "Available",
  "surface_name": "Pitcher V4 availability explanation",
  "team": "Los Angeles Angels (LAA, 108)",
  "weighting_scoring_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "raw score",
      "scoring weight",
      "weighted pressure"
    ],
    "violation_count": 0,
    "violations": []
  }
}
```

Rendered public copy:
```
He has no workload from yesterday in the stored data.
No injury data available
No team-reported availability data available
The stored workload data is current enough for this pitcher note.
```

Structured fields used:

```json
{
  "confidence": {
    "level": "high",
    "summary": "The public workload record is current enough for this note."
  },
  "freshness": {
    "data_through": "2026-06-26",
    "freshness_failure": null,
    "last_sync_at": null,
    "source_updated_at": "2026-06-30",
    "status": "current",
    "summary": "The stored workload data is current enough for this pitcher note."
  },
  "governance": {
    "advice_scope": "none",
    "decision_scope": "explanation_only",
    "prediction_made": false,
    "ranking_applied": false,
    "recommendation_made": false,
    "selection_made": false
  },
  "primary_reason_codes": [],
  "scope": "availability_state",
  "state_explained": "Available",
  "subject_id": "2",
  "subject_type": "pitcher",
  "trust": {
    "certification_status": "complete",
    "contract": "availability_engine_v1",
    "source": "availability_engine_v1",
    "status": "trusted",
    "summary": "The public workload record is strong enough for this note.",
    "trust_failure": null
  }
}
```

Evidence sections:

```json
{
  "limitations": [
    {
      "affected_scopes": [
        "availability_state"
      ],
      "limitation_type": "insufficient_context",
      "severity": "informational",
      "summary": "No injury data available"
    },
    {
      "affected_scopes": [
        "availability_state"
      ],
      "limitation_type": "insufficient_context",
      "severity": "informational",
      "summary": "No team-reported availability data available"
    }
  ],
  "primary_reasons": [],
  "supporting_evidence": [
    {
      "evidence_type": "availability_status",
      "impact": "explains_availability_state",
      "label": "Availability status",
      "source": "availability_engine_v1",
      "unit": "status",
      "value": "Available"
    },
    {
      "evidence_type": "availability_confidence",
      "impact": "explains_confidence_boundary",
      "label": "Availability confidence",
      "source": "availability_engine_v1",
      "unit": "level",
      "value": "high"
    },
    {
      "evidence_type": "availability_data_state",
      "impact": "explains_freshness_boundary",
      "label": "Availability data state",
      "source": "availability_engine_v1",
      "unit": "state",
      "value": "fresh"
    },
    {
      "evidence_type": "availability_fatigue_score",
      "impact": "explains_availability_state",
      "label": "Recent workload index",
      "source": "availability_engine_v1",
      "unit": "index",
      "value": 20.5
    },
    {
      "evidence_type": "availability_pitches_yesterday",
      "impact": "explains_availability_state",
      "label": "Pitches yesterday",
      "source": "availability_engine_v1",
      "unit": "pitches",
      "value": 0
    },
    {
      "evidence_type": "availability_pitches_last_3_days",
      "impact": "explains_availability_state",
      "label": "Pitches in 3 days",
      "source": "availability_engine_v1",
      "unit": "pitches",
      "value": 0
    },
    {
      "evidence_type": "availability_pitches_last_5_days",
      "impact": "explains_availability_state",
      "label": "Pitches in 5 days",
      "source": "availability_engine_v1",
      "unit": "pitches",
      "value": 52
    },
    {
      "evidence_type": "availability_appearances_last_3_days",
      "impact": "explains_availability_state",
      "label": "Appearances in 3 days",
      "source": "availability_engine_v1",
      "unit": "appearances",
      "value": 0
    },
    {
      "evidence_type": "availability_appearances_last_5_days",
      "impact": "explains_availability_state",
      "label": "Appearances in 5 days",
      "source": "availability_engine_v1",
      "unit": "appearances",
      "value": 1
    },
    {
      "evidence_type": "availability_days_rest",
      "impact": "explains_availability_state",
      "label": "Days of rest",
      "source": "availability_engine_v1",
      "unit": "days",
      "value": 4
    }
  ]
}
```

### Example 2: Pitcher Context modal/detail route

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "capitalization_sentence_scan": {
    "patterns": {
      "lowercase_sentence_start": "(?<=[.!?])\\s+([a-z])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "circular_meta_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "explanation confidence mirrors",
      "confidence mirrors",
      "visibility reflects existing availability confidence",
      "governed availability evidence",
      "state reflects",
      "explained state",
      "trust metadata",
      "readiness explanation confidence"
    ],
    "violation_count": 0,
    "violations": []
  },
  "disclaimer_repetition_scan": {
    "disclaimer": "This is a data-limited note, not a statement about injury status or manager intent.",
    "per_card_limit": 1,
    "scope": "Team bullpen shape rendered public copy",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "example_source": "stored-data example",
  "fallback_status": "rendered",
  "pitcher": "Brent Suter",
  "raw_count_formula_scan": {
    "patterns": {
      "jargon_coupled_raw_count": "(?<![\\w-])\\d+\\s+of\\s+\\d+\\s+(?:trust|bridge|coverage|depth)\\s+arms?\\b",
      "parenthetical_raw_basis": "\\(\\s*\\d+\\s+of\\s+\\d+\\s*\\)",
      "parenthetical_unknown_formula": "\\([^)]*\\bunknown\\b[^)]*\\)",
      "raw_empty_arithmetic": "(?<![\\w-])\\d+\\s+of\\s+\\d+(?![\\w-])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "length option",
      "length options",
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "classified available",
      "0 of 0",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "trust metadata",
      "explained state",
      "availability read",
      "bullpen planning read",
      "explanation confidence mirrors",
      "confidence mirrors",
      "governed availability evidence",
      "state reflects",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "role_or_classification": {
    "confidence": "high",
    "data_state": "fresh",
    "roster_status": "Active MLB"
  },
  "source_path": "api.bullpen.get_pitcher_fatigue",
  "status": "Available",
  "surface_name": "Pitcher Context modal/detail route",
  "team": "Los Angeles Angels (LAA, 108)",
  "weighting_scoring_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "raw score",
      "scoring weight",
      "weighted pressure"
    ],
    "violation_count": 0,
    "violations": []
  }
}
```

Rendered public copy:
```
Available
No injury data available
No team-reported availability data available
Active MLB
Current baseball data through 2026-06-29.
```

Structured fields used:

```json
{
  "availability": {
    "availability_status": "Available",
    "confidence": "high",
    "data_state": "fresh",
    "inputs": {
      "appearances_last_3_days": 0,
      "appearances_last_5_days": 1,
      "back_to_back": false,
      "days_rest": 4,
      "fatigue_risk_level": "LOW",
      "fatigue_score": 20.5,
      "four_in_five": false,
      "freshness_state": "fresh",
      "latest_game_date": "2026-06-26",
      "pitches_last_3_days": 0,
      "pitches_last_5_days": 52,
      "pitches_yesterday": 0,
      "reference_date": "2026-06-30",
      "three_in_four": false
    },
    "limitations": [
      "No injury data available",
      "No team-reported availability data available"
    ],
    "reasons": []
  },
  "freshness": {
    "data_age_days": 1,
    "data_through": "2026-06-29",
    "freshness_state": "current",
    "label": "Current baseball data through 2026-06-29.",
    "limitations": []
  },
  "roster_status": {
    "confidence": "high",
    "label": "Active MLB",
    "limitations": [],
    "source": "mlb_stats_api:roster_sync:active",
    "status": "ACTIVE"
  },
  "workload_signal": {
    "availability_status": "Available",
    "confidence": "high",
    "data_state": "fresh",
    "inputs": {
      "appearances_last_3_days": 0,
      "appearances_last_5_days": 1,
      "back_to_back": false,
      "days_rest": 4,
      "fatigue_risk_level": "LOW",
      "fatigue_score": 20.5,
      "four_in_five": false,
      "freshness_state": "fresh",
      "latest_game_date": "2026-06-26",
      "pitches_last_3_days": 0,
      "pitches_last_5_days": 52,
      "pitches_yesterday": 0,
      "reference_date": "2026-06-30",
      "three_in_four": false
    },
    "limitations": [
      "No injury data available",
      "No team-reported availability data available"
    ],
    "reasons": []
  }
}
```

Evidence sections:

```json
{
  "fatigue_trend_points": 120,
  "last_workload_appearance": {
    "game_date": "2026-06-26",
    "pitches": 52
  },
  "recent_logs_reviewed": 6
}
```

### Example 3: Pitcher public role/read labels

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "capitalization_sentence_scan": {
    "patterns": {
      "lowercase_sentence_start": "(?<=[.!?])\\s+([a-z])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "circular_meta_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "explanation confidence mirrors",
      "confidence mirrors",
      "visibility reflects existing availability confidence",
      "governed availability evidence",
      "state reflects",
      "explained state",
      "trust metadata",
      "readiness explanation confidence"
    ],
    "violation_count": 0,
    "violations": []
  },
  "disclaimer_repetition_scan": {
    "disclaimer": "This is a data-limited note, not a statement about injury status or manager intent.",
    "per_card_limit": 1,
    "scope": "Team bullpen shape rendered public copy",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "example_source": "stored-data example",
  "fallback_status": "limited_role_context",
  "pitcher": "Brent Suter",
  "raw_count_formula_scan": {
    "patterns": {
      "jargon_coupled_raw_count": "(?<![\\w-])\\d+\\s+of\\s+\\d+\\s+(?:trust|bridge|coverage|depth)\\s+arms?\\b",
      "parenthetical_raw_basis": "\\(\\s*\\d+\\s+of\\s+\\d+\\s*\\)",
      "parenthetical_unknown_formula": "\\([^)]*\\bunknown\\b[^)]*\\)",
      "raw_empty_arithmetic": "(?<![\\w-])\\d+\\s+of\\s+\\d+(?![\\w-])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "length option",
      "length options",
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "classified available",
      "0 of 0",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "trust metadata",
      "explained state",
      "availability read",
      "bullpen planning read",
      "explanation confidence mirrors",
      "confidence mirrors",
      "governed availability evidence",
      "state reflects",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "role_or_classification": {
    "read": "Rested",
    "role": "Limited Read"
  },
  "source_path": "services.pitcher_public_labels.build_pitcher_labels",
  "status": "Available",
  "surface_name": "Pitcher public role/read labels",
  "team": "Los Angeles Angels (LAA, 108)",
  "weighting_scoring_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "raw score",
      "scoring weight",
      "weighted pressure"
    ],
    "violation_count": 0,
    "violations": []
  }
}
```

Rendered public copy:
```
Limited Read
Rested
```

Structured fields used:

```json
{
  "availability_confidence": "high",
  "availability_data_state": "fresh",
  "availability_status": "Available",
  "labels": {
    "read": {
      "key": "clean_option",
      "kind": "read",
      "label": "Rested",
      "source": "backend:availability_status"
    },
    "role": {
      "key": "limited_read",
      "kind": "role",
      "label": "Limited Read",
      "source": "backend:role_key:missing"
    }
  },
  "role_input": null,
  "roster_status": {
    "confidence": "high",
    "current_assignment_unresolved": false,
    "evidence": [
      "Stored roster status: Active MLB."
    ],
    "is_active_mlb": true,
    "is_authoritative": true,
    "is_inactive_context": false,
    "label": "Active MLB",
    "limitations": [],
    "raw_status": "ACTIVE",
    "raw_status_code": "A",
    "raw_status_description": "Active",
    "source": "mlb_stats_api:roster_sync:active",
    "status": "ACTIVE",
    "updated_at": "2026-06-30T10:00:04.993867"
  }
}
```

Evidence sections:

```json
{}
```

### Example 4: Pitcher V4 availability explanation

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "capitalization_sentence_scan": {
    "patterns": {
      "lowercase_sentence_start": "(?<=[.!?])\\s+([a-z])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "circular_meta_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "explanation confidence mirrors",
      "confidence mirrors",
      "visibility reflects existing availability confidence",
      "governed availability evidence",
      "state reflects",
      "explained state",
      "trust metadata",
      "readiness explanation confidence"
    ],
    "violation_count": 0,
    "violations": []
  },
  "disclaimer_repetition_scan": {
    "disclaimer": "This is a data-limited note, not a statement about injury status or manager intent.",
    "per_card_limit": 1,
    "scope": "Team bullpen shape rendered public copy",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "example_source": "stored-data example",
  "fallback_status": "freshness_stale",
  "pitcher": "Caden Dana",
  "raw_count_formula_scan": {
    "patterns": {
      "jargon_coupled_raw_count": "(?<![\\w-])\\d+\\s+of\\s+\\d+\\s+(?:trust|bridge|coverage|depth)\\s+arms?\\b",
      "parenthetical_raw_basis": "\\(\\s*\\d+\\s+of\\s+\\d+\\s*\\)",
      "parenthetical_unknown_formula": "\\([^)]*\\bunknown\\b[^)]*\\)",
      "raw_empty_arithmetic": "(?<![\\w-])\\d+\\s+of\\s+\\d+(?![\\w-])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "length option",
      "length options",
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "classified available",
      "0 of 0",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "trust metadata",
      "explained state",
      "availability read",
      "bullpen planning read",
      "explanation confidence mirrors",
      "confidence mirrors",
      "governed availability evidence",
      "state reflects",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "role_or_classification": {
    "scope": "availability_state",
    "subject_type": "pitcher"
  },
  "source_path": "api.explanations._availability_explanation_payload -> explanations.availability.serialize_availability_explanation",
  "status": "Monitor",
  "surface_name": "Pitcher V4 availability explanation",
  "team": "Los Angeles Angels (LAA, 108)",
  "weighting_scoring_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "raw score",
      "scoring weight",
      "weighted pressure"
    ],
    "violation_count": 0,
    "violations": []
  }
}
```

Rendered public copy:
```
BaseballOS is treating him as a monitor arm, but the stored workload data is stale.
Recent usage is enough for BaseballOS to treat him as a monitor arm.
A heavy recent stretch has the workload up.
The stored workload data is stale.
The public data is not strong enough for a fuller explanation.
No injury data available
No team-reported availability data available
Recent usage information is incomplete, so workload data must not be treated as current availability
Stored workload data is stale for this pitcher.
BaseballOS is keeping this note limited to the public workload evidence.
The read is limited because the stored workload data is stale.
BaseballOS is keeping this note limited because the stored workload data is stale.
The safest note stays limited until fresher workload data is available.
```

Structured fields used:

```json
{
  "confidence": {
    "level": "low",
    "summary": "The safest note stays limited until fresher workload data is available."
  },
  "freshness": {
    "data_through": "2025-09-27",
    "freshness_failure": "stale_workload_data",
    "last_sync_at": null,
    "source_updated_at": "2026-06-30",
    "status": "stale",
    "summary": "The read is limited because the stored workload data is stale."
  },
  "governance": {
    "advice_scope": "none",
    "decision_scope": "explanation_only",
    "prediction_made": false,
    "ranking_applied": false,
    "recommendation_made": false,
    "selection_made": false
  },
  "primary_reason_codes": [
    "AVAILABILITY_MONITOR_THRESHOLD_MET",
    "WORKLOAD_RECENT_USAGE_ELEVATED",
    "FRESHNESS_STALE_SOURCE",
    "TRUST_LIMITED"
  ],
  "scope": "availability_state",
  "state_explained": "Monitor",
  "subject_id": "3",
  "subject_type": "pitcher",
  "trust": {
    "certification_status": "complete",
    "contract": "availability_engine_v1",
    "source": "availability_engine_v1",
    "status": "limited",
    "summary": "BaseballOS is keeping this note limited because the stored workload data is stale.",
    "trust_failure": "stale_availability_evidence"
  }
}
```

Evidence sections:

```json
{
  "limitations": [
    {
      "affected_scopes": [
        "availability_state"
      ],
      "limitation_type": "stale_data",
      "severity": "degrades_confidence",
      "summary": "No injury data available"
    },
    {
      "affected_scopes": [
        "availability_state"
      ],
      "limitation_type": "stale_data",
      "severity": "degrades_confidence",
      "summary": "No team-reported availability data available"
    },
    {
      "affected_scopes": [
        "availability_state"
      ],
      "limitation_type": "stale_data",
      "severity": "degrades_confidence",
      "summary": "Recent usage information is incomplete, so workload data must not be treated as current availability"
    },
    {
      "affected_scopes": [
        "availability_state"
      ],
      "limitation_type": "stale_data",
      "severity": "degrades_confidence",
      "summary": "Stored workload data is stale for this pitcher."
    },
    {
      "affected_scopes": [
        "availability_state"
      ],
      "limitation_type": "limited_confidence",
      "severity": "limits_confidence",
      "summary": "BaseballOS is keeping this note limited to the public workload evidence."
    }
  ],
  "primary_reasons": [
    {
      "code": "AVAILABILITY_MONITOR_THRESHOLD_MET",
      "label": "Monitor threshold met",
      "scope": "availability_state",
      "summary": "Recent usage is enough for BaseballOS to treat him as a monitor arm."
    },
    {
      "code": "WORKLOAD_RECENT_USAGE_ELEVATED",
      "label": "Recent usage elevated",
      "scope": "workload_state",
      "summary": "A heavy recent stretch has the workload up."
    },
    {
      "code": "FRESHNESS_STALE_SOURCE",
      "label": "Source freshness stale",
      "scope": "freshness_state",
      "summary": "The stored workload data is stale."
    },
    {
      "code": "TRUST_LIMITED",
      "label": "Trust limited",
      "scope": "trust_state",
      "summary": "The public data is not strong enough for a fuller explanation."
    }
  ],
  "supporting_evidence": [
    {
      "evidence_type": "availability_status",
      "impact": "explains_availability_state",
      "label": "Availability status",
      "source": "availability_engine_v1",
      "unit": "status",
      "value": "Monitor"
    },
    {
      "evidence_type": "availability_confidence",
      "impact": "explains_confidence_boundary",
      "label": "Availability confidence",
      "source": "availability_engine_v1",
      "unit": "level",
      "value": "low"
    },
    {
      "evidence_type": "availability_data_state",
      "impact": "explains_freshness_boundary",
      "label": "Availability data state",
      "source": "availability_engine_v1",
      "unit": "state",
      "value": "stale"
    },
    {
      "evidence_type": "availability_fatigue_score",
      "impact": "explains_availability_state",
      "label": "Recent workload index",
      "source": "availability_engine_v1",
      "unit": "index",
      "value": 54.2
    },
    {
      "evidence_type": "availability_pitches_yesterday",
      "impact": "explains_availability_state",
      "label": "Pitches yesterday",
      "source": "availability_engine_v1",
      "unit": "pitches",
      "value": 0
    },
    {
      "evidence_type": "availability_pitches_last_3_days",
      "impact": "explains_availability_state",
      "label": "Pitches in 3 days",
      "source": "availability_engine_v1",
      "unit": "pitches",
      "value": 0
    },
    {
      "evidence_type": "availability_pitches_last_5_days",
      "impact": "explains_availability_state",
      "label": "Pitches in 5 days",
      "source": "availability_engine_v1",
      "unit": "pitches",
      "value": 0
    },
    {
      "evidence_type": "availability_appearances_last_3_days",
      "impact": "explains_availability_state",
      "label": "Appearances in 3 days",
      "source": "availability_engine_v1",
      "unit": "appearances",
      "value": 0
    },
    {
      "evidence_type": "availability_appearances_last_5_days",
      "impact": "explains_availability_state",
      "label": "Appearances in 5 days",
      "source": "availability_engine_v1",
      "unit": "appearances",
      "value": 0
    },
    {
      "evidence_type": "availability_days_rest",
      "impact": "explains_availability_state",
      "label": "Days of rest",
      "source": "availability_engine_v1",
      "unit": "days",
      "value": 276
    }
  ]
}
```

### Example 5: Pitcher Context modal/detail route

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "capitalization_sentence_scan": {
    "patterns": {
      "lowercase_sentence_start": "(?<=[.!?])\\s+([a-z])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "circular_meta_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "explanation confidence mirrors",
      "confidence mirrors",
      "visibility reflects existing availability confidence",
      "governed availability evidence",
      "state reflects",
      "explained state",
      "trust metadata",
      "readiness explanation confidence"
    ],
    "violation_count": 0,
    "violations": []
  },
  "disclaimer_repetition_scan": {
    "disclaimer": "This is a data-limited note, not a statement about injury status or manager intent.",
    "per_card_limit": 1,
    "scope": "Team bullpen shape rendered public copy",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "example_source": "stored-data example",
  "fallback_status": "data_stale",
  "pitcher": "Caden Dana",
  "raw_count_formula_scan": {
    "patterns": {
      "jargon_coupled_raw_count": "(?<![\\w-])\\d+\\s+of\\s+\\d+\\s+(?:trust|bridge|coverage|depth)\\s+arms?\\b",
      "parenthetical_raw_basis": "\\(\\s*\\d+\\s+of\\s+\\d+\\s*\\)",
      "parenthetical_unknown_formula": "\\([^)]*\\bunknown\\b[^)]*\\)",
      "raw_empty_arithmetic": "(?<![\\w-])\\d+\\s+of\\s+\\d+(?![\\w-])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "length option",
      "length options",
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "classified available",
      "0 of 0",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "trust metadata",
      "explained state",
      "availability read",
      "bullpen planning read",
      "explanation confidence mirrors",
      "confidence mirrors",
      "governed availability evidence",
      "state reflects",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "role_or_classification": {
    "confidence": "high",
    "data_state": "stale",
    "roster_status": "40-Man (not active)"
  },
  "source_path": "api.bullpen.get_pitcher_fatigue",
  "status": "Unavailable",
  "surface_name": "Pitcher Context modal/detail route",
  "team": "Los Angeles Angels (LAA, 108)",
  "weighting_scoring_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "raw score",
      "scoring weight",
      "weighted pressure"
    ],
    "violation_count": 0,
    "violations": []
  }
}
```

Rendered public copy:
```
Unavailable
Roster status: 40-Man (not active).
Latest workload data is outside the 14-day freshness window
No injury data available
No team-reported availability data available
Recent usage information is incomplete, so workload data must not be treated as current availability
Unavailable due to roster status; not available for bullpen planning.
Monitor
40-Man (not active)
Current baseball data through 2026-06-29.
```

Structured fields used:

```json
{
  "availability": {
    "availability_status": "Unavailable",
    "confidence": "high",
    "data_state": "stale",
    "inputs": {
      "appearances_last_3_days": 0,
      "appearances_last_5_days": 0,
      "back_to_back": false,
      "days_rest": 276,
      "fatigue_risk_level": "HIGH",
      "fatigue_score": 54.2,
      "four_in_five": false,
      "freshness_state": "stale",
      "latest_game_date": "2025-09-27",
      "pitches_last_3_days": 0,
      "pitches_last_5_days": 0,
      "pitches_yesterday": 0,
      "reference_date": "2026-06-30",
      "three_in_four": false
    },
    "limitations": [
      "No injury data available",
      "No team-reported availability data available",
      "Recent usage information is incomplete, so workload data must not be treated as current availability",
      "Unavailable due to roster status; not available for bullpen planning."
    ],
    "reasons": [
      "Roster status: 40-Man (not active).",
      "Latest workload data is outside the 14-day freshness window"
    ]
  },
  "freshness": {
    "data_age_days": 1,
    "data_through": "2026-06-29",
    "freshness_state": "current",
    "label": "Current baseball data through 2026-06-29.",
    "limitations": []
  },
  "roster_status": {
    "confidence": "high",
    "label": "40-Man (not active)",
    "limitations": [],
    "source": "mlb_stats_api:roster_sync:40Man",
    "status": "40_MAN_ONLY"
  },
  "workload_signal": {
    "availability_status": "Monitor",
    "confidence": "low",
    "data_state": "stale",
    "inputs": {
      "appearances_last_3_days": 0,
      "appearances_last_5_days": 0,
      "back_to_back": false,
      "days_rest": 276,
      "fatigue_risk_level": "HIGH",
      "fatigue_score": 54.2,
      "four_in_five": false,
      "freshness_state": "stale",
      "latest_game_date": "2025-09-27",
      "pitches_last_3_days": 0,
      "pitches_last_5_days": 0,
      "pitches_yesterday": 0,
      "reference_date": "2026-06-30",
      "three_in_four": false
    },
    "limitations": [
      "No injury data available",
      "No team-reported availability data available",
      "Recent usage information is incomplete, so workload data must not be treated as current availability"
    ],
    "reasons": [
      "Latest workload data is outside the 14-day freshness window"
    ]
  }
}
```

Evidence sections:

```json
{
  "fatigue_trend_points": 1,
  "last_workload_appearance": {
    "game_date": "2025-09-27",
    "pitches": 93
  },
  "recent_logs_reviewed": 3
}
```

### Example 6: Pitcher public role/read labels

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "capitalization_sentence_scan": {
    "patterns": {
      "lowercase_sentence_start": "(?<=[.!?])\\s+([a-z])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "circular_meta_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "explanation confidence mirrors",
      "confidence mirrors",
      "visibility reflects existing availability confidence",
      "governed availability evidence",
      "state reflects",
      "explained state",
      "trust metadata",
      "readiness explanation confidence"
    ],
    "violation_count": 0,
    "violations": []
  },
  "disclaimer_repetition_scan": {
    "disclaimer": "This is a data-limited note, not a statement about injury status or manager intent.",
    "per_card_limit": 1,
    "scope": "Team bullpen shape rendered public copy",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "example_source": "stored-data example",
  "fallback_status": "limited_role_context",
  "pitcher": "Caden Dana",
  "raw_count_formula_scan": {
    "patterns": {
      "jargon_coupled_raw_count": "(?<![\\w-])\\d+\\s+of\\s+\\d+\\s+(?:trust|bridge|coverage|depth)\\s+arms?\\b",
      "parenthetical_raw_basis": "\\(\\s*\\d+\\s+of\\s+\\d+\\s*\\)",
      "parenthetical_unknown_formula": "\\([^)]*\\bunknown\\b[^)]*\\)",
      "raw_empty_arithmetic": "(?<![\\w-])\\d+\\s+of\\s+\\d+(?![\\w-])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "length option",
      "length options",
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "classified available",
      "0 of 0",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "trust metadata",
      "explained state",
      "availability read",
      "bullpen planning read",
      "explanation confidence mirrors",
      "confidence mirrors",
      "governed availability evidence",
      "state reflects",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "role_or_classification": {
    "read": "Unavailable",
    "role": "Limited Read"
  },
  "source_path": "services.pitcher_public_labels.build_pitcher_labels",
  "status": "Unavailable",
  "surface_name": "Pitcher public role/read labels",
  "team": "Los Angeles Angels (LAA, 108)",
  "weighting_scoring_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "raw score",
      "scoring weight",
      "weighted pressure"
    ],
    "violation_count": 0,
    "violations": []
  }
}
```

Rendered public copy:
```
Limited Read
Unavailable
```

Structured fields used:

```json
{
  "availability_confidence": "high",
  "availability_data_state": "stale",
  "availability_status": "Unavailable",
  "labels": {
    "read": {
      "key": "unavailable",
      "kind": "read",
      "label": "Unavailable",
      "source": "backend:unavailable_status"
    },
    "role": {
      "key": "limited_read",
      "kind": "role",
      "label": "Limited Read",
      "source": "backend:role_key:missing"
    }
  },
  "role_input": null,
  "roster_status": {
    "confidence": "high",
    "current_assignment_unresolved": false,
    "evidence": [
      "Stored roster status: 40-Man (not active)."
    ],
    "is_active_mlb": false,
    "is_authoritative": true,
    "is_inactive_context": true,
    "label": "40-Man (not active)",
    "limitations": [],
    "raw_status": "40_MAN_ONLY",
    "raw_status_code": null,
    "raw_status_description": null,
    "source": "mlb_stats_api:roster_sync:40Man",
    "status": "40_MAN_ONLY",
    "updated_at": "2026-06-30T10:00:04.993867"
  }
}
```

Evidence sections:

```json
{}
```

### Example 7: Pitcher public role/read labels

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "capitalization_sentence_scan": {
    "patterns": {
      "lowercase_sentence_start": "(?<=[.!?])\\s+([a-z])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "circular_meta_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "explanation confidence mirrors",
      "confidence mirrors",
      "visibility reflects existing availability confidence",
      "governed availability evidence",
      "state reflects",
      "explained state",
      "trust metadata",
      "readiness explanation confidence"
    ],
    "violation_count": 0,
    "violations": []
  },
  "disclaimer_repetition_scan": {
    "disclaimer": "This is a data-limited note, not a statement about injury status or manager intent.",
    "per_card_limit": 1,
    "scope": "Team bullpen shape rendered public copy",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "example_source": "stored-data example",
  "fallback_status": "limited_role_context",
  "pitcher": "José Fermin",
  "raw_count_formula_scan": {
    "patterns": {
      "jargon_coupled_raw_count": "(?<![\\w-])\\d+\\s+of\\s+\\d+\\s+(?:trust|bridge|coverage|depth)\\s+arms?\\b",
      "parenthetical_raw_basis": "\\(\\s*\\d+\\s+of\\s+\\d+\\s*\\)",
      "parenthetical_unknown_formula": "\\([^)]*\\bunknown\\b[^)]*\\)",
      "raw_empty_arithmetic": "(?<![\\w-])\\d+\\s+of\\s+\\d+(?![\\w-])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "length option",
      "length options",
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "classified available",
      "0 of 0",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "trust metadata",
      "explained state",
      "availability read",
      "bullpen planning read",
      "explanation confidence mirrors",
      "confidence mirrors",
      "governed availability evidence",
      "state reflects",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "role_or_classification": {
    "read": "Watch Arm",
    "role": "Limited Read"
  },
  "source_path": "services.pitcher_public_labels.build_pitcher_labels",
  "status": "Monitor",
  "surface_name": "Pitcher public role/read labels",
  "team": "Los Angeles Angels (LAA, 108)",
  "weighting_scoring_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "raw score",
      "scoring weight",
      "weighted pressure"
    ],
    "violation_count": 0,
    "violations": []
  }
}
```

Rendered public copy:
```
Limited Read
Watch Arm
```

Structured fields used:

```json
{
  "availability_confidence": "high",
  "availability_data_state": "fresh",
  "availability_status": "Monitor",
  "labels": {
    "read": {
      "key": "watch_arm",
      "kind": "read",
      "label": "Watch Arm",
      "source": "backend:availability_status"
    },
    "role": {
      "key": "limited_read",
      "kind": "role",
      "label": "Limited Read",
      "source": "backend:role_key:missing"
    }
  },
  "role_input": null,
  "roster_status": {
    "confidence": "high",
    "current_assignment_unresolved": false,
    "evidence": [
      "Stored roster status: Active MLB."
    ],
    "is_active_mlb": true,
    "is_authoritative": true,
    "is_inactive_context": false,
    "label": "Active MLB",
    "limitations": [],
    "raw_status": "ACTIVE",
    "raw_status_code": "A",
    "raw_status_description": "Active",
    "source": "mlb_stats_api:roster_sync:active",
    "status": "ACTIVE",
    "updated_at": "2026-06-30T10:00:04.993867"
  }
}
```

Evidence sections:

```json
{}
```

### Example 8: Pitcher V4 availability explanation

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "capitalization_sentence_scan": {
    "patterns": {
      "lowercase_sentence_start": "(?<=[.!?])\\s+([a-z])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "circular_meta_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "explanation confidence mirrors",
      "confidence mirrors",
      "visibility reflects existing availability confidence",
      "governed availability evidence",
      "state reflects",
      "explained state",
      "trust metadata",
      "readiness explanation confidence"
    ],
    "violation_count": 0,
    "violations": []
  },
  "disclaimer_repetition_scan": {
    "disclaimer": "This is a data-limited note, not a statement about injury status or manager intent.",
    "per_card_limit": 1,
    "scope": "Team bullpen shape rendered public copy",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "example_source": "stored-data example",
  "fallback_status": "rendered",
  "pitcher": "Kirby Yates",
  "raw_count_formula_scan": {
    "patterns": {
      "jargon_coupled_raw_count": "(?<![\\w-])\\d+\\s+of\\s+\\d+\\s+(?:trust|bridge|coverage|depth)\\s+arms?\\b",
      "parenthetical_raw_basis": "\\(\\s*\\d+\\s+of\\s+\\d+\\s*\\)",
      "parenthetical_unknown_formula": "\\([^)]*\\bunknown\\b[^)]*\\)",
      "raw_empty_arithmetic": "(?<![\\w-])\\d+\\s+of\\s+\\d+(?![\\w-])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "length option",
      "length options",
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "classified available",
      "0 of 0",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "trust metadata",
      "explained state",
      "availability read",
      "bullpen planning read",
      "explanation confidence mirrors",
      "confidence mirrors",
      "governed availability evidence",
      "state reflects",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "role_or_classification": {
    "scope": "availability_state",
    "subject_type": "pitcher"
  },
  "source_path": "api.explanations._availability_explanation_payload -> explanations.availability.serialize_availability_explanation",
  "status": "Limited",
  "surface_name": "Pitcher V4 availability explanation",
  "team": "Los Angeles Angels (LAA, 108)",
  "weighting_scoring_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "raw score",
      "scoring weight",
      "weighted pressure"
    ],
    "violation_count": 0,
    "violations": []
  }
}
```

Rendered public copy:
```
Recent usage points to a lighter lane if he is needed.
A heavy recent stretch has the workload up.
No injury data available
No team-reported availability data available
The stored workload data is current enough for this pitcher note.
```

Structured fields used:

```json
{
  "confidence": {
    "level": "high",
    "summary": "The public workload record is current enough for this note."
  },
  "freshness": {
    "data_through": "2026-06-27",
    "freshness_failure": null,
    "last_sync_at": null,
    "source_updated_at": "2026-06-30",
    "status": "current",
    "summary": "The stored workload data is current enough for this pitcher note."
  },
  "governance": {
    "advice_scope": "none",
    "decision_scope": "explanation_only",
    "prediction_made": false,
    "ranking_applied": false,
    "recommendation_made": false,
    "selection_made": false
  },
  "primary_reason_codes": [
    "WORKLOAD_RECENT_USAGE_ELEVATED"
  ],
  "scope": "availability_state",
  "state_explained": "Limited",
  "subject_id": "11",
  "subject_type": "pitcher",
  "trust": {
    "certification_status": "complete",
    "contract": "availability_engine_v1",
    "source": "availability_engine_v1",
    "status": "trusted",
    "summary": "The public workload record is strong enough for this note.",
    "trust_failure": null
  }
}
```

Evidence sections:

```json
{
  "limitations": [
    {
      "affected_scopes": [
        "availability_state"
      ],
      "limitation_type": "insufficient_context",
      "severity": "informational",
      "summary": "No injury data available"
    },
    {
      "affected_scopes": [
        "availability_state"
      ],
      "limitation_type": "insufficient_context",
      "severity": "informational",
      "summary": "No team-reported availability data available"
    }
  ],
  "primary_reasons": [
    {
      "code": "WORKLOAD_RECENT_USAGE_ELEVATED",
      "label": "Recent usage elevated",
      "scope": "workload_state",
      "summary": "A heavy recent stretch has the workload up."
    }
  ],
  "supporting_evidence": [
    {
      "evidence_type": "availability_status",
      "impact": "explains_availability_state",
      "label": "Availability status",
      "source": "availability_engine_v1",
      "unit": "status",
      "value": "Limited"
    },
    {
      "evidence_type": "availability_confidence",
      "impact": "explains_confidence_boundary",
      "label": "Availability confidence",
      "source": "availability_engine_v1",
      "unit": "level",
      "value": "high"
    },
    {
      "evidence_type": "availability_data_state",
      "impact": "explains_freshness_boundary",
      "label": "Availability data state",
      "source": "availability_engine_v1",
      "unit": "state",
      "value": "fresh"
    },
    {
      "evidence_type": "availability_fatigue_score",
      "impact": "explains_availability_state",
      "label": "Recent workload index",
      "source": "availability_engine_v1",
      "unit": "index",
      "value": 18.4
    },
    {
      "evidence_type": "availability_pitches_yesterday",
      "impact": "explains_availability_state",
      "label": "Pitches yesterday",
      "source": "availability_engine_v1",
      "unit": "pitches",
      "value": 0
    },
    {
      "evidence_type": "availability_pitches_last_3_days",
      "impact": "explains_availability_state",
      "label": "Pitches in 3 days",
      "source": "availability_engine_v1",
      "unit": "pitches",
      "value": 0
    },
    {
      "evidence_type": "availability_pitches_last_5_days",
      "impact": "explains_availability_state",
      "label": "Pitches in 5 days",
      "source": "availability_engine_v1",
      "unit": "pitches",
      "value": 22
    },
    {
      "evidence_type": "availability_appearances_last_3_days",
      "impact": "explains_availability_state",
      "label": "Appearances in 3 days",
      "source": "availability_engine_v1",
      "unit": "appearances",
      "value": 0
    },
    {
      "evidence_type": "availability_appearances_last_5_days",
      "impact": "explains_availability_state",
      "label": "Appearances in 5 days",
      "source": "availability_engine_v1",
      "unit": "appearances",
      "value": 2
    },
    {
      "evidence_type": "availability_days_rest",
      "impact": "explains_availability_state",
      "label": "Days of rest",
      "source": "availability_engine_v1",
      "unit": "days",
      "value": 3
    },
    {
      "evidence_type": "availability_back_to_back",
      "impact": "explains_availability_state",
      "label": "Back-to-back appearances",
      "source": "availability_engine_v1",
      "unit": "flag",
      "value": true
    }
  ]
}
```

### Example 9: Pitcher Context modal/detail route

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "capitalization_sentence_scan": {
    "patterns": {
      "lowercase_sentence_start": "(?<=[.!?])\\s+([a-z])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "circular_meta_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "explanation confidence mirrors",
      "confidence mirrors",
      "visibility reflects existing availability confidence",
      "governed availability evidence",
      "state reflects",
      "explained state",
      "trust metadata",
      "readiness explanation confidence"
    ],
    "violation_count": 0,
    "violations": []
  },
  "disclaimer_repetition_scan": {
    "disclaimer": "This is a data-limited note, not a statement about injury status or manager intent.",
    "per_card_limit": 1,
    "scope": "Team bullpen shape rendered public copy",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "example_source": "stored-data example",
  "fallback_status": "rendered",
  "pitcher": "Kirby Yates",
  "raw_count_formula_scan": {
    "patterns": {
      "jargon_coupled_raw_count": "(?<![\\w-])\\d+\\s+of\\s+\\d+\\s+(?:trust|bridge|coverage|depth)\\s+arms?\\b",
      "parenthetical_raw_basis": "\\(\\s*\\d+\\s+of\\s+\\d+\\s*\\)",
      "parenthetical_unknown_formula": "\\([^)]*\\bunknown\\b[^)]*\\)",
      "raw_empty_arithmetic": "(?<![\\w-])\\d+\\s+of\\s+\\d+(?![\\w-])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "length option",
      "length options",
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "classified available",
      "0 of 0",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "trust metadata",
      "explained state",
      "availability read",
      "bullpen planning read",
      "explanation confidence mirrors",
      "confidence mirrors",
      "governed availability evidence",
      "state reflects",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "role_or_classification": {
    "confidence": "high",
    "data_state": "fresh",
    "roster_status": "Active MLB"
  },
  "source_path": "api.bullpen.get_pitcher_fatigue",
  "status": "Limited",
  "surface_name": "Pitcher Context modal/detail route",
  "team": "Los Angeles Angels (LAA, 108)",
  "weighting_scoring_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "raw score",
      "scoring weight",
      "weighted pressure"
    ],
    "violation_count": 0,
    "violations": []
  }
}
```

Rendered public copy:
```
Limited
2 appearances in 5 days
Back-to-back appearances
No injury data available
No team-reported availability data available
Active MLB
Current baseball data through 2026-06-29.
```

Structured fields used:

```json
{
  "availability": {
    "availability_status": "Limited",
    "confidence": "high",
    "data_state": "fresh",
    "inputs": {
      "appearances_last_3_days": 0,
      "appearances_last_5_days": 2,
      "back_to_back": true,
      "days_rest": 3,
      "fatigue_risk_level": "LOW",
      "fatigue_score": 18.4,
      "four_in_five": false,
      "freshness_state": "fresh",
      "latest_game_date": "2026-06-27",
      "pitches_last_3_days": 0,
      "pitches_last_5_days": 22,
      "pitches_yesterday": 0,
      "reference_date": "2026-06-30",
      "three_in_four": false
    },
    "limitations": [
      "No injury data available",
      "No team-reported availability data available"
    ],
    "reasons": [
      "2 appearances in 5 days",
      "Back-to-back appearances"
    ]
  },
  "freshness": {
    "data_age_days": 1,
    "data_through": "2026-06-29",
    "freshness_state": "current",
    "label": "Current baseball data through 2026-06-29.",
    "limitations": []
  },
  "roster_status": {
    "confidence": "high",
    "label": "Active MLB",
    "limitations": [],
    "source": "mlb_stats_api:roster_sync:active",
    "status": "ACTIVE"
  },
  "workload_signal": {
    "availability_status": "Limited",
    "confidence": "high",
    "data_state": "fresh",
    "inputs": {
      "appearances_last_3_days": 0,
      "appearances_last_5_days": 2,
      "back_to_back": true,
      "days_rest": 3,
      "fatigue_risk_level": "LOW",
      "fatigue_score": 18.4,
      "four_in_five": false,
      "freshness_state": "fresh",
      "latest_game_date": "2026-06-27",
      "pitches_last_3_days": 0,
      "pitches_last_5_days": 22,
      "pitches_yesterday": 0,
      "reference_date": "2026-06-30",
      "three_in_four": false
    },
    "limitations": [
      "No injury data available",
      "No team-reported availability data available"
    ],
    "reasons": [
      "2 appearances in 5 days",
      "Back-to-back appearances"
    ]
  }
}
```

Evidence sections:

```json
{
  "fatigue_trend_points": 120,
  "last_workload_appearance": {
    "game_date": "2026-06-27",
    "pitches": 9
  },
  "recent_logs_reviewed": 7
}
```

### Example 10: Pitcher public role/read labels

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "capitalization_sentence_scan": {
    "patterns": {
      "lowercase_sentence_start": "(?<=[.!?])\\s+([a-z])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "circular_meta_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "explanation confidence mirrors",
      "confidence mirrors",
      "visibility reflects existing availability confidence",
      "governed availability evidence",
      "state reflects",
      "explained state",
      "trust metadata",
      "readiness explanation confidence"
    ],
    "violation_count": 0,
    "violations": []
  },
  "disclaimer_repetition_scan": {
    "disclaimer": "This is a data-limited note, not a statement about injury status or manager intent.",
    "per_card_limit": 1,
    "scope": "Team bullpen shape rendered public copy",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "example_source": "stored-data example",
  "fallback_status": "limited_role_context",
  "pitcher": "Kirby Yates",
  "raw_count_formula_scan": {
    "patterns": {
      "jargon_coupled_raw_count": "(?<![\\w-])\\d+\\s+of\\s+\\d+\\s+(?:trust|bridge|coverage|depth)\\s+arms?\\b",
      "parenthetical_raw_basis": "\\(\\s*\\d+\\s+of\\s+\\d+\\s*\\)",
      "parenthetical_unknown_formula": "\\([^)]*\\bunknown\\b[^)]*\\)",
      "raw_empty_arithmetic": "(?<![\\w-])\\d+\\s+of\\s+\\d+(?![\\w-])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "length option",
      "length options",
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "classified available",
      "0 of 0",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "trust metadata",
      "explained state",
      "availability read",
      "bullpen planning read",
      "explanation confidence mirrors",
      "confidence mirrors",
      "governed availability evidence",
      "state reflects",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "role_or_classification": {
    "read": "Rest-Restricted",
    "role": "Limited Read"
  },
  "source_path": "services.pitcher_public_labels.build_pitcher_labels",
  "status": "Limited",
  "surface_name": "Pitcher public role/read labels",
  "team": "Los Angeles Angels (LAA, 108)",
  "weighting_scoring_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "raw score",
      "scoring weight",
      "weighted pressure"
    ],
    "violation_count": 0,
    "violations": []
  }
}
```

Rendered public copy:
```
Limited Read
Rest-Restricted
```

Structured fields used:

```json
{
  "availability_confidence": "high",
  "availability_data_state": "fresh",
  "availability_status": "Limited",
  "labels": {
    "read": {
      "key": "rest_restricted",
      "kind": "read",
      "label": "Rest-Restricted",
      "source": "backend:availability_status"
    },
    "role": {
      "key": "limited_read",
      "kind": "role",
      "label": "Limited Read",
      "source": "backend:role_key:missing"
    }
  },
  "role_input": null,
  "roster_status": {
    "confidence": "high",
    "current_assignment_unresolved": false,
    "evidence": [
      "Stored roster status: Active MLB."
    ],
    "is_active_mlb": true,
    "is_authoritative": true,
    "is_inactive_context": false,
    "label": "Active MLB",
    "limitations": [],
    "raw_status": "ACTIVE",
    "raw_status_code": "A",
    "raw_status_description": "Active",
    "source": "mlb_stats_api:roster_sync:active",
    "status": "ACTIVE",
    "updated_at": "2026-06-30T10:00:04.993867"
  }
}
```

Evidence sections:

```json
{}
```

### Example 11: Pitcher V4 availability explanation

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "capitalization_sentence_scan": {
    "patterns": {
      "lowercase_sentence_start": "(?<=[.!?])\\s+([a-z])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "circular_meta_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "explanation confidence mirrors",
      "confidence mirrors",
      "visibility reflects existing availability confidence",
      "governed availability evidence",
      "state reflects",
      "explained state",
      "trust metadata",
      "readiness explanation confidence"
    ],
    "violation_count": 0,
    "violations": []
  },
  "disclaimer_repetition_scan": {
    "disclaimer": "This is a data-limited note, not a statement about injury status or manager intent.",
    "per_card_limit": 1,
    "scope": "Team bullpen shape rendered public copy",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "example_source": "stored-data example",
  "fallback_status": "rendered",
  "pitcher": "Mitch Farris",
  "raw_count_formula_scan": {
    "patterns": {
      "jargon_coupled_raw_count": "(?<![\\w-])\\d+\\s+of\\s+\\d+\\s+(?:trust|bridge|coverage|depth)\\s+arms?\\b",
      "parenthetical_raw_basis": "\\(\\s*\\d+\\s+of\\s+\\d+\\s*\\)",
      "parenthetical_unknown_formula": "\\([^)]*\\bunknown\\b[^)]*\\)",
      "raw_empty_arithmetic": "(?<![\\w-])\\d+\\s+of\\s+\\d+(?![\\w-])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "length option",
      "length options",
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "classified available",
      "0 of 0",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "trust metadata",
      "explained state",
      "availability read",
      "bullpen planning read",
      "explanation confidence mirrors",
      "confidence mirrors",
      "governed availability evidence",
      "state reflects",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "role_or_classification": {
    "scope": "availability_state",
    "subject_type": "pitcher"
  },
  "source_path": "api.explanations._availability_explanation_payload -> explanations.availability.serialize_availability_explanation",
  "status": "Avoid",
  "surface_name": "Pitcher V4 availability explanation",
  "team": "Los Angeles Angels (LAA, 108)",
  "weighting_scoring_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "raw score",
      "scoring weight",
      "weighted pressure"
    ],
    "violation_count": 0,
    "violations": []
  }
}
```

Rendered public copy:
```
Recent usage is heavy enough that BaseballOS is holding this as a rest-risk note.
A heavy recent stretch has the workload up.
No injury data available
No team-reported availability data available
The stored workload data is current enough for this pitcher note.
```

Structured fields used:

```json
{
  "confidence": {
    "level": "high",
    "summary": "The public workload record is current enough for this note."
  },
  "freshness": {
    "data_through": "2026-06-29",
    "freshness_failure": null,
    "last_sync_at": null,
    "source_updated_at": "2026-06-30",
    "status": "current",
    "summary": "The stored workload data is current enough for this pitcher note."
  },
  "governance": {
    "advice_scope": "none",
    "decision_scope": "explanation_only",
    "prediction_made": false,
    "ranking_applied": false,
    "recommendation_made": false,
    "selection_made": false
  },
  "primary_reason_codes": [
    "WORKLOAD_RECENT_USAGE_ELEVATED"
  ],
  "scope": "availability_state",
  "state_explained": "Avoid",
  "subject_id": "12",
  "subject_type": "pitcher",
  "trust": {
    "certification_status": "complete",
    "contract": "availability_engine_v1",
    "source": "availability_engine_v1",
    "status": "trusted",
    "summary": "The public workload record is strong enough for this note.",
    "trust_failure": null
  }
}
```

Evidence sections:

```json
{
  "limitations": [
    {
      "affected_scopes": [
        "availability_state"
      ],
      "limitation_type": "insufficient_context",
      "severity": "informational",
      "summary": "No injury data available"
    },
    {
      "affected_scopes": [
        "availability_state"
      ],
      "limitation_type": "insufficient_context",
      "severity": "informational",
      "summary": "No team-reported availability data available"
    }
  ],
  "primary_reasons": [
    {
      "code": "WORKLOAD_RECENT_USAGE_ELEVATED",
      "label": "Recent usage elevated",
      "scope": "workload_state",
      "summary": "A heavy recent stretch has the workload up."
    }
  ],
  "supporting_evidence": [
    {
      "evidence_type": "availability_status",
      "impact": "explains_availability_state",
      "label": "Availability status",
      "source": "availability_engine_v1",
      "unit": "status",
      "value": "Avoid"
    },
    {
      "evidence_type": "availability_confidence",
      "impact": "explains_confidence_boundary",
      "label": "Availability confidence",
      "source": "availability_engine_v1",
      "unit": "level",
      "value": "high"
    },
    {
      "evidence_type": "availability_data_state",
      "impact": "explains_freshness_boundary",
      "label": "Availability data state",
      "source": "availability_engine_v1",
      "unit": "state",
      "value": "fresh"
    },
    {
      "evidence_type": "availability_fatigue_score",
      "impact": "explains_availability_state",
      "label": "Recent workload index",
      "source": "availability_engine_v1",
      "unit": "index",
      "value": 54.6
    },
    {
      "evidence_type": "availability_pitches_yesterday",
      "impact": "explains_availability_state",
      "label": "Pitches yesterday",
      "source": "availability_engine_v1",
      "unit": "pitches",
      "value": 46
    },
    {
      "evidence_type": "availability_pitches_last_3_days",
      "impact": "explains_availability_state",
      "label": "Pitches in 3 days",
      "source": "availability_engine_v1",
      "unit": "pitches",
      "value": 46
    },
    {
      "evidence_type": "availability_pitches_last_5_days",
      "impact": "explains_availability_state",
      "label": "Pitches in 5 days",
      "source": "availability_engine_v1",
      "unit": "pitches",
      "value": 46
    },
    {
      "evidence_type": "availability_appearances_last_3_days",
      "impact": "explains_availability_state",
      "label": "Appearances in 3 days",
      "source": "availability_engine_v1",
      "unit": "appearances",
      "value": 1
    },
    {
      "evidence_type": "availability_appearances_last_5_days",
      "impact": "explains_availability_state",
      "label": "Appearances in 5 days",
      "source": "availability_engine_v1",
      "unit": "appearances",
      "value": 1
    },
    {
      "evidence_type": "availability_days_rest",
      "impact": "explains_availability_state",
      "label": "Days of rest",
      "source": "availability_engine_v1",
      "unit": "days",
      "value": 1
    }
  ]
}
```

### Example 12: Pitcher Context modal/detail route

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "capitalization_sentence_scan": {
    "patterns": {
      "lowercase_sentence_start": "(?<=[.!?])\\s+([a-z])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "circular_meta_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "explanation confidence mirrors",
      "confidence mirrors",
      "visibility reflects existing availability confidence",
      "governed availability evidence",
      "state reflects",
      "explained state",
      "trust metadata",
      "readiness explanation confidence"
    ],
    "violation_count": 0,
    "violations": []
  },
  "disclaimer_repetition_scan": {
    "disclaimer": "This is a data-limited note, not a statement about injury status or manager intent.",
    "per_card_limit": 1,
    "scope": "Team bullpen shape rendered public copy",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "example_source": "stored-data example",
  "fallback_status": "rendered",
  "pitcher": "Mitch Farris",
  "raw_count_formula_scan": {
    "patterns": {
      "jargon_coupled_raw_count": "(?<![\\w-])\\d+\\s+of\\s+\\d+\\s+(?:trust|bridge|coverage|depth)\\s+arms?\\b",
      "parenthetical_raw_basis": "\\(\\s*\\d+\\s+of\\s+\\d+\\s*\\)",
      "parenthetical_unknown_formula": "\\([^)]*\\bunknown\\b[^)]*\\)",
      "raw_empty_arithmetic": "(?<![\\w-])\\d+\\s+of\\s+\\d+(?![\\w-])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "length option",
      "length options",
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "classified available",
      "0 of 0",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "trust metadata",
      "explained state",
      "availability read",
      "bullpen planning read",
      "explanation confidence mirrors",
      "confidence mirrors",
      "governed availability evidence",
      "state reflects",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "role_or_classification": {
    "confidence": "high",
    "data_state": "fresh",
    "roster_status": "Active MLB"
  },
  "source_path": "api.bullpen.get_pitcher_fatigue",
  "status": "Avoid",
  "surface_name": "Pitcher Context modal/detail route",
  "team": "Los Angeles Angels (LAA, 108)",
  "weighting_scoring_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "raw score",
      "scoring weight",
      "weighted pressure"
    ],
    "violation_count": 0,
    "violations": []
  }
}
```

Rendered public copy:
```
Avoid
46 pitches yesterday
46 pitches in 3 days
Only 1 day of rest
Recent workload is high enough to narrow normal availability
No injury data available
No team-reported availability data available
Active MLB
Current baseball data through 2026-06-29.
```

Structured fields used:

```json
{
  "availability": {
    "availability_status": "Avoid",
    "confidence": "high",
    "data_state": "fresh",
    "inputs": {
      "appearances_last_3_days": 1,
      "appearances_last_5_days": 1,
      "back_to_back": false,
      "days_rest": 1,
      "fatigue_risk_level": "HIGH",
      "fatigue_score": 54.6,
      "four_in_five": false,
      "freshness_state": "fresh",
      "latest_game_date": "2026-06-29",
      "pitches_last_3_days": 46,
      "pitches_last_5_days": 46,
      "pitches_yesterday": 46,
      "reference_date": "2026-06-30",
      "three_in_four": false
    },
    "limitations": [
      "No injury data available",
      "No team-reported availability data available"
    ],
    "reasons": [
      "46 pitches yesterday",
      "46 pitches in 3 days",
      "Only 1 day of rest",
      "Recent workload is high enough to narrow normal availability"
    ]
  },
  "freshness": {
    "data_age_days": 1,
    "data_through": "2026-06-29",
    "freshness_state": "current",
    "label": "Current baseball data through 2026-06-29.",
    "limitations": []
  },
  "roster_status": {
    "confidence": "high",
    "label": "Active MLB",
    "limitations": [],
    "source": "mlb_stats_api:roster_sync:active",
    "status": "ACTIVE"
  },
  "workload_signal": {
    "availability_status": "Avoid",
    "confidence": "high",
    "data_state": "fresh",
    "inputs": {
      "appearances_last_3_days": 1,
      "appearances_last_5_days": 1,
      "back_to_back": false,
      "days_rest": 1,
      "fatigue_risk_level": "HIGH",
      "fatigue_score": 54.6,
      "four_in_five": false,
      "freshness_state": "fresh",
      "latest_game_date": "2026-06-29",
      "pitches_last_3_days": 46,
      "pitches_last_5_days": 46,
      "pitches_yesterday": 46,
      "reference_date": "2026-06-30",
      "three_in_four": false
    },
    "limitations": [
      "No injury data available",
      "No team-reported availability data available"
    ],
    "reasons": [
      "46 pitches yesterday",
      "46 pitches in 3 days",
      "Only 1 day of rest",
      "Recent workload is high enough to narrow normal availability"
    ]
  }
}
```

Evidence sections:

```json
{
  "fatigue_trend_points": 120,
  "last_workload_appearance": {
    "game_date": "2026-06-29",
    "pitches": 46
  },
  "recent_logs_reviewed": 3
}
```

### Example 13: Pitcher V4 availability explanation

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "capitalization_sentence_scan": {
    "patterns": {
      "lowercase_sentence_start": "(?<=[.!?])\\s+([a-z])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "circular_meta_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "explanation confidence mirrors",
      "confidence mirrors",
      "visibility reflects existing availability confidence",
      "governed availability evidence",
      "state reflects",
      "explained state",
      "trust metadata",
      "readiness explanation confidence"
    ],
    "violation_count": 0,
    "violations": []
  },
  "disclaimer_repetition_scan": {
    "disclaimer": "This is a data-limited note, not a statement about injury status or manager intent.",
    "per_card_limit": 1,
    "scope": "Team bullpen shape rendered public copy",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "example_source": "stored-data example",
  "fallback_status": "rendered",
  "pitcher": "Ryan Johnson",
  "raw_count_formula_scan": {
    "patterns": {
      "jargon_coupled_raw_count": "(?<![\\w-])\\d+\\s+of\\s+\\d+\\s+(?:trust|bridge|coverage|depth)\\s+arms?\\b",
      "parenthetical_raw_basis": "\\(\\s*\\d+\\s+of\\s+\\d+\\s*\\)",
      "parenthetical_unknown_formula": "\\([^)]*\\bunknown\\b[^)]*\\)",
      "raw_empty_arithmetic": "(?<![\\w-])\\d+\\s+of\\s+\\d+(?![\\w-])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "length option",
      "length options",
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "classified available",
      "0 of 0",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "trust metadata",
      "explained state",
      "availability read",
      "bullpen planning read",
      "explanation confidence mirrors",
      "confidence mirrors",
      "governed availability evidence",
      "state reflects",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "role_or_classification": {
    "scope": "availability_state",
    "subject_type": "pitcher"
  },
  "source_path": "api.explanations._availability_explanation_payload -> explanations.availability.serialize_availability_explanation",
  "status": "Unavailable",
  "surface_name": "Pitcher V4 availability explanation",
  "team": "Los Angeles Angels (LAA, 108)",
  "weighting_scoring_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "raw score",
      "scoring weight",
      "weighted pressure"
    ],
    "violation_count": 0,
    "violations": []
  }
}
```

Rendered public copy:
```
A heavy recent stretch has his workload up enough to make him unavailable.
A heavy recent stretch has the workload up.
No injury data available
No team-reported availability data available
The stored workload data is current enough for this pitcher note.
```

Structured fields used:

```json
{
  "confidence": {
    "level": "high",
    "summary": "The public workload record is current enough for this note."
  },
  "freshness": {
    "data_through": "2026-06-29",
    "freshness_failure": null,
    "last_sync_at": null,
    "source_updated_at": "2026-06-30",
    "status": "current",
    "summary": "The stored workload data is current enough for this pitcher note."
  },
  "governance": {
    "advice_scope": "none",
    "decision_scope": "explanation_only",
    "prediction_made": false,
    "ranking_applied": false,
    "recommendation_made": false,
    "selection_made": false
  },
  "primary_reason_codes": [
    "WORKLOAD_RECENT_USAGE_ELEVATED"
  ],
  "scope": "availability_state",
  "state_explained": "Unavailable",
  "subject_id": "15",
  "subject_type": "pitcher",
  "trust": {
    "certification_status": "complete",
    "contract": "availability_engine_v1",
    "source": "availability_engine_v1",
    "status": "trusted",
    "summary": "The public workload record is strong enough for this note.",
    "trust_failure": null
  }
}
```

Evidence sections:

```json
{
  "limitations": [
    {
      "affected_scopes": [
        "availability_state"
      ],
      "limitation_type": "insufficient_context",
      "severity": "informational",
      "summary": "No injury data available"
    },
    {
      "affected_scopes": [
        "availability_state"
      ],
      "limitation_type": "insufficient_context",
      "severity": "informational",
      "summary": "No team-reported availability data available"
    }
  ],
  "primary_reasons": [
    {
      "code": "WORKLOAD_RECENT_USAGE_ELEVATED",
      "label": "Recent usage elevated",
      "scope": "workload_state",
      "summary": "A heavy recent stretch has the workload up."
    }
  ],
  "supporting_evidence": [
    {
      "evidence_type": "availability_status",
      "impact": "explains_availability_state",
      "label": "Availability status",
      "source": "availability_engine_v1",
      "unit": "status",
      "value": "Unavailable"
    },
    {
      "evidence_type": "availability_confidence",
      "impact": "explains_confidence_boundary",
      "label": "Availability confidence",
      "source": "availability_engine_v1",
      "unit": "level",
      "value": "high"
    },
    {
      "evidence_type": "availability_data_state",
      "impact": "explains_freshness_boundary",
      "label": "Availability data state",
      "source": "availability_engine_v1",
      "unit": "state",
      "value": "fresh"
    },
    {
      "evidence_type": "availability_fatigue_score",
      "impact": "explains_availability_state",
      "label": "Recent workload index",
      "source": "availability_engine_v1",
      "unit": "index",
      "value": 79.5
    },
    {
      "evidence_type": "availability_pitches_yesterday",
      "impact": "explains_availability_state",
      "label": "Pitches yesterday",
      "source": "availability_engine_v1",
      "unit": "pitches",
      "value": 81
    },
    {
      "evidence_type": "availability_pitches_last_3_days",
      "impact": "explains_availability_state",
      "label": "Pitches in 3 days",
      "source": "availability_engine_v1",
      "unit": "pitches",
      "value": 81
    },
    {
      "evidence_type": "availability_pitches_last_5_days",
      "impact": "explains_availability_state",
      "label": "Pitches in 5 days",
      "source": "availability_engine_v1",
      "unit": "pitches",
      "value": 81
    },
    {
      "evidence_type": "availability_appearances_last_3_days",
      "impact": "explains_availability_state",
      "label": "Appearances in 3 days",
      "source": "availability_engine_v1",
      "unit": "appearances",
      "value": 1
    },
    {
      "evidence_type": "availability_appearances_last_5_days",
      "impact": "explains_availability_state",
      "label": "Appearances in 5 days",
      "source": "availability_engine_v1",
      "unit": "appearances",
      "value": 1
    },
    {
      "evidence_type": "availability_days_rest",
      "impact": "explains_availability_state",
      "label": "Days of rest",
      "source": "availability_engine_v1",
      "unit": "days",
      "value": 1
    }
  ]
}
```

### Example 14: Pitcher Context modal/detail route

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "capitalization_sentence_scan": {
    "patterns": {
      "lowercase_sentence_start": "(?<=[.!?])\\s+([a-z])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "circular_meta_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "explanation confidence mirrors",
      "confidence mirrors",
      "visibility reflects existing availability confidence",
      "governed availability evidence",
      "state reflects",
      "explained state",
      "trust metadata",
      "readiness explanation confidence"
    ],
    "violation_count": 0,
    "violations": []
  },
  "disclaimer_repetition_scan": {
    "disclaimer": "This is a data-limited note, not a statement about injury status or manager intent.",
    "per_card_limit": 1,
    "scope": "Team bullpen shape rendered public copy",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "example_source": "stored-data example",
  "fallback_status": "rendered",
  "pitcher": "Ryan Johnson",
  "raw_count_formula_scan": {
    "patterns": {
      "jargon_coupled_raw_count": "(?<![\\w-])\\d+\\s+of\\s+\\d+\\s+(?:trust|bridge|coverage|depth)\\s+arms?\\b",
      "parenthetical_raw_basis": "\\(\\s*\\d+\\s+of\\s+\\d+\\s*\\)",
      "parenthetical_unknown_formula": "\\([^)]*\\bunknown\\b[^)]*\\)",
      "raw_empty_arithmetic": "(?<![\\w-])\\d+\\s+of\\s+\\d+(?![\\w-])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "length option",
      "length options",
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "classified available",
      "0 of 0",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "trust metadata",
      "explained state",
      "availability read",
      "bullpen planning read",
      "explanation confidence mirrors",
      "confidence mirrors",
      "governed availability evidence",
      "state reflects",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "role_or_classification": {
    "confidence": "high",
    "data_state": "fresh",
    "roster_status": "Active MLB"
  },
  "source_path": "api.bullpen.get_pitcher_fatigue",
  "status": "Unavailable",
  "surface_name": "Pitcher Context modal/detail route",
  "team": "Los Angeles Angels (LAA, 108)",
  "weighting_scoring_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "raw score",
      "scoring weight",
      "weighted pressure"
    ],
    "violation_count": 0,
    "violations": []
  }
}
```

Rendered public copy:
```
Unavailable
81 pitches yesterday
81 pitches in 3 days
81 pitches in 5 days
Only 1 day of rest
Recent workload is high enough to narrow normal availability
No injury data available
No team-reported availability data available
Active MLB
Current baseball data through 2026-06-29.
```

Structured fields used:

```json
{
  "availability": {
    "availability_status": "Unavailable",
    "confidence": "high",
    "data_state": "fresh",
    "inputs": {
      "appearances_last_3_days": 1,
      "appearances_last_5_days": 1,
      "back_to_back": false,
      "days_rest": 1,
      "fatigue_risk_level": "HIGH",
      "fatigue_score": 79.5,
      "four_in_five": false,
      "freshness_state": "fresh",
      "latest_game_date": "2026-06-29",
      "pitches_last_3_days": 81,
      "pitches_last_5_days": 81,
      "pitches_yesterday": 81,
      "reference_date": "2026-06-30",
      "three_in_four": false
    },
    "limitations": [
      "No injury data available",
      "No team-reported availability data available"
    ],
    "reasons": [
      "81 pitches yesterday",
      "81 pitches in 3 days",
      "81 pitches in 5 days",
      "Only 1 day of rest",
      "Recent workload is high enough to narrow normal availability"
    ]
  },
  "freshness": {
    "data_age_days": 1,
    "data_through": "2026-06-29",
    "freshness_state": "current",
    "label": "Current baseball data through 2026-06-29.",
    "limitations": []
  },
  "roster_status": {
    "confidence": "high",
    "label": "Active MLB",
    "limitations": [],
    "source": "mlb_stats_api:roster_sync:active",
    "status": "ACTIVE"
  },
  "workload_signal": {
    "availability_status": "Unavailable",
    "confidence": "high",
    "data_state": "fresh",
    "inputs": {
      "appearances_last_3_days": 1,
      "appearances_last_5_days": 1,
      "back_to_back": false,
      "days_rest": 1,
      "fatigue_risk_level": "HIGH",
      "fatigue_score": 79.5,
      "four_in_five": false,
      "freshness_state": "fresh",
      "latest_game_date": "2026-06-29",
      "pitches_last_3_days": 81,
      "pitches_last_5_days": 81,
      "pitches_yesterday": 81,
      "reference_date": "2026-06-30",
      "three_in_four": false
    },
    "limitations": [
      "No injury data available",
      "No team-reported availability data available"
    ],
    "reasons": [
      "81 pitches yesterday",
      "81 pitches in 3 days",
      "81 pitches in 5 days",
      "Only 1 day of rest",
      "Recent workload is high enough to narrow normal availability"
    ]
  }
}
```

Evidence sections:

```json
{
  "fatigue_trend_points": 92,
  "last_workload_appearance": {
    "game_date": "2026-06-29",
    "pitches": 81
  },
  "recent_logs_reviewed": 3
}
```

### Example 15: Team bullpen board context

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "capitalization_sentence_scan": {
    "patterns": {
      "lowercase_sentence_start": "(?<=[.!?])\\s+([a-z])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "circular_meta_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "explanation confidence mirrors",
      "confidence mirrors",
      "visibility reflects existing availability confidence",
      "governed availability evidence",
      "state reflects",
      "explained state",
      "trust metadata",
      "readiness explanation confidence"
    ],
    "violation_count": 0,
    "violations": []
  },
  "disclaimer_repetition_scan": {
    "disclaimer": "This is a data-limited note, not a statement about injury status or manager intent.",
    "per_card_limit": 1,
    "scope": "Team bullpen shape rendered public copy",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "example_source": "stored-data example",
  "fallback_status": "rendered",
  "pitcher": null,
  "raw_count_formula_scan": {
    "patterns": {
      "jargon_coupled_raw_count": "(?<![\\w-])\\d+\\s+of\\s+\\d+\\s+(?:trust|bridge|coverage|depth)\\s+arms?\\b",
      "parenthetical_raw_basis": "\\(\\s*\\d+\\s+of\\s+\\d+\\s*\\)",
      "parenthetical_unknown_formula": "\\([^)]*\\bunknown\\b[^)]*\\)",
      "raw_empty_arithmetic": "(?<![\\w-])\\d+\\s+of\\s+\\d+(?![\\w-])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "length option",
      "length options",
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "classified available",
      "0 of 0",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "trust metadata",
      "explained state",
      "availability read",
      "bullpen planning read",
      "explanation confidence mirrors",
      "confidence mirrors",
      "governed availability evidence",
      "state reflects",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "role_or_classification": {
    "total_pitchers": 9,
    "ungrouped_pitchers": 0
  },
  "source_path": "api.bullpen._build_team_board -> services.bullpen_board.build_board_payload",
  "status": "elevated",
  "surface_name": "Team bullpen board context",
  "team": "Los Angeles Angels (LAA, 108)",
  "weighting_scoring_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "raw score",
      "scoring weight",
      "weighted pressure"
    ],
    "violation_count": 0,
    "violations": []
  }
}
```

Rendered public copy:
```
Bullpen workload is elevated.
Four relievers are available from the latest completed workload data.
Two relievers are Avoid or Unavailable.
One reliever is in the Monitor group.
Availability classifications are workload-based only.
Available
Workload signals are inside normal ranges in the latest completed data.
Monitor
Worth a look at recent workload before counting on these arms.
Limited
Recent workload suggests limited use from the latest completed data.
Avoid
Meaningful recent-use load on these arms.
Unavailable Pitchers
Not available from the latest public workload and roster context.
```

Structured fields used:

```json
{
  "context": {
    "confidence": "high",
    "health": {
      "label": "Bullpen workload is elevated.",
      "reasons": [
        "Four relievers are available from the latest completed workload data.",
        "Two relievers are Avoid or Unavailable.",
        "One reliever is in the Monitor group.",
        "Availability classifications are workload-based only."
      ],
      "state": "elevated"
    },
    "limitations": [],
    "metrics": {
      "available": 4,
      "avoid": 1,
      "limited": 2,
      "monitor": 1,
      "pct_available": 44,
      "pct_restricted": 22,
      "pct_unavailable": 11,
      "restricted": 2,
      "total_relievers": 9,
      "unavailable": 1
    }
  },
  "freshness": {
    "active_cutoff_date": "2026-06-16",
    "active_window_days": 14,
    "availability_reference_date": "2026-06-30",
    "data_age_days": 1,
    "data_through": "2026-06-29",
    "degradation": {
      "data_age_days": 1,
      "fail_closed": false,
      "stale_after_days": 14,
      "state": "fresh",
      "unavailable_after_days": 30
    },
    "degradation_state": "fresh",
    "fail_closed": false,
    "freshness_state": "current",
    "is_current": true,
    "is_stale": false,
    "label": "Current baseball data through 2026-06-29.",
    "last_completed_game_refresh": "2026-06-30T07:13:03.808628Z",
    "last_morning_full_sync": "2026-06-30T10:02:10.485036Z",
    "last_successful_sync": "2026-06-30T10:02:10.485036Z",
    "latest_workload_date": "2026-06-29",
    "limitations": [],
    "reason_codes": [],
    "reference_date": "2026-06-30",
    "sync_authority": "sync_runs",
    "sync_status": "success"
  },
  "groups": [
    {
      "count": 4,
      "description": "Workload signals are inside normal ranges in the latest completed data.",
      "label": "Available",
      "status": "Available"
    },
    {
      "count": 1,
      "description": "Worth a look at recent workload before counting on these arms.",
      "label": "Monitor",
      "status": "Monitor"
    },
    {
      "count": 2,
      "description": "Recent workload suggests limited use from the latest completed data.",
      "label": "Limited",
      "status": "Limited"
    },
    {
      "count": 1,
      "description": "Meaningful recent-use load on these arms.",
      "label": "Avoid",
      "status": "Avoid"
    },
    {
      "count": 1,
      "description": "Not available from the latest public workload and roster context.",
      "label": "Unavailable Pitchers",
      "status": "Unavailable"
    }
  ],
  "limitations": []
}
```

Evidence sections:

```json
{
  "group_counts": {
    "Available": 4,
    "Avoid": 1,
    "Limited": 2,
    "Monitor": 1,
    "Unavailable": 1
  },
  "roster_authority_summary": {
    "limitations": [],
    "population": {
      "known_count": 13,
      "roster_status_coverage": 1.0,
      "total_candidates": 13,
      "unknown_count": 0
    }
  }
}
```

### Example 16: Team bullpen shape explanations

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "capitalization_sentence_scan": {
    "patterns": {
      "lowercase_sentence_start": "(?<=[.!?])\\s+([a-z])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "circular_meta_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "explanation confidence mirrors",
      "confidence mirrors",
      "visibility reflects existing availability confidence",
      "governed availability evidence",
      "state reflects",
      "explained state",
      "trust metadata",
      "readiness explanation confidence"
    ],
    "violation_count": 0,
    "violations": []
  },
  "disclaimer_repetition_scan": {
    "disclaimer": "This is a data-limited note, not a statement about injury status or manager intent.",
    "per_card_limit": 1,
    "scope": "Team bullpen shape rendered public copy",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "example_source": "stored-data example",
  "fallback_status": "rendered",
  "pitcher": null,
  "raw_count_formula_scan": {
    "patterns": {
      "jargon_coupled_raw_count": "(?<![\\w-])\\d+\\s+of\\s+\\d+\\s+(?:trust|bridge|coverage|depth)\\s+arms?\\b",
      "parenthetical_raw_basis": "\\(\\s*\\d+\\s+of\\s+\\d+\\s*\\)",
      "parenthetical_unknown_formula": "\\([^)]*\\bunknown\\b[^)]*\\)",
      "raw_empty_arithmetic": "(?<![\\w-])\\d+\\s+of\\s+\\d+(?![\\w-])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "length option",
      "length options",
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "classified available",
      "0 of 0",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "trust metadata",
      "explained state",
      "availability read",
      "bullpen planning read",
      "explanation confidence mirrors",
      "confidence mirrors",
      "governed availability evidence",
      "state reflects",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "role_or_classification": {
    "read_labels": [
      "Stable Late-Inning Availability",
      "Healthy Rested Bullpen",
      "High Late-Inning Pressure",
      "No Workload Concentration",
      "Stable Coverage Safety",
      "Limited Depth Safety"
    ]
  },
  "source_path": "services.team_bullpen_shape.build_team_bullpen_shape",
  "status": "team_shape",
  "surface_name": "Team bullpen shape explanations",
  "team": "Los Angeles Angels (LAA, 108)",
  "weighting_scoring_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "raw score",
      "scoring weight",
      "weighted pressure"
    ],
    "violation_count": 0,
    "violations": []
  }
}
```

Rendered public copy:
```
Stable Late-Inning Availability
The late-inning group has two late-inning arms fully rested and no late-inning arms worth monitoring. Two late-inning arms are carrying enough recent workload to narrow the late-game path.
Healthy Rested Bullpen
The bullpen has four arms fully rested, with four rested arms who fit the late-inning bridge. That gives the late innings more cushion if the starter exits early.
High Late-Inning Pressure
The primary late-inning pocket has two arms fully rested and two arms carrying enough recent workload to narrow the path. The handoff innings add one arm with recent stress, and one arm is carrying heavy recent workload.
No Workload Concentration
Three arms have carried 51% of the recent relief work across eight bullpen arms.
Stable Coverage Safety
The bullpen has enough stored coverage to handle more than one relief inning.
The bullpen has eight relievers active in the stored board, with four relievers rested enough to cover innings.
The wider relief picture is moderate, with no late anchors and seven leverage arms near the back of the game.
Coverage reads stable because there are enough rested relievers with a broad late-inning group.
Limited Depth Safety
The lower-leverage layer has no arms who can cover softer innings, while no arms are carrying enough recent workload to limit the fallback cushion.
```

Structured fields used:

```json
{
  "reads": [
    {
      "explanation": "The late-inning group has two late-inning arms fully rested and no late-inning arms worth monitoring. Two late-inning arms are carrying enough recent workload to narrow the late-game path.",
      "key": "trustAvailability",
      "label": "Stable Late-Inning Availability",
      "reasons": [
        "The late-inning group has two late-inning arms fully rested and no late-inning arms worth monitoring. Two late-inning arms are carrying enough recent workload to narrow the late-game path."
      ],
      "supportingCounts": {
        "availableTrustArms": 2,
        "cleanTrustArms": 2,
        "limitedReadTrustArms": 0,
        "restRestrictedTrustArms": 2,
        "roleKnownCount": 9,
        "totalBullpenArms": 9,
        "trustArms": 4,
        "unavailableTrustArms": 0,
        "watchTrustArms": 0
      }
    },
    {
      "explanation": "The bullpen has four arms fully rested, with four rested arms who fit the late-inning bridge. That gives the late innings more cushion if the starter exits early.",
      "key": "cleanOptions",
      "label": "Healthy Rested Bullpen",
      "reasons": [
        "The bullpen has four arms fully rested, with four rested arms who fit the late-inning bridge. That gives the late innings more cushion if the starter exits early."
      ],
      "supportingCounts": {
        "activeBullpenArms": 8,
        "cleanBridgeArms": 2,
        "cleanCoverageArms": 0,
        "cleanDepthArms": 0,
        "cleanOptionCount": 4,
        "cleanTrustArms": 2,
        "limitedReadCount": 0,
        "meaningfulCleanBacking": true,
        "restRestrictedCount": 3,
        "totalBullpenArms": 9,
        "unavailableCount": 1
      }
    },
    {
      "explanation": "The primary late-inning pocket has two arms fully rested and two arms carrying enough recent workload to narrow the path. The handoff innings add one arm with recent stress, and one arm is carrying heavy recent workload.",
      "key": "bullpenPressure",
      "label": "High Late-Inning Pressure",
      "reasons": [
        "The primary late-inning pocket has two arms fully rested and two arms carrying enough recent workload to narrow the path. The handoff innings add one arm with recent stress, and one arm is carrying heavy recent workload."
      ],
      "supportingCounts": {
        "cleanTrustArms": 2,
        "highFatigueArms": 1,
        "limitedReadCount": 0,
        "noUsableTrust": false,
        "restRestrictedCount": 3,
        "restrictedTrustArms": 2,
        "stressedBridgeArms": 0,
        "stressedCoverageArms": 1,
        "totalBullpenArms": 9,
        "unavailableCount": 1,
        "unavailableTrustArms": 0,
        "usableTrustArms": 2,
        "watchArmCount": 1
      }
    },
    {
      "explanation": "Three arms have carried 51% of the recent relief work across eight bullpen arms.",
      "key": "workloadConcentration",
      "label": "No Workload Concentration",
      "reasons": [
        "Three arms have carried 51% of the recent relief work across eight bullpen arms."
      ],
      "supportingCounts": {
        "concentrationDescriptor": "no concentration",
        "concentrationLevel": "none",
        "participantCount": 8,
        "perArmPitches": 43.625,
        "topArmCount": 3,
        "topOneShare": 0.20916905444126074,
        "topPitchTotal": 179,
        "topShare": 0.5128939828080229,
        "topSharePct": 51,
        "totalRecentPitches": 349,
        "windowDays": 7
      }
    },
    {
      "capability": "bullpen_coverage_safety_v2",
      "explanation": "The bullpen has enough stored coverage to handle more than one relief inning.",
      "key": "coverageSafety",
      "label": "Stable Coverage Safety",
      "limitations": [],
      "reasons": [
        "The bullpen has eight relievers active in the stored board, with four relievers rested enough to cover innings.",
        "The wider relief picture is moderate, with no late anchors and seven leverage arms near the back of the game.",
        "Coverage reads stable because there are enough rested relievers with a broad late-inning group."
      ],
      "source": "backend",
      "supportingCounts": {
        "activeRelieverCount": 8,
        "anchorCount": 0,
        "capacityState": "reduced",
        "cleanActiveRelieverCount": 4,
        "coverageSafetyVersion": "2.0",
        "environmentPressureSources": [
          "capacity_loss",
          "rotation_support_pressure"
        ],
        "environmentStatus": "multi_source_pressure",
        "hierarchyConfidence": "medium",
        "leverageCount": 7,
        "resourceHealthState": "moderate",
        "thresholds": {
          "stableMinCleanActiveRelievers": 3,
          "stableMinTrustedGroupSize": 4,
          "strongMinCleanActiveRelievers": 5,
          "strongMinTrustedGroupSize": 5,
          "thinTrustUnavailableMin": 2,
          "thinTrustUnavailablePct": 40
        },
        "topTrustBucketAvailableCount": 7,
        "trustArmsUnavailable": 0,
        "trustCapacityUnavailablePct": 0,
        "trustedCount": 0,
        "trustedGroupSize": 7
      },
      "version": "2026-06-19"
    },
    {
      "explanation": "The lower-leverage layer has no arms who can cover softer innings, while no arms are carrying enough recent workload to limit the fallback cushion.",
      "key": "depthSafety",
      "label": "Limited Depth Safety",
      "reasons": [
        "The lower-leverage layer has no arms who can cover softer innings, while no arms are carrying enough recent workload to limit the fallback cushion."
      ],
      "supportingCounts": {
        "activeBullpenArms": 8,
        "anchoredByTrust": true,
        "availableDepthArms": 0,
        "cleanDepthArms": 0,
        "depthArms": 0,
        "limitedReadDepthArms": 0,
        "restRestrictedDepthArms": 0,
        "roleKnownCount": 9,
        "totalBullpenArms": 9,
        "unavailableDepthArms": 0,
        "usableTrustArms": 2,
        "watchDepthArms": 0
      }
    }
  ],
  "source": "backend",
  "supportingCounts": {
    "activeBullpenArms": 8,
    "readKnownCount": 9,
    "roleKnownCount": 9,
    "totalBullpenArms": 9
  }
}
```

Evidence sections:

```json
{
  "read_count": 6,
  "read_keys": [
    "trustAvailability",
    "cleanOptions",
    "bullpenPressure",
    "workloadConcentration",
    "coverageSafety",
    "depthSafety"
  ]
}
```

### Example 17: Team bullpen board context

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "capitalization_sentence_scan": {
    "patterns": {
      "lowercase_sentence_start": "(?<=[.!?])\\s+([a-z])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "circular_meta_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "explanation confidence mirrors",
      "confidence mirrors",
      "visibility reflects existing availability confidence",
      "governed availability evidence",
      "state reflects",
      "explained state",
      "trust metadata",
      "readiness explanation confidence"
    ],
    "violation_count": 0,
    "violations": []
  },
  "disclaimer_repetition_scan": {
    "disclaimer": "This is a data-limited note, not a statement about injury status or manager intent.",
    "per_card_limit": 1,
    "scope": "Team bullpen shape rendered public copy",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "example_source": "stored-data example",
  "fallback_status": "rendered",
  "pitcher": null,
  "raw_count_formula_scan": {
    "patterns": {
      "jargon_coupled_raw_count": "(?<![\\w-])\\d+\\s+of\\s+\\d+\\s+(?:trust|bridge|coverage|depth)\\s+arms?\\b",
      "parenthetical_raw_basis": "\\(\\s*\\d+\\s+of\\s+\\d+\\s*\\)",
      "parenthetical_unknown_formula": "\\([^)]*\\bunknown\\b[^)]*\\)",
      "raw_empty_arithmetic": "(?<![\\w-])\\d+\\s+of\\s+\\d+(?![\\w-])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "length option",
      "length options",
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "classified available",
      "0 of 0",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "trust metadata",
      "explained state",
      "availability read",
      "bullpen planning read",
      "explanation confidence mirrors",
      "confidence mirrors",
      "governed availability evidence",
      "state reflects",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "role_or_classification": {
    "total_pitchers": 9,
    "ungrouped_pitchers": 0
  },
  "source_path": "api.bullpen._build_team_board -> services.bullpen_board.build_board_payload",
  "status": "manageable",
  "surface_name": "Team bullpen board context",
  "team": "Arizona Diamondbacks (AZ, 109)",
  "weighting_scoring_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "raw score",
      "scoring weight",
      "weighted pressure"
    ],
    "violation_count": 0,
    "violations": []
  }
}
```

Rendered public copy:
```
Bullpen workload appears manageable.
Six relievers are available from the latest completed workload data.
No relievers are marked Avoid or Unavailable.
Availability classifications are workload-based only.
Available
Workload signals are inside normal ranges in the latest completed data.
Monitor
Worth a look at recent workload before counting on these arms.
Limited
Recent workload suggests limited use from the latest completed data.
Avoid
Meaningful recent-use load on these arms.
Unavailable Pitchers
Not available from the latest public workload and roster context.
```

Structured fields used:

```json
{
  "context": {
    "confidence": "high",
    "health": {
      "label": "Bullpen workload appears manageable.",
      "reasons": [
        "Six relievers are available from the latest completed workload data.",
        "No relievers are marked Avoid or Unavailable.",
        "Availability classifications are workload-based only."
      ],
      "state": "manageable"
    },
    "limitations": [],
    "metrics": {
      "available": 6,
      "avoid": 0,
      "limited": 0,
      "monitor": 3,
      "pct_available": 67,
      "pct_restricted": 0,
      "pct_unavailable": 0,
      "restricted": 0,
      "total_relievers": 9,
      "unavailable": 0
    }
  },
  "freshness": {
    "active_cutoff_date": "2026-06-16",
    "active_window_days": 14,
    "availability_reference_date": "2026-06-30",
    "data_age_days": 1,
    "data_through": "2026-06-29",
    "degradation": {
      "data_age_days": 1,
      "fail_closed": false,
      "stale_after_days": 14,
      "state": "fresh",
      "unavailable_after_days": 30
    },
    "degradation_state": "fresh",
    "fail_closed": false,
    "freshness_state": "current",
    "is_current": true,
    "is_stale": false,
    "label": "Current baseball data through 2026-06-29.",
    "last_completed_game_refresh": "2026-06-30T07:13:03.808628Z",
    "last_morning_full_sync": "2026-06-30T10:02:10.485036Z",
    "last_successful_sync": "2026-06-30T10:02:10.485036Z",
    "latest_workload_date": "2026-06-29",
    "limitations": [],
    "reason_codes": [],
    "reference_date": "2026-06-30",
    "sync_authority": "sync_runs",
    "sync_status": "success"
  },
  "groups": [
    {
      "count": 6,
      "description": "Workload signals are inside normal ranges in the latest completed data.",
      "label": "Available",
      "status": "Available"
    },
    {
      "count": 3,
      "description": "Worth a look at recent workload before counting on these arms.",
      "label": "Monitor",
      "status": "Monitor"
    },
    {
      "count": 0,
      "description": "Recent workload suggests limited use from the latest completed data.",
      "label": "Limited",
      "status": "Limited"
    },
    {
      "count": 0,
      "description": "Meaningful recent-use load on these arms.",
      "label": "Avoid",
      "status": "Avoid"
    },
    {
      "count": 0,
      "description": "Not available from the latest public workload and roster context.",
      "label": "Unavailable Pitchers",
      "status": "Unavailable"
    }
  ],
  "limitations": []
}
```

Evidence sections:

```json
{
  "group_counts": {
    "Available": 6,
    "Avoid": 0,
    "Limited": 0,
    "Monitor": 3,
    "Unavailable": 0
  },
  "roster_authority_summary": {
    "limitations": [],
    "population": {
      "known_count": 20,
      "roster_status_coverage": 1.0,
      "total_candidates": 20,
      "unknown_count": 0
    }
  }
}
```

### Example 18: Team bullpen shape explanations

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "capitalization_sentence_scan": {
    "patterns": {
      "lowercase_sentence_start": "(?<=[.!?])\\s+([a-z])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "circular_meta_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "explanation confidence mirrors",
      "confidence mirrors",
      "visibility reflects existing availability confidence",
      "governed availability evidence",
      "state reflects",
      "explained state",
      "trust metadata",
      "readiness explanation confidence"
    ],
    "violation_count": 0,
    "violations": []
  },
  "disclaimer_repetition_scan": {
    "disclaimer": "This is a data-limited note, not a statement about injury status or manager intent.",
    "per_card_limit": 1,
    "scope": "Team bullpen shape rendered public copy",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "example_source": "stored-data example",
  "fallback_status": "rendered",
  "pitcher": null,
  "raw_count_formula_scan": {
    "patterns": {
      "jargon_coupled_raw_count": "(?<![\\w-])\\d+\\s+of\\s+\\d+\\s+(?:trust|bridge|coverage|depth)\\s+arms?\\b",
      "parenthetical_raw_basis": "\\(\\s*\\d+\\s+of\\s+\\d+\\s*\\)",
      "parenthetical_unknown_formula": "\\([^)]*\\bunknown\\b[^)]*\\)",
      "raw_empty_arithmetic": "(?<![\\w-])\\d+\\s+of\\s+\\d+(?![\\w-])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "length option",
      "length options",
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "classified available",
      "0 of 0",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "trust metadata",
      "explained state",
      "availability read",
      "bullpen planning read",
      "explanation confidence mirrors",
      "confidence mirrors",
      "governed availability evidence",
      "state reflects",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "role_or_classification": {
    "read_labels": [
      "Stable Late-Inning Availability",
      "Healthy Rested Bullpen",
      "Elevated Late-Inning Pressure",
      "No Workload Concentration",
      "Stable Coverage Safety",
      "Limited Depth Safety"
    ]
  },
  "source_path": "services.team_bullpen_shape.build_team_bullpen_shape",
  "status": "team_shape",
  "surface_name": "Team bullpen shape explanations",
  "team": "Arizona Diamondbacks (AZ, 109)",
  "weighting_scoring_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "raw score",
      "scoring weight",
      "weighted pressure"
    ],
    "violation_count": 0,
    "violations": []
  }
}
```

Rendered public copy:
```
Stable Late-Inning Availability
The late-inning group has no late-inning arms fully rested and two late-inning arms worth monitoring. None of that group is blocked by a heavy recent workload signal.
Healthy Rested Bullpen
The bullpen has six arms fully rested, with four rested arms who fit the late-inning bridge. That gives the late innings more cushion if the starter exits early.
Elevated Late-Inning Pressure
The primary late-inning pocket has no arms fully rested and no arms carrying enough recent workload to narrow the path. The handoff innings add no arms with recent stress, and no arms are carrying heavy recent workload.
No Workload Concentration
Three arms have carried 49% of the recent relief work across nine bullpen arms.
Stable Coverage Safety
The bullpen has enough stored coverage to handle more than one relief inning.
The bullpen has nine relievers active in the stored board, with six relievers rested enough to cover innings.
The wider relief picture is strained, with no late anchors and six leverage arms near the back of the game.
The wider relief pool is strained, so coverage holds at stable rather than strong.
Limited Depth Safety
The lower-leverage layer has no arms who can cover softer innings, while no arms are carrying enough recent workload to limit the fallback cushion.
```

Structured fields used:

```json
{
  "reads": [
    {
      "explanation": "The late-inning group has no late-inning arms fully rested and two late-inning arms worth monitoring. None of that group is blocked by a heavy recent workload signal.",
      "key": "trustAvailability",
      "label": "Stable Late-Inning Availability",
      "reasons": [
        "The late-inning group has no late-inning arms fully rested and two late-inning arms worth monitoring. None of that group is blocked by a heavy recent workload signal."
      ],
      "supportingCounts": {
        "availableTrustArms": 2,
        "cleanTrustArms": 0,
        "limitedReadTrustArms": 0,
        "restRestrictedTrustArms": 0,
        "roleKnownCount": 8,
        "totalBullpenArms": 9,
        "trustArms": 2,
        "unavailableTrustArms": 0,
        "watchTrustArms": 2
      }
    },
    {
      "explanation": "The bullpen has six arms fully rested, with four rested arms who fit the late-inning bridge. That gives the late innings more cushion if the starter exits early.",
      "key": "cleanOptions",
      "label": "Healthy Rested Bullpen",
      "reasons": [
        "The bullpen has six arms fully rested, with four rested arms who fit the late-inning bridge. That gives the late innings more cushion if the starter exits early."
      ],
      "supportingCounts": {
        "activeBullpenArms": 9,
        "cleanBridgeArms": 4,
        "cleanCoverageArms": 1,
        "cleanDepthArms": 0,
        "cleanOptionCount": 6,
        "cleanTrustArms": 0,
        "limitedReadCount": 0,
        "meaningfulCleanBacking": true,
        "restRestrictedCount": 0,
        "totalBullpenArms": 9,
        "unavailableCount": 0
      }
    },
    {
      "explanation": "The primary late-inning pocket has no arms fully rested and no arms carrying enough recent workload to narrow the path. The handoff innings add no arms with recent stress, and no arms are carrying heavy recent workload.",
      "key": "bullpenPressure",
      "label": "Elevated Late-Inning Pressure",
      "reasons": [
        "The primary late-inning pocket has no arms fully rested and no arms carrying enough recent workload to narrow the path. The handoff innings add no arms with recent stress, and no arms are carrying heavy recent workload."
      ],
      "supportingCounts": {
        "cleanTrustArms": 0,
        "highFatigueArms": 0,
        "limitedReadCount": 0,
        "noUsableTrust": false,
        "restRestrictedCount": 0,
        "restrictedTrustArms": 0,
        "stressedBridgeArms": 0,
        "stressedCoverageArms": 0,
        "totalBullpenArms": 9,
        "unavailableCount": 0,
        "unavailableTrustArms": 0,
        "usableTrustArms": 2,
        "watchArmCount": 3
      }
    },
    {
      "explanation": "Three arms have carried 49% of the recent relief work across nine bullpen arms.",
      "key": "workloadConcentration",
      "label": "No Workload Concentration",
      "reasons": [
        "Three arms have carried 49% of the recent relief work across nine bullpen arms."
      ],
      "supportingCounts": {
        "concentrationDescriptor": "no concentration",
        "concentrationLevel": "none",
        "participantCount": 9,
        "perArmPitches": 22.333333333333332,
        "topArmCount": 3,
        "topOneShare": 0.21393034825870647,
        "topPitchTotal": 99,
        "topShare": 0.4925373134328358,
        "topSharePct": 49,
        "totalRecentPitches": 201,
        "windowDays": 7
      }
    },
    {
      "capability": "bullpen_coverage_safety_v2",
      "explanation": "The bullpen has enough stored coverage to handle more than one relief inning.",
      "key": "coverageSafety",
      "label": "Stable Coverage Safety",
      "limitations": [],
      "reasons": [
        "The bullpen has nine relievers active in the stored board, with six relievers rested enough to cover innings.",
        "The wider relief picture is strained, with no late anchors and six leverage arms near the back of the game.",
        "The wider relief pool is strained, so coverage holds at stable rather than strong."
      ],
      "source": "backend",
      "supportingCounts": {
        "activeRelieverCount": 9,
        "anchorCount": 0,
        "capacityState": "healthy",
        "cleanActiveRelieverCount": 6,
        "coverageSafetyVersion": "2.0",
        "environmentPressureSources": [
          "capacity_loss"
        ],
        "environmentStatus": "limited_read",
        "hierarchyConfidence": "medium",
        "leverageCount": 6,
        "resourceHealthState": "strained",
        "thresholds": {
          "stableMinCleanActiveRelievers": 3,
          "stableMinTrustedGroupSize": 4,
          "strongMinCleanActiveRelievers": 5,
          "strongMinTrustedGroupSize": 5,
          "thinTrustUnavailableMin": 2,
          "thinTrustUnavailablePct": 40
        },
        "topTrustBucketAvailableCount": 6,
        "trustArmsUnavailable": 0,
        "trustCapacityUnavailablePct": 0,
        "trustedCount": 1,
        "trustedGroupSize": 7
      },
      "version": "2026-06-19"
    },
    {
      "explanation": "The lower-leverage layer has no arms who can cover softer innings, while no arms are carrying enough recent workload to limit the fallback cushion.",
      "key": "depthSafety",
      "label": "Limited Depth Safety",
      "reasons": [
        "The lower-leverage layer has no arms who can cover softer innings, while no arms are carrying enough recent workload to limit the fallback cushion."
      ],
      "supportingCounts": {
        "activeBullpenArms": 9,
        "anchoredByTrust": true,
        "availableDepthArms": 0,
        "cleanDepthArms": 0,
        "depthArms": 0,
        "limitedReadDepthArms": 0,
        "restRestrictedDepthArms": 0,
        "roleKnownCount": 8,
        "totalBullpenArms": 9,
        "unavailableDepthArms": 0,
        "usableTrustArms": 2,
        "watchDepthArms": 0
      }
    }
  ],
  "source": "backend",
  "supportingCounts": {
    "activeBullpenArms": 9,
    "readKnownCount": 9,
    "roleKnownCount": 8,
    "totalBullpenArms": 9
  }
}
```

Evidence sections:

```json
{
  "read_count": 6,
  "read_keys": [
    "trustAvailability",
    "cleanOptions",
    "bullpenPressure",
    "workloadConcentration",
    "coverageSafety",
    "depthSafety"
  ]
}
```

### Example 19: Team bullpen board context

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "capitalization_sentence_scan": {
    "patterns": {
      "lowercase_sentence_start": "(?<=[.!?])\\s+([a-z])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "circular_meta_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "explanation confidence mirrors",
      "confidence mirrors",
      "visibility reflects existing availability confidence",
      "governed availability evidence",
      "state reflects",
      "explained state",
      "trust metadata",
      "readiness explanation confidence"
    ],
    "violation_count": 0,
    "violations": []
  },
  "disclaimer_repetition_scan": {
    "disclaimer": "This is a data-limited note, not a statement about injury status or manager intent.",
    "per_card_limit": 1,
    "scope": "Team bullpen shape rendered public copy",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "example_source": "stored-data example",
  "fallback_status": "rendered",
  "pitcher": null,
  "raw_count_formula_scan": {
    "patterns": {
      "jargon_coupled_raw_count": "(?<![\\w-])\\d+\\s+of\\s+\\d+\\s+(?:trust|bridge|coverage|depth)\\s+arms?\\b",
      "parenthetical_raw_basis": "\\(\\s*\\d+\\s+of\\s+\\d+\\s*\\)",
      "parenthetical_unknown_formula": "\\([^)]*\\bunknown\\b[^)]*\\)",
      "raw_empty_arithmetic": "(?<![\\w-])\\d+\\s+of\\s+\\d+(?![\\w-])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "length option",
      "length options",
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "classified available",
      "0 of 0",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "trust metadata",
      "explained state",
      "availability read",
      "bullpen planning read",
      "explanation confidence mirrors",
      "confidence mirrors",
      "governed availability evidence",
      "state reflects",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "role_or_classification": {
    "total_pitchers": 8,
    "ungrouped_pitchers": 0
  },
  "source_path": "api.bullpen._build_team_board -> services.bullpen_board.build_board_payload",
  "status": "monitoring",
  "surface_name": "Team bullpen board context",
  "team": "Baltimore Orioles (BAL, 110)",
  "weighting_scoring_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "raw score",
      "scoring weight",
      "weighted pressure"
    ],
    "violation_count": 0,
    "violations": []
  }
}
```

Rendered public copy:
```
Several relievers need a workload check.
One reliever is available from the latest completed workload data.
No relievers are marked Avoid or Unavailable.
Five relievers are in the Monitor group.
Availability classifications are workload-based only.
Available
Workload signals are inside normal ranges in the latest completed data.
Monitor
Worth a look at recent workload before counting on these arms.
Limited
Recent workload suggests limited use from the latest completed data.
Avoid
Meaningful recent-use load on these arms.
Unavailable Pitchers
Not available from the latest public workload and roster context.
```

Structured fields used:

```json
{
  "context": {
    "confidence": "high",
    "health": {
      "label": "Several relievers need a workload check.",
      "reasons": [
        "One reliever is available from the latest completed workload data.",
        "No relievers are marked Avoid or Unavailable.",
        "Five relievers are in the Monitor group.",
        "Availability classifications are workload-based only."
      ],
      "state": "monitoring"
    },
    "limitations": [],
    "metrics": {
      "available": 1,
      "avoid": 0,
      "limited": 2,
      "monitor": 5,
      "pct_available": 12,
      "pct_restricted": 0,
      "pct_unavailable": 0,
      "restricted": 0,
      "total_relievers": 8,
      "unavailable": 0
    }
  },
  "freshness": {
    "active_cutoff_date": "2026-06-16",
    "active_window_days": 14,
    "availability_reference_date": "2026-06-30",
    "data_age_days": 1,
    "data_through": "2026-06-29",
    "degradation": {
      "data_age_days": 1,
      "fail_closed": false,
      "stale_after_days": 14,
      "state": "fresh",
      "unavailable_after_days": 30
    },
    "degradation_state": "fresh",
    "fail_closed": false,
    "freshness_state": "current",
    "is_current": true,
    "is_stale": false,
    "label": "Current baseball data through 2026-06-29.",
    "last_completed_game_refresh": "2026-06-30T07:13:03.808628Z",
    "last_morning_full_sync": "2026-06-30T10:02:10.485036Z",
    "last_successful_sync": "2026-06-30T10:02:10.485036Z",
    "latest_workload_date": "2026-06-29",
    "limitations": [],
    "reason_codes": [],
    "reference_date": "2026-06-30",
    "sync_authority": "sync_runs",
    "sync_status": "success"
  },
  "groups": [
    {
      "count": 1,
      "description": "Workload signals are inside normal ranges in the latest completed data.",
      "label": "Available",
      "status": "Available"
    },
    {
      "count": 5,
      "description": "Worth a look at recent workload before counting on these arms.",
      "label": "Monitor",
      "status": "Monitor"
    },
    {
      "count": 2,
      "description": "Recent workload suggests limited use from the latest completed data.",
      "label": "Limited",
      "status": "Limited"
    },
    {
      "count": 0,
      "description": "Meaningful recent-use load on these arms.",
      "label": "Avoid",
      "status": "Avoid"
    },
    {
      "count": 0,
      "description": "Not available from the latest public workload and roster context.",
      "label": "Unavailable Pitchers",
      "status": "Unavailable"
    }
  ],
  "limitations": []
}
```

Evidence sections:

```json
{
  "group_counts": {
    "Available": 1,
    "Avoid": 0,
    "Limited": 2,
    "Monitor": 5,
    "Unavailable": 0
  },
  "roster_authority_summary": {
    "limitations": [],
    "population": {
      "known_count": 17,
      "roster_status_coverage": 1.0,
      "total_candidates": 17,
      "unknown_count": 0
    }
  }
}
```

### Example 20: Team bullpen shape explanations

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "capitalization_sentence_scan": {
    "patterns": {
      "lowercase_sentence_start": "(?<=[.!?])\\s+([a-z])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "circular_meta_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "explanation confidence mirrors",
      "confidence mirrors",
      "visibility reflects existing availability confidence",
      "governed availability evidence",
      "state reflects",
      "explained state",
      "trust metadata",
      "readiness explanation confidence"
    ],
    "violation_count": 0,
    "violations": []
  },
  "disclaimer_repetition_scan": {
    "disclaimer": "This is a data-limited note, not a statement about injury status or manager intent.",
    "per_card_limit": 1,
    "scope": "Team bullpen shape rendered public copy",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "example_source": "stored-data example",
  "fallback_status": "rendered",
  "pitcher": null,
  "raw_count_formula_scan": {
    "patterns": {
      "jargon_coupled_raw_count": "(?<![\\w-])\\d+\\s+of\\s+\\d+\\s+(?:trust|bridge|coverage|depth)\\s+arms?\\b",
      "parenthetical_raw_basis": "\\(\\s*\\d+\\s+of\\s+\\d+\\s*\\)",
      "parenthetical_unknown_formula": "\\([^)]*\\bunknown\\b[^)]*\\)",
      "raw_empty_arithmetic": "(?<![\\w-])\\d+\\s+of\\s+\\d+(?![\\w-])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "length option",
      "length options",
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "classified available",
      "0 of 0",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "trust metadata",
      "explained state",
      "availability read",
      "bullpen planning read",
      "explanation confidence mirrors",
      "confidence mirrors",
      "governed availability evidence",
      "state reflects",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "role_or_classification": {
    "read_labels": [
      "Stable Late-Inning Availability",
      "Very Thin Rested Bullpen",
      "High Late-Inning Pressure",
      "No Workload Concentration",
      "Thin Coverage Safety",
      "Limited Depth Safety"
    ]
  },
  "source_path": "services.team_bullpen_shape.build_team_bullpen_shape",
  "status": "team_shape",
  "surface_name": "Team bullpen shape explanations",
  "team": "Baltimore Orioles (BAL, 110)",
  "weighting_scoring_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "raw score",
      "scoring weight",
      "weighted pressure"
    ],
    "violation_count": 0,
    "violations": []
  }
}
```

Rendered public copy:
```
Stable Late-Inning Availability
The late-inning group has one late-inning arm fully rested and two late-inning arms worth monitoring. One late-inning arm is carrying enough recent workload to narrow the late-game path.
Very Thin Rested Bullpen
Only one arm is fully rested, with one rested arm who fits the late-inning bridge. The rest of the group looks more like depth coverage than leverage cushion.
High Late-Inning Pressure
The primary late-inning pocket has one arm fully rested and one arm carrying enough recent workload to narrow the path. The handoff innings add one arm with recent stress, and no arms are carrying heavy recent workload.
No Workload Concentration
Three arms have carried 49% of the recent relief work across eight bullpen arms.
Thin Coverage Safety
The bullpen has some coverage, but less room if the starter exits early.
The bullpen has eight relievers active in the stored board, with one reliever rested enough to cover innings.
The wider relief picture is strained, with no late anchors and five leverage arms near the back of the game.
Coverage reads thin because the rested group or late-inning availability is already tight.
Limited Depth Safety
The lower-leverage layer has no arms who can cover softer innings, while no arms are carrying enough recent workload to limit the fallback cushion.
```

Structured fields used:

```json
{
  "reads": [
    {
      "explanation": "The late-inning group has one late-inning arm fully rested and two late-inning arms worth monitoring. One late-inning arm is carrying enough recent workload to narrow the late-game path.",
      "key": "trustAvailability",
      "label": "Stable Late-Inning Availability",
      "reasons": [
        "The late-inning group has one late-inning arm fully rested and two late-inning arms worth monitoring. One late-inning arm is carrying enough recent workload to narrow the late-game path."
      ],
      "supportingCounts": {
        "availableTrustArms": 3,
        "cleanTrustArms": 1,
        "limitedReadTrustArms": 0,
        "restRestrictedTrustArms": 1,
        "roleKnownCount": 8,
        "totalBullpenArms": 8,
        "trustArms": 4,
        "unavailableTrustArms": 0,
        "watchTrustArms": 2
      }
    },
    {
      "explanation": "Only one arm is fully rested, with one rested arm who fits the late-inning bridge. The rest of the group looks more like depth coverage than leverage cushion.",
      "key": "cleanOptions",
      "label": "Very Thin Rested Bullpen",
      "reasons": [
        "Only one arm is fully rested, with one rested arm who fits the late-inning bridge. The rest of the group looks more like depth coverage than leverage cushion."
      ],
      "supportingCounts": {
        "activeBullpenArms": 8,
        "cleanBridgeArms": 0,
        "cleanCoverageArms": 0,
        "cleanDepthArms": 0,
        "cleanOptionCount": 1,
        "cleanTrustArms": 1,
        "limitedReadCount": 0,
        "meaningfulCleanBacking": true,
        "restRestrictedCount": 2,
        "totalBullpenArms": 8,
        "unavailableCount": 0
      }
    },
    {
      "explanation": "The primary late-inning pocket has one arm fully rested and one arm carrying enough recent workload to narrow the path. The handoff innings add one arm with recent stress, and no arms are carrying heavy recent workload.",
      "key": "bullpenPressure",
      "label": "High Late-Inning Pressure",
      "reasons": [
        "The primary late-inning pocket has one arm fully rested and one arm carrying enough recent workload to narrow the path. The handoff innings add one arm with recent stress, and no arms are carrying heavy recent workload."
      ],
      "supportingCounts": {
        "cleanTrustArms": 1,
        "highFatigueArms": 0,
        "limitedReadCount": 0,
        "noUsableTrust": false,
        "restRestrictedCount": 2,
        "restrictedTrustArms": 1,
        "stressedBridgeArms": 1,
        "stressedCoverageArms": 0,
        "totalBullpenArms": 8,
        "unavailableCount": 0,
        "unavailableTrustArms": 0,
        "usableTrustArms": 3,
        "watchArmCount": 5
      }
    },
    {
      "explanation": "Three arms have carried 49% of the recent relief work across eight bullpen arms.",
      "key": "workloadConcentration",
      "label": "No Workload Concentration",
      "reasons": [
        "Three arms have carried 49% of the recent relief work across eight bullpen arms."
      ],
      "supportingCounts": {
        "concentrationDescriptor": "no concentration",
        "concentrationLevel": "none",
        "participantCount": 8,
        "perArmPitches": 38.5,
        "topArmCount": 3,
        "topOneShare": 0.16883116883116883,
        "topPitchTotal": 151,
        "topShare": 0.4902597402597403,
        "topSharePct": 49,
        "totalRecentPitches": 308,
        "windowDays": 7
      }
    },
    {
      "capability": "bullpen_coverage_safety_v2",
      "explanation": "The bullpen has some coverage, but less room if the starter exits early.",
      "key": "coverageSafety",
      "label": "Thin Coverage Safety",
      "limitations": [],
      "reasons": [
        "The bullpen has eight relievers active in the stored board, with one reliever rested enough to cover innings.",
        "The wider relief picture is strained, with no late anchors and five leverage arms near the back of the game.",
        "Coverage reads thin because the rested group or late-inning availability is already tight."
      ],
      "source": "backend",
      "supportingCounts": {
        "activeRelieverCount": 8,
        "anchorCount": 0,
        "capacityState": "thin",
        "cleanActiveRelieverCount": 1,
        "coverageSafetyVersion": "2.0",
        "environmentPressureSources": [
          "capacity_loss"
        ],
        "environmentStatus": "pressure_with_context",
        "hierarchyConfidence": "medium",
        "leverageCount": 5,
        "resourceHealthState": "strained",
        "thresholds": {
          "stableMinCleanActiveRelievers": 3,
          "stableMinTrustedGroupSize": 4,
          "strongMinCleanActiveRelievers": 5,
          "strongMinTrustedGroupSize": 5,
          "thinTrustUnavailableMin": 2,
          "thinTrustUnavailablePct": 40
        },
        "topTrustBucketAvailableCount": 5,
        "trustArmsUnavailable": 0,
        "trustCapacityUnavailablePct": 0,
        "trustedCount": 0,
        "trustedGroupSize": 5
      },
      "version": "2026-06-19"
    },
    {
      "explanation": "The lower-leverage layer has no arms who can cover softer innings, while no arms are carrying enough recent workload to limit the fallback cushion.",
      "key": "depthSafety",
      "label": "Limited Depth Safety",
      "reasons": [
        "The lower-leverage layer has no arms who can cover softer innings, while no arms are carrying enough recent workload to limit the fallback cushion."
      ],
      "supportingCounts": {
        "activeBullpenArms": 8,
        "anchoredByTrust": true,
        "availableDepthArms": 0,
        "cleanDepthArms": 0,
        "depthArms": 0,
        "limitedReadDepthArms": 0,
        "restRestrictedDepthArms": 0,
        "roleKnownCount": 8,
        "totalBullpenArms": 8,
        "unavailableDepthArms": 0,
        "usableTrustArms": 3,
        "watchDepthArms": 0
      }
    }
  ],
  "source": "backend",
  "supportingCounts": {
    "activeBullpenArms": 8,
    "readKnownCount": 8,
    "roleKnownCount": 8,
    "totalBullpenArms": 8
  }
}
```

Evidence sections:

```json
{
  "read_count": 6,
  "read_keys": [
    "trustAvailability",
    "cleanOptions",
    "bullpenPressure",
    "workloadConcentration",
    "coverageSafety",
    "depthSafety"
  ]
}
```

### Example 21: Team Operations readiness V4 explanation

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "capitalization_sentence_scan": {
    "patterns": {
      "lowercase_sentence_start": "(?<=[.!?])\\s+([a-z])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "circular_meta_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "explanation confidence mirrors",
      "confidence mirrors",
      "visibility reflects existing availability confidence",
      "governed availability evidence",
      "state reflects",
      "explained state",
      "trust metadata",
      "readiness explanation confidence"
    ],
    "violation_count": 0,
    "violations": []
  },
  "disclaimer_repetition_scan": {
    "disclaimer": "This is a data-limited note, not a statement about injury status or manager intent.",
    "per_card_limit": 1,
    "scope": "Team bullpen shape rendered public copy",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "example_source": "stored-data example",
  "fallback_status": "data_limited",
  "pitcher": null,
  "raw_count_formula_scan": {
    "patterns": {
      "jargon_coupled_raw_count": "(?<![\\w-])\\d+\\s+of\\s+\\d+\\s+(?:trust|bridge|coverage|depth)\\s+arms?\\b",
      "parenthetical_raw_basis": "\\(\\s*\\d+\\s+of\\s+\\d+\\s*\\)",
      "parenthetical_unknown_formula": "\\([^)]*\\bunknown\\b[^)]*\\)",
      "raw_empty_arithmetic": "(?<![\\w-])\\d+\\s+of\\s+\\d+(?![\\w-])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "length option",
      "length options",
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "classified available",
      "0 of 0",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "trust metadata",
      "explained state",
      "availability read",
      "bullpen planning read",
      "explanation confidence mirrors",
      "confidence mirrors",
      "governed availability evidence",
      "state reflects",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "role_or_classification": {
    "readiness_status": "Limited Visibility",
    "readiness_status_code": "data_limited",
    "scope": "readiness_state"
  },
  "source_path": "api.explanations._team_readiness_payload_from_request -> explanations.readiness.serialize_readiness_explanation",
  "status": "data_limited",
  "surface_name": "Team Operations readiness V4 explanation",
  "team": "Los Angeles Angels (LAA, 108)",
  "weighting_scoring_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "raw score",
      "scoring weight",
      "weighted pressure"
    ],
    "violation_count": 0,
    "violations": []
  }
}
```

Rendered public copy:
```
The public data is not strong enough to give this team a full bullpen readiness note.
A heavy recent stretch has the workload up.
Some of the public workload detail is incomplete.
The public data is not strong enough for a fuller explanation.
Readiness is based on public workload data, not private team information.
Readiness is not injury or medical information.
Readiness is not a performance forecast.
Manager intent and bullpen warm-up state are not available.
The user remains responsible for baseball decisions.
Some active pitcher records have incomplete readiness evidence.
The safest read is limited until the public workload picture is stronger.
The stored workload data is current enough for this team note.
The safest note stays limited until the public workload picture is stronger.
```

Structured fields used:

```json
{
  "availability_distribution": {
    "available": 5,
    "avoid": 2,
    "limited": 4,
    "monitor": 7,
    "total": 19,
    "unavailable": 1,
    "unknown": 0
  },
  "constraints": [
    {
      "affected_area": "trust_metadata",
      "category": "trust",
      "constraint_id": "trust_metadata_limited",
      "count": 1,
      "evidence": [
        "confidence: low",
        "data_state: incomplete"
      ],
      "message": "The public workload record is not strong enough for a full readiness summary.",
      "severity": "caution"
    },
    {
      "affected_area": "coverage_inventory",
      "category": "coverage",
      "constraint_id": "coverage_partial",
      "count": 6,
      "evidence": [
        "missing_workload_data_count: 6",
        "availability_missing_count: 0"
      ],
      "message": "Some active pitcher records have incomplete readiness evidence.",
      "severity": "caution"
    },
    {
      "affected_area": "workload_pressure",
      "category": "workload",
      "constraint_id": "workload_elevated",
      "count": 3,
      "evidence": [
        "elevated_count: 3"
      ],
      "message": "Elevated team-level workload pressure is present.",
      "severity": "caution"
    },
    {
      "affected_area": "availability_distribution",
      "category": "availability",
      "constraint_id": "availability_constrained",
      "count": 3,
      "evidence": [
        "avoid_or_unavailable_count: 3"
      ],
      "message": "Availability distribution contains constrained inventory.",
      "severity": "caution"
    }
  ],
  "coverage_inventory": {
    "active_pitcher_count": 19,
    "availability_covered_count": 19,
    "availability_missing_count": 0,
    "coverage_state": "partial",
    "current_workload_data_count": 13,
    "missing_workload_data_count": 6
  },
  "freshness": {
    "data_through": "2026-06-29",
    "freshness_state": "current",
    "generated_at": "2026-06-30T10:00:47",
    "last_successful_sync": "2026-06-30T10:02:10.485036Z",
    "latest_fatigue_calculated_at": "2026-06-30T10:00:50.892219Z",
    "latest_sync_status": "success",
    "latest_workload_date": "2026-06-29",
    "limitations": [],
    "missing_data_warning": null,
    "stale_warning": null
  },
  "handedness_coverage": {
    "coverage_state": "covered",
    "left_handed_count": 7,
    "limitations": [],
    "right_handed_count": 12,
    "unknown_count": 0
  },
  "readiness": {
    "basis": [
      "availability_distribution",
      "workload_pressure",
      "freshness",
      "trust_metadata"
    ],
    "status": "Limited Visibility",
    "status_code": "data_limited",
    "summary": "Team-level bullpen visibility is limited by freshness, trust, or coverage evidence."
  },
  "trust_metadata": {
    "capability": "team_operations_bullpen_readiness",
    "confidence": "low",
    "confidence_reasons": [
      "limited_availability_evidence"
    ],
    "data_state": "incomplete",
    "explanations": [],
    "generated_at": "2026-06-30T10:00:47",
    "governance_state": "internal_uncertified",
    "limitations": [],
    "ranking_applied": false,
    "refusal_reasons": [],
    "scope": "team_bullpen_readiness",
    "selection_made": false,
    "source_evidence_state": "represented",
    "trust_validation_errors": []
  },
  "workload_pressure": {
    "elevated_count": 3,
    "latest_workload_date": "2026-06-29",
    "low_count": 4,
    "moderate_count": 6,
    "pressure_state": "elevated",
    "pressure_state_code": "elevated",
    "summary": "Recent workload pressure is elevated at the team level.",
    "unknown_count": 6
  }
}
```

Evidence sections:

```json
{
  "limitations": [
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "insufficient_context",
      "severity": "informational",
      "summary": "Readiness is based on public workload data, not private team information."
    },
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "insufficient_context",
      "severity": "informational",
      "summary": "Readiness is not injury or medical information."
    },
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "insufficient_context",
      "severity": "informational",
      "summary": "Readiness is not a performance forecast."
    },
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "insufficient_context",
      "severity": "informational",
      "summary": "Manager intent and bullpen warm-up state are not available."
    },
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "insufficient_context",
      "severity": "informational",
      "summary": "The user remains responsible for baseball decisions."
    },
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "partial_coverage",
      "severity": "limits_confidence",
      "summary": "Some active pitcher records have incomplete readiness evidence."
    },
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "limited_confidence",
      "severity": "limits_confidence",
      "summary": "The safest read is limited until the public workload picture is stronger."
    }
  ],
  "primary_reasons": [
    {
      "code": "READINESS_DEGRADED_BY_LIMITATIONS",
      "label": "Readiness degraded by limitations",
      "scope": "readiness_state",
      "summary": "The public data is not strong enough to give this team a full bullpen readiness note."
    },
    {
      "code": "WORKLOAD_RECENT_USAGE_ELEVATED",
      "label": "Recent usage elevated",
      "scope": "workload_state",
      "summary": "A heavy recent stretch has the workload up."
    },
    {
      "code": "COVERAGE_PARTIAL",
      "label": "Coverage partial",
      "scope": "coverage_state",
      "summary": "Some of the public workload detail is incomplete."
    },
    {
      "code": "TRUST_LIMITED",
      "label": "Trust limited",
      "scope": "trust_state",
      "summary": "The public data is not strong enough for a fuller explanation."
    }
  ],
  "supporting_evidence": [
    {
      "evidence_type": "readiness_status",
      "impact": "explains_readiness_state",
      "label": "Readiness status",
      "source": "team_operations_bullpen_readiness",
      "unit": "status",
      "value": "Limited Visibility"
    },
    {
      "evidence_type": "readiness_status_code",
      "impact": "explains_readiness_state",
      "label": "Readiness status code",
      "source": "team_operations_bullpen_readiness",
      "unit": "status_code",
      "value": "data_limited"
    },
    {
      "evidence_type": "readiness_contract_state",
      "impact": "explains_output_boundary",
      "label": "Readiness contract state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "degraded"
    },
    {
      "evidence_type": "readiness_basis",
      "impact": "explains_input_scope",
      "label": "Readiness basis",
      "source": "team_operations_bullpen_readiness",
      "unit": "sources",
      "value": [
        "availability_distribution",
        "workload_pressure",
        "freshness",
        "trust_metadata"
      ]
    },
    {
      "evidence_type": "readiness_freshness_state",
      "impact": "explains_freshness_boundary",
      "label": "Freshness state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "current"
    },
    {
      "evidence_type": "readiness_trust_confidence",
      "impact": "explains_confidence_boundary",
      "label": "Trust confidence",
      "source": "team_operations_bullpen_readiness",
      "unit": "level",
      "value": "low"
    },
    {
      "evidence_type": "readiness_trust_data_state",
      "impact": "explains_trust_boundary",
      "label": "Trust data state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "incomplete"
    },
    {
      "evidence_type": "workload_pressure_state",
      "impact": "explains_workload_state",
      "label": "Workload pressure state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "elevated"
    },
    {
      "evidence_type": "coverage_inventory_state",
      "impact": "explains_coverage_state",
      "label": "Coverage inventory state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "partial"
    },
    {
      "evidence_type": "handedness_coverage_state",
      "impact": "explains_coverage_state",
      "label": "Handedness coverage state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "covered"
    },
    {
      "evidence_type": "workload_pressure_low_count",
      "impact": "explains_workload_state",
      "label": "Low workload count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 4
    },
    {
      "evidence_type": "workload_pressure_moderate_count",
      "impact": "explains_workload_state",
      "label": "Moderate workload count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 6
    },
    {
      "evidence_type": "workload_pressure_elevated_count",
      "impact": "explains_workload_state",
      "label": "Elevated workload count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 3
    },
    {
      "evidence_type": "workload_pressure_unknown_count",
      "impact": "explains_workload_state",
      "label": "Unknown workload count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 6
    },
    {
      "evidence_type": "availability_distribution_available",
      "impact": "explains_availability_state",
      "label": "Available inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 5
    },
    {
      "evidence_type": "availability_distribution_monitor",
      "impact": "explains_availability_state",
      "label": "Monitor inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 7
    },
    {
      "evidence_type": "availability_distribution_limited",
      "impact": "explains_availability_state",
      "label": "Limited inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 4
    },
    {
      "evidence_type": "availability_distribution_avoid",
      "impact": "explains_availability_state",
      "label": "Avoid inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 2
    },
    {
      "evidence_type": "availability_distribution_unavailable",
      "impact": "explains_availability_state",
      "label": "Unavailable inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 1
    },
    {
      "evidence_type": "availability_distribution_unknown",
      "impact": "explains_availability_state",
      "label": "Unknown availability count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 0
    },
    {
      "evidence_type": "availability_distribution_total",
      "impact": "explains_availability_state",
      "label": "Total availability inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 19
    },
    {
      "evidence_type": "coverage_inventory_active_pitcher_count",
      "impact": "explains_coverage_state",
      "label": "Active pitcher count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 19
    },
    {
      "evidence_type": "coverage_inventory_current_workload_data_count",
      "impact": "explains_coverage_state",
      "label": "Current workload data count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 13
    },
    {
      "evidence_type": "coverage_inventory_missing_workload_data_count",
      "impact": "explains_coverage_state",
      "label": "Missing workload data count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 6
    },
    {
      "evidence_type": "coverage_inventory_availability_covered_count",
      "impact": "explains_coverage_state",
      "label": "Availability covered count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 19
    },
    {
      "evidence_type": "coverage_inventory_availability_missing_count",
      "impact": "explains_coverage_state",
      "label": "Availability missing count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 0
    },
    {
      "evidence_type": "handedness_coverage_left_handed_count",
      "impact": "explains_coverage_state",
      "label": "Left handed count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 7
    },
    {
      "evidence_type": "handedness_coverage_right_handed_count",
      "impact": "explains_coverage_state",
      "label": "Right handed count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 12
    },
    {
      "evidence_type": "handedness_coverage_unknown_count",
      "impact": "explains_coverage_state",
      "label": "Unknown handedness count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 0
    },
    {
      "evidence_type": "readiness_constraint_trust_metadata_limited",
      "impact": "explains_readiness_limitation",
      "label": "Readiness constraint trust_metadata_limited",
      "source": "team_operations_bullpen_readiness",
      "unit": "constraint",
      "value": {
        "affected_area": "trust_metadata",
        "category": "trust",
        "count": 1,
        "evidence": [
          "confidence: low",
          "data_state: incomplete"
        ],
        "message": "The public workload record is not strong enough for a full readiness summary.",
        "severity": "caution"
      }
    },
    {
      "evidence_type": "readiness_constraint_coverage_partial",
      "impact": "explains_readiness_limitation",
      "label": "Readiness constraint coverage_partial",
      "source": "team_operations_bullpen_readiness",
      "unit": "constraint",
      "value": {
        "affected_area": "coverage_inventory",
        "category": "coverage",
        "count": 6,
        "evidence": [
          "missing_workload_data_count: 6",
          "availability_missing_count: 0"
        ],
        "message": "Some active pitcher records have incomplete readiness evidence.",
        "severity": "caution"
      }
    },
    {
      "evidence_type": "readiness_constraint_workload_elevated",
      "impact": "explains_readiness_limitation",
      "label": "Readiness constraint workload_elevated",
      "source": "team_operations_bullpen_readiness",
      "unit": "constraint",
      "value": {
        "affected_area": "workload_pressure",
        "category": "workload",
        "count": 3,
        "evidence": [
          "elevated_count: 3"
        ],
        "message": "Elevated team-level workload pressure is present.",
        "severity": "caution"
      }
    },
    {
      "evidence_type": "readiness_constraint_availability_constrained",
      "impact": "explains_readiness_limitation",
      "label": "Readiness constraint availability_constrained",
      "source": "team_operations_bullpen_readiness",
      "unit": "constraint",
      "value": {
        "affected_area": "availability_distribution",
        "category": "availability",
        "count": 3,
        "evidence": [
          "avoid_or_unavailable_count: 3"
        ],
        "message": "Availability distribution contains constrained inventory.",
        "severity": "caution"
      }
    }
  ]
}
```

### Example 22: Team Operations readiness V4 explanation

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "capitalization_sentence_scan": {
    "patterns": {
      "lowercase_sentence_start": "(?<=[.!?])\\s+([a-z])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "circular_meta_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "explanation confidence mirrors",
      "confidence mirrors",
      "visibility reflects existing availability confidence",
      "governed availability evidence",
      "state reflects",
      "explained state",
      "trust metadata",
      "readiness explanation confidence"
    ],
    "violation_count": 0,
    "violations": []
  },
  "disclaimer_repetition_scan": {
    "disclaimer": "This is a data-limited note, not a statement about injury status or manager intent.",
    "per_card_limit": 1,
    "scope": "Team bullpen shape rendered public copy",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "example_source": "stored-data example",
  "fallback_status": "data_limited",
  "pitcher": null,
  "raw_count_formula_scan": {
    "patterns": {
      "jargon_coupled_raw_count": "(?<![\\w-])\\d+\\s+of\\s+\\d+\\s+(?:trust|bridge|coverage|depth)\\s+arms?\\b",
      "parenthetical_raw_basis": "\\(\\s*\\d+\\s+of\\s+\\d+\\s*\\)",
      "parenthetical_unknown_formula": "\\([^)]*\\bunknown\\b[^)]*\\)",
      "raw_empty_arithmetic": "(?<![\\w-])\\d+\\s+of\\s+\\d+(?![\\w-])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "length option",
      "length options",
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "classified available",
      "0 of 0",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "trust metadata",
      "explained state",
      "availability read",
      "bullpen planning read",
      "explanation confidence mirrors",
      "confidence mirrors",
      "governed availability evidence",
      "state reflects",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "role_or_classification": {
    "readiness_status": "Limited Visibility",
    "readiness_status_code": "data_limited",
    "scope": "workload_state"
  },
  "source_path": "api.explanations._team_readiness_payload_from_request -> explanations.readiness.serialize_readiness_explanation",
  "status": "elevated",
  "surface_name": "Team Operations readiness V4 explanation",
  "team": "Los Angeles Angels (LAA, 108)",
  "weighting_scoring_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "raw score",
      "scoring weight",
      "weighted pressure"
    ],
    "violation_count": 0,
    "violations": []
  }
}
```

Rendered public copy:
```
This note focuses on whether recent workload is pressing on the bullpen.
The public data is not strong enough to give this team a full bullpen readiness note.
A heavy recent stretch has the workload up.
Some of the public workload detail is incomplete.
The public data is not strong enough for a fuller explanation.
Readiness is based on public workload data, not private team information.
Readiness is not injury or medical information.
Readiness is not a performance forecast.
Manager intent and bullpen warm-up state are not available.
The user remains responsible for baseball decisions.
Some active pitcher records have incomplete readiness evidence.
The safest read is limited until the public workload picture is stronger.
The stored workload data is current enough for this team note.
The safest note stays limited until the public workload picture is stronger.
```

Structured fields used:

```json
{
  "availability_distribution": {
    "available": 5,
    "avoid": 2,
    "limited": 4,
    "monitor": 7,
    "total": 19,
    "unavailable": 1,
    "unknown": 0
  },
  "constraints": [
    {
      "affected_area": "trust_metadata",
      "category": "trust",
      "constraint_id": "trust_metadata_limited",
      "count": 1,
      "evidence": [
        "confidence: low",
        "data_state: incomplete"
      ],
      "message": "The public workload record is not strong enough for a full readiness summary.",
      "severity": "caution"
    },
    {
      "affected_area": "coverage_inventory",
      "category": "coverage",
      "constraint_id": "coverage_partial",
      "count": 6,
      "evidence": [
        "missing_workload_data_count: 6",
        "availability_missing_count: 0"
      ],
      "message": "Some active pitcher records have incomplete readiness evidence.",
      "severity": "caution"
    },
    {
      "affected_area": "workload_pressure",
      "category": "workload",
      "constraint_id": "workload_elevated",
      "count": 3,
      "evidence": [
        "elevated_count: 3"
      ],
      "message": "Elevated team-level workload pressure is present.",
      "severity": "caution"
    },
    {
      "affected_area": "availability_distribution",
      "category": "availability",
      "constraint_id": "availability_constrained",
      "count": 3,
      "evidence": [
        "avoid_or_unavailable_count: 3"
      ],
      "message": "Availability distribution contains constrained inventory.",
      "severity": "caution"
    }
  ],
  "coverage_inventory": {
    "active_pitcher_count": 19,
    "availability_covered_count": 19,
    "availability_missing_count": 0,
    "coverage_state": "partial",
    "current_workload_data_count": 13,
    "missing_workload_data_count": 6
  },
  "freshness": {
    "data_through": "2026-06-29",
    "freshness_state": "current",
    "generated_at": "2026-06-30T10:00:47",
    "last_successful_sync": "2026-06-30T10:02:10.485036Z",
    "latest_fatigue_calculated_at": "2026-06-30T10:00:50.892219Z",
    "latest_sync_status": "success",
    "latest_workload_date": "2026-06-29",
    "limitations": [],
    "missing_data_warning": null,
    "stale_warning": null
  },
  "handedness_coverage": {
    "coverage_state": "covered",
    "left_handed_count": 7,
    "limitations": [],
    "right_handed_count": 12,
    "unknown_count": 0
  },
  "readiness": {
    "basis": [
      "availability_distribution",
      "workload_pressure",
      "freshness",
      "trust_metadata"
    ],
    "status": "Limited Visibility",
    "status_code": "data_limited",
    "summary": "Team-level bullpen visibility is limited by freshness, trust, or coverage evidence."
  },
  "trust_metadata": {
    "capability": "team_operations_bullpen_readiness",
    "confidence": "low",
    "confidence_reasons": [
      "limited_availability_evidence"
    ],
    "data_state": "incomplete",
    "explanations": [],
    "generated_at": "2026-06-30T10:00:47",
    "governance_state": "internal_uncertified",
    "limitations": [],
    "ranking_applied": false,
    "refusal_reasons": [],
    "scope": "team_bullpen_readiness",
    "selection_made": false,
    "source_evidence_state": "represented",
    "trust_validation_errors": []
  },
  "workload_pressure": {
    "elevated_count": 3,
    "latest_workload_date": "2026-06-29",
    "low_count": 4,
    "moderate_count": 6,
    "pressure_state": "elevated",
    "pressure_state_code": "elevated",
    "summary": "Recent workload pressure is elevated at the team level.",
    "unknown_count": 6
  }
}
```

Evidence sections:

```json
{
  "limitations": [
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "insufficient_context",
      "severity": "informational",
      "summary": "Readiness is based on public workload data, not private team information."
    },
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "insufficient_context",
      "severity": "informational",
      "summary": "Readiness is not injury or medical information."
    },
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "insufficient_context",
      "severity": "informational",
      "summary": "Readiness is not a performance forecast."
    },
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "insufficient_context",
      "severity": "informational",
      "summary": "Manager intent and bullpen warm-up state are not available."
    },
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "insufficient_context",
      "severity": "informational",
      "summary": "The user remains responsible for baseball decisions."
    },
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "partial_coverage",
      "severity": "limits_confidence",
      "summary": "Some active pitcher records have incomplete readiness evidence."
    },
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "limited_confidence",
      "severity": "limits_confidence",
      "summary": "The safest read is limited until the public workload picture is stronger."
    }
  ],
  "primary_reasons": [
    {
      "code": "READINESS_DEGRADED_BY_LIMITATIONS",
      "label": "Readiness degraded by limitations",
      "scope": "readiness_state",
      "summary": "The public data is not strong enough to give this team a full bullpen readiness note."
    },
    {
      "code": "WORKLOAD_RECENT_USAGE_ELEVATED",
      "label": "Recent usage elevated",
      "scope": "workload_state",
      "summary": "A heavy recent stretch has the workload up."
    },
    {
      "code": "COVERAGE_PARTIAL",
      "label": "Coverage partial",
      "scope": "coverage_state",
      "summary": "Some of the public workload detail is incomplete."
    },
    {
      "code": "TRUST_LIMITED",
      "label": "Trust limited",
      "scope": "trust_state",
      "summary": "The public data is not strong enough for a fuller explanation."
    }
  ],
  "supporting_evidence": [
    {
      "evidence_type": "readiness_status",
      "impact": "explains_readiness_state",
      "label": "Readiness status",
      "source": "team_operations_bullpen_readiness",
      "unit": "status",
      "value": "Limited Visibility"
    },
    {
      "evidence_type": "readiness_status_code",
      "impact": "explains_readiness_state",
      "label": "Readiness status code",
      "source": "team_operations_bullpen_readiness",
      "unit": "status_code",
      "value": "data_limited"
    },
    {
      "evidence_type": "readiness_contract_state",
      "impact": "explains_output_boundary",
      "label": "Readiness contract state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "degraded"
    },
    {
      "evidence_type": "readiness_basis",
      "impact": "explains_input_scope",
      "label": "Readiness basis",
      "source": "team_operations_bullpen_readiness",
      "unit": "sources",
      "value": [
        "availability_distribution",
        "workload_pressure",
        "freshness",
        "trust_metadata"
      ]
    },
    {
      "evidence_type": "readiness_freshness_state",
      "impact": "explains_freshness_boundary",
      "label": "Freshness state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "current"
    },
    {
      "evidence_type": "readiness_trust_confidence",
      "impact": "explains_confidence_boundary",
      "label": "Trust confidence",
      "source": "team_operations_bullpen_readiness",
      "unit": "level",
      "value": "low"
    },
    {
      "evidence_type": "readiness_trust_data_state",
      "impact": "explains_trust_boundary",
      "label": "Trust data state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "incomplete"
    },
    {
      "evidence_type": "workload_pressure_state",
      "impact": "explains_workload_state",
      "label": "Workload pressure state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "elevated"
    },
    {
      "evidence_type": "coverage_inventory_state",
      "impact": "explains_coverage_state",
      "label": "Coverage inventory state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "partial"
    },
    {
      "evidence_type": "handedness_coverage_state",
      "impact": "explains_coverage_state",
      "label": "Handedness coverage state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "covered"
    },
    {
      "evidence_type": "workload_pressure_low_count",
      "impact": "explains_workload_state",
      "label": "Low workload count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 4
    },
    {
      "evidence_type": "workload_pressure_moderate_count",
      "impact": "explains_workload_state",
      "label": "Moderate workload count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 6
    },
    {
      "evidence_type": "workload_pressure_elevated_count",
      "impact": "explains_workload_state",
      "label": "Elevated workload count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 3
    },
    {
      "evidence_type": "workload_pressure_unknown_count",
      "impact": "explains_workload_state",
      "label": "Unknown workload count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 6
    },
    {
      "evidence_type": "availability_distribution_available",
      "impact": "explains_availability_state",
      "label": "Available inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 5
    },
    {
      "evidence_type": "availability_distribution_monitor",
      "impact": "explains_availability_state",
      "label": "Monitor inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 7
    },
    {
      "evidence_type": "availability_distribution_limited",
      "impact": "explains_availability_state",
      "label": "Limited inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 4
    },
    {
      "evidence_type": "availability_distribution_avoid",
      "impact": "explains_availability_state",
      "label": "Avoid inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 2
    },
    {
      "evidence_type": "availability_distribution_unavailable",
      "impact": "explains_availability_state",
      "label": "Unavailable inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 1
    },
    {
      "evidence_type": "availability_distribution_unknown",
      "impact": "explains_availability_state",
      "label": "Unknown availability count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 0
    },
    {
      "evidence_type": "availability_distribution_total",
      "impact": "explains_availability_state",
      "label": "Total availability inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 19
    },
    {
      "evidence_type": "coverage_inventory_active_pitcher_count",
      "impact": "explains_coverage_state",
      "label": "Active pitcher count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 19
    },
    {
      "evidence_type": "coverage_inventory_current_workload_data_count",
      "impact": "explains_coverage_state",
      "label": "Current workload data count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 13
    },
    {
      "evidence_type": "coverage_inventory_missing_workload_data_count",
      "impact": "explains_coverage_state",
      "label": "Missing workload data count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 6
    },
    {
      "evidence_type": "coverage_inventory_availability_covered_count",
      "impact": "explains_coverage_state",
      "label": "Availability covered count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 19
    },
    {
      "evidence_type": "coverage_inventory_availability_missing_count",
      "impact": "explains_coverage_state",
      "label": "Availability missing count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 0
    },
    {
      "evidence_type": "handedness_coverage_left_handed_count",
      "impact": "explains_coverage_state",
      "label": "Left handed count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 7
    },
    {
      "evidence_type": "handedness_coverage_right_handed_count",
      "impact": "explains_coverage_state",
      "label": "Right handed count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 12
    },
    {
      "evidence_type": "handedness_coverage_unknown_count",
      "impact": "explains_coverage_state",
      "label": "Unknown handedness count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 0
    },
    {
      "evidence_type": "readiness_constraint_trust_metadata_limited",
      "impact": "explains_readiness_limitation",
      "label": "Readiness constraint trust_metadata_limited",
      "source": "team_operations_bullpen_readiness",
      "unit": "constraint",
      "value": {
        "affected_area": "trust_metadata",
        "category": "trust",
        "count": 1,
        "evidence": [
          "confidence: low",
          "data_state: incomplete"
        ],
        "message": "The public workload record is not strong enough for a full readiness summary.",
        "severity": "caution"
      }
    },
    {
      "evidence_type": "readiness_constraint_coverage_partial",
      "impact": "explains_readiness_limitation",
      "label": "Readiness constraint coverage_partial",
      "source": "team_operations_bullpen_readiness",
      "unit": "constraint",
      "value": {
        "affected_area": "coverage_inventory",
        "category": "coverage",
        "count": 6,
        "evidence": [
          "missing_workload_data_count: 6",
          "availability_missing_count: 0"
        ],
        "message": "Some active pitcher records have incomplete readiness evidence.",
        "severity": "caution"
      }
    },
    {
      "evidence_type": "readiness_constraint_workload_elevated",
      "impact": "explains_readiness_limitation",
      "label": "Readiness constraint workload_elevated",
      "source": "team_operations_bullpen_readiness",
      "unit": "constraint",
      "value": {
        "affected_area": "workload_pressure",
        "category": "workload",
        "count": 3,
        "evidence": [
          "elevated_count: 3"
        ],
        "message": "Elevated team-level workload pressure is present.",
        "severity": "caution"
      }
    },
    {
      "evidence_type": "readiness_constraint_availability_constrained",
      "impact": "explains_readiness_limitation",
      "label": "Readiness constraint availability_constrained",
      "source": "team_operations_bullpen_readiness",
      "unit": "constraint",
      "value": {
        "affected_area": "availability_distribution",
        "category": "availability",
        "count": 3,
        "evidence": [
          "avoid_or_unavailable_count: 3"
        ],
        "message": "Availability distribution contains constrained inventory.",
        "severity": "caution"
      }
    }
  ]
}
```

### Example 23: Team Operations readiness V4 explanation

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "capitalization_sentence_scan": {
    "patterns": {
      "lowercase_sentence_start": "(?<=[.!?])\\s+([a-z])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "circular_meta_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "explanation confidence mirrors",
      "confidence mirrors",
      "visibility reflects existing availability confidence",
      "governed availability evidence",
      "state reflects",
      "explained state",
      "trust metadata",
      "readiness explanation confidence"
    ],
    "violation_count": 0,
    "violations": []
  },
  "disclaimer_repetition_scan": {
    "disclaimer": "This is a data-limited note, not a statement about injury status or manager intent.",
    "per_card_limit": 1,
    "scope": "Team bullpen shape rendered public copy",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "example_source": "stored-data example",
  "fallback_status": "data_limited",
  "pitcher": null,
  "raw_count_formula_scan": {
    "patterns": {
      "jargon_coupled_raw_count": "(?<![\\w-])\\d+\\s+of\\s+\\d+\\s+(?:trust|bridge|coverage|depth)\\s+arms?\\b",
      "parenthetical_raw_basis": "\\(\\s*\\d+\\s+of\\s+\\d+\\s*\\)",
      "parenthetical_unknown_formula": "\\([^)]*\\bunknown\\b[^)]*\\)",
      "raw_empty_arithmetic": "(?<![\\w-])\\d+\\s+of\\s+\\d+(?![\\w-])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "length option",
      "length options",
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "classified available",
      "0 of 0",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "trust metadata",
      "explained state",
      "availability read",
      "bullpen planning read",
      "explanation confidence mirrors",
      "confidence mirrors",
      "governed availability evidence",
      "state reflects",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "role_or_classification": {
    "readiness_status": "Limited Visibility",
    "readiness_status_code": "data_limited",
    "scope": "coverage_state"
  },
  "source_path": "api.explanations._team_readiness_payload_from_request -> explanations.readiness.serialize_readiness_explanation",
  "status": "workload:partial;handedness:covered",
  "surface_name": "Team Operations readiness V4 explanation",
  "team": "Los Angeles Angels (LAA, 108)",
  "weighting_scoring_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "raw score",
      "scoring weight",
      "weighted pressure"
    ],
    "violation_count": 0,
    "violations": []
  }
}
```

Rendered public copy:
```
This note focuses on whether the public data can describe bullpen coverage.
The public data is not strong enough to give this team a full bullpen readiness note.
A heavy recent stretch has the workload up.
Some of the public workload detail is incomplete.
The public data is not strong enough for a fuller explanation.
Readiness is based on public workload data, not private team information.
Readiness is not injury or medical information.
Readiness is not a performance forecast.
Manager intent and bullpen warm-up state are not available.
The user remains responsible for baseball decisions.
Some active pitcher records have incomplete readiness evidence.
The safest read is limited until the public workload picture is stronger.
The stored workload data is current enough for this team note.
The safest note stays limited until the public workload picture is stronger.
```

Structured fields used:

```json
{
  "availability_distribution": {
    "available": 5,
    "avoid": 2,
    "limited": 4,
    "monitor": 7,
    "total": 19,
    "unavailable": 1,
    "unknown": 0
  },
  "constraints": [
    {
      "affected_area": "trust_metadata",
      "category": "trust",
      "constraint_id": "trust_metadata_limited",
      "count": 1,
      "evidence": [
        "confidence: low",
        "data_state: incomplete"
      ],
      "message": "The public workload record is not strong enough for a full readiness summary.",
      "severity": "caution"
    },
    {
      "affected_area": "coverage_inventory",
      "category": "coverage",
      "constraint_id": "coverage_partial",
      "count": 6,
      "evidence": [
        "missing_workload_data_count: 6",
        "availability_missing_count: 0"
      ],
      "message": "Some active pitcher records have incomplete readiness evidence.",
      "severity": "caution"
    },
    {
      "affected_area": "workload_pressure",
      "category": "workload",
      "constraint_id": "workload_elevated",
      "count": 3,
      "evidence": [
        "elevated_count: 3"
      ],
      "message": "Elevated team-level workload pressure is present.",
      "severity": "caution"
    },
    {
      "affected_area": "availability_distribution",
      "category": "availability",
      "constraint_id": "availability_constrained",
      "count": 3,
      "evidence": [
        "avoid_or_unavailable_count: 3"
      ],
      "message": "Availability distribution contains constrained inventory.",
      "severity": "caution"
    }
  ],
  "coverage_inventory": {
    "active_pitcher_count": 19,
    "availability_covered_count": 19,
    "availability_missing_count": 0,
    "coverage_state": "partial",
    "current_workload_data_count": 13,
    "missing_workload_data_count": 6
  },
  "freshness": {
    "data_through": "2026-06-29",
    "freshness_state": "current",
    "generated_at": "2026-06-30T10:00:47",
    "last_successful_sync": "2026-06-30T10:02:10.485036Z",
    "latest_fatigue_calculated_at": "2026-06-30T10:00:50.892219Z",
    "latest_sync_status": "success",
    "latest_workload_date": "2026-06-29",
    "limitations": [],
    "missing_data_warning": null,
    "stale_warning": null
  },
  "handedness_coverage": {
    "coverage_state": "covered",
    "left_handed_count": 7,
    "limitations": [],
    "right_handed_count": 12,
    "unknown_count": 0
  },
  "readiness": {
    "basis": [
      "availability_distribution",
      "workload_pressure",
      "freshness",
      "trust_metadata"
    ],
    "status": "Limited Visibility",
    "status_code": "data_limited",
    "summary": "Team-level bullpen visibility is limited by freshness, trust, or coverage evidence."
  },
  "trust_metadata": {
    "capability": "team_operations_bullpen_readiness",
    "confidence": "low",
    "confidence_reasons": [
      "limited_availability_evidence"
    ],
    "data_state": "incomplete",
    "explanations": [],
    "generated_at": "2026-06-30T10:00:47",
    "governance_state": "internal_uncertified",
    "limitations": [],
    "ranking_applied": false,
    "refusal_reasons": [],
    "scope": "team_bullpen_readiness",
    "selection_made": false,
    "source_evidence_state": "represented",
    "trust_validation_errors": []
  },
  "workload_pressure": {
    "elevated_count": 3,
    "latest_workload_date": "2026-06-29",
    "low_count": 4,
    "moderate_count": 6,
    "pressure_state": "elevated",
    "pressure_state_code": "elevated",
    "summary": "Recent workload pressure is elevated at the team level.",
    "unknown_count": 6
  }
}
```

Evidence sections:

```json
{
  "limitations": [
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "insufficient_context",
      "severity": "informational",
      "summary": "Readiness is based on public workload data, not private team information."
    },
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "insufficient_context",
      "severity": "informational",
      "summary": "Readiness is not injury or medical information."
    },
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "insufficient_context",
      "severity": "informational",
      "summary": "Readiness is not a performance forecast."
    },
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "insufficient_context",
      "severity": "informational",
      "summary": "Manager intent and bullpen warm-up state are not available."
    },
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "insufficient_context",
      "severity": "informational",
      "summary": "The user remains responsible for baseball decisions."
    },
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "partial_coverage",
      "severity": "limits_confidence",
      "summary": "Some active pitcher records have incomplete readiness evidence."
    },
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "limited_confidence",
      "severity": "limits_confidence",
      "summary": "The safest read is limited until the public workload picture is stronger."
    }
  ],
  "primary_reasons": [
    {
      "code": "READINESS_DEGRADED_BY_LIMITATIONS",
      "label": "Readiness degraded by limitations",
      "scope": "readiness_state",
      "summary": "The public data is not strong enough to give this team a full bullpen readiness note."
    },
    {
      "code": "WORKLOAD_RECENT_USAGE_ELEVATED",
      "label": "Recent usage elevated",
      "scope": "workload_state",
      "summary": "A heavy recent stretch has the workload up."
    },
    {
      "code": "COVERAGE_PARTIAL",
      "label": "Coverage partial",
      "scope": "coverage_state",
      "summary": "Some of the public workload detail is incomplete."
    },
    {
      "code": "TRUST_LIMITED",
      "label": "Trust limited",
      "scope": "trust_state",
      "summary": "The public data is not strong enough for a fuller explanation."
    }
  ],
  "supporting_evidence": [
    {
      "evidence_type": "readiness_status",
      "impact": "explains_readiness_state",
      "label": "Readiness status",
      "source": "team_operations_bullpen_readiness",
      "unit": "status",
      "value": "Limited Visibility"
    },
    {
      "evidence_type": "readiness_status_code",
      "impact": "explains_readiness_state",
      "label": "Readiness status code",
      "source": "team_operations_bullpen_readiness",
      "unit": "status_code",
      "value": "data_limited"
    },
    {
      "evidence_type": "readiness_contract_state",
      "impact": "explains_output_boundary",
      "label": "Readiness contract state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "degraded"
    },
    {
      "evidence_type": "readiness_basis",
      "impact": "explains_input_scope",
      "label": "Readiness basis",
      "source": "team_operations_bullpen_readiness",
      "unit": "sources",
      "value": [
        "availability_distribution",
        "workload_pressure",
        "freshness",
        "trust_metadata"
      ]
    },
    {
      "evidence_type": "readiness_freshness_state",
      "impact": "explains_freshness_boundary",
      "label": "Freshness state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "current"
    },
    {
      "evidence_type": "readiness_trust_confidence",
      "impact": "explains_confidence_boundary",
      "label": "Trust confidence",
      "source": "team_operations_bullpen_readiness",
      "unit": "level",
      "value": "low"
    },
    {
      "evidence_type": "readiness_trust_data_state",
      "impact": "explains_trust_boundary",
      "label": "Trust data state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "incomplete"
    },
    {
      "evidence_type": "workload_pressure_state",
      "impact": "explains_workload_state",
      "label": "Workload pressure state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "elevated"
    },
    {
      "evidence_type": "coverage_inventory_state",
      "impact": "explains_coverage_state",
      "label": "Coverage inventory state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "partial"
    },
    {
      "evidence_type": "handedness_coverage_state",
      "impact": "explains_coverage_state",
      "label": "Handedness coverage state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "covered"
    },
    {
      "evidence_type": "workload_pressure_low_count",
      "impact": "explains_workload_state",
      "label": "Low workload count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 4
    },
    {
      "evidence_type": "workload_pressure_moderate_count",
      "impact": "explains_workload_state",
      "label": "Moderate workload count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 6
    },
    {
      "evidence_type": "workload_pressure_elevated_count",
      "impact": "explains_workload_state",
      "label": "Elevated workload count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 3
    },
    {
      "evidence_type": "workload_pressure_unknown_count",
      "impact": "explains_workload_state",
      "label": "Unknown workload count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 6
    },
    {
      "evidence_type": "availability_distribution_available",
      "impact": "explains_availability_state",
      "label": "Available inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 5
    },
    {
      "evidence_type": "availability_distribution_monitor",
      "impact": "explains_availability_state",
      "label": "Monitor inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 7
    },
    {
      "evidence_type": "availability_distribution_limited",
      "impact": "explains_availability_state",
      "label": "Limited inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 4
    },
    {
      "evidence_type": "availability_distribution_avoid",
      "impact": "explains_availability_state",
      "label": "Avoid inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 2
    },
    {
      "evidence_type": "availability_distribution_unavailable",
      "impact": "explains_availability_state",
      "label": "Unavailable inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 1
    },
    {
      "evidence_type": "availability_distribution_unknown",
      "impact": "explains_availability_state",
      "label": "Unknown availability count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 0
    },
    {
      "evidence_type": "availability_distribution_total",
      "impact": "explains_availability_state",
      "label": "Total availability inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 19
    },
    {
      "evidence_type": "coverage_inventory_active_pitcher_count",
      "impact": "explains_coverage_state",
      "label": "Active pitcher count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 19
    },
    {
      "evidence_type": "coverage_inventory_current_workload_data_count",
      "impact": "explains_coverage_state",
      "label": "Current workload data count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 13
    },
    {
      "evidence_type": "coverage_inventory_missing_workload_data_count",
      "impact": "explains_coverage_state",
      "label": "Missing workload data count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 6
    },
    {
      "evidence_type": "coverage_inventory_availability_covered_count",
      "impact": "explains_coverage_state",
      "label": "Availability covered count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 19
    },
    {
      "evidence_type": "coverage_inventory_availability_missing_count",
      "impact": "explains_coverage_state",
      "label": "Availability missing count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 0
    },
    {
      "evidence_type": "handedness_coverage_left_handed_count",
      "impact": "explains_coverage_state",
      "label": "Left handed count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 7
    },
    {
      "evidence_type": "handedness_coverage_right_handed_count",
      "impact": "explains_coverage_state",
      "label": "Right handed count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 12
    },
    {
      "evidence_type": "handedness_coverage_unknown_count",
      "impact": "explains_coverage_state",
      "label": "Unknown handedness count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 0
    },
    {
      "evidence_type": "readiness_constraint_trust_metadata_limited",
      "impact": "explains_readiness_limitation",
      "label": "Readiness constraint trust_metadata_limited",
      "source": "team_operations_bullpen_readiness",
      "unit": "constraint",
      "value": {
        "affected_area": "trust_metadata",
        "category": "trust",
        "count": 1,
        "evidence": [
          "confidence: low",
          "data_state: incomplete"
        ],
        "message": "The public workload record is not strong enough for a full readiness summary.",
        "severity": "caution"
      }
    },
    {
      "evidence_type": "readiness_constraint_coverage_partial",
      "impact": "explains_readiness_limitation",
      "label": "Readiness constraint coverage_partial",
      "source": "team_operations_bullpen_readiness",
      "unit": "constraint",
      "value": {
        "affected_area": "coverage_inventory",
        "category": "coverage",
        "count": 6,
        "evidence": [
          "missing_workload_data_count: 6",
          "availability_missing_count: 0"
        ],
        "message": "Some active pitcher records have incomplete readiness evidence.",
        "severity": "caution"
      }
    },
    {
      "evidence_type": "readiness_constraint_workload_elevated",
      "impact": "explains_readiness_limitation",
      "label": "Readiness constraint workload_elevated",
      "source": "team_operations_bullpen_readiness",
      "unit": "constraint",
      "value": {
        "affected_area": "workload_pressure",
        "category": "workload",
        "count": 3,
        "evidence": [
          "elevated_count: 3"
        ],
        "message": "Elevated team-level workload pressure is present.",
        "severity": "caution"
      }
    },
    {
      "evidence_type": "readiness_constraint_availability_constrained",
      "impact": "explains_readiness_limitation",
      "label": "Readiness constraint availability_constrained",
      "source": "team_operations_bullpen_readiness",
      "unit": "constraint",
      "value": {
        "affected_area": "availability_distribution",
        "category": "availability",
        "count": 3,
        "evidence": [
          "avoid_or_unavailable_count: 3"
        ],
        "message": "Availability distribution contains constrained inventory.",
        "severity": "caution"
      }
    }
  ]
}
```

### Example 24: Team Operations readiness V4 explanation

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "capitalization_sentence_scan": {
    "patterns": {
      "lowercase_sentence_start": "(?<=[.!?])\\s+([a-z])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "circular_meta_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "explanation confidence mirrors",
      "confidence mirrors",
      "visibility reflects existing availability confidence",
      "governed availability evidence",
      "state reflects",
      "explained state",
      "trust metadata",
      "readiness explanation confidence"
    ],
    "violation_count": 0,
    "violations": []
  },
  "disclaimer_repetition_scan": {
    "disclaimer": "This is a data-limited note, not a statement about injury status or manager intent.",
    "per_card_limit": 1,
    "scope": "Team bullpen shape rendered public copy",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "example_source": "stored-data example",
  "fallback_status": "data_limited",
  "pitcher": null,
  "raw_count_formula_scan": {
    "patterns": {
      "jargon_coupled_raw_count": "(?<![\\w-])\\d+\\s+of\\s+\\d+\\s+(?:trust|bridge|coverage|depth)\\s+arms?\\b",
      "parenthetical_raw_basis": "\\(\\s*\\d+\\s+of\\s+\\d+\\s*\\)",
      "parenthetical_unknown_formula": "\\([^)]*\\bunknown\\b[^)]*\\)",
      "raw_empty_arithmetic": "(?<![\\w-])\\d+\\s+of\\s+\\d+(?![\\w-])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "length option",
      "length options",
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "classified available",
      "0 of 0",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "trust metadata",
      "explained state",
      "availability read",
      "bullpen planning read",
      "explanation confidence mirrors",
      "confidence mirrors",
      "governed availability evidence",
      "state reflects",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "role_or_classification": {
    "readiness_status": "Limited Visibility",
    "readiness_status_code": "data_limited",
    "scope": "freshness_state"
  },
  "source_path": "api.explanations._team_readiness_payload_from_request -> explanations.readiness.serialize_readiness_explanation",
  "status": "current",
  "surface_name": "Team Operations readiness V4 explanation",
  "team": "Los Angeles Angels (LAA, 108)",
  "weighting_scoring_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "raw score",
      "scoring weight",
      "weighted pressure"
    ],
    "violation_count": 0,
    "violations": []
  }
}
```

Rendered public copy:
```
This note focuses on how current the stored workload data is.
The public data is not strong enough to give this team a full bullpen readiness note.
A heavy recent stretch has the workload up.
Some of the public workload detail is incomplete.
The public data is not strong enough for a fuller explanation.
Readiness is based on public workload data, not private team information.
Readiness is not injury or medical information.
Readiness is not a performance forecast.
Manager intent and bullpen warm-up state are not available.
The user remains responsible for baseball decisions.
Some active pitcher records have incomplete readiness evidence.
The safest read is limited until the public workload picture is stronger.
The stored workload data is current enough for this team note.
The safest note stays limited until the public workload picture is stronger.
```

Structured fields used:

```json
{
  "availability_distribution": {
    "available": 5,
    "avoid": 2,
    "limited": 4,
    "monitor": 7,
    "total": 19,
    "unavailable": 1,
    "unknown": 0
  },
  "constraints": [
    {
      "affected_area": "trust_metadata",
      "category": "trust",
      "constraint_id": "trust_metadata_limited",
      "count": 1,
      "evidence": [
        "confidence: low",
        "data_state: incomplete"
      ],
      "message": "The public workload record is not strong enough for a full readiness summary.",
      "severity": "caution"
    },
    {
      "affected_area": "coverage_inventory",
      "category": "coverage",
      "constraint_id": "coverage_partial",
      "count": 6,
      "evidence": [
        "missing_workload_data_count: 6",
        "availability_missing_count: 0"
      ],
      "message": "Some active pitcher records have incomplete readiness evidence.",
      "severity": "caution"
    },
    {
      "affected_area": "workload_pressure",
      "category": "workload",
      "constraint_id": "workload_elevated",
      "count": 3,
      "evidence": [
        "elevated_count: 3"
      ],
      "message": "Elevated team-level workload pressure is present.",
      "severity": "caution"
    },
    {
      "affected_area": "availability_distribution",
      "category": "availability",
      "constraint_id": "availability_constrained",
      "count": 3,
      "evidence": [
        "avoid_or_unavailable_count: 3"
      ],
      "message": "Availability distribution contains constrained inventory.",
      "severity": "caution"
    }
  ],
  "coverage_inventory": {
    "active_pitcher_count": 19,
    "availability_covered_count": 19,
    "availability_missing_count": 0,
    "coverage_state": "partial",
    "current_workload_data_count": 13,
    "missing_workload_data_count": 6
  },
  "freshness": {
    "data_through": "2026-06-29",
    "freshness_state": "current",
    "generated_at": "2026-06-30T10:00:47",
    "last_successful_sync": "2026-06-30T10:02:10.485036Z",
    "latest_fatigue_calculated_at": "2026-06-30T10:00:50.892219Z",
    "latest_sync_status": "success",
    "latest_workload_date": "2026-06-29",
    "limitations": [],
    "missing_data_warning": null,
    "stale_warning": null
  },
  "handedness_coverage": {
    "coverage_state": "covered",
    "left_handed_count": 7,
    "limitations": [],
    "right_handed_count": 12,
    "unknown_count": 0
  },
  "readiness": {
    "basis": [
      "availability_distribution",
      "workload_pressure",
      "freshness",
      "trust_metadata"
    ],
    "status": "Limited Visibility",
    "status_code": "data_limited",
    "summary": "Team-level bullpen visibility is limited by freshness, trust, or coverage evidence."
  },
  "trust_metadata": {
    "capability": "team_operations_bullpen_readiness",
    "confidence": "low",
    "confidence_reasons": [
      "limited_availability_evidence"
    ],
    "data_state": "incomplete",
    "explanations": [],
    "generated_at": "2026-06-30T10:00:47",
    "governance_state": "internal_uncertified",
    "limitations": [],
    "ranking_applied": false,
    "refusal_reasons": [],
    "scope": "team_bullpen_readiness",
    "selection_made": false,
    "source_evidence_state": "represented",
    "trust_validation_errors": []
  },
  "workload_pressure": {
    "elevated_count": 3,
    "latest_workload_date": "2026-06-29",
    "low_count": 4,
    "moderate_count": 6,
    "pressure_state": "elevated",
    "pressure_state_code": "elevated",
    "summary": "Recent workload pressure is elevated at the team level.",
    "unknown_count": 6
  }
}
```

Evidence sections:

```json
{
  "limitations": [
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "insufficient_context",
      "severity": "informational",
      "summary": "Readiness is based on public workload data, not private team information."
    },
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "insufficient_context",
      "severity": "informational",
      "summary": "Readiness is not injury or medical information."
    },
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "insufficient_context",
      "severity": "informational",
      "summary": "Readiness is not a performance forecast."
    },
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "insufficient_context",
      "severity": "informational",
      "summary": "Manager intent and bullpen warm-up state are not available."
    },
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "insufficient_context",
      "severity": "informational",
      "summary": "The user remains responsible for baseball decisions."
    },
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "partial_coverage",
      "severity": "limits_confidence",
      "summary": "Some active pitcher records have incomplete readiness evidence."
    },
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "limited_confidence",
      "severity": "limits_confidence",
      "summary": "The safest read is limited until the public workload picture is stronger."
    }
  ],
  "primary_reasons": [
    {
      "code": "READINESS_DEGRADED_BY_LIMITATIONS",
      "label": "Readiness degraded by limitations",
      "scope": "readiness_state",
      "summary": "The public data is not strong enough to give this team a full bullpen readiness note."
    },
    {
      "code": "WORKLOAD_RECENT_USAGE_ELEVATED",
      "label": "Recent usage elevated",
      "scope": "workload_state",
      "summary": "A heavy recent stretch has the workload up."
    },
    {
      "code": "COVERAGE_PARTIAL",
      "label": "Coverage partial",
      "scope": "coverage_state",
      "summary": "Some of the public workload detail is incomplete."
    },
    {
      "code": "TRUST_LIMITED",
      "label": "Trust limited",
      "scope": "trust_state",
      "summary": "The public data is not strong enough for a fuller explanation."
    }
  ],
  "supporting_evidence": [
    {
      "evidence_type": "readiness_status",
      "impact": "explains_readiness_state",
      "label": "Readiness status",
      "source": "team_operations_bullpen_readiness",
      "unit": "status",
      "value": "Limited Visibility"
    },
    {
      "evidence_type": "readiness_status_code",
      "impact": "explains_readiness_state",
      "label": "Readiness status code",
      "source": "team_operations_bullpen_readiness",
      "unit": "status_code",
      "value": "data_limited"
    },
    {
      "evidence_type": "readiness_contract_state",
      "impact": "explains_output_boundary",
      "label": "Readiness contract state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "degraded"
    },
    {
      "evidence_type": "readiness_basis",
      "impact": "explains_input_scope",
      "label": "Readiness basis",
      "source": "team_operations_bullpen_readiness",
      "unit": "sources",
      "value": [
        "availability_distribution",
        "workload_pressure",
        "freshness",
        "trust_metadata"
      ]
    },
    {
      "evidence_type": "readiness_freshness_state",
      "impact": "explains_freshness_boundary",
      "label": "Freshness state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "current"
    },
    {
      "evidence_type": "readiness_trust_confidence",
      "impact": "explains_confidence_boundary",
      "label": "Trust confidence",
      "source": "team_operations_bullpen_readiness",
      "unit": "level",
      "value": "low"
    },
    {
      "evidence_type": "readiness_trust_data_state",
      "impact": "explains_trust_boundary",
      "label": "Trust data state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "incomplete"
    },
    {
      "evidence_type": "workload_pressure_state",
      "impact": "explains_workload_state",
      "label": "Workload pressure state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "elevated"
    },
    {
      "evidence_type": "coverage_inventory_state",
      "impact": "explains_coverage_state",
      "label": "Coverage inventory state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "partial"
    },
    {
      "evidence_type": "handedness_coverage_state",
      "impact": "explains_coverage_state",
      "label": "Handedness coverage state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "covered"
    },
    {
      "evidence_type": "workload_pressure_low_count",
      "impact": "explains_workload_state",
      "label": "Low workload count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 4
    },
    {
      "evidence_type": "workload_pressure_moderate_count",
      "impact": "explains_workload_state",
      "label": "Moderate workload count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 6
    },
    {
      "evidence_type": "workload_pressure_elevated_count",
      "impact": "explains_workload_state",
      "label": "Elevated workload count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 3
    },
    {
      "evidence_type": "workload_pressure_unknown_count",
      "impact": "explains_workload_state",
      "label": "Unknown workload count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 6
    },
    {
      "evidence_type": "availability_distribution_available",
      "impact": "explains_availability_state",
      "label": "Available inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 5
    },
    {
      "evidence_type": "availability_distribution_monitor",
      "impact": "explains_availability_state",
      "label": "Monitor inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 7
    },
    {
      "evidence_type": "availability_distribution_limited",
      "impact": "explains_availability_state",
      "label": "Limited inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 4
    },
    {
      "evidence_type": "availability_distribution_avoid",
      "impact": "explains_availability_state",
      "label": "Avoid inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 2
    },
    {
      "evidence_type": "availability_distribution_unavailable",
      "impact": "explains_availability_state",
      "label": "Unavailable inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 1
    },
    {
      "evidence_type": "availability_distribution_unknown",
      "impact": "explains_availability_state",
      "label": "Unknown availability count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 0
    },
    {
      "evidence_type": "availability_distribution_total",
      "impact": "explains_availability_state",
      "label": "Total availability inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 19
    },
    {
      "evidence_type": "coverage_inventory_active_pitcher_count",
      "impact": "explains_coverage_state",
      "label": "Active pitcher count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 19
    },
    {
      "evidence_type": "coverage_inventory_current_workload_data_count",
      "impact": "explains_coverage_state",
      "label": "Current workload data count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 13
    },
    {
      "evidence_type": "coverage_inventory_missing_workload_data_count",
      "impact": "explains_coverage_state",
      "label": "Missing workload data count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 6
    },
    {
      "evidence_type": "coverage_inventory_availability_covered_count",
      "impact": "explains_coverage_state",
      "label": "Availability covered count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 19
    },
    {
      "evidence_type": "coverage_inventory_availability_missing_count",
      "impact": "explains_coverage_state",
      "label": "Availability missing count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 0
    },
    {
      "evidence_type": "handedness_coverage_left_handed_count",
      "impact": "explains_coverage_state",
      "label": "Left handed count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 7
    },
    {
      "evidence_type": "handedness_coverage_right_handed_count",
      "impact": "explains_coverage_state",
      "label": "Right handed count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 12
    },
    {
      "evidence_type": "handedness_coverage_unknown_count",
      "impact": "explains_coverage_state",
      "label": "Unknown handedness count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 0
    },
    {
      "evidence_type": "readiness_constraint_trust_metadata_limited",
      "impact": "explains_readiness_limitation",
      "label": "Readiness constraint trust_metadata_limited",
      "source": "team_operations_bullpen_readiness",
      "unit": "constraint",
      "value": {
        "affected_area": "trust_metadata",
        "category": "trust",
        "count": 1,
        "evidence": [
          "confidence: low",
          "data_state: incomplete"
        ],
        "message": "The public workload record is not strong enough for a full readiness summary.",
        "severity": "caution"
      }
    },
    {
      "evidence_type": "readiness_constraint_coverage_partial",
      "impact": "explains_readiness_limitation",
      "label": "Readiness constraint coverage_partial",
      "source": "team_operations_bullpen_readiness",
      "unit": "constraint",
      "value": {
        "affected_area": "coverage_inventory",
        "category": "coverage",
        "count": 6,
        "evidence": [
          "missing_workload_data_count: 6",
          "availability_missing_count: 0"
        ],
        "message": "Some active pitcher records have incomplete readiness evidence.",
        "severity": "caution"
      }
    },
    {
      "evidence_type": "readiness_constraint_workload_elevated",
      "impact": "explains_readiness_limitation",
      "label": "Readiness constraint workload_elevated",
      "source": "team_operations_bullpen_readiness",
      "unit": "constraint",
      "value": {
        "affected_area": "workload_pressure",
        "category": "workload",
        "count": 3,
        "evidence": [
          "elevated_count: 3"
        ],
        "message": "Elevated team-level workload pressure is present.",
        "severity": "caution"
      }
    },
    {
      "evidence_type": "readiness_constraint_availability_constrained",
      "impact": "explains_readiness_limitation",
      "label": "Readiness constraint availability_constrained",
      "source": "team_operations_bullpen_readiness",
      "unit": "constraint",
      "value": {
        "affected_area": "availability_distribution",
        "category": "availability",
        "count": 3,
        "evidence": [
          "avoid_or_unavailable_count: 3"
        ],
        "message": "Availability distribution contains constrained inventory.",
        "severity": "caution"
      }
    }
  ]
}
```

### Example 25: Team Operations readiness V4 explanation

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "capitalization_sentence_scan": {
    "patterns": {
      "lowercase_sentence_start": "(?<=[.!?])\\s+([a-z])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "circular_meta_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "explanation confidence mirrors",
      "confidence mirrors",
      "visibility reflects existing availability confidence",
      "governed availability evidence",
      "state reflects",
      "explained state",
      "trust metadata",
      "readiness explanation confidence"
    ],
    "violation_count": 0,
    "violations": []
  },
  "disclaimer_repetition_scan": {
    "disclaimer": "This is a data-limited note, not a statement about injury status or manager intent.",
    "per_card_limit": 1,
    "scope": "Team bullpen shape rendered public copy",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "example_source": "stored-data example",
  "fallback_status": "data_limited",
  "pitcher": null,
  "raw_count_formula_scan": {
    "patterns": {
      "jargon_coupled_raw_count": "(?<![\\w-])\\d+\\s+of\\s+\\d+\\s+(?:trust|bridge|coverage|depth)\\s+arms?\\b",
      "parenthetical_raw_basis": "\\(\\s*\\d+\\s+of\\s+\\d+\\s*\\)",
      "parenthetical_unknown_formula": "\\([^)]*\\bunknown\\b[^)]*\\)",
      "raw_empty_arithmetic": "(?<![\\w-])\\d+\\s+of\\s+\\d+(?![\\w-])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "length option",
      "length options",
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "classified available",
      "0 of 0",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "trust metadata",
      "explained state",
      "availability read",
      "bullpen planning read",
      "explanation confidence mirrors",
      "confidence mirrors",
      "governed availability evidence",
      "state reflects",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "role_or_classification": {
    "readiness_status": "Limited Visibility",
    "readiness_status_code": "data_limited",
    "scope": "trust_state"
  },
  "source_path": "api.explanations._team_readiness_payload_from_request -> explanations.readiness.serialize_readiness_explanation",
  "status": "limited",
  "surface_name": "Team Operations readiness V4 explanation",
  "team": "Los Angeles Angels (LAA, 108)",
  "weighting_scoring_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "raw score",
      "scoring weight",
      "weighted pressure"
    ],
    "violation_count": 0,
    "violations": []
  }
}
```

Rendered public copy:
```
This note focuses on how much the public workload record can support.
The public data is not strong enough to give this team a full bullpen readiness note.
A heavy recent stretch has the workload up.
Some of the public workload detail is incomplete.
The public data is not strong enough for a fuller explanation.
Readiness is based on public workload data, not private team information.
Readiness is not injury or medical information.
Readiness is not a performance forecast.
Manager intent and bullpen warm-up state are not available.
The user remains responsible for baseball decisions.
Some active pitcher records have incomplete readiness evidence.
The safest read is limited until the public workload picture is stronger.
The stored workload data is current enough for this team note.
The safest note stays limited until the public workload picture is stronger.
```

Structured fields used:

```json
{
  "availability_distribution": {
    "available": 5,
    "avoid": 2,
    "limited": 4,
    "monitor": 7,
    "total": 19,
    "unavailable": 1,
    "unknown": 0
  },
  "constraints": [
    {
      "affected_area": "trust_metadata",
      "category": "trust",
      "constraint_id": "trust_metadata_limited",
      "count": 1,
      "evidence": [
        "confidence: low",
        "data_state: incomplete"
      ],
      "message": "The public workload record is not strong enough for a full readiness summary.",
      "severity": "caution"
    },
    {
      "affected_area": "coverage_inventory",
      "category": "coverage",
      "constraint_id": "coverage_partial",
      "count": 6,
      "evidence": [
        "missing_workload_data_count: 6",
        "availability_missing_count: 0"
      ],
      "message": "Some active pitcher records have incomplete readiness evidence.",
      "severity": "caution"
    },
    {
      "affected_area": "workload_pressure",
      "category": "workload",
      "constraint_id": "workload_elevated",
      "count": 3,
      "evidence": [
        "elevated_count: 3"
      ],
      "message": "Elevated team-level workload pressure is present.",
      "severity": "caution"
    },
    {
      "affected_area": "availability_distribution",
      "category": "availability",
      "constraint_id": "availability_constrained",
      "count": 3,
      "evidence": [
        "avoid_or_unavailable_count: 3"
      ],
      "message": "Availability distribution contains constrained inventory.",
      "severity": "caution"
    }
  ],
  "coverage_inventory": {
    "active_pitcher_count": 19,
    "availability_covered_count": 19,
    "availability_missing_count": 0,
    "coverage_state": "partial",
    "current_workload_data_count": 13,
    "missing_workload_data_count": 6
  },
  "freshness": {
    "data_through": "2026-06-29",
    "freshness_state": "current",
    "generated_at": "2026-06-30T10:00:47",
    "last_successful_sync": "2026-06-30T10:02:10.485036Z",
    "latest_fatigue_calculated_at": "2026-06-30T10:00:50.892219Z",
    "latest_sync_status": "success",
    "latest_workload_date": "2026-06-29",
    "limitations": [],
    "missing_data_warning": null,
    "stale_warning": null
  },
  "handedness_coverage": {
    "coverage_state": "covered",
    "left_handed_count": 7,
    "limitations": [],
    "right_handed_count": 12,
    "unknown_count": 0
  },
  "readiness": {
    "basis": [
      "availability_distribution",
      "workload_pressure",
      "freshness",
      "trust_metadata"
    ],
    "status": "Limited Visibility",
    "status_code": "data_limited",
    "summary": "Team-level bullpen visibility is limited by freshness, trust, or coverage evidence."
  },
  "trust_metadata": {
    "capability": "team_operations_bullpen_readiness",
    "confidence": "low",
    "confidence_reasons": [
      "limited_availability_evidence"
    ],
    "data_state": "incomplete",
    "explanations": [],
    "generated_at": "2026-06-30T10:00:47",
    "governance_state": "internal_uncertified",
    "limitations": [],
    "ranking_applied": false,
    "refusal_reasons": [],
    "scope": "team_bullpen_readiness",
    "selection_made": false,
    "source_evidence_state": "represented",
    "trust_validation_errors": []
  },
  "workload_pressure": {
    "elevated_count": 3,
    "latest_workload_date": "2026-06-29",
    "low_count": 4,
    "moderate_count": 6,
    "pressure_state": "elevated",
    "pressure_state_code": "elevated",
    "summary": "Recent workload pressure is elevated at the team level.",
    "unknown_count": 6
  }
}
```

Evidence sections:

```json
{
  "limitations": [
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "insufficient_context",
      "severity": "informational",
      "summary": "Readiness is based on public workload data, not private team information."
    },
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "insufficient_context",
      "severity": "informational",
      "summary": "Readiness is not injury or medical information."
    },
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "insufficient_context",
      "severity": "informational",
      "summary": "Readiness is not a performance forecast."
    },
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "insufficient_context",
      "severity": "informational",
      "summary": "Manager intent and bullpen warm-up state are not available."
    },
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "insufficient_context",
      "severity": "informational",
      "summary": "The user remains responsible for baseball decisions."
    },
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "partial_coverage",
      "severity": "limits_confidence",
      "summary": "Some active pitcher records have incomplete readiness evidence."
    },
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "limited_confidence",
      "severity": "limits_confidence",
      "summary": "The safest read is limited until the public workload picture is stronger."
    }
  ],
  "primary_reasons": [
    {
      "code": "READINESS_DEGRADED_BY_LIMITATIONS",
      "label": "Readiness degraded by limitations",
      "scope": "readiness_state",
      "summary": "The public data is not strong enough to give this team a full bullpen readiness note."
    },
    {
      "code": "WORKLOAD_RECENT_USAGE_ELEVATED",
      "label": "Recent usage elevated",
      "scope": "workload_state",
      "summary": "A heavy recent stretch has the workload up."
    },
    {
      "code": "COVERAGE_PARTIAL",
      "label": "Coverage partial",
      "scope": "coverage_state",
      "summary": "Some of the public workload detail is incomplete."
    },
    {
      "code": "TRUST_LIMITED",
      "label": "Trust limited",
      "scope": "trust_state",
      "summary": "The public data is not strong enough for a fuller explanation."
    }
  ],
  "supporting_evidence": [
    {
      "evidence_type": "readiness_status",
      "impact": "explains_readiness_state",
      "label": "Readiness status",
      "source": "team_operations_bullpen_readiness",
      "unit": "status",
      "value": "Limited Visibility"
    },
    {
      "evidence_type": "readiness_status_code",
      "impact": "explains_readiness_state",
      "label": "Readiness status code",
      "source": "team_operations_bullpen_readiness",
      "unit": "status_code",
      "value": "data_limited"
    },
    {
      "evidence_type": "readiness_contract_state",
      "impact": "explains_output_boundary",
      "label": "Readiness contract state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "degraded"
    },
    {
      "evidence_type": "readiness_basis",
      "impact": "explains_input_scope",
      "label": "Readiness basis",
      "source": "team_operations_bullpen_readiness",
      "unit": "sources",
      "value": [
        "availability_distribution",
        "workload_pressure",
        "freshness",
        "trust_metadata"
      ]
    },
    {
      "evidence_type": "readiness_freshness_state",
      "impact": "explains_freshness_boundary",
      "label": "Freshness state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "current"
    },
    {
      "evidence_type": "readiness_trust_confidence",
      "impact": "explains_confidence_boundary",
      "label": "Trust confidence",
      "source": "team_operations_bullpen_readiness",
      "unit": "level",
      "value": "low"
    },
    {
      "evidence_type": "readiness_trust_data_state",
      "impact": "explains_trust_boundary",
      "label": "Trust data state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "incomplete"
    },
    {
      "evidence_type": "workload_pressure_state",
      "impact": "explains_workload_state",
      "label": "Workload pressure state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "elevated"
    },
    {
      "evidence_type": "coverage_inventory_state",
      "impact": "explains_coverage_state",
      "label": "Coverage inventory state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "partial"
    },
    {
      "evidence_type": "handedness_coverage_state",
      "impact": "explains_coverage_state",
      "label": "Handedness coverage state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "covered"
    },
    {
      "evidence_type": "workload_pressure_low_count",
      "impact": "explains_workload_state",
      "label": "Low workload count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 4
    },
    {
      "evidence_type": "workload_pressure_moderate_count",
      "impact": "explains_workload_state",
      "label": "Moderate workload count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 6
    },
    {
      "evidence_type": "workload_pressure_elevated_count",
      "impact": "explains_workload_state",
      "label": "Elevated workload count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 3
    },
    {
      "evidence_type": "workload_pressure_unknown_count",
      "impact": "explains_workload_state",
      "label": "Unknown workload count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 6
    },
    {
      "evidence_type": "availability_distribution_available",
      "impact": "explains_availability_state",
      "label": "Available inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 5
    },
    {
      "evidence_type": "availability_distribution_monitor",
      "impact": "explains_availability_state",
      "label": "Monitor inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 7
    },
    {
      "evidence_type": "availability_distribution_limited",
      "impact": "explains_availability_state",
      "label": "Limited inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 4
    },
    {
      "evidence_type": "availability_distribution_avoid",
      "impact": "explains_availability_state",
      "label": "Avoid inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 2
    },
    {
      "evidence_type": "availability_distribution_unavailable",
      "impact": "explains_availability_state",
      "label": "Unavailable inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 1
    },
    {
      "evidence_type": "availability_distribution_unknown",
      "impact": "explains_availability_state",
      "label": "Unknown availability count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 0
    },
    {
      "evidence_type": "availability_distribution_total",
      "impact": "explains_availability_state",
      "label": "Total availability inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 19
    },
    {
      "evidence_type": "coverage_inventory_active_pitcher_count",
      "impact": "explains_coverage_state",
      "label": "Active pitcher count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 19
    },
    {
      "evidence_type": "coverage_inventory_current_workload_data_count",
      "impact": "explains_coverage_state",
      "label": "Current workload data count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 13
    },
    {
      "evidence_type": "coverage_inventory_missing_workload_data_count",
      "impact": "explains_coverage_state",
      "label": "Missing workload data count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 6
    },
    {
      "evidence_type": "coverage_inventory_availability_covered_count",
      "impact": "explains_coverage_state",
      "label": "Availability covered count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 19
    },
    {
      "evidence_type": "coverage_inventory_availability_missing_count",
      "impact": "explains_coverage_state",
      "label": "Availability missing count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 0
    },
    {
      "evidence_type": "handedness_coverage_left_handed_count",
      "impact": "explains_coverage_state",
      "label": "Left handed count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 7
    },
    {
      "evidence_type": "handedness_coverage_right_handed_count",
      "impact": "explains_coverage_state",
      "label": "Right handed count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 12
    },
    {
      "evidence_type": "handedness_coverage_unknown_count",
      "impact": "explains_coverage_state",
      "label": "Unknown handedness count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 0
    },
    {
      "evidence_type": "readiness_constraint_trust_metadata_limited",
      "impact": "explains_readiness_limitation",
      "label": "Readiness constraint trust_metadata_limited",
      "source": "team_operations_bullpen_readiness",
      "unit": "constraint",
      "value": {
        "affected_area": "trust_metadata",
        "category": "trust",
        "count": 1,
        "evidence": [
          "confidence: low",
          "data_state: incomplete"
        ],
        "message": "The public workload record is not strong enough for a full readiness summary.",
        "severity": "caution"
      }
    },
    {
      "evidence_type": "readiness_constraint_coverage_partial",
      "impact": "explains_readiness_limitation",
      "label": "Readiness constraint coverage_partial",
      "source": "team_operations_bullpen_readiness",
      "unit": "constraint",
      "value": {
        "affected_area": "coverage_inventory",
        "category": "coverage",
        "count": 6,
        "evidence": [
          "missing_workload_data_count: 6",
          "availability_missing_count: 0"
        ],
        "message": "Some active pitcher records have incomplete readiness evidence.",
        "severity": "caution"
      }
    },
    {
      "evidence_type": "readiness_constraint_workload_elevated",
      "impact": "explains_readiness_limitation",
      "label": "Readiness constraint workload_elevated",
      "source": "team_operations_bullpen_readiness",
      "unit": "constraint",
      "value": {
        "affected_area": "workload_pressure",
        "category": "workload",
        "count": 3,
        "evidence": [
          "elevated_count: 3"
        ],
        "message": "Elevated team-level workload pressure is present.",
        "severity": "caution"
      }
    },
    {
      "evidence_type": "readiness_constraint_availability_constrained",
      "impact": "explains_readiness_limitation",
      "label": "Readiness constraint availability_constrained",
      "source": "team_operations_bullpen_readiness",
      "unit": "constraint",
      "value": {
        "affected_area": "availability_distribution",
        "category": "availability",
        "count": 3,
        "evidence": [
          "avoid_or_unavailable_count: 3"
        ],
        "message": "Availability distribution contains constrained inventory.",
        "severity": "caution"
      }
    }
  ]
}
```

### Example 26: Pitcher Context modal/detail route

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "capitalization_sentence_scan": {
    "patterns": {
      "lowercase_sentence_start": "(?<=[.!?])\\s+([a-z])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "circular_meta_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "explanation confidence mirrors",
      "confidence mirrors",
      "visibility reflects existing availability confidence",
      "governed availability evidence",
      "state reflects",
      "explained state",
      "trust metadata",
      "readiness explanation confidence"
    ],
    "violation_count": 0,
    "violations": []
  },
  "disclaimer_repetition_scan": {
    "disclaimer": "This is a data-limited note, not a statement about injury status or manager intent.",
    "per_card_limit": 1,
    "scope": "Team bullpen shape rendered public copy",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "example_source": "deterministic fixture example",
  "fallback_status": "rendered",
  "pitcher": "Deterministic fixture pitcher - Monitor",
  "raw_count_formula_scan": {
    "patterns": {
      "jargon_coupled_raw_count": "(?<![\\w-])\\d+\\s+of\\s+\\d+\\s+(?:trust|bridge|coverage|depth)\\s+arms?\\b",
      "parenthetical_raw_basis": "\\(\\s*\\d+\\s+of\\s+\\d+\\s*\\)",
      "parenthetical_unknown_formula": "\\([^)]*\\bunknown\\b[^)]*\\)",
      "raw_empty_arithmetic": "(?<![\\w-])\\d+\\s+of\\s+\\d+(?![\\w-])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "length option",
      "length options",
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "classified available",
      "0 of 0",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "trust metadata",
      "explained state",
      "availability read",
      "bullpen planning read",
      "explanation confidence mirrors",
      "confidence mirrors",
      "governed availability evidence",
      "state reflects",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "role_or_classification": {
    "confidence": "high",
    "data_state": "fresh",
    "roster_status": null
  },
  "source_path": "backend/tests/test_v4_availability_explanation_integration.py fixture pattern -> services.availability.classify_availability -> api.bullpen.get_pitcher_fatigue payload shape",
  "status": "Monitor",
  "surface_name": "Pitcher Context modal/detail route",
  "team": "Deterministic Context Fixture (FIX, fixture-context)",
  "weighting_scoring_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "raw score",
      "scoring weight",
      "weighted pressure"
    ],
    "violation_count": 0,
    "violations": []
  }
}
```

Rendered public copy:
```
Monitor
16 pitches yesterday
Only 1 day of rest
No injury data available
No team-reported availability data available
```

Structured fields used:

```json
{
  "availability": {
    "availability_status": "Monitor",
    "confidence": "high",
    "data_state": "fresh",
    "inputs": {
      "appearances_last_3_days": 1,
      "appearances_last_5_days": 1,
      "back_to_back": false,
      "days_rest": 1,
      "fatigue_risk_level": "LOW",
      "fatigue_score": 20.0,
      "four_in_five": false,
      "freshness_state": "fresh",
      "latest_game_date": "2026-05-31",
      "pitches_last_3_days": 16,
      "pitches_last_5_days": 16,
      "pitches_yesterday": 16,
      "reference_date": "2026-06-01",
      "three_in_four": false
    },
    "limitations": [
      "No injury data available",
      "No team-reported availability data available"
    ],
    "reasons": [
      "16 pitches yesterday",
      "Only 1 day of rest"
    ]
  },
  "freshness": {},
  "roster_status": {},
  "workload_signal": {
    "availability_status": "Monitor",
    "confidence": "high",
    "data_state": "fresh",
    "inputs": {
      "appearances_last_3_days": 1,
      "appearances_last_5_days": 1,
      "back_to_back": false,
      "days_rest": 1,
      "fatigue_risk_level": "LOW",
      "fatigue_score": 20.0,
      "four_in_five": false,
      "freshness_state": "fresh",
      "latest_game_date": "2026-05-31",
      "pitches_last_3_days": 16,
      "pitches_last_5_days": 16,
      "pitches_yesterday": 16,
      "reference_date": "2026-06-01",
      "three_in_four": false
    },
    "limitations": [
      "No injury data available",
      "No team-reported availability data available"
    ],
    "reasons": [
      "16 pitches yesterday",
      "Only 1 day of rest"
    ]
  }
}
```

Evidence sections:

```json
{
  "fatigue_trend_points": 0,
  "last_workload_appearance": {
    "game_date": "2026-05-31",
    "pitches": 16
  },
  "recent_logs_reviewed": 1
}
```

### Example 27: Pitcher public role/read labels

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "capitalization_sentence_scan": {
    "patterns": {
      "lowercase_sentence_start": "(?<=[.!?])\\s+([a-z])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "circular_meta_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "explanation confidence mirrors",
      "confidence mirrors",
      "visibility reflects existing availability confidence",
      "governed availability evidence",
      "state reflects",
      "explained state",
      "trust metadata",
      "readiness explanation confidence"
    ],
    "violation_count": 0,
    "violations": []
  },
  "disclaimer_repetition_scan": {
    "disclaimer": "This is a data-limited note, not a statement about injury status or manager intent.",
    "per_card_limit": 1,
    "scope": "Team bullpen shape rendered public copy",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "example_source": "deterministic fixture example",
  "fallback_status": "rendered",
  "pitcher": "Deterministic fixture pitcher - Trust Arm",
  "raw_count_formula_scan": {
    "patterns": {
      "jargon_coupled_raw_count": "(?<![\\w-])\\d+\\s+of\\s+\\d+\\s+(?:trust|bridge|coverage|depth)\\s+arms?\\b",
      "parenthetical_raw_basis": "\\(\\s*\\d+\\s+of\\s+\\d+\\s*\\)",
      "parenthetical_unknown_formula": "\\([^)]*\\bunknown\\b[^)]*\\)",
      "raw_empty_arithmetic": "(?<![\\w-])\\d+\\s+of\\s+\\d+(?![\\w-])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "length option",
      "length options",
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "classified available",
      "0 of 0",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "trust metadata",
      "explained state",
      "availability read",
      "bullpen planning read",
      "explanation confidence mirrors",
      "confidence mirrors",
      "governed availability evidence",
      "state reflects",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "role_or_classification": {
    "read": "Rested",
    "role": "Trust Arm"
  },
  "source_path": "backend/tests/test_team_bullpen_shape.py role fixture pattern -> services.pitcher_public_labels.build_pitcher_labels",
  "status": "Available",
  "surface_name": "Pitcher public role/read labels",
  "team": "Deterministic Context Fixture (FIX, fixture-context)",
  "weighting_scoring_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "raw score",
      "scoring weight",
      "weighted pressure"
    ],
    "violation_count": 0,
    "violations": []
  }
}
```

Rendered public copy:
```
Trust Arm
Rested
```

Structured fields used:

```json
{
  "availability_confidence": "high",
  "availability_data_state": "fresh",
  "availability_status": "Available",
  "labels": {
    "read": {
      "key": "clean_option",
      "kind": "read",
      "label": "Rested",
      "source": "backend:availability_status"
    },
    "role": {
      "key": "trust_arm",
      "kind": "role",
      "label": "Trust Arm",
      "source": "backend:role_key:late_high_leverage"
    }
  },
  "role_input": null,
  "roster_status": {}
}
```

Evidence sections:

```json
{}
```

### Example 28: Pitcher public role/read labels

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "capitalization_sentence_scan": {
    "patterns": {
      "lowercase_sentence_start": "(?<=[.!?])\\s+([a-z])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "circular_meta_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "explanation confidence mirrors",
      "confidence mirrors",
      "visibility reflects existing availability confidence",
      "governed availability evidence",
      "state reflects",
      "explained state",
      "trust metadata",
      "readiness explanation confidence"
    ],
    "violation_count": 0,
    "violations": []
  },
  "disclaimer_repetition_scan": {
    "disclaimer": "This is a data-limited note, not a statement about injury status or manager intent.",
    "per_card_limit": 1,
    "scope": "Team bullpen shape rendered public copy",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "example_source": "deterministic fixture example",
  "fallback_status": "rendered",
  "pitcher": "Deterministic fixture pitcher - Bridge Arm",
  "raw_count_formula_scan": {
    "patterns": {
      "jargon_coupled_raw_count": "(?<![\\w-])\\d+\\s+of\\s+\\d+\\s+(?:trust|bridge|coverage|depth)\\s+arms?\\b",
      "parenthetical_raw_basis": "\\(\\s*\\d+\\s+of\\s+\\d+\\s*\\)",
      "parenthetical_unknown_formula": "\\([^)]*\\bunknown\\b[^)]*\\)",
      "raw_empty_arithmetic": "(?<![\\w-])\\d+\\s+of\\s+\\d+(?![\\w-])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "length option",
      "length options",
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "classified available",
      "0 of 0",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "trust metadata",
      "explained state",
      "availability read",
      "bullpen planning read",
      "explanation confidence mirrors",
      "confidence mirrors",
      "governed availability evidence",
      "state reflects",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "role_or_classification": {
    "read": "Watch Arm",
    "role": "Bridge Arm"
  },
  "source_path": "backend/tests/test_team_bullpen_shape.py role fixture pattern -> services.pitcher_public_labels.build_pitcher_labels",
  "status": "Monitor",
  "surface_name": "Pitcher public role/read labels",
  "team": "Deterministic Context Fixture (FIX, fixture-context)",
  "weighting_scoring_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "raw score",
      "scoring weight",
      "weighted pressure"
    ],
    "violation_count": 0,
    "violations": []
  }
}
```

Rendered public copy:
```
Bridge Arm
Watch Arm
```

Structured fields used:

```json
{
  "availability_confidence": "high",
  "availability_data_state": "fresh",
  "availability_status": "Monitor",
  "labels": {
    "read": {
      "key": "watch_arm",
      "kind": "read",
      "label": "Watch Arm",
      "source": "backend:availability_status"
    },
    "role": {
      "key": "bridge_arm",
      "kind": "role",
      "label": "Bridge Arm",
      "source": "backend:role_key:setup_bridge"
    }
  },
  "role_input": null,
  "roster_status": {}
}
```

Evidence sections:

```json
{}
```

### Example 29: Pitcher public role/read labels

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "capitalization_sentence_scan": {
    "patterns": {
      "lowercase_sentence_start": "(?<=[.!?])\\s+([a-z])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "circular_meta_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "explanation confidence mirrors",
      "confidence mirrors",
      "visibility reflects existing availability confidence",
      "governed availability evidence",
      "state reflects",
      "explained state",
      "trust metadata",
      "readiness explanation confidence"
    ],
    "violation_count": 0,
    "violations": []
  },
  "disclaimer_repetition_scan": {
    "disclaimer": "This is a data-limited note, not a statement about injury status or manager intent.",
    "per_card_limit": 1,
    "scope": "Team bullpen shape rendered public copy",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "example_source": "deterministic fixture example",
  "fallback_status": "rendered",
  "pitcher": "Deterministic fixture pitcher - Coverage Arm",
  "raw_count_formula_scan": {
    "patterns": {
      "jargon_coupled_raw_count": "(?<![\\w-])\\d+\\s+of\\s+\\d+\\s+(?:trust|bridge|coverage|depth)\\s+arms?\\b",
      "parenthetical_raw_basis": "\\(\\s*\\d+\\s+of\\s+\\d+\\s*\\)",
      "parenthetical_unknown_formula": "\\([^)]*\\bunknown\\b[^)]*\\)",
      "raw_empty_arithmetic": "(?<![\\w-])\\d+\\s+of\\s+\\d+(?![\\w-])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "length option",
      "length options",
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "classified available",
      "0 of 0",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "trust metadata",
      "explained state",
      "availability read",
      "bullpen planning read",
      "explanation confidence mirrors",
      "confidence mirrors",
      "governed availability evidence",
      "state reflects",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "role_or_classification": {
    "read": "Rest-Restricted",
    "role": "Coverage Arm"
  },
  "source_path": "backend/tests/test_team_bullpen_shape.py role fixture pattern -> services.pitcher_public_labels.build_pitcher_labels",
  "status": "Limited",
  "surface_name": "Pitcher public role/read labels",
  "team": "Deterministic Context Fixture (FIX, fixture-context)",
  "weighting_scoring_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "raw score",
      "scoring weight",
      "weighted pressure"
    ],
    "violation_count": 0,
    "violations": []
  }
}
```

Rendered public copy:
```
Coverage Arm
Rest-Restricted
```

Structured fields used:

```json
{
  "availability_confidence": "high",
  "availability_data_state": "fresh",
  "availability_status": "Limited",
  "labels": {
    "read": {
      "key": "rest_restricted",
      "kind": "read",
      "label": "Rest-Restricted",
      "source": "backend:availability_status"
    },
    "role": {
      "key": "coverage_arm",
      "kind": "role",
      "label": "Coverage Arm",
      "source": "backend:role_key:long_relief"
    }
  },
  "role_input": null,
  "roster_status": {}
}
```

Evidence sections:

```json
{}
```

### Example 30: Pitcher public role/read labels

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "capitalization_sentence_scan": {
    "patterns": {
      "lowercase_sentence_start": "(?<=[.!?])\\s+([a-z])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "circular_meta_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "explanation confidence mirrors",
      "confidence mirrors",
      "visibility reflects existing availability confidence",
      "governed availability evidence",
      "state reflects",
      "explained state",
      "trust metadata",
      "readiness explanation confidence"
    ],
    "violation_count": 0,
    "violations": []
  },
  "disclaimer_repetition_scan": {
    "disclaimer": "This is a data-limited note, not a statement about injury status or manager intent.",
    "per_card_limit": 1,
    "scope": "Team bullpen shape rendered public copy",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "example_source": "deterministic fixture example",
  "fallback_status": "rendered",
  "pitcher": "Deterministic fixture pitcher - Depth Arm",
  "raw_count_formula_scan": {
    "patterns": {
      "jargon_coupled_raw_count": "(?<![\\w-])\\d+\\s+of\\s+\\d+\\s+(?:trust|bridge|coverage|depth)\\s+arms?\\b",
      "parenthetical_raw_basis": "\\(\\s*\\d+\\s+of\\s+\\d+\\s*\\)",
      "parenthetical_unknown_formula": "\\([^)]*\\bunknown\\b[^)]*\\)",
      "raw_empty_arithmetic": "(?<![\\w-])\\d+\\s+of\\s+\\d+(?![\\w-])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "length option",
      "length options",
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "classified available",
      "0 of 0",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "trust metadata",
      "explained state",
      "availability read",
      "bullpen planning read",
      "explanation confidence mirrors",
      "confidence mirrors",
      "governed availability evidence",
      "state reflects",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "role_or_classification": {
    "read": "Rest-Restricted",
    "role": "Depth Arm"
  },
  "source_path": "backend/tests/test_team_bullpen_shape.py role fixture pattern -> services.pitcher_public_labels.build_pitcher_labels",
  "status": "Avoid",
  "surface_name": "Pitcher public role/read labels",
  "team": "Deterministic Context Fixture (FIX, fixture-context)",
  "weighting_scoring_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "raw score",
      "scoring weight",
      "weighted pressure"
    ],
    "violation_count": 0,
    "violations": []
  }
}
```

Rendered public copy:
```
Depth Arm
Rest-Restricted
```

Structured fields used:

```json
{
  "availability_confidence": "high",
  "availability_data_state": "fresh",
  "availability_status": "Avoid",
  "labels": {
    "read": {
      "key": "rest_restricted",
      "kind": "read",
      "label": "Rest-Restricted",
      "source": "backend:availability_status"
    },
    "role": {
      "key": "depth_arm",
      "kind": "role",
      "label": "Depth Arm",
      "source": "backend:role_key:low_leverage"
    }
  },
  "role_input": null,
  "roster_status": {}
}
```

Evidence sections:

```json
{}
```

### Example 31: Pitcher public role/read labels

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "capitalization_sentence_scan": {
    "patterns": {
      "lowercase_sentence_start": "(?<=[.!?])\\s+([a-z])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "circular_meta_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "explanation confidence mirrors",
      "confidence mirrors",
      "visibility reflects existing availability confidence",
      "governed availability evidence",
      "state reflects",
      "explained state",
      "trust metadata",
      "readiness explanation confidence"
    ],
    "violation_count": 0,
    "violations": []
  },
  "disclaimer_repetition_scan": {
    "disclaimer": "This is a data-limited note, not a statement about injury status or manager intent.",
    "per_card_limit": 1,
    "scope": "Team bullpen shape rendered public copy",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "example_source": "deterministic fixture example",
  "fallback_status": "limited_role_context",
  "pitcher": "Deterministic fixture pitcher - Limited Read",
  "raw_count_formula_scan": {
    "patterns": {
      "jargon_coupled_raw_count": "(?<![\\w-])\\d+\\s+of\\s+\\d+\\s+(?:trust|bridge|coverage|depth)\\s+arms?\\b",
      "parenthetical_raw_basis": "\\(\\s*\\d+\\s+of\\s+\\d+\\s*\\)",
      "parenthetical_unknown_formula": "\\([^)]*\\bunknown\\b[^)]*\\)",
      "raw_empty_arithmetic": "(?<![\\w-])\\d+\\s+of\\s+\\d+(?![\\w-])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "length option",
      "length options",
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "classified available",
      "0 of 0",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "trust metadata",
      "explained state",
      "availability read",
      "bullpen planning read",
      "explanation confidence mirrors",
      "confidence mirrors",
      "governed availability evidence",
      "state reflects",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "role_or_classification": {
    "read": "Unavailable",
    "role": "Limited Read"
  },
  "source_path": "backend/tests/test_team_bullpen_shape.py role fixture pattern -> services.pitcher_public_labels.build_pitcher_labels",
  "status": "Unavailable",
  "surface_name": "Pitcher public role/read labels",
  "team": "Deterministic Context Fixture (FIX, fixture-context)",
  "weighting_scoring_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "raw score",
      "scoring weight",
      "weighted pressure"
    ],
    "violation_count": 0,
    "violations": []
  }
}
```

Rendered public copy:
```
Limited Read
Unavailable
```

Structured fields used:

```json
{
  "availability_confidence": "high",
  "availability_data_state": "fresh",
  "availability_status": "Unavailable",
  "labels": {
    "read": {
      "key": "unavailable",
      "kind": "read",
      "label": "Unavailable",
      "source": "backend:unavailable_status"
    },
    "role": {
      "key": "limited_read",
      "kind": "role",
      "label": "Limited Read",
      "source": "backend:role_key:insufficient_data"
    }
  },
  "role_input": null,
  "roster_status": {}
}
```

Evidence sections:

```json
{}
```

### Example 32: Pitcher public role/read labels

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "capitalization_sentence_scan": {
    "patterns": {
      "lowercase_sentence_start": "(?<=[.!?])\\s+([a-z])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "circular_meta_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "explanation confidence mirrors",
      "confidence mirrors",
      "visibility reflects existing availability confidence",
      "governed availability evidence",
      "state reflects",
      "explained state",
      "trust metadata",
      "readiness explanation confidence"
    ],
    "violation_count": 0,
    "violations": []
  },
  "disclaimer_repetition_scan": {
    "disclaimer": "This is a data-limited note, not a statement about injury status or manager intent.",
    "per_card_limit": 1,
    "scope": "Team bullpen shape rendered public copy",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "example_source": "deterministic fixture example",
  "fallback_status": "limited_role_context",
  "pitcher": "Deterministic fixture pitcher - Limited Read label",
  "raw_count_formula_scan": {
    "patterns": {
      "jargon_coupled_raw_count": "(?<![\\w-])\\d+\\s+of\\s+\\d+\\s+(?:trust|bridge|coverage|depth)\\s+arms?\\b",
      "parenthetical_raw_basis": "\\(\\s*\\d+\\s+of\\s+\\d+\\s*\\)",
      "parenthetical_unknown_formula": "\\([^)]*\\bunknown\\b[^)]*\\)",
      "raw_empty_arithmetic": "(?<![\\w-])\\d+\\s+of\\s+\\d+(?![\\w-])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "length option",
      "length options",
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "classified available",
      "0 of 0",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "trust metadata",
      "explained state",
      "availability read",
      "bullpen planning read",
      "explanation confidence mirrors",
      "confidence mirrors",
      "governed availability evidence",
      "state reflects",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "role_or_classification": {
    "read": "Limited Read",
    "role": "Limited Read"
  },
  "source_path": "backend/tests/test_v4_availability_explanation_integration.py missing-data fixture pattern -> services.pitcher_public_labels.build_pitcher_labels",
  "status": "Monitor",
  "surface_name": "Pitcher public role/read labels",
  "team": "Deterministic Context Fixture (FIX, fixture-context)",
  "weighting_scoring_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "raw score",
      "scoring weight",
      "weighted pressure"
    ],
    "violation_count": 0,
    "violations": []
  }
}
```

Rendered public copy:
```
Limited Read
```

Structured fields used:

```json
{
  "availability_confidence": "low",
  "availability_data_state": "missing",
  "availability_status": "Monitor",
  "labels": {
    "read": {
      "key": "limited_read",
      "kind": "read",
      "label": "Limited Read",
      "source": "backend:limited_data"
    },
    "role": {
      "key": "limited_read",
      "kind": "role",
      "label": "Limited Read",
      "source": "backend:role_key:insufficient_data"
    }
  },
  "role_input": null,
  "roster_status": {}
}
```

Evidence sections:

```json
{}
```

### Example 33: Team bullpen board context

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "capitalization_sentence_scan": {
    "patterns": {
      "lowercase_sentence_start": "(?<=[.!?])\\s+([a-z])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "circular_meta_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "explanation confidence mirrors",
      "confidence mirrors",
      "visibility reflects existing availability confidence",
      "governed availability evidence",
      "state reflects",
      "explained state",
      "trust metadata",
      "readiness explanation confidence"
    ],
    "violation_count": 0,
    "violations": []
  },
  "disclaimer_repetition_scan": {
    "disclaimer": "This is a data-limited note, not a statement about injury status or manager intent.",
    "per_card_limit": 1,
    "scope": "Team bullpen shape rendered public copy",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "example_source": "deterministic fixture example",
  "fallback_status": "rendered",
  "pitcher": null,
  "raw_count_formula_scan": {
    "patterns": {
      "jargon_coupled_raw_count": "(?<![\\w-])\\d+\\s+of\\s+\\d+\\s+(?:trust|bridge|coverage|depth)\\s+arms?\\b",
      "parenthetical_raw_basis": "\\(\\s*\\d+\\s+of\\s+\\d+\\s*\\)",
      "parenthetical_unknown_formula": "\\([^)]*\\bunknown\\b[^)]*\\)",
      "raw_empty_arithmetic": "(?<![\\w-])\\d+\\s+of\\s+\\d+(?![\\w-])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "length option",
      "length options",
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "classified available",
      "0 of 0",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "trust metadata",
      "explained state",
      "availability read",
      "bullpen planning read",
      "explanation confidence mirrors",
      "confidence mirrors",
      "governed availability evidence",
      "state reflects",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "role_or_classification": {
    "total_pitchers": 6,
    "ungrouped_pitchers": 0
  },
  "source_path": "api.bullpen._build_team_board -> services.bullpen_board.build_board_payload",
  "status": "elevated",
  "surface_name": "Team bullpen board context",
  "team": "Deterministic Context Fixture (FIX, fixture-context)",
  "weighting_scoring_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "raw score",
      "scoring weight",
      "weighted pressure"
    ],
    "violation_count": 0,
    "violations": []
  }
}
```

Rendered public copy:
```
Bullpen workload is elevated.
Two relievers are available from the latest completed workload data.
Two relievers are Avoid or Unavailable.
One reliever is in the Monitor group.
Availability classifications are workload-based only.
Available
Workload signals are inside normal ranges in the latest completed data.
Monitor
Worth a look at recent workload before counting on these arms.
Limited
Recent workload suggests limited use from the latest completed data.
Avoid
Meaningful recent-use load on these arms.
Unavailable Pitchers
Not available from the latest public workload and roster context.
```

Structured fields used:

```json
{
  "context": {
    "confidence": "high",
    "health": {
      "label": "Bullpen workload is elevated.",
      "reasons": [
        "Two relievers are available from the latest completed workload data.",
        "Two relievers are Avoid or Unavailable.",
        "One reliever is in the Monitor group.",
        "Availability classifications are workload-based only."
      ],
      "state": "elevated"
    },
    "limitations": [],
    "metrics": {
      "available": 2,
      "avoid": 1,
      "limited": 1,
      "monitor": 1,
      "pct_available": 33,
      "pct_restricted": 33,
      "pct_unavailable": 17,
      "restricted": 2,
      "total_relievers": 6,
      "unavailable": 1
    }
  },
  "freshness": {
    "data_through": "2026-06-01",
    "freshness_state": "current",
    "is_current": true,
    "limitations": []
  },
  "groups": [
    {
      "count": 2,
      "description": "Workload signals are inside normal ranges in the latest completed data.",
      "label": "Available",
      "status": "Available"
    },
    {
      "count": 1,
      "description": "Worth a look at recent workload before counting on these arms.",
      "label": "Monitor",
      "status": "Monitor"
    },
    {
      "count": 1,
      "description": "Recent workload suggests limited use from the latest completed data.",
      "label": "Limited",
      "status": "Limited"
    },
    {
      "count": 1,
      "description": "Meaningful recent-use load on these arms.",
      "label": "Avoid",
      "status": "Avoid"
    },
    {
      "count": 1,
      "description": "Not available from the latest public workload and roster context.",
      "label": "Unavailable Pitchers",
      "status": "Unavailable"
    }
  ],
  "limitations": []
}
```

Evidence sections:

```json
{
  "group_counts": {
    "Available": 2,
    "Avoid": 1,
    "Limited": 1,
    "Monitor": 1,
    "Unavailable": 1
  },
  "roster_authority_summary": {}
}
```

### Example 34: Team bullpen shape explanations

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "capitalization_sentence_scan": {
    "patterns": {
      "lowercase_sentence_start": "(?<=[.!?])\\s+([a-z])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "circular_meta_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "explanation confidence mirrors",
      "confidence mirrors",
      "visibility reflects existing availability confidence",
      "governed availability evidence",
      "state reflects",
      "explained state",
      "trust metadata",
      "readiness explanation confidence"
    ],
    "violation_count": 0,
    "violations": []
  },
  "disclaimer_repetition_scan": {
    "disclaimer": "This is a data-limited note, not a statement about injury status or manager intent.",
    "per_card_limit": 1,
    "scope": "Team bullpen shape rendered public copy",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "example_source": "deterministic fixture example",
  "fallback_status": "rendered",
  "pitcher": null,
  "raw_count_formula_scan": {
    "patterns": {
      "jargon_coupled_raw_count": "(?<![\\w-])\\d+\\s+of\\s+\\d+\\s+(?:trust|bridge|coverage|depth)\\s+arms?\\b",
      "parenthetical_raw_basis": "\\(\\s*\\d+\\s+of\\s+\\d+\\s*\\)",
      "parenthetical_unknown_formula": "\\([^)]*\\bunknown\\b[^)]*\\)",
      "raw_empty_arithmetic": "(?<![\\w-])\\d+\\s+of\\s+\\d+(?![\\w-])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "length option",
      "length options",
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "classified available",
      "0 of 0",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "trust metadata",
      "explained state",
      "availability read",
      "bullpen planning read",
      "explanation confidence mirrors",
      "confidence mirrors",
      "governed availability evidence",
      "state reflects",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "role_or_classification": {
    "read_labels": [
      "Thin Late-Inning Availability",
      "Thin Rested Bullpen",
      "High Late-Inning Pressure",
      "Heavily Concentrated Workload",
      "Limited Coverage Safety",
      "Thin Depth Safety"
    ]
  },
  "source_path": "services.team_bullpen_shape.build_team_bullpen_shape",
  "status": "team_shape",
  "surface_name": "Team bullpen shape explanations",
  "team": "Deterministic Context Fixture (FIX, fixture-context)",
  "weighting_scoring_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "raw score",
      "scoring weight",
      "weighted pressure"
    ],
    "violation_count": 0,
    "violations": []
  }
}
```

Rendered public copy:
```
Thin Late-Inning Availability
The late-inning group has one late-inning arm fully rested and no late-inning arms worth monitoring. None of that group is blocked by a heavy recent workload signal.
Thin Rested Bullpen
Only two arms are fully rested, with one rested arm who fits the late-inning bridge. The rest of the group looks more like depth coverage than leverage cushion.
High Late-Inning Pressure
The primary late-inning pocket has one arm fully rested and no arms carrying enough recent workload to narrow the path. The handoff innings add one arm with recent stress, and no arms are carrying heavy recent workload.
Heavily Concentrated Workload
Three arms have carried 84% of the recent relief work across five bullpen arms.
Limited Coverage Safety
The bullpen has no rested long reliever and no other long reliever is close to rested. One long reliever is carrying enough recent workload to limit coverage.
Thin Depth Safety
The lower-leverage layer has one arm who can cover softer innings, while two arms are carrying enough recent workload to limit the fallback cushion.
```

Structured fields used:

```json
{
  "reads": [
    {
      "explanation": "The late-inning group has one late-inning arm fully rested and no late-inning arms worth monitoring. None of that group is blocked by a heavy recent workload signal.",
      "key": "trustAvailability",
      "label": "Thin Late-Inning Availability",
      "reasons": [
        "The late-inning group has one late-inning arm fully rested and no late-inning arms worth monitoring. None of that group is blocked by a heavy recent workload signal."
      ],
      "supportingCounts": {
        "availableTrustArms": 1,
        "cleanTrustArms": 1,
        "limitedReadTrustArms": 0,
        "restRestrictedTrustArms": 0,
        "roleKnownCount": 6,
        "totalBullpenArms": 6,
        "trustArms": 1,
        "unavailableTrustArms": 0,
        "watchTrustArms": 0
      }
    },
    {
      "explanation": "Only two arms are fully rested, with one rested arm who fits the late-inning bridge. The rest of the group looks more like depth coverage than leverage cushion.",
      "key": "cleanOptions",
      "label": "Thin Rested Bullpen",
      "reasons": [
        "Only two arms are fully rested, with one rested arm who fits the late-inning bridge. The rest of the group looks more like depth coverage than leverage cushion."
      ],
      "supportingCounts": {
        "activeBullpenArms": 5,
        "cleanBridgeArms": 0,
        "cleanCoverageArms": 0,
        "cleanDepthArms": 1,
        "cleanOptionCount": 2,
        "cleanTrustArms": 1,
        "limitedReadCount": 0,
        "meaningfulCleanBacking": true,
        "restRestrictedCount": 2,
        "totalBullpenArms": 6,
        "unavailableCount": 1
      }
    },
    {
      "explanation": "The primary late-inning pocket has one arm fully rested and no arms carrying enough recent workload to narrow the path. The handoff innings add one arm with recent stress, and no arms are carrying heavy recent workload.",
      "key": "bullpenPressure",
      "label": "High Late-Inning Pressure",
      "reasons": [
        "The primary late-inning pocket has one arm fully rested and no arms carrying enough recent workload to narrow the path. The handoff innings add one arm with recent stress, and no arms are carrying heavy recent workload."
      ],
      "supportingCounts": {
        "cleanTrustArms": 1,
        "highFatigueArms": 0,
        "limitedReadCount": 0,
        "noUsableTrust": false,
        "restRestrictedCount": 2,
        "restrictedTrustArms": 0,
        "stressedBridgeArms": 0,
        "stressedCoverageArms": 1,
        "totalBullpenArms": 6,
        "unavailableCount": 1,
        "unavailableTrustArms": 0,
        "usableTrustArms": 1,
        "watchArmCount": 1
      }
    },
    {
      "explanation": "Three arms have carried 84% of the recent relief work across five bullpen arms.",
      "key": "workloadConcentration",
      "label": "Heavily Concentrated Workload",
      "reasons": [
        "Three arms have carried 84% of the recent relief work across five bullpen arms."
      ],
      "supportingCounts": {
        "concentrationDescriptor": "a heavily concentrated workload",
        "concentrationLevel": "severe",
        "participantCount": 5,
        "perArmPitches": 20.0,
        "topArmCount": 3,
        "topOneShare": 0.42,
        "topPitchTotal": 84,
        "topShare": 0.84,
        "topSharePct": 84,
        "totalRecentPitches": 100,
        "windowDays": 7
      }
    },
    {
      "explanation": "The bullpen has no rested long reliever and no other long reliever is close to rested. One long reliever is carrying enough recent workload to limit coverage.",
      "key": "coverageSafety",
      "label": "Limited Coverage Safety",
      "reasons": [
        "The bullpen has no rested long reliever and no other long reliever is close to rested. One long reliever is carrying enough recent workload to limit coverage."
      ],
      "supportingCounts": {
        "availableCoverageArms": 0,
        "cleanBridgeArms": 0,
        "cleanCoverageArms": 0,
        "coverageArms": 1,
        "limitedReadCoverageArms": 0,
        "restRestrictedCoverageArms": 1,
        "roleKnownCount": 6,
        "substituteCoverageApplied": false,
        "totalBullpenArms": 6,
        "unavailableCoverageArms": 0,
        "watchBridgeArms": 1,
        "watchCoverageArms": 0
      }
    },
    {
      "explanation": "The lower-leverage layer has one arm who can cover softer innings, while two arms are carrying enough recent workload to limit the fallback cushion.",
      "key": "depthSafety",
      "label": "Thin Depth Safety",
      "reasons": [
        "The lower-leverage layer has one arm who can cover softer innings, while two arms are carrying enough recent workload to limit the fallback cushion."
      ],
      "supportingCounts": {
        "activeBullpenArms": 5,
        "anchoredByTrust": true,
        "availableDepthArms": 1,
        "cleanDepthArms": 1,
        "depthArms": 3,
        "limitedReadDepthArms": 0,
        "restRestrictedDepthArms": 1,
        "roleKnownCount": 6,
        "totalBullpenArms": 6,
        "unavailableDepthArms": 1,
        "usableTrustArms": 1,
        "watchDepthArms": 0
      }
    }
  ],
  "source": "backend",
  "supportingCounts": {
    "activeBullpenArms": 5,
    "readKnownCount": 6,
    "roleKnownCount": 6,
    "totalBullpenArms": 6
  }
}
```

Evidence sections:

```json
{
  "read_count": 6,
  "read_keys": [
    "trustAvailability",
    "cleanOptions",
    "bullpenPressure",
    "workloadConcentration",
    "coverageSafety",
    "depthSafety"
  ]
}
```

### Example 35: Team bullpen board card labels

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "capitalization_sentence_scan": {
    "patterns": {
      "lowercase_sentence_start": "(?<=[.!?])\\s+([a-z])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "circular_meta_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "explanation confidence mirrors",
      "confidence mirrors",
      "visibility reflects existing availability confidence",
      "governed availability evidence",
      "state reflects",
      "explained state",
      "trust metadata",
      "readiness explanation confidence"
    ],
    "violation_count": 0,
    "violations": []
  },
  "disclaimer_repetition_scan": {
    "disclaimer": "This is a data-limited note, not a statement about injury status or manager intent.",
    "per_card_limit": 1,
    "scope": "Team bullpen shape rendered public copy",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "example_source": "deterministic fixture example",
  "fallback_status": "rendered",
  "pitcher": "Fixture Fresh Depth Arm",
  "raw_count_formula_scan": {
    "patterns": {
      "jargon_coupled_raw_count": "(?<![\\w-])\\d+\\s+of\\s+\\d+\\s+(?:trust|bridge|coverage|depth)\\s+arms?\\b",
      "parenthetical_raw_basis": "\\(\\s*\\d+\\s+of\\s+\\d+\\s*\\)",
      "parenthetical_unknown_formula": "\\([^)]*\\bunknown\\b[^)]*\\)",
      "raw_empty_arithmetic": "(?<![\\w-])\\d+\\s+of\\s+\\d+(?![\\w-])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "length option",
      "length options",
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "classified available",
      "0 of 0",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "trust metadata",
      "explained state",
      "availability read",
      "bullpen planning read",
      "explanation confidence mirrors",
      "confidence mirrors",
      "governed availability evidence",
      "state reflects",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "role_or_classification": {
    "group": "Available",
    "read": "Rested",
    "role": "Depth Arm"
  },
  "source_path": "services.bullpen_board.build_board_payload -> services.pitcher_public_labels.build_pitcher_labels",
  "status": "Available",
  "surface_name": "Team bullpen board card labels",
  "team": "Deterministic Context Fixture (FIX, fixture-context)",
  "weighting_scoring_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "raw score",
      "scoring weight",
      "weighted pressure"
    ],
    "violation_count": 0,
    "violations": []
  }
}
```

Rendered public copy:
```
Available
Workload signals are inside normal ranges in the latest completed data.
Low recent workload
Depth Arm
Rested
```

Structured fields used:

```json
{
  "card": {
    "availability_status": "Available",
    "confidence": "high",
    "data_state": "fresh",
    "fatigue_score": null,
    "limitations": [
      "No injury data available",
      "No team-reported availability data available"
    ],
    "pitcher_id": 9106,
    "pitcher_labels": {
      "read": {
        "key": "clean_option",
        "kind": "read",
        "label": "Rested",
        "source": "backend:availability_status"
      },
      "role": {
        "key": "depth_arm",
        "kind": "role",
        "label": "Depth Arm",
        "source": "backend:role_key:depth"
      }
    },
    "reasons": [],
    "role": {
      "confidence": "high",
      "role_key": "depth",
      "sample_size": 5
    },
    "short_reason": "Low recent workload"
  },
  "group": {
    "count": 2,
    "description": "Workload signals are inside normal ranges in the latest completed data.",
    "label": "Available",
    "status": "Available"
  }
}
```

Evidence sections:

```json
{
  "last_workload_appearance": {
    "game_date": null,
    "pitches": 0
  }
}
```

### Example 36: Team bullpen board card labels

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "capitalization_sentence_scan": {
    "patterns": {
      "lowercase_sentence_start": "(?<=[.!?])\\s+([a-z])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "circular_meta_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "explanation confidence mirrors",
      "confidence mirrors",
      "visibility reflects existing availability confidence",
      "governed availability evidence",
      "state reflects",
      "explained state",
      "trust metadata",
      "readiness explanation confidence"
    ],
    "violation_count": 0,
    "violations": []
  },
  "disclaimer_repetition_scan": {
    "disclaimer": "This is a data-limited note, not a statement about injury status or manager intent.",
    "per_card_limit": 1,
    "scope": "Team bullpen shape rendered public copy",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "example_source": "deterministic fixture example",
  "fallback_status": "rendered",
  "pitcher": "Fixture Bridge Arm",
  "raw_count_formula_scan": {
    "patterns": {
      "jargon_coupled_raw_count": "(?<![\\w-])\\d+\\s+of\\s+\\d+\\s+(?:trust|bridge|coverage|depth)\\s+arms?\\b",
      "parenthetical_raw_basis": "\\(\\s*\\d+\\s+of\\s+\\d+\\s*\\)",
      "parenthetical_unknown_formula": "\\([^)]*\\bunknown\\b[^)]*\\)",
      "raw_empty_arithmetic": "(?<![\\w-])\\d+\\s+of\\s+\\d+(?![\\w-])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "length option",
      "length options",
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "classified available",
      "0 of 0",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "trust metadata",
      "explained state",
      "availability read",
      "bullpen planning read",
      "explanation confidence mirrors",
      "confidence mirrors",
      "governed availability evidence",
      "state reflects",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "role_or_classification": {
    "group": "Monitor",
    "read": "Watch Arm",
    "role": "Bridge Arm"
  },
  "source_path": "services.bullpen_board.build_board_payload -> services.pitcher_public_labels.build_pitcher_labels",
  "status": "Monitor",
  "surface_name": "Team bullpen board card labels",
  "team": "Deterministic Context Fixture (FIX, fixture-context)",
  "weighting_scoring_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "raw score",
      "scoring weight",
      "weighted pressure"
    ],
    "violation_count": 0,
    "violations": []
  }
}
```

Rendered public copy:
```
Monitor
Worth a look at recent workload before counting on these arms.
16 pitches yesterday
Bridge Arm
Watch Arm
```

Structured fields used:

```json
{
  "card": {
    "availability_status": "Monitor",
    "confidence": "high",
    "data_state": "fresh",
    "fatigue_score": null,
    "limitations": [
      "No injury data available",
      "No team-reported availability data available"
    ],
    "pitcher_id": 9102,
    "pitcher_labels": {
      "read": {
        "key": "watch_arm",
        "kind": "read",
        "label": "Watch Arm",
        "source": "backend:availability_status"
      },
      "role": {
        "key": "bridge_arm",
        "kind": "role",
        "label": "Bridge Arm",
        "source": "backend:role_key:setup_bridge"
      }
    },
    "reasons": [
      "16 pitches yesterday",
      "Only 1 day of rest"
    ],
    "role": {
      "confidence": "high",
      "role_key": "setup_bridge",
      "sample_size": 5
    },
    "short_reason": "16 pitches yesterday"
  },
  "group": {
    "count": 1,
    "description": "Worth a look at recent workload before counting on these arms.",
    "label": "Monitor",
    "status": "Monitor"
  }
}
```

Evidence sections:

```json
{
  "last_workload_appearance": {
    "game_date": null,
    "pitches": 16
  }
}
```

### Example 37: Team bullpen board card labels

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "capitalization_sentence_scan": {
    "patterns": {
      "lowercase_sentence_start": "(?<=[.!?])\\s+([a-z])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "circular_meta_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "explanation confidence mirrors",
      "confidence mirrors",
      "visibility reflects existing availability confidence",
      "governed availability evidence",
      "state reflects",
      "explained state",
      "trust metadata",
      "readiness explanation confidence"
    ],
    "violation_count": 0,
    "violations": []
  },
  "disclaimer_repetition_scan": {
    "disclaimer": "This is a data-limited note, not a statement about injury status or manager intent.",
    "per_card_limit": 1,
    "scope": "Team bullpen shape rendered public copy",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "example_source": "deterministic fixture example",
  "fallback_status": "rendered",
  "pitcher": "Fixture Coverage Arm",
  "raw_count_formula_scan": {
    "patterns": {
      "jargon_coupled_raw_count": "(?<![\\w-])\\d+\\s+of\\s+\\d+\\s+(?:trust|bridge|coverage|depth)\\s+arms?\\b",
      "parenthetical_raw_basis": "\\(\\s*\\d+\\s+of\\s+\\d+\\s*\\)",
      "parenthetical_unknown_formula": "\\([^)]*\\bunknown\\b[^)]*\\)",
      "raw_empty_arithmetic": "(?<![\\w-])\\d+\\s+of\\s+\\d+(?![\\w-])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "length option",
      "length options",
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "classified available",
      "0 of 0",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "trust metadata",
      "explained state",
      "availability read",
      "bullpen planning read",
      "explanation confidence mirrors",
      "confidence mirrors",
      "governed availability evidence",
      "state reflects",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "role_or_classification": {
    "group": "Limited",
    "read": "Rest-Restricted",
    "role": "Coverage Arm"
  },
  "source_path": "services.bullpen_board.build_board_payload -> services.pitcher_public_labels.build_pitcher_labels",
  "status": "Limited",
  "surface_name": "Team bullpen board card labels",
  "team": "Deterministic Context Fixture (FIX, fixture-context)",
  "weighting_scoring_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "raw score",
      "scoring weight",
      "weighted pressure"
    ],
    "violation_count": 0,
    "violations": []
  }
}
```

Rendered public copy:
```
Limited
Recent workload suggests limited use from the latest completed data.
28 pitches yesterday
Coverage Arm
Rest-Restricted
```

Structured fields used:

```json
{
  "card": {
    "availability_status": "Limited",
    "confidence": "high",
    "data_state": "fresh",
    "fatigue_score": null,
    "limitations": [
      "No injury data available",
      "No team-reported availability data available"
    ],
    "pitcher_id": 9103,
    "pitcher_labels": {
      "read": {
        "key": "rest_restricted",
        "kind": "read",
        "label": "Rest-Restricted",
        "source": "backend:availability_status"
      },
      "role": {
        "key": "coverage_arm",
        "kind": "role",
        "label": "Coverage Arm",
        "source": "backend:role_key:long_relief"
      }
    },
    "reasons": [
      "28 pitches yesterday",
      "Only 1 day of rest"
    ],
    "role": {
      "confidence": "high",
      "role_key": "long_relief",
      "sample_size": 5
    },
    "short_reason": "28 pitches yesterday"
  },
  "group": {
    "count": 1,
    "description": "Recent workload suggests limited use from the latest completed data.",
    "label": "Limited",
    "status": "Limited"
  }
}
```

Evidence sections:

```json
{
  "last_workload_appearance": {
    "game_date": null,
    "pitches": 28
  }
}
```

### Example 38: Team bullpen board card labels

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "capitalization_sentence_scan": {
    "patterns": {
      "lowercase_sentence_start": "(?<=[.!?])\\s+([a-z])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "circular_meta_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "explanation confidence mirrors",
      "confidence mirrors",
      "visibility reflects existing availability confidence",
      "governed availability evidence",
      "state reflects",
      "explained state",
      "trust metadata",
      "readiness explanation confidence"
    ],
    "violation_count": 0,
    "violations": []
  },
  "disclaimer_repetition_scan": {
    "disclaimer": "This is a data-limited note, not a statement about injury status or manager intent.",
    "per_card_limit": 1,
    "scope": "Team bullpen shape rendered public copy",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "example_source": "deterministic fixture example",
  "fallback_status": "rendered",
  "pitcher": "Fixture Depth Arm",
  "raw_count_formula_scan": {
    "patterns": {
      "jargon_coupled_raw_count": "(?<![\\w-])\\d+\\s+of\\s+\\d+\\s+(?:trust|bridge|coverage|depth)\\s+arms?\\b",
      "parenthetical_raw_basis": "\\(\\s*\\d+\\s+of\\s+\\d+\\s*\\)",
      "parenthetical_unknown_formula": "\\([^)]*\\bunknown\\b[^)]*\\)",
      "raw_empty_arithmetic": "(?<![\\w-])\\d+\\s+of\\s+\\d+(?![\\w-])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "length option",
      "length options",
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "classified available",
      "0 of 0",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "trust metadata",
      "explained state",
      "availability read",
      "bullpen planning read",
      "explanation confidence mirrors",
      "confidence mirrors",
      "governed availability evidence",
      "state reflects",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "role_or_classification": {
    "group": "Avoid",
    "read": "Rest-Restricted",
    "role": "Depth Arm"
  },
  "source_path": "services.bullpen_board.build_board_payload -> services.pitcher_public_labels.build_pitcher_labels",
  "status": "Avoid",
  "surface_name": "Team bullpen board card labels",
  "team": "Deterministic Context Fixture (FIX, fixture-context)",
  "weighting_scoring_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "raw score",
      "scoring weight",
      "weighted pressure"
    ],
    "violation_count": 0,
    "violations": []
  }
}
```

Rendered public copy:
```
Avoid
Meaningful recent-use load on these arms.
42 pitches yesterday
Depth Arm
Rest-Restricted
```

Structured fields used:

```json
{
  "card": {
    "availability_status": "Avoid",
    "confidence": "high",
    "data_state": "fresh",
    "fatigue_score": null,
    "limitations": [
      "No injury data available",
      "No team-reported availability data available"
    ],
    "pitcher_id": 9104,
    "pitcher_labels": {
      "read": {
        "key": "rest_restricted",
        "kind": "read",
        "label": "Rest-Restricted",
        "source": "backend:availability_status"
      },
      "role": {
        "key": "depth_arm",
        "kind": "role",
        "label": "Depth Arm",
        "source": "backend:role_key:low_leverage"
      }
    },
    "reasons": [
      "42 pitches yesterday",
      "42 pitches in 3 days",
      "Only 1 day of rest"
    ],
    "role": {
      "confidence": "high",
      "role_key": "low_leverage",
      "sample_size": 5
    },
    "short_reason": "42 pitches yesterday"
  },
  "group": {
    "count": 1,
    "description": "Meaningful recent-use load on these arms.",
    "label": "Avoid",
    "status": "Avoid"
  }
}
```

Evidence sections:

```json
{
  "last_workload_appearance": {
    "game_date": null,
    "pitches": 42
  }
}
```

### Example 39: Team bullpen board card labels

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "capitalization_sentence_scan": {
    "patterns": {
      "lowercase_sentence_start": "(?<=[.!?])\\s+([a-z])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "circular_meta_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "explanation confidence mirrors",
      "confidence mirrors",
      "visibility reflects existing availability confidence",
      "governed availability evidence",
      "state reflects",
      "explained state",
      "trust metadata",
      "readiness explanation confidence"
    ],
    "violation_count": 0,
    "violations": []
  },
  "disclaimer_repetition_scan": {
    "disclaimer": "This is a data-limited note, not a statement about injury status or manager intent.",
    "per_card_limit": 1,
    "scope": "Team bullpen shape rendered public copy",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "example_source": "deterministic fixture example",
  "fallback_status": "rendered",
  "pitcher": "Fixture Unavailable Arm",
  "raw_count_formula_scan": {
    "patterns": {
      "jargon_coupled_raw_count": "(?<![\\w-])\\d+\\s+of\\s+\\d+\\s+(?:trust|bridge|coverage|depth)\\s+arms?\\b",
      "parenthetical_raw_basis": "\\(\\s*\\d+\\s+of\\s+\\d+\\s*\\)",
      "parenthetical_unknown_formula": "\\([^)]*\\bunknown\\b[^)]*\\)",
      "raw_empty_arithmetic": "(?<![\\w-])\\d+\\s+of\\s+\\d+(?![\\w-])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "length option",
      "length options",
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "classified available",
      "0 of 0",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "trust metadata",
      "explained state",
      "availability read",
      "bullpen planning read",
      "explanation confidence mirrors",
      "confidence mirrors",
      "governed availability evidence",
      "state reflects",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "role_or_classification": {
    "group": "Unavailable Pitchers",
    "read": "Unavailable",
    "role": "Depth Arm"
  },
  "source_path": "services.bullpen_board.build_board_payload -> services.pitcher_public_labels.build_pitcher_labels",
  "status": "Unavailable",
  "surface_name": "Team bullpen board card labels",
  "team": "Deterministic Context Fixture (FIX, fixture-context)",
  "weighting_scoring_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "raw score",
      "scoring weight",
      "weighted pressure"
    ],
    "violation_count": 0,
    "violations": []
  }
}
```

Rendered public copy:
```
Unavailable Pitchers
Not available from the latest public workload and roster context.
52 pitches yesterday
Depth Arm
Unavailable
```

Structured fields used:

```json
{
  "card": {
    "availability_status": "Unavailable",
    "confidence": "high",
    "data_state": "fresh",
    "fatigue_score": null,
    "limitations": [
      "No injury data available",
      "No team-reported availability data available"
    ],
    "pitcher_id": 9105,
    "pitcher_labels": {
      "read": {
        "key": "unavailable",
        "kind": "read",
        "label": "Unavailable",
        "source": "backend:unavailable_status"
      },
      "role": {
        "key": "depth_arm",
        "kind": "role",
        "label": "Depth Arm",
        "source": "backend:role_key:depth"
      }
    },
    "reasons": [
      "52 pitches yesterday",
      "52 pitches in 3 days",
      "Only 1 day of rest"
    ],
    "role": {
      "confidence": "high",
      "role_key": "depth",
      "sample_size": 5
    },
    "short_reason": "52 pitches yesterday"
  },
  "group": {
    "count": 1,
    "description": "Not available from the latest public workload and roster context.",
    "label": "Unavailable Pitchers",
    "status": "Unavailable"
  }
}
```

Evidence sections:

```json
{
  "last_workload_appearance": {
    "game_date": null,
    "pitches": 52
  }
}
```

### Example 40: Team Operations readiness V4 explanation

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "capitalization_sentence_scan": {
    "patterns": {
      "lowercase_sentence_start": "(?<=[.!?])\\s+([a-z])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "circular_meta_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "explanation confidence mirrors",
      "confidence mirrors",
      "visibility reflects existing availability confidence",
      "governed availability evidence",
      "state reflects",
      "explained state",
      "trust metadata",
      "readiness explanation confidence"
    ],
    "violation_count": 0,
    "violations": []
  },
  "disclaimer_repetition_scan": {
    "disclaimer": "This is a data-limited note, not a statement about injury status or manager intent.",
    "per_card_limit": 1,
    "scope": "Team bullpen shape rendered public copy",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "example_source": "deterministic fixture example",
  "fallback_status": "rendered",
  "pitcher": null,
  "raw_count_formula_scan": {
    "patterns": {
      "jargon_coupled_raw_count": "(?<![\\w-])\\d+\\s+of\\s+\\d+\\s+(?:trust|bridge|coverage|depth)\\s+arms?\\b",
      "parenthetical_raw_basis": "\\(\\s*\\d+\\s+of\\s+\\d+\\s*\\)",
      "parenthetical_unknown_formula": "\\([^)]*\\bunknown\\b[^)]*\\)",
      "raw_empty_arithmetic": "(?<![\\w-])\\d+\\s+of\\s+\\d+(?![\\w-])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "length option",
      "length options",
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "classified available",
      "0 of 0",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "trust metadata",
      "explained state",
      "availability read",
      "bullpen planning read",
      "explanation confidence mirrors",
      "confidence mirrors",
      "governed availability evidence",
      "state reflects",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "role_or_classification": {
    "readiness_status": "Operationally Stable",
    "readiness_status_code": "operationally_stable",
    "scope": "readiness_state"
  },
  "source_path": "backend/tests/test_v4_team_operations_readiness_explanation_integration.py fixture pattern -> team_operations.assemble_bullpen_readiness -> explanations.readiness.serialize_readiness_explanation",
  "status": "operationally_stable",
  "surface_name": "Team Operations readiness V4 explanation",
  "team": "Deterministic Context Fixture (FIX, fixture-context)",
  "weighting_scoring_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "raw score",
      "scoring weight",
      "weighted pressure"
    ],
    "violation_count": 0,
    "violations": []
  }
}
```

Rendered public copy:
```
The public data is not strong enough to give this team a full bullpen readiness note.
Readiness is based on public workload data, not private team information.
Readiness is not injury or medical information.
Readiness is not a performance forecast.
Manager intent and bullpen warm-up state are not available.
The user remains responsible for baseball decisions.
The stored workload data is current enough for this team note.
```

Structured fields used:

```json
{
  "availability_distribution": {
    "available": 2,
    "avoid": 0,
    "limited": 0,
    "monitor": 0,
    "total": 2,
    "unavailable": 0,
    "unknown": 0
  },
  "constraints": [],
  "coverage_inventory": {
    "active_pitcher_count": 2,
    "availability_covered_count": 2,
    "availability_missing_count": 0,
    "coverage_state": "covered",
    "current_workload_data_count": 2,
    "missing_workload_data_count": 0
  },
  "freshness": {
    "data_through": "2026-06-03",
    "freshness_state": "current",
    "generated_at": "2026-06-03T12:00:00Z",
    "last_successful_sync": "2026-06-03T11:30:00Z",
    "latest_fatigue_calculated_at": "2026-06-03T11:45:00Z",
    "latest_sync_status": "success",
    "latest_workload_date": "2026-06-03",
    "limitations": [],
    "missing_data_warning": null,
    "stale_warning": null
  },
  "handedness_coverage": {
    "coverage_state": "covered",
    "left_handed_count": 1,
    "limitations": [],
    "right_handed_count": 1,
    "unknown_count": 0
  },
  "readiness": {
    "basis": [
      "availability_distribution",
      "workload_pressure",
      "freshness",
      "trust_metadata"
    ],
    "status": "Operationally Stable",
    "status_code": "operationally_stable",
    "summary": "Team-level bullpen readiness looks steady from current public workload evidence."
  },
  "trust_metadata": {
    "capability": "team_operations_bullpen_readiness",
    "confidence": "high",
    "confidence_reasons": [
      "fresh_data",
      "complete_metadata"
    ],
    "data_state": "fresh",
    "explanations": [],
    "generated_at": "2026-06-03T12:00:00Z",
    "governance_state": "compliant",
    "limitations": [],
    "ranking_applied": false,
    "refusal_reasons": [],
    "scope": "team_bullpen_readiness",
    "selection_made": false,
    "source_evidence_state": "represented",
    "trust_validation_errors": []
  },
  "workload_pressure": {
    "elevated_count": 0,
    "latest_workload_date": "2026-06-03",
    "low_count": 2,
    "moderate_count": 0,
    "pressure_state": "low",
    "pressure_state_code": "low",
    "summary": "Recent workload pressure is low at the team level.",
    "unknown_count": 0
  }
}
```

Evidence sections:

```json
{
  "limitations": [
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "insufficient_context",
      "severity": "informational",
      "summary": "Readiness is based on public workload data, not private team information."
    },
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "insufficient_context",
      "severity": "informational",
      "summary": "Readiness is not injury or medical information."
    },
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "insufficient_context",
      "severity": "informational",
      "summary": "Readiness is not a performance forecast."
    },
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "insufficient_context",
      "severity": "informational",
      "summary": "Manager intent and bullpen warm-up state are not available."
    },
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "insufficient_context",
      "severity": "informational",
      "summary": "The user remains responsible for baseball decisions."
    }
  ],
  "primary_reasons": [],
  "supporting_evidence": [
    {
      "evidence_type": "readiness_status",
      "impact": "explains_readiness_state",
      "label": "Readiness status",
      "source": "team_operations_bullpen_readiness",
      "unit": "status",
      "value": "Operationally Stable"
    },
    {
      "evidence_type": "readiness_status_code",
      "impact": "explains_readiness_state",
      "label": "Readiness status code",
      "source": "team_operations_bullpen_readiness",
      "unit": "status_code",
      "value": "operationally_stable"
    },
    {
      "evidence_type": "readiness_contract_state",
      "impact": "explains_output_boundary",
      "label": "Readiness contract state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "available"
    },
    {
      "evidence_type": "readiness_basis",
      "impact": "explains_input_scope",
      "label": "Readiness basis",
      "source": "team_operations_bullpen_readiness",
      "unit": "sources",
      "value": [
        "availability_distribution",
        "workload_pressure",
        "freshness",
        "trust_metadata"
      ]
    },
    {
      "evidence_type": "readiness_freshness_state",
      "impact": "explains_freshness_boundary",
      "label": "Freshness state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "current"
    },
    {
      "evidence_type": "readiness_trust_confidence",
      "impact": "explains_confidence_boundary",
      "label": "Trust confidence",
      "source": "team_operations_bullpen_readiness",
      "unit": "level",
      "value": "high"
    },
    {
      "evidence_type": "readiness_trust_data_state",
      "impact": "explains_trust_boundary",
      "label": "Trust data state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "fresh"
    },
    {
      "evidence_type": "workload_pressure_state",
      "impact": "explains_workload_state",
      "label": "Workload pressure state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "low"
    },
    {
      "evidence_type": "coverage_inventory_state",
      "impact": "explains_coverage_state",
      "label": "Coverage inventory state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "covered"
    },
    {
      "evidence_type": "handedness_coverage_state",
      "impact": "explains_coverage_state",
      "label": "Handedness coverage state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "covered"
    },
    {
      "evidence_type": "workload_pressure_low_count",
      "impact": "explains_workload_state",
      "label": "Low workload count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 2
    },
    {
      "evidence_type": "workload_pressure_moderate_count",
      "impact": "explains_workload_state",
      "label": "Moderate workload count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 0
    },
    {
      "evidence_type": "workload_pressure_elevated_count",
      "impact": "explains_workload_state",
      "label": "Elevated workload count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 0
    },
    {
      "evidence_type": "workload_pressure_unknown_count",
      "impact": "explains_workload_state",
      "label": "Unknown workload count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 0
    },
    {
      "evidence_type": "availability_distribution_available",
      "impact": "explains_availability_state",
      "label": "Available inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 2
    },
    {
      "evidence_type": "availability_distribution_monitor",
      "impact": "explains_availability_state",
      "label": "Monitor inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 0
    },
    {
      "evidence_type": "availability_distribution_limited",
      "impact": "explains_availability_state",
      "label": "Limited inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 0
    },
    {
      "evidence_type": "availability_distribution_avoid",
      "impact": "explains_availability_state",
      "label": "Avoid inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 0
    },
    {
      "evidence_type": "availability_distribution_unavailable",
      "impact": "explains_availability_state",
      "label": "Unavailable inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 0
    },
    {
      "evidence_type": "availability_distribution_unknown",
      "impact": "explains_availability_state",
      "label": "Unknown availability count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 0
    },
    {
      "evidence_type": "availability_distribution_total",
      "impact": "explains_availability_state",
      "label": "Total availability inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 2
    },
    {
      "evidence_type": "coverage_inventory_active_pitcher_count",
      "impact": "explains_coverage_state",
      "label": "Active pitcher count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 2
    },
    {
      "evidence_type": "coverage_inventory_current_workload_data_count",
      "impact": "explains_coverage_state",
      "label": "Current workload data count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 2
    },
    {
      "evidence_type": "coverage_inventory_missing_workload_data_count",
      "impact": "explains_coverage_state",
      "label": "Missing workload data count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 0
    },
    {
      "evidence_type": "coverage_inventory_availability_covered_count",
      "impact": "explains_coverage_state",
      "label": "Availability covered count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 2
    },
    {
      "evidence_type": "coverage_inventory_availability_missing_count",
      "impact": "explains_coverage_state",
      "label": "Availability missing count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 0
    },
    {
      "evidence_type": "handedness_coverage_left_handed_count",
      "impact": "explains_coverage_state",
      "label": "Left handed count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 1
    },
    {
      "evidence_type": "handedness_coverage_right_handed_count",
      "impact": "explains_coverage_state",
      "label": "Right handed count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 1
    },
    {
      "evidence_type": "handedness_coverage_unknown_count",
      "impact": "explains_coverage_state",
      "label": "Unknown handedness count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 0
    }
  ]
}
```

### Example 41: Team Operations readiness V4 explanation

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "capitalization_sentence_scan": {
    "patterns": {
      "lowercase_sentence_start": "(?<=[.!?])\\s+([a-z])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "circular_meta_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "explanation confidence mirrors",
      "confidence mirrors",
      "visibility reflects existing availability confidence",
      "governed availability evidence",
      "state reflects",
      "explained state",
      "trust metadata",
      "readiness explanation confidence"
    ],
    "violation_count": 0,
    "violations": []
  },
  "disclaimer_repetition_scan": {
    "disclaimer": "This is a data-limited note, not a statement about injury status or manager intent.",
    "per_card_limit": 1,
    "scope": "Team bullpen shape rendered public copy",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "example_source": "deterministic fixture example",
  "fallback_status": "rendered",
  "pitcher": null,
  "raw_count_formula_scan": {
    "patterns": {
      "jargon_coupled_raw_count": "(?<![\\w-])\\d+\\s+of\\s+\\d+\\s+(?:trust|bridge|coverage|depth)\\s+arms?\\b",
      "parenthetical_raw_basis": "\\(\\s*\\d+\\s+of\\s+\\d+\\s*\\)",
      "parenthetical_unknown_formula": "\\([^)]*\\bunknown\\b[^)]*\\)",
      "raw_empty_arithmetic": "(?<![\\w-])\\d+\\s+of\\s+\\d+(?![\\w-])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "length option",
      "length options",
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "classified available",
      "0 of 0",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "trust metadata",
      "explained state",
      "availability read",
      "bullpen planning read",
      "explanation confidence mirrors",
      "confidence mirrors",
      "governed availability evidence",
      "state reflects",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "role_or_classification": {
    "readiness_status": "Operationally Constrained",
    "readiness_status_code": "operationally_constrained",
    "scope": "readiness_state"
  },
  "source_path": "backend/tests/test_v4_team_operations_readiness_explanation_integration.py fixture pattern -> team_operations.assemble_bullpen_readiness -> explanations.readiness.serialize_readiness_explanation",
  "status": "operationally_constrained",
  "surface_name": "Team Operations readiness V4 explanation",
  "team": "Deterministic Context Fixture (FIX, fixture-context)",
  "weighting_scoring_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "raw score",
      "scoring weight",
      "weighted pressure"
    ],
    "violation_count": 0,
    "violations": []
  }
}
```

Rendered public copy:
```
The public data is not strong enough to give this team a full bullpen readiness note.
Readiness is based on public workload data, not private team information.
Readiness is not injury or medical information.
Readiness is not a performance forecast.
Manager intent and bullpen warm-up state are not available.
The user remains responsible for baseball decisions.
The stored workload data is current enough for this team note.
```

Structured fields used:

```json
{
  "availability_distribution": {
    "available": 1,
    "avoid": 0,
    "limited": 1,
    "monitor": 1,
    "total": 3,
    "unavailable": 0,
    "unknown": 0
  },
  "constraints": [],
  "coverage_inventory": {
    "active_pitcher_count": 3,
    "availability_covered_count": 3,
    "availability_missing_count": 0,
    "coverage_state": "covered",
    "current_workload_data_count": 3,
    "missing_workload_data_count": 0
  },
  "freshness": {
    "data_through": "2026-06-03",
    "freshness_state": "current",
    "generated_at": "2026-06-03T12:00:00Z",
    "last_successful_sync": "2026-06-03T11:30:00Z",
    "latest_fatigue_calculated_at": "2026-06-03T11:45:00Z",
    "latest_sync_status": "success",
    "latest_workload_date": "2026-06-03",
    "limitations": [],
    "missing_data_warning": null,
    "stale_warning": null
  },
  "handedness_coverage": {
    "coverage_state": "covered",
    "left_handed_count": 1,
    "limitations": [],
    "right_handed_count": 2,
    "unknown_count": 0
  },
  "readiness": {
    "basis": [
      "availability_distribution",
      "workload_pressure",
      "freshness",
      "trust_metadata"
    ],
    "status": "Operationally Constrained",
    "status_code": "operationally_constrained",
    "summary": "Team-level bullpen readiness is constrained by workload or coverage context."
  },
  "trust_metadata": {
    "capability": "team_operations_bullpen_readiness",
    "confidence": "high",
    "confidence_reasons": [
      "fresh_data",
      "complete_metadata"
    ],
    "data_state": "fresh",
    "explanations": [],
    "generated_at": "2026-06-03T12:00:00Z",
    "governance_state": "compliant",
    "limitations": [],
    "ranking_applied": false,
    "refusal_reasons": [],
    "scope": "team_bullpen_readiness",
    "selection_made": false,
    "source_evidence_state": "represented",
    "trust_validation_errors": []
  },
  "workload_pressure": {
    "elevated_count": 0,
    "latest_workload_date": "2026-06-03",
    "low_count": 2,
    "moderate_count": 1,
    "pressure_state": "moderate",
    "pressure_state_code": "moderate",
    "summary": "Recent workload pressure is moderate at the team level.",
    "unknown_count": 0
  }
}
```

Evidence sections:

```json
{
  "limitations": [
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "insufficient_context",
      "severity": "informational",
      "summary": "Readiness is based on public workload data, not private team information."
    },
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "insufficient_context",
      "severity": "informational",
      "summary": "Readiness is not injury or medical information."
    },
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "insufficient_context",
      "severity": "informational",
      "summary": "Readiness is not a performance forecast."
    },
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "insufficient_context",
      "severity": "informational",
      "summary": "Manager intent and bullpen warm-up state are not available."
    },
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "insufficient_context",
      "severity": "informational",
      "summary": "The user remains responsible for baseball decisions."
    }
  ],
  "primary_reasons": [
    {
      "code": "READINESS_DEGRADED_BY_LIMITATIONS",
      "label": "Readiness degraded by limitations",
      "scope": "readiness_state",
      "summary": "The public data is not strong enough to give this team a full bullpen readiness note."
    }
  ],
  "supporting_evidence": [
    {
      "evidence_type": "readiness_status",
      "impact": "explains_readiness_state",
      "label": "Readiness status",
      "source": "team_operations_bullpen_readiness",
      "unit": "status",
      "value": "Operationally Constrained"
    },
    {
      "evidence_type": "readiness_status_code",
      "impact": "explains_readiness_state",
      "label": "Readiness status code",
      "source": "team_operations_bullpen_readiness",
      "unit": "status_code",
      "value": "operationally_constrained"
    },
    {
      "evidence_type": "readiness_contract_state",
      "impact": "explains_output_boundary",
      "label": "Readiness contract state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "available"
    },
    {
      "evidence_type": "readiness_basis",
      "impact": "explains_input_scope",
      "label": "Readiness basis",
      "source": "team_operations_bullpen_readiness",
      "unit": "sources",
      "value": [
        "availability_distribution",
        "workload_pressure",
        "freshness",
        "trust_metadata"
      ]
    },
    {
      "evidence_type": "readiness_freshness_state",
      "impact": "explains_freshness_boundary",
      "label": "Freshness state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "current"
    },
    {
      "evidence_type": "readiness_trust_confidence",
      "impact": "explains_confidence_boundary",
      "label": "Trust confidence",
      "source": "team_operations_bullpen_readiness",
      "unit": "level",
      "value": "high"
    },
    {
      "evidence_type": "readiness_trust_data_state",
      "impact": "explains_trust_boundary",
      "label": "Trust data state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "fresh"
    },
    {
      "evidence_type": "workload_pressure_state",
      "impact": "explains_workload_state",
      "label": "Workload pressure state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "moderate"
    },
    {
      "evidence_type": "coverage_inventory_state",
      "impact": "explains_coverage_state",
      "label": "Coverage inventory state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "covered"
    },
    {
      "evidence_type": "handedness_coverage_state",
      "impact": "explains_coverage_state",
      "label": "Handedness coverage state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "covered"
    },
    {
      "evidence_type": "workload_pressure_low_count",
      "impact": "explains_workload_state",
      "label": "Low workload count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 2
    },
    {
      "evidence_type": "workload_pressure_moderate_count",
      "impact": "explains_workload_state",
      "label": "Moderate workload count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 1
    },
    {
      "evidence_type": "workload_pressure_elevated_count",
      "impact": "explains_workload_state",
      "label": "Elevated workload count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 0
    },
    {
      "evidence_type": "workload_pressure_unknown_count",
      "impact": "explains_workload_state",
      "label": "Unknown workload count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 0
    },
    {
      "evidence_type": "availability_distribution_available",
      "impact": "explains_availability_state",
      "label": "Available inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 1
    },
    {
      "evidence_type": "availability_distribution_monitor",
      "impact": "explains_availability_state",
      "label": "Monitor inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 1
    },
    {
      "evidence_type": "availability_distribution_limited",
      "impact": "explains_availability_state",
      "label": "Limited inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 1
    },
    {
      "evidence_type": "availability_distribution_avoid",
      "impact": "explains_availability_state",
      "label": "Avoid inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 0
    },
    {
      "evidence_type": "availability_distribution_unavailable",
      "impact": "explains_availability_state",
      "label": "Unavailable inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 0
    },
    {
      "evidence_type": "availability_distribution_unknown",
      "impact": "explains_availability_state",
      "label": "Unknown availability count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 0
    },
    {
      "evidence_type": "availability_distribution_total",
      "impact": "explains_availability_state",
      "label": "Total availability inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 3
    },
    {
      "evidence_type": "coverage_inventory_active_pitcher_count",
      "impact": "explains_coverage_state",
      "label": "Active pitcher count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 3
    },
    {
      "evidence_type": "coverage_inventory_current_workload_data_count",
      "impact": "explains_coverage_state",
      "label": "Current workload data count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 3
    },
    {
      "evidence_type": "coverage_inventory_missing_workload_data_count",
      "impact": "explains_coverage_state",
      "label": "Missing workload data count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 0
    },
    {
      "evidence_type": "coverage_inventory_availability_covered_count",
      "impact": "explains_coverage_state",
      "label": "Availability covered count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 3
    },
    {
      "evidence_type": "coverage_inventory_availability_missing_count",
      "impact": "explains_coverage_state",
      "label": "Availability missing count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 0
    },
    {
      "evidence_type": "handedness_coverage_left_handed_count",
      "impact": "explains_coverage_state",
      "label": "Left handed count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 1
    },
    {
      "evidence_type": "handedness_coverage_right_handed_count",
      "impact": "explains_coverage_state",
      "label": "Right handed count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 2
    },
    {
      "evidence_type": "handedness_coverage_unknown_count",
      "impact": "explains_coverage_state",
      "label": "Unknown handedness count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 0
    }
  ]
}
```

### Example 42: Team Operations readiness V4 explanation

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "capitalization_sentence_scan": {
    "patterns": {
      "lowercase_sentence_start": "(?<=[.!?])\\s+([a-z])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "circular_meta_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "explanation confidence mirrors",
      "confidence mirrors",
      "visibility reflects existing availability confidence",
      "governed availability evidence",
      "state reflects",
      "explained state",
      "trust metadata",
      "readiness explanation confidence"
    ],
    "violation_count": 0,
    "violations": []
  },
  "disclaimer_repetition_scan": {
    "disclaimer": "This is a data-limited note, not a statement about injury status or manager intent.",
    "per_card_limit": 1,
    "scope": "Team bullpen shape rendered public copy",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "example_source": "deterministic fixture example",
  "fallback_status": "rendered",
  "pitcher": null,
  "raw_count_formula_scan": {
    "patterns": {
      "jargon_coupled_raw_count": "(?<![\\w-])\\d+\\s+of\\s+\\d+\\s+(?:trust|bridge|coverage|depth)\\s+arms?\\b",
      "parenthetical_raw_basis": "\\(\\s*\\d+\\s+of\\s+\\d+\\s*\\)",
      "parenthetical_unknown_formula": "\\([^)]*\\bunknown\\b[^)]*\\)",
      "raw_empty_arithmetic": "(?<![\\w-])\\d+\\s+of\\s+\\d+(?![\\w-])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "length option",
      "length options",
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "classified available",
      "0 of 0",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "trust metadata",
      "explained state",
      "availability read",
      "bullpen planning read",
      "explanation confidence mirrors",
      "confidence mirrors",
      "governed availability evidence",
      "state reflects",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "role_or_classification": {
    "readiness_status": "Operationally Stressed",
    "readiness_status_code": "operationally_stressed",
    "scope": "readiness_state"
  },
  "source_path": "backend/tests/test_v4_team_operations_readiness_explanation_integration.py fixture pattern -> team_operations.assemble_bullpen_readiness -> explanations.readiness.serialize_readiness_explanation",
  "status": "operationally_stressed",
  "surface_name": "Team Operations readiness V4 explanation",
  "team": "Deterministic Context Fixture (FIX, fixture-context)",
  "weighting_scoring_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "raw score",
      "scoring weight",
      "weighted pressure"
    ],
    "violation_count": 0,
    "violations": []
  }
}
```

Rendered public copy:
```
The public data is not strong enough to give this team a full bullpen readiness note.
A heavy recent stretch has the workload up.
Readiness is based on public workload data, not private team information.
Readiness is not injury or medical information.
Readiness is not a performance forecast.
Manager intent and bullpen warm-up state are not available.
The user remains responsible for baseball decisions.
The stored workload data is current enough for this team note.
```

Structured fields used:

```json
{
  "availability_distribution": {
    "available": 1,
    "avoid": 0,
    "limited": 0,
    "monitor": 0,
    "total": 2,
    "unavailable": 1,
    "unknown": 0
  },
  "constraints": [
    {
      "affected_area": "workload_pressure",
      "category": "workload",
      "constraint_id": "workload_elevated",
      "count": 1,
      "evidence": [
        "elevated_count: 1"
      ],
      "message": "Elevated team-level workload pressure is present.",
      "severity": "caution"
    },
    {
      "affected_area": "availability_distribution",
      "category": "availability",
      "constraint_id": "availability_constrained",
      "count": 1,
      "evidence": [
        "avoid_or_unavailable_count: 1"
      ],
      "message": "Availability distribution contains constrained inventory.",
      "severity": "caution"
    }
  ],
  "coverage_inventory": {
    "active_pitcher_count": 2,
    "availability_covered_count": 2,
    "availability_missing_count": 0,
    "coverage_state": "covered",
    "current_workload_data_count": 2,
    "missing_workload_data_count": 0
  },
  "freshness": {
    "data_through": "2026-06-03",
    "freshness_state": "current",
    "generated_at": "2026-06-03T12:00:00Z",
    "last_successful_sync": "2026-06-03T11:30:00Z",
    "latest_fatigue_calculated_at": "2026-06-03T11:45:00Z",
    "latest_sync_status": "success",
    "latest_workload_date": "2026-06-03",
    "limitations": [],
    "missing_data_warning": null,
    "stale_warning": null
  },
  "handedness_coverage": {
    "coverage_state": "covered",
    "left_handed_count": 1,
    "limitations": [],
    "right_handed_count": 1,
    "unknown_count": 0
  },
  "readiness": {
    "basis": [
      "availability_distribution",
      "workload_pressure",
      "freshness",
      "trust_metadata"
    ],
    "status": "Operationally Stressed",
    "status_code": "operationally_stressed",
    "summary": "Team-level bullpen readiness is stressed by current workload or availability constraints."
  },
  "trust_metadata": {
    "capability": "team_operations_bullpen_readiness",
    "confidence": "high",
    "confidence_reasons": [
      "fresh_data",
      "complete_metadata"
    ],
    "data_state": "fresh",
    "explanations": [],
    "generated_at": "2026-06-03T12:00:00Z",
    "governance_state": "compliant",
    "limitations": [],
    "ranking_applied": false,
    "refusal_reasons": [],
    "scope": "team_bullpen_readiness",
    "selection_made": false,
    "source_evidence_state": "represented",
    "trust_validation_errors": []
  },
  "workload_pressure": {
    "elevated_count": 1,
    "latest_workload_date": "2026-06-03",
    "low_count": 1,
    "moderate_count": 0,
    "pressure_state": "elevated",
    "pressure_state_code": "elevated",
    "summary": "Recent workload pressure is elevated at the team level.",
    "unknown_count": 0
  }
}
```

Evidence sections:

```json
{
  "limitations": [
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "insufficient_context",
      "severity": "informational",
      "summary": "Readiness is based on public workload data, not private team information."
    },
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "insufficient_context",
      "severity": "informational",
      "summary": "Readiness is not injury or medical information."
    },
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "insufficient_context",
      "severity": "informational",
      "summary": "Readiness is not a performance forecast."
    },
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "insufficient_context",
      "severity": "informational",
      "summary": "Manager intent and bullpen warm-up state are not available."
    },
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "insufficient_context",
      "severity": "informational",
      "summary": "The user remains responsible for baseball decisions."
    }
  ],
  "primary_reasons": [
    {
      "code": "READINESS_DEGRADED_BY_LIMITATIONS",
      "label": "Readiness degraded by limitations",
      "scope": "readiness_state",
      "summary": "The public data is not strong enough to give this team a full bullpen readiness note."
    },
    {
      "code": "WORKLOAD_RECENT_USAGE_ELEVATED",
      "label": "Recent usage elevated",
      "scope": "workload_state",
      "summary": "A heavy recent stretch has the workload up."
    }
  ],
  "supporting_evidence": [
    {
      "evidence_type": "readiness_status",
      "impact": "explains_readiness_state",
      "label": "Readiness status",
      "source": "team_operations_bullpen_readiness",
      "unit": "status",
      "value": "Operationally Stressed"
    },
    {
      "evidence_type": "readiness_status_code",
      "impact": "explains_readiness_state",
      "label": "Readiness status code",
      "source": "team_operations_bullpen_readiness",
      "unit": "status_code",
      "value": "operationally_stressed"
    },
    {
      "evidence_type": "readiness_contract_state",
      "impact": "explains_output_boundary",
      "label": "Readiness contract state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "degraded"
    },
    {
      "evidence_type": "readiness_basis",
      "impact": "explains_input_scope",
      "label": "Readiness basis",
      "source": "team_operations_bullpen_readiness",
      "unit": "sources",
      "value": [
        "availability_distribution",
        "workload_pressure",
        "freshness",
        "trust_metadata"
      ]
    },
    {
      "evidence_type": "readiness_freshness_state",
      "impact": "explains_freshness_boundary",
      "label": "Freshness state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "current"
    },
    {
      "evidence_type": "readiness_trust_confidence",
      "impact": "explains_confidence_boundary",
      "label": "Trust confidence",
      "source": "team_operations_bullpen_readiness",
      "unit": "level",
      "value": "high"
    },
    {
      "evidence_type": "readiness_trust_data_state",
      "impact": "explains_trust_boundary",
      "label": "Trust data state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "fresh"
    },
    {
      "evidence_type": "workload_pressure_state",
      "impact": "explains_workload_state",
      "label": "Workload pressure state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "elevated"
    },
    {
      "evidence_type": "coverage_inventory_state",
      "impact": "explains_coverage_state",
      "label": "Coverage inventory state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "covered"
    },
    {
      "evidence_type": "handedness_coverage_state",
      "impact": "explains_coverage_state",
      "label": "Handedness coverage state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "covered"
    },
    {
      "evidence_type": "workload_pressure_low_count",
      "impact": "explains_workload_state",
      "label": "Low workload count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 1
    },
    {
      "evidence_type": "workload_pressure_moderate_count",
      "impact": "explains_workload_state",
      "label": "Moderate workload count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 0
    },
    {
      "evidence_type": "workload_pressure_elevated_count",
      "impact": "explains_workload_state",
      "label": "Elevated workload count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 1
    },
    {
      "evidence_type": "workload_pressure_unknown_count",
      "impact": "explains_workload_state",
      "label": "Unknown workload count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 0
    },
    {
      "evidence_type": "availability_distribution_available",
      "impact": "explains_availability_state",
      "label": "Available inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 1
    },
    {
      "evidence_type": "availability_distribution_monitor",
      "impact": "explains_availability_state",
      "label": "Monitor inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 0
    },
    {
      "evidence_type": "availability_distribution_limited",
      "impact": "explains_availability_state",
      "label": "Limited inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 0
    },
    {
      "evidence_type": "availability_distribution_avoid",
      "impact": "explains_availability_state",
      "label": "Avoid inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 0
    },
    {
      "evidence_type": "availability_distribution_unavailable",
      "impact": "explains_availability_state",
      "label": "Unavailable inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 1
    },
    {
      "evidence_type": "availability_distribution_unknown",
      "impact": "explains_availability_state",
      "label": "Unknown availability count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 0
    },
    {
      "evidence_type": "availability_distribution_total",
      "impact": "explains_availability_state",
      "label": "Total availability inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 2
    },
    {
      "evidence_type": "coverage_inventory_active_pitcher_count",
      "impact": "explains_coverage_state",
      "label": "Active pitcher count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 2
    },
    {
      "evidence_type": "coverage_inventory_current_workload_data_count",
      "impact": "explains_coverage_state",
      "label": "Current workload data count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 2
    },
    {
      "evidence_type": "coverage_inventory_missing_workload_data_count",
      "impact": "explains_coverage_state",
      "label": "Missing workload data count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 0
    },
    {
      "evidence_type": "coverage_inventory_availability_covered_count",
      "impact": "explains_coverage_state",
      "label": "Availability covered count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 2
    },
    {
      "evidence_type": "coverage_inventory_availability_missing_count",
      "impact": "explains_coverage_state",
      "label": "Availability missing count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 0
    },
    {
      "evidence_type": "handedness_coverage_left_handed_count",
      "impact": "explains_coverage_state",
      "label": "Left handed count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 1
    },
    {
      "evidence_type": "handedness_coverage_right_handed_count",
      "impact": "explains_coverage_state",
      "label": "Right handed count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 1
    },
    {
      "evidence_type": "handedness_coverage_unknown_count",
      "impact": "explains_coverage_state",
      "label": "Unknown handedness count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 0
    },
    {
      "evidence_type": "readiness_constraint_workload_elevated",
      "impact": "explains_readiness_limitation",
      "label": "Readiness constraint workload_elevated",
      "source": "team_operations_bullpen_readiness",
      "unit": "constraint",
      "value": {
        "affected_area": "workload_pressure",
        "category": "workload",
        "count": 1,
        "evidence": [
          "elevated_count: 1"
        ],
        "message": "Elevated team-level workload pressure is present.",
        "severity": "caution"
      }
    },
    {
      "evidence_type": "readiness_constraint_availability_constrained",
      "impact": "explains_readiness_limitation",
      "label": "Readiness constraint availability_constrained",
      "source": "team_operations_bullpen_readiness",
      "unit": "constraint",
      "value": {
        "affected_area": "availability_distribution",
        "category": "availability",
        "count": 1,
        "evidence": [
          "avoid_or_unavailable_count: 1"
        ],
        "message": "Availability distribution contains constrained inventory.",
        "severity": "caution"
      }
    }
  ]
}
```

### Example 43: Team Operations readiness V4 explanation

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "capitalization_sentence_scan": {
    "patterns": {
      "lowercase_sentence_start": "(?<=[.!?])\\s+([a-z])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "circular_meta_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "explanation confidence mirrors",
      "confidence mirrors",
      "visibility reflects existing availability confidence",
      "governed availability evidence",
      "state reflects",
      "explained state",
      "trust metadata",
      "readiness explanation confidence"
    ],
    "violation_count": 0,
    "violations": []
  },
  "disclaimer_repetition_scan": {
    "disclaimer": "This is a data-limited note, not a statement about injury status or manager intent.",
    "per_card_limit": 1,
    "scope": "Team bullpen shape rendered public copy",
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "example_source": "deterministic fixture example",
  "fallback_status": "rendered",
  "pitcher": null,
  "raw_count_formula_scan": {
    "patterns": {
      "jargon_coupled_raw_count": "(?<![\\w-])\\d+\\s+of\\s+\\d+\\s+(?:trust|bridge|coverage|depth)\\s+arms?\\b",
      "parenthetical_raw_basis": "\\(\\s*\\d+\\s+of\\s+\\d+\\s*\\)",
      "parenthetical_unknown_formula": "\\([^)]*\\bunknown\\b[^)]*\\)",
      "raw_empty_arithmetic": "(?<![\\w-])\\d+\\s+of\\s+\\d+(?![\\w-])"
    },
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "length option",
      "length options",
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "classified available",
      "0 of 0",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "trusted-group",
      "top trust bucket",
      "coverage margin",
      "resource health",
      "active capacity",
      "trust structure",
      "trust hierarchy",
      "trust metadata",
      "explained state",
      "availability read",
      "bullpen planning read",
      "explanation confidence mirrors",
      "confidence mirrors",
      "governed availability evidence",
      "state reflects",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "role_or_classification": {
    "readiness_status": "Refused",
    "readiness_status_code": "refused",
    "scope": "readiness_state"
  },
  "source_path": "backend/tests/test_v4_team_operations_readiness_explanation_integration.py fixture pattern -> team_operations.assemble_bullpen_readiness -> explanations.readiness.serialize_readiness_explanation",
  "status": "refused",
  "surface_name": "Team Operations readiness V4 explanation",
  "team": "Deterministic Context Fixture (FIX, fixture-context)",
  "weighting_scoring_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "pass",
    "terms": [
      "interpretation weighs",
      "weighs clean",
      "weighs trust",
      "weighs bridge",
      "late-inning pressure weighs",
      "trust arms above",
      "depth arms above",
      "raw score",
      "scoring weight",
      "weighted pressure"
    ],
    "violation_count": 0,
    "violations": []
  }
}
```

Rendered public copy:
```
The public data is not strong enough to give this team a full bullpen readiness note.
The public data is not strong enough for a fuller explanation.
Readiness output is withheld until required metadata is available.
The safest read is limited until the public workload picture is clearer.
The stored workload data is current enough for this team note.
The public data is not strong enough to give this team a readiness note.
The safest note stays limited until the public workload picture is clearer.
```

Structured fields used:

```json
{
  "availability_distribution": {},
  "constraints": [
    {
      "affected_area": "readiness",
      "category": "trust",
      "constraint_id": "trust_metadata_missing",
      "count": 1,
      "evidence": [
        "trust_metadata is missing."
      ],
      "message": "Readiness output is refused because required trust metadata is missing.",
      "severity": "blocking"
    }
  ],
  "coverage_inventory": {},
  "freshness": {
    "data_through": "2026-06-03",
    "freshness_state": "current",
    "generated_at": "2026-06-03T12:00:00Z",
    "last_successful_sync": "2026-06-03T11:30:00Z",
    "latest_fatigue_calculated_at": "2026-06-03T11:45:00Z",
    "latest_sync_status": "success",
    "latest_workload_date": "2026-06-03",
    "limitations": [],
    "missing_data_warning": null,
    "stale_warning": null
  },
  "handedness_coverage": {},
  "readiness": {
    "basis": [
      "trust_metadata",
      "freshness",
      "fail_closed"
    ],
    "status": "Refused",
    "status_code": "refused",
    "summary": "Readiness output is refused because required trust metadata is missing."
  },
  "trust_metadata": {
    "capability": "team_operations_bullpen_readiness",
    "confidence": "unknown",
    "confidence_reasons": [
      "trust_metadata_missing"
    ],
    "data_state": "unknown",
    "explanations": [
      "readiness_refused_trust_metadata_missing"
    ],
    "generated_at": "2026-06-03T12:00:00Z",
    "governance_state": "refused",
    "limitations": [
      "readiness_refused"
    ],
    "ranking_applied": false,
    "refusal_reasons": [
      "trust_metadata_missing"
    ],
    "scope": "team_bullpen_readiness",
    "selection_made": false,
    "source_evidence_state": "missing",
    "trust_validation_errors": [
      "trust_metadata is missing."
    ]
  },
  "workload_pressure": {}
}
```

Evidence sections:

```json
{
  "limitations": [
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "missing_data",
      "severity": "blocking",
      "summary": "Readiness output is withheld until required metadata is available."
    },
    {
      "affected_scopes": [
        "readiness_state"
      ],
      "limitation_type": "limited_confidence",
      "severity": "limits_confidence",
      "summary": "The safest read is limited until the public workload picture is clearer."
    }
  ],
  "primary_reasons": [
    {
      "code": "READINESS_DEGRADED_BY_LIMITATIONS",
      "label": "Readiness degraded by limitations",
      "scope": "readiness_state",
      "summary": "The public data is not strong enough to give this team a full bullpen readiness note."
    },
    {
      "code": "TRUST_LIMITED",
      "label": "Trust limited",
      "scope": "trust_state",
      "summary": "The public data is not strong enough for a fuller explanation."
    }
  ],
  "supporting_evidence": [
    {
      "evidence_type": "readiness_status",
      "impact": "explains_readiness_state",
      "label": "Readiness status",
      "source": "team_operations_bullpen_readiness",
      "unit": "status",
      "value": "Refused"
    },
    {
      "evidence_type": "readiness_status_code",
      "impact": "explains_readiness_state",
      "label": "Readiness status code",
      "source": "team_operations_bullpen_readiness",
      "unit": "status_code",
      "value": "refused"
    },
    {
      "evidence_type": "readiness_contract_state",
      "impact": "explains_output_boundary",
      "label": "Readiness contract state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "refused"
    },
    {
      "evidence_type": "readiness_basis",
      "impact": "explains_input_scope",
      "label": "Readiness basis",
      "source": "team_operations_bullpen_readiness",
      "unit": "sources",
      "value": [
        "trust_metadata",
        "freshness",
        "fail_closed"
      ]
    },
    {
      "evidence_type": "readiness_freshness_state",
      "impact": "explains_freshness_boundary",
      "label": "Freshness state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "current"
    },
    {
      "evidence_type": "readiness_trust_confidence",
      "impact": "explains_confidence_boundary",
      "label": "Trust confidence",
      "source": "team_operations_bullpen_readiness",
      "unit": "level",
      "value": "unknown"
    },
    {
      "evidence_type": "readiness_trust_data_state",
      "impact": "explains_trust_boundary",
      "label": "Trust data state",
      "source": "team_operations_bullpen_readiness",
      "unit": "state",
      "value": "unknown"
    },
    {
      "evidence_type": "readiness_constraint_trust_metadata_missing",
      "impact": "explains_readiness_limitation",
      "label": "Readiness constraint trust_metadata_missing",
      "source": "team_operations_bullpen_readiness",
      "unit": "constraint",
      "value": {
        "affected_area": "readiness",
        "category": "trust",
        "count": 1,
        "evidence": [
          "trust_metadata is missing."
        ],
        "message": "Readiness output is refused because required trust metadata is missing.",
        "severity": "blocking"
      }
    }
  ]
}
```
