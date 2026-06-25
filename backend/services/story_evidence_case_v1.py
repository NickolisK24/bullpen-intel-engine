"""Evidence Case builder (V2) — the Story Blueprint's curated Evidence section.

The Editorial Calibration Lab found the Evidence section to be the weakest part
of a BaseballOS story: it stitched the baseline and cause beats together into a
list of short declaratives that repeated facts, presented tiny deltas as
meaningful, read like a diff report, and sometimes named a different group than
the headline did.

This module rebuilds the Evidence section as a short BUILT CASE from the same
structured construction-frame facts the story already rests on — no new baseball
data, no prediction, no LLM. For each internal observation type it composes, in
order:

    1. the strongest single piece of support,
    2. one corroborating fact,
    3. one plain-language meaning sentence (what the numbers add up to),

capped at three sentences, de-duplicated, with consistent player names and
correct singular/plural grammar. Tiny, non-meaningful deltas are omitted rather
than dressed up as evidence (prefer under-claiming).

The closing meaning sentence is drawn deterministically from a small bank of
approved, fact-free variants (keyed by ``variety_key``), so two same-type cases
in the same feed do not share identical sentence scaffolding while their facts
stay exactly as the frame reports them (Feed Variety Pass).

It is deterministic and additive: when it cannot build a case (an unsupported
type, or a frame without facts) it returns ``''`` and the blueprint falls back to
the existing baseline+cause text, so output is never lost. The internal editorial
intent is not exposed; only frame facts are used, and only in plain language.
"""

from __future__ import annotations

from typing import Any

from services.story_observation_engine import (
    TYPE_BRIDGE_INSTABILITY,
    TYPE_CONCENTRATION_PRESSURE,
    TYPE_CORE_TRANSITION,
    TYPE_DEPTH_PRESSURE,
    TYPE_OPTIONALITY_STRENGTH,
    TYPE_ROTATION_PRESSURE,
    TYPE_STABLE_CORE,
    TYPE_TRUST_LANE_PRESSURE,
)
from services.story_voice_library_v1 import stable_voice_index


CAPABILITY = 'story_evidence_case_v1'
VERSION = '2026-06-25.v2'

MAX_SENTENCES = 3
NAME_LIMIT = 3
# Below these, a delta is noise, not evidence — omit it (prefer under-claiming).
MIN_MEANINGFUL_IP_DELTA = 0.3
MIN_MEANINGFUL_PCT_DELTA = 2.0

# Approved, fact-free closing "meaning" sentences per observation type. The first
# is the canonical line (used when no variety_key is given, keeping output
# backward-compatible); the alternates let same-type cases differ in the feed
# without changing any fact. All clear the engine's guardrail vocabularies.
MEANING_VARIANTS = {
    TYPE_ROTATION_PRESSURE: (
        'A steady pitching line is sitting on a heavier real workload',
        'The result looks routine; the innings underneath it are not',
        'A clean line can hide how much the bullpen is carrying',
    ),
    TYPE_CONCENTRATION_PRESSURE: (
        'The late innings are riding a few arms more than the roster spreads them',
        'The work is gathering on a small group rather than the whole bullpen',
        'A few arms are carrying more than their share of the late work',
    ),
    TYPE_OPTIONALITY_STRENGTH: (
        'The manager has more than one rested way through the late innings',
        'There is more than one clean path to the end of a close game',
        'Late-inning choices like these are what flexibility looks like',
    ),
    TYPE_STABLE_CORE: (
        'The manager knows who is ready late without guessing',
        'A settled group takes the guesswork out of the late innings',
        'There is no question about who handles the end of a game',
    ),
    TYPE_CORE_TRANSITION: (
        'Who gets the biggest outs has changed, even with a similar-looking roster',
        'The names that finish games are not the ones from a month ago',
        'The late-inning order has been redrawn under a familiar roster',
    ),
    TYPE_DEPTH_PRESSURE: (
        'That leaves the roster looking deeper than the group the manager can actually use',
        'The usable group is smaller than the roster line suggests',
        'On paper the bullpen looks deeper than the arms truly in the plan',
    ),
    TYPE_TRUST_LANE_PRESSURE: (
        'The trusted lane is narrower than the full board makes it look',
        'The list of arms is long; the list of trusted arms is short',
        'A full board and a short circle of trust are not the same thing',
    ),
    TYPE_BRIDGE_INSTABILITY: (
        'The soft spot is the path to the late arms, not the arms themselves',
        'The challenge is the bridge to the closer, not the closer',
        'Reaching the late arms is harder than the late arms themselves',
    ),
}


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _clean(value: Any) -> str:
    return ' '.join(str(value or '').strip().split())


