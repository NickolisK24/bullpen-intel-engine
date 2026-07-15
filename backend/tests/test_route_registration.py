"""Route registration coverage for preserved and retired product surfaces."""


def test_retired_routes_are_absent_and_preserved_routes_remain(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///:memory:')
    monkeypatch.setenv('TEST_DATABASE_URL', 'sqlite:///:memory:')

    from app import create_app

    flask_app = create_app('test')
    rules = {str(rule) for rule in flask_app.url_map.iter_rules()}

    retired_exact = {
        '/api/system/product-events',
        '/api/system/product-event-heartbeat',
        '/api/system/digest-status',
        '/api/system/digest-metrics',
        '/api/system/digest-test-send',
    }
    assert rules.isdisjoint(retired_exact)
    assert not any(rule.startswith('/api/product/') for rule in rules)
    assert not any(rule.startswith('/api/digest/') for rule in rules)

    assert '/api/audience/signup' in rules
    assert '/api/auth/me' in rules
    assert '/api/auth/request-link' in rules
    assert '/api/auth/verify' in rules
    assert '/api/me/teams' in rules
    assert '/api/me/teams/<int:team_id>' in rules
    assert '/api/me/primary-team' in rules
    assert '/api/system/email-delivery-health' in rules
    assert '/api/bullpen/dashboard' in rules
    assert '/api/system/pipeline-health' in rules
    assert '/api/system/internal/pitcher-evidence' in rules
    assert '/api/traffic/page-view' in rules
    assert '/api/traffic/internal/summary' in rules
