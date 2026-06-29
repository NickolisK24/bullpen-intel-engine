"""Tonight candidate selection V1 (pregame, internal).

Joins Schedule Context (Phase 2) with the existing trusted bullpen context to
produce diverse pregame "Tonight" candidate objects — bullpen situations worth
watching before first pitch. It selects at most one candidate per signal family,
across distinct teams, so the output reads as different story shapes rather than
three copies of "TEAM enters tonight short N arms".

This is internal selection support only: candidates are plain dicts, copy is
descriptive and evidence-backed, and an internal ``strength`` orders selection
without being a public ranking claim. Nothing here predicts outcomes, recommends
a "best" team, names a reliever a manager will use, or invents a metric. It reads
existing context and the schedule; it builds no endpoint and changes no surface.

Reference date is supplied by the caller (a pregame/current-day concept) — this
is deliberately NOT tied to completed-game default dates.
"""

from __future__ import annotations

import logging

from services.editorial_voice_contract_v1 import (
    build_comparison_sentence,
    contains_editorial_banned_language,
    count_to_baseball_language,
)
from services.schedule_context import (
    build_schedule_contexts_for_date,
    build_team_schedule_context,
)

logger = logging.getLogger(__name__)

# ── Signal families and types ─────────────────────────────────────────────────
FAMILY_SCHEDULE_PRESSURE = 'schedule_pressure'
FAMILY_LATE_GAME_PATH = 'late_game_path'
FAMILY_WORKLOAD_PRESSURE = 'workload_pressure'
FAMILY_OFF_DAY_RELIEF = 'off_day_relief'

SIGNAL_THIN_BEFORE_OFF_DAY = 'thin_before_next_off_day'
SIGNAL_NO_CLEAN_MARGIN = 'no_clean_margin_tonight'
SIGNAL_HEAVY_WORKLOAD_AHEAD = 'heavy_recent_workload_with_games_ahead'
SIGNAL_OFF_DAY_RELIEF = 'off_day_relief_pressure_reduced'

# ── Thresholds (conservative, deterministic) ──────────────────────────────────
_CLEAN_LOW = 2          # "clean options are low"
_CLEAN_VERY_LOW = 1     # "almost no clean margin"
_PATHS_VERY_LOW = 1
_TOP_THREE_SHARE_ELEVATED = 45.0
_THIN_BANDS = ('thin', 'narrow')
_ELEVATED_CONCENTRATION = ('concentrated', 'narrow')
_INSUFFICIENT = 'insufficient_data'
PREGAME_STORY_TYPE = 'pregame_bullpen_watch_v1'
PREGAME_STORY_LABEL = "Tonight's Bullpen Watch"
VOICE_SURFACE = 'todays_watch'


def build_tonight_candidates(reference_date, *, limit=3, schedule_contexts=None,
                             bullpen_context_builder=None):
    """Build up to ``limit`` diverse Tonight candidates for ``reference_date``.

    Joins each playing team's schedule context with its bullpen context, derives
    every matching signal, then selects at most one candidate per signal family
    across distinct teams (strongest first). Returns ``[]`` when no team is
    playing or no candidate clears a signal. ``schedule_contexts`` and
    ``bullpen_context_builder`` may be injected for tests/pure use.
    """
    if schedule_contexts is None:
        schedule_contexts = build_schedule_contexts_for_date(reference_date)
    builder = bullpen_context_builder or _default_bullpen_context_builder

    pool = []
    for sc in schedule_contexts or []:
        if not sc or not sc.get('is_playing_today'):
            continue
        team_id = sc.get('team_id')
        try:
            bc = builder(team_id, reference_date)
        except Exception:  # noqa: BLE001 — one team's missing context never aborts
            logger.warning('Tonight: bullpen context failed for team %s', team_id,
                           exc_info=True)
            bc = None
        pool.extend(_team_signal_candidates(team_id, sc, bc))

    return _select(pool, limit)


