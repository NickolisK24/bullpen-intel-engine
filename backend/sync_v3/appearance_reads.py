"""Project game-side appearances from the sources pinned by an isolated edition."""

from datetime import date, timedelta
from types import SimpleNamespace

from services.mlb_club_directory import MLB_CLUBS
from services.public_recent_work import LOOKBACK_DAYS, RECENT_LINES_MAX, _appearance_line
from sync_v3.history import METHODOLOGY


def appearance_ledger(cur, digest, subject, entity, through, *, appearance_team=None):
    """Return confirmed regular-season appearances and the dates the snapshot could not settle."""
    if subject not in ('team', 'pitcher'):
        raise ValueError('Expected a club or pitcher ledger')
    if appearance_team is not None and subject != 'pitcher':
        raise ValueError('Only a pitcher ledger can use an appearance club')
    source_subject, source_entity = (subject, entity) if appearance_team is None else ('team', appearance_team)
    cur.execute("""SELECT h.id,h.facts->'coverage_gaps',h.semantic_digest,h.input_digest
                   FROM candidate.generation_inputs g JOIN candidate.workload_history h ON h.id=g.snapshot
                   WHERE g.generation=%s AND h.methodology=%s AND h.subject=%s AND h.mlb_id=%s""",
                (digest, METHODOLOGY, source_subject, source_entity))
    snapshot, gap_dates, semantic, inputs = cur.fetchone()
    return _ledger(cur, snapshot, subject, entity, through, gap_dates, semantic, inputs, METHODOLOGY, appearance_team=appearance_team)


def postseason_appearances(cur, digest, subject, entity, through, readiness_team, *, club_only=False):
    """Read positive appearance evidence only from this edition's verified postseason finals."""
    from psycopg2.extras import Json
    from services.club_competition_status import POSTSEASON_GAME_TYPES
    from sync_v3.competition_calendar import calendar_games
    from sync_v3.discovery import competition_calendar_request
    from sync_v3.evidence import replay
    from sync_v3.intelligence_history import DOMAINS

    if subject not in ('team', 'pitcher') or (subject == 'team' and entity != readiness_team):
        raise ValueError('Expected a pitcher or the represented readiness team')
    methodology = DOMAINS['readiness'][1]
    cur.execute("""SELECT h.id,h.facts->'verified_decisions',h.semantic_digest,h.input_digest,h.facts->'missing_decisions'
                   FROM candidate.generation_inputs g JOIN candidate.workload_history h ON h.id=g.snapshot
                   WHERE g.generation=%s AND h.methodology=%s AND h.subject='team' AND h.mlb_id=%s
                     AND h.represented=%s""", (digest, methodology, readiness_team, through))
    snapshot, games, semantic, inputs, missing = cur.fetchone()
    ledger = _ledger(cur, snapshot, subject, entity, through, {}, semantic, inputs, methodology,
                     game_types=sorted(POSTSEASON_GAME_TYPES), verified_games=games or [],
                     appearance_team=readiness_team if club_only else None)
    if missing:
        # Missing decisions are league-wide. Attribute only the games that fall
        # in this ledger's window and appearance-club scope.
        request = competition_calendar_request(through.year)
        cur.execute("""SELECT min(f.id) FROM candidate.workload_history_sources hs
                       JOIN candidate.fetches f ON f.id=hs.source_id
                       WHERE hs.snapshot=%s AND f.endpoint=%s AND f.parameters=%s AND f.outcome='received'
                       GROUP BY f.sha256""", (snapshot, request.endpoint, Json(request.params())))
        sources = cur.fetchall()
        if len(sources) != 1:
            raise ValueError('Missing or ambiguous pinned calendar for unresolved postseason games')
        calendar = calendar_games(request.params(), replay(cur, sources[0][0]).body)
        for pk in missing:
            day, row, _ = calendar[pk]
            applies = subject == 'pitcher' and not club_only or readiness_team in (row['home_team_id'], row['away_team_id'])
            if applies and ledger['start'] <= day.isoformat() <= ledger['through']:
                ledger['status'] = 'partial'
                ledger['gaps'].setdefault(day.isoformat(), 'missing_verified_postseason_decision')
    return ledger


