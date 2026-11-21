"""Freeze isolated intelligence reads and rebuild domains affected by one source request."""

from datetime import timedelta

from psycopg2.extras import Json

from services.mlb_club_directory import MLB_TEAM_IDS
from sync_v3.comparison import compare_readiness
from sync_v3.dependencies import capture_reads
from sync_v3.deployment import club_role_movement, game_deployment, pitcher_measurement_history
from sync_v3.depth import club_depth
from sync_v3.group_performance import active_group_performance
from sync_v3.history import _store, _transaction
from sync_v3.readiness import represented_readiness
from sync_v3.rosters import dated_pitcher_sources
from sync_v3.rotation import club_rotation
from sync_v3.schedule_context import club_schedule_context
from sync_v3.season_deployment import pitcher_season_deployment
from sync_v3.workload import load_calendar, outing_pitch_comparison, regular_day, rest_from_calendar


def _readiness(cur, team, through):
    report = represented_readiness(cur, team, through)
    report['comparison'] = compare_readiness(report)
    # The relational source links preserve receipt IDs independently of the facts.
    facts = {key: value for key, value in report.items() if key not in (
        'calendar_source', 'reference_slate_source', 'decision_sources', 'roster_source', 'workload_sources', 'profiles')}
    facts['verified_decisions'] = sorted(report['decision_sources'])
    facts['profile_status'] = {player: profile['reason'] for player, profile in report.get('profiles', {}).items()}
    return facts


def _rotation(cur, team, through):
    days = [through - timedelta(days=n) for n in range(14)]
    facts = club_rotation({d: regular_day(cur, d, team=team) for d in days}, team, through)
    for day in facts['dates'].values():
        del day['sources']
    return facts


def _schedule(cur, team, through):
    facts = club_schedule_context(cur, team, through)
    for day in facts['dates'].values():
        del day['source']
    return facts


def _depth(cur, team, through):
    facts = club_depth(cur, team, through)
    del facts['directory_source']
    views = [*facts['views'].values(), *facts['affiliate_views'].values()]
    if 'active_profiles' in facts:
        views.append(facts['active_profiles'])
    for view in views:
        del view['source']
    return facts


def _roles(cur, team, through):
    report = club_role_movement(cur, team, through)
    report['games_by_date'] = {
        day: {game: {key: row[key] for key in ('final_reason', 'entry_reason')}
              for game, row in slate['games'].items()}
        for day, slate in report.pop('sources').items()
    }
    return report


def _group(cur, team, through):
    facts = active_group_performance(cur, team, through)
    del facts['roster_source']
    for profile in facts['profiles'].values():
        del profile['sources']
    for day in facts.get('dates', {}).values():
        del day['sources']
    return facts


def _pitcher(cur, player, through):
    season = pitcher_season_deployment(cur, player, through)
    facts = pitcher_measurement_history(cur, player, through, season)
    del season['sources']
    facts['deployment'] = season
    del facts['pitch_history']['season_sources']
    del facts['performance']['season_sources']
    for game in facts['performance']['games']:
        del game['boxscore'], game['schedule']
    for month in facts['pitch_history']['months']:
        for game in month['games']:
            del game['sources']
    return facts


def _pitcher_rest(cur, player, through):
    calendar = load_calendar(cur, through)
    identity = dated_pitcher_sources(cur, player, through)
    rest = rest_from_calendar(calendar, player, through, identity_sources=identity)
    outing = outing_pitch_comparison(calendar, player, through)
    del rest['identity_sources'], rest['sources'], outing['sources']
    return {'rest': rest, 'outing_comparison': outing}


def _game(cur, game, through):
    facts = game_deployment(cur, game, through, include_pitch_samples=True)
    del facts['sources']
    return facts


# Methodologies are explicit to allow a future calculation to coexist with its predecessor.
DOMAINS = {
    'readiness': ('team', 'candidate_regular_readiness_v1', _readiness),
    'rotation': ('team', 'candidate_rotation_v1', _rotation),
    'schedule': ('team', 'candidate_schedule_context_v1', _schedule),
    'depth': ('team', 'candidate_roster_depth_v1', _depth),
    'roles': ('team', 'candidate_club_role_movement_v1', _roles),
    'group_performance': ('team', 'candidate_active_group_performance_v1', _group),
    'pitcher_rest': ('pitcher', 'candidate_pitcher_rest_v1', _pitcher_rest),
    'pitcher_profile': ('pitcher', 'candidate_pitcher_profile_v1', _pitcher),
    'game_deployment': ('game', 'candidate_game_deployment_v1', _game),
}


def _append(cur, domain, identity, through):
    subject, methodology, build = DOMAINS[domain]
    if type(identity) is not int or identity <= 0 or (subject == 'team' and identity not in MLB_TEAM_IDS):
        raise ValueError('Snapshot requires an official MLB subject')
    cur.execute('SELECT pg_advisory_xact_lock(hashtext(%s),%s)', (subject, identity))
    with capture_reads(cur) as reads:
        facts = build(cur, identity, through)
    return _store(cur, subject, identity, through, methodology, facts, sorted(reads.receipts), reads.requests)


def record_intelligence(connection, domain, identity, through):
    return _transaction(connection, _append, domain, identity, through)


def _affected(cur, receipt, domains):
    cur.execute('SELECT endpoint,parameters FROM candidate.fetches WHERE id=%s', (receipt,))
    request = cur.fetchone()
    if not request:
        raise ValueError('Unknown receipt')
    by_method = {DOMAINS[domain][1]: domain for domain in domains}
    cur.execute("""SELECT h.methodology,h.mlb_id,h.represented FROM candidate.history_requests d
                   JOIN candidate.workload_history h ON h.id=d.snapshot
                   WHERE d.endpoint=%s AND d.parameters=%s AND h.methodology=ANY(%s) AND NOT EXISTS (
                       SELECT 1 FROM candidate.workload_history newer WHERE
                       (newer.subject,newer.mlb_id,newer.represented,newer.methodology)=
                       (h.subject,h.mlb_id,h.represented,h.methodology) AND newer.revision>h.revision)
                   ORDER BY h.subject,h.mlb_id,h.represented,h.methodology""", (request[0], Json(request[1]), list(by_method)))
    return [_append(cur, by_method[method], identity, through) for method, identity, through in cur.fetchall()]


def rebuild_intelligence(connection, receipt, *, domains=tuple(DOMAINS)):
    return _transaction(connection, _affected, receipt, domains)
