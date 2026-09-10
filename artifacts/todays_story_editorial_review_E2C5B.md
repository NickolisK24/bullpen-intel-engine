# Today's Story Editorial Review Corpus - E2C-5B

Review artifact for the homepage-visible Today's Story / completed-game story
writer migration to the E2 Editorial Voice helpers.

## Export Metadata

```json
{
  "artifact": "artifacts/todays_story_editorial_review_E2C5B.md",
  "migration": "E2C-5B - Today's Story / Completed-Game Voice Migration",
  "source_mode": "deterministic seeded completed-game fixtures plus focused public-render tests",
  "surface_scope": [
    "backend/story_writers/base_story_writer.py",
    "backend/story_writers/team_story_writer.py",
    "backend/story_writers/dashboard_story_writer.py",
    "backend/story_writers/morning_brief_writer.py",
    "backend/services/intelligence_surface_service.py"
  ],
  "unchanged_surfaces": [
    "Compare Bullpens",
    "Today's Watch",
    "What Changed",
    "frontend layout",
    "public story beat selection",
    "publishability thresholds"
  ],
  "completed_game_seeded_rendered_drafts": 11,
  "banned_language_violation_count": 0,
  "impossible_innings_notation_count": 0,
  "headline_reuse_max_in_seeded_review": 2,
  "public_surfaces_migrated_entry": "todays_story_completed_game"
}
```

## Migration Summary

- Completed-game bullpen-state tails now route through
  `services.editorial_voice_contract_v1.render_baseball_consequence`.
- Decimal inning fractions now render as baseball outs notation via
  `utils.baseball_innings.format_baseball_innings`.
- Starter-covered-bullpen public copy now requires a starter name plus innings
  or pitch count. If that anchor is missing, the writer falls back to neutral
  insufficient-detail copy instead of publishing the old nameless sentence.
- Completed-game headline/body templates now use deterministic variants keyed
  from stable feed identifiers to reduce same-beat repetition without inventing
  facts.
- Public evidence keeps the named reliever evidence, with the discouraged
  "Clean options" label replaced by "Available relievers."

## Rendered-Copy Audit

```json
{
  "draft_count": 11,
  "violation_count": 0,
  "impossible_innings": [],
  "headline_reuse_max": 2
}
```

Representative migrated copy from the seeded review path:

```text
Late lead slipped away

After their most recent game, Landen Roupp gave the Giants six innings and a four-run lead. It didn't last. Seven late runs turned the game, with Ryan Walker and Tyler Rogers surrendering the decisive blows. That leaves fewer clean ways through a close game.
```

```text
Bullpen note: Late lead slipped away

After their most recent game, the Giants carried a four-run lead into the late innings and let it get away on seven late runs. Available arms: Erik Miller. Yesterday's late damage matters here. That narrows the usable group before the game gets late.
```

## Guardrails Preserved

- Completed-game `StoryPackage` structured fields are unchanged.
- Publishable/unpublishable behavior is unchanged.
- Homepage empty/fallback handling is unchanged.
- The intelligence surface ranking order and thresholds are unchanged.
- No models were added.
- Frontend layout was not modified.

## Test Ledger

```text
PYTHONPATH=backend AUTO_SYNC=false backend/.venv/bin/python -m pytest backend/tests/test_editorial_voice_contract_v1.py backend/tests/test_coin_story_corpus.py backend/tests/test_coin_story_inspection.py -q -rxX
37 passed

PYTHONPATH=backend AUTO_SYNC=false backend/.venv/bin/python -m pytest backend/tests/test_story_writers.py backend/tests/test_story_writers_evidence.py backend/tests/test_story_writer_v1.py -q -rxX
76 passed

PYTHONPATH=backend AUTO_SYNC=false backend/.venv/bin/python -m pytest backend/tests/test_intelligence_surface_service.py backend/tests/test_intelligence_surface_snapshot.py backend/tests/test_intelligence_surface_endpoint.py -q -rxX
39 passed

PYTHONPATH=backend AUTO_SYNC=false backend/.venv/bin/python -m pytest backend/tests/test_story*.py backend/tests/test_four_beat_real_quality_audit.py -q -rxX
479 passed
```

Note: plain `python` is not installed on this machine's PATH, so the repository
virtualenv interpreter (`backend/.venv/bin/python`) was used for the test runs.