def build_team_tonight_candidate(team_id, reference_date, schedule_context=None,
                                 bullpen_context=None):
    """Build one team's strongest Tonight candidate, or ``None``.

    Loads schedule/bullpen context on demand when not injected. Returns the
    highest-strength matching signal for the team, or ``None`` if the team is not
    playing today or matches no signal.
    """
    if schedule_context is None:
        schedule_context = build_team_schedule_context(team_id, reference_date)
    if not schedule_context or not schedule_context.get('is_playing_today'):
        return None
    if bullpen_context is None:
        bullpen_context = _default_bullpen_context_builder(team_id, reference_date)

    candidates = _team_signal_candidates(team_id, schedule_context, bullpen_context)
    if not candidates:
        return None
    return sorted(candidates, key=_sort_key)[0]


# ── Per-team signal derivation ────────────────────────────────────────────────

def _team_signal_candidates(team_id, sc, bc):
    """Every signal a single playing team matches (zero or more candidates)."""
    if not sc or not sc.get('is_playing_today'):
        return []

    pen = _normalize_bullpen_context(bc)
    team_name = _team_name(bc, team_id)
    limitations = list(sc.get('limitations') or [])
    if not pen['context_available']:
        limitations = _dedupe(limitations + ['bullpen_context_unavailable'])

    out = []
    for evaluate in (_signal_thin_before_off_day, _signal_no_clean_margin,
                     _signal_heavy_workload_ahead, _signal_off_day_relief):
        candidate = evaluate(team_id, team_name, sc, pen, limitations)
        if candidate is not None:
            out.append(candidate)
    return out


def _signal_thin_before_off_day(team_id, team_name, sc, pen, limitations):
    band = pen['optionality_band']
    clean = pen['clean_options_count']
    thin_pen = band in _THIN_BANDS or (clean is not None and clean <= _CLEAN_LOW)
    days = sc.get('days_until_next_off_day')
    games_until = sc.get('games_until_next_off_day')
    no_rest = (days is not None and days >= 2) or (games_until is not None and games_until >= 2)
    if not (thin_pen and no_rest):
        return None

    strength = 30
    strength += {'thin': 25, 'narrow': 15}.get(band, 0)
    strength += min(games_until or 0, 6) * 5
    if clean is not None:
        strength += max(0, 3 - clean) * 5

    evidence = []
    if _clean_is_limited(clean, band):
        evidence.append(_LATE_CUSHION_THIN_PHRASE)
    if days is not None:
        evidence.append(f'Next off day in {days} {_plural(days, "day")}')
    if games_until is not None:
        evidence.append(f'{games_until} {_plural(games_until, "game")} before the next off day')
    if band in _THIN_BANDS:
        evidence.append(_optionality_evidence(band))

    # Team-neutral copy: the card carries team_name separately, so the prose never
    # makes a (often plural) team name the grammatical subject. Clean optionality
    # is described qualitatively (never as an exact count) so the homepage card
    # cannot contradict the linked team page's own clean-option labels.
    summary = _public_sentence(
        subject='The late-inning cushion is thin',
        reason=f'the bullpen has {_prose_games_phrase(games_until)} before the next off day',
        consequence_key='availability_narrowed',
        stable_parts=('summary', SIGNAL_THIN_BEFORE_OFF_DAY, games_until, band),
    )
    return _candidate(
        team_id, team_name, sc, pen, limitations,
        family=FAMILY_SCHEDULE_PRESSURE, signal=SIGNAL_THIN_BEFORE_OFF_DAY,
        headline='Little margin before the next rest day',
        summary=summary, evidence=evidence, strength=min(strength, 100))


