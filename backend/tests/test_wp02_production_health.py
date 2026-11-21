"""WP-0.2 production health contract (EOS-008) and offseason quiet-day rules."""

from datetime import datetime, timedelta, timezone

import pytest

from scripts import check_production_health as cli
from services.production_health import (
    MAX_CURRENT_READ_DATA_AGE_DAYS,
    evaluate_production_health,
)

NOW = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)
HEALTH = {'status': 'ok', 'environment': 'production', 'release': 'a' * 40}


def _team(outcome='season_complete', available=False):
    return {'team_state': {'available': available, 'outcome': outcome}}


def _listing(*, available=0, season_complete=30, data_through='2026-10-28',
             published_at=(NOW - timedelta(hours=3)).replace(tzinfo=None).isoformat()):
    teams = [_team('available', True) for _ in range(available)]
    teams += [_team() for _ in range(season_complete)]
    teams += [_team('competition_status_unconfirmed') for _ in range(30 - len(teams))]
    return {
        'expected_team_count': 30,
        'team_count': 30,
        'represented_team_count': available,
        'withheld_team_count': 30 - available,
        'publication_authority': {
            'snapshot_id': 5820, 'data_through': data_through, 'published_at': published_at,
        },
        'freshness': {'data_through': data_through},
        'teams': teams,
    }


def _evaluate(**overrides):
    kwargs = dict(
        health=HEALTH, health_status_code=200, listing=_listing(), listing_status_code=200,
        now=NOW, expected_release='b' * 40, release_is_current=True,
    )
    kwargs.update(overrides)
    return evaluate_production_health(**kwargs)


def _severity(result, name):
    return {item['check']: item['severity'] for item in result['checks']}[name]


def test_offseason_quiet_day_is_healthy():
    # 2026-11-05: last game 2026-10-28, every club Season Complete, a fresh
    # scheduled publication. No games is not an outage.
    result = _evaluate()
    assert result['status'] == 'healthy'
    assert result['critical_checks'] == []
    assert _severity(result, 'season_phase') == 'info'
    assert _severity(result, 'publication_recent') == 'ok'


def test_missed_publication_is_critical_even_in_the_offseason():
    stale = (NOW - timedelta(hours=40)).replace(tzinfo=None).isoformat()
    result = _evaluate(listing=_listing(published_at=stale))
    assert 'publication_recent' in result['critical_checks']


def test_stale_data_presented_as_current_is_critical():
    # The October 2026 failure: current reads from data a week old.
    old = (NOW.date() - timedelta(days=MAX_CURRENT_READ_DATA_AGE_DAYS + 2)).isoformat()
    result = _evaluate(listing=_listing(available=28, season_complete=2, data_through=old))
    assert 'stale_read_presented_as_current' in result['critical_checks']


def test_in_season_current_reads_with_recent_data_are_healthy():
    recent = (NOW.date() - timedelta(days=1)).isoformat()
    result = _evaluate(listing=_listing(available=30, season_complete=0, data_through=recent))
    assert result['status'] == 'healthy'


def test_unexplained_empty_listing_is_a_warning_not_an_outage():
    result = _evaluate(listing=_listing(available=0, season_complete=10))
    assert result['status'] == 'degraded'
    assert result['warning_checks'] == ['season_phase']


def test_api_down_is_critical():
    result = _evaluate(health=None, health_status_code=None, listing=None, listing_status_code=503)
    assert {'api_serving', 'read_model_serving'} <= set(result['critical_checks'])


def test_inconsistent_read_model_is_critical():
    listing = _listing()
    listing['represented_team_count'] = 3
    result = _evaluate(listing=listing)
    assert 'read_model_consistency' in result['critical_checks']


def test_future_data_through_is_critical():
    result = _evaluate(listing=_listing(data_through=(NOW.date() + timedelta(days=1)).isoformat()))
    assert 'data_dating' in result['critical_checks']


@pytest.mark.parametrize('environment', ['development', 'test', None])
def test_non_production_environment_is_critical(environment):
    result = _evaluate(health={**HEALTH, 'environment': environment})
    assert 'api_environment' in result['critical_checks']


def test_backend_deployment_identity_checks():
    # Behind main's latest backend change: the deployment did not land.
    assert 'deployed_release' in _evaluate(release_is_current=False)['critical_checks']
    # No reported release: unverifiable, never silently healthy.
    result = _evaluate(health={**HEALTH, 'release': None})
    assert result['warning_checks'] == ['deployed_release']
    # Reported but not comparable (e.g. commit not in local history).
    assert _severity(_evaluate(release_is_current=None), 'deployed_release') == 'info'


def test_api_base_url_is_derived_from_the_sync_url_without_exposing_it():
    assert cli.api_base_url({'BASEBALLOS_API_BASE_URL': 'https://api.example.test/'}) == (
        'https://api.example.test'
    )
    assert cli.api_base_url({'BASEBALLOS_SYNC_URL': 'https://api.example.test/api/bullpen/sync'}) == (
        'https://api.example.test'
    )
    assert cli.api_base_url({'BASEBALLOS_SYNC_URL': 'https://api.example.test/other'}) is None
    assert cli.api_base_url({}) is None


def test_release_comparison_uses_git_ancestry():
    head = cli._git('rev-parse', 'HEAD')[1]
    parent = cli._git('rev-parse', 'HEAD~1')[1]
    if not head or not parent:
        pytest.skip('git history unavailable')
    assert cli.release_contains(head, parent) is True
    assert cli.release_contains(parent, head) is False
    assert cli.release_contains('f' * 40, head) is None
    assert cli.release_contains(None, head) is None


def test_health_endpoint_reports_the_render_release(monkeypatch):
    from app import create_app

    monkeypatch.setenv('RENDER_GIT_COMMIT', 'c' * 40)
    client = create_app('test').test_client()
    body = client.get('/api/health').get_json()
    assert body['status'] == 'ok'
    assert body['release'] == 'c' * 40

    monkeypatch.delenv('RENDER_GIT_COMMIT', raising=False)
    assert create_app('test').test_client().get('/api/health').get_json()['release'] is None
