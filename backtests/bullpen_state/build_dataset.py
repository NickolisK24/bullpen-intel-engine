"""Build the backtest dataset from the warm cache (no network).

Outputs (CSV, under OUTPUT_DIR):

* team_games.csv    one row per team per game: date, team, opponent, ballpark,
                    pre-game Team State + evidence counts, team fatigue score,
                    and the raw same-game pitching/linescore facts the outcome
                    step reads.
* reliever_days.csv one row per active-bullpen reliever per team-game: his
                    pre-game availability flag and whether he pitched.
* dataset_summary.json  counts used by the report.

Doubleheaders: both games of a date share one pre-game state (computed from data
through the previous day, as the nightly pipeline would). Game 2 rows carry
``dh_game2 = 1`` so the analysis can report them separately.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import timedelta

from . import config, mlb_client
from .games import load_games, parse_boxscore
from .replay import History, replay_team_day

TEAM_GAME_FIELDS = [
    'season', 'game_date', 'game_pk', 'start_utc', 'team_id', 'team_name',
    'opponent_id', 'opponent_name', 'home_away', 'venue_id', 'venue_name',
    'double_header', 'game_number', 'dh_game2', 'resumed', 'scheduled_innings',
    # pre-game state
    'public_state', 'readiness_code', 'decisive_rule', 'trust_confidence',
    'active_count', 'clean_count', 'moderate_count', 'severe_count', 'unknown_count',
    'severe_share', 'team_fatigue_mean', 'roster_pitchers',
    # same-game raw facts (outcomes are derived from these in the next step)
    'runs_scored', 'runs_allowed', 'starter_mlb_id', 'starter_outs',
    'starter_runs', 'bullpen_outs', 'bullpen_runs', 'bullpen_earned_runs',
    'relievers_used', 'innings_for', 'innings_against',
]
RELIEVER_FIELDS = [
    'season', 'game_date', 'game_pk', 'team_id', 'dh_game2', 'public_state',
    'pitcher_mlb_id', 'name', 'role', 'availability_status', 'availability_data_state',
    'fatigue_score', 'pitch_count_unknown', 'days_rest',
    'pitched', 'pitched_relief', 'outs', 'runs_allowed',
]


def _load_appearances(seasons, offline=True):
    games_by_season, apps = {}, []
    missing = 0
    for season in seasons:
        games = load_games(season, offline=offline)
        games_by_season[season] = games
        for g in games:
            try:
                apps.extend(parse_boxscore(g, mlb_client.boxscore(g.game_pk, offline=offline)))
            except FileNotFoundError:
                missing += 1
    return games_by_season, apps, missing


def build(eval_seasons=config.EVAL_SEASONS, history_seasons=config.HISTORY_SEASONS, offline=True):
    seasons = sorted(set(history_seasons) | set(eval_seasons))
    games_by_season, apps, missing_box = _load_appearances(seasons, offline=offline)
    if missing_box:
        print(f'WARNING: {missing_box} boxscores missing from cache', file=sys.stderr)
    history = History(apps)
    apps_by_game_team = defaultdict(list)
    for a in apps:
        apps_by_game_team[(a.game_pk, a.team_id)].append(a)

    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    tg_file = open(config.OUTPUT_DIR / 'team_games.csv', 'w', newline='')
    rd_file = open(config.OUTPUT_DIR / 'reliever_days.csv', 'w', newline='')
    tg = csv.DictWriter(tg_file, TEAM_GAME_FIELDS)
    rd = csv.DictWriter(rd_file, RELIEVER_FIELDS)
    tg.writeheader()
    rd.writeheader()

    summary = {'seasons': {}, 'missing_boxscores': missing_box}
    for season in eval_seasons:
        state_counts = Counter()
        flag_counts = Counter()
        missing_roster = 0
        reliever_days = 0
        pitch_unknown_days = 0
        team_games = 0
        cache = {}
        for g in games_by_season[season]:
            for side in ('home', 'away'):
                team_id = g.home_id if side == 'home' else g.away_id
                opp_id = g.away_id if side == 'home' else g.home_id
                key = (team_id, g.game_date)
                if key not in cache:
                    try:
                        roster = mlb_client.active_roster(
                            team_id, g.game_date - timedelta(days=1), offline=offline,
                        ).get('roster') or []
                    except FileNotFoundError:
                        roster = None
                    if roster is None:
                        cache[key] = None
                    else:
                        cache[key] = replay_team_day(
                            team_id, g.game_date, roster, history.view_before(g.game_date),
                        )
                state = cache[key]
                if state is None:
                    missing_roster += 1
                    continue

                team_apps = sorted(apps_by_game_team.get((g.game_pk, team_id), []), key=lambda a: a.order)
                starter = team_apps[0] if team_apps else None
                pen = team_apps[1:]
                ours = [(n, (h if side == 'home' else a)) for n, a, h in g.innings]
                theirs = [(n, (a if side == 'home' else h)) for n, a, h in g.innings]
                dh2 = int(g.game_number == 2)
                row = {
                    'season': season, 'game_date': g.game_date.isoformat(), 'game_pk': g.game_pk,
                    'start_utc': g.start_utc, 'team_id': team_id,
                    'team_name': g.home_abbr if side == 'home' else g.away_abbr,
                    'opponent_id': opp_id,
                    'opponent_name': g.away_abbr if side == 'home' else g.home_abbr,
                    'home_away': side, 'venue_id': g.venue_id, 'venue_name': g.venue_name,
                    'double_header': g.double_header, 'game_number': g.game_number,
                    'dh_game2': dh2, 'resumed': int(g.resumed), 'scheduled_innings': g.scheduled_innings,
                    'public_state': state.public_state, 'readiness_code': state.readiness_code,
                    'decisive_rule': state.decisive_rule, 'trust_confidence': state.trust_confidence,
                    'active_count': state.active_count, 'clean_count': state.clean_count,
                    'moderate_count': state.moderate_count, 'severe_count': state.severe_count,
                    'unknown_count': state.unknown_count,
                    'severe_share': round(state.severe_count / state.active_count, 4) if state.active_count else '',
                    'team_fatigue_mean': state.team_fatigue_mean,
                    'roster_pitchers': state.roster_pitchers,
                    'runs_scored': g.home_runs if side == 'home' else g.away_runs,
                    'runs_allowed': g.away_runs if side == 'home' else g.home_runs,
                    'starter_mlb_id': starter.pitcher_mlb_id if starter else '',
                    'starter_outs': starter.innings_pitched_outs if starter else '',
                    'starter_runs': starter.runs_allowed if starter else '',
                    'bullpen_outs': sum(a.innings_pitched_outs for a in pen),
                    'bullpen_runs': sum(a.runs_allowed for a in pen),
                    'bullpen_earned_runs': sum(a.earned_runs for a in pen),
                    'relievers_used': len(pen),
                    'innings_for': json.dumps(ours), 'innings_against': json.dumps(theirs),
                }
                tg.writerow(row)
                team_games += 1
                state_counts[state.public_state] += 1

                pitched = {a.pitcher_mlb_id: a for a in team_apps}
                for r in state.relievers:
                    a = pitched.get(r.pitcher_mlb_id)
                    rd.writerow({
                        'season': season, 'game_date': g.game_date.isoformat(), 'game_pk': g.game_pk,
                        'team_id': team_id, 'dh_game2': dh2, 'public_state': state.public_state,
                        'pitcher_mlb_id': r.pitcher_mlb_id, 'name': r.name, 'role': r.role,
                        'availability_status': r.availability_status,
                        'availability_data_state': r.availability_data_state,
                        'fatigue_score': r.fatigue_score, 'pitch_count_unknown': int(r.pitch_count_unknown),
                        'days_rest': '' if r.days_rest is None else r.days_rest,
                        'pitched': int(a is not None),
                        'pitched_relief': int(a is not None and (a.games_started or 0) == 0),
                        'outs': a.innings_pitched_outs if a else 0,
                        'runs_allowed': a.runs_allowed if a else 0,
                    })
                    reliever_days += 1
                    pitch_unknown_days += int(r.pitch_count_unknown)
                    flag_counts[r.availability_status] += 1
        summary['seasons'][season] = {
            'team_games': team_games,
            'team_games_missing_roster': missing_roster,
            'team_games_by_state': dict(state_counts),
            'reliever_days': reliever_days,
            'reliever_days_by_flag': dict(flag_counts),
            'reliever_days_pitch_count_unknown_scored_as_zero': pitch_unknown_days,
        }
        print(f'[dataset] {season}: {team_games} team-games {dict(state_counts)}; '
              f'{reliever_days} reliever-days; pitch-count-unknown={pitch_unknown_days}; '
              f'missing roster={missing_roster}', flush=True)
    tg_file.close()
    rd_file.close()
    with open(config.OUTPUT_DIR / 'dataset_summary.json', 'w') as fh:
        json.dump(summary, fh, indent=2, default=str)
    return summary


if __name__ == '__main__':
    build()
