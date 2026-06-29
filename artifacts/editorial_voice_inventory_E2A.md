# E2A Editorial Voice Inventory

Date: 2026-06-29

Branch: docs/editorial-voice-inventory

Scope: audit and document public storytelling voice systems only. No story output, story selection, UI behavior, thresholds, or models were changed.

## Verdict

BaseballOS does not currently speak through one editorial voice system across every public storytelling surface.

The canonical public story engine is the healthiest shared path. Its beat openings, surface framing, lessons, forward lines, and watch cues draw from `backend/services/story_voice_library_v1.py`. But several public surfaces still write copy through independent deterministic systems: homepage Today's Story, completed-game stories, What Changed, Today's Watch, Compare Bullpens, pitcher/team context explanations, and frontend framing/fallback text.

This is an editorial consistency risk, not a correctness failure. Most independent systems are deterministic and guarded, but they are not governed by the same shared voice library.

## Shared Voice Library

Primary shared library:

- `backend/services/story_voice_library_v1.py`

Shared assets found there:

- `VOICE_LIBRARY`
- `FORWARD_CLAUSE_LINES`
- `SURFACE_FRAMING_LINES`
- `LESSON_LINES`
- `WATCH_LINES`
- `ELIGIBILITY_CONTEXT_LINES`
- `BANNED_PUBLIC_LANGUAGE`
- `DENIED_PUBLIC_PHRASES`

Primary consumers:

- `backend/services/story_writer_v1.py`
- `backend/services/story_blueprint_v1.py`
- `backend/services/story_reasoning_engine_v1.py`
- `backend/services/story_feed_variety_v1.py`
- `backend/services/story_eligibility_context.py`
- story tests under `backend/tests/test_story*.py`

Shared public beats covered:

- `route_change`
- `coverage_pressure`
- `depth_constraint`
- `sustainability_question`
- `availability_depth`
- `trust_lane`
- `bridge`

## Inventory

