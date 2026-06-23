"""Story Writer V1.

Deterministic backend writer for Story Construction Engine frames. It converts
structured facts into BaseballOS-style written observations without external
text generation, public routes, predictions, rankings, betting language, or
scoring changes.
"""

from __future__ import annotations

from typing import Any

from services.story_construction_engine import (
    build_story_construction_engine_v1,
    construct_team_story_frames,
)
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
from services.story_voice_library_v1 import (
    BEAT_AVAILABILITY_DEPTH,
    BEAT_BRIDGE,
    BEAT_COVERAGE_PRESSURE,
    BEAT_DEPTH_CONSTRAINT,
    BEAT_ROUTE_CHANGE,
    BEAT_SUSTAINABILITY_QUESTION,
    BEAT_TRUST_LANE,
    DENIED_PUBLIC_PHRASES,
    render_voice_line,
)


CAPABILITY = 'story_writer_v1'
VERSION = '2026-06-21.v1'
SOURCE = 'backend'

SECTION_KEYS = (
    'headline',
    'observation_paragraph',
    'baseline_paragraph',
    'cause_paragraph',
    'constraint_paragraph',
)

BANNED_TERMS = (
    'bet',
    'betting',
    'odds',
    'probability',
    'projection',
    'projected',
    'predict',
    'prediction',
    'rank',
    'ranking',
    'score',
    'confidence score',
)

ROBOTIC_TERMS = (
    'context indicates',
    'observation type',
    'constraint facts',
    'baseline facts',
    'optionality band',
    'depth pressure band',
    'forward constraint is',
    'the frame shows',
    'the frame marks',
    *DENIED_PUBLIC_PHRASES,
)


def _dict(value):
    return value if isinstance(value, dict) else {}


def _list(value):
    return value if isinstance(value, list) else []


def _present(value):
    if value is None:
        return False
    if value == '':
        return False
    if isinstance(value, (list, dict)) and not value:
        return False
    return True


def _clean_text(value):
    return ' '.join(str(value or '').strip().split())


def _team(frame):
    return (
        _clean_text(_dict(frame).get('team_name'))
        or _clean_text(_dict(_dict(frame).get('story_frame')).get('team_name'))
        or 'This bullpen'
    )


def _possessive(value):
    text = _clean_text(value)
    if not text:
        return 'This bullpen'
    if text.lower().endswith('sox'):
        return f"{text}'"
    return f"{text}'" if text.lower().endswith('s') else f"{text}'s"


def _fmt(value, *, suffix=''):
    if value is None:
        return None
    if isinstance(value, float):
        text = f'{value:.1f}'.rstrip('0').rstrip('.')
    else:
        text = str(value)
    return f'{text}{suffix}'


def _lte(value, threshold):
    try:
        return float(value) <= threshold
    except (TypeError, ValueError):
        return False


def _name_from_row(row):
    if isinstance(row, str):
        return _clean_text(row)
    return _clean_text(_dict(row).get('name'))


def _join_names(names, *, limit=None):
    rows = []
    for row in _list(names):
        name = _name_from_row(row)
        if name and name not in rows:
            rows.append(name)
    names = rows
    if limit is not None:
        try:
            names = names[:int(limit)]
        except (TypeError, ValueError):
            pass
    if not names:
        return None
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f'{names[0]} and {names[1]}'
    return f"{', '.join(names[:-1])}, and {names[-1]}"


def _sentence(text):
    text = _clean_text(text)
    if not text:
        return None
    if text[-1] not in '.!?':
        text = f'{text}.'
    return text


def _paragraph(*sentences):
    rows = []
    seen = set()
    for sentence in sentences:
        sentence = _sentence(sentence)
        if not sentence:
            continue
        key = sentence.lower()
        if key in seen:
            continue
        seen.add(key)
        rows.append(sentence)
    return ' '.join(rows) if rows else None


def _sections(**values):
    return {key: values.get(key) for key in SECTION_KEYS}


def _frame_sections(frame):
    return _dict(_dict(frame).get('story_frame'))


def _facts(frame, key):
    return _dict(_frame_sections(frame).get(key))


def _count_word(value, singular, plural=None):
    plural = plural or f'{singular}s'
    return singular if value == 1 else plural


def _voice_opening(frame, beat, *, names=None, extra_parts=()):
    team = _team(frame)
    return render_voice_line(
        beat,
        stable_parts=(
            _dict(frame).get('team_id'),
            _dict(frame).get('team_abbreviation'),
            _dict(frame).get('observation_type'),
            _clean_text(names),
            *tuple(extra_parts or ()),
        ),
        team=team,
        possessive=_possessive(team),
        names=names or 'the bullpen',
    )


def _has_banned_language(text):
    lower = _clean_text(text).lower()
    return any(term in lower for term in BANNED_TERMS)


def _has_robotic_language(text):
    lower = _clean_text(text).lower()
    return any(term in lower for term in ROBOTIC_TERMS)


