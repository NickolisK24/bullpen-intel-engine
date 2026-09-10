# Context Explanation Editorial Review Corpus - E2D-1 Context Explanation Corpus

Read-only export of current Pitcher Context and Team Context explanation copy before E2 Editorial Voice migration.

## Export Metadata

```json
{
  "artifact": "artifacts/context_explanation_editorial_review_E2D1.md",
  "data_notes": [
    "Current stored team board path returned zero eligible visible pitcher cards for every reviewed team; board card/group examples are documented as real fallback/no-card rows."
  ],
  "example_count": 21,
  "generated_at": "2026-06-30T01:57:55.982471",
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
  "review_label": "E2D-1 Context Explanation Corpus",
  "source_mode": "current stored DB data only; exporter starts no sync",
  "team_ids_reviewed": [
    108,
    112,
    113,
    116,
    119,
    121,
    133,
    138,
    143,
    147
  ]
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
  "examples_exported": 21,
  "missing_categories": {
    "board_card_groups_with_no_current_cards": [
      "Available",
      "Monitor",
      "Limited",
      "Avoid",
      "Unavailable"
    ],
    "pitcher_availability_statuses": [
      "Available",
      "Avoid"
    ],
    "pitcher_context_modal_statuses": [
      "Available",
      "Avoid"
    ],
    "role_label_examples": "Current board records produced no eligible visible pitcher cards, so Trust Arm, Bridge Arm, Coverage Arm, and Depth Arm role examples were not available from stored board data.",
    "team_readiness_statuses": [
      "operationally_stable",
      "operationally_constrained",
      "operationally_stressed",
      "refused"
    ],
    "team_shape_non_limited_examples": "Current board rows produced Limited Read team-shape examples only."
  },
  "pitcher_availability_statuses_found": [
    "Limited",
    "Monitor",
    "Unavailable"
  ],
  "pitcher_context_statuses_found": [
    "Limited",
    "Monitor",
    "Unavailable"
  ],
  "team_readiness_states_found": [
    "data_limited"
  ]
}
```

## Editorial Banned-Language Scan

Status: warn - 9 banned language violation(s) found.

```json
{
  "scope": "rendered public context explanation copy only",
  "status": "warn",
  "violation_count": 9,
  "violations": [
    {
      "category": "editorial_contract_denied_phrase",
      "example_index": 12,
      "match": "clean options",
      "pitcher": null,
      "start": 213,
      "surface_name": "Team bullpen shape explanations",
      "team": "Los Angeles Angels (LAA, 108)",
      "term": "clean option"
    },
    {
      "category": "editorial_contract_denied_phrase",
      "example_index": 12,
      "match": "clean options",
      "pitcher": null,
      "start": 213,
      "surface_name": "Team bullpen shape explanations",
      "team": "Los Angeles Angels (LAA, 108)",
      "term": "clean options"
    },
    {
      "category": "editorial_contract_denied_phrase",
      "example_index": 12,
      "match": "0 trusted",
      "pitcher": null,
      "start": 604,
      "surface_name": "Team bullpen shape explanations",
      "team": "Los Angeles Angels (LAA, 108)",
      "term": "0 trusted"
    },
    {
      "category": "editorial_contract_denied_phrase",
      "example_index": 14,
      "match": "clean options",
      "pitcher": null,
      "start": 213,
      "surface_name": "Team bullpen shape explanations",
      "team": "Chicago Cubs (CHC, 112)",
      "term": "clean option"
    },
    {
      "category": "editorial_contract_denied_phrase",
      "example_index": 14,
      "match": "clean options",
      "pitcher": null,
      "start": 213,
      "surface_name": "Team bullpen shape explanations",
      "team": "Chicago Cubs (CHC, 112)",
      "term": "clean options"
    },
    {
      "category": "editorial_contract_denied_phrase",
      "example_index": 14,
      "match": "0 trusted",
      "pitcher": null,
      "start": 604,
      "surface_name": "Team bullpen shape explanations",
      "team": "Chicago Cubs (CHC, 112)",
      "term": "0 trusted"
    },
    {
      "category": "editorial_contract_denied_phrase",
      "example_index": 16,
      "match": "clean options",
      "pitcher": null,
      "start": 213,
      "surface_name": "Team bullpen shape explanations",
      "team": "Cincinnati Reds (CIN, 113)",
      "term": "clean option"
    },
    {
      "category": "editorial_contract_denied_phrase",
      "example_index": 16,
      "match": "clean options",
      "pitcher": null,
      "start": 213,
      "surface_name": "Team bullpen shape explanations",
      "team": "Cincinnati Reds (CIN, 113)",
      "term": "clean options"
    },
    {
      "category": "editorial_contract_denied_phrase",
      "example_index": 16,
      "match": "0 trusted",
      "pitcher": null,
      "start": 604,
      "surface_name": "Team bullpen shape explanations",
      "team": "Cincinnati Reds (CIN, 113)",
      "term": "0 trusted"
    }
  ]
}
```

## Retired Phrase Scan

Status: warn - 9 retired phrase violation(s) found.

```json
{
  "scope": "rendered public context explanation copy only",
  "status": "warn",
  "terms": [
    "clean option",
    "clean options",
    "clean arms",
    "short list of clean arms",
    "clean way",
    "clean ways",
    "usable group",
    "usable depth",
    "in good shape",
    "availability distributions",
    "practical path",
    "practical paths",
    "0 trusted"
  ],
  "violation_count": 9,
  "violations": [
    {
      "category": "editorial_contract_denied_phrase",
      "example_index": 12,
      "match": "clean options",
      "pitcher": null,
      "start": 213,
      "surface_name": "Team bullpen shape explanations",
      "team": "Los Angeles Angels (LAA, 108)",
      "term": "clean option"
    },
    {
      "category": "editorial_contract_denied_phrase",
      "example_index": 12,
      "match": "clean options",
      "pitcher": null,
      "start": 213,
      "surface_name": "Team bullpen shape explanations",
      "team": "Los Angeles Angels (LAA, 108)",
      "term": "clean options"
    },
    {
      "category": "editorial_contract_denied_phrase",
      "example_index": 12,
      "match": "0 trusted",
      "pitcher": null,
      "start": 604,
      "surface_name": "Team bullpen shape explanations",
      "team": "Los Angeles Angels (LAA, 108)",
      "term": "0 trusted"
    },
    {
      "category": "editorial_contract_denied_phrase",
      "example_index": 14,
      "match": "clean options",
      "pitcher": null,
      "start": 213,
      "surface_name": "Team bullpen shape explanations",
      "team": "Chicago Cubs (CHC, 112)",
      "term": "clean option"
    },
    {
      "category": "editorial_contract_denied_phrase",
      "example_index": 14,
      "match": "clean options",
      "pitcher": null,
      "start": 213,
      "surface_name": "Team bullpen shape explanations",
      "team": "Chicago Cubs (CHC, 112)",
      "term": "clean options"
    },
    {
      "category": "editorial_contract_denied_phrase",
      "example_index": 14,
      "match": "0 trusted",
      "pitcher": null,
      "start": 604,
      "surface_name": "Team bullpen shape explanations",
      "team": "Chicago Cubs (CHC, 112)",
      "term": "0 trusted"
    },
    {
      "category": "editorial_contract_denied_phrase",
      "example_index": 16,
      "match": "clean options",
      "pitcher": null,
      "start": 213,
      "surface_name": "Team bullpen shape explanations",
      "team": "Cincinnati Reds (CIN, 113)",
      "term": "clean option"
    },
    {
      "category": "editorial_contract_denied_phrase",
      "example_index": 16,
      "match": "clean options",
      "pitcher": null,
      "start": 213,
      "surface_name": "Team bullpen shape explanations",
      "team": "Cincinnati Reds (CIN, 113)",
      "term": "clean options"
    },
    {
      "category": "editorial_contract_denied_phrase",
      "example_index": 16,
      "match": "0 trusted",
      "pitcher": null,
      "start": 604,
      "surface_name": "Team bullpen shape explanations",
      "team": "Cincinnati Reds (CIN, 113)",
      "term": "0 trusted"
    }
  ]
}
```

## Fallbacks Found

```json
{
  "fallback_counts": {
    "data_limited": 5,
    "data_stale": 1,
    "freshness_stale": 1,
    "limited_read_shape": 3,
    "limited_role_context": 4,
    "no_visible_pitcher_cards": 3,
    "rendered": 4
  },
  "fallback_rows": [
    {
      "fallback_status": "freshness_stale",
      "pitcher": "Alek Manoah",
      "status": "Monitor",
      "surface_name": "Pitcher V4 availability explanation",
      "team": "Los Angeles Angels (LAA, 108)"
    },
    {
      "fallback_status": "data_stale",
      "pitcher": "Alek Manoah",
      "status": "Monitor",
      "surface_name": "Pitcher Context modal/detail route",
      "team": "Los Angeles Angels (LAA, 108)"
    },
    {
      "fallback_status": "limited_role_context",
      "pitcher": "Alek Manoah",
      "status": "Monitor",
      "surface_name": "Pitcher public role/read labels",
      "team": "Los Angeles Angels (LAA, 108)"
    },
    {
      "fallback_status": "limited_role_context",
      "pitcher": "Ryan Zeferjahn",
      "status": "Monitor",
      "surface_name": "Pitcher public role/read labels",
      "team": "Los Angeles Angels (LAA, 108)"
    },
    {
      "fallback_status": "limited_role_context",
      "pitcher": "Brady Singer",
      "status": "Unavailable",
      "surface_name": "Pitcher public role/read labels",
      "team": "Cincinnati Reds (CIN, 113)"
    },
    {
      "fallback_status": "limited_role_context",
      "pitcher": "Pierce Johnson",
      "status": "Limited",
      "surface_name": "Pitcher public role/read labels",
      "team": "Cincinnati Reds (CIN, 113)"
    },
    {
      "fallback_status": "no_visible_pitcher_cards",
      "pitcher": null,
      "status": "no_data",
      "surface_name": "Team bullpen board context",
      "team": "Los Angeles Angels (LAA, 108)"
    },
    {
      "fallback_status": "limited_read_shape",
      "pitcher": null,
      "status": "team_shape",
      "surface_name": "Team bullpen shape explanations",
      "team": "Los Angeles Angels (LAA, 108)"
    },
    {
      "fallback_status": "no_visible_pitcher_cards",
      "pitcher": null,
      "status": "no_data",
      "surface_name": "Team bullpen board context",
      "team": "Chicago Cubs (CHC, 112)"
    },
    {
      "fallback_status": "limited_read_shape",
      "pitcher": null,
      "status": "team_shape",
      "surface_name": "Team bullpen shape explanations",
      "team": "Chicago Cubs (CHC, 112)"
    },
    {
      "fallback_status": "no_visible_pitcher_cards",
      "pitcher": null,
      "status": "no_data",
      "surface_name": "Team bullpen board context",
      "team": "Cincinnati Reds (CIN, 113)"
    },
    {
      "fallback_status": "limited_read_shape",
      "pitcher": null,
      "status": "team_shape",
      "surface_name": "Team bullpen shape explanations",
      "team": "Cincinnati Reds (CIN, 113)"
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
      "status": "unknown",
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
    }
  ]
}
```