| Surface | Writer/component | Voice source | Shared library? | Hardcoded? | Uses editorial pools? | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Homepage Today's Story | `backend/services/intelligence_surface_service.py`, `backend/services/intelligence_surface_snapshot.py`, `backend/story_writers/*`, `frontend/src/components/home/IntelligenceSurface.jsx` | Completed-game writer phrase banks in `BaseStoryWriter` and subclasses | No | Yes | Yes | Separate completed-game lead path. It selects a StoryPackage and renders existing writer drafts; it does not use `story_voice_library_v1`. |
| Stories feed | `backend/services/story_feed.py`, `backend/services/story_writer_v1.py`, `backend/services/story_blueprint_v1.py`, `backend/services/story_evidence_case_v1.py`, `frontend/src/components/stories/*` | Shared beat voice plus local evidence and league-context helpers | Partial | Partial | Yes | Team story beats use the central library for openings, forward lines, surface framing, lessons, and watch cues. Evidence and league note copy are separate hardcoded systems. |
| Team bullpen stories | `backend/services/story_intelligence_service_v1.py`, `backend/api/bullpen.py`, `frontend/src/components/bullpen/board/storyCardView.js`, `frontend/src/components/bullpen/board/StoryCard.jsx` | Shared beat voice plus `story_writer_v1` fact templates | Partial | Partial | Yes | Team board story prose comes from the backend story engine. Frontend adds labels, helpers, neutral states, and metadata copy. |
| Compare Bullpens | `backend/services/bullpen_comparison.py`, `backend/api/bullpen.py` | Local comparison statements | No | Yes | No | Public copy is count-comparison language local to the service. The line "Both bullpens currently show similar availability distributions." is a known mechanical phrase to centralize later. |
| What Changed | `backend/services/what_changed_since_yesterday_copy.py`, `backend/services/what_changed_since_yesterday_public.py`, `frontend/src/components/dashboard/WhatChangedCard.jsx`, `frontend/src/components/home/IntelligenceSurface.jsx` | Local headline, summary, and context pools | No | Yes | Yes | Deterministic and guarded, but it is a separate public copy system with its own variant picker and review flags. |
| Today's Watch | `backend/services/tonight_candidate_selection.py`, `backend/services/tonight_intelligence_service.py`, `backend/services/tonight_intelligence_snapshot.py`, `frontend/src/components/home/IntelligenceSurface.jsx` | Local pregame card helpers | No | Yes | No | Public card copy is assembled in `_pregame_story`, `_watching_sentence`, `_why_it_matters_sentence`, `_key_note_sentence`, and `_watch_point_sentence`. |
| Completed-game stories | `backend/story_orchestrator/story_orchestrator.py`, `backend/story_writers/base_story_writer.py`, `backend/story_writers/team_story_writer.py`, `backend/story_writers/dashboard_story_writer.py`, `backend/story_writers/morning_brief_writer.py`, `backend/services/coin_story_corpus.py` | Completed-game writer phrase banks | No | Yes | Yes | Independent writer stack with `_HEADLINES`, `_OPTIONALITY_PHRASE`, `_CONCENTRATION_PHRASE`, `_OBSERVATION_PHRASES`, and subclass body composition. |
| Bridge stories | `backend/services/story_writer_v1.py`, `backend/services/story_blueprint_v1.py`, `backend/services/story_voice_library_v1.py` | Shared beat voice plus bridge fact templates | Partial | Partial | Yes | Beat openings, forward lines, surface, lesson, and watch copy are shared. Bridge fact paragraphs remain local to `_bridge_instability`. |
| Route Change stories | `backend/services/story_writer_v1.py`, `backend/services/story_blueprint_v1.py`, `backend/services/story_voice_library_v1.py` | Shared beat voice plus route-change fact templates | Partial | Partial | Yes | Route-change public copy now avoids mechanical delta math, but fact paragraphs remain local to `_core_transition`. |
| Coverage Pressure stories | `backend/services/story_writer_v1.py`, `backend/services/story_blueprint_v1.py`, `backend/services/story_voice_library_v1.py` | Shared beat voice plus rotation-pressure fact templates | Partial | Partial | Yes | Uses shared voice for framing and watch copy; rotation fact paragraphs and baseline band lines are local. |
| Depth Constraint stories | `backend/services/story_writer_v1.py`, `backend/services/story_blueprint_v1.py`, `backend/services/story_voice_library_v1.py` | Shared beat voice plus depth-pressure fact templates | Partial | Partial | Yes | Uses shared voice for framing and watch copy; inactive/depth-pressure fact paragraphs remain local to `_depth_pressure`. |
| Sustainability Question stories | `backend/services/story_writer_v1.py`, `backend/services/story_blueprint_v1.py`, `backend/services/story_voice_library_v1.py` | Shared beat voice plus concentration fact templates | Partial | Partial | Yes | Uses shared voice for framing and watch copy; workload concentration fact paragraphs remain local to `_concentration_pressure`. |
| Availability Depth stories | `backend/services/story_writer_v1.py`, `backend/services/story_blueprint_v1.py`, `backend/services/story_voice_library_v1.py` | Shared beat voice plus optionality fact templates | Partial | Partial | Yes | Uses shared voice for beat framing; practical-path and clean-option facts remain local to `_optionality_strength`. |
| Trust Lane stories | `backend/services/story_writer_v1.py`, `backend/services/story_blueprint_v1.py`, `backend/services/story_voice_library_v1.py` | Shared beat voice plus trust-lane fact templates | Partial | Partial | Yes | Uses shared voice for framing and watch copy; clean trusted-lane fact paragraphs remain local to `_trust_lane_pressure`. |
| Pitcher Context explanations | `backend/services/pitcher_public_labels.py`, `backend/services/availability_explanations.py`, `backend/explanations/readiness.py` | Public label and explanation catalogs | No | Yes | Yes | This is a context/label layer, not narrative prose. It is centralized within pitcher/readiness explanations but not tied to the story voice library. |
| Team bullpen shape explanations | `backend/services/team_bullpen_shape.py`, `frontend/src/utils/teamBullpenScoring.js`, `frontend/src/utils/bullpenConcepts.js` | Team shape label and explanation catalogs | No | Yes | Yes | Owns public labels such as Trust Arm Availability, Clean Options, Bullpen Pressure, Workload Concentration, Coverage Safety, and Depth Safety. |
| Dormant frontend language layer | `frontend/src/utils/bullpenLanguage.js`, `docs/product/LANGUAGE_ENGINE_V1.md` | Frontend `SIGNAL_HEADLINES` pools | No | Yes | Yes | `rg` found no current imports of `bullpenLanguage.js`. Treat as dead or dormant duplicate voice assets until proven otherwise. |

## Public Copy Locations To Centralize Later

- `backend/services/bullpen_comparison.py`
  - `COMPARISON_DIMENSIONS`
  - `_build_observation`
  - `summary['statement']`
- `backend/services/what_changed_since_yesterday_copy.py`
  - `_headline`
  - `_summary`
  - `_secondary_phrase`
  - `_context`
