"""Deterministic WP43 slate ranking, evidence, refusal, and copy contracts.

The ranker is an editorial ordering aid. Evidence completeness and freshness
remain independent refusal gates, and the deterministic template never creates
facts that are absent from the candidate evidence payload.
"""

from __future__ import annotations

import json
import hashlib
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from models.editorial_post_history import EditorialPostHistory
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.slate_game import SlateGame
from services.bullpen_context import build_team_bullpen_context
from services.schedule_authority import schedule_freshness
from services.workload_appearance import is_pitch_count_workload_log
from utils.db import db
from utils.time import utc_now_naive


CONFIG_PATH = Path(__file__).resolve().parent.parent / 'config' / 'slate_editorial_ranker_v1.json'
SHAPES = {'gassed', 'narrow', 'thin', 'recovered', 'contrast'}
STATE_ORDER = {'unknown': 0, 'fresh': 1, 'stretched': 2, 'vulnerable': 3}
EASTERN = ZoneInfo('America/New_York')


def load_ranker_config(path=None):
    with Path(path or CONFIG_PATH).open(encoding='utf-8') as handle:
        return json.load(handle)


def _number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _integer(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _datetime(value):
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00')).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


def _team_label(team):
    return team.get('team_name') or team.get('team_abbreviation') or f"Team {team.get('team_id')}"


def _candidate_id(slate_date, home_team_id, away_team_id, game_pks):
    game_key = '-'.join(str(value) for value in sorted(_integer(pk) for pk in game_pks))
    return f'{slate_date}:{_integer(away_team_id)}-{_integer(home_team_id)}:{game_key}'


def candidate_evidence_reference(candidate):
    """Return a stable digest for the facts that authorize a posting record."""
    evidence = {
        'candidate_id': candidate.get('candidate_id'),
        'score_version': candidate.get('score_version'),
        'shape': candidate.get('shape'),
        'publishable': candidate.get('publishable'),
        'withholding_reasons': candidate.get('withholding_reasons') or [],
        'game_pks': candidate.get('game_pks') or [],
        'home_team': candidate.get('home_team'),
        'away_team': candidate.get('away_team'),
        'data_freshness': candidate.get('data_freshness'),
    }
    serialized = json.dumps(evidence, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()


def build_named_arms_evidence(logs, *, reference_date, config=None):
    """Return a seven-day, game-log-backed top-three reliever payload."""
    config = config or load_ranker_config()
    ref = _date(reference_date)
    window_days = config['windows']['workload_days']
    start = ref - timedelta(days=window_days - 1)
    by_pitcher = defaultdict(lambda: {
        'player_id': None,
        'name': None,
        'trailing_pitches': 0,
        'appearances': [],
    })
    incomplete_rows = 0
    for log in logs or []:
        game_date = _date(getattr(log, 'game_date', None) if not isinstance(log, dict) else log.get('game_date'))
        if game_date is None or not start <= game_date <= ref:
            continue
        get = log.get if isinstance(log, dict) else lambda key, default=None: getattr(log, key, default)
        if get('game_type') not in (None, '', 'R'):
            continue
        if get('games_started') is None:
            if is_pitch_count_workload_log(log):
                incomplete_rows += 1
            continue
        if get('games_started') != 0:
            continue
        if not is_pitch_count_workload_log(log):
            incomplete_rows += 1
            continue
        pitcher = get('pitcher')
        pitcher_id = get('pitcher_id') or (pitcher.get('id') if isinstance(pitcher, dict) else getattr(pitcher, 'id', None))
        player_id = get('player_id') or (pitcher.get('mlb_id') if isinstance(pitcher, dict) else getattr(pitcher, 'mlb_id', None))
        name = get('pitcher_name') or get('name') or (pitcher.get('full_name') if isinstance(pitcher, dict) else getattr(pitcher, 'full_name', None))
        pitches = _integer(get('pitches_thrown'), -1)
        if pitcher_id is None or player_id is None or not str(name or '').strip() or pitches <= 0:
            incomplete_rows += 1
            continue
        row = by_pitcher[pitcher_id]
        row['player_id'] = player_id
        row['name'] = str(name).strip()
        row['trailing_pitches'] += pitches
        row['appearances'].append({
            'game_pk': get('mlb_game_pk'),
            'date': game_date.isoformat(),
            'pitch_count': pitches,
        })

    relievers = list(by_pitcher.values())
    for row in relievers:
        row['appearances'].sort(key=lambda item: (item['date'], item.get('game_pk') or 0), reverse=True)
    relievers.sort(key=lambda row: (-row['trailing_pitches'], str(row['name']).lower(), row['player_id']))
    total = sum(row['trailing_pitches'] for row in relievers)
    top = relievers[:config['shape_gates']['minimum_named_arms']]
    for row in top:
        row['workload_share_pct'] = round(row['trailing_pitches'] / total * 100, 1) if total else None
        row['last_outing_date'] = row['appearances'][0]['date'] if row['appearances'] else None
        row['last_outing_pitch_count'] = row['appearances'][0]['pitch_count'] if row['appearances'] else None
    top_share = round(sum(row['trailing_pitches'] for row in top) / total * 100, 1) if total else None
    complete = (
        len(top) == config['shape_gates']['minimum_named_arms']
        and incomplete_rows == 0
        and all(
            row['player_id'] is not None
            and row['name']
            and row['last_outing_date']
            and row['last_outing_pitch_count'] is not None
            and row['workload_share_pct'] is not None
            for row in top
        )
    )
    return {
        'window_days': window_days,
        'window_start': start.isoformat(),
        'window_end': ref.isoformat(),
        'total_relief_pitches': total,
        'top_three_share_pct': top_share,
        'top_relievers': top,
        'qualifying_reliever_count': len(relievers),
        'excluded_incomplete_rows': incomplete_rows,
        'complete': complete,
    }


def _team_components(team, config):
    weights = config['weights']
    caps = config['group_caps']
    state = team.get('bullpen_state') if team.get('bullpen_state') in STATE_ORDER else 'unknown'
    clean = _integer(team.get('clean_option_count'))
    scarcity = max(weights['clean_option_target'] - clean, 0) * weights['clean_option_scarcity_per_missing']
    current_detail = {
        'state_severity': _number(config['state_severity_points'].get(state)),
        'clean_option_scarcity': scarcity,
    }
    current = min(sum(current_detail.values()), caps['current_condition'])

    evidence = team.get('named_arms_evidence') or {}
    share = _number(evidence.get('top_three_share_pct'))
    threshold = weights['concentration_threshold_pct']
    concentration = 0
    if share >= threshold:
        concentration = min((share - threshold) / max(100 - threshold, 1) * weights['concentration_max_points'] + 8, weights['concentration_max_points'])
    recent = min(_integer(team.get('recent_games')) * weights['recent_game_points'], 12)
    consecutive = min(_integer(team.get('consecutive_usage_arms')) * weights['consecutive_usage_points'], 9)
    named = weights['named_arms_complete_points'] if evidence.get('complete') else 0
    evidence_detail = {
        'workload_concentration': round(concentration, 2),
        'recent_density': recent,
        'consecutive_day_usage': consecutive,
        'named_arms_completeness': named,
    }
    evidence_score = min(sum(evidence_detail.values()), caps['evidence_strength'])
    stakes_detail = {
        'upcoming_density': min(_integer(team.get('upcoming_games')) * weights['upcoming_game_points'], 16),
        'repetition_penalty': -abs(_number(team.get('repetition_penalty'))),
    }
    stakes = max(min(sum(stakes_detail.values()), caps['editorial_stakes']), 0)
    return {
        'current_condition': {'score': round(current, 2), 'cap': caps['current_condition'], 'components': current_detail},
        'evidence_strength': {'score': round(evidence_score, 2), 'cap': caps['evidence_strength'], 'components': evidence_detail},
        'editorial_stakes': {'score': round(stakes, 2), 'cap': caps['editorial_stakes'], 'components': stakes_detail},
    }


def classify_team_shape(team, config=None):
    config = config or load_ranker_config()
    gates = config['shape_gates']
    evidence = team.get('named_arms_evidence') or {}
    complete = evidence.get('complete') is True
    fresh = team.get('data_freshness', {}).get('state') == 'fresh'
    total = _integer(evidence.get('total_relief_pitches'))
    share = _number(evidence.get('top_three_share_pct'))
    recent = _integer(team.get('recent_games'))
    consecutive = _integer(team.get('consecutive_usage_arms'))
    clean = _integer(team.get('clean_option_count'), 99)

    prior = team.get('prior_state') or {}
    recovered = (
        fresh
        and prior.get('comparable') is True
        and prior.get('freshness_state') == 'fresh'
        and STATE_ORDER.get(prior.get('bullpen_state'), 0) > STATE_ORDER.get(team.get('bullpen_state'), 0)
        and _integer(team.get('rest_days_accumulated')) >= gates['recovered_rest_days_min']
    )
    if recovered:
        return 'recovered'
    if fresh and clean <= gates['thin_clean_options_max']:
        return 'thin'
    if (
        fresh and complete and total >= gates['minimum_relief_pitches']
        and recent >= gates['gassed_recent_games_min']
        and consecutive >= gates['gassed_consecutive_arms_min']
    ):
        return 'gassed'
    if (
        fresh and complete and total >= gates['minimum_relief_pitches']
        and share >= gates['narrow_concentration_pct']
        and recent <= gates['narrow_recent_games_max']
    ):
        return 'narrow'
    return None


def repetition_penalty(team_id, shape, history, *, as_of, config=None):
    if not shape:
        return 0
    config = config or load_ranker_config()
    cutoff = _datetime(as_of) - timedelta(days=config['windows']['repetition_days'])
    recent_shapes = []
    for row in history or []:
        get = row.get if isinstance(row, dict) else lambda key, default=None: getattr(row, key, default)
        if _integer(get('team_id'), -1) != _integer(team_id, -2):
            continue
        posted_at = _datetime(get('posted_at'))
        if posted_at is not None and posted_at >= cutoff:
            recent_shapes.append(get('story_shape'))
    if shape in recent_shapes:
        return config['weights']['same_team_same_shape_penalty']
    if recent_shapes:
        return config['weights']['same_team_other_shape_penalty']
    return 0


def _contrast_score(home, away, config):
    gap = abs(STATE_ORDER.get(home.get('bullpen_state'), 0) - STATE_ORDER.get(away.get('bullpen_state'), 0))
    if gap < config['shape_gates']['contrast_state_gap_min']:
        return 0
    if home.get('data_freshness', {}).get('state') != 'fresh' or away.get('data_freshness', {}).get('state') != 'fresh':
        return 0
    return config['weights']['contrast_points']


def _withholding_reasons(team, shape, schedule):
    reasons = []
    evidence = team.get('named_arms_evidence') or {}
    if team.get('data_freshness', {}).get('state') != 'fresh':
        reasons.append('team_data_not_fresh')
    if schedule.get('state') != 'fresh':
        reasons.append('schedule_data_not_fresh')
    if shape is None:
        reasons.append('no_distinct_editorial_signal')
    share = _number(evidence.get('top_three_share_pct'))
    if share >= 70 and evidence.get('complete') is not True:
        reasons.append('named_arms_evidence_incomplete')
    if shape in {'narrow', 'gassed'} and evidence.get('complete') is not True:
        reasons.append('named_arms_evidence_incomplete')
    return list(dict.fromkeys(reasons))


def render_plain_one_liner(candidate):
    """Render condition first and stakes second; never make schedule causal."""
    shape = candidate.get('shape')
    team = candidate.get('featured_team') or {}
    label = _team_label(team)
    evidence = team.get('named_arms_evidence') or {}
    share = evidence.get('top_three_share_pct')
    clean = _integer(team.get('clean_option_count'))
    upcoming = _integer(team.get('upcoming_games'))
    if not candidate.get('publishable'):
        return None
    if shape == 'narrow':
        condition = f"{label}'s top three relievers carried {share:.1f}% of its relief pitches over the last seven days."
    elif shape == 'gassed':
        condition = f"{label} has used relievers on consecutive days during a dense three-day stretch."
    elif shape == 'thin':
        condition = f"{label} has {clean} clean bullpen option{'s' if clean != 1 else ''} in the current read."
    elif shape == 'recovered':
        condition = f"{label}'s bullpen state improved after {_integer(team.get('rest_days_accumulated'))} days of accumulated rest."
    elif shape == 'contrast':
        opponent = candidate['away_team'] if team.get('team_id') == candidate['home_team'].get('team_id') else candidate['home_team']
        condition = f"{label}'s bullpen condition differs sharply from {_team_label(opponent)}'s current read."
    else:
        return None
    stakes = f"With {upcoming} game{'s' if upcoming != 1 else ''} scheduled over the next three days, that condition is worth monitoring."
    return f'{condition} {stakes}'


def rank_matchup(matchup, *, config=None, history=None, as_of=None):
    config = config or load_ranker_config()
    as_of = _datetime(as_of) or utc_now_naive()
    home = dict(matchup['home_team'])
    away = dict(matchup['away_team'])
    home_shape = classify_team_shape(home, config)
    away_shape = classify_team_shape(away, config)
    home['repetition_penalty'] = repetition_penalty(home.get('team_id'), home_shape, history, as_of=as_of, config=config)
    away['repetition_penalty'] = repetition_penalty(away.get('team_id'), away_shape, history, as_of=as_of, config=config)
    home_breakdown = _team_components(home, config)
    away_breakdown = _team_components(away, config)
    home_score = round(sum(group['score'] for group in home_breakdown.values()), 2)
    away_score = round(sum(group['score'] for group in away_breakdown.values()), 2)
    contrast = _contrast_score(home, away, config)
    featured = home if (home_score, -_integer(home.get('team_id'))) >= (away_score, -_integer(away.get('team_id'))) else away
    shape = home_shape if featured is home else away_shape
    if shape is None and contrast:
        shape = 'contrast'
        featured = home if STATE_ORDER.get(home.get('bullpen_state'), 0) > STATE_ORDER.get(away.get('bullpen_state'), 0) else away
        featured['repetition_penalty'] = repetition_penalty(
            featured.get('team_id'), shape, history, as_of=as_of, config=config,
        )
        if featured is home:
            home_breakdown = _team_components(home, config)
            home_score = round(sum(group['score'] for group in home_breakdown.values()), 2)
        else:
            away_breakdown = _team_components(away, config)
            away_score = round(sum(group['score'] for group in away_breakdown.values()), 2)
    schedule = matchup.get('schedule_freshness') or {'state': 'unavailable'}
    reasons = _withholding_reasons(featured, shape, schedule)
    candidate = {
        'candidate_id': matchup.get('candidate_id'),
        'briefing_date': matchup.get('briefing_date'),
        'game_pk': matchup.get('game_pk'),
        'game_pks': list(matchup.get('game_pks') or [matchup.get('game_pk')]),
        'doubleheader': bool(matchup.get('doubleheader')),
        'first_pitch_et': matchup.get('first_pitch_et'),
        'games': list(matchup.get('games') or []),
        'score_version': config['score_version'],
        'home_team': home,
        'away_team': away,
        'home_team_story_score': home_score,
        'away_team_story_score': away_score,
        'matchup_contrast_score': contrast,
        'final_editorial_score': round(max(home_score, away_score) + contrast, 2),
        'featured_team': featured,
        'component_breakdown': {'home_team': home_breakdown, 'away_team': away_breakdown, 'matchup_contrast': contrast},
        'shape': shape,
        'publishable': not reasons,
        'withholding_reasons': reasons,
        'evidence_completeness': {
            'home_team': bool((home.get('named_arms_evidence') or {}).get('complete')),
            'away_team': bool((away.get('named_arms_evidence') or {}).get('complete')),
            'featured_team': bool((featured.get('named_arms_evidence') or {}).get('complete')),
        },
        'data_freshness': {'schedule': schedule, 'featured_team': featured.get('data_freshness') or {}},
    }
    candidate['plain_one_liner'] = render_plain_one_liner(candidate)
    candidate['evidence_reference'] = candidate_evidence_reference(candidate)
    return candidate


def rank_slate(matchups, *, config=None, history=None, as_of=None):
    config = config or load_ranker_config()
    candidates = [rank_matchup(item, config=config, history=history, as_of=as_of) for item in matchups or []]
    return sorted(candidates, key=lambda item: (-item['final_editorial_score'], _integer(item.get('game_pk'), 2**63 - 1)))


def _derive_bullpen_state(optionality):
    band = optionality.get('optionality_band')
    if band == 'thin':
        return 'vulnerable'
    if band == 'narrow':
        return 'stretched'
    if band in {'flexible', 'deep'}:
        return 'fresh'
    return 'unknown'


def _team_game_count(team_id, start, end, *, states=None):
    query = SlateGame.query.filter(
        SlateGame.game_date_et >= start,
        SlateGame.game_date_et <= end,
        or_(SlateGame.home_team_id == team_id, SlateGame.away_team_id == team_id),
    )
    if states:
        query = query.filter(SlateGame.normalized_state.in_(states))
    return query.count()


def build_team_ranking_input(team_id, *, reference_date, config=None, prior_state=None):
    """Assemble one ranker input from current BaseballOS stores."""
    config = config or load_ranker_config()
    ref = _date(reference_date)
    start = ref - timedelta(days=config['windows']['workload_days'] - 1)
    logs = (
        GameLog.query.options(joinedload(GameLog.pitcher))
        .join(Pitcher, GameLog.pitcher_id == Pitcher.id)
        .filter(Pitcher.team_id == team_id, GameLog.game_date >= start, GameLog.game_date <= ref)
        .all()
    )
    context = build_team_bullpen_context(team_id, reference_date=ref)
    optionality = context.get('bullpen_optionality_context') or {}
    evidence = build_named_arms_evidence(logs, reference_date=ref, config=config)
    latest = max((_date(getattr(log, 'game_date', None)) for log in logs), default=None)
    freshness_days = config['windows']['data_freshness_days']
    freshness_state = 'fresh' if latest is not None and (ref - latest).days <= freshness_days else ('stale' if latest else 'unavailable')
    recent_start = ref - timedelta(days=config['windows']['recent_days'] - 1)
    recent_logs = [log for log in logs if _date(log.game_date) >= recent_start and getattr(log, 'games_started', None) == 0 and is_pitch_count_workload_log(log)]
    dates_by_pitcher = defaultdict(set)
    for log in recent_logs:
        dates_by_pitcher[log.pitcher_id].add(log.game_date)
    consecutive = sum(1 for dates in dates_by_pitcher.values() if any(day - timedelta(days=1) in dates for day in dates))
    team = context.get('team') or {'team_id': team_id}
    return {
        **team,
        'team_id': team_id,
        'bullpen_state': _derive_bullpen_state(optionality),
        'clean_option_count': len(optionality.get('clean_workload_options') or []),
        'named_arms_evidence': evidence,
        'recent_games': _team_game_count(team_id, recent_start, ref, states={SlateGame.STATE_COMPLETED}),
        'upcoming_games': _team_game_count(team_id, ref, ref + timedelta(days=config['windows']['upcoming_days'] - 1), states={SlateGame.STATE_UPCOMING}),
        'consecutive_usage_arms': consecutive,
        'data_freshness': {'state': freshness_state, 'data_through': latest.isoformat() if latest else None},
        'prior_state': prior_state,
        'rest_days_accumulated': max((ref - latest).days, 0) if latest else 0,
    }


def build_ranked_slate(slate_date, *, prior_states=None, as_of=None, config=None):
    """DB-backed assembly seam for WP44; this function is not an endpoint."""
    config = config or load_ranker_config()
    ref = _date(slate_date)
    rows = SlateGame.query.filter(SlateGame.game_date_et == ref).order_by(SlateGame.game_time_utc, SlateGame.game_pk).all()
    freshness = schedule_freshness(as_of=_datetime(as_of) if as_of is not None else None)
    cutoff = (_datetime(as_of) or utc_now_naive()) - timedelta(days=config['windows']['repetition_days'])
    history = EditorialPostHistory.query.filter(EditorialPostHistory.posted_at >= cutoff).all()
    prior_states = prior_states or {}
    grouped_rows = defaultdict(list)
    for row in rows:
        grouped_rows[(row.home_team_id, row.away_team_id)].append(row)
    matchups = []
    for (_home_team_id, _away_team_id), games in sorted(
        grouped_rows.items(), key=lambda item: (item[1][0].game_time_utc, item[1][0].game_pk),
    ):
        row = games[0]
        sorted_games = sorted(games, key=lambda game: (game.game_time_utc, game.game_pk))
        game_pks = [game.game_pk for game in sorted_games]
        first_pitch = sorted_games[0].game_time_utc.replace(tzinfo=ZoneInfo('UTC')).astimezone(EASTERN)
        matchups.append({
            'game_pk': row.game_pk,
            'candidate_id': _candidate_id(ref.isoformat(), row.home_team_id, row.away_team_id, game_pks),
            'briefing_date': ref.isoformat(),
            'game_pks': game_pks,
            'doubleheader': len(games) > 1,
            'first_pitch_et': first_pitch.isoformat(),
            'games': [game.to_dict() for game in sorted_games],
            'schedule_freshness': freshness,
            'home_team': build_team_ranking_input(row.home_team_id, reference_date=ref, config=config, prior_state=prior_states.get(row.home_team_id)),
            'away_team': build_team_ranking_input(row.away_team_id, reference_date=ref, config=config, prior_state=prior_states.get(row.away_team_id)),
        })
    return rank_slate(matchups, config=config, history=history, as_of=as_of)


def validate_fact_claims(claims, candidate):
    """Exact structured fact guard for generated-copy integrations.

    A generator may add ``fact_claims`` beside prose. Every supplied claim is
    matched to the evidence payload; callers must refuse drafts with violations.
    """
    violations = []
    teams = [candidate.get('home_team') or {}, candidate.get('away_team') or {}]
    allowed_teams = {
        str(value).casefold()
        for team in teams
        for value in (team.get('team_id'), team.get('team_name'), team.get('team_abbreviation'))
        if value not in (None, '')
    }
    allowed_matchup = {str(team.get('team_id')) for team in teams}
    allowed_names, allowed_dates, allowed_pitches, allowed_percentages = set(), set(), set(), set()
    for team in teams:
        evidence = team.get('named_arms_evidence') or {}
        if evidence.get('top_three_share_pct') is not None:
            allowed_percentages.add(round(_number(evidence['top_three_share_pct']), 1))
        for arm in evidence.get('top_relievers') or []:
            allowed_names.add(str(arm.get('name') or '').casefold())
            allowed_dates.add(str(arm.get('last_outing_date') or ''))
            allowed_pitches.add(_integer(arm.get('last_outing_pitch_count'), -1))
            allowed_pitches.add(_integer(arm.get('trailing_pitches'), -1))
            for appearance in arm.get('appearances') or []:
                allowed_dates.add(str(appearance.get('date') or ''))
                allowed_pitches.add(_integer(appearance.get('pitch_count'), -1))
    for value in claims.get('teams') or []:
        if str(value).casefold() not in allowed_teams:
            violations.append(f'unverified_team:{value}')
    for value in claims.get('matchup_team_ids') or []:
        if str(value) not in allowed_matchup:
            violations.append(f'unverified_matchup_team:{value}')
    for value in claims.get('names') or []:
        if str(value).casefold() not in allowed_names:
            violations.append(f'unverified_name:{value}')
    for value in claims.get('dates') or []:
        if str(value) not in allowed_dates:
            violations.append(f'unverified_date:{value}')
    for value in claims.get('pitch_counts') or []:
        if _integer(value, -2) not in allowed_pitches:
            violations.append(f'unverified_pitch_count:{value}')
    for value in claims.get('percentages') or []:
        if round(_number(value, -2), 1) not in allowed_percentages:
            violations.append(f'unverified_percentage:{value}')
    return {'checked': True, 'valid': not violations, 'violations': violations}


__all__ = [
    'build_named_arms_evidence',
    'build_ranked_slate',
    'build_team_ranking_input',
    'candidate_evidence_reference',
    'classify_team_shape',
    'load_ranker_config',
    'rank_matchup',
    'rank_slate',
    'render_plain_one_liner',
    'repetition_penalty',
    'validate_fact_claims',
]