def _signal_no_clean_margin(team_id, team_name, sc, pen, limitations):
    clean = pen['clean_options_count']
    paths = pen['practical_close_game_paths_count']
    trigger = (clean is not None and clean <= _CLEAN_VERY_LOW) or \
              (paths is not None and paths <= _PATHS_VERY_LOW)
    if not trigger:
        return None

    strength = 35
    if clean is not None:
        strength += max(0, 2 - clean) * 20
    if paths is not None:
        strength += max(0, 2 - paths) * 15

    # Public copy is qualitative and severity-capped. The strict optionality
    # clean count can read 0 for an arm the linked team page still labels a
    # "Clean Option" (status AVAILABLE), so the card never publishes an exact
    # clean/path count, and the headline never uses "no"/"almost no"/"zero"
    # margin language (see _margin_headline for the severity ceiling).
    evidence = [_LATE_CUSHION_THIN_PHRASE]
    if pen['optionality_band'] in _THIN_BANDS:
        evidence.append(_optionality_evidence(pen['optionality_band']))

    summary = _public_sentence(
        subject='The late-game path has little cushion',
        reason='the bridge behind the first trusted arm is short',
        consequence_key='narrow_late_path',
        stable_parts=('summary', SIGNAL_NO_CLEAN_MARGIN, clean, paths, pen['optionality_band']),
    )
    return _candidate(
        team_id, team_name, sc, pen, limitations,
        family=FAMILY_LATE_GAME_PATH, signal=SIGNAL_NO_CLEAN_MARGIN,
        headline=_margin_headline(pen),
        summary=summary, evidence=evidence, strength=min(strength, 100))


def _signal_heavy_workload_ahead(team_id, team_name, sc, pen, limitations):
    band = pen['concentration_band']
    share = pen['top_three_workload_share_10d']
    elevated = band in _ELEVATED_CONCENTRATION or (share is not None and share >= _TOP_THREE_SHARE_ELEVATED)
    games_next3 = sc.get('games_in_next_3_days')
    games_ahead = games_next3 is not None and games_next3 >= 2
    if not (elevated and games_ahead):
        return None

    strength = 28
    strength += {'narrow': 22, 'concentrated': 14}.get(band, 0)
    if share is not None:
        strength += int(min(max(share - _TOP_THREE_SHARE_ELEVATED, 0), 30))
    strength += min(games_next3 or 0, 3) * 5

    # The workload share is the strongest fact when present; lead the evidence
    # with it. Only cite the concentration band when the band itself signals
    # pressure (concentrated / narrow) — never "normal", which would undercut the
    # card it is attached to.
    evidence = []
    if share is not None:
        evidence.append(f'Top three relievers at {_round1(share)}% of recent bullpen workload')
    evidence.append(f'{games_next3} {_plural(games_next3, "game")} in the next three days')
    if band in _ELEVATED_CONCENTRATION:
        evidence.append(_concentration_evidence(band))
    last3 = sc.get('games_played_last_3_days')
    if last3:
        evidence.append(f'{last3} {_plural(last3, "game")} played in the last three days')

    if share is not None:
        summary = (f'The top three relievers have handled {_round1(share)}% of recent '
                   f'bullpen workload, with {_prose_games_phrase(games_next3)} scheduled over '
                   f'the next three days.')
    else:
        summary = _public_sentence(
            subject='Recent bullpen work is gathered on a smaller group',
            reason=f'the schedule has {_prose_games_phrase(games_next3)} over the next three days',
            consequence_key='workload_concentration',
            stable_parts=('summary', SIGNAL_HEAVY_WORKLOAD_AHEAD, band, games_next3),
        )
    return _candidate(
        team_id, team_name, sc, pen, limitations,
        family=FAMILY_WORKLOAD_PRESSURE, signal=SIGNAL_HEAVY_WORKLOAD_AHEAD,
        headline='Top-heavy workload before another busy stretch',
        summary=summary, evidence=evidence, strength=min(strength, 100))


