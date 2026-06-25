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


CAPABILITY = 'story_evidence_case_v1'
VERSION = '2026-06-25.v1'

MAX_SENTENCES = 3
NAME_LIMIT = 3
# Below these, a delta is noise, not evidence — omit it (prefer under-claiming).
MIN_MEANINGFUL_IP_DELTA = 0.3
MIN_MEANINGFUL_PCT_DELTA = 2.0


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


# ── Per-type evidence cases ───────────────────────────────────────────────────
# Each returns an ordered list of raw sentence strings (strongest, corroborating,
# meaning); _assemble() filters, de-duplicates, and caps them.

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
    parts.append('A steady pitching line is sitting on a heavier real workload')
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
    parts.append('The late innings are riding a few arms more than the roster spreads them')
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
    parts.append('The manager has more than one rested way through the late innings')
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
    parts.append('The manager knows who is ready late without guessing')
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
    parts.append('Who gets the biggest outs has changed, even with a similar-looking roster')
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
    parts.append('That leaves the roster looking deeper than the group the manager can actually use')
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
    parts.append('The trusted lane is narrower than the full board makes it look')
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
    parts.append('The soft spot is the path to the late arms, not the arms themselves')
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


def build_evidence_case(frame: Any, *, story_type: Any = None) -> str:
    """Build the curated Evidence-section text for one construction frame.

    Returns ``''`` when no case can be built (unsupported type or a frame with no
    facts), so the blueprint can fall back to the existing beat text. Never
    mutates the frame. Deterministic.
    """
    frame = _dict(frame)
    builder = _BUILDERS.get(frame.get('observation_type'))
    if builder is None:
        return ''
    return _assemble(builder(frame))


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
    }


__all__ = [
    'CAPABILITY',
    'VERSION',
    'MAX_SENTENCES',
    'NAME_LIMIT',
    'MIN_MEANINGFUL_IP_DELTA',
    'MIN_MEANINGFUL_PCT_DELTA',
    'SUPPORTED_OBSERVATION_TYPES',
    'build_evidence_case',
    'evidence_case_report',
]
