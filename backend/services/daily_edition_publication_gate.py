"""Today-only semantic publication gate for the Daily Edition lead.

The existing COIN writers translate two independent structured inputs: a
completed-game narrative and the bullpen's current optionality/concentration
snapshot.  On the public Today lead those inputs must be checked together
before any rendered draft is exposed.  This module performs that narrow check;
it does not redefine either input, calculate workload, or generate prose.

The gate is intentionally downstream of story inspection.  It validates the
exact consequence the Team Story writer would render and returns the exact
claim-driving relief receipts the API is allowed to publish.  Callers withhold
the candidate when the result is not ``pass``.
"""

from __future__ import annotations

from typing import Any

from services.editorial_voice_contract_v1 import resolve_bullpen_consequence_key
from services.today_relief_appearance_evidence import (
    RELIEF_PARTICIPANT_ROLE,
    SCORING_EVENT_ROLE,
)


GATE_VERSION = 'daily_edition_claim_evidence_v1'

STATUS_PASS = 'pass'
STATUS_WITHHELD = 'withheld'

REASON_EVENT_CONSEQUENCE_INCOMPATIBLE = 'event_consequence_incompatible'
REASON_RESPONSIBLE_RELIEF_EVIDENCE_MISSING = 'responsible_relief_evidence_missing'
REASON_RESPONSIBLE_RELIEF_EVIDENCE_MISMATCH = 'responsible_relief_evidence_mismatch'
REASON_STORY_PACKAGE_UNAVAILABLE = 'story_package_unavailable'

POSITIVE_CONSEQUENCES = frozenset({
    'late_inning_margin',
    'workload_spread',
})
NEGATIVE_CONSEQUENCES = frozenset({
    'availability_narrowed',
    'workload_concentration',
})
KNOWN_CONSEQUENCES = POSITIVE_CONSEQUENCES | NEGATIVE_CONSEQUENCES

# Explicit rather than inferred from prose.  ``None`` is handled separately: no
# rendered consequence means there is no directional pairing to validate.
EVENT_CONSEQUENCE_COMPATIBILITY = {
    'lost_game_shape': NEGATIVE_CONSEQUENCES,
    'late_pressure_accumulated': NEGATIVE_CONSEQUENCES,
    'bullpen_overexposed': NEGATIVE_CONSEQUENCES,
    'protected_game_shape': POSITIVE_CONSEQUENCES,
    'bullpen_kept_team_alive': POSITIVE_CONSEQUENCES,
    'starter_covered_bullpen': POSITIVE_CONSEQUENCES,
}

PERSONNEL_DEPENDENT_NARRATIVES = frozenset({
    'lost_game_shape',
    'late_pressure_accumulated',
    'bullpen_overexposed',
    'protected_game_shape',
    'bullpen_kept_team_alive',
})

_APPEARANCE_FIELDS = (
    'pitcher_id',
    'pitcher_mlb_id',
    'name',
    'game_pk',
    'appearance_team_id',
    'innings',
    'innings_pitched_outs',
    'pitches_thrown',
    'runs_allowed',
    'claim_evidence_role',
    'claim_event_indexes',
    'claim_event_innings',
    'claim_source_play_ids',
)

_REQUIRED_EVIDENCE_ROLE = {
    'lost_game_shape': SCORING_EVENT_ROLE,
    'late_pressure_accumulated': SCORING_EVENT_ROLE,
    'bullpen_overexposed': RELIEF_PARTICIPANT_ROLE,
    'protected_game_shape': RELIEF_PARTICIPANT_ROLE,
    'bullpen_kept_team_alive': RELIEF_PARTICIPANT_ROLE,
}