def _all_output_text(output):
    sections = _dict(output.get('written_observation'))
    return ' '.join(_clean_text(value) for value in sections.values() if value)


def validate_written_observation(output):
    text = _all_output_text(output)
    return {
        'passed': bool(text) and not _has_banned_language(text) and not _has_robotic_language(text),
        'contains_banned_language': _has_banned_language(text),
        'contains_robotic_language': _has_robotic_language(text),
        'has_text': bool(text),
    }


# Distribution-aware league phrasing for the rotation-pressure story's baseline
# beat. rotation_avg_ip_7d is better-is-higher (longer starts ease bullpen load),
# so the engine's value-neutral position bands read as starter length: a
# below-average 7-day average is shorter than the league norm. Descriptive
# context only — no rank, recommendation, prediction, or superlative-singular
# ("longest"/"most") language (governance C1K).
_ROTATION_LENGTH_BASELINE_SENTENCE = {
    'below_average': 'That is shorter than the league norm for starter length',
    'about_typical': 'That is around the league norm for starter length',
    'above_average': 'That is longer than the league norm for starter length',
    'well_above_average': 'That is well above the league norm for starter length',
    'among_highest': 'That recent starter length is among the longer rotations in baseball',
}


def _rotation_length_band(baseline):
    """The supported comparison band, only when the baseline read is available."""
    read = baseline.get('baseline_read') if isinstance(baseline, dict) else None
    if not isinstance(read, dict) or read.get('available') is not True:
        return None
    comparison = read.get('comparison')
    return comparison if comparison in _ROTATION_LENGTH_BASELINE_SENTENCE else None


def _rotation_length_baseline_sentence(baseline):
    band = _rotation_length_band(baseline)
    return _ROTATION_LENGTH_BASELINE_SENTENCE.get(band) if band else None


def _rotation_pressure(frame):
    team = _team(frame)
    headline = _facts(frame, 'headline_facts')
    observed = _facts(frame, 'observation_facts')
    baseline = _facts(frame, 'baseline_facts')
    cause = _facts(frame, 'cause_facts')
    interpretation = _facts(frame, 'interpretation_facts')
    constraint = _facts(frame, 'constraint_facts')

    avg_7 = headline.get('rotation_avg_ip_7d') or observed.get('rotation_avg_ip_7d')
    avg_14 = headline.get('rotation_avg_ip_14d') or observed.get('rotation_avg_ip_14d')
    trend = headline.get('rotation_ip_trend') or observed.get('rotation_ip_trend')
    early_rate = observed.get('early_bullpen_entry_rate')
    coverage = cause.get('bullpen_coverage_ip_7d') or interpretation.get('bullpen_coverage_ip_7d')
    short_starts = _present(avg_7) and _present(avg_14) and avg_7 < avg_14

    return _sections(
        headline=_voice_opening(frame, BEAT_COVERAGE_PRESSURE, extra_parts=(avg_7, avg_14, trend)),
        observation_paragraph=_paragraph(
            (
                f"The starters are averaging {_fmt(avg_7)} innings over the last week"
                if _present(avg_7) else None
            ),
            (
                f"That recent starter length is down {_fmt(abs(trend))} innings from the two-week mark"
                if _present(trend) and trend < 0 else None
            ),
            (
                f"The bullpen has entered before the sixth in {_fmt(early_rate, suffix='%')} of recent games"
                if _present(early_rate) else None
            ),
        ),
        baseline_paragraph=_paragraph(
            # Distribution-aware league read of recent starter length when
            # available; adds "compared to what?" context alongside the team's own
            # 14-day mark. The seven-day restate is dropped when the league read is
            # present (it already anchors the seven-day value) to avoid stacking.
            _rotation_length_baseline_sentence(baseline),
            (
                f"The comparison point is {_fmt(avg_14)} starter innings over the full 14-day window"
                if _present(avg_14) else None
            ),
            (
                f"The current seven-day handoff is {_fmt(avg_7)} innings"
                if _present(avg_7) and not _rotation_length_band(baseline) else None
            ),
        ),
        cause_paragraph=_paragraph(
            (
                f"The starters are not covering as many innings as the recent baseline"
                if short_starts else None
            ),
            (
                f"Shorter starts are pushing {_fmt(coverage)} bullpen innings per game into the relief group"
                if _present(coverage) else None
            ),
            (
                f"The rotation has been handing the game to the bullpen earlier"
                if _present(early_rate) and early_rate >= 40.0 else None
            ),
        ),
        constraint_paragraph=_paragraph(
            (
                f"If short starts continue, the bullpen has fewer ways to spread the middle innings"
                if _present(constraint.get('bullpen_coverage_ip_7d')) or _present(coverage) else None
            ),
        ),
    )


# Distribution-aware league phrasing for the workload concentration story's
# baseline beat. Descriptive context only — no rank, recommendation, prediction,
# or superlative-singular ("highest"/"most") language (governance C1E).
_CONCENTRATION_BASELINE_SENTENCE = {
    'among_highest': 'This bullpen has been among the more concentrated workloads in baseball recently',
    'well_above_average': 'That concentration sits well above the league norm',
    'above_average': 'That concentration sits above the league norm',
    'about_typical': 'That concentration is around the league norm',
    'below_average': 'That concentration is more spread out than a typical bullpen',
}