## Surface Summary

```json
{
  "examples_by_surface": {
    "Pitcher Context modal/detail route": 3,
    "Pitcher V4 availability explanation": 3,
    "Pitcher public role/read labels": 4,
    "Team Operations readiness V4 explanation": 5,
    "Team bullpen board context": 3,
    "Team bullpen shape explanations": 3
  },
  "statuses_by_surface": {
    "Pitcher Context modal/detail route": {
      "Limited": 1,
      "Monitor": 1,
      "Unavailable": 1
    },
    "Pitcher V4 availability explanation": {
      "Limited": 1,
      "Monitor": 1,
      "Unavailable": 1
    },
    "Pitcher public role/read labels": {
      "Limited": 1,
      "Monitor": 2,
      "Unavailable": 1
    },
    "Team Operations readiness V4 explanation": {
      "current": 1,
      "data_limited": 1,
      "limited": 1,
      "unknown": 1,
      "workload:partial;handedness:covered": 1
    },
    "Team bullpen board context": {
      "no_data": 3
    },
    "Team bullpen shape explanations": {
      "team_shape": 3
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
  "fallback_status": "freshness_stale",
  "pitcher": "Alek Manoah",
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
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
  "team": "Los Angeles Angels (LAA, 108)"
}
```

Rendered public copy:
```
This availability state reflects existing workload, freshness, confidence, and limitation evidence.
Governed availability evidence supports Monitor state.
Recent public workload evidence contributes to elevated workload.
Source freshness is stale for the explained state.
Trust metadata limits confidence in the explanation.
No injury data available
No team-reported availability data available
Recent usage information is incomplete, so workload data must not be treated as current availability
Workload evidence is stale for this availability state.
Availability explanation confidence is limited by current evidence.
Availability explanation is limited by stale workload evidence.
Visibility reflects existing availability confidence and data-state detail.
Explanation confidence mirrors the existing availability confidence value.
```

Structured fields used:

```json
{
  "confidence": {
    "level": "low",
    "summary": "Explanation confidence mirrors the existing availability confidence value."
  },
  "freshness": {
    "data_through": "2026-03-13",
    "freshness_failure": "stale_workload_data",
    "last_sync_at": null,
    "source_updated_at": "2026-06-29",
    "status": "stale",
    "summary": "Availability explanation is limited by stale workload evidence."
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
  "subject_id": "92",
  "subject_type": "pitcher",
  "trust": {
    "certification_status": "complete",
    "contract": "availability_engine_v1",
    "source": "availability_engine_v1",
    "status": "limited",
    "summary": "Visibility reflects existing availability confidence and data-state detail.",
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
      "summary": "Workload evidence is stale for this availability state."
    },
    {
      "affected_scopes": [
        "availability_state"
      ],
      "limitation_type": "limited_confidence",
      "severity": "limits_confidence",
      "summary": "Availability explanation confidence is limited by current evidence."
    }
  ],
  "primary_reasons": [
    {
      "code": "AVAILABILITY_MONITOR_THRESHOLD_MET",
      "label": "Monitor threshold met",
      "scope": "availability_state",
      "summary": "Governed availability evidence supports Monitor state."
    },
    {
      "code": "WORKLOAD_RECENT_USAGE_ELEVATED",
      "label": "Recent usage elevated",
      "scope": "workload_state",
      "summary": "Recent public workload evidence contributes to elevated workload."
    },
    {
      "code": "FRESHNESS_STALE_SOURCE",
      "label": "Source freshness stale",
      "scope": "freshness_state",
      "summary": "Source freshness is stale for the explained state."
    },
    {
      "code": "TRUST_LIMITED",
      "label": "Trust limited",
      "scope": "trust_state",
      "summary": "Trust metadata limits confidence in the explanation."
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
      "value": 68.1
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
      "value": 108
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
  "fallback_status": "data_stale",
  "pitcher": "Alek Manoah",
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "role_or_classification": {
    "confidence": "low",
    "data_state": "stale",
    "roster_status": "Roster Unknown"
  },
  "source_path": "api.bullpen.get_pitcher_fatigue",
  "status": "Monitor",
  "surface_name": "Pitcher Context modal/detail route",
  "team": "Los Angeles Angels (LAA, 108)"
}
```

Rendered public copy:
```
Monitor
Latest workload data is outside the 14-day freshness window
No injury data available
No team-reported availability data available
Recent usage information is incomplete, so workload data must not be treated as current availability
Roster status unavailable; bullpen eligibility is based on stored usage and position data.
Roster Unknown
Current baseball data through 2026-06-28.
```

Structured fields used:

```json
{
  "availability": {
    "availability_status": "Monitor",
    "confidence": "low",
    "data_state": "stale",
    "inputs": {
      "appearances_last_3_days": 0,
      "appearances_last_5_days": 0,
      "back_to_back": false,
      "days_rest": 108,
      "fatigue_risk_level": "HIGH",
      "fatigue_score": 68.1,
      "four_in_five": false,
      "freshness_state": "stale",
      "latest_game_date": "2026-03-13",
      "pitches_last_3_days": 0,
      "pitches_last_5_days": 0,
      "pitches_yesterday": 0,
      "reference_date": "2026-06-29",
      "three_in_four": false
    },
    "limitations": [
      "No injury data available",
      "No team-reported availability data available",
      "Recent usage information is incomplete, so workload data must not be treated as current availability",
      "Roster status unavailable; bullpen eligibility is based on stored usage and position data."
    ],
    "reasons": [
      "Latest workload data is outside the 14-day freshness window"
    ]
  },
  "freshness": {
    "data_age_days": 1,
    "data_through": "2026-06-28",
    "freshness_state": "current",
    "label": "Current baseball data through 2026-06-28.",
    "limitations": []
  },
  "roster_status": {
    "confidence": "low",
    "label": "Roster Unknown",
    "limitations": [
      "Roster status unavailable; bullpen eligibility is based on stored usage and position data."
    ],
    "source": "unavailable",
    "status": "UNKNOWN"
  },
  "workload_signal": {
    "availability_status": "Monitor",
    "confidence": "low",
    "data_state": "stale",
    "inputs": {
      "appearances_last_3_days": 0,
      "appearances_last_5_days": 0,
      "back_to_back": false,
      "days_rest": 108,
      "fatigue_risk_level": "HIGH",
      "fatigue_score": 68.1,
      "four_in_five": false,
      "freshness_state": "stale",
      "latest_game_date": "2026-03-13",
      "pitches_last_3_days": 0,
      "pitches_last_5_days": 0,
      "pitches_yesterday": 0,
      "reference_date": "2026-06-29",
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
  "fatigue_trend_points": 6,
  "last_workload_appearance": {
    "game_date": "2026-03-13",
    "pitches": 13
  },
  "recent_logs_reviewed": 5
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
  "fallback_status": "limited_role_context",
  "pitcher": "Alek Manoah",
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
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
  "source_path": "services.pitcher_public_labels.build_pitcher_labels",
  "status": "Monitor",
  "surface_name": "Pitcher public role/read labels",
  "team": "Los Angeles Angels (LAA, 108)"
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
  "availability_data_state": "stale",
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
      "source": "backend:role_key:missing"
    }
  },
  "role_input": null,
  "roster_status": {
    "confidence": "low",
    "current_assignment_unresolved": false,
    "evidence": [],
    "is_active_mlb": null,
    "is_authoritative": false,
    "is_inactive_context": false,
    "label": "Roster Unknown",
    "limitations": [
      "Roster status unavailable; bullpen eligibility is based on stored usage and position data."
    ],
    "raw_status": null,
    "raw_status_code": null,
    "raw_status_description": null,
    "source": "unavailable",
    "status": "UNKNOWN",
    "updated_at": null
  }
}
```

Evidence sections:

```json
{}
```

### Example 4: Pitcher public role/read labels

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "fallback_status": "limited_role_context",
  "pitcher": "Ryan Zeferjahn",
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
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
  "team": "Los Angeles Angels (LAA, 108)"
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
    "confidence": "low",
    "current_assignment_unresolved": false,
    "evidence": [],
    "is_active_mlb": null,
    "is_authoritative": false,
    "is_inactive_context": false,
    "label": "Roster Unknown",
    "limitations": [
      "Roster status unavailable; bullpen eligibility is based on stored usage and position data."
    ],
    "raw_status": null,
    "raw_status_code": null,
    "raw_status_description": null,
    "source": "unavailable",
    "status": "UNKNOWN",
    "updated_at": null
  }
}
```

Evidence sections:

```json
{}
```

### Example 5: Pitcher V4 availability explanation

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "fallback_status": "rendered",
  "pitcher": "Brady Singer",
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
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
  "team": "Cincinnati Reds (CIN, 113)"
}
```

Rendered public copy:
```
This availability state reflects existing workload, freshness, confidence, and limitation evidence.
Recent public workload evidence contributes to elevated workload.
No injury data available
No team-reported availability data available
Availability explanation uses current workload evidence.
Visibility reflects existing availability confidence and data-state detail.
Explanation confidence mirrors the existing availability confidence value.
```

Structured fields used:

```json
{
  "confidence": {
    "level": "high",
    "summary": "Explanation confidence mirrors the existing availability confidence value."
  },
  "freshness": {
    "data_through": "2026-06-28",
    "freshness_failure": null,
    "last_sync_at": null,
    "source_updated_at": "2026-06-29",
    "status": "current",
    "summary": "Availability explanation uses current workload evidence."
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
  "subject_id": "21",
  "subject_type": "pitcher",
  "trust": {
    "certification_status": "complete",
    "contract": "availability_engine_v1",
    "source": "availability_engine_v1",
    "status": "trusted",
    "summary": "Visibility reflects existing availability confidence and data-state detail.",
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
      "summary": "Recent public workload evidence contributes to elevated workload."
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
      "value": 57.5
    },
    {
      "evidence_type": "availability_pitches_yesterday",
      "impact": "explains_availability_state",
      "label": "Pitches yesterday",
      "source": "availability_engine_v1",
      "unit": "pitches",
      "value": 98
    },
    {
      "evidence_type": "availability_pitches_last_3_days",
      "impact": "explains_availability_state",
      "label": "Pitches in 3 days",
      "source": "availability_engine_v1",
      "unit": "pitches",
      "value": 98
    },
    {
      "evidence_type": "availability_pitches_last_5_days",
      "impact": "explains_availability_state",
      "label": "Pitches in 5 days",
      "source": "availability_engine_v1",
      "unit": "pitches",
      "value": 98
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

### Example 6: Pitcher Context modal/detail route

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "fallback_status": "rendered",
  "pitcher": "Brady Singer",
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
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
    "roster_status": "Roster Unknown"
  },
  "source_path": "api.bullpen.get_pitcher_fatigue",
  "status": "Unavailable",
  "surface_name": "Pitcher Context modal/detail route",
  "team": "Cincinnati Reds (CIN, 113)"
}
```

