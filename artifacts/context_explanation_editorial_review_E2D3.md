# Context Explanation Editorial Review Corpus - E2D-3 Healthy-State Context Explanation Corpus

Read-only export of current Pitcher Context and Team Context explanation copy for E2 Editorial Voice review.

## Export Metadata

```json
{
  "artifact": "artifacts/context_explanation_editorial_review_E2D3.md",
  "before_after_summary": {
    "current_banned_language_status": "warn",
    "current_circular_meta_status": "pass",
    "current_raw_count_formula_status": "warn",
    "current_retired_phrase_status": "warn",
    "disclaimer_preservation_status": "pass",
    "prior_artifact": "artifacts/context_explanation_editorial_review_E2D1.md",
    "prior_artifact_string_counts": {
      "circular_meta_examples": 93,
      "formula_term_examples": 118,
      "raw_arithmetic_examples": 33
    }
  },
  "data_notes": [
    "Current stored team board path returned zero eligible visible pitcher cards for every reviewed team; board card/group examples are documented as real fallback/no-card rows.",
    "Deterministic fixture examples use existing backend test fixture shapes and production helper paths; they are labeled separately from stored data."
  ],
  "example_count": 42,
  "generated_at": "2026-06-30T02:31:19.001100",
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
  "review_label": "E2D-3 Healthy-State Context Explanation Corpus",
  "source_mode": "current stored DB data first; deterministic fixtures fill uncaptured healthy-state categories; exporter starts no sync",
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
  "board_card_groups_found": {
    "Available": 2,
    "Avoid": 1,
    "Limited": 1,
    "Monitor": 1,
    "Unavailable": 1
  },
  "examples_by_source": {
    "deterministic fixture example": 21,
    "stored-data example": 21
  },
  "examples_exported": 42,
  "fixture_backed_examples": 21,
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
    "Clean Option",
    "Limited Read",
    "Rest-Restricted",
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
  "stored_data_examples": 21,
  "team_readiness_states_found": [
    "data_limited",
    "operationally_constrained",
    "operationally_stable",
    "operationally_stressed",
    "refused"
  ],
  "team_shape_read_labels_found": [
    "Heavily Concentrated Workload",
    "High Trust-Lane Pressure",
    "Limited Coverage Safety",
    "Limited Read",
    "Thin Clean Options",
    "Thin Depth Safety",
    "Thin Trust Arm Availability"
  ]
}
```

## Before / After Summary

```json
{
  "current_banned_language_status": "warn",
  "current_circular_meta_status": "pass",
  "current_raw_count_formula_status": "warn",
  "current_retired_phrase_status": "warn",
  "disclaimer_preservation_status": "pass",
  "prior_artifact": "artifacts/context_explanation_editorial_review_E2D1.md",
  "prior_artifact_string_counts": {
    "circular_meta_examples": 93,
    "formula_term_examples": 118,
    "raw_arithmetic_examples": 33
  }
}
```

## Editorial Banned-Language Scan

Status: warn - 20 banned language violation(s) found.

```json
{
  "scope": "rendered public context explanation copy only",
  "status": "warn",
  "violation_count": 20,
  "violations": [
    {
      "category": "editorial_contract_denied_phrase",
      "example_index": 26,
      "match": "Clean Option",
      "pitcher": "Deterministic fixture pitcher - Trust Arm",
      "start": 10,
      "surface_name": "Pitcher public role/read labels",
      "team": "Deterministic Context Fixture (FIX, fixture-context)",
      "term": "clean option"
    },
    {
      "category": "editorial_contract_denied_phrase",
      "example_index": 26,
      "match": "Clean Option",
      "pitcher": "Deterministic fixture pitcher - Trust Arm",
      "start": 10,
      "surface_name": "Pitcher public role/read labels",
      "team": "Deterministic Context Fixture (FIX, fixture-context)",
      "term": "clean options"
    },
    {
      "category": "raw_count_formula",
      "example_index": 32,
      "match": "2 of 6",
      "pitcher": null,
      "start": 30,
      "surface_name": "Team bullpen board context",
      "team": "Deterministic Context Fixture (FIX, fixture-context)",
      "term": "raw arithmetic pattern"
    },
    {
      "category": "raw_count_formula",
      "example_index": 32,
      "match": "2 of 6",
      "pitcher": null,
      "start": 73,
      "surface_name": "Team bullpen board context",
      "team": "Deterministic Context Fixture (FIX, fixture-context)",
      "term": "raw arithmetic pattern"
    },
    {
      "category": "raw_count_formula",
      "example_index": 32,
      "match": "1 of 6",
      "pitcher": null,
      "start": 116,
      "surface_name": "Team bullpen board context",
      "team": "Deterministic Context Fixture (FIX, fixture-context)",
      "term": "raw arithmetic pattern"
    },
    {
      "category": "raw_count_formula",
      "example_index": 33,
      "match": "1 of 1",
      "pitcher": null,
      "start": 28,
      "surface_name": "Team bullpen shape explanations",
      "team": "Deterministic Context Fixture (FIX, fixture-context)",
      "term": "raw arithmetic pattern"
    },
    {
      "category": "editorial_contract_denied_phrase",
      "example_index": 33,
      "match": "Clean Options",
      "pitcher": null,
      "start": 50,
      "surface_name": "Team bullpen shape explanations",
      "team": "Deterministic Context Fixture (FIX, fixture-context)",
      "term": "clean option"
    },
    {
      "category": "editorial_contract_denied_phrase",
      "example_index": 33,
      "match": "Clean Options",
      "pitcher": null,
      "start": 50,
      "surface_name": "Team bullpen shape explanations",
      "team": "Deterministic Context Fixture (FIX, fixture-context)",
      "term": "clean options"
    },
    {
      "category": "editorial_contract_denied_phrase",
      "example_index": 33,
      "match": "Clean Options",
      "pitcher": null,
      "start": 134,
      "surface_name": "Team bullpen shape explanations",
      "team": "Deterministic Context Fixture (FIX, fixture-context)",
      "term": "clean option"
    },
    {
      "category": "editorial_contract_denied_phrase",
      "example_index": 33,
      "match": "Clean Options",
      "pitcher": null,
      "start": 134,
      "surface_name": "Team bullpen shape explanations",
      "team": "Deterministic Context Fixture (FIX, fixture-context)",
      "term": "clean options"
    },
    {
      "category": "editorial_contract_denied_phrase",
      "example_index": 33,
      "match": "Clean Options",
      "pitcher": null,
      "start": 150,
      "surface_name": "Team bullpen shape explanations",
      "team": "Deterministic Context Fixture (FIX, fixture-context)",
      "term": "clean option"
    },
    {
      "category": "editorial_contract_denied_phrase",
      "example_index": 33,
      "match": "Clean Options",
      "pitcher": null,
      "start": 150,
      "surface_name": "Team bullpen shape explanations",
      "team": "Deterministic Context Fixture (FIX, fixture-context)",
      "term": "clean options"
    },
    {
      "category": "raw_count_formula",
      "example_index": 33,
      "match": "84 of 100",
      "pitcher": null,
      "start": 693,
      "surface_name": "Team bullpen shape explanations",
      "team": "Deterministic Context Fixture (FIX, fixture-context)",
      "term": "raw arithmetic pattern"
    },
    {
      "category": "raw_count_formula",
      "example_index": 33,
      "match": "0 of 1",
      "pitcher": null,
      "start": 757,
      "surface_name": "Team bullpen shape explanations",
      "team": "Deterministic Context Fixture (FIX, fixture-context)",
      "term": "raw arithmetic pattern"
    },
    {
      "category": "editorial_contract_denied_phrase",
      "example_index": 33,
      "match": "Clean Options",
      "pitcher": null,
      "start": 782,
      "surface_name": "Team bullpen shape explanations",
      "team": "Deterministic Context Fixture (FIX, fixture-context)",
      "term": "clean option"
    },
    {
      "category": "editorial_contract_denied_phrase",
      "example_index": 33,
      "match": "Clean Options",
      "pitcher": null,
      "start": 782,
      "surface_name": "Team bullpen shape explanations",
      "team": "Deterministic Context Fixture (FIX, fixture-context)",
      "term": "clean options"
    },
    {
      "category": "editorial_contract_denied_phrase",
      "example_index": 33,
      "match": "Clean Options",
      "pitcher": null,
      "start": 918,
      "surface_name": "Team bullpen shape explanations",
      "team": "Deterministic Context Fixture (FIX, fixture-context)",
      "term": "clean option"
    },
    {
      "category": "editorial_contract_denied_phrase",
      "example_index": 33,
      "match": "Clean Options",
      "pitcher": null,
      "start": 918,
      "surface_name": "Team bullpen shape explanations",
      "team": "Deterministic Context Fixture (FIX, fixture-context)",
      "term": "clean options"
    },
    {
      "category": "editorial_contract_denied_phrase",
      "example_index": 34,
      "match": "Clean Option",
      "pitcher": "Fixture Fresh Depth Arm",
      "start": 112,
      "surface_name": "Team bullpen board card labels",
      "team": "Deterministic Context Fixture (FIX, fixture-context)",
      "term": "clean option"
    },
    {
      "category": "editorial_contract_denied_phrase",
      "example_index": 34,
      "match": "Clean Option",
      "pitcher": "Fixture Fresh Depth Arm",
      "start": 112,
      "surface_name": "Team bullpen board card labels",
      "team": "Deterministic Context Fixture (FIX, fixture-context)",
      "term": "clean options"
    }
  ]
}
```