def _baseline_band(baseline):
    """The supported comparison band, only when the baseline read is available."""
    read = baseline.get('baseline_read') if isinstance(baseline, dict) else None
    if not isinstance(read, dict) or read.get('available') is not True:
        return None
    comparison = read.get('comparison')
    return comparison if comparison in _CONCENTRATION_BASELINE_SENTENCE else None


def _concentration_baseline_sentence(baseline):
    band = _baseline_band(baseline)
    return _CONCENTRATION_BASELINE_SENTENCE.get(band) if band else None


# Secondary distribution-aware phrasing for lead-arm (single most-used reliever)
# workload reliance, layered under the primary top-three concentration read.
# top_one_share is higher-is-more-concentrated (not "better"). Descriptive context
# only — no rank, recommendation, prediction, or superlative-singular
# ("highest"/"most used") language (governance C1L).
_LEAD_ARM_BASELINE_SENTENCE = {
    'below_average': 'The lead arm is carrying less of the workload than a typical bullpen',
    'about_typical': 'The lead arm is carrying about a typical share of the workload',
    'above_average': 'The lead arm is carrying more of the workload than a typical bullpen',
    'well_above_average': 'The lead arm is carrying well above a typical share of the workload',
    'among_highest': 'The lead arm is near the upper end of recent single-arm workload',
}


def _lead_arm_band(baseline):
    """The supported lead-arm comparison band, only when its read is available."""
    read = baseline.get('lead_arm_baseline_read') if isinstance(baseline, dict) else None
    if not isinstance(read, dict) or read.get('available') is not True:
        return None
    comparison = read.get('comparison')
    return comparison if comparison in _LEAD_ARM_BASELINE_SENTENCE else None


def _lead_arm_baseline_sentence(baseline):
    band = _lead_arm_band(baseline)
    return _LEAD_ARM_BASELINE_SENTENCE.get(band) if band else None


def _concentration_pressure(frame):
    team = _team(frame)
    headline = _facts(frame, 'headline_facts')
    observed = _facts(frame, 'observation_facts')
    baseline = _facts(frame, 'baseline_facts')
    cause = _facts(frame, 'cause_facts')
    interpretation = _facts(frame, 'interpretation_facts')
    constraint = _facts(frame, 'constraint_facts')

    names = _join_names(headline.get('top_three_relievers'))
    share = headline.get('top_three_workload_share_10d') or observed.get('top_three_workload_share_10d')
    league = baseline.get('league_top_three_workload_share_10d')
    delta = baseline.get('top_three_share_delta_vs_league')
    total = observed.get('bullpen_workload_total_10d')
    trend = cause.get('rotation_ip_trend')
    paths = interpretation.get('practical_close_game_paths_count')
    core = _join_names(constraint.get('current_operational_core'))
    route_names = core or names
    band = observed.get('concentration_band') or interpretation.get('concentration_band')
    narrow_route = band in {'narrow', 'concentrated'} or _lte(paths, 3)
    short_starts = _present(trend) and trend < 0

    return _sections(
        headline=_voice_opening(
            frame,
            BEAT_SUSTAINABILITY_QUESTION,
            names=names or route_names or 'the same relievers',
            extra_parts=(share, band, paths),
        ),
        observation_paragraph=_paragraph(
            (
                "The bullpen is functioning, but the meaningful innings are bunching around a smaller group"
                if narrow_route else None
            ),
            (
                f"{names} have handled {_fmt(share, suffix='%')} of the bullpen workload"
                if names and _present(share) else None
            ),
            (
                f"The top group has handled {_fmt(share, suffix='%')} of the bullpen workload"
                if _present(share) and not names else None
            ),
            (
                f"That comes inside a {_fmt(total)}-pitch bullpen window"
                if _present(total) else None
            ),
        ),
        baseline_paragraph=_paragraph(
            # Distribution-aware league read when available; otherwise fall back to
            # the existing league-average comparison (never both, to avoid stacking
            # two "vs league" statements).
            _concentration_baseline_sentence(baseline),
            (
                f"The league comparison is {_fmt(league, suffix='%')} for top-three bullpen workload"
                if _present(league) and not _baseline_band(baseline) else None
            ),
            (
                f"That puts this bullpen {_fmt(delta)} percentage points above that baseline"
                if _present(delta) and not _baseline_band(baseline) else None
            ),
            # Secondary, optional lead-arm read: single-arm reliance vs the league,
            # voiced only when the separate lead-arm baseline read is available. The
            # top-three comparison above stays primary; absent/guarded reads add
            # nothing and preserve the existing C1E copy.
            _lead_arm_baseline_sentence(baseline),
        ),
        cause_paragraph=_paragraph(
            (
                f"The starters are not covering as many innings as the recent baseline"
                if short_starts else None
            ),
            (
                f"Starter length is down {_fmt(abs(trend))} innings against the 14-day mark"
                if _present(trend) and trend < 0 else None
            ),
            (
                f"The same arms are carrying the meaningful work: {route_names}"
                if route_names else None
            ),
            (
                f"The bullpen has {_fmt(paths)} close-game {_count_word(paths, 'choice')}"
                if _present(paths) else None
            ),
        ),
        constraint_paragraph=_paragraph(
            (
                f"If this pattern continues, the margin for spreading the work stays thin around {route_names}"
                if route_names else None
            ),
        ),
    )


