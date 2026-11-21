"""Dated MLB roster views and independently scoped affiliate roster observations."""

from collections import defaultdict
from datetime import date

from psycopg2.extras import Json

from services.mlb_club_directory import MLB_TEAM_IDS
from services.roster_evidence import roster_entry_player_id
from services.roster_status_sync import _two_way_eligible
from sync_v3.discovery import affiliate_directory_request, depth_directory, depth_roster_requests
from sync_v3.evidence import latest_qualified_source, latest_source_status, replay
from sync_v3.roster_scope import NON_PITCHING_POSITIONS
from sync_v3.rosters import roster_on


def _pitchers(body, team, parent, kind):
    if body.get('teamId') != team or body.get('rosterType') != kind or not isinstance(body.get('roster'), list):
        return None, 'missing_scoped_roster_collection'
    players = defaultdict(list)
    for row in body['roster']:
        if not isinstance(row, dict) or not isinstance(row.get('person'), dict):
            return None, 'missing_player_identity'
        player = roster_entry_player_id(row)
        if not player:
            return None, 'missing_player_identity'
        if row.get('parentTeamId') not in (None, parent):
            return None, 'parent_club_conflict'
        if (not isinstance(row.get('position'), dict) or not isinstance(row.get('status') or {}, dict)
                or not isinstance(row['person'].get('pitchHand') or {}, dict)):
            return None, 'invalid_roster_attributes'
        players[player].append(row)
    pitchers = {}
    for player, entries in players.items():
        positions = {(r.get('position') or {}).get('code') for r in entries}
        if len(positions) != 1 or None in positions:
            return None, 'pitcher_population_unresolved'
        code, = positions
        if code not in ('1', 'Y') and not any(_two_way_eligible(r) for r in entries):
            if code not in NON_PITCHING_POSITIONS:
                return None, 'pitcher_population_unresolved'
            continue
        hands = {(r['person'].get('pitchHand') or {}).get('code') for r in entries}
        hand = next(iter(hands)) if len(hands) == 1 else None
        pitchers[player] = {'profile_pitch_hand': hand if hand in ('L', 'R', 'S') else None,
                            'status_codes': sorted({r['status']['code'] for r in entries
                                                    if (r.get('status') or {}).get('code')})}
    return pitchers, None


def _view(cur, team, parent, kind, params, *, membership=False):
    endpoint = f'/teams/{team}/roster'
    latest = latest_source_status(cur, endpoint, params)
    result = {'source': latest[0] if latest else None, 'pitchers': None, 'reason': None}
    if latest is None:
        result['reason'] = 'missing_roster_observation'
        return result
    source, outcome, reason = latest
    if outcome != 'received' or reason is not None:
        result['reason'] = reason or outcome
        return result
    receipt = replay(cur, source)
    if membership and roster_on(cur, team, kind, date.fromisoformat(params['date'])) is None:
        result['reason'] = 'unconfirmed_mlb_membership'
        return result
    result['retrieved_at'] = receipt.retrieved_at.isoformat()
    result['pitchers'], result['reason'] = _pitchers(receipt.body, team, parent, kind)
    return result


def club_depth(cur, team, day):
    if team not in MLB_TEAM_IDS:
        raise ValueError('Expected an MLB parent')
    result = {'team': team, 'represented': day.isoformat(), 'views': {}, 'affiliate_views': {},
              'directory_source': None, 'affiliate_assignments': None, 'assignment_reason': None,
              'profile_hand_basis': 'official_person_attribute_at_retrieval'}
    views = result['views']
    for kind in ('active', '40Man', 'fullRoster'):
        params = {'date': day.isoformat(), 'rosterType': kind}
        views[kind] = _view(cur, team, team, kind, params, membership=kind != 'fullRoster')
    active = views['active']['pitchers']
    forty = views['40Man']['pitchers']
    result['forty_man_outside_active'] = (sorted(forty.keys() - active.keys())
                                         if active is not None and forty is not None else None)
    request = affiliate_directory_request(day, team)
    source = latest_qualified_source(cur, request.endpoint, request.params())
    result['directory_source'] = source
    if source is None:
        result['assignment_reason'] = 'missing_or_refused_affiliate_directory'
        return result
    directory = depth_directory(request, replay(cur, source).body)
    requests = depth_roster_requests(day, directory)
    surveyed = set()
    assignments = defaultdict(list)
    complete = True
    for req in requests:
        org_team = int(req.endpoint.split('/')[2])
        surveyed.add(org_team)
        view = _view(cur, org_team, team, 'active', req.params())
        if org_team == team:
            listed = views['active']['pitchers']
            hydrated = view['pitchers']
            if listed is None or hydrated is None or set(hydrated) != set(listed):
                view.update(pitchers=None, reason=view['reason'] or 'mlb_active_rosters_disagree')
            result['active_profiles'] = view
            continue
        result['affiliate_views'][org_team] = {**directory[org_team], **view}
        if view['reason']:
            complete = False
        else:
            for player in view['pitchers']:
                assignments[player].append(org_team)
    result['other_directory_entries'] = [directory[t] for t in sorted(directory.keys() - surveyed)]
    if not complete or len(surveyed) == 1:
        result['assignment_reason'] = 'affiliated_level_coverage_incomplete'
    elif views['active']['pitchers'] is None:
        result['assignment_reason'] = 'mlb_active_membership_unverified'
    else:
        active = set(views['active']['pitchers'])
        result['assignment_conflicts'] = {p: clubs for p, clubs in assignments.items() if len(clubs) > 1 or p in active}
        result['affiliate_assignments'] = {p: clubs[0] for p, clubs in assignments.items()
                                           if p not in result['assignment_conflicts']}
    return result