def _num(value: Any):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _intval(value: Any):
    n = _num(value)
    return int(n) if n is not None else None


def _fmt(value: Any):
    """Format a number the house way: one decimal, trailing zeros stripped."""
    n = _num(value)
    if n is None:
        return None
    return f'{n:.1f}'.rstrip('0').rstrip('.')


def _arm(count) -> str:
    return 'arm' if _intval(count) == 1 else 'arms'


def _be(count) -> str:
    return 'is' if _intval(count) == 1 else 'are'


def _way(count) -> str:
    return 'way' if _intval(count) == 1 else 'ways'


def _name_from_row(row: Any) -> str:
    if isinstance(row, str):
        return _clean(row)
    return _clean(_dict(row).get('name'))


def _join_names(names: Any, *, limit: int | None = NAME_LIMIT):
    rows: list[str] = []
    for row in _list(names):
        name = _name_from_row(row)
        if name and name not in rows:
            rows.append(name)
    if limit is not None:
        rows = rows[:limit]
    if not rows:
        return None
    if len(rows) == 1:
        return rows[0]
    if len(rows) == 2:
        return f'{rows[0]} and {rows[1]}'
    return f"{', '.join(rows[:-1])}, and {rows[-1]}"


def _sentence(text: Any):
    text = _clean(text)
    if not text:
        return None
    if text[-1] not in '.!?':
        text = f'{text}.'
    return text


def _facts(frame: dict, key: str) -> dict:
    return _dict(_dict(frame.get('story_frame')).get(key))


def _key_text(variety_key: Any) -> str:
    if isinstance(variety_key, (list, tuple)):
        return '|'.join(_clean(part) for part in variety_key if _clean(part))
    return _clean(variety_key)


def _meaning(observation_type: Any, variety_key: Any):
    """Select the closing meaning sentence deterministically.

    Index 0 (the canonical line) when no variety_key is supplied, so callers
    without one stay backward-compatible; otherwise a stable per-story choice.
    """
    variants = MEANING_VARIANTS.get(observation_type) or ()
    if not variants:
        return None
    key = _key_text(variety_key)
    if not key:
        return variants[0]
    index = stable_voice_index((CAPABILITY, VERSION, observation_type, key), len(variants))
    return variants[index]


# ── Per-type evidence cases (factual sentences only; meaning added centrally) ──

def _rotation_pressure(frame: dict) -> list:
    obs = _facts(frame, 'observation_facts')
    cause = _facts(frame, 'cause_facts')
    avg7 = _num(obs.get('rotation_avg_ip_7d'))
    avg14 = _num(obs.get('rotation_avg_ip_14d'))
    early = _num(obs.get('early_bullpen_entry_rate'))
    coverage = _num(cause.get('bullpen_coverage_ip_7d'))

    if avg7 is not None and avg14 is not None and (avg14 - avg7) >= MIN_MEANINGFUL_IP_DELTA:
        starts = f'Starts have shortened to {_fmt(avg7)} innings from {_fmt(avg14)} over the prior two weeks'
    elif avg7 is not None:
        starts = f'Starts have run {_fmt(avg7)} innings over the last week'
    else:
        starts = None
    coverage_line = (
        f'That hands the relief group about {_fmt(coverage)} innings a game the rotation usually covers'
        if coverage is not None else None
    )

    parts = []
    if early is not None:
        parts.append(f'The bullpen has been entering before the sixth in {_fmt(early)}% of recent games')
        parts.append(starts or coverage_line)
    else:
        parts.append(starts)
        parts.append(coverage_line)
    return parts


