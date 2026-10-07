"""Read-only truth certification of one trusted Dashboard publication.

Answers, per MLB club and per domain, whether the facts frozen in a published
snapshot agree with the canonical rows they were derived from:

* roster: the Active Bullpen the publication serves is compared with the
  canonical Active Bullpen membership authority on the membership date
  (missing, extra, duplicate, wrong-team, unknown pitcher), and every arm is
  checked against the same-date roster snapshot for MLB active-roster presence;
* workload: each arm's frozen recent-usage facts (last appearance, pitched
  yesterday, Back-to-Back, 3-in-4, 4-in-6, and the appearance/pitch/out totals
  of the 1, 3 and 7 day windows) are compared with an INDEPENDENT recount of
  GameLog relief lines (``games_started == 0``);
* arm attribution: for every arm in the Team State population, the frozen
  availability status and WHY it holds that status. A ``Monitor`` arm (public
  reader form "On Watch") is attributed to workload (fresh data), stale data,
  missing data, a workload fetch failure, an incomplete log, or another
  data state. This is the evidence for the stale/missing On Watch question;
* team_state: the frozen Team State receipt, the frozen per-team sidecar when
  one is bound to this snapshot, the clean/moderate/severe/unknown partition
  rebuilt from the frozen statuses, a reproduction check of the published
  state, and two clearly labelled HYPOTHETICAL / AUDIT ONLY recomputations;
* postseason: how much of each club's recent relief work comes from postseason
  game types (counted, never excluded);
* schedule: slate coverage for ``data_through`` and the schedule rows of the
  presented dates, including games retired from MLB's schedule (#904);
* tonight: the immutable tonight_v1 editions bound to the snapshot, and the
  state each stored game is served with now.

It never writes. ``scripts/certify_publication_truth.py`` runs it only after
the transaction is proven read-only. The workload recount deliberately does not
reuse the publisher's classifier: an opener credited as a start (or a bulk
reliever credited as relief) by ``services.game_shape`` is reported as a
discrepancy for review, not silently accepted.

The output is deterministic for the same rows: no wall-clock value is read and
every collection is sorted.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
from fractions import Fraction
from typing import Mapping

from models.dashboard_snapshot import DashboardSnapshot
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.roster_status_snapshot import RosterStatusSnapshot
from models.scheduled_game import ScheduledGame
from models.slate_game import SlateGame
from models.tonight_publication import TonightPublication
from services import public_serving_authority as psa
from services import slate_coverage, tonight_read_model
from services.mlb_club_directory import MLB_CLUBS, MLB_TEAM_IDS
from services.schedule_absence import POSTSEASON_GAME_TYPES
from services.team_state_public_vocabulary import INTERNAL_TO_PUBLIC_STATE
from services.tonight_v1_serving import overlay_game_state
from team_operations.contracts import TEAM_STATE_CONTRACT_A
from utils.db import db


CERTIFICATION_CONTRACT = 'publication_truth_certification_v2'
PASS, CONDITIONAL, FAIL = 'PASS', 'CONDITIONAL', 'FAIL'
CANONICAL_PUBLIC_STATES = frozenset({'fresh', 'stretched', 'vulnerable'})
RETIRED_STATUS_CODE = 'RETIRED'

HYPOTHETICAL_LABEL = 'HYPOTHETICAL / AUDIT ONLY'
HYPOTHETICAL_NOTICE = (
    'Audit-only recomputation from frozen counts with the Contract A thresholds. '
    'It is not the published Team State, not a proposed methodology, and not a '
    'correction. It only answers whether the state would differ if arms whose '
    'Monitor status comes from stale or missing evidence were not counted as '
    'workload concern.'
)

# Public reader forms of the internal availability statuses.
PUBLIC_STATUS_FORMS = {
    'Available': 'Available',
    'Monitor': 'On Watch',
    'Limited': 'Limited',
    'Avoid': 'Unavailable',
    'Unavailable': 'Unavailable',
}

# Why a Monitor (On Watch) arm is Monitor, from its frozen data_state.
MONITOR_WORKLOAD = 'monitor_workload'
MONITOR_STALE = 'monitor_stale'
MONITOR_MISSING = 'monitor_missing'
MONITOR_FETCH_FAILURE = 'monitor_fetch_failure'
MONITOR_INCOMPLETE = 'monitor_incomplete'
MONITOR_OTHER = 'monitor_other'
MONITOR_BASES = (
    MONITOR_WORKLOAD, MONITOR_STALE, MONITOR_MISSING, MONITOR_FETCH_FAILURE,
    MONITOR_INCOMPLETE, MONITOR_OTHER,
)
# Monitor bases that come from evidence quality rather than observed work.
EVIDENCE_QUALITY_MONITOR_BASES = (MONITOR_STALE, MONITOR_MISSING)

# Recent-usage windows and pattern spans (calendar days ending at data_through).
WINDOW_DAYS = {'yesterday': 1, 'last_3_days': 3, 'last_7_days': 7}
THREE_IN_FOUR = (4, 3)
FOUR_IN_SIX = (6, 4)
POSTSEASON_WINDOWS = {'last_7_days': 7, 'active_window_15_days': 15}

_CLEAN_SHARE_FRESH_MIN = Fraction(*TEAM_STATE_CONTRACT_A['clean_share_fresh_min'])
_CLEAN_COUNT_FRESH_MIN = TEAM_STATE_CONTRACT_A['clean_count_fresh_min']
_SEVERE_COUNT_FRESH_MAX = TEAM_STATE_CONTRACT_A['severe_count_fresh_max']
_CLEAN_COUNT_VULNERABLE_MAX = TEAM_STATE_CONTRACT_A['clean_count_vulnerable_max']
_SEVERE_SHARE_VULNERABLE_MIN = Fraction(*TEAM_STATE_CONTRACT_A['severe_share_vulnerable_min'])


def _iso(value):
    return value.isoformat() if hasattr(value, 'isoformat') else value


def _date(value):
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _mapping(value):
    return value if isinstance(value, Mapping) else {}


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


def reference_dates(snapshot):
    """The (membership, availability) dates the publication proof used."""
    from services.active_bullpen_coverage_diagnostic import reference_dates_for_snapshot
    return reference_dates_for_snapshot(snapshot)


def _frozen_records(team_package):
    if not team_package:
        return {}
    return {
        record.get('pitcher_id'): record
        for record in psa._records_for_view(team_package, False)
        if isinstance(record, Mapping) and type(record.get('pitcher_id')) is int
    }


def _membership(team_id, membership_date):
    from services.team_readiness_coverage import resolve_active_bullpen_membership
    member_ids, complete = resolve_active_bullpen_membership(team_id, membership_date)
    return sorted(int(pid) for pid in member_ids), bool(complete)


# ── Roster ───────────────────────────────────────────────────────────────────

def certify_roster(snapshot, *, membership_date, memberships=None):
    """Published Active Bullpen vs the canonical membership authority."""
    package = _package(snapshot)
    memberships = memberships if memberships is not None else {}
    seen = defaultdict(list)
    teams = {}
    for club in MLB_CLUBS:
        team_package = _team_package(package, club.team_id)
        arms = tonight_read_model._active_arms(team_package) if team_package else []
        published = sorted({arm.get('pitcher_id') for arm in arms if arm.get('pitcher_id')})
        for pitcher_id in published:
            seen[pitcher_id].append(club.team_id)
        if club.team_id not in memberships:
            memberships[club.team_id] = _membership(club.team_id, membership_date)
        expected, authority_complete = memberships[club.team_id]
        frozen = _frozen_records(team_package)
        snapshots = {
            row.pitcher_id: row
            for row in RosterStatusSnapshot.query
            .filter(RosterStatusSnapshot.pitcher_id.in_(published))
            .filter(RosterStatusSnapshot.snapshot_date == membership_date)
            .all()
        } if published else {}
        pitchers = {
            row.id: row for row in Pitcher.query.filter(Pitcher.id.in_(published)).all()
        } if published else {}
        issues, observations = [], []
        for pitcher_id in published:
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
            elif str(row.roster_status).lower() != 'active':
                issues.append({'pitcher_id': pitcher_id, 'mlb_id': pitcher.mlb_id,
                               'issue': 'not_on_mlb_active_roster',
                               'roster_status': row.roster_status})
            elif row.active_roster is False:
                # The canonical membership authority decides membership; a
                # disagreeing flag on the same row is recorded for review.
                observations.append({'pitcher_id': pitcher_id, 'mlb_id': pitcher.mlb_id,
                                     'observation': 'active_status_with_active_roster_false'})
        expected_set, published_set = set(expected), set(published)
        missing = sorted(expected_set - published_set)
        extra = sorted(published_set - expected_set) if authority_complete else []
        for pitcher_id in extra:
            issues.append({'pitcher_id': pitcher_id, 'issue': 'published_not_in_membership'})
        for pitcher_id in (pid for pid in missing if pid in frozen):
            issues.append({'pitcher_id': pitcher_id,
                           'issue': 'member_with_frozen_record_not_published'})
        missing_without_record = [pid for pid in missing if pid not in frozen]
        notes = []
        if missing_without_record:
            notes.append('members_without_frozen_record')
        if not authority_complete:
            notes.append('membership_authority_incomplete')
        if observations:
            notes.append('roster_flag_observations')
        teams[club.team_id] = {
            'team': club.abbreviation,
            'package_present': team_package is not None,
            'membership_authority_complete': authority_complete,
            'expected_member_count': len(expected),
            'active_bullpen_count': len(published),
            'missing': missing,
            'missing_without_frozen_record': missing_without_record,
            'extra': extra,
            'issues': issues,
            'observations': observations,
            'notes': notes,
        }
    duplicates = {pid: owners for pid, owners in seen.items() if len(owners) > 1}
    for pitcher_id, owners in sorted(duplicates.items()):
        for team_id in owners:
            teams[team_id]['issues'].append({
                'pitcher_id': pitcher_id, 'issue': 'listed_by_multiple_clubs',
                'team_ids': sorted(owners),
            })
    for result in teams.values():
        result['duplicate'] = sorted(
            i['pitcher_id'] for i in result['issues']
            if i['issue'] == 'listed_by_multiple_clubs')
        result['wrong_team'] = sorted(
            i['pitcher_id'] for i in result['issues']
            if i['issue'] == 'roster_snapshot_other_team')
        result['verdict'] = (
            FAIL if result['issues']
            else CONDITIONAL if (result['notes'] or not result['package_present'])
            else PASS
        )
    return teams


# ── Workload ─────────────────────────────────────────────────────────────────

def _relief_rows(pitcher_id, start, end):
    rows = (
        GameLog.query
        .filter(GameLog.pitcher_id == pitcher_id)
        .filter(GameLog.game_date >= start)
        .filter(GameLog.game_date <= end)
        .order_by(GameLog.game_date, GameLog.mlb_game_pk)
        .all()
    )
    relief = [row for row in rows if row.games_started == 0]
    unknown = [row for row in rows if row.games_started is None]
    return relief, unknown


def _latest_date(pitcher_id, anchor, *, relief_only):
    query = (
        db.session.query(db.func.max(GameLog.game_date))
        .filter(GameLog.pitcher_id == pitcher_id)
        .filter(GameLog.game_date <= anchor)
    )
    if relief_only:
        query = query.filter(GameLog.games_started == 0)
    return query.scalar()


def _complete_value(fact):
    if isinstance(fact, Mapping) and fact.get('status') == 'complete':
        return fact.get('value')
    return None


def _sum(rows, field):
    values = [getattr(row, field) for row in rows]
    return None if any(value is None for value in values) else sum(values)


def _pattern(dates, anchor, span, minimum):
    start = anchor - timedelta(days=span - 1)
    window = {day for day in dates if start <= day <= anchor}
    return anchor in window and len(window) >= minimum


def recount_arm(pitcher_id, *, anchor, reference):
    """Independent recount of one arm's recent relief work from GameLog."""
    relief, unknown = _relief_rows(pitcher_id, anchor - timedelta(days=6), anchor)
    dates = {row.game_date for row in relief}
    latest_relief = _latest_date(pitcher_id, anchor, relief_only=True)
    latest_any = _latest_date(pitcher_id, anchor, relief_only=False)
    recount = {
        'days_since_last_appearance': (
            (reference - latest_relief).days if latest_relief and reference else None),
        'pitched_yesterday': anchor in dates,
        'back_to_back': anchor in dates and anchor - timedelta(days=1) in dates,
        'three_in_four': _pattern(dates, anchor, *THREE_IN_FOUR),
        'four_in_six': _pattern(dates, anchor, *FOUR_IN_SIX),
    }
    for key, days in WINDOW_DAYS.items():
        start = anchor - timedelta(days=days - 1)
        window = [row for row in relief if row.game_date >= start]
        recount[f'{key}.appearances'] = len(window)
        recount[f'{key}.pitches'] = _sum(window, 'pitches_thrown')
        recount[f'{key}.outs'] = _sum(window, 'innings_pitched_outs')
    return recount, {
        'last_relief_appearance_date': _iso(latest_relief),
        'last_any_appearance_date': _iso(latest_any),
        'days_since_any_appearance': (
            (reference - latest_any).days if latest_any and reference else None),
        'unknown_start_flags': len(unknown),
    }