def roster_depth_evidence(depth, team, through):
    """Describe dated MLB roster listings without assigning off-active pitchers a bullpen role."""
    facts = depth['value']
    if facts['team'] != team or facts['represented'] != through.isoformat():
        raise ValueError('Historical roster evidence belongs to another club or date')
    result = dict(team=team, represented=facts['represented'], citation=depth['citation'],
                  active_listed=None, forty_man_listed=None, forty_man_listed_outside_active=None, status_codes=None)
    active, forty = (facts['views'][kind] for kind in ('active', '40Man'))
    for view in (active, forty):
        if view['reason'] or view['pitchers'] is None:
            return dict(result, reason=view['reason'] or 'missing_dated_roster')
    if (facts.get('active_profiles') or {}).get('reason') == 'mlb_active_rosters_disagree':
        return dict(result, reason='mlb_active_rosters_disagree')
    outside = sorted(int(player) for player in forty['pitchers'].keys() - active['pitchers'].keys())
    if outside != facts['forty_man_outside_active']:
        raise ValueError('Historical roster comparison disagrees with its frozen depth snapshot')
    codes = {player: forty['pitchers'][str(player)]['status_codes'] for player in outside}
    return dict(result, active_listed=len(active['pitchers']), forty_man_listed=len(forty['pitchers']),
                forty_man_listed_outside_active=outside, status_codes=codes,
                reason='off_active_bullpen_population_unverified')


def named_roster_lists(depth, evidence, directory):
    """Display the frozen club lists even when a BaseballOS pitcher route is unknown."""
    if evidence['active_listed'] is None:
        return None
    team = evidence['team']
    active = depth['value']['views']['active']['pitchers']
    lists = {}
    for kind, ids in [('active', sorted(map(int, active))), ('forty_man_only', evidence['forty_man_listed_outside_active'])]:
        rows = []
        for mlb in ids:
            person = directory.get(mlb, {})
            receipt = person.get('roster_observation', {})
            matches = person.get('team_id') == team if kind == 'active' else (
                receipt.get('team_id') == team and receipt.get('membership') == '40Man'
                and receipt.get('represented') == evidence['represented'])
            rows.append(dict(mlb_id=mlb, name=person.get('name') if matches else None))
        lists[kind] = rows
    return lists


def dated_roster_capture(cur, generation, evidence, kind):
    """Resolve one confirmed source body cited by the frozen club depth snapshot."""
    if kind not in ('active', '40Man'):
        raise ValueError('Expected an MLB membership roster')
    team, day = evidence['team'], evidence['represented']
    endpoint = f'/teams/{team}/roster'
    params = {'date': day, 'rosterType': kind}
    cur.execute("""SELECT min(f.id) FROM candidate.generation_inputs g
                   JOIN candidate.workload_history h ON h.id=g.snapshot
                   JOIN candidate.workload_history_sources hs ON hs.snapshot=h.id
                   JOIN candidate.fetches f ON f.id=hs.source_id
                   JOIN candidate.confirmations c ON c.source_id=f.id AND c.domain='roster'
                   WHERE g.generation=%s AND h.subject='team' AND h.mlb_id=%s AND h.represented=%s
                     AND h.methodology=%s AND f.endpoint=%s AND f.parameters=%s AND c.identity=%s
                   GROUP BY f.sha256""",
                (generation, team, day, evidence['citation']['methodology'], endpoint,
                 Json(params), f'{team}/{kind}/{day}'))
    receipts = cur.fetchall()
    if len(receipts) != 1:
        return None
    capture = replay(cur, receipts[0][0])
    if capture.request.endpoint != endpoint or capture.request.params() != params:
        raise ValueError('Roster receipt belongs to another club, membership type or date')
    return capture


def forty_man_status_labels(cur, generation, evidence):
    """Read MLB's own status wording from the forty-man response pinned by this edition."""
    expected = evidence['status_codes']
    if not expected:
        return {}
    capture = dated_roster_capture(cur, generation, evidence, '40Man')
    if capture is None:
        return {}
    statuses = defaultdict(lambda: defaultdict(set))
    for member in capture.body['roster']:
        player = roster_entry_player_id(member)
        raw = member.get('status') or {}
        if player in expected and raw.get('code'):
            description = raw.get('description')
            statuses[player][raw['code']].add(description if isinstance(description, str) else None)
    labels = {}
    for player, codes in expected.items():
        if set(codes) != statuses[player].keys():
            continue
        labels[player] = {}
        for code, descriptions in statuses[player].items():
            if len(descriptions) == 1:
                label = next(iter(descriptions))
                if isinstance(label, str) and label.strip():
                    labels[player][code] = label
    return labels
