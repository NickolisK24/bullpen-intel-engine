"""Project pregame rotation pressure from a generation's dated, verified club pitching lines."""
from datetime import date, timedelta

from models.team_game_pitching_split import TeamGamePitchingSplit
from services import rotation_support_pressure as rotation


def matchup_rotation(facts, reference, *, reference_day_unresolved):
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
            if (game['game_pk'] in seen or game['shape_reason'] or not record
                    or record['kind'] != rotation.KIND_ROTATION_START or not game['credited_starter']
                    or not game['relief_pitchers'] or starter != record['starter_outs']
                    or relief != record['bullpen_outs_required'] or starter + relief != record['total_known_outs']
                    or (starter <= rotation.OPENER_MAX_OUTS and relief >= rotation.BULK_FOLLOWER_MIN_OUTS)):
                return None
            seen.add(game['game_pk'])
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