# Distribution-aware league phrasing for the positive optionality/depth story's
# baseline beat. Same clean-options metric and bands as the trust-lane story, but
# voiced for a healthy-depth narrative (better-is-higher). Descriptive context
# only — no rank, recommendation, prediction, or superlative-singular language
# (governance C1I). Reuses the shared C1H band reader; does not recompute the read.
_OPTIONALITY_DEPTH_BASELINE_SENTENCE = {
    'below_average': 'That is still thinner than the league norm',
    'about_typical': 'That is about as deep as a typical bullpen',
    'above_average': 'That is deeper than the league norm',
    'well_above_average': 'That clean lane sits well above the league norm',
    'among_highest': 'That puts them among the deeper clean-options groups in baseball',
}


def _optionality_depth_baseline_sentence(baseline):
    band = _clean_options_band(baseline)
    return _OPTIONALITY_DEPTH_BASELINE_SENTENCE.get(band) if band else None


def _optionality_strength(frame):
    team = _team(frame)
    headline = _facts(frame, 'headline_facts')
    observed = _facts(frame, 'observation_facts')
    baseline = _facts(frame, 'baseline_facts')
    cause = _facts(frame, 'cause_facts')
    interpretation = _facts(frame, 'interpretation_facts')
    constraint = _facts(frame, 'constraint_facts')

    paths = headline.get('practical_close_game_paths_count') or observed.get('practical_close_game_paths_count')
    band = headline.get('optionality_band') or observed.get('optionality_band')
    available = observed.get('available_arms_count') or baseline.get('available_arms_count')
    clean_count = observed.get('clean_workload_options_count')
    secondary_count = observed.get('secondary_options_count')
    clean_names = _join_names(cause.get('clean_workload_options'))
    secondary_names = _join_names(cause.get('secondary_options'))
    concentration = interpretation.get('concentration_band')
    unavailable = constraint.get('unavailable_arms_count')
    has_unavailable = _present(unavailable) and unavailable > 0

    return _sections(
        headline=_voice_opening(
            frame,
            BEAT_AVAILABILITY_DEPTH,
            names=clean_names or secondary_names or 'the late relievers',
            extra_parts=(paths, band, unavailable),
        ),
        observation_paragraph=_paragraph(
            (
                f"The bullpen has {_fmt(paths)} close-game {_count_word(paths, 'choice')}"
                if _present(paths) else None
            ),
            (
                f"That leaves the late-game map {band}"
                if _present(band) else None
            ),
        ),
        baseline_paragraph=_paragraph(
            (
                f"The active board includes {_fmt(available)} available {_count_word(available, 'arm')}"
                if _present(available) else None
            ),
            (
                f"There are {_fmt(clean_count)} low-workload late-inning {_count_word(clean_count, 'choice', 'choices')}"
                if _present(clean_count) and clean_count > 0 else None
            ),
            # Distribution-aware league depth read of the clean-options count,
            # enriching the internal counts above with "compared to what?" context.
            # Absent or guarded reads return None and leave the copy unchanged.
            _optionality_depth_baseline_sentence(baseline),
        ),
        cause_paragraph=_paragraph(
            (
                f"The clearest late-inning choices include {clean_names}"
                if clean_names else None
            ),
            (
                f"The secondary choices include {secondary_names}"
                if secondary_names else None
            ),
            (
                f"Coverage is also coming from {_fmt(secondary_count)} secondary {_count_word(secondary_count, 'option')}"
                if _present(secondary_count) and secondary_count > 0 else None
            ),
            (
                f"The workload pattern is {concentration}"
                if _present(concentration) else None
            ),
        ),
        constraint_paragraph=_paragraph(
            (
                f"If the same game shape returns, the club can choose among multiple late-inning options rather than force one route"
                if _present(paths) else None
            ),
            (
                f"The current plan has to work around {_fmt(unavailable)} unavailable {_count_word(unavailable, 'arm')}"
                if has_unavailable else None
            ),
        ),
    )