def _signal_off_day_relief(team_id, team_name, sc, pen, limitations):
    band = pen['optionality_band']
    clean = pen['clean_options_count']
    conc = pen['concentration_band']
    some_pressure = (band in _THIN_BANDS
                     or (clean is not None and clean <= _CLEAN_LOW)
                     or conc in _ELEVATED_CONCENTRATION)
    days = sc.get('days_until_next_off_day')
    off_soon = sc.get('is_last_game_before_off_day') or days == 1
    if not (some_pressure and off_soon):
        return None

    # Deliberately lower base so this variety card does not crowd out risk cards.
    strength = 15
    strength += {'thin': 10, 'narrow': 6}.get(band, 0)
    if clean is not None:
        strength += max(0, 2 - clean) * 4

    evidence = []
    if _clean_is_limited(clean, band):
        evidence.append(_LATE_CUSHION_THIN_PHRASE)
    if band in _THIN_BANDS:
        evidence.append(_optionality_evidence(band))
    evidence.append('Off day tomorrow' if days == 1 else 'Last game before an off day')

    summary = ('The bullpen still has pressure to carry, but the next off day '
               'creates a reset point after tonight.')
    return _candidate(
        team_id, team_name, sc, pen, limitations,
        family=FAMILY_OFF_DAY_RELIEF, signal=SIGNAL_OFF_DAY_RELIEF,
        headline='A softer landing after tonight',
        summary=summary, evidence=evidence, strength=min(strength, 100))


# ── Selection ─────────────────────────────────────────────────────────────────

def _select(pool, limit):
    """At most one per family, distinct teams, strongest first, up to ``limit``."""
    selected = []
    used_families = set()
    used_teams = set()
    for candidate in sorted(pool, key=_sort_key):
        if candidate['signal_family'] in used_families:
            continue
        if candidate['team_id'] in used_teams:
            continue
        selected.append(candidate)
        used_families.add(candidate['signal_family'])
        used_teams.add(candidate['team_id'])
        if len(selected) >= limit:
            break
    return selected


def _sort_key(candidate):
    # Strongest first; ties broken deterministically by family then team_id.
    return (-candidate['strength'], candidate['signal_family'], candidate['team_id'])


# ── Candidate assembly ────────────────────────────────────────────────────────

def _candidate(team_id, team_name, sc, pen, limitations, *, family, signal,
               headline, summary, evidence, strength):
    return {
        'team_id': team_id,
        'team_name': team_name,
        'reference_date': sc.get('reference_date'),
        'signal_type': signal,
        'signal_family': family,
        'headline': headline,
        'summary': summary,
        'pregame_story': _pregame_story(
            team_name, sc, pen, signal=signal, headline=headline),
        'evidence': list(evidence),
        'schedule_context': _schedule_subset(sc),
        'bullpen_context': pen,
        'strength': int(strength),
        'limitations': list(limitations),
    }


def _schedule_subset(sc):
    keys = (
        'is_playing_today', 'opponent_today', 'home_away_today', 'game_time_today',
        'games_played_last_3_days', 'games_played_last_5_days', 'games_in_next_3_days',
        'next_off_day', 'days_until_next_off_day', 'games_until_next_off_day',
        'consecutive_games_played_entering_today', 'consecutive_games_scheduled_from_today',
        'doubleheader_today', 'limitations',
    )
    return {key: sc.get(key) for key in keys}