def evaluate_daily_edition_publication(inspected: dict[str, Any] | None) -> dict:
    """Return the governed Today publication decision for one inspected story."""
    package = inspected.get('package') if isinstance(inspected, dict) else None
    if not isinstance(package, dict):
        return _result(
            STATUS_WITHHELD,
            REASON_STORY_PACKAGE_UNAVAILABLE,
            primary_story=None,
            consequence_key=None,
            appearances=[],
        )

    primary = package.get('primary_story')
    consequence = rendered_team_story_consequence(package)
    if not event_consequence_is_compatible(primary, consequence):
        return _result(
            STATUS_WITHHELD,
            REASON_EVENT_CONSEQUENCE_INCOMPATIBLE,
            primary_story=primary,
            consequence_key=consequence,
            appearances=[],
        )

    raw_appearances = _package_appearances(package)
    normalized = [
        record
        for record in (_normalize_appearance(item) for item in raw_appearances)
        if record is not None
    ]
    if primary in PERSONNEL_DEPENDENT_NARRATIVES:
        if not normalized:
            return _result(
                STATUS_WITHHELD,
                REASON_RESPONSIBLE_RELIEF_EVIDENCE_MISSING,
                primary_story=primary,
                consequence_key=consequence,
                appearances=[],
            )
        if (
            len(normalized) != len(raw_appearances)
            or not all(_appearance_has_authoritative_link(primary, record)
                       for record in normalized)
            or not _identity_matches_story(
                inspected,
                package,
                normalized,
            )
        ):
            return _result(
                STATUS_WITHHELD,
                REASON_RESPONSIBLE_RELIEF_EVIDENCE_MISMATCH,
                primary_story=primary,
                consequence_key=consequence,
                appearances=[],
            )

    return _result(
        STATUS_PASS,
        None,
        primary_story=primary,
        consequence_key=consequence,
        appearances=normalized,
    )


def event_consequence_is_compatible(primary: Any, consequence: Any) -> bool:
    """Return the explicit table decision for one structured pairing."""
    compatible = EVENT_CONSEQUENCE_COMPATIBILITY.get(primary)
    return compatible is not None and (
        consequence is None or consequence in compatible
    )


def rendered_team_story_consequence(package: dict[str, Any]) -> str | None:
    """Resolve only a consequence that the public Team Story actually emits."""
    primary = package.get('primary_story')
    priority = package.get('story_priority')
    emits_takeaway = priority in {'CRITICAL', 'HIGH'}
    embeds_consequence = primary == 'starter_covered_bullpen'
    if not emits_takeaway and not embeds_consequence:
        return None

    availability = package.get('availability_snapshot')
    availability = availability if isinstance(availability, dict) else {}
    workload = package.get('workload_snapshot')
    workload = workload if isinstance(workload, dict) else {}

    return resolve_bullpen_consequence_key(
        availability,
        workload,
        'workload_spread' if embeds_consequence else None,
    )


def _package_appearances(package: dict[str, Any]) -> list:
    blocks = package.get('evidence_blocks')
    blocks = blocks if isinstance(blocks, dict) else {}
    appearances = blocks.get('key_relief_appearances')
    return appearances if isinstance(appearances, list) else []


def _normalize_appearance(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    name = item.get('name')
    if not isinstance(name, str) or not name.strip():
        return None
    record = {
        key: item.get(key)
        for key in _APPEARANCE_FIELDS
        if item.get(key) is not None
    }
    record['name'] = name.strip()
    return record


def _appearance_has_authoritative_link(
    primary: Any,
    appearance: dict[str, Any],
) -> bool:
    if appearance.get('claim_evidence_role') != _REQUIRED_EVIDENCE_ROLE.get(primary):
        return False
    pitcher_mlb_id = appearance.get('pitcher_mlb_id')
    if (
        isinstance(pitcher_mlb_id, bool)
        or not isinstance(pitcher_mlb_id, int)
        or pitcher_mlb_id <= 0
    ):
        return False
    if appearance.get('claim_evidence_role') == SCORING_EVENT_ROLE:
        indexes = appearance.get('claim_event_indexes')
        return (
            isinstance(indexes, list)
            and bool(indexes)
            and all(
                isinstance(index, int) and not isinstance(index, bool) and index >= 0
                for index in indexes
            )
        )
    return True


def _identity_matches_story(
    inspected: dict[str, Any],
    package: dict[str, Any],
    appearances: list[dict[str, Any]],
) -> bool:
    expected_game = inspected.get('game_pk')
    expected_team = inspected.get('team_id')
    if expected_game is None or expected_team is None:
        return False
    if (
        package.get('game_pk') != expected_game
        or package.get('team_id') != expected_team
    ):
        return False
    for appearance in appearances:
        if (
            appearance.get('game_pk') != expected_game
            or appearance.get('appearance_team_id') != expected_team
        ):
            return False
    return True


def _result(status, reason, *, primary_story, consequence_key, appearances):
    return {
        'status': status,
        'reason': reason,
        'gate_version': GATE_VERSION,
        'primary_story': primary_story,
        'consequence_key': consequence_key,
        'claim_evidence': {
            'relief_appearances': [dict(item) for item in appearances],
        },
    }