def _stable_core(frame):
    team = _team(frame)
    headline = _facts(frame, 'headline_facts')
    observed = _facts(frame, 'observation_facts')
    baseline = _facts(frame, 'baseline_facts')
    cause = _facts(frame, 'cause_facts')
    interpretation = _facts(frame, 'interpretation_facts')
    constraint = _facts(frame, 'constraint_facts')

    current = _join_names(headline.get('current_operational_core') or cause.get('current_operational_core'))
    previous = _join_names(baseline.get('previous_operational_core'))
    retention = (
        observed.get('core_retention_count')
        if _present(observed.get('core_retention_count'))
        else cause.get('core_retention_count')
    )
    stability = observed.get('core_stability_pct')
    concentration = interpretation.get('concentration_band')
    core_size = constraint.get('current_core_size')

    return _sections(
        headline=_voice_opening(
            frame,
            BEAT_AVAILABILITY_DEPTH,
            names=current or 'the current late group',
            extra_parts=(previous, retention, stability),
        ),
        observation_paragraph=_paragraph(
            (
                f"The current core is {current}"
                if current else None
            ),
            (
                f"The same core is still carrying the main bullpen route"
                if _present(observed.get('stability_band')) else None
            ),
        ),
        baseline_paragraph=_paragraph(
            (
                f"The previous core was {previous}"
                if previous else None
            ),
            (
                f"The current group retained {_fmt(retention)} {_count_word(retention, 'member')} from that baseline"
                if _present(retention) else None
            ),
        ),
        cause_paragraph=_paragraph(
            (
                f"The current group carried {_fmt(stability, suffix='%')} of the route overlap"
                if _present(stability) else None
            ),
            (
                f"The workload pattern is {concentration}"
                if _present(concentration) else None
            ),
        ),
        constraint_paragraph=_paragraph(
            (
                f"If the next game tightens, the route points back through {current}"
                if current else None
            ),
            (
                f"If the next game tightens, the route points back through the {_fmt(core_size)}-arm core"
                if not current and _present(core_size) else None
            ),
        ),
    )


def _core_transition(frame):
    team = _team(frame)
    headline = _facts(frame, 'headline_facts')
    observed = _facts(frame, 'observation_facts')
    baseline = _facts(frame, 'baseline_facts')
    cause = _facts(frame, 'cause_facts')
    interpretation = _facts(frame, 'interpretation_facts')
    constraint = _facts(frame, 'constraint_facts')

    current = _join_names(headline.get('current_operational_core') or cause.get('current_operational_core'))
    previous = _join_names(baseline.get('previous_operational_core'))
    new_members = _join_names(headline.get('new_core_members') or cause.get('new_core_members'))
    departed = _join_names(cause.get('departed_core_members'))
    changes = headline.get('core_change_count') or observed.get('core_change_count')
    stability = observed.get('core_stability_pct') or interpretation.get('core_stability_pct')
    retention = (
        interpretation.get('core_retention_count')
        if _present(interpretation.get('core_retention_count'))
        else constraint.get('core_retention_count')
    )

    return _sections(
        headline=_voice_opening(
            frame,
            BEAT_ROUTE_CHANGE,
            names=current or new_members or 'the current late group',
            extra_parts=(previous, changes, retention),
        ),
        observation_paragraph=_paragraph(
            (
                f"The important-outs route now runs through {current}"
                if current else None
            ),
            (
                f"That is a {_fmt(changes)}-spot change from the prior route"
                if _present(changes) else None
            ),
        ),
        baseline_paragraph=_paragraph(
            (
                f"The comparison point is the previous route: {previous}"
                if previous else None
            ),
            (
                f"The current route retained {_fmt(retention)} {_count_word(retention, 'arm')} from that baseline"
                if _present(retention) else None
            ),
        ),
        cause_paragraph=_paragraph(
            (
                f"The added arms are {new_members}"
                if new_members else None
            ),
            (
                f"The arms moving out of that route are {departed}"
                if departed else None
            ),
        ),
        constraint_paragraph=_paragraph(
            (
                f"If the next game tightens, the route points back through {current}"
                if current else None
            ),
            (
                f"If the next game tightens, the bullpen is working with {_fmt(retention)} retained {_count_word(retention, 'arm')} from the prior core"
                if not current and _present(retention) else None
            ),
        ),
    )