def published_arm_facts(item):
    published = {
        'days_since_last_appearance': _complete_value(item.get('days_since_last_appearance')),
        'pitched_yesterday': _complete_value(item.get('pitched_yesterday')),
        'back_to_back': _complete_value(item.get('back_to_back')),
        'three_in_four': _complete_value(item.get('three_in_four')),
        'four_in_six': _complete_value(item.get('four_in_six')),
    }
    windows = _mapping(item.get('windows'))
    for key in WINDOW_DAYS:
        window = _mapping(windows.get(key))
        for measure in ('appearances', 'pitches', 'outs'):
            published[f'{key}.{measure}'] = _complete_value(window.get(measure))
    return published


def certify_workload(snapshot):
    package = _package(snapshot)
    anchor = _date(snapshot.data_through)
    reference = _date(snapshot.availability_reference_date)
    teams = {}
    for club in MLB_CLUBS:
        team_package = _team_package(package, club.team_id)
        carrier = (
            psa._frozen_recent_usage_rest_for_view(snapshot, team_package)
            if team_package else None
        )
        if carrier is None:
            teams[club.team_id] = {
                'team': club.abbreviation, 'verdict': CONDITIONAL,
                'reason': 'recent_usage_rest_unavailable', 'arms_checked': 0,
                'facts_compared': 0, 'arms_with_incomplete_facts': 0, 'mismatches': [],
                'days_since_basis_any_appearance': 0,
            }
            continue
        mismatches, checked, compared, incomplete, any_basis = [], 0, 0, 0, 0
        items = sorted(
            (item for item in carrier.get('active_pitchers') or ()
             if isinstance(item, Mapping)),
            key=lambda item: item.get('pitcher_id') or 0,
        )
        for item in items:
            pitcher_id = item.get('pitcher_id')
            recount, context = recount_arm(pitcher_id, anchor=anchor, reference=reference)
            published = published_arm_facts(item)
            if any(value is None for value in published.values()):
                incomplete += 1
            checked += 1
            diff = {}
            for key, expected in recount.items():
                if published.get(key) is None:
                    continue
                compared += 1
                if published[key] == expected:
                    continue
                if (key == 'days_since_last_appearance'
                        and published[key] == context['days_since_any_appearance']):
                    # The carrier may take this from the availability record,
                    # whose latest appearance includes starts. Counted, not a
                    # contradiction.
                    any_basis += 1
                    continue
                diff[key] = {'published': published[key], 'recount': expected}
            if diff:
                mismatches.append({'pitcher_id': pitcher_id,
                                   'pitcher_name': item.get('pitcher_name'),
                                   **context, 'diff': diff})
        teams[club.team_id] = {
            'team': club.abbreviation,
            'arms_checked': checked,
            'facts_compared': compared,
            'arms_with_incomplete_facts': incomplete,
            'days_since_basis_any_appearance': any_basis,
            'mismatches': mismatches,
            'verdict': FAIL if mismatches else (CONDITIONAL if incomplete else PASS),
        }
    return teams