- `backend/services/tonight_candidate_selection.py`
  - `_signal_*` headline/summary fields
  - `_pregame_story`
  - `_watching_sentence`
  - `_why_it_matters_sentence`
  - `_key_note_sentence`
  - `_watch_point_sentence`
- `backend/story_writers/base_story_writer.py`
  - `_HEADLINES`
  - `_OPTIONALITY_PHRASE`
  - `_CONCENTRATION_PHRASE`
  - `_OBSERVATION_PHRASES`
  - lead/body/takeaway helpers
- `backend/services/story_evidence_case_v1.py`
  - `MEANING_VARIANTS`
  - `_LEAD_VARIANTS`
- `backend/services/story_feed.py`
  - `_select_league_mode`
  - `LEAGUE_CONTINUITY_SENTENCES`
- `backend/services/team_bullpen_shape.py`
  - `TEAM_BULLPEN_PUBLIC_LABELS`
  - read explanation helpers
- `backend/services/pitcher_public_labels.py`
  - `ROLE_PUBLIC_LABELS`
  - `READ_PUBLIC_LABELS`
- `backend/services/availability_explanations.py`
  - `REASON_CATALOG`
  - reason and limitation text helpers
- `frontend/src/components/home/IntelligenceSurface.jsx`
  - Today's Story framing, Around Baseball transformations, Tonight framing, empty/error states
- `frontend/src/components/stories/storiesCanonicalFeedView.js`
  - feed fallback, limitations fallback, story kickers, continuity badges, league-card fallback
- `frontend/src/components/stories/storiesFeedView.js`
  - filter labels, active labels, empty states
- `frontend/src/components/bullpen/board/storyCardView.js`
  - story type labels/helpers, neutral states, trust label
- `frontend/src/utils/bullpenLanguage.js`
  - dormant `SIGNAL_HEADLINES`

## Duplicate Voice Systems Found

1. Shared public story voice library: `backend/services/story_voice_library_v1.py`.
2. Canonical story fact writer: `backend/services/story_writer_v1.py`.
3. Canonical story evidence case writer: `backend/services/story_evidence_case_v1.py`.
4. Canonical league-context writer: `backend/services/story_feed.py`.
5. Completed-game writer stack: `backend/story_writers/*`.
6. What Changed copy helper: `backend/services/what_changed_since_yesterday_copy.py`.
7. Pregame Today's Watch copy helper: `backend/services/tonight_candidate_selection.py`.
8. Compare Bullpens copy helper: `backend/services/bullpen_comparison.py`.
9. Pitcher/team context label and explanation catalogs: `pitcher_public_labels.py`, `team_bullpen_shape.py`, `availability_explanations.py`, `backend/explanations/readiness.py`.
10. Frontend presentation/framing copy: Stories, Home, team board story card helpers.
11. Dormant frontend language pools: `frontend/src/utils/bullpenLanguage.js`.

## Editorial Risks

- The same baseball idea can sound different depending on whether it comes from the canonical story engine, homepage Today's Story, What Changed, Today's Watch, or Compare Bullpens.
- Guardrails are duplicated. Several surfaces ban internal or predictive language independently rather than reusing one public voice contract.
- Some public phrases remain mechanical because they live outside the shared voice library, especially Compare Bullpens and some What Changed count movement summaries.
- Public beat stories are only partially centralized. The highest-level beat voice is shared, but fact paragraphs and evidence variants are still local.
- Frontend surface framing can alter the publication voice even when backend story prose is shared.
- Dormant voice assets can mislead future work unless they are either reactivated deliberately or archived.

## Diagnostic Test Added

`backend/tests/test_editorial_voice_inventory_e2a.py` codifies this inventory. It checks:

- required public surfaces are inventoried;
- every inventory row has a voice-source classification;
- referenced files still exist;
- known independent public voice systems are documented;
- documented public story beats are covered by the shared voice library;
- the dormant frontend language layer is explicitly marked as dormant duplicate voice.

## Recommended E2B Scope

E2B should be a unification design pass, not a copy rewrite. Recommended scope:

1. Define a single `public_editorial_voice` contract that can serve both story prose and shorter card/explanation surfaces.
2. Decide whether `story_voice_library_v1.py` becomes that contract or whether a new wrapper organizes existing pools without changing copy.
3. Move one low-risk independent surface first, likely Compare Bullpens or Today's Watch, behind shared public phrase helpers while preserving output with tests.
4. Add a hard governance test that any new public storytelling surface must declare its voice source.
5. Leave completed-game story rewrites for a later phase because that stack has broader body-composition behavior.