## Retired Phrase Scan

Status: warn - 14 retired phrase violation(s) found.

```json
{
  "scope": "rendered public context explanation copy only",
  "status": "warn",
  "terms": [
    "clean option",
    "clean options",
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
  "violation_count": 14,
  "violations": [
    {
      "category": "editorial_contract_denied_phrase",
      "example_index": 26,
      "match": "Clean Option",
      "pitcher": "Deterministic fixture pitcher - Trust Arm",
      "start": 10,
      "surface_name": "Pitcher public role/read labels",
      "team": "Deterministic Context Fixture (FIX, fixture-context)",
      "term": "clean option"
    },
    {
      "category": "editorial_contract_denied_phrase",
      "example_index": 26,
      "match": "Clean Option",
      "pitcher": "Deterministic fixture pitcher - Trust Arm",
      "start": 10,
      "surface_name": "Pitcher public role/read labels",
      "team": "Deterministic Context Fixture (FIX, fixture-context)",
      "term": "clean options"
    },
    {
      "category": "editorial_contract_denied_phrase",
      "example_index": 33,
      "match": "Clean Options",
      "pitcher": null,
      "start": 50,
      "surface_name": "Team bullpen shape explanations",
      "team": "Deterministic Context Fixture (FIX, fixture-context)",
      "term": "clean option"
    },
    {
      "category": "editorial_contract_denied_phrase",
      "example_index": 33,
      "match": "Clean Options",
      "pitcher": null,
      "start": 50,
      "surface_name": "Team bullpen shape explanations",
      "team": "Deterministic Context Fixture (FIX, fixture-context)",
      "term": "clean options"
    },
    {
      "category": "editorial_contract_denied_phrase",
      "example_index": 33,
      "match": "Clean Options",
      "pitcher": null,
      "start": 134,
      "surface_name": "Team bullpen shape explanations",
      "team": "Deterministic Context Fixture (FIX, fixture-context)",
      "term": "clean option"
    },
    {
      "category": "editorial_contract_denied_phrase",
      "example_index": 33,
      "match": "Clean Options",
      "pitcher": null,
      "start": 134,
      "surface_name": "Team bullpen shape explanations",
      "team": "Deterministic Context Fixture (FIX, fixture-context)",
      "term": "clean options"
    },
    {
      "category": "editorial_contract_denied_phrase",
      "example_index": 33,
      "match": "Clean Options",
      "pitcher": null,
      "start": 150,
      "surface_name": "Team bullpen shape explanations",
      "team": "Deterministic Context Fixture (FIX, fixture-context)",
      "term": "clean option"
    },
    {
      "category": "editorial_contract_denied_phrase",
      "example_index": 33,
      "match": "Clean Options",
      "pitcher": null,
      "start": 150,
      "surface_name": "Team bullpen shape explanations",
      "team": "Deterministic Context Fixture (FIX, fixture-context)",
      "term": "clean options"
    },
    {
      "category": "editorial_contract_denied_phrase",
      "example_index": 33,
      "match": "Clean Options",
      "pitcher": null,
      "start": 782,
      "surface_name": "Team bullpen shape explanations",
      "team": "Deterministic Context Fixture (FIX, fixture-context)",
      "term": "clean option"
    },
    {
      "category": "editorial_contract_denied_phrase",
      "example_index": 33,
      "match": "Clean Options",
      "pitcher": null,
      "start": 782,
      "surface_name": "Team bullpen shape explanations",
      "team": "Deterministic Context Fixture (FIX, fixture-context)",
      "term": "clean options"
    },
    {
      "category": "editorial_contract_denied_phrase",
      "example_index": 33,
      "match": "Clean Options",
      "pitcher": null,
      "start": 918,
      "surface_name": "Team bullpen shape explanations",
      "team": "Deterministic Context Fixture (FIX, fixture-context)",
      "term": "clean option"
    },
    {
      "category": "editorial_contract_denied_phrase",
      "example_index": 33,
      "match": "Clean Options",
      "pitcher": null,
      "start": 918,
      "surface_name": "Team bullpen shape explanations",
      "team": "Deterministic Context Fixture (FIX, fixture-context)",
      "term": "clean options"
    },
    {
      "category": "editorial_contract_denied_phrase",
      "example_index": 34,
      "match": "Clean Option",
      "pitcher": "Fixture Fresh Depth Arm",
      "start": 112,
      "surface_name": "Team bullpen board card labels",
      "team": "Deterministic Context Fixture (FIX, fixture-context)",
      "term": "clean option"
    },
    {
      "category": "editorial_contract_denied_phrase",
      "example_index": 34,
      "match": "Clean Option",
      "pitcher": "Fixture Fresh Depth Arm",
      "start": 112,
      "surface_name": "Team bullpen board card labels",
      "team": "Deterministic Context Fixture (FIX, fixture-context)",
      "term": "clean options"
    }
  ]
}
```

## Raw-Count / Formula Scan

Status: warn - 6 raw-count or formula violation(s) found.

