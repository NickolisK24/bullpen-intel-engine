"""Evidence Composition Engine (ECE) — COIN.

Every BaseballOS story must be explainable: the story tells the narrative, the
observations explain it, and the evidence proves the observations. ECE builds
the evidence layer. It sits between the Narrative Feed and the Story Package:

    Narrative Feed -> Evidence Composition Engine -> Story Package -> Story Writers

ECE produces NO prose, NO opinions, and NO new intelligence. It only reorganizes
facts COIN already knows — the completed-game context, the narrative's own
supporting facts/observations, and the bullpen/availability/workload snapshots —
into a fixed set of labeled, structured evidence blocks.

It is deterministic and fail-closed: a fact that is not present in the feed is
omitted (scalar) or yields an empty list (collection); nothing is invented,
inferred, or summarized into sentences.
"""

from __future__ import annotations

from typing import Any


EVIDENCE_VERSION = 'evidence_v1'

# The fixed, ordered set of evidence blocks ECE emits.
EVIDENCE_BLOCK_NAMES = (
    'available_relievers',
    'monitor_relievers',
    'limited_relievers',
    'unavailable_relievers',
    'starter_summary',
    'bullpen_summary',
    'largest_lead',
    'largest_deficit',
    'turning_point',
    'bullpen_entry_situation',
    'key_relief_appearances',
    'late_runs',
    'coverage_depth',
    'workload_concentration',
    'clean_options',
    'story_evidence',
)


def _as_dict(value) -> dict:
    if isinstance(value, dict):
        return value
    to_dict = getattr(value, 'to_dict', None)
    if callable(to_dict):
        result = to_dict()
        return result if isinstance(result, dict) else {}
    return {}


def _sub(feed: dict, key: str) -> dict:
    value = feed.get(key)
    return value if isinstance(value, dict) else {}


def _list(value) -> list:
    return value if isinstance(value, list) else []


def _compact(facts: dict) -> dict:
    """Drop keys whose value is None — a missing fact is omitted, never guessed."""
    return {key: value for key, value in facts.items() if value is not None}


def _reliever_record(item: Any, default_status=None) -> dict | None:
    """Normalize one named reliever into {name, status}; drop if unnamed."""
    if not isinstance(item, dict):
        return None
    name = item.get('name')
    if not name:
        return None
    status = item.get('status') or item.get('availability') or default_status
    record = {'name': name}
    if status is not None:
        record['status'] = status
    return record


def _named_relievers(items, default_status=None) -> list[dict]:
    records = [_reliever_record(item, default_status) for item in _list(items)]
    return [record for record in records if record is not None]


def _relief_appearances(items) -> list[dict]:
    """Normalize per-appearance lines into {name, innings, runs_allowed} facts."""
    appearances = []
    for item in _list(items):
        if not isinstance(item, dict):
            continue
        name = item.get('name')
        if not name:
            continue
        appearances.append(_compact({
            'name': name,
            'innings': item.get('innings'),
            'runs_allowed': item.get('runs_allowed'),
        }))
    return appearances


def compose_evidence_blocks(narrative_feed) -> dict:
    """Build the deterministic evidence blocks from a NarrativeFeed (dict or object).

    Reads only the feed. Returns a dict with every block name present (collections
    default to ``[]``, summaries to ``{}``) plus an ``evidence_version`` marker, so
    consumers can rely on a stable shape regardless of how much data was available.
    """
    feed = _as_dict(narrative_feed)
    completed = _sub(feed, 'completed_game_context')
    narrative = _sub(feed, 'narrative_context')
    availability = _sub(feed, 'availability_snapshot')
    workload = _sub(feed, 'workload_snapshot')
    bullpen = _sub(feed, 'bullpen_snapshot')

    facts = feed.get('supporting_facts')
    facts = facts if isinstance(facts, dict) else {}
    observations = _list(feed.get('supporting_observations'))

    # Named clean options double as the named "available" arms COIN can prove;
    # status buckets without a named source stay empty (counts live in the
    # bullpen summary) rather than inventing names.
    clean_options = _named_relievers(bullpen.get('clean_options'), default_status='Available')

    blocks = {
        'available_relievers': list(clean_options),
        'monitor_relievers': _named_relievers(availability.get('monitor_relievers')),
        'limited_relievers': _named_relievers(availability.get('limited_relievers')),
        'unavailable_relievers': _named_relievers(availability.get('unavailable_relievers')),
        'starter_summary': _compact({
            'name': completed.get('starter_name'),
            'innings': completed.get('starter_ip'),
            'pitch_count': completed.get('starter_pitch_count'),
            'exit_inning': completed.get('starter_exit_inning'),
            'exit_score_for': completed.get('starter_exit_score_for'),
            'exit_score_against': completed.get('starter_exit_score_against'),
            'game_shape_created': completed.get('game_shape_created'),
        }),
        'bullpen_summary': _compact({
            'available_count': availability.get('available_arms_count'),
            'monitor_count': availability.get('monitor_arms_count'),
            'limited_count': availability.get('limited_arms_count'),
            'unavailable_count': availability.get('unavailable_arms_count'),
            'optionality_band': availability.get('optionality_band'),
            'late_runs_allowed': completed.get('late_runs_allowed'),
            'lead_protected': completed.get('lead_protected'),
            'lead_lost': completed.get('lead_lost'),
            'comeback_completed': completed.get('comeback_completed'),
        }),
        'largest_lead': _compact({'runs': completed.get('largest_lead')}),
        'largest_deficit': _compact({'runs': completed.get('largest_deficit')}),
        'turning_point': _compact({'inning': completed.get('turning_inning')}),
        'bullpen_entry_situation': _compact({
            'inning': completed.get('bullpen_entry_inning'),
            'score_for': completed.get('bullpen_entry_score_for'),
            'score_against': completed.get('bullpen_entry_score_against'),
            'lead_when_entered': completed.get('lead_when_bullpen_entered'),
            'deficit_when_entered': completed.get('deficit_when_bullpen_entered'),
        }),
        'key_relief_appearances': _relief_appearances(
            completed.get('key_relief_appearances')
        ),
        'late_runs': _compact({
            'late_runs_allowed': completed.get('late_runs_allowed'),
            'runs_allowed_innings_7_to_9': completed.get('runs_allowed_innings_7_to_9'),
        }),
        'coverage_depth': _compact({
            'clean_options_count': bullpen.get('clean_options_count'),
            'secondary_options_count': bullpen.get('secondary_options_count'),
            'practical_close_game_paths_count': bullpen.get('practical_close_game_paths_count'),
            'bullpen_coverage_ip_7d': workload.get('bullpen_coverage_ip_7d'),
            'depth_pressure_band': bullpen.get('depth_pressure_band'),
        }),
        'workload_concentration': _compact({
            'concentration_band': workload.get('concentration_band'),
            'top_three_workload_share_10d': workload.get('top_three_workload_share_10d'),
            'bullpen_workload_total_10d': workload.get('bullpen_workload_total_10d'),
            'bullpen_workload_appearances_10d': workload.get('bullpen_workload_appearances_10d'),
            'window_days': workload.get('window_days'),
        }),
        'clean_options': list(clean_options),
        'story_evidence': {
            'primary_story': narrative.get('primary_story') or feed.get('primary_narrative'),
            'supporting_observations': list(observations),
            'supporting_facts': dict(facts),
        },
        'evidence_version': EVIDENCE_VERSION,
    }
    return blocks