Rendered public copy:
```
Unavailable
98 pitches yesterday
98 pitches in 3 days
98 pitches in 5 days
Only 1 day of rest
Recent workload is high enough to narrow normal availability
No injury data available
No team-reported availability data available
Roster status unavailable; bullpen eligibility is based on stored usage and position data.
Roster Unknown
Current baseball data through 2026-06-28.
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
      "fatigue_score": 57.5,
      "four_in_five": false,
      "freshness_state": "fresh",
      "latest_game_date": "2026-06-28",
      "pitches_last_3_days": 98,
      "pitches_last_5_days": 98,
      "pitches_yesterday": 98,
      "reference_date": "2026-06-29",
      "three_in_four": false
    },
    "limitations": [
      "No injury data available",
      "No team-reported availability data available",
      "Roster status unavailable; bullpen eligibility is based on stored usage and position data."
    ],
    "reasons": [
      "98 pitches yesterday",
      "98 pitches in 3 days",
      "98 pitches in 5 days",
      "Only 1 day of rest",
      "Recent workload is high enough to narrow normal availability"
    ]
  },
  "freshness": {
    "data_age_days": 1,
    "data_through": "2026-06-28",
    "freshness_state": "current",
    "label": "Current baseball data through 2026-06-28.",
    "limitations": []
  },
  "roster_status": {
    "confidence": "low",
    "label": "Roster Unknown",
    "limitations": [
      "Roster status unavailable; bullpen eligibility is based on stored usage and position data."
    ],
    "source": "unavailable",
    "status": "UNKNOWN"
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
      "fatigue_score": 57.5,
      "four_in_five": false,
      "freshness_state": "fresh",
      "latest_game_date": "2026-06-28",
      "pitches_last_3_days": 98,
      "pitches_last_5_days": 98,
      "pitches_yesterday": 98,
      "reference_date": "2026-06-29",
      "three_in_four": false
    },
    "limitations": [
      "No injury data available",
      "No team-reported availability data available"
    ],
    "reasons": [
      "98 pitches yesterday",
      "98 pitches in 3 days",
      "98 pitches in 5 days",
      "Only 1 day of rest",
      "Recent workload is high enough to narrow normal availability"
    ]
  }
}
```

Evidence sections:

```json
{
  "fatigue_trend_points": 1,
  "last_workload_appearance": {
    "game_date": "2026-06-28",
    "pitches": 98
  },
  "recent_logs_reviewed": 1
}
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
  "fallback_status": "limited_role_context",
  "pitcher": "Brady Singer",
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
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
  "team": "Cincinnati Reds (CIN, 113)"
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
      "source": "backend:role_key:missing"
    }
  },
  "role_input": null,
  "roster_status": {
    "confidence": "low",
    "current_assignment_unresolved": false,
    "evidence": [],
    "is_active_mlb": null,
    "is_authoritative": false,
    "is_inactive_context": false,
    "label": "Roster Unknown",
    "limitations": [
      "Roster status unavailable; bullpen eligibility is based on stored usage and position data."
    ],
    "raw_status": null,
    "raw_status_code": null,
    "raw_status_description": null,
    "source": "unavailable",
    "status": "UNKNOWN",
    "updated_at": null
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
  "fallback_status": "rendered",
  "pitcher": "Pierce Johnson",
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
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
  "team": "Cincinnati Reds (CIN, 113)"
}
```

Rendered public copy:
```
This availability state reflects existing workload, freshness, confidence, and limitation evidence.
Recent public workload evidence contributes to elevated workload.
No injury data available
No team-reported availability data available
Availability explanation uses current workload evidence.
Visibility reflects existing availability confidence and data-state detail.
Explanation confidence mirrors the existing availability confidence value.
```

Structured fields used:

```json
{
  "confidence": {
    "level": "high",
    "summary": "Explanation confidence mirrors the existing availability confidence value."
  },
  "freshness": {
    "data_through": "2026-06-28",
    "freshness_failure": null,
    "last_sync_at": null,
    "source_updated_at": "2026-06-29",
    "status": "current",
    "summary": "Availability explanation uses current workload evidence."
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
  "subject_id": "33",
  "subject_type": "pitcher",
  "trust": {
    "certification_status": "complete",
    "contract": "availability_engine_v1",
    "source": "availability_engine_v1",
    "status": "trusted",
    "summary": "Visibility reflects existing availability confidence and data-state detail.",
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
      "summary": "Recent public workload evidence contributes to elevated workload."
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
      "value": 32.5
    },
    {
      "evidence_type": "availability_pitches_yesterday",
      "impact": "explains_availability_state",
      "label": "Pitches yesterday",
      "source": "availability_engine_v1",
      "unit": "pitches",
      "value": 27
    },
    {
      "evidence_type": "availability_pitches_last_3_days",
      "impact": "explains_availability_state",
      "label": "Pitches in 3 days",
      "source": "availability_engine_v1",
      "unit": "pitches",
      "value": 27
    },
    {
      "evidence_type": "availability_pitches_last_5_days",
      "impact": "explains_availability_state",
      "label": "Pitches in 5 days",
      "source": "availability_engine_v1",
      "unit": "pitches",
      "value": 27
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

### Example 9: Pitcher Context modal/detail route

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "fallback_status": "rendered",
  "pitcher": "Pierce Johnson",
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
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
    "roster_status": "Roster Unknown"
  },
  "source_path": "api.bullpen.get_pitcher_fatigue",
  "status": "Limited",
  "surface_name": "Pitcher Context modal/detail route",
  "team": "Cincinnati Reds (CIN, 113)"
}
```

Rendered public copy:
```
Limited
27 pitches yesterday
Only 1 day of rest
No injury data available
No team-reported availability data available
Roster status unavailable; bullpen eligibility is based on stored usage and position data.
Roster Unknown
Current baseball data through 2026-06-28.
```

Structured fields used:

```json
{
  "availability": {
    "availability_status": "Limited",
    "confidence": "high",
    "data_state": "fresh",
    "inputs": {
      "appearances_last_3_days": 1,
      "appearances_last_5_days": 1,
      "back_to_back": false,
      "days_rest": 1,
      "fatigue_risk_level": "MODERATE",
      "fatigue_score": 32.5,
      "four_in_five": false,
      "freshness_state": "fresh",
      "latest_game_date": "2026-06-28",
      "pitches_last_3_days": 27,
      "pitches_last_5_days": 27,
      "pitches_yesterday": 27,
      "reference_date": "2026-06-29",
      "three_in_four": false
    },
    "limitations": [
      "No injury data available",
      "No team-reported availability data available",
      "Roster status unavailable; bullpen eligibility is based on stored usage and position data."
    ],
    "reasons": [
      "27 pitches yesterday",
      "Only 1 day of rest"
    ]
  },
  "freshness": {
    "data_age_days": 1,
    "data_through": "2026-06-28",
    "freshness_state": "current",
    "label": "Current baseball data through 2026-06-28.",
    "limitations": []
  },
  "roster_status": {
    "confidence": "low",
    "label": "Roster Unknown",
    "limitations": [
      "Roster status unavailable; bullpen eligibility is based on stored usage and position data."
    ],
    "source": "unavailable",
    "status": "UNKNOWN"
  },
  "workload_signal": {
    "availability_status": "Limited",
    "confidence": "high",
    "data_state": "fresh",
    "inputs": {
      "appearances_last_3_days": 1,
      "appearances_last_5_days": 1,
      "back_to_back": false,
      "days_rest": 1,
      "fatigue_risk_level": "MODERATE",
      "fatigue_score": 32.5,
      "four_in_five": false,
      "freshness_state": "fresh",
      "latest_game_date": "2026-06-28",
      "pitches_last_3_days": 27,
      "pitches_last_5_days": 27,
      "pitches_yesterday": 27,
      "reference_date": "2026-06-29",
      "three_in_four": false
    },
    "limitations": [
      "No injury data available",
      "No team-reported availability data available"
    ],
    "reasons": [
      "27 pitches yesterday",
      "Only 1 day of rest"
    ]
  }
}
```

Evidence sections:

```json
{
  "fatigue_trend_points": 1,
  "last_workload_appearance": {
    "game_date": "2026-06-28",
    "pitches": 27
  },
  "recent_logs_reviewed": 1
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
  "fallback_status": "limited_role_context",
  "pitcher": "Pierce Johnson",
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
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
  "team": "Cincinnati Reds (CIN, 113)"
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
    "confidence": "low",
    "current_assignment_unresolved": false,
    "evidence": [],
    "is_active_mlb": null,
    "is_authoritative": false,
    "is_inactive_context": false,
    "label": "Roster Unknown",
    "limitations": [
      "Roster status unavailable; bullpen eligibility is based on stored usage and position data."
    ],
    "raw_status": null,
    "raw_status_code": null,
    "raw_status_description": null,
    "source": "unavailable",
    "status": "UNKNOWN",
    "updated_at": null
  }
}
```

Evidence sections:

```json
{}
```