def _ledger(cur, snapshot, subject, entity, through, gap_dates, semantic, inputs, methodology,
            game_types=('R',), verified_games=None, appearance_team=None):
    start = through - timedelta(days=LOOKBACK_DAYS - 1)
    games = None if verified_games is None else [str(pk) for pk in verified_games]
    identity_field = 'team_id' if subject == 'team' else 'pitcher_mlb_id'
    cur.execute("""SELECT c.identity,r.revision,s.facts->>'officialDate',s.facts->'gameNumber',
                          a.line,f.sha256
                   FROM candidate.workload_history_sources hs
                   JOIN candidate.fetches f ON f.id=hs.source_id
                   JOIN candidate.confirmations c ON c.source_id=f.id AND c.domain='final'
                   JOIN candidate.revisions r ON r.id=c.revision_id
                   JOIN candidate.confirmations sc ON sc.source_id=c.context_id AND sc.domain='schedule'
                     AND split_part(sc.identity,'/',1)=c.identity
                   JOIN candidate.revisions s ON s.id=sc.revision_id
                   CROSS JOIN LATERAL jsonb_array_elements(r.facts) a(line)
                   WHERE hs.snapshot=%s AND s.facts->>'gameType'=ANY(%s)
                     AND (%s::text[] IS NULL OR c.identity=ANY(%s))
                     AND s.facts->>'officialDate' BETWEEN %s AND %s
                     AND a.line->>%s=%s AND (%s='pitcher' OR a.line->>'games_started'='0')
                   ORDER BY c.identity,r.revision,f.sha256""",
                (snapshot, list(game_types), games, games, start.isoformat(), through.isoformat(),
                 identity_field, str(entity), subject))
    clubs = {club.team_id: club for club in MLB_CLUBS}
    lines, gaps = {}, dict(gap_dates)
    for pk, revision, day, game_number, line, sha in cur:
        if day in gaps or (appearance_team is not None and line['team_id'] != appearance_team):
            continue
        key = (int(pk), line['pitcher_mlb_id'])
        if line['game_pk'] != key[0] or line['game_date'] != day:
            raise ValueError('Appearance disagrees with its confirmed final schedule')
        if key in lines:
            old = lines[key]
            if old['final_revision'] != revision or old['game_number'] != game_number:
                gaps[day] = 'conflicting_pinned_appearance_versions'
            elif sha not in old['boxscore_digests']:
                old['boxscore_digests'].append(sha)
            continue
        opponent = clubs[line['opponent_team_id']]
        log = SimpleNamespace(**dict(line, game_date=date.fromisoformat(day), innings_pitched_outs=line['outs_recorded'],
                                     opponent=opponent.team_name, opponent_abbreviation=opponent.abbreviation))
        lines[key] = dict(_appearance_line(log), game_pk=key[0], mlb_id=key[1], game_number=game_number,
                          appearance_team_id=line['team_id'], opponent_team_id=line['opponent_team_id'], home_away=line['side'],
                          role=line['appearance_role'], games_finished=line.get('games_finished'), save=line.get('save'),
                          final_revision=revision, boxscore_digests=[sha])
    kept = [row for row in lines.values() if row['game_date'] not in gaps]
    kept.sort(key=lambda row: (-date.fromisoformat(row['game_date']).toordinal(), row['game_number'] is None,
                               row['game_number'] or 0, row['game_pk'], row['mlb_id']))
    scope = 'official_regular_season' if verified_games is None else 'verified_postseason_finals'
    status = 'complete' if verified_games is None else 'verified_games_only'
    return dict(scope=scope, status='partial' if gaps else status,
                population='game_side_relief' if subject=='team' else 'all_pitching_appearances',
                through=through.isoformat(), start=start.isoformat(), gaps=gaps, appearances=kept,
                citation=dict(methodology=methodology, facts_digest=semantic, input_digest=inputs))