def _concentration_pressure(frame: dict) -> list:
    head = _facts(frame, 'headline_facts')
    base = _facts(frame, 'baseline_facts')
    names = _join_names(head.get('top_three_relievers'))
    share = _num(head.get('top_three_workload_share_10d'))
    delta = _num(base.get('top_three_share_delta_vs_league'))

    parts = []
    if names and share is not None:
        parts.append(f"{names} have handled {_fmt(share)}% of the bullpen's recent work")
    elif share is not None:
        parts.append(f"A few arms have handled {_fmt(share)}% of the bullpen's recent work")
    if delta is not None and delta >= MIN_MEANINGFUL_PCT_DELTA:
        parts.append(f"That is {_fmt(delta)} points above the league's typical top-three share")
    return parts


def _optionality_strength(frame: dict) -> list:
    obs = _facts(frame, 'observation_facts')
    cause = _facts(frame, 'cause_facts')
    paths = _intval(obs.get('practical_close_game_paths_count'))
    clean = _intval(obs.get('clean_workload_options_count'))
    clean_names = _join_names(cause.get('clean_workload_options'))

    parts = []
    if paths is not None:
        parts.append(f'The bullpen has {paths} clean {_way(paths)} to close a game right now')
    elif clean is not None:
        parts.append(f'{clean} {_arm(clean)} {_be(clean)} rested and clean for the late innings')
    if clean_names:
        parts.append(f'The rested group is led by {clean_names}')
    return parts


def _stable_core(frame: dict) -> list:
    head = _facts(frame, 'headline_facts')
    base = _facts(frame, 'baseline_facts')
    names = _join_names(head.get('current_operational_core'))
    pct = _num(head.get('core_stability_pct'))
    previous = base.get('previous_operational_core')

    parts = []
    if names and pct is not None:
        parts.append(f'{names} have handled {_fmt(pct)}% of the recent late-inning work')
    elif names:
        parts.append(f'The late innings have run through {names}')
    if previous:
        parts.append('It is the same trusted group as before')
    return parts


def _core_transition(frame: dict) -> list:
    head = _facts(frame, 'headline_facts')
    base = _facts(frame, 'baseline_facts')
    cause = _facts(frame, 'cause_facts')
    current = _join_names(head.get('current_operational_core'))
    previous = _join_names(base.get('previous_operational_core'))
    added = _join_names(cause.get('new_core_members'))
    departed = _join_names(cause.get('departed_core_members'))

    parts = []
    if current and previous:
        parts.append(f'The late innings now run through {current}, where they recently ran through {previous}')
    elif current:
        parts.append(f'The late innings now run through {current}')
    moves = []
    if added:
        moves.append(f'added {added}')
    if departed:
        moves.append(f'moved on from {departed}')
    if moves:
        parts.append('The route ' + ' and '.join(moves))
    return parts


def _depth_pressure(frame: dict) -> list:
    obs = _facts(frame, 'observation_facts')
    base = _facts(frame, 'baseline_facts')
    cause = _facts(frame, 'cause_facts')
    inactive = _intval(obs.get('inactive_bullpen_arms_count'))
    il = _intval(cause.get('il_bullpen_arms_count'))
    active = _intval(base.get('active_bullpen_arms_count'))

    parts = []
    if inactive is not None:
        line = f'{inactive} {_arm(inactive)} {_be(inactive)} outside the current plan'
        if il:
            line += f', {il} of them on the IL'
        parts.append(line)
    if active is not None:
        parts.append(f'The live bullpen is down to {active} {_arm(active)}')
    return parts


def _trust_lane_pressure(frame: dict) -> list:
    obs = _facts(frame, 'observation_facts')
    cause = _facts(frame, 'cause_facts')
    available = _intval(obs.get('available_arms_count'))
    clean = _intval(obs.get('clean_workload_options_count'))
    clean_names = _join_names(cause.get('clean_workload_options'))

    parts = []
    if available is not None and clean is not None:
        parts.append(
            f'The board lists {available} available {_arm(available)}, '
            f'but only {clean} {_be(clean)} clean and rested for the late innings'
        )
    if clean_names:
        parts.append(f'The dependable late work runs through {clean_names}')
    return parts


