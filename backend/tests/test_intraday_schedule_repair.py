from services import intraday_reconcile
from services.intraday_schedule_repair import (
    IntradayScheduleRepairError,
    apply_intraday_schedule_findings,
    build_schedule_repair_scope,
)


PHI = 143
NYM = 121
SLATE_DATE = '2026-07-23'


def _audit(*differences, status='success', verification='complete'):
    return {
        'status': status,
        'lanes': {
            intraday_reconcile.LANE_SCHEDULE_FINALITY: {
                'verification_status': verification,
                'differences': list(differences),
            }
        },
    }


def _finding(change_type, *, game_pk=800001, severity='actionable'):
    return {
        'change_type': change_type,
        'game_pk': game_pk,
        'game_date': SLATE_DATE,
        'home_team_id': PHI,
        'away_team_id': NYM,
        'severity': severity,
    }


def _game(game_pk=800001, *, status_code='F', detailed='Final', abstract='Final'):
    return {
        'gamePk': game_pk,
        'officialDate': SLATE_DATE,
        'status': {
            'statusCode': status_code,
            'detailedState': detailed,
            'abstractGameState': abstract,
        },
        'teams': {
            'home': {'team': {'id': PHI}},
            'away': {'team': {'id': NYM}},
        },
        'doubleHeader': 'N',
    }


class _Client:
    def __init__(self, games):
        self.games = games
        self.calls = []

    def get_schedule(self, start_date=None, end_date=None):
        self.calls.append((start_date, end_date))
        return list(self.games)


def test_no_change_is_safe_noop():
    scope = build_schedule_repair_scope(_audit())
    assert scope['status'] == 'no_change'
    assert scope['game_pks'] == []


def test_newly_final_game_is_repairable():
    scope = build_schedule_repair_scope(_audit(
        _finding(intraday_reconcile.GAME_NOW_FINAL)
    ))
    assert scope['status'] == 'ready'
    assert scope['game_pks'] == [800001]
    assert scope['completed_game_pks'] == [800001]
    assert scope['affected_team_ids'] == [NYM, PHI]
    assert scope['slate_dates'] == [SLATE_DATE]


def test_postponement_is_repairable_without_completed_game_plan():
    scope = build_schedule_repair_scope(_audit(
        _finding(intraday_reconcile.GAME_POSTPONED)
    ))
    assert scope['status'] == 'ready'
    assert scope['completed_game_pks'] == []


def test_source_conflict_blocks_entire_write():
    repairable = _finding(intraday_reconcile.GAME_NOW_FINAL)
    conflict = _finding(
        intraday_reconcile.GAME_SOURCE_CONFLICT,
        game_pk=800002,
        severity='review_required',
    )
    scope = build_schedule_repair_scope(_audit(repairable, conflict))
    assert scope['status'] == 'blocked'
    assert scope['reason'] == 'unsupported_schedule_findings'
    assert scope['repairable_findings'] == [repairable]
    assert scope['unsupported_findings'] == [conflict]


def test_partial_lane_blocks_all_writes():
    scope = build_schedule_repair_scope(_audit(
        _finding(intraday_reconcile.GAME_NOW_FINAL),
        verification='partial',
    ))
    assert scope['status'] == 'blocked'
    assert scope['reason'] == 'schedule_lane_not_complete'
    assert scope['repairable_findings'] == []


def test_apply_reproves_exact_game_and_uses_existing_ingester():
    client = _Client([_game()])
    captured = {}

    def ingester(games, *, source, commit):
        captured['games'] = games
        captured['source'] = source
        captured['commit'] = commit
        return {'games_ingested': 1, 'errors': 0}

    result = apply_intraday_schedule_findings(
        [_finding(intraday_reconcile.GAME_NOW_FINAL)],
        client=client,
        ingester=ingester,
    )

    assert client.calls == [(SLATE_DATE, SLATE_DATE)]
    assert result['game_pks'] == [800001]
    assert captured['games'] == [_game()]
    assert captured['commit'] is False
    assert captured['source'] == 'mlb_stats_api:intraday_schedule_repair'


def test_apply_fails_closed_when_audited_game_disappears():
    client = _Client([])
    try:
        apply_intraday_schedule_findings(
            [_finding(intraday_reconcile.GAME_NOW_FINAL)],
            client=client,
            ingester=lambda *_args, **_kwargs: {'errors': 0},
        )
    except IntradayScheduleRepairError as exc:
        assert 'no longer contains audited game' in str(exc)
    else:
        raise AssertionError('Expected missing official game to fail closed.')


def test_apply_fails_closed_on_conflicting_duplicate_source_rows():
    client = _Client([
        _game(status_code='F', detailed='Final', abstract='Final'),
        _game(status_code='I', detailed='In Progress', abstract='Live'),
    ])
    try:
        apply_intraday_schedule_findings(
            [_finding(intraday_reconcile.GAME_NOW_FINAL)],
            client=client,
            ingester=lambda *_args, **_kwargs: {'errors': 0},
        )
    except IntradayScheduleRepairError as exc:
        assert 'conflicting rows' in str(exc)
    else:
        raise AssertionError('Expected source conflict to fail closed.')


def test_apply_fails_closed_when_team_identity_changes():
    changed = _game()
    changed['teams']['away']['team']['id'] = 110
    client = _Client([changed])
    try:
        apply_intraday_schedule_findings(
            [_finding(intraday_reconcile.GAME_NOW_FINAL)],
            client=client,
            ingester=lambda *_args, **_kwargs: {'errors': 0},
        )
    except IntradayScheduleRepairError as exc:
        assert 'team identity changed' in str(exc)
    else:
        raise AssertionError('Expected changed game identity to fail closed.')
