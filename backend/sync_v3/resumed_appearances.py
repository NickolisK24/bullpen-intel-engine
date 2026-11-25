"""Qualify single-session pitching lines in a game MLB completed on another baseball date."""
from collections import Counter, defaultdict
from datetime import date, datetime
from zoneinfo import ZoneInfo


def session_dates(original, resumed, feed, lines):
    pk = original['gamePk']
    first, second = original['officialDate'], original['resumeGameDate']
    if (first >= second or resumed['gamePk'] != pk or feed['gamePk'] != pk
            or resumed.get('resumedFromDate') != first or resumed['officialDate'] != first
            or original['resumeDate'] != resumed['gameDate'] or resumed['resumedFrom'] != original['gameDate']
            or feed['gameData']['datetime']['officialDate'] != first
            or feed['gameData']['datetime']['resumeDate'] != second):
        raise ValueError('Official resumed game dates differ')
    meta = feed['gameData']
    for side in ('away', 'home'):
        club = original['teams'][side]['team']['id']
        if resumed['teams'][side]['team']['id'] != club or meta['teams'][side]['id'] != club:
            raise ValueError('Resumed game club identities differ')
    if original['venue']['id'] != meta['venue']['id']:
        raise ValueError('Resumed game venue differs')
    zone = ZoneInfo(meta['venue']['timeZone']['id'])
    boundary = datetime.fromisoformat(original['resumeDate'])
    totals, days = Counter(), defaultdict(set)
    for play in feed['liveData']['plays']['allPlays']:
        if not play['about']['isComplete']:
            raise ValueError('Incomplete resumed play sequence')
        pitcher = play['matchup']['pitcher']['id']
        for event in play['playEvents']:
            if not event.get('isPitch'):
                continue
            stamp = datetime.fromisoformat(event['startTime'])
            if stamp.tzinfo is None or boundary.tzinfo is None:
                raise ValueError('Unknown resumed pitch time zone')
            day = first if stamp < boundary else second
            if stamp.astimezone(zone).date() != date.fromisoformat(day):
                raise ValueError('Pitch timestamp does not establish a single official session')
            totals[pitcher] += 1
            days[pitcher].add(day)
    expected = {row['pitcher_mlb_id']: row['pitches_thrown'] for row in lines}
    if (set(totals) != set(expected) or dict(totals) != expected or len(expected) != len(lines)
            or any(len(values) != 1 for values in days.values())):
        raise ValueError('Resumed pitch dates or counts do not fully reconcile with credited lines')
    return {pitcher: min(values) for pitcher, values in days.items()}