def _bridge_instability(frame: dict) -> list:
    obs = _facts(frame, 'observation_facts')
    head = _facts(frame, 'headline_facts')
    core = _join_names(head.get('current_operational_core'))
    volatile = _intval(obs.get('volatile_middle_count'))
    early = _num(obs.get('early_bullpen_entry_rate'))
    coverage = _num(obs.get('bullpen_coverage_ip_7d'))

    parts = []
    if core and volatile is not None:
        parts.append(
            f'The late-game core — {core} — is settled, but the path to it runs through '
            f'{volatile} unsettled middle {_arm(volatile)}'
        )
    elif volatile is not None:
        parts.append(f'A settled late group sits behind {volatile} unsettled middle {_arm(volatile)}')
    if early is not None:
        parts.append(f'Starters are handing off early, entering before the sixth in {_fmt(early)}% of recent games')
    elif coverage is not None:
        parts.append(f'The bullpen is covering {_fmt(coverage)} innings a game to reach them')
    return parts


_BUILDERS = {
    TYPE_ROTATION_PRESSURE: _rotation_pressure,
    TYPE_CONCENTRATION_PRESSURE: _concentration_pressure,
    TYPE_OPTIONALITY_STRENGTH: _optionality_strength,
    TYPE_STABLE_CORE: _stable_core,
    TYPE_CORE_TRANSITION: _core_transition,
    TYPE_DEPTH_PRESSURE: _depth_pressure,
    TYPE_TRUST_LANE_PRESSURE: _trust_lane_pressure,
    TYPE_BRIDGE_INSTABILITY: _bridge_instability,
}

SUPPORTED_OBSERVATION_TYPES = tuple(_BUILDERS)


def _assemble(parts: list) -> str:
    """Filter, de-duplicate (no repeated sentence) and cap at MAX_SENTENCES."""
    seen: set = set()
    out: list = []
    for part in parts:
        sentence = _sentence(part)
        if not sentence:
            continue
        key = sentence.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(sentence)
        if len(out) >= MAX_SENTENCES:
            break
    return ' '.join(out)


def build_evidence_case(frame: Any, *, story_type: Any = None, variety_key: Any = None) -> str:
    """Build the curated Evidence-section text for one construction frame.

    ``variety_key`` (e.g. the story id) selects the closing meaning sentence so
    same-type cases differ across a feed; without it the canonical line is used.
    Returns ``''`` when no case can be built (unsupported type or a frame with no
    facts), so the blueprint can fall back to the existing beat text. Never
    mutates the frame. Deterministic.
    """
    frame = _dict(frame)
    observation_type = frame.get('observation_type')
    builder = _BUILDERS.get(observation_type)
    if builder is None:
        return ''
    parts = list(builder(frame))
    parts.append(_meaning(observation_type, variety_key))
    return _assemble(parts)


def evidence_case_report() -> dict:
    """Compact deterministic metadata for audit tests."""
    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'deterministic': True,
        'max_sentences': MAX_SENTENCES,
        'name_limit': NAME_LIMIT,
        'min_meaningful_ip_delta': MIN_MEANINGFUL_IP_DELTA,
        'min_meaningful_pct_delta': MIN_MEANINGFUL_PCT_DELTA,
        'supported_observation_types': list(SUPPORTED_OBSERVATION_TYPES),
        'meaning_variant_counts': {k: len(v) for k, v in MEANING_VARIANTS.items()},
    }


__all__ = [
    'CAPABILITY',
    'VERSION',
    'MAX_SENTENCES',
    'NAME_LIMIT',
    'MIN_MEANINGFUL_IP_DELTA',
    'MIN_MEANINGFUL_PCT_DELTA',
    'MEANING_VARIANTS',
    'SUPPORTED_OBSERVATION_TYPES',
    'build_evidence_case',
    'evidence_case_report',
]
