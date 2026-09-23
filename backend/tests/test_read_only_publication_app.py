"""Security boundary for read-only trusted-publication commands."""

import json
from types import SimpleNamespace

import pytest


def test_read_only_production_context_needs_no_write_endpoint_credentials(
    monkeypatch, tmp_path,
):
    monkeypatch.setenv('APP_ENV', 'production')
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{tmp_path / "proof.db"}')
    monkeypatch.delenv('SECRET_KEY', raising=False)
    monkeypatch.delenv('ADMIN_API_TOKEN', raising=False)

    from utils.read_only_app import create_read_only_app

    app = create_read_only_app()

    assert app.config['APP_ENV'] == 'production'
    assert app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite:///')
    assert [rule.rule for rule in app.url_map.iter_rules()] == ['/static/<path:filename>']


def test_production_api_still_refuses_to_start_without_admin_token(
    monkeypatch, tmp_path,
):
    from app import create_app
    from config import ProductionConfig

    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{tmp_path / "api.db"}')
    monkeypatch.setattr(ProductionConfig, 'SECRET_KEY', 'strong-production-test-secret')
    monkeypatch.setattr(ProductionConfig, 'ADMIN_API_TOKEN', None)

    with pytest.raises(RuntimeError, match='ADMIN_API_TOKEN must be set'):
        create_app('production')


def test_proof_export_succeeds_without_admin_token(
    monkeypatch, tmp_path,
):
    from flask import Flask
    from scripts import export_team_state_publication_proof as exporter
    from services import team_state_vnext_production_proof as proof_module

    monkeypatch.delenv('ADMIN_API_TOKEN', raising=False)
    snapshot = SimpleNamespace(id=3435)
    proof = {'publication': {'dashboard_snapshot_id': 3435}}
    observation = {
        'publication_observed': True,
        'snapshot_id': 3435,
        'status': proof_module.OBSERVATION_PROOF_VALID,
        'reason_code': None,
        'observed_team_count': 30,
        'receipt_digest': 'sha256:same',
        'expected_receipt_digest': 'sha256:same',
        'differences': [],
    }
    monkeypatch.setattr(
        'utils.read_only_app.create_read_only_app', lambda: Flask('read-only-test'),
    )
    monkeypatch.setattr(
        'services.production_accuracy_reconciliation.resolve_snapshot',
        lambda **_kwargs: snapshot,
    )
    monkeypatch.setattr(
        proof_module, 'load_durable_proof',
        lambda _snapshot_id: SimpleNamespace(proof=proof),
    )
    monkeypatch.setattr(
        proof_module, 'build_postcommit_observation',
        lambda _snapshot, _proof: observation,
    )
    output = tmp_path / 'proof.json'
    marker = tmp_path / 'observation.json'

    result = exporter.main([
        '--current', '--output', str(output),
        '--observation-output', str(marker),
    ])

    assert result == 0
    assert json.loads(output.read_text())['postcommit_observation'] == observation
    assert json.loads(marker.read_text()) == observation


def test_proof_export_retains_a_precise_failure_marker(monkeypatch, tmp_path):
    from flask import Flask
    from scripts import export_team_state_publication_proof as exporter

    monkeypatch.setattr(
        'utils.read_only_app.create_read_only_app', lambda: Flask('read-only-test'),
    )
    monkeypatch.setattr(
        'services.production_accuracy_reconciliation.resolve_snapshot',
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError('database unavailable')),
    )
    marker = tmp_path / 'observation.json'

    result = exporter.main([
        '--current', '--output', str(tmp_path / 'proof.json'),
        '--observation-output', str(marker),
    ])

    assert result == 4
    assert json.loads(marker.read_text()) == {
        'publication_observed': None,
        'snapshot_id': None,
        'status': 'export_failed',
        'reason_code': 'proof_export_failed',
    }
