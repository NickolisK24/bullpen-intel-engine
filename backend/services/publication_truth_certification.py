"""Read-only truth certification of one trusted Dashboard publication.

Answers, per MLB club and per domain, whether the facts frozen in a published
snapshot agree with the canonical rows they were derived from:

* roster: every Active Bullpen arm is a known pitcher, on a governed MLB club,
  listed once across the league, and backed by a same-date roster snapshot
  for that club with MLB active-roster presence;
* workload: each arm's frozen "pitched yesterday", Back-to-Back and window
  appearance counts agree with an INDEPENDENT recount of GameLog relief lines
  (``games_started == 0``) for the frozen calendar windows;
* rest population: arms whose availability is driven only by stale data
  (no appearance inside the active window) are counted per club, because the
  public reader form of that label ("On Watch") is shared with workload
  concern;
* team_state: the frozen Team State receipt is present, available, and one of
  the canonical public states;
* schedule: slate coverage for ``data_through`` and the schedule rows of the
  presented dates, including games retired from MLB's schedule (#904);
* tonight: the immutable tonight_v1 editions bound to the snapshot, and the
  state each stored game is served with now.

It never writes. ``scripts/certify_publication_truth.py`` runs it inside a
read-only transaction. The workload recount deliberately does not reuse the
publisher's classifier: an opener credited as a start (or a bulk reliever
credited as relief) by ``services.game_shape`` is reported as a discrepancy
for review, not silently accepted.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Mapping

from models.game_log import GameLog
from models.pitcher import Pitcher
from models.roster_status_snapshot import RosterStatusSnapshot
from models.scheduled_game import ScheduledGame
from models.slate_game import SlateGame
from models.tonight_publication import TonightPublication
from services import public_serving_authority as psa
from services import slate_coverage, tonight_read_model
from services.mlb_club_directory import MLB_CLUBS, MLB_TEAM_IDS
from services.tonight_v1_serving import overlay_game_state
from utils.db import db


CERTIFICATION_CONTRACT = 'publication_truth_certification_v1'
PASS, CONDITIONAL, FAIL = 'PASS', 'CONDITIONAL', 'FAIL'
CANONICAL_PUBLIC_STATES = frozenset({'fresh', 'stretched', 'vulnerable'})
RETIRED_STATUS_CODE = 'RETIRED'


def _iso(value):
    return value.isoformat() if hasattr(value, 'isoformat') else value


def _date(value):
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _package(snapshot):
    payload = snapshot.payload if isinstance(snapshot.payload, Mapping) else {}
    package = payload.get(psa.TEAM_BOARD_PACKAGE_KEY)
    return package if isinstance(package, Mapping) else None


def _team_package(package, team_id):
    value = (package.get('by_team_id') or {}).get(str(team_id)) if package else None
    return value if isinstance(value, Mapping) else None


def _availability(record):
    nested = record.get('availability')
    return nested if isinstance(nested, Mapping) else record


# ── Roster ───────────────────────────────────────────────────────────────────

def certify_roster(snapshot, *, membership_date):
    package = _package(snapshot)
    seen = defaultdict(list)
    teams = {}
    for club in MLB_CLUBS:
        team_package = _team_package(package, club.team_id)
        arms = tonight_read_model._active_arms(team_package) if team_package else []
        pitcher_ids = [arm.get('pitcher_id') for arm in arms]
        for pitcher_id in pitcher_ids:
            seen[pitcher_id].append(club.team_id)
        snapshots = {
            row.pitcher_id: row
            for row in RosterStatusSnapshot.query
            .filter(RosterStatusSnapshot.pitcher_id.in_([p for p in pitcher_ids if p]))
            .filter(RosterStatusSnapshot.snapshot_date == membership_date)
            .all()
        } if pitcher_ids else {}
        pitchers = {
            row.id: row for row in Pitcher.query.filter(
                Pitcher.id.in_([p for p in pitcher_ids if p])
            ).all()
        } if pitcher_ids else {}
        issues = []
        for pitcher_id in pitcher_ids:
            pitcher = pitchers.get(pitcher_id)
            row = snapshots.get(pitcher_id)
            if pitcher is None:
                issues.append({'pitcher_id': pitcher_id, 'issue': 'unknown_pitcher'})
                continue
            if row is None:
                issues.append({'pitcher_id': pitcher_id, 'mlb_id': pitcher.mlb_id,
                               'issue': 'no_roster_snapshot_for_membership_date'})
            elif row.team_id != club.team_id:
                issues.append({'pitcher_id': pitcher_id, 'mlb_id': pitcher.mlb_id,
                               'issue': 'roster_snapshot_other_team',
                               'snapshot_team_id': row.team_id})
            elif row.active_roster is not True:
                issues.append({'pitcher_id': pitcher_id, 'mlb_id': pitcher.mlb_id,
                               'issue': 'not_on_mlb_active_roster',
                               'roster_status': row.roster_status})
        teams[club.team_id] = {
            'team': club.abbreviation,
            'package_present': team_package is not None,
            'active_bullpen_count': len(pitcher_ids),
            'issues': issues,
        }
    duplicates = {pid: owners for pid, owners in seen.items() if len(owners) > 1}
    for pitcher_id, owners in duplicates.items():
        for team_id in owners:
            teams[team_id]['issues'].append({
                'pitcher_id': pitcher_id, 'issue': 'listed_by_multiple_clubs',
                'team_ids': owners,
            })
    for result in teams.values():
        result['verdict'] = (
            FAIL if result['issues'] else PASS if result['package_present'] else CONDITIONAL
        )
    return teams


# ── Workload ─────────────────────────────────────────────────────────────────

def _relief_dates(pitcher_id, start, end):
    rows = (
        GameLog.query
        .filter(GameLog.pitcher_id == pitcher_id)
        .filter(GameLog.game_date >= start)
        .filter(GameLog.game_date <= end)
        .all()
    )
    relief = [row for row in rows if row.games_started == 0]
    unknown = [row for row in rows if row.games_started is None]
    return relief, unknown


def _complete_value(fact):
    if isinstance(fact, Mapping) and fact.get('status') == 'complete':
        return fact.get('value')
    return None


def certify_workload(snapshot):
    package = _package(snapshot)
    anchor = _date(snapshot.data_through)
    teams = {}
    for club in MLB_CLUBS:
        team_package = _team_package(package, club.team_id)
        carrier = psa._frozen_recent_usage_rest_for_view(snapshot, team_package) if team_package else None
        if carrier is None:
            teams[club.team_id] = {'team': club.abbreviation, 'verdict': CONDITIONAL,
                                   'reason': 'recent_usage_rest_unavailable',
                                   'arms_checked': 0, 'mismatches': []}
            continue
        mismatches, checked, incomplete = [], 0, 0
        for item in carrier.get('active_pitchers') or ():
            pitcher_id = item.get('pitcher_id')
            relief, unknown = _relief_dates(pitcher_id, anchor - timedelta(days=6), anchor)
            dates = {row.game_date for row in relief}
            expected = {
                'pitched_yesterday': anchor in dates,
                'back_to_back': anchor in dates and anchor - timedelta(days=1) in dates,
                'appearances_last_3_days': sum(
                    1 for row in relief if row.game_date >= anchor - timedelta(days=2)),
                'appearances_last_7_days': len(relief),
            }
            published = {
                'pitched_yesterday': _complete_value(item.get('pitched_yesterday')),
                'back_to_back': _complete_value(item.get('back_to_back')),
                'appearances_last_3_days': _complete_value(
                    ((item.get('windows') or {}).get('last_3_days') or {}).get('appearances')),
                'appearances_last_7_days': _complete_value(
                    ((item.get('windows') or {}).get('last_7_days') or {}).get('appearances')),
            }
            if any(value is None for value in published.values()):
                incomplete += 1
            checked += 1
            diff = {
                key: {'published': published[key], 'recount': expected[key]}
                for key in expected
                if published[key] is not None and published[key] != expected[key]
            }
            if diff:
                mismatches.append({'pitcher_id': pitcher_id,
                                   'pitcher_name': item.get('pitcher_name'),
                                   'unknown_start_flags': len(unknown), 'diff': diff})
        teams[club.team_id] = {
            'team': club.abbreviation,
            'arms_checked': checked,
            'arms_with_incomplete_facts': incomplete,
            'mismatches': mismatches,
            'verdict': FAIL if mismatches else (CONDITIONAL if incomplete else PASS),
        }
    return teams


# ── Availability population (stale-data On Watch) ────────────────────────────

def certify_availability_population(snapshot):
    package = _package(snapshot)
    teams = {}
    for club in MLB_CLUBS:
        team_package = _team_package(package, club.team_id)
        records = psa._records_for_view(team_package, False) if team_package else []
        statuses = Counter()
        stale_monitor = 0
        for record in records:
            availability = _availability(record)
            status = availability.get('availability_status')
            statuses[status] += 1
            if status == 'Monitor' and str(availability.get('data_state') or '') == 'stale':
                stale_monitor += 1
        teams[club.team_id] = {
            'team': club.abbreviation,
            'status_counts': dict(statuses),
            'monitor_from_stale_data_only': stale_monitor,
        }
    return teams


# ── Team State ───────────────────────────────────────────────────────────────

TEAM_STATE_DETAIL_KEYS = (
    'usable_arm_count', 'unresolved_arm_count', 'coverage', 'data_state',
    'confidence', 'status_code', 'eligibility', 'reason_code', 'reason_codes',
)


def certify_team_state(snapshot):
    teams = {}
    for club in MLB_CLUBS:
        state = tonight_read_model._team_state(snapshot, club.team_id)
        present, value = tonight_read_model.receipt_value(snapshot, club.team_id)
        detail = {key: value.get(key) for key in TEAM_STATE_DETAIL_KEYS
                  if isinstance(value, Mapping) and key in value}
        verdict = PASS if (
            state.get('available') and state.get('public_state') in CANONICAL_PUBLIC_STATES
        ) else CONDITIONAL if present else FAIL
        teams[club.team_id] = {'team': club.abbreviation, **state,
                               'receipt_present': present, 'detail': detail,
                               'verdict': verdict}
    return teams


# ── Schedule and Tonight ─────────────────────────────────────────────────────

def certify_schedule(snapshot):
    data_through = _date(snapshot.data_through)
    reference = _date(snapshot.availability_reference_date)
    coverage = slate_coverage.compute_slate_coverage(data_through)
    dates = sorted({d for d in (data_through, reference) if d is not None})
    rows = ScheduledGame.query.filter(ScheduledGame.game_date.in_(dates)).all()
    by_game = defaultdict(set)
    for row in rows:
        by_game[(row.game_date.isoformat(), row.game_pk)].add(
            (row.status_state, row.status_code))
    retired = sorted(
        pk for (_day, pk), states in by_game.items()
        if any(code == RETIRED_STATUS_CODE for _s, code in states)
    )
    mixed = sorted(pk for (_day, pk), states in by_game.items() if len(states) > 1)
    return {
        'data_through': _iso(data_through),
        'availability_reference_date': _iso(reference),
        'slate_complete': coverage.get('complete_enough_to_publish'),
        'slate_reason_codes': coverage.get('reason_codes'),
        'games_by_date': {
            day: sorted(pk for (d, pk) in by_game if d == day) for day in map(_iso, dates)
        },
        'retired_game_pks': retired,
        'games_with_disagreeing_rows': mixed,
        'verdict': FAIL if mixed else PASS if coverage.get('complete_enough_to_publish') else CONDITIONAL,
    }


def certify_tonight(snapshot):
    editions = TonightPublication.query.filter_by(dashboard_snapshot_id=snapshot.id).all()
    results = []
    for edition in editions:
        payload = edition.payload if isinstance(edition.payload, Mapping) else {}
        games = payload.get('games') or []
        current = {
            row.game_pk: row for row in SlateGame.query.filter(
                SlateGame.game_pk.in_([g.get('game_pk') for g in games])
            ).all()
        } if games else {}
        served, _identity = overlay_game_state(payload, current)
        served_states = {g.get('game_pk'): g.get('state') for g in served.get('games') or []}
        issues = []
        for game in games:
            row = current.get(game.get('game_pk'))
            if row is None:
                issues.append({'game_pk': game.get('game_pk'), 'issue': 'no_current_slate_row'})
            elif _iso(row.game_date_et) != _iso(edition.reference_date):
                issues.append({'game_pk': game.get('game_pk'), 'issue': 'game_date_moved'})
            for side in ('away', 'home'):
                team_id = (game.get(side) or {}).get('team_id')
                if team_id not in MLB_TEAM_IDS:
                    issues.append({'game_pk': game.get('game_pk'), 'issue': f'{side}_not_mlb_club'})
        results.append({
            'reference_date': _iso(edition.reference_date),
            'stored_game_count': (payload.get('summary') or {}).get('game_count'),
            'served_game_count': (served.get('summary') or {}).get('game_count'),
            'served_states': served_states,
            'issues': issues,
            'verdict': FAIL if issues else PASS,
        })
    return results


# ── Orchestration ────────────────────────────────────────────────────────────

def _league_verdict(per_team_domains):
    verdicts = [result['verdict'] for domain in per_team_domains for result in domain.values()]
    if FAIL in verdicts:
        return FAIL
    if CONDITIONAL in verdicts:
        return CONDITIONAL
    return PASS


def certify_snapshot(snapshot, *, membership_date=None):
    """The full read-only certification document for one snapshot."""
    membership_date = membership_date or _date(snapshot.availability_reference_date)
    roster = certify_roster(snapshot, membership_date=membership_date)
    workload = certify_workload(snapshot)
    team_state = certify_team_state(snapshot)
    team_verdicts = {}
    for club in MLB_CLUBS:
        verdicts = [d[club.team_id]['verdict'] for d in (roster, workload, team_state)]
        team_verdicts[club.abbreviation] = (
            FAIL if FAIL in verdicts else CONDITIONAL if CONDITIONAL in verdicts else PASS
        )
    schedule = certify_schedule(snapshot)
    tonight = certify_tonight(snapshot)
    domain_verdicts = {
        'roster': _league_verdict([roster]),
        'workload': _league_verdict([workload]),
        'team_state': _league_verdict([team_state]),
        'schedule': schedule['verdict'],
        'tonight': (FAIL if any(t['verdict'] == FAIL for t in tonight)
                    else PASS if tonight else CONDITIONAL),
    }
    overall = (
        FAIL if FAIL in domain_verdicts.values()
        else CONDITIONAL if CONDITIONAL in domain_verdicts.values() else PASS
    )
    counts = Counter(team_verdicts.values())
    return {
        'contract': CERTIFICATION_CONTRACT,
        'snapshot_id': snapshot.id,
        'sync_run_id': getattr(snapshot, 'sync_run_id', None),
        'data_through': _iso(snapshot.data_through),
        'availability_reference_date': _iso(snapshot.availability_reference_date),
        'membership_date': _iso(membership_date),
        'league_verdict': overall,
        'teams_passed': counts.get(PASS, 0),
        'teams_conditional': counts.get(CONDITIONAL, 0),
        'teams_failed': counts.get(FAIL, 0),
        'domains': domain_verdicts,
        'team_verdicts': team_verdicts,
        'roster': {str(k): v for k, v in roster.items()},
        'workload': {str(k): v for k, v in workload.items()},
        'availability_population': {
            str(k): v for k, v in certify_availability_population(snapshot).items()
        },
        'team_state': {str(k): v for k, v in team_state.items()},
        'schedule': schedule,
        'tonight': tonight,
        'not_covered': [
            'MLB live roster/transaction parity (no MLB source access in this harness)',
            'What Changed event receipts',
            'Rotation impact, deployment and performance context',
            'Frontend rendering parity',
        ],
    }