# ── Team State sidecars (frozen per-team arm reads) ──────────────────────────

def team_state_sidecars(snapshot):
    """The frozen Team Board sidecar bound to this snapshot, per team id."""
    from services.team_board_delta_substrate import SNAPSHOT_SOURCE_PREFIX, SNAPSHOT_TYPE

    rows = (
        DashboardSnapshot.query
        .filter(DashboardSnapshot.snapshot_type == SNAPSHOT_TYPE)
        .filter(DashboardSnapshot.data_through == _date(snapshot.data_through))
        .filter(DashboardSnapshot.source.like(f'{SNAPSHOT_SOURCE_PREFIX}%'))
        .order_by(DashboardSnapshot.id)
        .all()
    )
    bound = {}
    for row in rows:
        payload = _mapping(row.payload)
        if _mapping(payload.get('source')).get('snapshot_id') != snapshot.id:
            continue
        team_id = payload.get('team_id')
        if type(team_id) is int:
            bound[team_id] = row
    return bound


# ── Arm attribution (why each arm holds its status) ──────────────────────────

def monitor_basis(availability):
    """Why a Monitor arm is Monitor, from its frozen evidence state."""
    from services.availability_snapshot import FETCH_FAILED_WORKLOAD_REASON

    data_state = availability.get('data_state')
    inputs = _mapping(availability.get('inputs'))
    if data_state == 'fresh':
        return MONITOR_WORKLOAD
    if data_state == 'stale':
        return MONITOR_STALE
    if data_state == 'missing':
        return MONITOR_MISSING
    if data_state == 'incomplete':
        if inputs.get('workload_fetch_failed') or FETCH_FAILED_WORKLOAD_REASON in (
            availability.get('reasons') or ()
        ):
            return MONITOR_FETCH_FAILURE
        return MONITOR_INCOMPLETE
    return MONITOR_OTHER