def _depth_pressure(frame):
    team = _team(frame)
    headline = _facts(frame, 'headline_facts')
    observed = _facts(frame, 'observation_facts')
    baseline = _facts(frame, 'baseline_facts')
    cause = _facts(frame, 'cause_facts')
    interpretation = _facts(frame, 'interpretation_facts')
    constraint = _facts(frame, 'constraint_facts')

    inactive = headline.get('inactive_bullpen_arms_count') or observed.get('inactive_bullpen_arms_count')
    depth_band = headline.get('depth_pressure_band') or observed.get('depth_pressure_band')
    active = baseline.get('active_bullpen_arms_count') or constraint.get('active_bullpen_arms_count')
    il_count = cause.get('il_bullpen_arms_count')
    non_il = cause.get('non_il_inactive_bullpen_arms_count')
    inactive_names = _join_names(cause.get('inactive_bullpen_arms'), limit=4)
    paths = interpretation.get('practical_close_game_paths_count')
    optionality = interpretation.get('optionality_band')

    return _sections(
        headline=_voice_opening(
            frame,
            BEAT_DEPTH_CONSTRAINT,
            names=inactive_names or 'the relief group',
            extra_parts=(inactive, active, depth_band),
        ),
        observation_paragraph=_paragraph(
            (
                f"For {team}, the roster shows {_fmt(active)} bullpen {_count_word(active, 'arm')}, but {_fmt(inactive)} {_count_word(inactive, 'reliever')} are not part of the current game plan"
                if _present(inactive) and _present(active) else None
            ),
            (
                f"For {team}, {_fmt(inactive)} bullpen {_count_word(inactive, 'reliever')} are not part of the current game plan"
                if _present(inactive) and not _present(active) else None
            ),
            (
                f"That leaves the late-inning depth {depth_band}"
                if _present(depth_band) else None
            ),
        ),
        baseline_paragraph=_paragraph(
            (
                f"The roster baseline still shows {_fmt(active)} bullpen {_count_word(active, 'arm')}"
                if _present(active) else None
            ),
        ),
        cause_paragraph=_paragraph(
            (
                f"The inactive group includes {inactive_names}"
                if inactive_names else None
            ),
            (
                f"The depth loss includes {_fmt(il_count)} IL {_count_word(il_count, 'arm')}"
                if _present(il_count) else None
            ),
            (
                f"It also includes {_fmt(non_il)} non-IL inactive {_count_word(non_il, 'arm')}"
                if _present(non_il) else None
            ),
        ),
        constraint_paragraph=_paragraph(
            (
                f"If the roster stays this thin, the manager has fewer ways to cover the late innings than the roster count suggests"
                if _present(paths) or _present(inactive) else None
            ),
            (
                f"The current plan has {_fmt(paths)} close-game {_count_word(paths, 'choice')}"
                if _present(paths) else None
            ),
            (
                f"The available late-inning map is {optionality}"
                if _present(optionality) else None
            ),
        ),
    )


# Distribution-aware league phrasing for the trust-lane story's baseline beat.
# Clean options is better-is-higher, so the engine's value-neutral position bands
# read as lane depth: a below-average clean-options count is a thinner trusted
# lane, an above-average one is deeper. Descriptive context only — no rank,
# recommendation, prediction, or superlative-singular ("deepest"/"most") language
# (governance C1H). Kept separate from the concentration phrasing on purpose.
_CLEAN_OPTIONS_BASELINE_SENTENCE = {
    'below_average': 'That trusted group is thinner than the league norm',
    'about_typical': 'That trusted group is about as deep as the league norm',
    'above_average': 'That trusted group is deeper than the league norm',
    'well_above_average': 'That trusted group sits well above the league norm',
    'among_highest': 'That trusted group is among the deeper clean-options groups in baseball',
}


def _clean_options_band(baseline):
    """The supported comparison band, only when the baseline read is available."""
    read = baseline.get('baseline_read') if isinstance(baseline, dict) else None
    if not isinstance(read, dict) or read.get('available') is not True:
        return None
    comparison = read.get('comparison')
    return comparison if comparison in _CLEAN_OPTIONS_BASELINE_SENTENCE else None


def _clean_options_baseline_sentence(baseline):
    band = _clean_options_band(baseline)
    return _CLEAN_OPTIONS_BASELINE_SENTENCE.get(band) if band else None


def _trust_lane_pressure(frame):
    team = _team(frame)
    headline = _facts(frame, 'headline_facts')
    observed = _facts(frame, 'observation_facts')
    baseline = _facts(frame, 'baseline_facts')
    cause = _facts(frame, 'cause_facts')
    interpretation = _facts(frame, 'interpretation_facts')
    constraint = _facts(frame, 'constraint_facts')

    available = headline.get('available_arms_count') or observed.get('available_arms_count')
    clean_count = observed.get('clean_workload_options_count')
    secondary_count = observed.get('secondary_options_count')
    clean_names = _join_names(cause.get('clean_workload_options'), limit=3)
    route_names = (
        _join_names(cause.get('top_three_relievers'), limit=3)
        or _join_names(constraint.get('current_operational_core'), limit=3)
    )
    trusted_names = clean_names or route_names
    share = cause.get('top_three_workload_share_10d') or interpretation.get('top_three_workload_share_10d')
    has_clean = _present(clean_count) and clean_count and clean_count > 0

    return _sections(
        headline=_voice_opening(
            frame,
            BEAT_TRUST_LANE,
            names=trusted_names or 'a short list of arms',
            extra_parts=(available, clean_count, secondary_count),
        ),
        observation_paragraph=_paragraph(
            (
                f"The active board lists {_fmt(available)} available {_count_word(available, 'arm')}, but the clean, low-workload group is just {_fmt(clean_count)} deep"
                if _present(available) and has_clean else None
            ),
            (
                f"The active board lists {_fmt(available)} available {_count_word(available, 'arm')}, but none of them come in clean of recent workload"
                if _present(available) and _present(clean_count) and not has_clean else None
            ),
            (
                f"That keeps the trusted late-game lane narrow even with a fuller board"
                if _present(clean_count) else None
            ),
        ),
        baseline_paragraph=_paragraph(
            # Distribution-aware league read of the clean-options count when
            # available; otherwise fall back to the board-vs-lane comparison
            # (never both, to avoid stacking two competing "comparison" lines).
            _clean_options_baseline_sentence(baseline),
            (
                f"The comparison point is the {_fmt(available)}-arm available board set against a thinner trusted late-inning lane"
                if _present(available) and not _clean_options_band(baseline) else None
            ),
            (
                f"Set against that board, the workload-flagged group numbers {_fmt(secondary_count)}"
                if _present(secondary_count) and secondary_count else None
            ),
        ),
        cause_paragraph=_paragraph(
            (
                f"The dependable late-inning work keeps running through {trusted_names}"
                if trusted_names else None
            ),
            (
                f"The most-used group has handled {_fmt(share, suffix='%')} of the recent bullpen workload"
                if _present(share) and route_names and not clean_names else None
            ),
            (
                f"The rest of the available arms are still working back from recent outings"
                if _present(secondary_count) and secondary_count else None
            ),
        ),
        constraint_paragraph=_paragraph(
            (
                f"If the game tightens, the late-game plan leans back on {trusted_names}, a thinner trusted lane than the {_fmt(available)}-arm board suggests"
                if trusted_names and _present(available) else None
            ),
            (
                f"If the game tightens, the trusted late-game lane stays thinner than the available arm count suggests"
                if not (trusted_names and _present(available)) else None
            ),
        ),
    )


