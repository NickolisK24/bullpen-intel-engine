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
    if clean is not None:
        evidence.append(_clean_phrase(clean))
    if days is not None:
        evidence.append(f'Next off day in {days} {_plural(days, "day")}')
    if games_until is not None:
        evidence.append(f'{games_until} {_plural(games_until, "game")} before the next off day')
    if band in _THIN_BANDS:
        evidence.append(f'{band.capitalize()} bullpen optionality')

    # Team-neutral copy: the card carries team_name separately, so the prose never
    # makes a (often plural) team name the grammatical subject.
    summary = (f'{_clean_summary_cap(clean)} {_be(clean)} available, '
               f'with {_games_phrase(games_until)} before the next off day.')
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

    evidence = []
    if clean is not None:
        evidence.append(_clean_phrase(clean))
    if paths is not None:
        evidence.append(f'{paths} practical close-game {_plural(paths, "path")}')
    if pen['optionality_band'] in _THIN_BANDS:
        evidence.append(f"{pen['optionality_band'].capitalize()} bullpen optionality")

    summary = (f'{_clean_summary_cap(clean)} and {_paths_summary(paths)} '
               f'are available tonight.')
    return _candidate(
        team_id, team_name, sc, pen, limitations,
        family=FAMILY_LATE_GAME_PATH, signal=SIGNAL_NO_CLEAN_MARGIN,
        headline='Almost no clean margin tonight',
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
        evidence.append(f'{band.capitalize()} bullpen workload concentration')
    last3 = sc.get('games_played_last_3_days')
    if last3:
        evidence.append(f'{last3} {_plural(last3, "game")} played in the last three days')

    if share is not None:
        summary = (f'The top three relievers have handled {_round1(share)}% of recent '
                   f'bullpen workload, with {_games_phrase(games_next3)} scheduled over '
                   f'the next three days.')
    else:
        summary = (f'A {band} bullpen workload faces {_games_phrase(games_next3)} over '
                   f'the next three days.')
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
    if clean is not None:
        evidence.append(_clean_phrase(clean))
    if band in _THIN_BANDS:
        evidence.append(f'{band.capitalize()} bullpen optionality')
    evidence.append('Off day tomorrow' if days == 1 else 'Last game before an off day')

    summary = ('Pressure remains, but the next off day limits how long the '
               'bullpen has to carry it.')
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

def _clean_phrase(n):
    return f'{n} clean bullpen {_plural(n, "option")}'


def _clean_summary(n):
    if n is None:
        return 'a thin set of clean bullpen paths'
    if n == 0:
        return 'no clean bullpen paths'
    if n == 1:
        return 'only one clean bullpen path'
    return f'{n} clean bullpen paths'


def _clean_summary_cap(n):
    text = _clean_summary(n)
    return text[:1].upper() + text[1:]


def _be(n):
    # Subject-verb agreement for the clean-paths phrase ("path is" / "paths are";
    # the singular "set" also takes "is").
    return 'is' if n in (None, 1) else 'are'


def _paths_summary(paths):
    if paths is None:
        return 'few practical close-game paths'
    return f'{paths} practical close-game {_plural(paths, "path")}'


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