def _status_bucket(status):
    return {
        'Available': 'clean', 'Monitor': 'monitor', 'Limited': 'limited',
        'Avoid': 'avoid', 'Unavailable': 'unavailable',
    }.get(status, 'unknown')


def _arm_row(pitcher_id, record, sidecar_record, ledger_complete):
    availability = _availability(record) if record else {}
    inputs = _mapping(availability.get('inputs'))
    status = availability.get('availability_status') if record else None
    bucket = _status_bucket(status)
    data_state = availability.get('data_state')
    reasons = list(availability.get('reasons') or ())
    sidecar_record = _mapping(sidecar_record)
    sidecar_evidence = _mapping(sidecar_record.get('evidence_state'))
    return {
        'pitcher_id': pitcher_id,
        'pitcher_name': (record or {}).get('name') or sidecar_record.get('pitcher_name'),
        'frozen_record_present': record is not None,
        'availability_status': status,
        'public_form': PUBLIC_STATUS_FORMS.get(status),
        'bucket': bucket,
        'monitor_basis': monitor_basis(availability) if bucket == 'monitor' else None,
        'data_state': data_state,
        'confidence': availability.get('confidence'),
        'latest_game_date': _iso(inputs.get('latest_game_date')),
        'days_rest': inputs.get('days_rest'),
        'first_reason': reasons[0] if reasons else None,
        'sidecar_public_read': _mapping(sidecar_record.get('public_read')).get('key'),
        'sidecar_data_state': sidecar_evidence.get('data_state'),
        'sidecar_confidence': sidecar_evidence.get('confidence'),
        # The trust gate's rule (api.team_operations): a stale arm is usable
        # coverage when the appearance ledger is complete. Evaluated now.
        'ledger_confirmed_rest': bool(data_state == 'stale' and ledger_complete),
    }