# Distribution-aware league phrasing for the bridge story's bullpen-coverage
# baseline line. bullpen_coverage_ip_7d is higher-is-more-pressure (more relief
# innings absorbed). Descriptive context only — no rank, recommendation,
# prediction, or superlative-singular ("highest"/"most overworked") language
# (governance C1N).
_COVERAGE_BASELINE_SENTENCE = {
    'below_average': 'That is below the league norm for recent bullpen coverage',
    'about_typical': 'That is around the league norm for recent bullpen coverage',
    'above_average': 'That is above the league norm for recent bullpen coverage',
    'well_above_average': 'That is well above the league norm for recent bullpen coverage',
    'among_highest': 'That is among the heavier recent bullpen-coverage workloads',
}


def _coverage_band(baseline):
    """The supported coverage comparison band, only when its read is available."""
    read = baseline.get('coverage_baseline_read') if isinstance(baseline, dict) else None
    if not isinstance(read, dict) or read.get('available') is not True:
        return None
    comparison = read.get('comparison')
    return comparison if comparison in _COVERAGE_BASELINE_SENTENCE else None


def _coverage_baseline_sentence(baseline):
    band = _coverage_band(baseline)
    return _COVERAGE_BASELINE_SENTENCE.get(band) if band else None


def _bridge_instability(frame):
    team = _team(frame)
    headline = _facts(frame, 'headline_facts')
    observed = _facts(frame, 'observation_facts')
    baseline = _facts(frame, 'baseline_facts')
    cause = _facts(frame, 'cause_facts')
    interpretation = _facts(frame, 'interpretation_facts')
    constraint = _facts(frame, 'constraint_facts')

    core_names = _join_names(
        headline.get('current_operational_core') or baseline.get('current_operational_core'),
        limit=3,
    )
    early_rate = observed.get('early_bullpen_entry_rate') or cause.get('early_bullpen_entry_rate')
    coverage_ip = observed.get('bullpen_coverage_ip_7d') or cause.get('bullpen_coverage_ip_7d')
    volatile = observed.get('volatile_middle_count')
    clean_count = observed.get('clean_workload_options_count')
    monitor = cause.get('monitor_arms_count')
    has_monitor = _present(monitor) and monitor

    return _sections(
        headline=_voice_opening(
            frame,
            BEAT_BRIDGE,
            names=core_names or 'the late arms',
            extra_parts=(early_rate, coverage_ip, volatile),
        ),
        observation_paragraph=_paragraph(
            (
                f"The late-game core — {core_names} — is settled, but the bullpen is reaching it through {_fmt(volatile)} unsettled middle-relief {_count_word(volatile, 'arm')}"
                if core_names and _present(volatile) else None
            ),
            (
                f"The late-game core is settled, but the bullpen is reaching it through {_fmt(volatile)} unsettled middle-relief {_count_word(volatile, 'arm')}"
                if not core_names and _present(volatile) else None
            ),
            (
                f"The starters are handing off early, with the bullpen entering before the sixth in {_fmt(early_rate, suffix='%')} of recent games"
                if _present(early_rate) else None
            ),
        ),
        baseline_paragraph=_paragraph(
            (
                f"The comparison point is a settled late group against a thin handoff: {_fmt(clean_count)} clean middle {_count_word(clean_count, 'option')} feeding the back of the bullpen"
                if _present(clean_count) else None
            ),
            (
                f"The bullpen is covering {_fmt(coverage_ip)} innings a game on the way there"
                if _present(coverage_ip) else None
            ),
            # Distribution-aware league read of recent bullpen-coverage burden,
            # appended to the coverage line above; voiced only when the coverage
            # baseline read is available. Absent or guarded reads leave the
            # existing bridge copy unchanged.
            _coverage_baseline_sentence(baseline),
        ),
        cause_paragraph=_paragraph(
            (
                f"The early starter exits keep putting the middle innings back on the bullpen"
                if _present(early_rate) else None
            ),
            (
                f"The handoff is leaning on {_fmt(volatile)} unsettled middle {_count_word(volatile, 'arm')}, with {_fmt(monitor)} on the watch list rather than rested options"
                if _present(volatile) and has_monitor else None
            ),
            (
                f"The handoff is leaning on {_fmt(volatile)} unsettled middle {_count_word(volatile, 'arm')} rather than rested options"
                if _present(volatile) and not has_monitor else None
            ),
        ),
        constraint_paragraph=_paragraph(
            (
                f"If the starters keep exiting early, the path to {core_names} runs through a fragile middle, thinner than the settled late group suggests"
                if core_names else None
            ),
            (
                f"If the starters keep exiting early, the path to the late arms runs through a fragile middle"
                if not core_names else None
            ),
        ),
    )