### Example 11: Team bullpen board context

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "fallback_status": "no_visible_pitcher_cards",
  "pitcher": null,
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "role_or_classification": {
    "total_pitchers": 0,
    "ungrouped_pitchers": 0
  },
  "source_path": "api.bullpen._build_team_board -> services.bullpen_board.build_board_payload",
  "status": "no_data",
  "surface_name": "Team bullpen board context",
  "team": "Los Angeles Angels (LAA, 108)"
}
```

Rendered public copy:
```
No bullpen availability to summarize from the latest completed data.
No active relievers fall inside the current freshness window.
Available
Workload signals are inside normal ranges in the latest completed data.
Monitor
Worth a look at recent workload before counting on these arms.
Limited
Recent workload suggests limited use in the current availability read.
Avoid
Meaningful recent-use load on these arms.
Unavailable Pitchers
Not available in the current bullpen planning read.
```

Structured fields used:

```json
{
  "context": {
    "confidence": "none",
    "health": {
      "label": "No bullpen availability to summarize from the latest completed data.",
      "reasons": [
        "No active relievers fall inside the current freshness window."
      ],
      "state": "no_data"
    },
    "limitations": [],
    "metrics": {
      "available": 0,
      "avoid": 0,
      "limited": 0,
      "monitor": 0,
      "pct_available": 0,
      "pct_restricted": 0,
      "pct_unavailable": 0,
      "restricted": 0,
      "total_relievers": 0,
      "unavailable": 0
    }
  },
  "freshness": {
    "active_cutoff_date": "2026-06-15",
    "active_window_days": 14,
    "availability_reference_date": "2026-06-29",
    "data_age_days": 1,
    "data_through": "2026-06-28",
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
    "label": "Current baseball data through 2026-06-28.",
    "last_completed_game_refresh": "2026-06-30T00:54:04.076792Z",
    "last_morning_full_sync": null,
    "last_successful_sync": "2026-06-30T00:54:04.076792Z",
    "latest_workload_date": "2026-06-28",
    "limitations": [],
    "reason_codes": [],
    "reference_date": "2026-06-29",
    "sync_authority": "sync_runs",
    "sync_status": "success"
  },
  "groups": [
    {
      "count": 0,
      "description": "Workload signals are inside normal ranges in the latest completed data.",
      "label": "Available",
      "status": "Available"
    },
    {
      "count": 0,
      "description": "Worth a look at recent workload before counting on these arms.",
      "label": "Monitor",
      "status": "Monitor"
    },
    {
      "count": 0,
      "description": "Recent workload suggests limited use in the current availability read.",
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
      "description": "Not available in the current bullpen planning read.",
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
    "Available": 0,
    "Avoid": 0,
    "Limited": 0,
    "Monitor": 0,
    "Unavailable": 0
  },
  "roster_authority_summary": {
    "limitations": [
      "Some bullpen candidates have an unconfirmed roster status and are counted only toward roster status coverage."
    ],
    "population": {
      "known_count": 0,
      "roster_status_coverage": 0.0,
      "total_candidates": 19,
      "unknown_count": 19
    }
  }
}
```

### Example 12: Team bullpen shape explanations

Metadata:

```json
{
  "banned_language_scan": {
    "status": "warn",
    "violation_count": 3,
    "violations": [
      {
        "category": "editorial_contract_denied_phrase",
        "match": "clean options",
        "start": 213,
        "term": "clean option"
      },
      {
        "category": "editorial_contract_denied_phrase",
        "match": "clean options",
        "start": 213,
        "term": "clean options"
      },
      {
        "category": "editorial_contract_denied_phrase",
        "match": "0 trusted",
        "start": 604,
        "term": "0 trusted"
      }
    ]
  },
  "fallback_status": "limited_read_shape",
  "pitcher": null,
  "retired_phrase_scan": {
    "status": "warn",
    "terms": [
      "clean option",
      "clean options",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 3,
    "violations": [
      {
        "category": "editorial_contract_denied_phrase",
        "match": "clean options",
        "start": 213,
        "term": "clean option"
      },
      {
        "category": "editorial_contract_denied_phrase",
        "match": "clean options",
        "start": 213,
        "term": "clean options"
      },
      {
        "category": "editorial_contract_denied_phrase",
        "match": "0 trusted",
        "start": 604,
        "term": "0 trusted"
      }
    ]
  },
  "role_or_classification": {
    "read_labels": [
      "Limited Read",
      "Limited Read",
      "Limited Read",
      "Limited Read",
      "Limited Read",
      "Limited Read"
    ]
  },
  "source_path": "services.team_bullpen_shape.build_team_bullpen_shape",
  "status": "team_shape",
  "surface_name": "Team bullpen shape explanations",
  "team": "Los Angeles Angels (LAA, 108)"
}
```

Rendered public copy:
```
Limited Read
Only 0 of 0 bullpen arms have clear role labels, so this part of the bullpen read stays limited.
Only 0 of 0 bullpen arms have clear workload or availability labels, so BaseballOS cannot say how many clean options the manager really has.
Only 0 of 0 bullpen arms have clear workload or availability labels, so the late-inning pressure read stays cautious.
No recent relief workload was available in the workload window, so BaseballOS cannot tell whether the same arms are carrying the work.
Coverage margin combines active capacity (unknown), resource health (unknown), and trust structure (0 trusted-group arms, 0 available in the top trust bucket).
Coverage margin is limited because the current capacity, resource health, or trust hierarchy read is incomplete.
```

Structured fields used:

```json
{
  "reads": [
    {
      "explanation": "Only 0 of 0 bullpen arms have clear role labels, so this part of the bullpen read stays limited.",
      "key": "trustAvailability",
      "label": "Limited Read",
      "reasons": [
        "Only 0 of 0 bullpen arms have clear role labels, so this part of the bullpen read stays limited."
      ],
      "supportingCounts": {
        "availableTrustArms": 0,
        "cleanTrustArms": 0,
        "limitedReadTrustArms": 0,
        "restRestrictedTrustArms": 0,
        "roleKnownCount": 0,
        "totalBullpenArms": 0,
        "trustArms": 0,
        "unavailableTrustArms": 0,
        "watchTrustArms": 0
      }
    },
    {
      "explanation": "Only 0 of 0 bullpen arms have clear workload or availability labels, so BaseballOS cannot say how many clean options the manager really has.",
      "key": "cleanOptions",
      "label": "Limited Read",
      "reasons": [
        "Only 0 of 0 bullpen arms have clear workload or availability labels, so BaseballOS cannot say how many clean options the manager really has."
      ],
      "supportingCounts": {
        "activeBullpenArms": 0,
        "cleanBridgeArms": 0,
        "cleanCoverageArms": 0,
        "cleanDepthArms": 0,
        "cleanOptionCount": 0,
        "cleanTrustArms": 0,
        "limitedReadCount": 0,
        "meaningfulCleanBacking": false,
        "restRestrictedCount": 0,
        "totalBullpenArms": 0,
        "unavailableCount": 0
      }
    },
    {
      "explanation": "Only 0 of 0 bullpen arms have clear workload or availability labels, so the late-inning pressure read stays cautious.",
      "key": "bullpenPressure",
      "label": "Limited Read",
      "reasons": [
        "Only 0 of 0 bullpen arms have clear workload or availability labels, so the late-inning pressure read stays cautious."
      ],
      "supportingCounts": {
        "cleanTrustArms": 0,
        "highFatigueArms": 0,
        "limitedReadCount": 0,
        "noUsableTrust": true,
        "restRestrictedCount": 0,
        "restrictedTrustArms": 0,
        "stressedBridgeArms": 0,
        "stressedCoverageArms": 0,
        "totalBullpenArms": 0,
        "unavailableCount": 0,
        "unavailableTrustArms": 0,
        "usableTrustArms": 0,
        "watchArmCount": 0
      }
    },
    {
      "explanation": "No recent relief workload was available in the workload window, so BaseballOS cannot tell whether the same arms are carrying the work.",
      "key": "workloadConcentration",
      "label": "Limited Read",
      "reasons": [
        "No recent relief workload was available in the workload window, so BaseballOS cannot tell whether the same arms are carrying the work."
      ],
      "supportingCounts": {
        "concentrationDescriptor": "no concentration",
        "concentrationLevel": "none",
        "participantCount": 0,
        "perArmPitches": 0.0,
        "topArmCount": 0,
        "topOneShare": 0.0,
        "topPitchTotal": 0,
        "topShare": 0.0,
        "topSharePct": 0,
        "totalRecentPitches": 0,
        "windowDays": 7
      }
    },
    {
      "capability": "bullpen_coverage_safety_v2",
      "explanation": "Coverage margin combines active capacity (unknown), resource health (unknown), and trust structure (0 trusted-group arms, 0 available in the top trust bucket).",
      "key": "coverageSafety",
      "label": "Limited Read",
      "limitations": [
        "Coverage margin is a Limited Read because active capacity, resource health, or trust hierarchy is unknown."
      ],
      "reasons": [
        "Coverage margin is limited because the current capacity, resource health, or trust hierarchy read is incomplete."
      ],
      "source": "backend",
      "supportingCounts": {
        "activeRelieverCount": 0,
        "anchorCount": 0,
        "capacityState": "unknown",
        "cleanActiveRelieverCount": 0,
        "coverageSafetyVersion": "2.0",
        "environmentPressureSources": [],
        "environmentStatus": "limited_read",
        "hierarchyConfidence": "none",
        "leverageCount": 0,
        "resourceHealthState": "unknown",
        "thresholds": {
          "stableMinCleanActiveRelievers": 3,
          "stableMinTrustedGroupSize": 4,
          "strongMinCleanActiveRelievers": 5,
          "strongMinTrustedGroupSize": 5,
          "thinTrustUnavailableMin": 2,
          "thinTrustUnavailablePct": 40
        },
        "topTrustBucketAvailableCount": 0,
        "trustArmsUnavailable": 0,
        "trustCapacityUnavailablePct": 0,
        "trustedCount": 0,
        "trustedGroupSize": 0
      },
      "version": "2026-06-19"
    },
    {
      "explanation": "Only 0 of 0 bullpen arms have clear role labels, so this part of the bullpen read stays limited.",
      "key": "depthSafety",
      "label": "Limited Read",
      "reasons": [
        "Only 0 of 0 bullpen arms have clear role labels, so this part of the bullpen read stays limited."
      ],
      "supportingCounts": {
        "activeBullpenArms": 0,
        "anchoredByTrust": false,
        "availableDepthArms": 0,
        "cleanDepthArms": 0,
        "depthArms": 0,
        "limitedReadDepthArms": 0,
        "restRestrictedDepthArms": 0,
        "roleKnownCount": 0,
        "totalBullpenArms": 0,
        "unavailableDepthArms": 0,
        "usableTrustArms": 0,
        "watchDepthArms": 0
      }
    }
  ],
  "source": "backend",
  "supportingCounts": {
    "activeBullpenArms": 0,
    "readKnownCount": 0,
    "roleKnownCount": 0,
    "totalBullpenArms": 0
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

### Example 13: Team bullpen board context

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "fallback_status": "no_visible_pitcher_cards",
  "pitcher": null,
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "role_or_classification": {
    "total_pitchers": 0,
    "ungrouped_pitchers": 0
  },
  "source_path": "api.bullpen._build_team_board -> services.bullpen_board.build_board_payload",
  "status": "no_data",
  "surface_name": "Team bullpen board context",
  "team": "Chicago Cubs (CHC, 112)"
}
```

Rendered public copy:
```
No bullpen availability to summarize from the latest completed data.
No active relievers fall inside the current freshness window.
Available
Workload signals are inside normal ranges in the latest completed data.
Monitor
Worth a look at recent workload before counting on these arms.
Limited
Recent workload suggests limited use in the current availability read.
Avoid
Meaningful recent-use load on these arms.
Unavailable Pitchers
Not available in the current bullpen planning read.
```

Structured fields used:

```json
{
  "context": {
    "confidence": "none",
    "health": {
      "label": "No bullpen availability to summarize from the latest completed data.",
      "reasons": [
        "No active relievers fall inside the current freshness window."
      ],
      "state": "no_data"
    },
    "limitations": [],
    "metrics": {
      "available": 0,
      "avoid": 0,
      "limited": 0,
      "monitor": 0,
      "pct_available": 0,
      "pct_restricted": 0,
      "pct_unavailable": 0,
      "restricted": 0,
      "total_relievers": 0,
      "unavailable": 0
    }
  },
  "freshness": {
    "active_cutoff_date": "2026-06-15",
    "active_window_days": 14,
    "availability_reference_date": "2026-06-29",
    "data_age_days": 1,
    "data_through": "2026-06-28",
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
    "label": "Current baseball data through 2026-06-28.",
    "last_completed_game_refresh": "2026-06-30T00:54:04.076792Z",
    "last_morning_full_sync": null,
    "last_successful_sync": "2026-06-30T00:54:04.076792Z",
    "latest_workload_date": "2026-06-28",
    "limitations": [],
    "reason_codes": [],
    "reference_date": "2026-06-29",
    "sync_authority": "sync_runs",
    "sync_status": "success"
  },
  "groups": [
    {
      "count": 0,
      "description": "Workload signals are inside normal ranges in the latest completed data.",
      "label": "Available",
      "status": "Available"
    },
    {
      "count": 0,
      "description": "Worth a look at recent workload before counting on these arms.",
      "label": "Monitor",
      "status": "Monitor"
    },
    {
      "count": 0,
      "description": "Recent workload suggests limited use in the current availability read.",
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
      "description": "Not available in the current bullpen planning read.",
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
    "Available": 0,
    "Avoid": 0,
    "Limited": 0,
    "Monitor": 0,
    "Unavailable": 0
  },
  "roster_authority_summary": {
    "limitations": [
      "Some bullpen candidates have an unconfirmed roster status and are counted only toward roster status coverage."
    ],
    "population": {
      "known_count": 0,
      "roster_status_coverage": 0.0,
      "total_candidates": 19,
      "unknown_count": 19
    }
  }
}
```

### Example 14: Team bullpen shape explanations

Metadata:

```json
{
  "banned_language_scan": {
    "status": "warn",
    "violation_count": 3,
    "violations": [
      {
        "category": "editorial_contract_denied_phrase",
        "match": "clean options",
        "start": 213,
        "term": "clean option"
      },
      {
        "category": "editorial_contract_denied_phrase",
        "match": "clean options",
        "start": 213,
        "term": "clean options"
      },
      {
        "category": "editorial_contract_denied_phrase",
        "match": "0 trusted",
        "start": 604,
        "term": "0 trusted"
      }
    ]
  },
  "fallback_status": "limited_read_shape",
  "pitcher": null,
  "retired_phrase_scan": {
    "status": "warn",
    "terms": [
      "clean option",
      "clean options",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 3,
    "violations": [
      {
        "category": "editorial_contract_denied_phrase",
        "match": "clean options",
        "start": 213,
        "term": "clean option"
      },
      {
        "category": "editorial_contract_denied_phrase",
        "match": "clean options",
        "start": 213,
        "term": "clean options"
      },
      {
        "category": "editorial_contract_denied_phrase",
        "match": "0 trusted",
        "start": 604,
        "term": "0 trusted"
      }
    ]
  },
  "role_or_classification": {
    "read_labels": [
      "Limited Read",
      "Limited Read",
      "Limited Read",
      "Limited Read",
      "Limited Read",
      "Limited Read"
    ]
  },
  "source_path": "services.team_bullpen_shape.build_team_bullpen_shape",
  "status": "team_shape",
  "surface_name": "Team bullpen shape explanations",
  "team": "Chicago Cubs (CHC, 112)"
}
```

Rendered public copy:
```
Limited Read
Only 0 of 0 bullpen arms have clear role labels, so this part of the bullpen read stays limited.
Only 0 of 0 bullpen arms have clear workload or availability labels, so BaseballOS cannot say how many clean options the manager really has.
Only 0 of 0 bullpen arms have clear workload or availability labels, so the late-inning pressure read stays cautious.
No recent relief workload was available in the workload window, so BaseballOS cannot tell whether the same arms are carrying the work.
Coverage margin combines active capacity (unknown), resource health (unknown), and trust structure (0 trusted-group arms, 0 available in the top trust bucket).
Coverage margin is limited because the current capacity, resource health, or trust hierarchy read is incomplete.
```

Structured fields used:

```json
{
  "reads": [
    {
      "explanation": "Only 0 of 0 bullpen arms have clear role labels, so this part of the bullpen read stays limited.",
      "key": "trustAvailability",
      "label": "Limited Read",
      "reasons": [
        "Only 0 of 0 bullpen arms have clear role labels, so this part of the bullpen read stays limited."
      ],
      "supportingCounts": {
        "availableTrustArms": 0,
        "cleanTrustArms": 0,
        "limitedReadTrustArms": 0,
        "restRestrictedTrustArms": 0,
        "roleKnownCount": 0,
        "totalBullpenArms": 0,
        "trustArms": 0,
        "unavailableTrustArms": 0,
        "watchTrustArms": 0
      }
    },
    {
      "explanation": "Only 0 of 0 bullpen arms have clear workload or availability labels, so BaseballOS cannot say how many clean options the manager really has.",
      "key": "cleanOptions",
      "label": "Limited Read",
      "reasons": [
        "Only 0 of 0 bullpen arms have clear workload or availability labels, so BaseballOS cannot say how many clean options the manager really has."
      ],
      "supportingCounts": {
        "activeBullpenArms": 0,
        "cleanBridgeArms": 0,
        "cleanCoverageArms": 0,
        "cleanDepthArms": 0,
        "cleanOptionCount": 0,
        "cleanTrustArms": 0,
        "limitedReadCount": 0,
        "meaningfulCleanBacking": false,
        "restRestrictedCount": 0,
        "totalBullpenArms": 0,
        "unavailableCount": 0
      }
    },
    {
      "explanation": "Only 0 of 0 bullpen arms have clear workload or availability labels, so the late-inning pressure read stays cautious.",
      "key": "bullpenPressure",
      "label": "Limited Read",
      "reasons": [
        "Only 0 of 0 bullpen arms have clear workload or availability labels, so the late-inning pressure read stays cautious."
      ],
      "supportingCounts": {
        "cleanTrustArms": 0,
        "highFatigueArms": 0,
        "limitedReadCount": 0,
        "noUsableTrust": true,
        "restRestrictedCount": 0,
        "restrictedTrustArms": 0,
        "stressedBridgeArms": 0,
        "stressedCoverageArms": 0,
        "totalBullpenArms": 0,
        "unavailableCount": 0,
        "unavailableTrustArms": 0,
        "usableTrustArms": 0,
        "watchArmCount": 0
      }
    },
    {
      "explanation": "No recent relief workload was available in the workload window, so BaseballOS cannot tell whether the same arms are carrying the work.",
      "key": "workloadConcentration",
      "label": "Limited Read",
      "reasons": [
        "No recent relief workload was available in the workload window, so BaseballOS cannot tell whether the same arms are carrying the work."
      ],
      "supportingCounts": {
        "concentrationDescriptor": "no concentration",
        "concentrationLevel": "none",
        "participantCount": 0,
        "perArmPitches": 0.0,
        "topArmCount": 0,
        "topOneShare": 0.0,
        "topPitchTotal": 0,
        "topShare": 0.0,
        "topSharePct": 0,
        "totalRecentPitches": 0,
        "windowDays": 7
      }
    },
    {
      "capability": "bullpen_coverage_safety_v2",
      "explanation": "Coverage margin combines active capacity (unknown), resource health (unknown), and trust structure (0 trusted-group arms, 0 available in the top trust bucket).",
      "key": "coverageSafety",
      "label": "Limited Read",
      "limitations": [
        "Coverage margin is a Limited Read because active capacity, resource health, or trust hierarchy is unknown."
      ],
      "reasons": [
        "Coverage margin is limited because the current capacity, resource health, or trust hierarchy read is incomplete."
      ],
      "source": "backend",
      "supportingCounts": {
        "activeRelieverCount": 0,
        "anchorCount": 0,
        "capacityState": "unknown",
        "cleanActiveRelieverCount": 0,
        "coverageSafetyVersion": "2.0",
        "environmentPressureSources": [],
        "environmentStatus": "limited_read",
        "hierarchyConfidence": "none",
        "leverageCount": 0,
        "resourceHealthState": "unknown",
        "thresholds": {
          "stableMinCleanActiveRelievers": 3,
          "stableMinTrustedGroupSize": 4,
          "strongMinCleanActiveRelievers": 5,
          "strongMinTrustedGroupSize": 5,
          "thinTrustUnavailableMin": 2,
          "thinTrustUnavailablePct": 40
        },
        "topTrustBucketAvailableCount": 0,
        "trustArmsUnavailable": 0,
        "trustCapacityUnavailablePct": 0,
        "trustedCount": 0,
        "trustedGroupSize": 0
      },
      "version": "2026-06-19"
    },
    {
      "explanation": "Only 0 of 0 bullpen arms have clear role labels, so this part of the bullpen read stays limited.",
      "key": "depthSafety",
      "label": "Limited Read",
      "reasons": [
        "Only 0 of 0 bullpen arms have clear role labels, so this part of the bullpen read stays limited."
      ],
      "supportingCounts": {
        "activeBullpenArms": 0,
        "anchoredByTrust": false,
        "availableDepthArms": 0,
        "cleanDepthArms": 0,
        "depthArms": 0,
        "limitedReadDepthArms": 0,
        "restRestrictedDepthArms": 0,
        "roleKnownCount": 0,
        "totalBullpenArms": 0,
        "unavailableDepthArms": 0,
        "usableTrustArms": 0,
        "watchDepthArms": 0
      }
    }
  ],
  "source": "backend",
  "supportingCounts": {
    "activeBullpenArms": 0,
    "readKnownCount": 0,
    "roleKnownCount": 0,
    "totalBullpenArms": 0
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

### Example 15: Team bullpen board context

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "fallback_status": "no_visible_pitcher_cards",
  "pitcher": null,
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 0,
    "violations": []
  },
  "role_or_classification": {
    "total_pitchers": 0,
    "ungrouped_pitchers": 0
  },
  "source_path": "api.bullpen._build_team_board -> services.bullpen_board.build_board_payload",
  "status": "no_data",
  "surface_name": "Team bullpen board context",
  "team": "Cincinnati Reds (CIN, 113)"
}
```

Rendered public copy:
```
No bullpen availability to summarize from the latest completed data.
No active relievers fall inside the current freshness window.
Available
Workload signals are inside normal ranges in the latest completed data.
Monitor
Worth a look at recent workload before counting on these arms.
Limited
Recent workload suggests limited use in the current availability read.
Avoid
Meaningful recent-use load on these arms.
Unavailable Pitchers
Not available in the current bullpen planning read.
```

Structured fields used:

```json
{
  "context": {
    "confidence": "none",
    "health": {
      "label": "No bullpen availability to summarize from the latest completed data.",
      "reasons": [
        "No active relievers fall inside the current freshness window."
      ],
      "state": "no_data"
    },
    "limitations": [],
    "metrics": {
      "available": 0,
      "avoid": 0,
      "limited": 0,
      "monitor": 0,
      "pct_available": 0,
      "pct_restricted": 0,
      "pct_unavailable": 0,
      "restricted": 0,
      "total_relievers": 0,
      "unavailable": 0
    }
  },
  "freshness": {
    "active_cutoff_date": "2026-06-15",
    "active_window_days": 14,
    "availability_reference_date": "2026-06-29",
    "data_age_days": 1,
    "data_through": "2026-06-28",
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
    "label": "Current baseball data through 2026-06-28.",
    "last_completed_game_refresh": "2026-06-30T00:54:04.076792Z",
    "last_morning_full_sync": null,
    "last_successful_sync": "2026-06-30T00:54:04.076792Z",
    "latest_workload_date": "2026-06-28",
    "limitations": [],
    "reason_codes": [],
    "reference_date": "2026-06-29",
    "sync_authority": "sync_runs",
    "sync_status": "success"
  },
  "groups": [
    {
      "count": 0,
      "description": "Workload signals are inside normal ranges in the latest completed data.",
      "label": "Available",
      "status": "Available"
    },
    {
      "count": 0,
      "description": "Worth a look at recent workload before counting on these arms.",
      "label": "Monitor",
      "status": "Monitor"
    },
    {
      "count": 0,
      "description": "Recent workload suggests limited use in the current availability read.",
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
      "description": "Not available in the current bullpen planning read.",
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
    "Available": 0,
    "Avoid": 0,
    "Limited": 0,
    "Monitor": 0,
    "Unavailable": 0
  },
  "roster_authority_summary": {
    "limitations": [
      "Some bullpen candidates have an unconfirmed roster status and are counted only toward roster status coverage."
    ],
    "population": {
      "known_count": 0,
      "roster_status_coverage": 0.0,
      "total_candidates": 17,
      "unknown_count": 17
    }
  }
}
```

### Example 16: Team bullpen shape explanations

Metadata:

```json
{
  "banned_language_scan": {
    "status": "warn",
    "violation_count": 3,
    "violations": [
      {
        "category": "editorial_contract_denied_phrase",
        "match": "clean options",
        "start": 213,
        "term": "clean option"
      },
      {
        "category": "editorial_contract_denied_phrase",
        "match": "clean options",
        "start": 213,
        "term": "clean options"
      },
      {
        "category": "editorial_contract_denied_phrase",
        "match": "0 trusted",
        "start": 604,
        "term": "0 trusted"
      }
    ]
  },
  "fallback_status": "limited_read_shape",
  "pitcher": null,
  "retired_phrase_scan": {
    "status": "warn",
    "terms": [
      "clean option",
      "clean options",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
      "availability distributions",
      "practical path",
      "practical paths",
      "0 trusted"
    ],
    "violation_count": 3,
    "violations": [
      {
        "category": "editorial_contract_denied_phrase",
        "match": "clean options",
        "start": 213,
        "term": "clean option"
      },
      {
        "category": "editorial_contract_denied_phrase",
        "match": "clean options",
        "start": 213,
        "term": "clean options"
      },
      {
        "category": "editorial_contract_denied_phrase",
        "match": "0 trusted",
        "start": 604,
        "term": "0 trusted"
      }
    ]
  },
  "role_or_classification": {
    "read_labels": [
      "Limited Read",
      "Limited Read",
      "Limited Read",
      "Limited Read",
      "Limited Read",
      "Limited Read"
    ]
  },
  "source_path": "services.team_bullpen_shape.build_team_bullpen_shape",
  "status": "team_shape",
  "surface_name": "Team bullpen shape explanations",
  "team": "Cincinnati Reds (CIN, 113)"
}
```

Rendered public copy:
```
Limited Read
Only 0 of 0 bullpen arms have clear role labels, so this part of the bullpen read stays limited.
Only 0 of 0 bullpen arms have clear workload or availability labels, so BaseballOS cannot say how many clean options the manager really has.
Only 0 of 0 bullpen arms have clear workload or availability labels, so the late-inning pressure read stays cautious.
No recent relief workload was available in the workload window, so BaseballOS cannot tell whether the same arms are carrying the work.
Coverage margin combines active capacity (unknown), resource health (unknown), and trust structure (0 trusted-group arms, 0 available in the top trust bucket).
Coverage margin is limited because the current capacity, resource health, or trust hierarchy read is incomplete.
```

Structured fields used:

```json
{
  "reads": [
    {
      "explanation": "Only 0 of 0 bullpen arms have clear role labels, so this part of the bullpen read stays limited.",
      "key": "trustAvailability",
      "label": "Limited Read",
      "reasons": [
        "Only 0 of 0 bullpen arms have clear role labels, so this part of the bullpen read stays limited."
      ],
      "supportingCounts": {
        "availableTrustArms": 0,
        "cleanTrustArms": 0,
        "limitedReadTrustArms": 0,
        "restRestrictedTrustArms": 0,
        "roleKnownCount": 0,
        "totalBullpenArms": 0,
        "trustArms": 0,
        "unavailableTrustArms": 0,
        "watchTrustArms": 0
      }
    },
    {
      "explanation": "Only 0 of 0 bullpen arms have clear workload or availability labels, so BaseballOS cannot say how many clean options the manager really has.",
      "key": "cleanOptions",
      "label": "Limited Read",
      "reasons": [
        "Only 0 of 0 bullpen arms have clear workload or availability labels, so BaseballOS cannot say how many clean options the manager really has."
      ],
      "supportingCounts": {
        "activeBullpenArms": 0,
        "cleanBridgeArms": 0,
        "cleanCoverageArms": 0,
        "cleanDepthArms": 0,
        "cleanOptionCount": 0,
        "cleanTrustArms": 0,
        "limitedReadCount": 0,
        "meaningfulCleanBacking": false,
        "restRestrictedCount": 0,
        "totalBullpenArms": 0,
        "unavailableCount": 0
      }
    },
    {
      "explanation": "Only 0 of 0 bullpen arms have clear workload or availability labels, so the late-inning pressure read stays cautious.",
      "key": "bullpenPressure",
      "label": "Limited Read",
      "reasons": [
        "Only 0 of 0 bullpen arms have clear workload or availability labels, so the late-inning pressure read stays cautious."
      ],
      "supportingCounts": {
        "cleanTrustArms": 0,
        "highFatigueArms": 0,
        "limitedReadCount": 0,
        "noUsableTrust": true,
        "restRestrictedCount": 0,
        "restrictedTrustArms": 0,
        "stressedBridgeArms": 0,
        "stressedCoverageArms": 0,
        "totalBullpenArms": 0,
        "unavailableCount": 0,
        "unavailableTrustArms": 0,
        "usableTrustArms": 0,
        "watchArmCount": 0
      }
    },
    {
      "explanation": "No recent relief workload was available in the workload window, so BaseballOS cannot tell whether the same arms are carrying the work.",
      "key": "workloadConcentration",
      "label": "Limited Read",
      "reasons": [
        "No recent relief workload was available in the workload window, so BaseballOS cannot tell whether the same arms are carrying the work."
      ],
      "supportingCounts": {
        "concentrationDescriptor": "no concentration",
        "concentrationLevel": "none",
        "participantCount": 0,
        "perArmPitches": 0.0,
        "topArmCount": 0,
        "topOneShare": 0.0,
        "topPitchTotal": 0,
        "topShare": 0.0,
        "topSharePct": 0,
        "totalRecentPitches": 0,
        "windowDays": 7
      }
    },
    {
      "capability": "bullpen_coverage_safety_v2",
      "explanation": "Coverage margin combines active capacity (unknown), resource health (unknown), and trust structure (0 trusted-group arms, 0 available in the top trust bucket).",
      "key": "coverageSafety",
      "label": "Limited Read",
      "limitations": [
        "Coverage margin is a Limited Read because active capacity, resource health, or trust hierarchy is unknown."
      ],
      "reasons": [
        "Coverage margin is limited because the current capacity, resource health, or trust hierarchy read is incomplete."
      ],
      "source": "backend",
      "supportingCounts": {
        "activeRelieverCount": 0,
        "anchorCount": 0,
        "capacityState": "unknown",
        "cleanActiveRelieverCount": 0,
        "coverageSafetyVersion": "2.0",
        "environmentPressureSources": [],
        "environmentStatus": "limited_read",
        "hierarchyConfidence": "none",
        "leverageCount": 0,
        "resourceHealthState": "unknown",
        "thresholds": {
          "stableMinCleanActiveRelievers": 3,
          "stableMinTrustedGroupSize": 4,
          "strongMinCleanActiveRelievers": 5,
          "strongMinTrustedGroupSize": 5,
          "thinTrustUnavailableMin": 2,
          "thinTrustUnavailablePct": 40
        },
        "topTrustBucketAvailableCount": 0,
        "trustArmsUnavailable": 0,
        "trustCapacityUnavailablePct": 0,
        "trustedCount": 0,
        "trustedGroupSize": 0
      },
      "version": "2026-06-19"
    },
    {
      "explanation": "Only 0 of 0 bullpen arms have clear role labels, so this part of the bullpen read stays limited.",
      "key": "depthSafety",
      "label": "Limited Read",
      "reasons": [
        "Only 0 of 0 bullpen arms have clear role labels, so this part of the bullpen read stays limited."
      ],
      "supportingCounts": {
        "activeBullpenArms": 0,
        "anchoredByTrust": false,
        "availableDepthArms": 0,
        "cleanDepthArms": 0,
        "depthArms": 0,
        "limitedReadDepthArms": 0,
        "restRestrictedDepthArms": 0,
        "roleKnownCount": 0,
        "totalBullpenArms": 0,
        "unavailableDepthArms": 0,
        "usableTrustArms": 0,
        "watchDepthArms": 0
      }
    }
  ],
  "source": "backend",
  "supportingCounts": {
    "activeBullpenArms": 0,
    "readKnownCount": 0,
    "roleKnownCount": 0,
    "totalBullpenArms": 0
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

### Example 17: Team Operations readiness V4 explanation

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "fallback_status": "data_limited",
  "pitcher": null,
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
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
  "team": "Los Angeles Angels (LAA, 108)"
}
```

Rendered public copy:
```
This readiness state reflects workload, freshness, coverage, trust, and limitation evidence.
Readiness context is degraded by visible limitations.
Coverage evidence is partial for the explained state.
Trust metadata limits confidence in the explanation.
Readiness is based on public workload data, not private team information.
Readiness is not injury or medical information.
Readiness is not a performance forecast.
Manager intent and bullpen warm-up state are not available.
The user remains responsible for baseball decisions.
Some active pitcher records have incomplete readiness evidence.
Readiness explanation confidence is limited by trust metadata.
Readiness explanation uses current Team Operations freshness metadata.
Trust reflects existing Team Operations metadata and confidence.
Explanation confidence mirrors the existing Team Operations confidence metadata.
```

Structured fields used:

```json
{
  "availability_distribution": {
    "available": 0,
    "avoid": 0,
    "limited": 0,
    "monitor": 19,
    "total": 19,
    "unavailable": 0,
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
      "message": "Trust metadata limits the readiness summary.",
      "severity": "caution"
    },
    {
      "affected_area": "coverage_inventory",
      "category": "coverage",
      "constraint_id": "coverage_partial",
      "count": 18,
      "evidence": [
        "missing_workload_data_count: 18",
        "availability_missing_count: 0"
      ],
      "message": "Some active pitcher records have incomplete readiness evidence.",
      "severity": "caution"
    }
  ],
  "coverage_inventory": {
    "active_pitcher_count": 19,
    "availability_covered_count": 19,
    "availability_missing_count": 0,
    "coverage_state": "partial",
    "current_workload_data_count": 1,
    "missing_workload_data_count": 18
  },
  "freshness": {
    "data_through": "2026-06-28",
    "freshness_state": "current",
    "generated_at": "2026-06-30T00:54:01",
    "last_successful_sync": "2026-06-30T00:54:04.076792Z",
    "latest_fatigue_calculated_at": "2026-06-30T00:54:01.265129Z",
    "latest_sync_status": "success",
    "latest_workload_date": "2026-06-28",
    "limitations": [],
    "missing_data_warning": null,
    "stale_warning": null
  },
  "handedness_coverage": {
    "coverage_state": "covered",
    "left_handed_count": 5,
    "limitations": [],
    "right_handed_count": 14,
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
    "generated_at": "2026-06-30T00:54:01",
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
    "elevated_count": 0,
    "latest_workload_date": "2026-06-28",
    "low_count": 0,
    "moderate_count": 1,
    "pressure_state": "unknown",
    "pressure_state_code": "unknown",
    "summary": "Recent workload pressure is partially unknown.",
    "unknown_count": 18
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
      "summary": "Readiness explanation confidence is limited by trust metadata."
    }
  ],
  "primary_reasons": [
    {
      "code": "READINESS_DEGRADED_BY_LIMITATIONS",
      "label": "Readiness degraded by limitations",
      "scope": "readiness_state",
      "summary": "Readiness context is degraded by visible limitations."
    },
    {
      "code": "COVERAGE_PARTIAL",
      "label": "Coverage partial",
      "scope": "coverage_state",
      "summary": "Coverage evidence is partial for the explained state."
    },
    {
      "code": "TRUST_LIMITED",
      "label": "Trust limited",
      "scope": "trust_state",
      "summary": "Trust metadata limits confidence in the explanation."
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
      "value": "unknown"
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
      "value": 0
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
      "value": 18
    },
    {
      "evidence_type": "availability_distribution_available",
      "impact": "explains_availability_state",
      "label": "Available inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 0
    },
    {
      "evidence_type": "availability_distribution_monitor",
      "impact": "explains_availability_state",
      "label": "Monitor inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 19
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
      "value": 1
    },
    {
      "evidence_type": "coverage_inventory_missing_workload_data_count",
      "impact": "explains_coverage_state",
      "label": "Missing workload data count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 18
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
      "value": 5
    },
    {
      "evidence_type": "handedness_coverage_right_handed_count",
      "impact": "explains_coverage_state",
      "label": "Right handed count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 14
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
        "message": "Trust metadata limits the readiness summary.",
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
        "count": 18,
        "evidence": [
          "missing_workload_data_count: 18",
          "availability_missing_count: 0"
        ],
        "message": "Some active pitcher records have incomplete readiness evidence.",
        "severity": "caution"
      }
    }
  ]
}
```

### Example 18: Team Operations readiness V4 explanation

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "fallback_status": "data_limited",
  "pitcher": null,
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
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
  "status": "unknown",
  "surface_name": "Team Operations readiness V4 explanation",
  "team": "Los Angeles Angels (LAA, 108)"
}
```

Rendered public copy:
```
This workload state reflects team-level workload pressure evidence.
Readiness context is degraded by visible limitations.
Coverage evidence is partial for the explained state.
Trust metadata limits confidence in the explanation.
Readiness is based on public workload data, not private team information.
Readiness is not injury or medical information.
Readiness is not a performance forecast.
Manager intent and bullpen warm-up state are not available.
The user remains responsible for baseball decisions.
Some active pitcher records have incomplete readiness evidence.
Readiness explanation confidence is limited by trust metadata.
Readiness explanation uses current Team Operations freshness metadata.
Trust reflects existing Team Operations metadata and confidence.
Explanation confidence mirrors the existing Team Operations confidence metadata.
```

Structured fields used:

```json
{
  "availability_distribution": {
    "available": 0,
    "avoid": 0,
    "limited": 0,
    "monitor": 19,
    "total": 19,
    "unavailable": 0,
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
      "message": "Trust metadata limits the readiness summary.",
      "severity": "caution"
    },
    {
      "affected_area": "coverage_inventory",
      "category": "coverage",
      "constraint_id": "coverage_partial",
      "count": 18,
      "evidence": [
        "missing_workload_data_count: 18",
        "availability_missing_count: 0"
      ],
      "message": "Some active pitcher records have incomplete readiness evidence.",
      "severity": "caution"
    }
  ],
  "coverage_inventory": {
    "active_pitcher_count": 19,
    "availability_covered_count": 19,
    "availability_missing_count": 0,
    "coverage_state": "partial",
    "current_workload_data_count": 1,
    "missing_workload_data_count": 18
  },
  "freshness": {
    "data_through": "2026-06-28",
    "freshness_state": "current",
    "generated_at": "2026-06-30T00:54:01",
    "last_successful_sync": "2026-06-30T00:54:04.076792Z",
    "latest_fatigue_calculated_at": "2026-06-30T00:54:01.265129Z",
    "latest_sync_status": "success",
    "latest_workload_date": "2026-06-28",
    "limitations": [],
    "missing_data_warning": null,
    "stale_warning": null
  },
  "handedness_coverage": {
    "coverage_state": "covered",
    "left_handed_count": 5,
    "limitations": [],
    "right_handed_count": 14,
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
    "generated_at": "2026-06-30T00:54:01",
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
    "elevated_count": 0,
    "latest_workload_date": "2026-06-28",
    "low_count": 0,
    "moderate_count": 1,
    "pressure_state": "unknown",
    "pressure_state_code": "unknown",
    "summary": "Recent workload pressure is partially unknown.",
    "unknown_count": 18
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
      "summary": "Readiness explanation confidence is limited by trust metadata."
    }
  ],
  "primary_reasons": [
    {
      "code": "READINESS_DEGRADED_BY_LIMITATIONS",
      "label": "Readiness degraded by limitations",
      "scope": "readiness_state",
      "summary": "Readiness context is degraded by visible limitations."
    },
    {
      "code": "COVERAGE_PARTIAL",
      "label": "Coverage partial",
      "scope": "coverage_state",
      "summary": "Coverage evidence is partial for the explained state."
    },
    {
      "code": "TRUST_LIMITED",
      "label": "Trust limited",
      "scope": "trust_state",
      "summary": "Trust metadata limits confidence in the explanation."
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
      "value": "unknown"
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
      "value": 0
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
      "value": 18
    },
    {
      "evidence_type": "availability_distribution_available",
      "impact": "explains_availability_state",
      "label": "Available inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 0
    },
    {
      "evidence_type": "availability_distribution_monitor",
      "impact": "explains_availability_state",
      "label": "Monitor inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 19
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
      "value": 1
    },
    {
      "evidence_type": "coverage_inventory_missing_workload_data_count",
      "impact": "explains_coverage_state",
      "label": "Missing workload data count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 18
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
      "value": 5
    },
    {
      "evidence_type": "handedness_coverage_right_handed_count",
      "impact": "explains_coverage_state",
      "label": "Right handed count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 14
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
        "message": "Trust metadata limits the readiness summary.",
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
        "count": 18,
        "evidence": [
          "missing_workload_data_count: 18",
          "availability_missing_count: 0"
        ],
        "message": "Some active pitcher records have incomplete readiness evidence.",
        "severity": "caution"
      }
    }
  ]
}
```

### Example 19: Team Operations readiness V4 explanation

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "fallback_status": "data_limited",
  "pitcher": null,
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
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
  "team": "Los Angeles Angels (LAA, 108)"
}
```

Rendered public copy:
```
This coverage state reflects workload, availability, and handedness coverage evidence.
Readiness context is degraded by visible limitations.
Coverage evidence is partial for the explained state.
Trust metadata limits confidence in the explanation.
Readiness is based on public workload data, not private team information.
Readiness is not injury or medical information.
Readiness is not a performance forecast.
Manager intent and bullpen warm-up state are not available.
The user remains responsible for baseball decisions.
Some active pitcher records have incomplete readiness evidence.
Readiness explanation confidence is limited by trust metadata.
Readiness explanation uses current Team Operations freshness metadata.
Trust reflects existing Team Operations metadata and confidence.
Explanation confidence mirrors the existing Team Operations confidence metadata.
```

Structured fields used:

```json
{
  "availability_distribution": {
    "available": 0,
    "avoid": 0,
    "limited": 0,
    "monitor": 19,
    "total": 19,
    "unavailable": 0,
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
      "message": "Trust metadata limits the readiness summary.",
      "severity": "caution"
    },
    {
      "affected_area": "coverage_inventory",
      "category": "coverage",
      "constraint_id": "coverage_partial",
      "count": 18,
      "evidence": [
        "missing_workload_data_count: 18",
        "availability_missing_count: 0"
      ],
      "message": "Some active pitcher records have incomplete readiness evidence.",
      "severity": "caution"
    }
  ],
  "coverage_inventory": {
    "active_pitcher_count": 19,
    "availability_covered_count": 19,
    "availability_missing_count": 0,
    "coverage_state": "partial",
    "current_workload_data_count": 1,
    "missing_workload_data_count": 18
  },
  "freshness": {
    "data_through": "2026-06-28",
    "freshness_state": "current",
    "generated_at": "2026-06-30T00:54:01",
    "last_successful_sync": "2026-06-30T00:54:04.076792Z",
    "latest_fatigue_calculated_at": "2026-06-30T00:54:01.265129Z",
    "latest_sync_status": "success",
    "latest_workload_date": "2026-06-28",
    "limitations": [],
    "missing_data_warning": null,
    "stale_warning": null
  },
  "handedness_coverage": {
    "coverage_state": "covered",
    "left_handed_count": 5,
    "limitations": [],
    "right_handed_count": 14,
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
    "generated_at": "2026-06-30T00:54:01",
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
    "elevated_count": 0,
    "latest_workload_date": "2026-06-28",
    "low_count": 0,
    "moderate_count": 1,
    "pressure_state": "unknown",
    "pressure_state_code": "unknown",
    "summary": "Recent workload pressure is partially unknown.",
    "unknown_count": 18
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
      "summary": "Readiness explanation confidence is limited by trust metadata."
    }
  ],
  "primary_reasons": [
    {
      "code": "READINESS_DEGRADED_BY_LIMITATIONS",
      "label": "Readiness degraded by limitations",
      "scope": "readiness_state",
      "summary": "Readiness context is degraded by visible limitations."
    },
    {
      "code": "COVERAGE_PARTIAL",
      "label": "Coverage partial",
      "scope": "coverage_state",
      "summary": "Coverage evidence is partial for the explained state."
    },
    {
      "code": "TRUST_LIMITED",
      "label": "Trust limited",
      "scope": "trust_state",
      "summary": "Trust metadata limits confidence in the explanation."
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
      "value": "unknown"
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
      "value": 0
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
      "value": 18
    },
    {
      "evidence_type": "availability_distribution_available",
      "impact": "explains_availability_state",
      "label": "Available inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 0
    },
    {
      "evidence_type": "availability_distribution_monitor",
      "impact": "explains_availability_state",
      "label": "Monitor inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 19
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
      "value": 1
    },
    {
      "evidence_type": "coverage_inventory_missing_workload_data_count",
      "impact": "explains_coverage_state",
      "label": "Missing workload data count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 18
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
      "value": 5
    },
    {
      "evidence_type": "handedness_coverage_right_handed_count",
      "impact": "explains_coverage_state",
      "label": "Right handed count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 14
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
        "message": "Trust metadata limits the readiness summary.",
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
        "count": 18,
        "evidence": [
          "missing_workload_data_count: 18",
          "availability_missing_count: 0"
        ],
        "message": "Some active pitcher records have incomplete readiness evidence.",
        "severity": "caution"
      }
    }
  ]
}
```

### Example 20: Team Operations readiness V4 explanation

Metadata:

```json
{
  "banned_language_scan": {
    "status": "pass",
    "violation_count": 0,
    "violations": []
  },
  "fallback_status": "data_limited",
  "pitcher": null,
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
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
  "team": "Los Angeles Angels (LAA, 108)"
}
```

Rendered public copy:
```
This freshness state reflects source sync and workload-recency evidence.
Readiness context is degraded by visible limitations.
Coverage evidence is partial for the explained state.
Trust metadata limits confidence in the explanation.
Readiness is based on public workload data, not private team information.
Readiness is not injury or medical information.
Readiness is not a performance forecast.
Manager intent and bullpen warm-up state are not available.
The user remains responsible for baseball decisions.
Some active pitcher records have incomplete readiness evidence.
Readiness explanation confidence is limited by trust metadata.
Readiness explanation uses current Team Operations freshness metadata.
Trust reflects existing Team Operations metadata and confidence.
Explanation confidence mirrors the existing Team Operations confidence metadata.
```

Structured fields used:

```json
{
  "availability_distribution": {
    "available": 0,
    "avoid": 0,
    "limited": 0,
    "monitor": 19,
    "total": 19,
    "unavailable": 0,
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
      "message": "Trust metadata limits the readiness summary.",
      "severity": "caution"
    },
    {
      "affected_area": "coverage_inventory",
      "category": "coverage",
      "constraint_id": "coverage_partial",
      "count": 18,
      "evidence": [
        "missing_workload_data_count: 18",
        "availability_missing_count: 0"
      ],
      "message": "Some active pitcher records have incomplete readiness evidence.",
      "severity": "caution"
    }
  ],
  "coverage_inventory": {
    "active_pitcher_count": 19,
    "availability_covered_count": 19,
    "availability_missing_count": 0,
    "coverage_state": "partial",
    "current_workload_data_count": 1,
    "missing_workload_data_count": 18
  },
  "freshness": {
    "data_through": "2026-06-28",
    "freshness_state": "current",
    "generated_at": "2026-06-30T00:54:01",
    "last_successful_sync": "2026-06-30T00:54:04.076792Z",
    "latest_fatigue_calculated_at": "2026-06-30T00:54:01.265129Z",
    "latest_sync_status": "success",
    "latest_workload_date": "2026-06-28",
    "limitations": [],
    "missing_data_warning": null,
    "stale_warning": null
  },
  "handedness_coverage": {
    "coverage_state": "covered",
    "left_handed_count": 5,
    "limitations": [],
    "right_handed_count": 14,
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
    "generated_at": "2026-06-30T00:54:01",
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
    "elevated_count": 0,
    "latest_workload_date": "2026-06-28",
    "low_count": 0,
    "moderate_count": 1,
    "pressure_state": "unknown",
    "pressure_state_code": "unknown",
    "summary": "Recent workload pressure is partially unknown.",
    "unknown_count": 18
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
      "summary": "Readiness explanation confidence is limited by trust metadata."
    }
  ],
  "primary_reasons": [
    {
      "code": "READINESS_DEGRADED_BY_LIMITATIONS",
      "label": "Readiness degraded by limitations",
      "scope": "readiness_state",
      "summary": "Readiness context is degraded by visible limitations."
    },
    {
      "code": "COVERAGE_PARTIAL",
      "label": "Coverage partial",
      "scope": "coverage_state",
      "summary": "Coverage evidence is partial for the explained state."
    },
    {
      "code": "TRUST_LIMITED",
      "label": "Trust limited",
      "scope": "trust_state",
      "summary": "Trust metadata limits confidence in the explanation."
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
      "value": "unknown"
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
      "value": 0
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
      "value": 18
    },
    {
      "evidence_type": "availability_distribution_available",
      "impact": "explains_availability_state",
      "label": "Available inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 0
    },
    {
      "evidence_type": "availability_distribution_monitor",
      "impact": "explains_availability_state",
      "label": "Monitor inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 19
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
      "value": 1
    },
    {
      "evidence_type": "coverage_inventory_missing_workload_data_count",
      "impact": "explains_coverage_state",
      "label": "Missing workload data count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 18
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
      "value": 5
    },
    {
      "evidence_type": "handedness_coverage_right_handed_count",
      "impact": "explains_coverage_state",
      "label": "Right handed count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 14
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
        "message": "Trust metadata limits the readiness summary.",
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
        "count": 18,
        "evidence": [
          "missing_workload_data_count: 18",
          "availability_missing_count: 0"
        ],
        "message": "Some active pitcher records have incomplete readiness evidence.",
        "severity": "caution"
      }
    }
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
  "fallback_status": "data_limited",
  "pitcher": null,
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
      "clean arms",
      "short list of clean arms",
      "clean way",
      "clean ways",
      "usable group",
      "usable depth",
      "in good shape",
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
  "team": "Los Angeles Angels (LAA, 108)"
}
```

Rendered public copy:
```
This trust state reflects Team Operations trust metadata and confidence evidence.
Readiness context is degraded by visible limitations.
Coverage evidence is partial for the explained state.
Trust metadata limits confidence in the explanation.
Readiness is based on public workload data, not private team information.
Readiness is not injury or medical information.
Readiness is not a performance forecast.
Manager intent and bullpen warm-up state are not available.
The user remains responsible for baseball decisions.
Some active pitcher records have incomplete readiness evidence.
Readiness explanation confidence is limited by trust metadata.
Readiness explanation uses current Team Operations freshness metadata.
Trust reflects existing Team Operations metadata and confidence.
Explanation confidence mirrors the existing Team Operations confidence metadata.
```

Structured fields used:

```json
{
  "availability_distribution": {
    "available": 0,
    "avoid": 0,
    "limited": 0,
    "monitor": 19,
    "total": 19,
    "unavailable": 0,
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
      "message": "Trust metadata limits the readiness summary.",
      "severity": "caution"
    },
    {
      "affected_area": "coverage_inventory",
      "category": "coverage",
      "constraint_id": "coverage_partial",
      "count": 18,
      "evidence": [
        "missing_workload_data_count: 18",
        "availability_missing_count: 0"
      ],
      "message": "Some active pitcher records have incomplete readiness evidence.",
      "severity": "caution"
    }
  ],
  "coverage_inventory": {
    "active_pitcher_count": 19,
    "availability_covered_count": 19,
    "availability_missing_count": 0,
    "coverage_state": "partial",
    "current_workload_data_count": 1,
    "missing_workload_data_count": 18
  },
  "freshness": {
    "data_through": "2026-06-28",
    "freshness_state": "current",
    "generated_at": "2026-06-30T00:54:01",
    "last_successful_sync": "2026-06-30T00:54:04.076792Z",
    "latest_fatigue_calculated_at": "2026-06-30T00:54:01.265129Z",
    "latest_sync_status": "success",
    "latest_workload_date": "2026-06-28",
    "limitations": [],
    "missing_data_warning": null,
    "stale_warning": null
  },
  "handedness_coverage": {
    "coverage_state": "covered",
    "left_handed_count": 5,
    "limitations": [],
    "right_handed_count": 14,
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
    "generated_at": "2026-06-30T00:54:01",
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
    "elevated_count": 0,
    "latest_workload_date": "2026-06-28",
    "low_count": 0,
    "moderate_count": 1,
    "pressure_state": "unknown",
    "pressure_state_code": "unknown",
    "summary": "Recent workload pressure is partially unknown.",
    "unknown_count": 18
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
      "summary": "Readiness explanation confidence is limited by trust metadata."
    }
  ],
  "primary_reasons": [
    {
      "code": "READINESS_DEGRADED_BY_LIMITATIONS",
      "label": "Readiness degraded by limitations",
      "scope": "readiness_state",
      "summary": "Readiness context is degraded by visible limitations."
    },
    {
      "code": "COVERAGE_PARTIAL",
      "label": "Coverage partial",
      "scope": "coverage_state",
      "summary": "Coverage evidence is partial for the explained state."
    },
    {
      "code": "TRUST_LIMITED",
      "label": "Trust limited",
      "scope": "trust_state",
      "summary": "Trust metadata limits confidence in the explanation."
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
      "value": "unknown"
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
      "value": 0
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
      "value": 18
    },
    {
      "evidence_type": "availability_distribution_available",
      "impact": "explains_availability_state",
      "label": "Available inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 0
    },
    {
      "evidence_type": "availability_distribution_monitor",
      "impact": "explains_availability_state",
      "label": "Monitor inventory count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 19
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
      "value": 1
    },
    {
      "evidence_type": "coverage_inventory_missing_workload_data_count",
      "impact": "explains_coverage_state",
      "label": "Missing workload data count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 18
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
      "value": 5
    },
    {
      "evidence_type": "handedness_coverage_right_handed_count",
      "impact": "explains_coverage_state",
      "label": "Right handed count",
      "source": "team_operations_bullpen_readiness",
      "unit": "pitchers",
      "value": 14
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
        "message": "Trust metadata limits the readiness summary.",
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
        "count": 18,
        "evidence": [
          "missing_workload_data_count: 18",
          "availability_missing_count: 0"
        ],
        "message": "Some active pitcher records have incomplete readiness evidence.",
        "severity": "caution"
      }
    }
  ]
}
```
