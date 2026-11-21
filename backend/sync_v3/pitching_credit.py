"""Distinguish an explicitly uncredited MLB listing from a credited zero-out appearance."""


def uncredited_pitching_line(stats):
    credit = stats.get('gamesPitched')
    if credit is None:
        return False
    if type(credit) is not int or credit not in (0, 1):
        raise ValueError('invalid_single_game_stat')
    if credit == 1:
        return False
    required = ('gamesPlayed', 'gamesStarted', 'numberOfPitches', 'battersFaced', 'outs')
    optional = ('hits', 'runs', 'earnedRuns', 'homeRuns', 'baseOnBalls', 'strikeOuts', 'hitBatsmen',
                'hitByPitch', 'wildPitches', 'balks', 'wins', 'losses', 'saves', 'saveOpportunities',
                'blownSaves', 'holds', 'gamesFinished', 'inheritedRunners', 'inheritedRunnersScored',
                'strikes', 'balls', 'pickoffs', 'atBats', 'doubles', 'triples', 'stolenBases',
                'caughtStealing', 'flyOuts', 'groundOuts', 'airOuts', 'intentionalWalks',
                'completeGames', 'shutouts', 'totalBases', 'sacBunts', 'sacFlies', 'catchersInterference',
                'rbi', 'groundIntoDoublePlay', 'passedBall', 'popOuts', 'lineOuts')
    if (stats.get('inningsPitched') != '0.0'
            or any(type(stats.get(key)) is not int or stats[key] != 0 for key in required)
            or any(key in stats and (type(stats[key]) is not int or stats[key] != 0) for key in optional)):
        raise ValueError('invalid_single_game_stat')
    return True