def _population(team_package, sidecar, membership):
    """The Team State arm population, preferring the frozen sidecar."""
    frozen = _frozen_records(team_package)
    if sidecar is not None:
        arm_read = _mapping(_mapping(_mapping(sidecar.payload).get('values')).get('arm_read'))
        records = [r for r in arm_read.get('records') or () if isinstance(r, Mapping)]
        if records or arm_read.get('member_pitcher_ids'):
            by_id = {r.get('pitcher_id'): r for r in records}
            return (sorted(by_id), by_id, frozen, 'frozen_team_state_sidecar',
                    sorted(arm_read.get('missing_record_pitcher_ids') or []))
    member_ids, _complete = membership
    ids = sorted(pid for pid in member_ids if pid in frozen)
    missing = sorted(pid for pid in member_ids if pid not in frozen)
    return ids, {}, frozen, 'membership_intersect_frozen_board_records', missing


def contract_a_state(clean, severe, total):
    """Contract A precedence (steps 2-4) on counts. The data gate is NOT applied."""
    if total <= 0:
        return None, None
    clean_share = Fraction(clean, total)
    severe_share = Fraction(severe, total)
    if clean <= _CLEAN_COUNT_VULNERABLE_MAX:
        status, rule = 'operationally_stressed', 'margin_floor'
    elif severe_share >= _SEVERE_SHARE_VULNERABLE_MIN:
        status, rule = 'operationally_stressed', 'severity_share'
    elif (clean_share >= _CLEAN_SHARE_FRESH_MIN and clean >= _CLEAN_COUNT_FRESH_MIN
          and severe <= _SEVERE_COUNT_FRESH_MAX):
        status, rule = 'operationally_stable', 'fresh_coverage'
    else:
        status, rule = 'operationally_constrained', 'residual_stretched'
    return INTERNAL_TO_PUBLIC_STATE[status], {'status_code': status, 'decisive_rule': rule}


def _board_on_watch_group(team_package, frozen, population_ids):
    """The Team Board's own On Watch group: the count its public sentence uses.

    "N relievers are in the On Watch group" counts the Monitor cards of the
    served Active Bullpen, which need not be the Team State population. Each
    card is attributed the same way, and cards outside the Team State
    population are counted.
    """
    if not team_package:
        return None
    arms = tonight_read_model._active_arms(team_package)
    on_watch = sorted(
        arm.get('pitcher_id') for arm in arms
        if _availability(frozen.get(arm.get('pitcher_id')) or {}).get(
            'availability_status') == 'Monitor'
    )
    bases = Counter(
        monitor_basis(_availability(frozen[pitcher_id])) for pitcher_id in on_watch
    )
    return {
        'count': len(on_watch),
        **{basis: bases[basis] for basis in MONITOR_BASES},
        'outside_team_state_population': sum(
            1 for pitcher_id in on_watch if pitcher_id not in population_ids),
        'pitcher_ids': on_watch,
    }


def certify_arm_attribution(snapshot, *, memberships, sidecars, ledger_complete):
    package = _package(snapshot)
    teams = {}
    for club in MLB_CLUBS:
        team_package = _team_package(package, club.team_id)
        ids, sidecar_records, frozen, source, unscored = _population(
            team_package, sidecars.get(club.team_id), memberships[club.team_id],
        )
        arms = [
            _arm_row(pid, frozen.get(pid), sidecar_records.get(pid), ledger_complete)
            for pid in ids
        ]
        buckets = Counter(arm['bucket'] for arm in arms)
        bases = Counter(arm['monitor_basis'] for arm in arms if arm['monitor_basis'])
        data_states = Counter(str(arm['data_state']) for arm in arms)
        counts = {
            'active_bullpen_count': len(arms),
            'clean': buckets['clean'],
            'monitor_total': buckets['monitor'],
            **{basis: bases[basis] for basis in MONITOR_BASES},
            'limited': buckets['limited'],
            'avoid': buckets['avoid'],
            'unavailable': buckets['unavailable'],
            'unknown': buckets['unknown'],
            'low_confidence': sum(1 for arm in arms if arm['confidence'] == 'low'),
            'stale_arms': data_states['stale'],
            'missing_arms': data_states['missing'],
            'ledger_confirmed_rest': sum(1 for arm in arms if arm['ledger_confirmed_rest']),
            'members_without_record': len(unscored),
            'sidecar_disagreements': sum(
                1 for arm in arms
                if arm['sidecar_data_state'] is not None
                and arm['sidecar_data_state'] != arm['data_state']
            ),
        }
        teams[club.team_id] = {
            'team': club.abbreviation,
            'population_source': source,
            'members_without_record': unscored,
            'board_on_watch_group': _board_on_watch_group(team_package, frozen, set(ids)),
            'counts': counts,
            'data_state_counts': dict(sorted(data_states.items())),
            'arms': arms,
        }
    return teams


