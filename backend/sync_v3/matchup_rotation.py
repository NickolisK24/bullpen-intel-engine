"""Project pregame rotation pressure from a generation's dated, verified club pitching lines."""
from datetime import date, timedelta

from models.team_game_pitching_split import TeamGamePitchingSplit
from services import rotation_support_pressure as rotation


def _confirmed_nonrotation(game, club, day, lines):
    """Reproduce the recorded opener/bulk or bullpen-game split from this game's pinned final revision."""
    if not lines or any(line['game_pk'] != game['game_pk'] or line['game_date'] != day.isoformat()
                        or line['team_id'] != club for line in lines):
        return False
    ids = [line['pitcher_mlb_id'] for line in lines]
    if len(set(ids)) != len(ids) or any(type(pid) is not int or pid < 1 for pid in ids):
        return False
    if any(type(line['outs_recorded']) is not int or line['outs_recorded'] < 0
           or type(line['games_started']) is not int or line['games_started'] not in (0, 1) for line in lines):
        return False
    starts = [line for line in lines if line['games_started'] == 1]
    relief = [line for line in lines if line['games_started'] == 0]
    logs = [dict(line, innings_pitched_outs=line['outs_recorded']) for line in lines]
    record, reason = rotation._classify_team_game(logs)
    relief_ids = sorted(line['pitcher_mlb_id'] for line in relief)
    if (reason or record != game['rotation'] or relief_ids != sorted(game['relief_pitchers'])
            or sum(line['outs_recorded'] for line in relief) != game['relief_outs']):
        return False
    if record['kind'] == rotation.KIND_BULLPEN_GAME:
        return not starts and game['credited_starter'] is None and game['starter_outs'] is None
    return (record['kind'] == rotation.KIND_OPENER_BULK and len(starts) == 1
            and starts[0]['pitcher_mlb_id'] == game['credited_starter'] and starts[0]['outs_recorded'] == game['starter_outs'])


def matchup_rotation(facts, reference, *, reference_day_unresolved, pinned_lines=None):
    """Require every final in the window and withhold shapes needing separate split evidence."""
    through = date.fromisoformat(facts['through'])
    if reference != through + timedelta(days=1) or reference_day_unresolved:
        return None
    splits = []
    seen = set()
    short_starts = 0
    bullpen_outs = 0
    for offset in range(1, rotation.DEFAULT_WINDOW_DAYS):
        day = reference - timedelta(days=offset)
        daily = facts['dates'].get(day.isoformat())
        if not daily or daily['reason']:
            return None
        for game in daily['games']:
            record = game['rotation']
            starter, relief = game['starter_outs'], game['relief_outs']
            if game['game_pk'] in seen or game['shape_reason'] or not record:
                return None
            seen.add(game['game_pk'])
            if record['kind'] in (rotation.KIND_OPENER_BULK, rotation.KIND_BULLPEN_GAME):
                if not _confirmed_nonrotation(game, facts['team'], day, (pinned_lines or {}).get(game['game_pk'])):
                    return None
                continue
            if (record['kind'] != rotation.KIND_ROTATION_START or not game['credited_starter']
                    or not game['relief_pitchers'] or starter != record['starter_outs']
                    or relief != record['bullpen_outs_required'] or starter + relief != record['total_known_outs']
                    or (starter <= rotation.OPENER_MAX_OUTS and relief >= rotation.BULK_FOLLOWER_MIN_OUTS)):
                return None
            short_starts += int(record['short_start'])
            bullpen_outs += relief
            splits.append(dict(mlb_game_pk=game['game_pk'], game_date=day, team_id=facts['team'],
                               starter_identity_status=TeamGamePitchingSplit.STARTER_KNOWN,
                               split_completeness_status=TeamGamePitchingSplit.STATUS_PARTIAL,
                               starter_outs_recorded=starter, bullpen_outs_recorded=relief, total_team_outs=starter + relief,
                               starter_mlb_id=game['credited_starter']))
    if not splits:
        return None
    # The accepted ordinary-start inputs above take the pure branch of the existing split classifier.
    pressure = rotation.build_team_rotation_support_pressure_from_splits(splits, team={'team_id': facts['team']},
                                                                         reference_date=reference)
    if (pressure['games_analyzed'] != len(splits) or pressure['short_start_count'] != short_starts
            or pressure['bullpen_outs_required'] != bullpen_outs):
        return None
    return dict(window_days=pressure['window_days'], short_starts=pressure['short_start_count'],
                bullpen_innings=pressure['bullpen_innings_required'], limitations=pressure['limitations'])
