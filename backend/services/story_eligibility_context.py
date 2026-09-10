"""Eligibility-aware story context (Phase C3E).

After C3D, Swing/Bulk Relief arms contribute to coverage and depth context but
are held out of the trust/bridge/clean lanes. This module lets the canonical
story system qualify a bullpen story when Swing/Bulk arms materially shape the
coverage or depth picture — for example, noting that part of the available
coverage comes from swing/bulk usage rather than dedicated relief roles.

It is deliberately narrow and governed:

* It adds story CONTEXT only — a single approved voice-library sentence appended
  to an existing forward-constraint beat. It never adds a public role/label,
  changes the story payload shape, or exposes eligibility_type.
* The swing/bulk signal is computed transiently from the team's current
  availability records (which already carry eligibility metadata). It is never
  written into team_context, the diagnostic context API, or the public feed.
* It qualifies a story only when one is already available and its family is one
  where swing/bulk participation is meaningful (coverage, depth, trust lane,
  bridge, availability depth).
"""

from __future__ import annotations

from typing import Any

from services.availability_population import current_availability_records
from services.availability_snapshot import latest_fatigue_rows
from services.bullpen_eligibility_vocabulary import (
    record_is_bullpen_eligible,
    record_is_swing_bulk,
)
from services.story_observation_engine import (
    TYPE_BRIDGE_INSTABILITY,
    TYPE_DEPTH_PRESSURE,
    TYPE_OPTIONALITY_STRENGTH,
    TYPE_ROTATION_PRESSURE,
    TYPE_TRUST_LANE_PRESSURE,
)
from services.story_voice_library_v1 import (
    BEAT_AVAILABILITY_DEPTH,
    BEAT_BRIDGE,
    BEAT_COVERAGE_PRESSURE,
    BEAT_DEPTH_CONSTRAINT,
    BEAT_TRUST_LANE,
    PURPOSE_ELIGIBILITY_CONTEXT,
    render_voice_line,
)


# Internal observation type -> the forward-constraint beat its story qualifies.
_OBSERVATION_BEAT = {
    TYPE_ROTATION_PRESSURE: BEAT_COVERAGE_PRESSURE,
    TYPE_DEPTH_PRESSURE: BEAT_DEPTH_CONSTRAINT,
    TYPE_TRUST_LANE_PRESSURE: BEAT_TRUST_LANE,
    TYPE_BRIDGE_INSTABILITY: BEAT_BRIDGE,
    TYPE_OPTIONALITY_STRENGTH: BEAT_AVAILABILITY_DEPTH,
}

_ABSENT_SIGNAL = {'present': False, 'swing_bulk_count': 0, 'eligible_count': 0}


def _clean(value: Any) -> str:
    return ' '.join(str(value or '').strip().split())


def team_swing_bulk_context(records) -> dict[str, Any]:
    """Summarize Swing/Bulk participation from a team's availability records.

    Records carry the normalized eligibility payload. Swing/Bulk is material when
    at least one eligible bullpen arm is typed swing_bulk_relief.
    """
    eligible = [record for record in (records or []) if record_is_bullpen_eligible(record)]
    swing_bulk = [record for record in eligible if record_is_swing_bulk(record)]
    return {
        'present': len(swing_bulk) >= 1,
        'swing_bulk_count': len(swing_bulk),
        'eligible_count': len(eligible),
    }


def observation_type_of(payload: dict[str, Any]) -> Any:
    selected = payload.get('selected_observation')
    if isinstance(selected, dict) and selected.get('type'):
        return selected.get('type')
    frame = payload.get('construction_frame')
    if isinstance(frame, dict):
        return frame.get('observation_type')
    return None


def swing_bulk_clause_for(payload: dict[str, Any]) -> str | None:
    """Render the governed swing/bulk context sentence for a story payload."""
    beat = _OBSERVATION_BEAT.get(observation_type_of(payload))
    if beat is None:
        return None
    return render_voice_line(
        beat,
        purpose=PURPOSE_ELIGIBILITY_CONTEXT,
        stable_parts=(payload.get('team_id'), observation_type_of(payload)),
    )


def attach_swing_bulk_story_context(payload: dict[str, Any], signal: dict[str, Any]) -> dict[str, Any]:
    """Append the swing/bulk context sentence to a story's forward-constraint beat.

    Returns the payload unchanged unless a story is available, the signal is
    material, the story family is relevant, and a forward-constraint paragraph
    already exists (the sentence qualifies an existing beat, never creating one).
    The eligible/role/status of any pitcher and the payload shape are untouched.
    """
    if not isinstance(payload, dict) or payload.get('story_available') is not True:
        return payload
    if not (isinstance(signal, dict) and signal.get('present')):
        return payload
    written = payload.get('written_story')
    if not isinstance(written, dict):
        return payload
    constraint = _clean(written.get('constraint_paragraph'))
    if not constraint:
        return payload
    clause = swing_bulk_clause_for(payload)
    if not clause or clause.lower() in constraint.lower():
        return payload
    updated = dict(written)
    updated['constraint_paragraph'] = f'{constraint} {clause}.'
    payload['written_story'] = updated
    return payload


def _team_swing_bulk_signal(team_id, reference_date=None) -> dict[str, Any]:
    if team_id is None:
        return dict(_ABSENT_SIGNAL)
    try:
        records = current_availability_records(
            latest_fatigue_rows(team_id=team_id),
            reference_date=reference_date,
        )
    except Exception:
        # Story enrichment is optional; never let a data/context error break
        # story generation. Absent the signal, no context is added.
        return dict(_ABSENT_SIGNAL)
    return team_swing_bulk_context(records)


def apply_swing_bulk_story_context(payload: dict[str, Any], *, reference_date=None) -> dict[str, Any]:
    """Compute the team's swing/bulk signal and qualify the story when material."""
    if not isinstance(payload, dict) or payload.get('story_available') is not True:
        return payload
    signal = _team_swing_bulk_signal(payload.get('team_id'), reference_date)
    return attach_swing_bulk_story_context(payload, signal)