def team_relief_games(team, regular, postseason):
    """Summarize evidenced relief games on the Board's latest five verified appearance dates."""
    from collections import defaultdict
    from services.team_board_recent_relief_work import DISPLAY_GAME_DATES, relief_game_totals

    if (regular['population'] != 'game_side_relief' or postseason['population'] != regular['population']
            or regular['start'] != postseason['start'] or regular['through'] != postseason['through']):
        raise ValueError('Club relief windows or populations disagree')
    games = []
    seen = set()
    for ledger in (regular, postseason):
        grouped = defaultdict(list)
        for line in ledger['appearances']:
            if line['appearance_team_id'] != team:
                raise ValueError('Relief appearance belongs to another club')
            grouped[line['game_pk']].append(line)
        for pk, lines in grouped.items():
            identities = {(r['game_date'], r['game_number'], r['opponent_team_id'], r['opponent_abbreviation'],
                           r['home_away'], r['final_revision']) for r in lines}
            if pk in seen or len(identities) != 1 or len({r['mlb_id'] for r in lines}) != len(lines):
                raise ValueError('Conflicting game or pitcher in the selected relief evidence')
            seen.add(pk)
            day, number, opponent, abbreviation, side, revision = identities.pop()
            games.append(dict(mlb_game_pk=pk, game_date=day, game_number=number, opponent_team_id=opponent,
                              opponent_abbreviation=abbreviation, home_away=side, final_revision=revision, scope=ledger['scope'],
                              boxscore_digests=sorted({sha for r in lines for sha in r['boxscore_digests']}),
                              **relief_game_totals([r['innings_pitched_outs'] for r in lines],
                                                   [r['pitches_thrown'] for r in lines])))
    games.sort(key=lambda g: (-date.fromisoformat(g['game_date']).toordinal(), g['game_number'] is None,
                              g['game_number'] or 0, g['mlb_game_pk']))
    dates = sorted({g['game_date'] for g in games}, reverse=True)[:DISPLAY_GAME_DATES]
    return dict(status='verified_games_only', through=regular['through'], regular_gaps=regular['gaps'],
                postseason_gaps=postseason['gaps'], games=[g for g in games if g['game_date'] in dates])


def pitcher_recent_work(regular, postseason):
    """Present confirmed outings from both ledgers without asserting coverage of missing games."""
    if (regular['through'] != postseason['through'] or regular['start'] != postseason['start']
            or regular['population'] != 'all_pitching_appearances' or postseason['population'] != regular['population']):
        raise ValueError('Pitcher appearance windows or populations disagree')
    rows = regular['appearances'] + postseason['appearances']
    if len({r['mlb_id'] for r in rows}) > 1:
        raise ValueError('Appearance ledgers contain different pitchers')
    if len({r['game_pk'] for r in rows}) != len(rows):
        raise ValueError('Conflicting regular-season and postseason appearances for one pitcher')
    ordered = sorted(rows, key=lambda r: (r['game_date'], r['game_number'] is None, r['game_number'] or 0, r['game_pk']))
    series = [dict(date=r['game_date'], game_pk=r['game_pk'], pitches=r['pitches_thrown'],
                   opponent=r['opponent_abbreviation']) for r in ordered]
    note = 'Includes verified regular-season and postseason outings.'
    if regular['gaps'] or postseason['gaps']:
        note += ' Some dates have incomplete evidence.'
    latest_first = list(reversed(ordered))
    result = dict(scope='regular_season_and_verified_postseason', population=regular['population'],
                  status='partial' if regular['gaps'] or postseason['gaps'] else 'verified_games_only',
                  start=regular['start'], through=regular['through'], data_through=regular['through'],
                  regular_citation=regular['citation'], postseason_citation=postseason['citation'],
                  regular_gaps=regular['gaps'], postseason_gaps=postseason['gaps'],
                  appearances=latest_first, recent_appearances=latest_first[:RECENT_LINES_MAX],
                  workload_series=series, workload_series_note=note)
    if not ordered:
        result['absence_sentence'] = 'No verified outings in the available records for this window.'
    return result