```json
{
  "scope": "rendered public context explanation copy only",
  "status": "warn",
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
  "violation_count": 6,
  "violations": [
    {
      "example_index": 32,
      "match": "2 of 6",
      "pitcher": null,
      "start": 30,
      "surface_name": "Team bullpen board context",
      "team": "Deterministic Context Fixture (FIX, fixture-context)",
      "term": "raw arithmetic pattern"
    },
    {
      "example_index": 32,
      "match": "2 of 6",
      "pitcher": null,
      "start": 73,
      "surface_name": "Team bullpen board context",
      "team": "Deterministic Context Fixture (FIX, fixture-context)",
      "term": "raw arithmetic pattern"
    },
    {
      "example_index": 32,
      "match": "1 of 6",
      "pitcher": null,
      "start": 116,
      "surface_name": "Team bullpen board context",
      "team": "Deterministic Context Fixture (FIX, fixture-context)",
      "term": "raw arithmetic pattern"
    },
    {
      "example_index": 33,
      "match": "1 of 1",
      "pitcher": null,
      "start": 28,
      "surface_name": "Team bullpen shape explanations",
      "team": "Deterministic Context Fixture (FIX, fixture-context)",
      "term": "raw arithmetic pattern"
    },
    {
      "example_index": 33,
      "match": "84 of 100",
      "pitcher": null,
      "start": 693,
      "surface_name": "Team bullpen shape explanations",
      "team": "Deterministic Context Fixture (FIX, fixture-context)",
      "term": "raw arithmetic pattern"
    },
    {
      "example_index": 33,
      "match": "0 of 1",
      "pitcher": null,
      "start": 757,
      "surface_name": "Team bullpen shape explanations",
      "team": "Deterministic Context Fixture (FIX, fixture-context)",
      "term": "raw arithmetic pattern"
    }
  ]
}
```

## Circular-Meta Scan