def _normalize_bullpen_context(bc):
    """Reduce a full or partial bullpen context to the small Tonight subset.

    Accepts the full dict from build_team_bullpen_context (with nested
    bullpen_optionality_context / bullpen_concentration_context) OR an already
    small/normalized dict (injected in tests). Unavailable fields are ``None`` —
    never faked.
    """
    if not isinstance(bc, dict):
        return _empty_bullpen_norm(available=False)

    if 'bullpen_optionality_context' in bc or 'bullpen_concentration_context' in bc:
        opt = bc.get('bullpen_optionality_context') or {}
        con = bc.get('bullpen_concentration_context') or {}
        available = bool(opt.get('context_available'))
        if not available:
            norm = _empty_bullpen_norm(available=False)
            norm['concentration_band'] = _clean_band(con.get('concentration_band'))
            norm['top_three_workload_share_10d'] = con.get('top_three_workload_share_10d')
            return norm
        clean_list = opt.get('clean_workload_options')
        return {
            'context_available': True,
            'clean_options_count': len(clean_list) if isinstance(clean_list, list) else None,
            'clean_workload_option_names': _clean_option_names(clean_list),
            'optionality_band': _clean_band(opt.get('optionality_band')),
            'practical_close_game_paths_count': opt.get('practical_close_game_paths_count'),
            'available_arms_count': opt.get('available_arms_count'),
            'monitor_arms_count': opt.get('monitor_arms_count'),
            'limited_arms_count': opt.get('limited_arms_count'),
            'restricted_arms_count': opt.get('restricted_arms_count'),
            'concentration_band': _clean_band(con.get('concentration_band')),
            'top_three_workload_share_10d': con.get('top_three_workload_share_10d'),
        }

    # Already-normalized (test injection): copy known keys, default to None.
    norm = _empty_bullpen_norm(available=bool(
        bc.get('context_available', any(
            bc.get(k) is not None for k in
            ('clean_options_count', 'optionality_band', 'practical_close_game_paths_count')))))
    for key in norm:
        if key in bc and key != 'context_available':
            norm[key] = bc[key]
    norm['optionality_band'] = _clean_band(norm['optionality_band'])
    norm['concentration_band'] = _clean_band(norm['concentration_band'])
    return norm


def _empty_bullpen_norm(*, available):
    return {
        'context_available': bool(available),
        'clean_options_count': None,
        'clean_workload_option_names': [],
        'optionality_band': None,
        'practical_close_game_paths_count': None,
        'available_arms_count': None,
        'monitor_arms_count': None,
        'limited_arms_count': None,
        'restricted_arms_count': None,
        'concentration_band': None,
        'top_three_workload_share_10d': None,
    }


# ── Copy helpers (descriptive, evidence-backed; no predictions) ───────────────

def _pregame_story(team_name, sc, pen, *, signal, headline):
    story = {
        'story_type': PREGAME_STORY_TYPE,
        'label': PREGAME_STORY_LABEL,
        'headline': headline,
        'team_context': _team_context_sentence(team_name, sc),
        'watching': _watching_sentence(signal),
        'why_it_matters': _why_it_matters_sentence(signal, sc, pen),
        'key_note': _key_note_sentence(pen),
        'watch_point': _watch_point_sentence(signal),
    }
    return {key: value for key, value in story.items() if value}


def _team_context_sentence(team_name, sc):
    opponent = sc.get('opponent_today')
    home_away = sc.get('home_away_today')
    if opponent and home_away == 'home':
        text = f"Tonight's schedule has {team_name} at home against {opponent}."
    elif opponent and home_away == 'away':
        text = f"Tonight's schedule has {team_name} on the road against {opponent}."
    elif opponent:
        text = f"Tonight's schedule has {team_name} against {opponent}."
    else:
        text = f"Tonight's schedule includes {team_name}."
    if sc.get('doubleheader_today'):
        text += ' It is a doubleheader day.'
    return text


def _watching_sentence(signal):
    if signal == SIGNAL_THIN_BEFORE_OFF_DAY:
        return 'Watch whether the bullpen can keep the bridge manageable before the next rest day.'
    if signal == SIGNAL_NO_CLEAN_MARGIN:
        return 'Watch whether the late-game path has enough cushion if the game tightens.'
    if signal == SIGNAL_HEAVY_WORKLOAD_AHEAD:
        return 'Watch whether the work spreads beyond the relievers carrying the recent load.'
    if signal == SIGNAL_OFF_DAY_RELIEF:
        return 'Watch how directly the bullpen can get to the next rest day.'
    return 'Watch how the bullpen workload shapes the first pitching change.'


