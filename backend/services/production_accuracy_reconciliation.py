"""Read-only reconciliation of one exact trusted BaseballOS publication."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from fractions import Fraction
from typing import Any, Mapping

from models.dashboard_snapshot import DashboardSnapshot
from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.postgame_processed_game import PostgameProcessedGame
from models.pitcher import Pitcher
from models.scheduled_game import ScheduledGame
from models.sync_run import SyncRun
from services import public_serving_authority
from services.team_state_vnext_production_proof import load_durable_proof
from services.availability import (
    ACTIVE_WINDOW_DAYS, STATUS_AVAILABLE, STATUS_AVOID, STATUS_LIMITED,
    STATUS_MONITOR, STATUS_UNAVAILABLE, THRESHOLDS,
)
from services.workload_appearance import is_workload_appearance_log
from utils.db import db


VERIFIED = 'VERIFIED'
CONDITIONALLY_VERIFIED = 'CONDITIONALLY_VERIFIED'
NOT_VERIFIED = 'NOT_VERIFIED'
PASS = 'PASS'
FAIL = 'FAIL'
UNPROVEN = 'UNPROVEN'
HISTORICAL_METHOD_DIFFERENCE = 'HISTORICAL_METHOD_DIFFERENCE'
FROZEN_WORKLOAD_METHOD_VERSION = 'fatigue_score_workload_windows_v1'
FROZEN_WORKLOAD_REFERENCE_POLICY = (
    'canonical_latest_workload_at_score_calculation_plus_one_v1'
)
REQUIRED_INTERNAL_DOMAINS = (
    'publication_coherence',
    'games',
    'pitching_appearances',
    'bullpen_membership',
    'workload_values',
    'rest_patterns',
    'arm_reads',
    'team_states',
    'team_aggregates',
    'served_read_models',
)


def _domain(*, checked=0, correct=0, incorrect=0, unproven=0, status=None, detail=None):
    if status is None:
        status = FAIL if incorrect else (UNPROVEN if unproven else PASS)
    result = {
        'checked': int(checked),
        'correct': int(correct),
        'incorrect': int(incorrect),
        'unproven': int(unproven),
        'status': status,
    }
    if detail is not None:
        result['detail'] = detail
    return result


def _mismatch(domain, snapshot_id, published, recomputed, *, team=None,
              pitcher=None, game=None, rows=None, method_version=None,
              authoritative=None, likely_layer=None):
    return {
        'domain': domain,
        'team': team,
        'pitcher': pitcher,
        'game': game,
        'snapshot_id': snapshot_id,
        'published_value': published,
        'recomputed_value': recomputed,
        'authoritative_source_value': authoritative,
        'canonical_rows': list(rows or []),
        'method_version': method_version,
        'likely_originating_layer': likely_layer,
    }


def resolve_snapshot(*, snapshot_id=None, current=False):
    if bool(snapshot_id is not None) == bool(current):
        raise ValueError('select_exactly_one_of_snapshot_id_or_current')
    if current:
        return (
            DashboardSnapshot.query
            .filter_by(snapshot_type='bullpen_dashboard', status='ready', is_published=True)
            .order_by(DashboardSnapshot.published_at.desc(), DashboardSnapshot.id.desc())
            .first()
        )
    return DashboardSnapshot.query.filter_by(id=int(snapshot_id)).one_or_none()


def _trusted_snapshot(snapshot):
    return bool(
        snapshot is not None
        and snapshot.status == 'ready'
        and snapshot.published_at is not None
        and snapshot.sync_run_id is not None
        and isinstance(snapshot.payload, Mapping)
    )


def _package(snapshot):
    payload = snapshot.payload if isinstance(snapshot.payload, Mapping) else {}
    value = payload.get(public_serving_authority.TEAM_BOARD_PACKAGE_KEY)
    return value if isinstance(value, Mapping) else {}


def _team_packages(snapshot):
    by_team = _package(snapshot).get('by_team_id')
    return by_team if isinstance(by_team, Mapping) else {}


def _publication_coherence(snapshot, mismatches):
    checked = 7
    failures = []
    if not _trusted_snapshot(snapshot):
        failures.append('snapshot_not_trusted_publication')
    package = _package(snapshot) if snapshot is not None else {}
    if package.get('contract') != public_serving_authority.TEAM_BOARD_PACKAGE_CONTRACT:
        failures.append('team_board_package_contract_invalid')
    if package.get('data_through') != (snapshot.data_through.isoformat() if snapshot and snapshot.data_through else None):
        failures.append('team_board_data_through_mismatch')
    teams = _team_packages(snapshot) if snapshot is not None else {}
    if len(teams) != 30:
        failures.append('team_board_population_not_30')
    if snapshot is not None and snapshot.payload_version is None:
        failures.append('payload_version_missing')
    if snapshot is not None and snapshot.snapshot_generated_at is None:
        failures.append('generated_timestamp_missing')
    if snapshot is not None and snapshot.source is None:
        failures.append('publication_source_missing')
    for reason in failures:
        mismatches.append(_mismatch(
            f'publication_coherence.{reason}', getattr(snapshot, 'id', None),
            'coherent trusted publication', reason,
            likely_layer='publication',
        ))
    return _domain(checked=checked, correct=checked-len(failures), incorrect=len(failures), detail=failures)


def _game_ledger(snapshot, mismatches):
    final_rows = ScheduledGame.query.filter_by(
        game_date=snapshot.data_through,
        status_state=ScheduledGame.STATE_FINAL,
    ).all()
    sides_by_game = defaultdict(list)
    for row in final_rows:
        sides_by_game[row.game_pk].append(row)
    expected = sorted(sides_by_game)
    markers = {
        row.mlb_game_pk: row
        for row in PostgameProcessedGame.query.filter(
            PostgameProcessedGame.mlb_game_pk.in_(expected or [-1])
        ).all()
    }
    incorrect_games = 0
    for game_pk in expected:
        sides = sides_by_game[game_pk]
        marker = markers.get(game_pk)
        valid = (
            len(sides) == 2
            and len({row.team_id for row in sides}) == 2
            and marker is not None
            and marker.processing_status == PostgameProcessedGame.STATUS_FULLY_PROCESSED
        )
        if not valid:
            incorrect_games += 1
            mismatches.append(_mismatch(
                'games.canonical_final', snapshot.id, 'two final sides and complete marker',
                {'side_count': len(sides), 'marker_status': getattr(marker, 'processing_status', None)},
                game=game_pk,
                rows=[row.id for row in sides] + ([marker.id] if marker else []),
                likely_layer='schedule_or_postgame_ingestion',
            ))
    appearances = GameLog.query.filter(
        GameLog.mlb_game_pk.in_(expected or [-1])
    ).all()
    bad_appearances = 0
    for log in appearances:
        if log.appearance_team_status != GameLog.APPEARANCE_TEAM_RESOLVED or log.appearance_team_id is None:
            bad_appearances += 1
            mismatches.append(_mismatch(
                'pitching_appearances.appearance_team', snapshot.id, 'resolved game-side team',
                {'status': log.appearance_team_status, 'team_id': log.appearance_team_id},
                pitcher=log.pitcher_id, game=log.mlb_game_pk, rows=[log.id],
                likely_layer='appearance_team_resolution',
            ))
    return (
        _domain(checked=len(expected), correct=len(expected)-incorrect_games, incorrect=incorrect_games),
        _domain(checked=len(appearances), correct=len(appearances)-bad_appearances, incorrect=bad_appearances),
    )


def _record_logs(pitcher_ids, through):
    rows = (
        GameLog.query
        .filter(GameLog.pitcher_id.in_(pitcher_ids or [-1]))
        .filter(GameLog.game_date <= through)
        .order_by(GameLog.pitcher_id, GameLog.game_date, GameLog.mlb_game_pk)
        .all()
    )
    result = defaultdict(list)
    for row in rows:
        if row.game_date is not None and (
            row.pitches_thrown is not None or (row.innings_pitched_outs or 0) > 0
        ):
            result[row.pitcher_id].append(row)
    return result


def _sum_known_pitches(rows):
    return None if any(row.pitches_thrown is None for row in rows) else sum(row.pitches_thrown for row in rows)


def _recomputed_workload(rows, workload_through, rest_reference_date):
    latest = max((row.game_date for row in rows), default=None)
    rows_7 = [row for row in rows if workload_through - timedelta(days=6) <= row.game_date <= workload_through]
    rows_14 = [row for row in rows if workload_through - timedelta(days=13) <= row.game_date <= workload_through]
    latest_rows = [row for row in rows if row.game_date == latest]
    return {
        'last_workload_appearance': None if latest is None else {
            'game_date': latest.isoformat(),
            'pitches': _sum_known_pitches(latest_rows),
        },
        'days_since_last_appearance': None if latest is None else (rest_reference_date-latest).days,
        'appearances_last_7': len(rows_7),
        'appearances_last_14': len(rows_14),
        'pitches_last_7_days': _sum_known_pitches(rows_7),
        'innings_last_7_days': sum(row.innings_pitched_outs for row in rows_7) / 3.0,
    }


def _score_reference_date(score):
    """Recover the canonical workload anchor in force when a score was stored.

    Legacy ``FatigueScore`` rows did not persist their reference date. Their
    production authority was nevertheless deterministic: the greatest workload
    date present when the row was calculated, plus one day. Reconstructing that
    date prevents an immutable stale score from being judged against a later
    publication's availability date.
    """
    calculated_at = getattr(score, 'calculated_at', None)
    if calculated_at is None:
        return None
    latest_available = (
        db.session.query(db.func.max(GameLog.game_date))
        .filter(GameLog.created_at <= calculated_at)
        .scalar()
    )
    return latest_available + timedelta(days=1) if latest_available else None


def _rows_available_at_score_calculation(rows, score):
    calculated_at = getattr(score, 'calculated_at', None)
    if calculated_at is None:
        return []
    return [
        row for row in rows
        if getattr(row, 'created_at', None) is None
        or row.created_at <= calculated_at
    ]


def _recomputed_frozen_score_workload(rows, reference_date):
    """Independently reproduce the legacy FatigueScore workload carrier.

    ``calculate_fatigue`` historically named its inclusive ``ref - 7`` and
    ``ref - 14`` windows seven and fourteen days. The auditor reproduces that
    frozen method literally here instead of calling the production calculator.
    """
    workload_rows = [row for row in rows if is_workload_appearance_log(row)]
    latest = max((row.game_date for row in workload_rows), default=None)
    rows_7 = [
        row for row in workload_rows
        if reference_date - timedelta(days=7) <= row.game_date <= reference_date
    ]
    rows_14 = [
        row for row in workload_rows
        if reference_date - timedelta(days=14) <= row.game_date <= reference_date
    ]
    return {
        'days_since_last_appearance': (
            None if latest is None else (reference_date - latest).days
        ),
        'appearances_last_7': len(rows_7),
        'appearances_last_14': len(rows_14),
        'pitches_last_7_days': _sum_known_pitches(rows_7),
        'innings_last_7_days': (
            sum(row.innings_pitched_outs for row in rows_7) / 3.0
        ),
    }


def _availability_inputs(rows, reference_date, score):
    latest = max((row.game_date for row in rows), default=None)
    rows_5 = [row for row in rows if reference_date - timedelta(days=4) <= row.game_date <= reference_date]
    rows_4 = [row for row in rows if reference_date - timedelta(days=3) <= row.game_date <= reference_date]
    rows_3 = [row for row in rows if reference_date - timedelta(days=2) <= row.game_date <= reference_date]
    yesterday = [row for row in rows if row.game_date == reference_date - timedelta(days=1)]
    dates = {row.game_date for row in rows_5}
    if any(row.pitches_thrown is None for row in rows_5):
        freshness = 'incomplete'
    elif score is None or getattr(score, 'raw_score', None) is None or latest is None:
        freshness = 'missing'
    elif latest < reference_date - timedelta(days=ACTIVE_WINDOW_DAYS):
        freshness = 'stale'
    else:
        freshness = 'fresh'
    return {
        'fatigue_score': None if score is None else round(float(score.raw_score), 1),
        'pitches_yesterday': _sum_known_pitches(yesterday),
        'pitches_last_3_days': _sum_known_pitches(rows_3),
        'pitches_last_5_days': _sum_known_pitches(rows_5),
        'appearances_last_3_days': len(rows_3),
        'appearances_last_5_days': len(rows_5),
        'days_rest': None if latest is None else (reference_date-latest).days,
        'back_to_back': any(day-timedelta(days=1) in dates for day in dates),
        'three_in_four': len(rows_4) >= 3,
        'four_in_five': len(rows_5) >= 4,
        'freshness_state': freshness,
        'latest_game_date': latest.isoformat() if latest else None,
        'reference_date': reference_date.isoformat(),
    }


def _reproduce_arm_status(inputs):
    """Duplicate the governed decision table without calling its classifier."""
    state = inputs.get('freshness_state')
    if state in ('missing', 'stale'):
        return STATUS_MONITOR
    p1 = inputs.get('pitches_yesterday') or 0
    p3 = inputs.get('pitches_last_3_days') or 0
    p5 = inputs.get('pitches_last_5_days') or 0
    a3 = inputs.get('appearances_last_3_days') or 0
    a5 = inputs.get('appearances_last_5_days') or 0
    fatigue = inputs.get('fatigue_score')
    rest = inputs.get('days_rest')
    if (
        p1 >= THRESHOLDS.unavailable_pitches_yesterday
        or p3 >= THRESHOLDS.unavailable_pitches_last_3_days
        or (a5 >= 4 and p5 >= THRESHOLDS.unavailable_multi_day_pitch_threshold)
        or (fatigue is not None and fatigue >= THRESHOLDS.unavailable_fatigue_score
            and p1 >= THRESHOLDS.avoid_pitches_yesterday)
    ):
        status = STATUS_UNAVAILABLE
    elif (
        p1 >= THRESHOLDS.avoid_pitches_yesterday
        or p3 >= THRESHOLDS.avoid_pitches_last_3_days
        or a3 >= THRESHOLDS.avoid_appearances_last_3_days
        or a5 >= THRESHOLDS.avoid_appearances_last_5_days
        or (inputs.get('back_to_back') and p3 >= THRESHOLDS.limited_back_to_back_pitches_last_3_days)
        or (fatigue is not None and fatigue >= THRESHOLDS.avoid_fatigue_score)
    ):
        status = STATUS_AVOID
    elif (
        p1 >= THRESHOLDS.limited_pitches_yesterday
        or p3 >= THRESHOLDS.limited_pitches_last_3_days
        or p5 >= THRESHOLDS.limited_pitches_last_5_days
        or a3 >= THRESHOLDS.limited_appearances_last_3_days
        or a5 >= THRESHOLDS.limited_appearances_last_5_days
        or inputs.get('back_to_back')
        or (fatigue is not None and fatigue >= THRESHOLDS.limited_fatigue_score)
        or (rest is not None and rest <= 1 and fatigue is not None and fatigue >= 50)
    ):
        status = STATUS_LIMITED
    elif (
        p1 >= THRESHOLDS.monitor_pitches_yesterday
        or p3 >= THRESHOLDS.monitor_pitches_last_3_days
        or a5 >= THRESHOLDS.monitor_appearances_last_5_days
        or (rest is not None and rest <= 1)
        or (fatigue is not None and fatigue >= THRESHOLDS.monitor_fatigue_score)
    ):
        status = STATUS_MONITOR
    else:
        status = STATUS_AVAILABLE
    if state == 'incomplete' and status == STATUS_AVAILABLE:
        return STATUS_MONITOR
    return status


def _score_for_record(pitcher_id, record):
    facts = record.get('workload_facts') if isinstance(record.get('workload_facts'), Mapping) else {}
    stamp = facts.get('calculated_at')
    query = FatigueScore.query.filter_by(pitcher_id=pitcher_id)
    if stamp:
        try:
            parsed = datetime.fromisoformat(str(stamp).replace('Z', '+00:00')).replace(tzinfo=None)
            return query.filter(FatigueScore.calculated_at == parsed).one_or_none()
        except (TypeError, ValueError):
            return None
    return query.order_by(FatigueScore.calculated_at.desc(), FatigueScore.id.desc()).first()


def _current_pitchers(pitcher_ids):
    return {
        row.id: row
        for row in Pitcher.query.filter(Pitcher.id.in_(pitcher_ids or [-1])).all()
    }


def _membership_workload(snapshot, mismatches, governed_differences=None):
    governed_differences = (
        governed_differences if governed_differences is not None else []
    )
    teams = _team_packages(snapshot)
    membership_checked = membership_bad = 0
    records = []
    for raw_team_id, package in teams.items():
        try:
            team_id = int(raw_team_id)
        except (TypeError, ValueError):
            continue
        default_ids = package.get('default_pitcher_ids') if isinstance(package, Mapping) else None
        team_records = package.get('records') if isinstance(package, Mapping) else None
        default_ids = list(default_ids or [])
        team_records = [row for row in (team_records or []) if isinstance(row, Mapping)]
        membership_checked += len(default_ids)
        by_id = {row.get('pitcher_id'): row for row in team_records}
        for pitcher_id in default_ids:
            if pitcher_id not in by_id:
                membership_bad += 1
                mismatches.append(_mismatch(
                    'bullpen_membership.default_record_missing', snapshot.id, 'member record', None,
                    team=team_id, pitcher=pitcher_id, likely_layer='team_board_population',
                ))
            else:
                records.append((team_id, int(pitcher_id), by_id[pitcher_id]))
    logs = _record_logs([pitcher_id for _team, pitcher_id, _row in records], snapshot.availability_reference_date)
    current_pitchers = _current_pitchers([
        pitcher_id for _team, pitcher_id, _row in records
    ])
    workload_checked = workload_bad = rest_checked = rest_bad = arm_checked = arm_bad = 0
    for team_id, pitcher_id, record in records:
        pitcher = current_pitchers.get(pitcher_id)
        if pitcher is None or pitcher.team_id != team_id or pitcher.active is not True:
            membership_bad += 1
            mismatches.append(_mismatch(
                'bullpen_membership.current_roster_authority', snapshot.id,
                {'team_id': team_id, 'active': True},
                None if pitcher is None else {
                    'team_id': pitcher.team_id, 'active': pitcher.active,
                },
                team=team_id, pitcher=pitcher_id,
                likely_layer='current_roster_population',
            ))
        recomputed = _recomputed_workload(
            logs[pitcher_id], snapshot.data_through,
            snapshot.availability_reference_date,
        )
        published_last = record.get('last_workload_appearance')
        workload_checked += 1
        if published_last != recomputed['last_workload_appearance']:
            workload_bad += 1
            mismatches.append(_mismatch(
                'workload.last_workload_appearance', snapshot.id, published_last,
                recomputed['last_workload_appearance'], team=team_id, pitcher=pitcher_id,
                rows=[row.id for row in logs[pitcher_id]], likely_layer='workload_derivation',
            ))
        facts = record.get('workload_facts') if isinstance(record.get('workload_facts'), Mapping) else {}
        availability = record.get('availability') if isinstance(record.get('availability'), Mapping) else {}
        published_inputs = availability.get('inputs') if isinstance(availability.get('inputs'), Mapping) else {}
        score = _score_for_record(pitcher_id, record)
        frozen_reference_date = _score_reference_date(score) if score is not None else None
        frozen_recomputed = None
        if (
            frozen_reference_date is not None
            and published_inputs.get('freshness_state') == 'stale'
            and frozen_reference_date != snapshot.availability_reference_date
        ):
            frozen_recomputed = _recomputed_frozen_score_workload(
                _rows_available_at_score_calculation(logs[pitcher_id], score),
                frozen_reference_date,
            )
        for key in ('appearances_last_7', 'appearances_last_14', 'pitches_last_7_days', 'innings_last_7_days'):
            workload_checked += 1
            left = facts.get(key)
            right = (
                frozen_recomputed[key]
                if frozen_recomputed is not None
                else recomputed[key]
            )
            if isinstance(left, float) and isinstance(right, float):
                equal = abs(left-right) < 1e-6
            else:
                equal = left == right
            if not equal:
                workload_bad += 1
                mismatches.append(_mismatch(
                    f'workload.{key}', snapshot.id, left, right, team=team_id,
                    pitcher=pitcher_id, rows=[row.id for row in logs[pitcher_id]],
                    likely_layer='workload_derivation',
                ))
        rest_checked += 1
        recomputed_rest = (
            frozen_recomputed['days_since_last_appearance']
            if frozen_recomputed is not None
            else recomputed['days_since_last_appearance']
        )
        if facts.get('days_since_last_appearance') != recomputed_rest:
            rest_bad += 1
            mismatches.append(_mismatch(
                'rest.days_since_last_appearance', snapshot.id,
                facts.get('days_since_last_appearance'), recomputed_rest,
                team=team_id, pitcher=pitcher_id,
                rows=[row.id for row in logs[pitcher_id]], likely_layer='rest_derivation',
            ))
        if frozen_recomputed is not None and (
            facts.get('appearances_last_14') != recomputed['appearances_last_14']
            or facts.get('days_since_last_appearance')
            != recomputed['days_since_last_appearance']
        ):
            governed_differences.append({
                'classification': HISTORICAL_METHOD_DIFFERENCE,
                'domain': 'workload.frozen_score_reference',
                'team': team_id,
                'pitcher': pitcher_id,
                'snapshot_id': snapshot.id,
                'source_score_id': getattr(score, 'id', None),
                'score_calculated_at': (
                    score.calculated_at.isoformat()
                    if getattr(score, 'calculated_at', None) else None
                ),
                'frozen_reference_date': frozen_reference_date.isoformat(),
                'publication_availability_reference_date': (
                    snapshot.availability_reference_date.isoformat()
                ),
                'published_value': {
                    'appearances_last_14': facts.get('appearances_last_14'),
                    'days_since_last_appearance': facts.get(
                        'days_since_last_appearance'
                    ),
                },
                'recomputed_frozen_value': {
                    'appearances_last_14': frozen_recomputed[
                        'appearances_last_14'
                    ],
                    'days_since_last_appearance': frozen_recomputed[
                        'days_since_last_appearance'
                    ],
                },
                'current_publication_value': {
                    'appearances_last_14': recomputed['appearances_last_14'],
                    'days_since_last_appearance': recomputed[
                        'days_since_last_appearance'
                    ],
                },
                'canonical_rows': [row.id for row in logs[pitcher_id]],
                'method_version': FROZEN_WORKLOAD_METHOD_VERSION,
                'reference_date_policy': FROZEN_WORKLOAD_REFERENCE_POLICY,
                'reason': (
                    'The immutable stale FatigueScore carrier is reproduced at '
                    'its calculation-time anchor; current availability evidence '
                    'is checked separately at the publication reference date.'
                ),
            })
        audit_inputs = _availability_inputs(
            logs[pitcher_id], snapshot.availability_reference_date, score,
        )
        for key in (
            'pitches_yesterday', 'pitches_last_3_days', 'pitches_last_5_days',
            'appearances_last_3_days', 'appearances_last_5_days', 'days_rest',
            'back_to_back', 'three_in_four', 'four_in_five', 'freshness_state',
            'latest_game_date', 'reference_date',
        ):
            if key in published_inputs:
                workload_checked += 1
                if published_inputs.get(key) != audit_inputs.get(key):
                    workload_bad += 1
                    mismatches.append(_mismatch(
                        f'workload.availability_input.{key}', snapshot.id,
                        published_inputs.get(key), audit_inputs.get(key),
                        team=team_id, pitcher=pitcher_id,
                        rows=[row.id for row in logs[pitcher_id]],
                        likely_layer='availability_input_derivation',
                    ))
        arm_checked += 1
        published_status = availability.get('availability_status')
        recomputed_status = _reproduce_arm_status(audit_inputs) if score is not None else None
        if published_status is None or recomputed_status != published_status:
            arm_bad += 1
            mismatches.append(_mismatch(
                'arm_reads.classification', snapshot.id, published_status,
                recomputed_status, team=team_id, pitcher=pitcher_id,
                rows=[row.id for row in logs[pitcher_id]] + ([score.id] if score else []),
                method_version='availability_engine_v1',
                likely_layer='availability_classification_or_score_provenance',
            ))
    return {
        'bullpen_membership': _domain(checked=membership_checked, correct=membership_checked-membership_bad, incorrect=membership_bad),
        'workload_values': _domain(checked=workload_checked, correct=workload_checked-workload_bad, incorrect=workload_bad),
        'rest_patterns': _domain(checked=rest_checked, correct=rest_checked-rest_bad, incorrect=rest_bad),
        'arm_reads': _domain(checked=arm_checked, correct=arm_checked-arm_bad, incorrect=arm_bad),
    }


def _reproduce_team_state(team):
    total = team.get('active_pitcher_count')
    partition = team.get('partition') if isinstance(team.get('partition'), Mapping) else {}
    clean, severe = partition.get('clean_count'), partition.get('severe_count')
    thresholds = team.get('thresholds_applied') if isinstance(team.get('thresholds_applied'), Mapping) else {}
    try:
        if clean <= int(thresholds['clean_count_vulnerable_max']):
            status, rule = 'operationally_stressed', 'margin_floor'
        elif Fraction(severe, total) >= Fraction(*thresholds['severe_share_vulnerable_min']):
            status, rule = 'operationally_stressed', 'severity_share'
        elif (
            Fraction(clean, total) >= Fraction(*thresholds['clean_share_fresh_min'])
            and clean >= int(thresholds['clean_count_fresh_min'])
            and severe <= int(thresholds['severe_count_fresh_max'])
        ):
            status, rule = 'operationally_stable', 'fresh_coverage'
        else:
            status, rule = 'operationally_constrained', 'residual_stretched'
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return None, None
    return status, rule


def _team_states(snapshot, mismatches):
    row = load_durable_proof(snapshot.id)
    if row is None:
        mismatches.append(_mismatch(
            'team_states.required_proof_missing', snapshot.id, 'durable proof', None,
            likely_layer='post_publication_proof',
        ))
        return _domain(checked=30, correct=0, incorrect=30, detail='durable proof missing')
    proof = row.proof if isinstance(row.proof, Mapping) else {}
    teams = proof.get('teams') if isinstance(proof.get('teams'), list) else []
    seen, bad = set(), 0
    publication = proof.get('publication') if isinstance(proof.get('publication'), Mapping) else {}
    identity_valid = (
        getattr(row, 'snapshot_id', snapshot.id) == snapshot.id
        and getattr(row, 'data_through', snapshot.data_through) == snapshot.data_through
        and publication.get('dashboard_snapshot_id') == snapshot.id
        and publication.get('sync_run_id') == snapshot.sync_run_id
        and publication.get('data_through') == snapshot.data_through.isoformat()
        and proof.get('proof_generated_at') not in (None, '')
    )
    if not identity_valid:
        bad += 1
        mismatches.append(_mismatch(
            'team_states.proof_publication_identity', snapshot.id,
            {
                'snapshot_id': snapshot.id,
                'sync_run_id': snapshot.sync_run_id,
                'data_through': snapshot.data_through.isoformat(),
            },
            publication,
            likely_layer='durable_proof_storage_or_retrieval',
        ))
    public_by_internal = {
        'operationally_stable': 'fresh',
        'operationally_constrained': 'stretched',
        'operationally_stressed': 'vulnerable',
    }
    for team in teams:
        team_id = team.get('team_id')
        seen.add(team_id)
        partition = team.get('partition') if isinstance(team.get('partition'), Mapping) else {}
        total = team.get('active_pitcher_count')
        values = [partition.get(key) for key in ('clean_count', 'moderate_count', 'severe_count', 'unknown_count')]
        final = team.get('final_team_state') if isinstance(team.get('final_team_state'), Mapping) else {}
        withheld = (
            total is None
            and all(value is None for value in values)
            and final.get('readiness_status_code') is None
            and final.get('published_public_state') is None
            and team.get('partition_invariant_state') == 'not_applicable'
        )
        if withheld:
            partition_sum, status, rule, valid = None, None, None, True
        else:
            partition_sum = sum(values) if all(type(value) is int for value in values) else None
            status, rule = _reproduce_team_state(team)
            valid = (
                partition_sum == total
                and status == final.get('readiness_status_code')
                and rule == team.get('decisive_rule')
                and public_by_internal.get(status) == final.get('published_public_state')
                and team.get('source_snapshot_id') in (None, snapshot.id)
            )
        if not valid:
            bad += 1
            mismatches.append(_mismatch(
                'team_states.contract_a', snapshot.id,
                {'status': final.get('readiness_status_code'), 'rule': team.get('decisive_rule'), 'partition_sum': partition_sum},
                {'status': status, 'rule': rule, 'active_pitcher_count': total},
                team=team_id, method_version=team.get('method_version'),
                likely_layer='team_state_classification_or_proof',
            ))
    duplicate_or_missing = len(teams) != 30 or len(seen) != 30
    if duplicate_or_missing:
        bad += max(1, 30-len(seen))
        mismatches.append(_mismatch(
            'team_states.team_set', snapshot.id, '30 unique teams',
            {'rows': len(teams), 'unique': len(seen)}, likely_layer='team_state_generation',
        ))
    return _domain(checked=30, correct=max(0, 30-bad), incorrect=bad)


def _team_aggregates(snapshot, mismatches):
    checked = bad = 0
    for raw_team_id, package in _team_packages(snapshot).items():
        try:
            team_id = int(raw_team_id)
        except (TypeError, ValueError):
            continue
        default_ids = list(package.get('default_pitcher_ids') or [])
        records = [row for row in (package.get('records') or []) if isinstance(row, Mapping)]
        rest = package.get('rest_status') if isinstance(package.get('rest_status'), Mapping) else {}
        if rest:
            if rest.get('available') is True:
                active_records = [
                    row for row in records if row.get('pitcher_id') in default_ids
                ]
                facts = [row.get('workload_facts') or {} for row in active_records]
                expected = {
                    'active_arm_count': len(default_ids),
                    'rested_arm_count': sum(
                        type(row.get('days_since_last_appearance')) is int
                        and row['days_since_last_appearance'] >= 2 for row in facts
                    ),
                    'worked_yesterday_count': sum(
                        row.get('days_since_last_appearance') == 1 for row in facts
                    ),
                    'back_to_back_count': sum(
                        ((row.get('availability') or {}).get('inputs') or {}).get(
                            'back_to_back'
                        ) is True
                        for row in active_records
                    ),
                }
                for key, value in expected.items():
                    checked += 1
                    if rest.get(key) != value:
                        bad += 1
                        mismatches.append(_mismatch(
                            f'team_aggregates.{key}', snapshot.id,
                            rest.get(key), value, team=team_id,
                            likely_layer='team_board_rest_aggregate',
                        ))
            else:
                checked += 4
                for key in ('active_arm_count', 'rested_arm_count', 'worked_yesterday_count', 'back_to_back_count'):
                    if rest.get(key) is not None:
                        bad += 1
                        mismatches.append(_mismatch(
                            f'team_aggregates.withheld_{key}', snapshot.id,
                            rest.get(key), None, team=team_id,
                            likely_layer='team_board_rest_withholding',
                        ))

        windows = package.get('workload_windows') if isinstance(package.get('workload_windows'), Mapping) else {}
        if windows.get('status') == 'complete':
            rows = (
                GameLog.query
                .filter(
                    GameLog.appearance_team_status == GameLog.APPEARANCE_TEAM_RESOLVED,
                    GameLog.appearance_team_id == team_id,
                    GameLog.game_date >= snapshot.data_through-timedelta(days=29),
                    GameLog.game_date <= snapshot.data_through,
                    GameLog.games_started == 0,
                )
                .all()
            )
            by_window = windows.get('windows') if isinstance(windows.get('windows'), Mapping) else {}
            for days in (7, 14):
                published = by_window.get(f'window_{days}') if isinstance(by_window.get(f'window_{days}'), Mapping) else {}
                selected = [row for row in rows if row.game_date >= snapshot.data_through-timedelta(days=days-1)]
                known = [row.pitches_thrown for row in selected if row.pitches_thrown is not None]
                expected = {
                    'relief_appearances': len(selected),
                    'pitchers_in_relief': len({row.pitcher_id for row in selected}),
                    'pitches_total': 0 if not selected else (
                        sum(known) if len(known) == len(selected) else None
                    ),
                    'appearances_with_pitches': len(known),
                }
                for key, value in expected.items():
                    checked += 1
                    if published.get(key) != value:
                        bad += 1
                        mismatches.append(_mismatch(
                            f'team_aggregates.workload_{days}d.{key}', snapshot.id,
                            published.get(key), value, team=team_id,
                            rows=[row.id for row in selected],
                            likely_layer='historical_appearance_team_aggregate',
                        ))
    return _domain(checked=checked, correct=checked-bad, incorrect=bad)


def _landscape_team_states(payload):
    found = {}

    def visit(value):
        if isinstance(value, Mapping):
            state = value.get('team_state')
            team_id = value.get('team_id')
            if team_id is None and isinstance(value.get('team'), Mapping):
                team_id = value['team'].get('team_id')
            if team_id is not None and isinstance(state, Mapping):
                found[int(team_id)] = state
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(payload.get('landscape') if isinstance(payload, Mapping) else None)
    return found


def _served_models(snapshot, mismatches):
    package = _package(snapshot)
    checked = 3
    failures = []
    if package.get('data_through') != snapshot.data_through.isoformat():
        failures.append('data_through')
    authority = snapshot.payload.get('publication_authority') if isinstance(snapshot.payload, Mapping) else None
    if isinstance(authority, Mapping) and authority.get('snapshot_id') not in (None, snapshot.id):
        failures.append('publication_authority_snapshot_id')
    if package.get('contract') != public_serving_authority.TEAM_BOARD_PACKAGE_CONTRACT:
        failures.append('package_contract')
    proof_row = load_durable_proof(snapshot.id)
    proof = proof_row.proof if proof_row is not None and isinstance(proof_row.proof, Mapping) else {}
    proof_states = {
        int(team['team_id']): (team.get('final_team_state') or {}).get('published_public_state')
        for team in proof.get('teams') or []
        if isinstance(team, Mapping) and team.get('team_id') is not None
    }
    landscape_states = _landscape_team_states(snapshot.payload)
    for team_id, published_state in (landscape_states.items() if proof_states else ()):
        checked += 1
        served_state = published_state.get('public_state')
        if proof_states.get(team_id) != served_state:
            failures.append(f'team_state_semantic_mismatch:{team_id}')
            mismatches.append(_mismatch(
                'served_read_models.dashboard_team_state', snapshot.id,
                served_state, proof_states.get(team_id), team=team_id,
                likely_layer='dashboard_team_state_projection',
            ))
    for failure in failures:
        if failure.startswith('team_state_semantic_mismatch:'):
            continue
        mismatches.append(_mismatch(
            f'served_read_models.{failure}', snapshot.id, snapshot.id, failure,
            likely_layer='served_snapshot_projection',
        ))
    return _domain(checked=checked, correct=checked-len(failures), incorrect=len(failures))


def _external_unproven(reason='MLB external validation not requested or unavailable'):
    return {
        'games': _domain(unproven=1, status=UNPROVEN, detail=reason),
        'pitching_lines': _domain(unproven=1, status=UNPROVEN, detail=reason),
        'roster_authority': _domain(unproven=1, status=UNPROVEN, detail=reason),
    }


def reconcile_external_mlb(snapshot, *, client=None):
    """Compare the latest completed slate to official MLB schedule/boxscore rows."""
    try:
        if client is None:
            from services.mlb_api import MLBApiClient
            client = MLBApiClient()
        from services.game_finality import has_safe_final_status
        from utils.innings import parse_mlb_innings_to_outs

        slate = snapshot.data_through.isoformat()
        official_games = client.get_schedule(start_date=slate, end_date=slate) or []
        official_finals = {
            int(game['gamePk']): game
            for game in official_games
            if game.get('gamePk') is not None and has_safe_final_status(game)
        }
    except Exception as exc:
        return _external_unproven(f'MLB schedule unavailable: {type(exc).__name__}')

    stored_game_pks = {
        row.game_pk
        for row in ScheduledGame.query.filter_by(
            game_date=snapshot.data_through,
            status_state=ScheduledGame.STATE_FINAL,
        ).all()
    }
    game_incorrect = len(set(official_finals) ^ stored_game_pks)
    games = _domain(
        checked=len(official_finals),
        correct=max(0, len(official_finals)-game_incorrect),
        incorrect=game_incorrect,
        detail={
            'official_game_pks': sorted(official_finals),
            'stored_game_pks': sorted(stored_game_pks),
        },
    )

    stored_logs = GameLog.query.filter(
        GameLog.mlb_game_pk.in_(list(official_finals) or [-1])
    ).all()
    pitcher_ids = {row.pitcher_id for row in stored_logs}
    mlb_by_internal = {
        row.id: row.mlb_id
        for row in Pitcher.query.filter(Pitcher.id.in_(pitcher_ids or [-1])).all()
    }
    stored_by_key = {
        (row.mlb_game_pk, mlb_by_internal.get(row.pitcher_id)): row
        for row in stored_logs
        if mlb_by_internal.get(row.pitcher_id) is not None
    }
    line_checked = line_correct = line_incorrect = line_unproven = 0
    for game_pk in sorted(official_finals):
        try:
            official_lines = client.get_game_pitching_lines(game_pk) or []
        except Exception:
            line_unproven += 1
            continue
        for line in official_lines:
            line_checked += 1
            stats = line.get('stats') if isinstance(line.get('stats'), Mapping) else {}
            stored = stored_by_key.get((game_pk, line.get('player_id')))
            try:
                official = {
                    'team_id': int(line.get('team_id')),
                    'pitches': int(stats['numberOfPitches']),
                    'outs': parse_mlb_innings_to_outs(stats['inningsPitched']),
                    'games_started': int(stats.get('gamesStarted') or 0),
                }
            except (KeyError, TypeError, ValueError):
                line_unproven += 1
                continue
            actual = None if stored is None else {
                'team_id': stored.appearance_team_id,
                'pitches': stored.pitches_thrown,
                'outs': stored.innings_pitched_outs,
                'games_started': stored.games_started,
            }
            if actual == official:
                line_correct += 1
            else:
                line_incorrect += 1
    pitching_lines = _domain(
        checked=line_checked,
        correct=line_correct,
        incorrect=line_incorrect,
        unproven=line_unproven,
    )
    return {
        'games': games,
        'pitching_lines': pitching_lines,
        'roster_authority': _domain(
            unproven=30,
            status=UNPROVEN,
            detail='Official roster comparison is not available from this bounded run.',
        ),
    }


def reconcile_publication(snapshot, *, external_domains=None, external_required=False):
    """Reconcile a previously resolved snapshot without selecting another one."""
    mismatches = []
    if snapshot is None:
        return {
            'snapshot_id': None,
            'verdict': NOT_VERIFIED,
            'domains': {'publication_coherence': _domain(checked=1, incorrect=1)},
            'external_mlb': _external_unproven('publication not found'),
            'mismatches': [_mismatch('publication.not_found', None, 'snapshot', None)],
            'governed_differences': [],
        }
    governed_differences = []
    domains = {'publication_coherence': _publication_coherence(snapshot, mismatches)}
    games, appearances = _game_ledger(snapshot, mismatches)
    domains['games'] = games
    domains['pitching_appearances'] = appearances
    domains.update(_membership_workload(
        snapshot, mismatches, governed_differences,
    ))
    domains['team_states'] = _team_states(snapshot, mismatches)
    domains['team_aggregates'] = _team_aggregates(snapshot, mismatches)
    domains['served_read_models'] = _served_models(snapshot, mismatches)
    external = external_domains or _external_unproven()

    internal_failed = any(domains[name]['status'] != PASS for name in REQUIRED_INTERNAL_DOMAINS)
    external_failed = any(item['status'] == FAIL for item in external.values())
    external_unproven = any(item['status'] == UNPROVEN for item in external.values())
    if internal_failed or external_failed or (external_required and external_unproven):
        verdict = NOT_VERIFIED
    elif external_unproven:
        verdict = CONDITIONALLY_VERIFIED
    else:
        verdict = VERIFIED
    return {
        'snapshot_id': snapshot.id,
        'sync_run_id': snapshot.sync_run_id,
        'data_through': snapshot.data_through.isoformat() if snapshot.data_through else None,
        'generated_at': snapshot.snapshot_generated_at.isoformat() if snapshot.snapshot_generated_at else None,
        'published_at': snapshot.published_at.isoformat() if snapshot.published_at else None,
        'publication_source': snapshot.source,
        'payload_version': snapshot.payload_version,
        'is_current': bool(snapshot.is_published),
        'verdict': verdict,
        'domains': domains,
        'external_mlb': external,
        'mismatches': mismatches,
        'governed_differences': governed_differences,
    }