Status: pass - no circular-meta violations found.

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
    "limited_read_shape": 3,
    "limited_role_context": 6,
    "no_visible_pitcher_cards": 3,
    "rendered": 23
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
    "Pitcher Context modal/detail route": 5,
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
      "Unavailable": 1
    },
    "Pitcher V4 availability explanation": {
      "Available": 1,
      "Avoid": 1,
      "Limited": 1,
      "Monitor": 1,
      "Unavailable": 1
    },
    "Pitcher public role/read labels": {
      "Available": 1,
      "Avoid": 1,
      "Limited": 2,
      "Monitor": 4,
      "Unavailable": 2
    },
    "Team Operations readiness V4 explanation": {
      "current": 1,
      "data_limited": 1,
      "limited": 1,
      "operationally_constrained": 1,
      "operationally_stable": 1,
      "operationally_stressed": 1,
      "refused": 1,
      "unknown": 1,
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
      "elevated": 1,
      "no_data": 3
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
  "example_source": "stored-data example",
  "fallback_status": "freshness_stale",
  "pitcher": "Alek Manoah",
  "raw_count_formula_scan": {
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
  "team": "Los Angeles Angels (LAA, 108)"
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
    "data_through": "2026-03-13",
    "freshness_failure": "stale_workload_data",
    "last_sync_at": null,
    "source_updated_at": "2026-06-29",
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
  "subject_id": "92",
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
  "example_source": "stored-data example",
  "fallback_status": "data_stale",
  "pitcher": "Alek Manoah",
  "raw_count_formula_scan": {
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
  "example_source": "stored-data example",
  "fallback_status": "limited_role_context",
  "pitcher": "Alek Manoah",
  "raw_count_formula_scan": {
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
  "example_source": "stored-data example",
  "fallback_status": "limited_role_context",
  "pitcher": "Ryan Zeferjahn",
  "raw_count_formula_scan": {
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
  "example_source": "stored-data example",
  "fallback_status": "rendered",
  "pitcher": "Brady Singer",
  "raw_count_formula_scan": {
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
  "team": "Cincinnati Reds (CIN, 113)"
}
```

Rendered public copy:
```
A heavy recent stretch has his workload up enough to make him unavailable.
A heavy recent stretch has the workload up.
No injury data available
No team-reported availability data available
The stored workload data is current enough for this pitcher note.
The public workload record is strong enough for this note.
The public workload record is current enough for this note.
```

Structured fields used:

```json
{
  "confidence": {
    "level": "high",
    "summary": "The public workload record is current enough for this note."
  },
  "freshness": {
    "data_through": "2026-06-28",
    "freshness_failure": null,
    "last_sync_at": null,
    "source_updated_at": "2026-06-29",
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
  "subject_id": "21",
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
  "example_source": "stored-data example",
  "fallback_status": "rendered",
  "pitcher": "Brady Singer",
  "raw_count_formula_scan": {
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
  "example_source": "stored-data example",
  "fallback_status": "limited_role_context",
  "pitcher": "Brady Singer",
  "raw_count_formula_scan": {
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
  "example_source": "stored-data example",
  "fallback_status": "rendered",
  "pitcher": "Pierce Johnson",
  "raw_count_formula_scan": {
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
  "team": "Cincinnati Reds (CIN, 113)"
}
```

Rendered public copy:
```
Recent usage points to a lighter lane if he is needed.
A heavy recent stretch has the workload up.
No injury data available
No team-reported availability data available
The stored workload data is current enough for this pitcher note.
The public workload record is strong enough for this note.
The public workload record is current enough for this note.
```

Structured fields used:

```json
{
  "confidence": {
    "level": "high",
    "summary": "The public workload record is current enough for this note."
  },
  "freshness": {
    "data_through": "2026-06-28",
    "freshness_failure": null,
    "last_sync_at": null,
    "source_updated_at": "2026-06-29",
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
  "subject_id": "33",
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
  "example_source": "stored-data example",
  "fallback_status": "rendered",
  "pitcher": "Pierce Johnson",
  "raw_count_formula_scan": {
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
  "example_source": "stored-data example",
  "fallback_status": "limited_role_context",
  "pitcher": "Pierce Johnson",
  "raw_count_formula_scan": {
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
  "example_source": "stored-data example",
  "fallback_status": "no_visible_pitcher_cards",
  "pitcher": null,
  "raw_count_formula_scan": {
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
  "example_source": "stored-data example",
  "fallback_status": "limited_read_shape",
  "pitcher": null,
  "raw_count_formula_scan": {
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
There is not enough recent workload data to read Trust Arm Availability yet. This is a data-limited note, not a statement about injury status or manager intent.
BaseballOS cannot yet say how many rested late-inning arms are ready from the stored data. This is a data-limited note, not a statement about injury status or manager intent.
BaseballOS cannot yet say how much late-inning pressure is on this bullpen from the stored data. This is a data-limited note, not a statement about injury status or manager intent.
No recent relief workload was available in the workload window, so BaseballOS cannot tell whether the same arms are carrying the work.
There is not enough recent workload data to read this bullpen yet. This is a data-limited note, not a statement about injury status or manager intent.
BaseballOS cannot yet say how much room this bullpen has if the starter exits early. This is a data-limited note, not a statement about injury status or manager intent.
There is not enough recent workload data to read Depth Safety yet. This is a data-limited note, not a statement about injury status or manager intent.
```

Structured fields used:

```json
{
  "reads": [
    {
      "explanation": "There is not enough recent workload data to read Trust Arm Availability yet. This is a data-limited note, not a statement about injury status or manager intent.",
      "key": "trustAvailability",
      "label": "Limited Read",
      "reasons": [
        "There is not enough recent workload data to read Trust Arm Availability yet. This is a data-limited note, not a statement about injury status or manager intent."
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
      "explanation": "BaseballOS cannot yet say how many rested late-inning arms are ready from the stored data. This is a data-limited note, not a statement about injury status or manager intent.",
      "key": "cleanOptions",
      "label": "Limited Read",
      "reasons": [
        "BaseballOS cannot yet say how many rested late-inning arms are ready from the stored data. This is a data-limited note, not a statement about injury status or manager intent."
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
      "explanation": "BaseballOS cannot yet say how much late-inning pressure is on this bullpen from the stored data. This is a data-limited note, not a statement about injury status or manager intent.",
      "key": "bullpenPressure",
      "label": "Limited Read",
      "reasons": [
        "BaseballOS cannot yet say how much late-inning pressure is on this bullpen from the stored data. This is a data-limited note, not a statement about injury status or manager intent."
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
      "explanation": "There is not enough recent workload data to read this bullpen yet. This is a data-limited note, not a statement about injury status or manager intent.",
      "key": "coverageSafety",
      "label": "Limited Read",
      "limitations": [
        "There is not enough stored bullpen context to read multi-inning coverage yet."
      ],
      "reasons": [
        "BaseballOS cannot yet say how much room this bullpen has if the starter exits early. This is a data-limited note, not a statement about injury status or manager intent."
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
      "explanation": "There is not enough recent workload data to read Depth Safety yet. This is a data-limited note, not a statement about injury status or manager intent.",
      "key": "depthSafety",
      "label": "Limited Read",
      "reasons": [
        "There is not enough recent workload data to read Depth Safety yet. This is a data-limited note, not a statement about injury status or manager intent."
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
  "example_source": "stored-data example",
  "fallback_status": "no_visible_pitcher_cards",
  "pitcher": null,
  "raw_count_formula_scan": {
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
  "example_source": "stored-data example",
  "fallback_status": "limited_read_shape",
  "pitcher": null,
  "raw_count_formula_scan": {
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
There is not enough recent workload data to read Trust Arm Availability yet. This is a data-limited note, not a statement about injury status or manager intent.
BaseballOS cannot yet say how many rested late-inning arms are ready from the stored data. This is a data-limited note, not a statement about injury status or manager intent.
BaseballOS cannot yet say how much late-inning pressure is on this bullpen from the stored data. This is a data-limited note, not a statement about injury status or manager intent.
No recent relief workload was available in the workload window, so BaseballOS cannot tell whether the same arms are carrying the work.
There is not enough recent workload data to read this bullpen yet. This is a data-limited note, not a statement about injury status or manager intent.
BaseballOS cannot yet say how much room this bullpen has if the starter exits early. This is a data-limited note, not a statement about injury status or manager intent.
There is not enough recent workload data to read Depth Safety yet. This is a data-limited note, not a statement about injury status or manager intent.
```

Structured fields used:

```json
{
  "reads": [
    {
      "explanation": "There is not enough recent workload data to read Trust Arm Availability yet. This is a data-limited note, not a statement about injury status or manager intent.",
      "key": "trustAvailability",
      "label": "Limited Read",
      "reasons": [
        "There is not enough recent workload data to read Trust Arm Availability yet. This is a data-limited note, not a statement about injury status or manager intent."
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
      "explanation": "BaseballOS cannot yet say how many rested late-inning arms are ready from the stored data. This is a data-limited note, not a statement about injury status or manager intent.",
      "key": "cleanOptions",
      "label": "Limited Read",
      "reasons": [
        "BaseballOS cannot yet say how many rested late-inning arms are ready from the stored data. This is a data-limited note, not a statement about injury status or manager intent."
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
      "explanation": "BaseballOS cannot yet say how much late-inning pressure is on this bullpen from the stored data. This is a data-limited note, not a statement about injury status or manager intent.",
      "key": "bullpenPressure",
      "label": "Limited Read",
      "reasons": [
        "BaseballOS cannot yet say how much late-inning pressure is on this bullpen from the stored data. This is a data-limited note, not a statement about injury status or manager intent."
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
      "explanation": "There is not enough recent workload data to read this bullpen yet. This is a data-limited note, not a statement about injury status or manager intent.",
      "key": "coverageSafety",
      "label": "Limited Read",
      "limitations": [
        "There is not enough stored bullpen context to read multi-inning coverage yet."
      ],
      "reasons": [
        "BaseballOS cannot yet say how much room this bullpen has if the starter exits early. This is a data-limited note, not a statement about injury status or manager intent."
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
      "explanation": "There is not enough recent workload data to read Depth Safety yet. This is a data-limited note, not a statement about injury status or manager intent.",
      "key": "depthSafety",
      "label": "Limited Read",
      "reasons": [
        "There is not enough recent workload data to read Depth Safety yet. This is a data-limited note, not a statement about injury status or manager intent."
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
  "example_source": "stored-data example",
  "fallback_status": "no_visible_pitcher_cards",
  "pitcher": null,
  "raw_count_formula_scan": {
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
  "example_source": "stored-data example",
  "fallback_status": "limited_read_shape",
  "pitcher": null,
  "raw_count_formula_scan": {
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
There is not enough recent workload data to read Trust Arm Availability yet. This is a data-limited note, not a statement about injury status or manager intent.
BaseballOS cannot yet say how many rested late-inning arms are ready from the stored data. This is a data-limited note, not a statement about injury status or manager intent.
BaseballOS cannot yet say how much late-inning pressure is on this bullpen from the stored data. This is a data-limited note, not a statement about injury status or manager intent.
No recent relief workload was available in the workload window, so BaseballOS cannot tell whether the same arms are carrying the work.
There is not enough recent workload data to read this bullpen yet. This is a data-limited note, not a statement about injury status or manager intent.
BaseballOS cannot yet say how much room this bullpen has if the starter exits early. This is a data-limited note, not a statement about injury status or manager intent.
There is not enough recent workload data to read Depth Safety yet. This is a data-limited note, not a statement about injury status or manager intent.
```

Structured fields used:

```json
{
  "reads": [
    {
      "explanation": "There is not enough recent workload data to read Trust Arm Availability yet. This is a data-limited note, not a statement about injury status or manager intent.",
      "key": "trustAvailability",
      "label": "Limited Read",
      "reasons": [
        "There is not enough recent workload data to read Trust Arm Availability yet. This is a data-limited note, not a statement about injury status or manager intent."
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
      "explanation": "BaseballOS cannot yet say how many rested late-inning arms are ready from the stored data. This is a data-limited note, not a statement about injury status or manager intent.",
      "key": "cleanOptions",
      "label": "Limited Read",
      "reasons": [
        "BaseballOS cannot yet say how many rested late-inning arms are ready from the stored data. This is a data-limited note, not a statement about injury status or manager intent."
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
      "explanation": "BaseballOS cannot yet say how much late-inning pressure is on this bullpen from the stored data. This is a data-limited note, not a statement about injury status or manager intent.",
      "key": "bullpenPressure",
      "label": "Limited Read",
      "reasons": [
        "BaseballOS cannot yet say how much late-inning pressure is on this bullpen from the stored data. This is a data-limited note, not a statement about injury status or manager intent."
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
      "explanation": "There is not enough recent workload data to read this bullpen yet. This is a data-limited note, not a statement about injury status or manager intent.",
      "key": "coverageSafety",
      "label": "Limited Read",
      "limitations": [
        "There is not enough stored bullpen context to read multi-inning coverage yet."
      ],
      "reasons": [
        "BaseballOS cannot yet say how much room this bullpen has if the starter exits early. This is a data-limited note, not a statement about injury status or manager intent."
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
      "explanation": "There is not enough recent workload data to read Depth Safety yet. This is a data-limited note, not a statement about injury status or manager intent.",
      "key": "depthSafety",
      "label": "Limited Read",
      "reasons": [
        "There is not enough recent workload data to read Depth Safety yet. This is a data-limited note, not a statement about injury status or manager intent."
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
  "example_source": "stored-data example",
  "fallback_status": "data_limited",
  "pitcher": null,
  "raw_count_formula_scan": {
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
  "team": "Los Angeles Angels (LAA, 108)"
}
```

Rendered public copy:
```
The public data is not strong enough to give this team a full bullpen readiness note.
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
      "message": "The public workload record is not strong enough for a full readiness summary.",
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
  "example_source": "stored-data example",
  "fallback_status": "data_limited",
  "pitcher": null,
  "raw_count_formula_scan": {
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
  "status": "unknown",
  "surface_name": "Team Operations readiness V4 explanation",
  "team": "Los Angeles Angels (LAA, 108)"
}
```

Rendered public copy:
```
This note focuses on whether recent workload is pressing on the bullpen.
The public data is not strong enough to give this team a full bullpen readiness note.
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
      "message": "The public workload record is not strong enough for a full readiness summary.",
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
  "example_source": "stored-data example",
  "fallback_status": "data_limited",
  "pitcher": null,
  "raw_count_formula_scan": {
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
  "team": "Los Angeles Angels (LAA, 108)"
}
```

Rendered public copy:
```
This note focuses on whether the public data can describe bullpen coverage.
The public data is not strong enough to give this team a full bullpen readiness note.
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
      "message": "The public workload record is not strong enough for a full readiness summary.",
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
  "example_source": "stored-data example",
  "fallback_status": "data_limited",
  "pitcher": null,
  "raw_count_formula_scan": {
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
  "team": "Los Angeles Angels (LAA, 108)"
}
```

Rendered public copy:
```
This note focuses on how current the stored workload data is.
The public data is not strong enough to give this team a full bullpen readiness note.
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
      "message": "The public workload record is not strong enough for a full readiness summary.",
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
  "example_source": "stored-data example",
  "fallback_status": "data_limited",
  "pitcher": null,
  "raw_count_formula_scan": {
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
  "team": "Los Angeles Angels (LAA, 108)"
}
```

Rendered public copy:
```
This note focuses on how much the public workload record can support.
The public data is not strong enough to give this team a full bullpen readiness note.
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
      "message": "The public workload record is not strong enough for a full readiness summary.",
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

### Example 22: Pitcher V4 availability explanation

Metadata:

```json
{
  "banned_language_scan": {
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
  "example_source": "deterministic fixture example",
  "fallback_status": "rendered",
  "pitcher": "Deterministic fixture pitcher - Available",
  "raw_count_formula_scan": {
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
  "source_path": "backend/tests/test_v4_availability_explanation_integration.py fixture pattern -> services.availability.classify_availability -> explanations.availability.serialize_availability_explanation",
  "status": "Available",
  "surface_name": "Pitcher V4 availability explanation",
  "team": "Deterministic Context Fixture (FIX, fixture-context)"
}
```

Rendered public copy:
```
He has no workload from yesterday in the stored data.
No injury data available
No team-reported availability data available
The stored workload data is current enough for this pitcher note.
The public workload record is strong enough for this note.
The public workload record is current enough for this note.
```

Structured fields used:

```json
{
  "confidence": {
    "level": "high",
    "summary": "The public workload record is current enough for this note."
  },
  "freshness": {
    "data_through": "2026-05-29",
    "freshness_failure": null,
    "last_sync_at": null,
    "source_updated_at": "2026-06-01",
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
  "subject_id": "fixture:1",
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
      "value": 20.0
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
      "value": 8
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
      "value": 3
    }
  ]
}
```

### Example 23: Pitcher Context modal/detail route

Metadata:

```json
{
  "banned_language_scan": {
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
  "example_source": "deterministic fixture example",
  "fallback_status": "rendered",
  "pitcher": "Deterministic fixture pitcher - Available",
  "raw_count_formula_scan": {
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
  "status": "Available",
  "surface_name": "Pitcher Context modal/detail route",
  "team": "Deterministic Context Fixture (FIX, fixture-context)"
}
```

Rendered public copy:
```
Available
No injury data available
No team-reported availability data available
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
      "days_rest": 3,
      "fatigue_risk_level": "LOW",
      "fatigue_score": 20.0,
      "four_in_five": false,
      "freshness_state": "fresh",
      "latest_game_date": "2026-05-29",
      "pitches_last_3_days": 0,
      "pitches_last_5_days": 8,
      "pitches_yesterday": 0,
      "reference_date": "2026-06-01",
      "three_in_four": false
    },
    "limitations": [
      "No injury data available",
      "No team-reported availability data available"
    ],
    "reasons": []
  },
  "freshness": {},
  "roster_status": {},
  "workload_signal": {
    "availability_status": "Available",
    "confidence": "high",
    "data_state": "fresh",
    "inputs": {
      "appearances_last_3_days": 0,
      "appearances_last_5_days": 1,
      "back_to_back": false,
      "days_rest": 3,
      "fatigue_risk_level": "LOW",
      "fatigue_score": 20.0,
      "four_in_five": false,
      "freshness_state": "fresh",
      "latest_game_date": "2026-05-29",
      "pitches_last_3_days": 0,
      "pitches_last_5_days": 8,
      "pitches_yesterday": 0,
      "reference_date": "2026-06-01",
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
  "fatigue_trend_points": 0,
  "last_workload_appearance": {
    "game_date": "2026-05-29",
    "pitches": 8
  },
  "recent_logs_reviewed": 1
}
```

### Example 24: Pitcher V4 availability explanation

Metadata:

```json
{
  "banned_language_scan": {
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
  "example_source": "deterministic fixture example",
  "fallback_status": "rendered",
  "pitcher": "Deterministic fixture pitcher - Avoid",
  "raw_count_formula_scan": {
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
  "source_path": "backend/tests/test_v4_availability_explanation_integration.py fixture pattern -> services.availability.classify_availability -> explanations.availability.serialize_availability_explanation",
  "status": "Avoid",
  "surface_name": "Pitcher V4 availability explanation",
  "team": "Deterministic Context Fixture (FIX, fixture-context)"
}
```

Rendered public copy:
```
Recent usage is heavy enough that BaseballOS is holding this as a rest-risk note.
A heavy recent stretch has the workload up.
No injury data available
No team-reported availability data available
The stored workload data is current enough for this pitcher note.
The public workload record is strong enough for this note.
The public workload record is current enough for this note.
```

Structured fields used:

```json
{
  "confidence": {
    "level": "high",
    "summary": "The public workload record is current enough for this note."
  },
  "freshness": {
    "data_through": "2026-05-31",
    "freshness_failure": null,
    "last_sync_at": null,
    "source_updated_at": "2026-06-01",
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
  "subject_id": "fixture:4",
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
      "value": 30.0
    },
    {
      "evidence_type": "availability_pitches_yesterday",
      "impact": "explains_availability_state",
      "label": "Pitches yesterday",
      "source": "availability_engine_v1",
      "unit": "pitches",
      "value": 42
    },
    {
      "evidence_type": "availability_pitches_last_3_days",
      "impact": "explains_availability_state",
      "label": "Pitches in 3 days",
      "source": "availability_engine_v1",
      "unit": "pitches",
      "value": 42
    },
    {
      "evidence_type": "availability_pitches_last_5_days",
      "impact": "explains_availability_state",
      "label": "Pitches in 5 days",
      "source": "availability_engine_v1",
      "unit": "pitches",
      "value": 42
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

### Example 25: Pitcher Context modal/detail route

Metadata:

```json
{
  "banned_language_scan": {
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
  "example_source": "deterministic fixture example",
  "fallback_status": "rendered",
  "pitcher": "Deterministic fixture pitcher - Avoid",
  "raw_count_formula_scan": {
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
  "status": "Avoid",
  "surface_name": "Pitcher Context modal/detail route",
  "team": "Deterministic Context Fixture (FIX, fixture-context)"
}
```

Rendered public copy:
```
Avoid
42 pitches yesterday
42 pitches in 3 days
Only 1 day of rest
No injury data available
No team-reported availability data available
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
      "fatigue_risk_level": "LOW",
      "fatigue_score": 30.0,
      "four_in_five": false,
      "freshness_state": "fresh",
      "latest_game_date": "2026-05-31",
      "pitches_last_3_days": 42,
      "pitches_last_5_days": 42,
      "pitches_yesterday": 42,
      "reference_date": "2026-06-01",
      "three_in_four": false
    },
    "limitations": [
      "No injury data available",
      "No team-reported availability data available"
    ],
    "reasons": [
      "42 pitches yesterday",
      "42 pitches in 3 days",
      "Only 1 day of rest"
    ]
  },
  "freshness": {},
  "roster_status": {},
  "workload_signal": {
    "availability_status": "Avoid",
    "confidence": "high",
    "data_state": "fresh",
    "inputs": {
      "appearances_last_3_days": 1,
      "appearances_last_5_days": 1,
      "back_to_back": false,
      "days_rest": 1,
      "fatigue_risk_level": "LOW",
      "fatigue_score": 30.0,
      "four_in_five": false,
      "freshness_state": "fresh",
      "latest_game_date": "2026-05-31",
      "pitches_last_3_days": 42,
      "pitches_last_5_days": 42,
      "pitches_yesterday": 42,
      "reference_date": "2026-06-01",
      "three_in_four": false
    },
    "limitations": [
      "No injury data available",
      "No team-reported availability data available"
    ],
    "reasons": [
      "42 pitches yesterday",
      "42 pitches in 3 days",
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
    "pitches": 42
  },
  "recent_logs_reviewed": 1
}
```

### Example 26: Pitcher public role/read labels

Metadata:

```json
{
  "banned_language_scan": {
    "status": "warn",
    "violation_count": 2,
    "violations": [
      {
        "category": "editorial_contract_denied_phrase",
        "match": "Clean Option",
        "start": 10,
        "term": "clean option"
      },
      {
        "category": "editorial_contract_denied_phrase",
        "match": "Clean Option",
        "start": 10,
        "term": "clean options"
      }
    ]
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
  "example_source": "deterministic fixture example",
  "fallback_status": "rendered",
  "pitcher": "Deterministic fixture pitcher - Trust Arm",
  "raw_count_formula_scan": {
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
    "status": "warn",
    "terms": [
      "clean option",
      "clean options",
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
    "violation_count": 2,
    "violations": [
      {
        "category": "editorial_contract_denied_phrase",
        "match": "Clean Option",
        "start": 10,
        "term": "clean option"
      },
      {
        "category": "editorial_contract_denied_phrase",
        "match": "Clean Option",
        "start": 10,
        "term": "clean options"
      }
    ]
  },
  "role_or_classification": {
    "read": "Clean Option",
    "role": "Trust Arm"
  },
  "source_path": "backend/tests/test_team_bullpen_shape.py role fixture pattern -> services.pitcher_public_labels.build_pitcher_labels",
  "status": "Available",
  "surface_name": "Pitcher public role/read labels",
  "team": "Deterministic Context Fixture (FIX, fixture-context)"
}
```

Rendered public copy:
```
Trust Arm
Clean Option
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
      "label": "Clean Option",
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

### Example 27: Pitcher public role/read labels

Metadata:

```json
{
  "banned_language_scan": {
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
  "example_source": "deterministic fixture example",
  "fallback_status": "rendered",
  "pitcher": "Deterministic fixture pitcher - Bridge Arm",
  "raw_count_formula_scan": {
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
  "team": "Deterministic Context Fixture (FIX, fixture-context)"
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

### Example 28: Pitcher public role/read labels

Metadata:

```json
{
  "banned_language_scan": {
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
  "example_source": "deterministic fixture example",
  "fallback_status": "rendered",
  "pitcher": "Deterministic fixture pitcher - Coverage Arm",
  "raw_count_formula_scan": {
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
  "team": "Deterministic Context Fixture (FIX, fixture-context)"
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

### Example 29: Pitcher public role/read labels

Metadata:

```json
{
  "banned_language_scan": {
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
  "example_source": "deterministic fixture example",
  "fallback_status": "rendered",
  "pitcher": "Deterministic fixture pitcher - Depth Arm",
  "raw_count_formula_scan": {
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
  "team": "Deterministic Context Fixture (FIX, fixture-context)"
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

### Example 30: Pitcher public role/read labels

Metadata:

```json
{
  "banned_language_scan": {
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
  "example_source": "deterministic fixture example",
  "fallback_status": "limited_role_context",
  "pitcher": "Deterministic fixture pitcher - Limited Read",
  "raw_count_formula_scan": {
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
  "team": "Deterministic Context Fixture (FIX, fixture-context)"
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

### Example 31: Pitcher public role/read labels

Metadata:

```json
{
  "banned_language_scan": {
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
  "example_source": "deterministic fixture example",
  "fallback_status": "limited_role_context",
  "pitcher": "Deterministic fixture pitcher - Limited Read label",
  "raw_count_formula_scan": {
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
  "team": "Deterministic Context Fixture (FIX, fixture-context)"
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

### Example 32: Team bullpen board context

Metadata:

```json
{
  "banned_language_scan": {
    "status": "warn",
    "violation_count": 3,
    "violations": [
      {
        "category": "raw_count_formula",
        "match": "2 of 6",
        "start": 30,
        "term": "raw arithmetic pattern"
      },
      {
        "category": "raw_count_formula",
        "match": "2 of 6",
        "start": 73,
        "term": "raw arithmetic pattern"
      },
      {
        "category": "raw_count_formula",
        "match": "1 of 6",
        "start": 116,
        "term": "raw arithmetic pattern"
      }
    ]
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
  "example_source": "deterministic fixture example",
  "fallback_status": "rendered",
  "pitcher": null,
  "raw_count_formula_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "warn",
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
    "violation_count": 3,
    "violations": [
      {
        "example_index": 1,
        "match": "2 of 6",
        "pitcher": null,
        "start": 30,
        "surface_name": "Team bullpen board context",
        "team": "Deterministic Context Fixture (FIX, fixture-context)",
        "term": "raw arithmetic pattern"
      },
      {
        "example_index": 1,
        "match": "2 of 6",
        "pitcher": null,
        "start": 73,
        "surface_name": "Team bullpen board context",
        "team": "Deterministic Context Fixture (FIX, fixture-context)",
        "term": "raw arithmetic pattern"
      },
      {
        "example_index": 1,
        "match": "1 of 6",
        "pitcher": null,
        "start": 116,
        "surface_name": "Team bullpen board context",
        "team": "Deterministic Context Fixture (FIX, fixture-context)",
        "term": "raw arithmetic pattern"
      }
    ]
  },
  "retired_phrase_scan": {
    "status": "pass",
    "terms": [
      "clean option",
      "clean options",
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
  "team": "Deterministic Context Fixture (FIX, fixture-context)"
}
```

Rendered public copy:
```
Bullpen workload is elevated.
2 of 6 relievers are classified Available.
2 of 6 relievers are Avoid or Unavailable.
1 of 6 relievers are in the Monitor group.
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
        "2 of 6 relievers are classified Available.",
        "2 of 6 relievers are Avoid or Unavailable.",
        "1 of 6 relievers are in the Monitor group.",
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

### Example 33: Team bullpen shape explanations

Metadata:

```json
{
  "banned_language_scan": {
    "status": "warn",
    "violation_count": 13,
    "violations": [
      {
        "category": "raw_count_formula",
        "match": "1 of 1",
        "start": 28,
        "term": "raw arithmetic pattern"
      },
      {
        "category": "editorial_contract_denied_phrase",
        "match": "Clean Options",
        "start": 50,
        "term": "clean option"
      },
      {
        "category": "editorial_contract_denied_phrase",
        "match": "Clean Options",
        "start": 50,
        "term": "clean options"
      },
      {
        "category": "editorial_contract_denied_phrase",
        "match": "Clean Options",
        "start": 134,
        "term": "clean option"
      },
      {
        "category": "editorial_contract_denied_phrase",
        "match": "Clean Options",
        "start": 134,
        "term": "clean options"
      },
      {
        "category": "editorial_contract_denied_phrase",
        "match": "Clean Options",
        "start": 150,
        "term": "clean option"
      },
      {
        "category": "editorial_contract_denied_phrase",
        "match": "Clean Options",
        "start": 150,
        "term": "clean options"
      },
      {
        "category": "raw_count_formula",
        "match": "84 of 100",
        "start": 693,
        "term": "raw arithmetic pattern"
      },
      {
        "category": "raw_count_formula",
        "match": "0 of 1",
        "start": 757,
        "term": "raw arithmetic pattern"
      },
      {
        "category": "editorial_contract_denied_phrase",
        "match": "Clean Options",
        "start": 782,
        "term": "clean option"
      },
      {
        "category": "editorial_contract_denied_phrase",
        "match": "Clean Options",
        "start": 782,
        "term": "clean options"
      },
      {
        "category": "editorial_contract_denied_phrase",
        "match": "Clean Options",
        "start": 918,
        "term": "clean option"
      },
      {
        "category": "editorial_contract_denied_phrase",
        "match": "Clean Options",
        "start": 918,
        "term": "clean options"
      }
    ]
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
  "example_source": "deterministic fixture example",
  "fallback_status": "rendered",
  "pitcher": null,
  "raw_count_formula_scan": {
    "scope": "rendered public context explanation copy only",
    "status": "warn",
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
    "violation_count": 3,
    "violations": [
      {
        "example_index": 1,
        "match": "1 of 1",
        "pitcher": null,
        "start": 28,
        "surface_name": "Team bullpen shape explanations",
        "team": "Deterministic Context Fixture (FIX, fixture-context)",
        "term": "raw arithmetic pattern"
      },
      {
        "example_index": 1,
        "match": "84 of 100",
        "pitcher": null,
        "start": 693,
        "surface_name": "Team bullpen shape explanations",
        "team": "Deterministic Context Fixture (FIX, fixture-context)",
        "term": "raw arithmetic pattern"
      },
      {
        "example_index": 1,
        "match": "0 of 1",
        "pitcher": null,
        "start": 757,
        "surface_name": "Team bullpen shape explanations",
        "team": "Deterministic Context Fixture (FIX, fixture-context)",
        "term": "raw arithmetic pattern"
      }
    ]
  },
  "retired_phrase_scan": {
    "status": "warn",
    "terms": [
      "clean option",
      "clean options",
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
    "violation_count": 10,
    "violations": [
      {
        "category": "editorial_contract_denied_phrase",
        "match": "Clean Options",
        "start": 50,
        "term": "clean option"
      },
      {
        "category": "editorial_contract_denied_phrase",
        "match": "Clean Options",
        "start": 50,
        "term": "clean options"
      },
      {
        "category": "editorial_contract_denied_phrase",
        "match": "Clean Options",
        "start": 134,
        "term": "clean option"
      },
      {
        "category": "editorial_contract_denied_phrase",
        "match": "Clean Options",
        "start": 134,
        "term": "clean options"
      },
      {
        "category": "editorial_contract_denied_phrase",
        "match": "Clean Options",
        "start": 150,
        "term": "clean option"
      },
      {
        "category": "editorial_contract_denied_phrase",
        "match": "Clean Options",
        "start": 150,
        "term": "clean options"
      },
      {
        "category": "editorial_contract_denied_phrase",
        "match": "Clean Options",
        "start": 782,
        "term": "clean option"
      },
      {
        "category": "editorial_contract_denied_phrase",
        "match": "Clean Options",
        "start": 782,
        "term": "clean options"
      },
      {
        "category": "editorial_contract_denied_phrase",
        "match": "Clean Options",
        "start": 918,
        "term": "clean option"
      },
      {
        "category": "editorial_contract_denied_phrase",
        "match": "Clean Options",
        "start": 918,
        "term": "clean options"
      }
    ]
  },
  "role_or_classification": {
    "read_labels": [
      "Thin Trust Arm Availability",
      "Thin Clean Options",
      "High Trust-Lane Pressure",
      "Heavily Concentrated Workload",
      "Limited Coverage Safety",
      "Thin Depth Safety"
    ]
  },
  "source_path": "services.team_bullpen_shape.build_team_bullpen_shape",
  "status": "team_shape",
  "surface_name": "Team bullpen shape explanations",
  "team": "Deterministic Context Fixture (FIX, fixture-context)"
}
```

Rendered public copy:
```
Thin Trust Arm Availability
1 of 1 Trust Arms are Clean Options; 0 are Watch Arms, 0 are Rest-Restricted, and 0 are Unavailable.
Thin Clean Options
2 Clean Options out of 5 active bullpen arms - 1 Trust, 0 Bridge, 0 Coverage, 1 Depth, with 2 Rest-Restricted and 1 Unavailable. Interpretation weighs clean Trust Arms above clean Depth Arms.
High Trust-Lane Pressure
Trust Arms show 1 clean, 0 Rest-Restricted, and 0 Unavailable; 0 Bridge Arms and 1 Coverage Arms are stressed, and 0 arms are carrying heavy recent workload. Late-inning pressure weighs Trust and Bridge Arm stress above Depth Arm stress.
Heavily Concentrated Workload
The top 3 relief arms carried 84% of recent relief pitches (84 of 100) across 5 participating arms.
Limited Coverage Safety
0 of 1 Coverage Arms are Clean Options; 0 are Watch Arms, 1 are Rest-Restricted, and 0 are Unavailable.
Thin Depth Safety
3 Depth Arms in a 6-arm bullpen; 1 are Clean Options or Watch Arms, 1 are Rest-Restricted, and 1 are Unavailable.
```

Structured fields used:

```json
{
  "reads": [
    {
      "explanation": "1 of 1 Trust Arms are Clean Options; 0 are Watch Arms, 0 are Rest-Restricted, and 0 are Unavailable.",
      "key": "trustAvailability",
      "label": "Thin Trust Arm Availability",
      "reasons": [
        "1 of 1 Trust Arms are Clean Options; 0 are Watch Arms, 0 are Rest-Restricted, and 0 are Unavailable."
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
      "explanation": "2 Clean Options out of 5 active bullpen arms - 1 Trust, 0 Bridge, 0 Coverage, 1 Depth, with 2 Rest-Restricted and 1 Unavailable. Interpretation weighs clean Trust Arms above clean Depth Arms.",
      "key": "cleanOptions",
      "label": "Thin Clean Options",
      "reasons": [
        "2 Clean Options out of 5 active bullpen arms - 1 Trust, 0 Bridge, 0 Coverage, 1 Depth, with 2 Rest-Restricted and 1 Unavailable. Interpretation weighs clean Trust Arms above clean Depth Arms."
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
      "explanation": "Trust Arms show 1 clean, 0 Rest-Restricted, and 0 Unavailable; 0 Bridge Arms and 1 Coverage Arms are stressed, and 0 arms are carrying heavy recent workload. Late-inning pressure weighs Trust and Bridge Arm stress above Depth Arm stress.",
      "key": "bullpenPressure",
      "label": "High Trust-Lane Pressure",
      "reasons": [
        "Trust Arms show 1 clean, 0 Rest-Restricted, and 0 Unavailable; 0 Bridge Arms and 1 Coverage Arms are stressed, and 0 arms are carrying heavy recent workload. Late-inning pressure weighs Trust and Bridge Arm stress above Depth Arm stress."
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
      "explanation": "The top 3 relief arms carried 84% of recent relief pitches (84 of 100) across 5 participating arms.",
      "key": "workloadConcentration",
      "label": "Heavily Concentrated Workload",
      "reasons": [
        "The top 3 relief arms carried 84% of recent relief pitches (84 of 100) across 5 participating arms."
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
      "explanation": "0 of 1 Coverage Arms are Clean Options; 0 are Watch Arms, 1 are Rest-Restricted, and 0 are Unavailable.",
      "key": "coverageSafety",
      "label": "Limited Coverage Safety",
      "reasons": [
        "0 of 1 Coverage Arms are Clean Options; 0 are Watch Arms, 1 are Rest-Restricted, and 0 are Unavailable."
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
      "explanation": "3 Depth Arms in a 6-arm bullpen; 1 are Clean Options or Watch Arms, 1 are Rest-Restricted, and 1 are Unavailable.",
      "key": "depthSafety",
      "label": "Thin Depth Safety",
      "reasons": [
        "3 Depth Arms in a 6-arm bullpen; 1 are Clean Options or Watch Arms, 1 are Rest-Restricted, and 1 are Unavailable."
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

### Example 34: Team bullpen board card labels

Metadata:

```json
{
  "banned_language_scan": {
    "status": "warn",
    "violation_count": 2,
    "violations": [
      {
        "category": "editorial_contract_denied_phrase",
        "match": "Clean Option",
        "start": 112,
        "term": "clean option"
      },
      {
        "category": "editorial_contract_denied_phrase",
        "match": "Clean Option",
        "start": 112,
        "term": "clean options"
      }
    ]
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
  "example_source": "deterministic fixture example",
  "fallback_status": "rendered",
  "pitcher": "Fixture Fresh Depth Arm",
  "raw_count_formula_scan": {
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
    "status": "warn",
    "terms": [
      "clean option",
      "clean options",
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
    "violation_count": 2,
    "violations": [
      {
        "category": "editorial_contract_denied_phrase",
        "match": "Clean Option",
        "start": 112,
        "term": "clean option"
      },
      {
        "category": "editorial_contract_denied_phrase",
        "match": "Clean Option",
        "start": 112,
        "term": "clean options"
      }
    ]
  },
  "role_or_classification": {
    "group": "Available",
    "read": "Clean Option",
    "role": "Depth Arm"
  },
  "source_path": "services.bullpen_board.build_board_payload -> services.pitcher_public_labels.build_pitcher_labels",
  "status": "Available",
  "surface_name": "Team bullpen board card labels",
  "team": "Deterministic Context Fixture (FIX, fixture-context)"
}
```

Rendered public copy:
```
Available
Workload signals are inside normal ranges in the latest completed data.
Low recent workload
Depth Arm
Clean Option
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
        "label": "Clean Option",
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

### Example 35: Team bullpen board card labels

Metadata:

```json
{
  "banned_language_scan": {
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
  "example_source": "deterministic fixture example",
  "fallback_status": "rendered",
  "pitcher": "Fixture Bridge Arm",
  "raw_count_formula_scan": {
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
  "team": "Deterministic Context Fixture (FIX, fixture-context)"
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

### Example 36: Team bullpen board card labels

Metadata:

```json
{
  "banned_language_scan": {
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
  "example_source": "deterministic fixture example",
  "fallback_status": "rendered",
  "pitcher": "Fixture Coverage Arm",
  "raw_count_formula_scan": {
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
  "team": "Deterministic Context Fixture (FIX, fixture-context)"
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

### Example 37: Team bullpen board card labels

Metadata:

```json
{
  "banned_language_scan": {
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
  "example_source": "deterministic fixture example",
  "fallback_status": "rendered",
  "pitcher": "Fixture Depth Arm",
  "raw_count_formula_scan": {
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
  "team": "Deterministic Context Fixture (FIX, fixture-context)"
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

### Example 38: Team bullpen board card labels

Metadata:

```json
{
  "banned_language_scan": {
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
  "example_source": "deterministic fixture example",
  "fallback_status": "rendered",
  "pitcher": "Fixture Unavailable Arm",
  "raw_count_formula_scan": {
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
  "team": "Deterministic Context Fixture (FIX, fixture-context)"
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

### Example 39: Team Operations readiness V4 explanation

Metadata:

```json
{
  "banned_language_scan": {
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
  "example_source": "deterministic fixture example",
  "fallback_status": "rendered",
  "pitcher": null,
  "raw_count_formula_scan": {
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
  "team": "Deterministic Context Fixture (FIX, fixture-context)"
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
The public workload record is strong enough for this team note.
The public workload record is strong enough for this note.
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

### Example 40: Team Operations readiness V4 explanation

Metadata:

```json
{
  "banned_language_scan": {
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
  "example_source": "deterministic fixture example",
  "fallback_status": "rendered",
  "pitcher": null,
  "raw_count_formula_scan": {
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
  "team": "Deterministic Context Fixture (FIX, fixture-context)"
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
The public workload record is strong enough for this team note.
The public workload record is strong enough for this note.
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

### Example 41: Team Operations readiness V4 explanation

Metadata:

```json
{
  "banned_language_scan": {
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
  "example_source": "deterministic fixture example",
  "fallback_status": "rendered",
  "pitcher": null,
  "raw_count_formula_scan": {
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
  "team": "Deterministic Context Fixture (FIX, fixture-context)"
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
The public workload record is strong enough for this team note.
The public workload record is strong enough for this note.
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

### Example 42: Team Operations readiness V4 explanation

Metadata:

```json
{
  "banned_language_scan": {
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
  "example_source": "deterministic fixture example",
  "fallback_status": "rendered",
  "pitcher": null,
  "raw_count_formula_scan": {
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
  "team": "Deterministic Context Fixture (FIX, fixture-context)"
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