# ── Team State ───────────────────────────────────────────────────────────────

COVERAGE_KEYS = (
    'confidence', 'data_state', 'coverage_reason_code', 'usable_record_count',
    'unresolved_record_count', 'coverage_pct', 'ledger_complete', 'cause_counts',
)


def certify_team_state(snapshot, *, attribution, sidecars, coverage=None):
    coverage = coverage or {}
    teams = {}
    for club in MLB_CLUBS:
        state = tonight_read_model._team_state(snapshot, club.team_id)
        present, value = tonight_read_model.receipt_value(snapshot, club.team_id)
        counts = attribution[club.team_id]['counts']
        total = counts['active_bullpen_count']
        clean = counts['clean']
        severe = counts['avoid'] + counts['unavailable']
        quality = sum(counts[basis] for basis in EVIDENCE_QUALITY_MONITOR_BASES)
        reproduced, reproduced_detail = contract_a_state(clean, severe, total)
        as_clean, _ = contract_a_state(clean + quality, severe, total)
        excluded, _ = contract_a_state(clean, severe, total - quality)
        published_state = state.get('public_state')
        sidecar = sidecars.get(club.team_id)
        sidecar_payload = _mapping(sidecar.payload) if sidecar is not None else {}
        sidecar_domain = _mapping(_mapping(sidecar_payload.get('domains')).get('team_state'))
        sidecar_value = _mapping(_mapping(sidecar_payload.get('values')).get('team_state'))
        verdict = PASS if (
            state.get('available') and published_state in CANONICAL_PUBLIC_STATES
        ) else CONDITIONAL if present else FAIL
        notes = []
        if published_state and reproduced and reproduced != published_state:
            notes.append('partition_does_not_reproduce_published_state')
        if sidecar_value and sidecar_value.get('public_state') not in (None, published_state):
            notes.append('sidecar_state_differs_from_receipt')
        if notes and verdict == PASS:
            verdict = CONDITIONAL
        team_coverage = _mapping(coverage.get(club.team_id))
        teams[club.team_id] = {
            'team': club.abbreviation,
            **state,
            'receipt_present': present,
            'receipt_reason_code': _mapping(value).get('reason_code'),
            'sidecar_bound': sidecar is not None,
            'sidecar_trust_state': sidecar_domain.get('trust_state'),
            'sidecar_trust_data_state': sidecar_domain.get('trust_data_state'),
            'sidecar_freshness_state': sidecar_domain.get('freshness_state'),
            'sidecar_public_state': sidecar_value.get('public_state'),
            'partition': {
                'active_pitcher_count': total, 'clean_count': clean,
                'moderate_count': counts['monitor_total'] + counts['limited'],
                'severe_count': severe, 'unknown_count': counts['unknown'],
            },
            'stale_arms': counts['stale_arms'],
            'missing_arms': counts['missing_arms'],
            'monitor_workload': counts[MONITOR_WORKLOAD],
            'monitor_from_evidence_quality': quality,
            'reproduced_public_state': reproduced,
            'reproduced': reproduced_detail,
            'reproduction_matches_published': (
                reproduced == published_state if published_state and reproduced else None),
            'coverage_at_audit_time': (
                {key: team_coverage.get(key) for key in COVERAGE_KEYS}
                if team_coverage else None
            ),
            'hypothetical': {
                'label': HYPOTHETICAL_LABEL,
                'evidence_quality_monitor_as_clean': as_clean,
                'evidence_quality_monitor_excluded': excluded,
                'would_differ': bool(quality) and published_state is not None and (
                    (as_clean is not None and as_clean != published_state)
                    or (excluded is not None and excluded != published_state)
                ),
            },
            'notes': notes,
            'verdict': verdict,
        }
    return teams


def coverage_at_audit_time(membership_date, availability_date):
    """The unchanged Team State coverage diagnostic, evaluated on current rows."""
    from services import active_bullpen_coverage_diagnostic as diagnostic

    ledger_complete = diagnostic._ledger_complete(availability_date)
    reports = {}
    for club in MLB_CLUBS:
        report = diagnostic.diagnose_active_bullpen_coverage(
            club.team_id, membership_date=membership_date,
            availability_date=availability_date, ledger_complete=ledger_complete,
        )
        report.pop('arms', None)
        reports[club.team_id] = report
    return ledger_complete, reports


# ── Postseason workload quantification ───────────────────────────────────────

