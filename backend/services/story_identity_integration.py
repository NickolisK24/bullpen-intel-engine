"""Public-safe Bullpen Identity texture for rendered team stories.

This adapter turns an existing Bullpen Identity read into one supporting
story sentence. It does not select stories, rank teams or relievers, recommend
usage, predict outcomes, or expose identity labels as story copy.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Callable

from services.bullpen_identity import (
    IDENTITY_DEPTH_DRIVEN,
    IDENTITY_FLEXIBLE_DISTRIBUTION,
    IDENTITY_FRAGILE_COVERAGE,
    IDENTITY_LEVERAGE_HEAVY,
    IDENTITY_RESOURCE_STRAINED,
    IDENTITY_TRUST_CONCENTRATED,
    IDENTITY_UNKNOWN,
)


CAPABILITY = 'story_identity_integration_v1'
VERSION = '2026-06-19'

IDENTITY_CONFIDENCE_ALLOWED = {'medium', 'high'}

MISSING_IDENTITY_LIMITATION = (
    'Story identity integration did not apply because Bullpen Identity context is missing.'
)
UNKNOWN_IDENTITY_LIMITATION = (
    'Story identity integration did not apply because Bullpen Identity context is unknown or low confidence.'
)

_SentenceBuilder = Callable[[dict[str, Any]], str]


def _clean_text(value: Any) -> str:
    return ' '.join(str(value or '').strip().split())


def _norm(value: Any) -> str:
    return _clean_text(value).lower()


def _stable_seed(facts: dict[str, Any], namespace: str) -> str:
    team = facts.get('team') or {}
    payload = {
        'namespace': namespace,
        'team_id': team.get('team_id'),
        'team_name': team.get('team_name'),
        'team_abbreviation': team.get('team_abbreviation'),
        'primary_observation': facts.get('primary_observation'),
        'supporting_context': facts.get('supporting_context'),
        'pressure_source': facts.get('pressure_source'),
        'workload_pattern': facts.get('workload_pattern'),
        'capacity_context': facts.get('capacity_context'),
        'bullpen_context': facts.get('bullpen_context'),
        'watch_question': facts.get('watch_question'),
    }
    return json.dumps(payload, sort_keys=True, default=str)


def _stable_index(facts: dict[str, Any], namespace: str, length: int) -> int:
    if length <= 0:
        return 0
    digest = hashlib.sha256(_stable_seed(facts, namespace).encode('utf-8')).hexdigest()
    team_offset = 0
    if namespace == 'identity-texture:leverage_backbone':
        team = facts.get('team') or {}
        team_offset = int(team.get('team_id') or 0) % length
    return (int(digest[:12], 16) + team_offset) % length


def _choose(facts: dict[str, Any], namespace: str, options: list[_SentenceBuilder]) -> str:
    return options[_stable_index(facts, namespace, len(options))](facts)


def _result(text: str, *, reason: str) -> dict[str, Any]:
    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'applied': True,
        'text': text,
        'reason': reason,
        'sources': ['bullpen_identity'],
        'ranking_applied': False,
        'selection_made': False,
        'prediction_applied': False,
        'limitations': [],
    }


def _not_applied(reason: str, limitations: list[str] | None = None) -> dict[str, Any]:
    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'applied': False,
        'text': None,
        'reason': reason,
        'sources': [],
        'ranking_applied': False,
        'selection_made': False,
        'prediction_applied': False,
        'limitations': list(limitations or []),
    }


def _identity_ready(identity: dict[str, Any]) -> bool:
    if not isinstance(identity, dict) or not identity:
        return False
    if _norm(identity.get('identity_key')) in {'', IDENTITY_UNKNOWN}:
        return False
    return _norm(identity.get('confidence')) in IDENTITY_CONFIDENCE_ALLOWED


def _phrase_options(identity_key: str) -> tuple[str, list[_SentenceBuilder]] | None:
    options_by_identity: dict[str, tuple[str, list[_SentenceBuilder]]] = {
        IDENTITY_FLEXIBLE_DISTRIBUTION: (
            'usable_width',
            [
                lambda f: "This group usually survives by spreading innings across several usable options.",
                lambda f: "The shape is less about one arm and more about how many paths are still open.",
                lambda f: "The useful part is the number of ways this group can cover the middle of a game.",
            ],
        ),
        IDENTITY_LEVERAGE_HEAVY: (
            'leverage_backbone',
            [
                lambda f: "The leverage group still gives this bullpen a recognizable backbone.",
                lambda f: "The late-inning structure is still the clearest part of the picture.",
                lambda f: "Even when the night gets uneven, the back of the bullpen gives the story a spine.",
                lambda f: "This bullpen's shape still starts with the arms trusted for the biggest innings.",
                lambda f: "The most defined part of this group remains the late-game structure.",
                lambda f: "The late innings still give this bullpen its clearest shape.",
                lambda f: "The back of the game still gives this bullpen a clear starting point.",
            ],
        ),
        IDENTITY_DEPTH_DRIVEN: (
            'depth_width',
            [
                lambda f: "The coverage comes less from one obvious answer and more from having enough usable pieces.",
                lambda f: "This bullpen can absorb a normal night because the options do not fall off immediately.",
                lambda f: "The depth matters because the game does not have to hinge on one perfect handoff.",
            ],
        ),
        IDENTITY_RESOURCE_STRAINED: (
            'resource_edges',
            [
                lambda f: "The challenge is not just tonight's workload; it is how much flexibility remains around the edges.",
                lambda f: "The first move may be manageable, but the later innings can get narrower if the game stretches.",
                lambda f: "The stress shows up around the margins, where one extra inning can start shrinking the choices.",
            ],
        ),
        IDENTITY_TRUST_CONCENTRATED: (
            'narrow_trust_lane',
            [
                lambda f: "The comfortable part of the bullpen is narrower than the full list suggests.",
                lambda f: "This story runs through a smaller trusted lane before it reaches the rest of the group.",
                lambda f: "The game can still have a plan, but the plan leans on a smaller trusted pocket.",
            ],
        ),
        IDENTITY_FRAGILE_COVERAGE: (
            'thin_cover',
            [
                lambda f: "The first answers may exist, but the cover behind them can thin out quickly.",
                lambda f: "This bullpen has less cushion if the game moves off script.",
                lambda f: "A normal inning can be manageable; a messy one can shrink the board quickly.",
            ],
        ),
    }
    return options_by_identity.get(identity_key)


def build_story_identity_integration(facts: dict[str, Any] | None) -> dict[str, Any]:
    """Return one public-safe identity sentence for story texture, if supported."""

    facts = facts or {}
    identity = facts.get('bullpen_identity') or {}
    if not isinstance(identity, dict) or not identity:
        return _not_applied('missing_identity', [MISSING_IDENTITY_LIMITATION])
    if not _identity_ready(identity):
        return _not_applied('unknown_or_low_confidence_identity', [UNKNOWN_IDENTITY_LIMITATION])

    identity_key = _norm(identity.get('identity_key'))
    phrase_config = _phrase_options(identity_key)
    if not phrase_config:
        return _not_applied('unsupported_identity')

    reason, options = phrase_config
    text = _choose(facts, f'identity-texture:{reason}', options)
    return _result(text, reason=reason)


__all__ = [
    'CAPABILITY',
    'IDENTITY_CONFIDENCE_ALLOWED',
    'MISSING_IDENTITY_LIMITATION',
    'UNKNOWN_IDENTITY_LIMITATION',
    'VERSION',
    'build_story_identity_integration',
]