def _why_it_matters_sentence(signal, sc, pen):
    games_until = sc.get('games_until_next_off_day')
    games_next3 = sc.get('games_in_next_3_days')
    share = pen.get('top_three_workload_share_10d')

    # Clean optionality is described qualitatively (never as an exact count) so
    # the homepage card cannot contradict the linked team page's clean-option
    # labels. The workload-share branch keeps a number because it is traceable and
    # does not assert a bullpen arm-count the team page would dispute.
    if signal == SIGNAL_THIN_BEFORE_OFF_DAY:
        return _public_sentence(
            subject='A thin bullpen cushion matters before a rest day',
            reason=f'the schedule still has {_prose_games_phrase(games_until)} before the next off day',
            consequence_key='availability_narrowed',
            stable_parts=('why', signal, games_until),
        )
    if signal == SIGNAL_NO_CLEAN_MARGIN:
        return _public_sentence(
            subject='A tight game asks more from the bridge',
            reason='the late-game cushion is thin behind the first trusted arm',
            consequence_key='bridge_pressure',
            stable_parts=('why', signal),
        )
    if signal == SIGNAL_HEAVY_WORKLOAD_AHEAD:
        if share is not None:
            return _public_sentence(
                subject=f'The top three relievers have handled {_round1(share)}% of recent bullpen workload',
                reason=f'the schedule still has {_prose_games_phrase(games_next3)} over the next three days',
                consequence_key='workload_concentration',
                stable_parts=('why', signal, share, games_next3),
            )
        return _public_sentence(
            subject='Recent bullpen work is gathered on a smaller group',
            reason=f'the schedule still has {_prose_games_phrase(games_next3)} over the next three days',
            consequence_key='workload_concentration',
            stable_parts=('why', signal, games_next3),
        )
    if signal == SIGNAL_OFF_DAY_RELIEF:
        return ('The bullpen still has pressure to carry, but the next off day '
                'gives the staff a natural reset point after tonight.')
    return _public_sentence(
        subject='Bullpen availability can shape a close game late',
        reason='the first pitching change can alter the path to the final outs',
        consequence_key='no_clear_signal',
        stable_parts=('why', signal),
    )


def _key_note_sentence(pen):
    # Naming the actual clean arms is traceable and safe — these are arms the team
    # page also surfaces as available/clean. When no clean arm is named, the note
    # stays qualitative: it never publishes a rested/limited arm count, because the
    # card's pool differs from the team page's active-bullpen totals and a bare
    # "N limited by recent work" reads as a contradiction (the original defect).
    names = pen.get('clean_workload_option_names') or []
    if names:
        return _safe_public_copy(
            f'Key bullpen note: clean late-inning looks include {_join_names(names[:3])}.',
            'Key bullpen note: the late-inning cushion has a named clean look.',
        )

    if not pen.get('context_available'):
        return None

    clean = pen.get('clean_options_count')
    band = pen.get('optionality_band')
    monitor = pen.get('monitor_arms_count')
    if _clean_is_limited(clean, band):
        if monitor:
            return 'Key bullpen note: the bridge carries pressure before the late innings, with secondary arms carrying caution.'
        return 'Key bullpen note: the late-game cushion is thin before the trusted arms.'
    if monitor:
        return 'Key bullpen note: several middle-inning arms carry caution.'
    return None


def _watch_point_sentence(signal):
    if signal == SIGNAL_THIN_BEFORE_OFF_DAY:
        return 'The key question is whether the bridge to the late innings stays manageable without leaning on the same arms again.'
    if signal == SIGNAL_NO_CLEAN_MARGIN:
        return 'If the starter exits early, watch whether the bridge can cover the sixth and seventh before the late arms take over.'
    if signal == SIGNAL_HEAVY_WORKLOAD_AHEAD:
        return 'The key question is whether the middle innings can spread work beyond the relievers carrying the recent load.'
    if signal == SIGNAL_OFF_DAY_RELIEF:
        return 'The key question is how directly the bullpen can get to the next rest day.'
    return 'The key question is how the bullpen workload holds together tonight.'


def _clean_option_names(items):
    names = []
    for item in items or []:
        if isinstance(item, dict):
            name = item.get('name') or item.get('player_name') or item.get('full_name')
        else:
            name = item
        if name:
            names.append(str(name))
    return names


