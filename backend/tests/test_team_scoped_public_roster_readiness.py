from services import public_roster_readiness as readiness_service


SNAPSHOT_DAY = '2026-07-24'


def _family(*, status='degraded', reasons=(), missing=(), fail_closed=None):
    if fail_closed is None:
        fail_closed = status != 'ready'
    return {
        'status': status,
        'fail_closed': fail_closed,
        'reason_codes': list(reasons),
        'last_successful_at': SNAPSHOT_DAY,
        'last_attempted_at': SNAPSHOT_DAY,
        'stale_after_days': 1,
        'data_age_days': 0,
        'coverage': {
            'snapshot_date': SNAPSHOT_DAY,
            'teams_expected': 30,
            'teams_covered': 30 - len(missing),
            'teams_missing': list(missing),
        },
    }


def _team_read(family, team_id=113):
    return readiness_service.build_public_roster_readiness(
        reference_date=None,
        team_id=team_id,
        scope='team',
        family=family,
    )


def test_missing_other_team_does_not_withhold_clean_team():
    readiness = _team_read(_family(
        reasons=('roster_snapshot_team_coverage_incomplete',),
        missing=(114,),
    ))

    assert readiness['claims_available'] is True
    assert readiness['readiness_state'] == 'ready'
    assert readiness['league_readiness_state'] == 'degraded'
    assert readiness['coverage']['complete'] is False
    assert readiness['coverage']['scope_complete'] is True
    assert readiness['reason_codes'] == []


def test_missing_selected_team_still_fails_closed():
    readiness = _team_read(_family(
        reasons=('roster_snapshot_team_coverage_incomplete',),
        missing=(113,),
    ))

    assert readiness['claims_available'] is False
    assert readiness['readiness_state'] == 'degraded'
    assert readiness['coverage']['scope_complete'] is False
    assert readiness['reason_codes'] == ['roster_snapshot_team_coverage_incomplete']


def test_dead_letter_on_another_team_is_isolated(monkeypatch):
    monkeypatch.setattr(
        readiness_service,
        '_team_dead_letter_evaluation',
        lambda team_id: {'team_failure_count': 0, 'unscoped_failure_count': 0},
    )
    readiness = _team_read(_family(reasons=('dead_letters_unresolved',)))

    assert readiness['claims_available'] is True
    assert readiness['scope_evaluation']['isolated_from_league_degradation'] is True
    assert readiness['reason_codes'] == []
    assert readiness['league_reason_codes'] == ['dead_letters_unresolved']


def test_dead_letter_on_selected_team_still_fails_closed(monkeypatch):
    monkeypatch.setattr(
        readiness_service,
        '_team_dead_letter_evaluation',
        lambda team_id: {'team_failure_count': 2, 'unscoped_failure_count': 0},
    )
    readiness = _team_read(_family(reasons=('dead_letters_unresolved',)))

    assert readiness['claims_available'] is False
    assert readiness['reason_codes'] == ['dead_letters_unresolved']
    assert readiness['scope_evaluation']['team_dead_letter_count'] == 2


def test_unscoped_dead_letter_still_blocks_every_team(monkeypatch):
    monkeypatch.setattr(
        readiness_service,
        '_team_dead_letter_evaluation',
        lambda team_id: {'team_failure_count': 0, 'unscoped_failure_count': 1},
    )
    readiness = _team_read(_family(reasons=('dead_letters_unresolved',)))

    assert readiness['claims_available'] is False
    assert readiness['reason_codes'] == ['dead_letters_unresolved']
    assert readiness['scope_evaluation']['unscoped_dead_letter_count'] == 1


def test_cache_divergence_is_checked_only_for_selected_team(monkeypatch):
    monkeypatch.setattr(
        readiness_service,
        'roster_status_cache_divergence_count',
        lambda team_ids=None: 1 if team_ids == [114] else 0,
    )
    family = _family(reasons=('roster_status_cache_divergence',))

    clean = _team_read(family, team_id=113)
    affected = _team_read(family, team_id=114)

    assert clean['claims_available'] is True
    assert clean['reason_codes'] == []
    assert affected['claims_available'] is False
    assert affected['reason_codes'] == ['roster_status_cache_divergence']


def test_stale_source_remains_a_global_team_page_blocker(monkeypatch):
    monkeypatch.setattr(
        readiness_service,
        '_team_dead_letter_evaluation',
        lambda team_id: (_ for _ in ()).throw(AssertionError('must not query team blockers')),
    )
    readiness = _team_read(_family(
        status='stale',
        reasons=('source_stale',),
        fail_closed=True,
    ))

    assert readiness['claims_available'] is False
    assert readiness['readiness_state'] == 'stale'
    assert readiness['reason_codes'] == ['source_stale']


def test_league_scope_remains_globally_fail_closed():
    readiness = readiness_service.build_public_roster_readiness(
        scope='league',
        family=_family(reasons=('dead_letters_unresolved',)),
    )

    assert readiness['claims_available'] is False
    assert readiness['readiness_state'] == 'degraded'
    assert readiness['reason_codes'] == ['dead_letters_unresolved']
    assert readiness['scope_evaluation']['mode'] == 'league'
