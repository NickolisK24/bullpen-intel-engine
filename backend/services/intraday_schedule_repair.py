"""Governed intraday repair for schedule and game-finality changes.

The intraday audit remains the detection authority. This module authorizes only
fully verified, actionable schedule findings and re-proves each candidate from
MLB schedule evidence before writing through the existing schedule ingester.
Review-required identity/finality conflicts block the entire write.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from services import intraday_reconcile, schedule_ingestion
from services.mlb_api import mlb_client

SOURCE = 'mlb_stats_api:intraday_schedule_repair'

REPAIRABLE_CHANGE_TYPES = frozenset({
    intraday_reconcile.GAME_POSTPONED,
    intraday_reconcile.GAME_RESCHEDULED,
    intraday_reconcile.GAME_IN_PROGRESS,
    intraday_reconcile.GAME_NOW_FINAL,
    intraday_reconcile.GAME_NEWLY_DISCOVERED,
    intraday_reconcile.GAME_SCHEDULE_STATUS_CHANGE,
})

BLOCKING_CHANGE_TYPES = frozenset({
    intraday_reconcile.GAME_STORED_FINALITY_CONFLICT,
    intraday_reconcile.GAME_ABSENT_FROM_SOURCE,
    intraday_reconcile.GAME_RESCHEDULE_IDENTITY_ISSUE,
    intraday_reconcile.GAME_SOURCE_CONFLICT,
})


class IntradayScheduleRepairError(RuntimeError):
    pass


def build_schedule_repair_scope(audit: dict) -> dict:
    lane = (audit.get('lanes') or {}).get(intraday_reconcile.LANE_SCHEDULE_FINALITY) or {}
    differences = list(lane.get('differences') or [])
    if audit.get('status') != intraday_reconcile.STATUS_SUCCESS:
        return _blocked_scope('audit_not_successful', differences)
    if lane.get('verification_status') != intraday_reconcile.LANE_COMPLETE:
        return _blocked_scope('schedule_lane_not_complete', differences)

    repairable = []
    unsupported = []
    for finding in differences:
        change_type = finding.get('change_type')
        if (
            finding.get('severity') == intraday_reconcile.SEVERITY_ACTIONABLE
            and change_type in REPAIRABLE_CHANGE_TYPES
            and _positive_int(finding.get('game_pk')) is not None
            and _finding_date(finding) is not None
        ):
            repairable.append(finding)
        elif change_type in BLOCKING_CHANGE_TYPES or finding.get('severity') is not None:
            unsupported.append(finding)

    game_pks = sorted({_positive_int(f.get('game_pk')) for f in repairable})
    slate_dates = sorted({_finding_date(f).isoformat() for f in repairable})
    affected_team_ids = sorted({
        team_id
        for finding in repairable
        for team_id in _finding_team_ids(finding)
    })
    return {
        'status': 'blocked' if unsupported else ('ready' if repairable else 'no_change'),
        'reason': 'unsupported_schedule_findings' if unsupported else None,
        'repairable_findings': repairable,
        'unsupported_findings': unsupported,
        'game_pks': game_pks,
        'slate_dates': slate_dates,
        'affected_team_ids': affected_team_ids,
        'completed_game_pks': sorted({
            _positive_int(f.get('game_pk'))
            for f in repairable
            if f.get('change_type') == intraday_reconcile.GAME_NOW_FINAL
        }),
    }


def apply_intraday_schedule_findings(findings, *, client=None, ingester=None):
    """Re-fetch and ingest only exact, conflict-free audited games.

    The write never trusts serialized source rows from the audit. It re-fetches
    each affected slate, resolves the exact gamePk, rejects changed/missing or
    contradictory identity evidence, and then delegates to Schedule Storage V1.
    """
    client = client or mlb_client
    ingester = ingester or schedule_ingestion.ingest_games
    grouped = defaultdict(list)
    for finding in findings or []:
        slate_date = _finding_date(finding)
        game_pk = _positive_int(finding.get('game_pk'))
        if slate_date is None or game_pk is None:
            raise IntradayScheduleRepairError('Schedule finding lacks date or gamePk authority.')
        grouped[slate_date].append(finding)

    selected = []
    for slate_date, slate_findings in sorted(grouped.items()):
        source_games = client.get_schedule(
            start_date=slate_date.isoformat(),
            end_date=slate_date.isoformat(),
        ) or []
        by_pk = defaultdict(list)
        for game in source_games:
            game_pk = _positive_int((game or {}).get('gamePk'))
            if game_pk is not None:
                by_pk[game_pk].append(game)

        for finding in slate_findings:
            game_pk = _positive_int(finding.get('game_pk'))
            candidates = by_pk.get(game_pk) or []
            if not candidates:
                raise IntradayScheduleRepairError(
                    f'Official schedule no longer contains audited game {game_pk} on {slate_date}.'
                )
            signatures = {_game_signature(game) for game in candidates}
            if len(signatures) != 1:
                raise IntradayScheduleRepairError(
                    f'Official schedule has conflicting rows for game {game_pk}.'
                )
            game = candidates[0]
            audited_teams = set(_finding_team_ids(finding))
            source_teams = set(_source_team_ids(game))
            if audited_teams and source_teams != audited_teams:
                raise IntradayScheduleRepairError(
                    f'Official team identity changed for game {game_pk}.'
                )
            selected.append(game)

    unique = {}
    for game in selected:
        unique[_positive_int(game.get('gamePk'))] = game
    summary = ingester(list(unique.values()), source=SOURCE, commit=False)
    if int((summary or {}).get('errors') or 0):
        raise IntradayScheduleRepairError('Schedule ingestion reported errors.')
    return {
        'source': SOURCE,
        'games_selected': len(unique),
        'game_pks': sorted(unique),
        'summary': summary,
    }


def _blocked_scope(reason, findings):
    return {
        'status': 'blocked',
        'reason': reason,
        'repairable_findings': [],
        'unsupported_findings': list(findings or []),
        'game_pks': [],
        'slate_dates': [],
        'affected_team_ids': [],
        'completed_game_pks': [],
    }


def _finding_date(finding):
    for key in ('game_date', 'official_date', 'source_game_date', 'observed_game_date', 'stored_game_date'):
        value = finding.get(key)
        if isinstance(value, date):
            return value
        if value:
            try:
                return date.fromisoformat(str(value)[:10])
            except ValueError:
                pass
    return None


def _finding_team_ids(finding):
    values = set()
    for key in ('home_team_id', 'away_team_id', 'stored_home_team_id', 'stored_away_team_id'):
        value = _positive_int(finding.get(key))
        if value is not None:
            values.add(value)
    for value in finding.get('affected_team_ids') or finding.get('team_ids') or []:
        parsed = _positive_int(value)
        if parsed is not None:
            values.add(parsed)
    return sorted(values)


def _source_team_ids(game):
    teams = (game or {}).get('teams') or {}
    values = []
    for side in ('home', 'away'):
        value = _positive_int((((teams.get(side) or {}).get('team') or {}).get('id')))
        if value is not None:
            values.append(value)
    return values


def _game_signature(game):
    status = (game or {}).get('status') or {}
    return (
        _positive_int((game or {}).get('gamePk')),
        str((game or {}).get('officialDate') or '')[:10],
        tuple(sorted(_source_team_ids(game))),
        str(status.get('statusCode') or ''),
        str(status.get('detailedState') or ''),
        str(status.get('abstractGameState') or ''),
        str((game or {}).get('doubleHeader') or ''),
        _positive_int((game or {}).get('gameNumber')),
    )


def _positive_int(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None