def _join_names(names):
    return _join_parts(list(names))


def _join_parts(parts):
    if not parts:
        return ''
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f'{parts[0]} and {parts[1]}'
    return f'{", ".join(parts[:-1])}, and {parts[-1]}'


# Public clean-optionality copy is deliberately qualitative and severity-capped
# so the homepage Tonight card cannot contradict the linked team bullpen state
# page. Two rules drive this:
#   1. Never publish an exact clean/path count. The strict optionality count can
#      be 0 for an arm the team page still labels a "Clean Option" (status
#      AVAILABLE), so an exact "0 clean options" reads as a direct contradiction.
#   2. Never let the card's severity exceed the team state. With any available
#      arm, the headline stays "thin", never "no"/"almost no"/"zero".
_LATE_CUSHION_THIN_PHRASE = 'Late-inning cushion is thin'

_MARGIN_HEADLINE_THIN = 'Thin late-game margin tonight'
_MARGIN_HEADLINE_LIMITED = 'Short late-game cushion tonight'


def _clean_is_limited(clean, band):
    """True when clean optionality is genuinely limited for a thin-signal card."""
    return (clean is not None and clean <= _CLEAN_LOW) or band in _THIN_BANDS


def _margin_headline(pen):
    # Severity ceiling: with at least one available arm the late-game margin is
    # thin, not absent. Only when no arm is available at all does the card use a
    # firmer cushion headline without publishing a zero-count claim.
    available = pen.get('available_arms_count')
    if available is not None and available <= 0:
        return _MARGIN_HEADLINE_LIMITED
    return _MARGIN_HEADLINE_THIN


def _safe_public_copy(text, fallback):
    """Fail closed if future Today copy trips the shared banned-language scan."""
    return fallback if contains_editorial_banned_language(text) else text


def _public_sentence(*, subject, reason, stable_parts, consequence_key=None, consequence=None):
    sentence = build_comparison_sentence(
        subject=subject,
        reason=reason,
        consequence=consequence,
        consequence_key=consequence_key,
        stable_parts=(VOICE_SURFACE, *tuple(stable_parts)),
    )
    fallback = build_comparison_sentence(
        subject='The bullpen read stays focused on tonight',
        reason='the baseball consequence needs to stay clear',
        consequence='That keeps the watch note tied to the game shape',
        stable_parts=(VOICE_SURFACE, 'fallback'),
    )
    return _safe_public_copy(sentence, fallback)


def _optionality_evidence(band):
    if band == 'thin':
        return 'Bullpen cushion is thin'
    if band == 'narrow':
        return 'Bullpen cushion is narrow'
    return 'Bullpen cushion is constrained'


def _concentration_evidence(band):
    if band == 'narrow':
        return 'Recent bullpen work is clustered tightly'
    return 'Recent bullpen work is clustered on a smaller group'


def _prose_games_phrase(games, noun='game'):
    return count_to_baseball_language(games, noun, _plural(2, noun)) or f'multiple {_plural(2, noun)}'


def _games_phrase(games, noun='game'):
    if games is None:
        return f'multiple {noun}s'
    return f'{games} {_plural(games, noun)}'


def _plural(n, word):
    return word if n == 1 else word + 's'


def _round1(value):
    try:
        return round(float(value), 1)
    except (TypeError, ValueError):
        return value


def _clean_band(band):
    return None if band in (None, _INSUFFICIENT) else band


def _team_name(bc, team_id):
    if isinstance(bc, dict):
        name = bc.get('team_name') or (bc.get('team') or {}).get('team_name')
        if name:
            return name
    return f'Team {team_id}'


def _dedupe(items):
    seen = []
    for item in items:
        if item not in seen:
            seen.append(item)
    return seen


def _default_bullpen_context_builder(team_id, reference_date):
    # Imported lazily so the module stays import-light and easy to stub in tests.
    from services.bullpen_context import build_team_bullpen_context
    return build_team_bullpen_context(team_id, reference_date=reference_date)