def certify_postseason_workload(snapshot, *, attribution):
    """How much recent relief work comes from postseason games (never excluded)."""
    anchor = _date(snapshot.data_through)
    teams = {}
    for club in MLB_CLUBS:
        pitcher_ids = [arm['pitcher_id'] for arm in attribution[club.team_id]['arms']]
        windows = {}
        for key, days in POSTSEASON_WINDOWS.items():
            start = anchor - timedelta(days=days - 1)
            rows = (
                GameLog.query
                .filter(GameLog.pitcher_id.in_(pitcher_ids))
                .filter(GameLog.game_date >= start)
                .filter(GameLog.game_date <= anchor)
                .filter(GameLog.games_started == 0)
                .all()
            ) if pitcher_ids else []
            post = [row for row in rows if row.game_type in POSTSEASON_GAME_TYPES]
            regular = [row for row in rows if row.game_type == 'R']
            windows[key] = {
                'start_date': start.isoformat(),
                'through_date': anchor.isoformat(),
                'relief_appearances': len(rows),
                'postseason_relief_appearances': len(post),
                'postseason_relief_pitches': sum(row.pitches_thrown or 0 for row in post),
                'regular_season_relief_appearances': len(regular),
                'regular_season_relief_pitches': sum(
                    row.pitches_thrown or 0 for row in regular),
                'other_game_type_relief_appearances': len(rows) - len(post) - len(regular),
                'arms_with_postseason_relief': len({row.pitcher_id for row in post}),
                'postseason_game_types': sorted({row.game_type for row in post}),
            }
        teams[club.team_id] = {
            'team': club.abbreviation,
            'windows': windows,
            'postseason_workload_present': any(
                window['postseason_relief_appearances'] for window in windows.values()),
        }
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
        'slate_reason_codes': sorted(coverage.get('reason_codes') or []),
        'games_by_date': {
            day: sorted(pk for (d, pk) in by_game if d == day) for day in map(_iso, dates)
        },
        'retired_game_pks': retired,
        'games_with_disagreeing_rows': mixed,
        'verdict': (
            FAIL if mixed
            else PASS if coverage.get('complete_enough_to_publish') else CONDITIONAL
        ),
    }


def certify_tonight(snapshot):
    editions = (
        TonightPublication.query.filter_by(dashboard_snapshot_id=snapshot.id)
        .order_by(TonightPublication.reference_date, TonightPublication.id)
        .all()
    )
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
        served_states = {
            str(g.get('game_pk')): g.get('state') for g in served.get('games') or []}
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
                    issues.append({'game_pk': game.get('game_pk'),
                                   'issue': f'{side}_not_mlb_club'})
        results.append({
            'reference_date': _iso(edition.reference_date),
            'stored_game_count': (payload.get('summary') or {}).get('game_count'),
            'served_game_count': (served.get('summary') or {}).get('game_count'),
            'served_states': dict(sorted(served_states.items())),
            'issues': issues,
            'verdict': FAIL if issues else PASS,
        })
    return results


# ── Orchestration ────────────────────────────────────────────────────────────

NOT_COVERED = (
    'MLB live roster/transaction parity (the harness reads only the database)',
    'MLB live schedule parity',
    'What Changed event receipts',
    'Rotation impact, deployment and performance context',
    'Frontend rendering parity',
)


def _league_verdict(domain):
    verdicts = [result['verdict'] for result in domain.values()]
    if FAIL in verdicts:
        return FAIL
    if CONDITIONAL in verdicts:
        return CONDITIONAL
    return PASS


def _findings(roster, workload, attribution, team_state, postseason, schedule, tonight):
    findings = []
    for _team_id, result in sorted(roster.items()):
        for issue in result['issues']:
            findings.append({'domain': 'roster', 'team': result['team'], **issue})
    for _team_id, result in sorted(workload.items()):
        for mismatch in result['mismatches']:
            findings.append({'domain': 'workload', 'team': result['team'],
                             'issue': 'published_fact_contradicts_recount',
                             'pitcher_id': mismatch['pitcher_id'],
                             'facts': sorted(mismatch['diff'])})
    for _team_id, result in sorted(attribution.items()):
        counts = result['counts']
        board = result.get('board_on_watch_group') or {}
        if (counts[MONITOR_STALE] or counts[MONITOR_MISSING]
                or board.get(MONITOR_STALE) or board.get(MONITOR_MISSING)):
            findings.append({
                'domain': 'arm_attribution', 'team': result['team'],
                'issue': 'on_watch_from_stale_or_missing_evidence',
                'monitor_total': counts['monitor_total'],
                'monitor_stale': counts[MONITOR_STALE],
                'monitor_missing': counts[MONITOR_MISSING],
                'monitor_workload': counts[MONITOR_WORKLOAD],
                'board_on_watch': board.get('count'),
                'board_on_watch_stale': board.get(MONITOR_STALE),
                'board_on_watch_missing': board.get(MONITOR_MISSING),
            })
    for _team_id, result in sorted(team_state.items()):
        if result['hypothetical']['would_differ']:
            findings.append({
                'domain': 'team_state', 'team': result['team'],
                'issue': 'team_state_depends_on_evidence_quality_monitor',
                'published_state': result.get('public_state'),
                'hypothetical_label': HYPOTHETICAL_LABEL,
                'hypothetical_as_clean': result['hypothetical'][
                    'evidence_quality_monitor_as_clean'],
                'hypothetical_excluded': result['hypothetical'][
                    'evidence_quality_monitor_excluded'],
            })
        for note in result['notes']:
            findings.append({'domain': 'team_state', 'team': result['team'], 'issue': note})
    for _team_id, result in sorted(postseason.items()):
        if result['postseason_workload_present']:
            window = result['windows']['last_7_days']
            findings.append({
                'domain': 'postseason_workload', 'team': result['team'],
                'issue': 'postseason_relief_work_in_workload_windows',
                'postseason_relief_appearances_7d': window['postseason_relief_appearances'],
                'postseason_relief_pitches_7d': window['postseason_relief_pitches'],
            })
    if schedule['games_with_disagreeing_rows']:
        findings.append({'domain': 'schedule', 'issue': 'games_with_disagreeing_rows',
                         'game_pks': schedule['games_with_disagreeing_rows']})
    for edition in tonight:
        for issue in edition['issues']:
            findings.append({'domain': 'tonight',
                             'reference_date': edition['reference_date'], **issue})
    return findings


