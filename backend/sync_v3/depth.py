"""Dated MLB roster views and independently scoped affiliate roster observations."""

from collections import defaultdict
from datetime import date

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