WRITERS = {
    TYPE_ROTATION_PRESSURE: _rotation_pressure,
    TYPE_CONCENTRATION_PRESSURE: _concentration_pressure,
    TYPE_OPTIONALITY_STRENGTH: _optionality_strength,
    TYPE_TRUST_LANE_PRESSURE: _trust_lane_pressure,
    TYPE_BRIDGE_INSTABILITY: _bridge_instability,
    TYPE_STABLE_CORE: _stable_core,
    TYPE_CORE_TRANSITION: _core_transition,
    TYPE_DEPTH_PRESSURE: _depth_pressure,
}


def write_story_frame(frame):
    """Write one deterministic BaseballOS observation from one construction frame."""
    frame = _dict(frame)
    observation_type = frame.get('observation_type')
    writer = WRITERS.get(observation_type)
    written = writer(frame) if writer else _sections()
    output = {
        'capability': CAPABILITY,
        'version': VERSION,
        'source': SOURCE,
        'team_id': frame.get('team_id'),
        'team_name': frame.get('team_name'),
        'team_abbreviation': frame.get('team_abbreviation'),
        'observation_type': observation_type,
        'severity': frame.get('severity'),
        'written_observation': written,
        'source_frame': frame,
        'limitations': list(frame.get('limitations') or []),
    }
    output['validation'] = validate_written_observation(output)
    return output


def write_team_story_frames(construction_payload):
    """Write deterministic observations for every frame in one team payload."""
    construction_payload = _dict(construction_payload)
    written = [
        write_story_frame(frame)
        for frame in _list(construction_payload.get('story_frames'))
    ]
    strongest = _dict(construction_payload.get('strongest_story_frame'))
    strongest_type = strongest.get('observation_type')
    strongest_written = next(
        (
            item for item in written
            if item.get('observation_type') == strongest_type
        ),
        None,
    )
    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'source': SOURCE,
        'team_id': construction_payload.get('team_id'),
        'team_name': construction_payload.get('team_name'),
        'team_abbreviation': construction_payload.get('team_abbreviation'),
        'reference_date': construction_payload.get('reference_date'),
        'data_through_date': construction_payload.get('data_through_date'),
        'written_count': len(written),
        'written_observations': written,
        'strongest_written_observation': strongest_written,
        'limitations': list(construction_payload.get('limitations') or []),
    }


def build_story_writer_v1(*, construction_payloads=None, team_contexts=None, team_ids=None, reference_date=None):
    """Build deterministic written observations from construction frames."""
    if construction_payloads is None:
        if team_contexts is not None:
            construction_payloads = [
                construct_team_story_frames(team_context)
                for team_context in _list(team_contexts)
            ]
        else:
            construction_payloads = (
                build_story_construction_engine_v1(
                    team_ids=team_ids or [],
                    reference_date=reference_date,
                ).get('teams')
                or []
            )

    teams = [
        write_team_story_frames(payload)
        for payload in _list(construction_payloads)
    ]
    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'source': SOURCE,
        'reference_date': (
            reference_date.isoformat()
            if hasattr(reference_date, 'isoformat')
            else reference_date
        ),
        'team_count': len(teams),
        'teams': teams,
        'limitations': [
            'deterministic_templates_only',
            'facts_limited_to_story_construction_frame',
            'no_external_generation',
            'no_engine_state_changes',
        ],
    }


__all__ = [
    'BANNED_TERMS',
    'CAPABILITY',
    'ROBOTIC_TERMS',
    'SECTION_KEYS',
    'VERSION',
    'build_story_writer_v1',
    'validate_written_observation',
    'write_story_frame',
    'write_team_story_frames',
]