def certify_snapshot(snapshot, *, membership_date=None, include_audit_time_coverage=True):
    """The full read-only certification document for one snapshot."""
    default_membership, availability_date = reference_dates(snapshot)
    membership_date = membership_date or default_membership
    availability_date = availability_date or _date(snapshot.availability_reference_date)
    memberships = {}
    roster = certify_roster(snapshot, membership_date=membership_date, memberships=memberships)
    workload = certify_workload(snapshot)
    sidecars = team_state_sidecars(snapshot)
    if include_audit_time_coverage:
        ledger_complete, coverage = coverage_at_audit_time(membership_date, availability_date)
    else:
        from services import active_bullpen_coverage_diagnostic as diagnostic
        ledger_complete, coverage = diagnostic._ledger_complete(availability_date), {}
    attribution = certify_arm_attribution(
        snapshot, memberships=memberships, sidecars=sidecars,
        ledger_complete=ledger_complete,
    )
    team_state = certify_team_state(
        snapshot, attribution=attribution, sidecars=sidecars, coverage=coverage,
    )
    postseason = certify_postseason_workload(snapshot, attribution=attribution)
    team_verdicts = {}
    for club in MLB_CLUBS:
        verdicts = [d[club.team_id]['verdict'] for d in (roster, workload, team_state)]
        team_verdicts[club.abbreviation] = (
            FAIL if FAIL in verdicts else CONDITIONAL if CONDITIONAL in verdicts else PASS
        )
    schedule = certify_schedule(snapshot)
    tonight = certify_tonight(snapshot)
    domain_verdicts = {
        'roster': _league_verdict(roster),
        'workload': _league_verdict(workload),
        'team_state': _league_verdict(team_state),
        'schedule': schedule['verdict'],
        'tonight': (FAIL if any(t['verdict'] == FAIL for t in tonight)
                    else PASS if tonight else CONDITIONAL),
    }
    overall = (
        FAIL if FAIL in domain_verdicts.values()
        else CONDITIONAL if CONDITIONAL in domain_verdicts.values() else PASS
    )
    verdict_counts = Counter(team_verdicts.values())
    league_counts = Counter()
    for result in attribution.values():
        league_counts.update(result['counts'])
    count_keys = list(next(iter(attribution.values()))['counts']) if attribution else []
    return {
        'contract': CERTIFICATION_CONTRACT,
        'subject': {
            'snapshot_id': snapshot.id,
            'sync_run_id': getattr(snapshot, 'sync_run_id', None),
            'status': getattr(snapshot, 'status', None),
            'is_published': bool(getattr(snapshot, 'is_published', False)),
            'data_through': _iso(snapshot.data_through),
            'availability_reference_date': _iso(snapshot.availability_reference_date),
            'membership_date': _iso(membership_date),
            'availability_date_used': _iso(availability_date),
            'team_state_sidecars_bound': len(sidecars),
            'appearance_ledger_complete_at_audit_time': ledger_complete,
        },
        'league_verdict': overall,
        'teams_passed': verdict_counts.get(PASS, 0),
        'teams_conditional': verdict_counts.get(CONDITIONAL, 0),
        'teams_failed': verdict_counts.get(FAIL, 0),
        'domains': domain_verdicts,
        'team_verdicts': dict(sorted(team_verdicts.items())),
        'league_arm_attribution': {key: league_counts.get(key, 0) for key in count_keys},
        'roster': {str(k): v for k, v in sorted(roster.items())},
        'workload': {str(k): v for k, v in sorted(workload.items())},
        'arm_attribution': {str(k): v for k, v in sorted(attribution.items())},
        'team_state': {str(k): v for k, v in sorted(team_state.items())},
        'postseason_workload': {str(k): v for k, v in sorted(postseason.items())},
        'schedule': schedule,
        'tonight': tonight,
        'findings': _findings(
            roster, workload, attribution, team_state, postseason, schedule, tonight),
        'hypothetical_notice': HYPOTHETICAL_NOTICE,
        'not_covered': list(NOT_COVERED),
    }
