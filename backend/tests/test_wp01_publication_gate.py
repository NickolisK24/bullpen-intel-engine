"""WP-0.1 through the real publication transaction and Team State proof.

Drives ``publish_dashboard_snapshot`` with the mandatory pre-trust proof, a
governed readiness resolver standing in for the live classifier, and the real
receipts, eligibility, plausibility, and League listing code:

* a World Series publication (two clubs playing, 28 finished) commits, with
  the 28 frozen as governed season withholdings rather than failing the proof;
* every surface reads the same withholding for those clubs;
* a publication that would count an idle arm as a constraint is refused and
  the previous trusted snapshot keeps serving.
"""

from datetime import date, timedelta

import pytest

from models.dashboard_snapshot import DashboardSnapshot
from models.share_artifact import ShareArtifact
from models.team_state_publication_proof import TeamStatePublicationProof
from services import dashboard_snapshot, team_state_source
from services import team_state_vnext_production_proof as proof_service
from services.mlb_club_directory import MLB_TEAM_IDS
from services.team_board_snapshot_team_state import build_team_accounting, receipt_value
from services.team_state_plausibility import TeamStatePlausibilityBlocked
from services.team_state_public_vocabulary import TEAM_STATE_SEASON_COMPLETE
from tests.test_dashboard_snapshot import (  # noqa: F401
    _create_sync_run,
    _minimal_dashboard_payload,
    _team_state_proof_readiness,
    app,
)
from utils.db import db
from utils.time import utc_now_naive


DATA_THROUGH = date(2026, 10, 27)
AVAILABILITY = date(2026, 10, 28)
PLAYING = (158, 139)  # Milwaukee, Tampa Bay


def _season_context(team_id):
    if team_id in PLAYING:
        return {
            'contract': 'club_competition_status_v1', 'team_id': team_id,
            'status': 'active', 'basis': 'upcoming_scheduled_game',
            'reference_date': AVAILABILITY.isoformat(),
            'last_final_game_date': DATA_THROUGH.isoformat(),
            'last_final_game_type': 'W',
            'next_scheduled_game_date': AVAILABILITY.isoformat(),
        }
    return {
        'contract': 'club_competition_status_v1', 'team_id': team_id,
        'status': 'season_complete', 'basis': 'postseason_scheduled_without_club',
        'reference_date': AVAILABILITY.isoformat(),
        'last_final_game_date': '2026-09-27',
        'last_final_game_type': 'R',
        'next_scheduled_game_date': None,
    }


def _candidate(run):
    payload = _minimal_dashboard_payload()
    payload['freshness']['data_through'] = DATA_THROUGH.isoformat()
    payload['freshness']['availability_reference_date'] = AVAILABILITY.isoformat()
    payload['freshness']['slate_coverage']['slate_date'] = DATA_THROUGH.isoformat()
    payload['trusted_team_boards'] = {
        'contract': 'trusted_team_board_publication_v1',
        'data_through': DATA_THROUGH.isoformat(),
        'team_accounting': build_team_accounting(MLB_TEAM_IDS, MLB_TEAM_IDS),
        'by_team_id': {
            str(team_id): {'team': {'team_id': team_id}} for team_id in MLB_TEAM_IDS
        },
    }
    candidate = DashboardSnapshot(
        snapshot_type=dashboard_snapshot.SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
        sync_run_id=run.id,
        status=dashboard_snapshot.SNAPSHOT_STATUS_PENDING,
        is_published=False,
        payload=payload,
        payload_version=dashboard_snapshot.DASHBOARD_PAYLOAD_VERSION,
        data_through=DATA_THROUGH,
        availability_reference_date=AVAILABILITY,
        snapshot_generated_at=utc_now_naive(),
        source='external_schedule',
    )
    db.session.add(candidate)
    return candidate


def _serving(run):
    previous = DashboardSnapshot(
        snapshot_type=dashboard_snapshot.SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
        sync_run_id=run.id,
        status=dashboard_snapshot.SNAPSHOT_STATUS_READY,
        is_published=True,
        published_at=utc_now_naive() - timedelta(days=1),
        payload={**_minimal_dashboard_payload(), 'name': 'serving'},
        payload_version=dashboard_snapshot.DASHBOARD_PAYLOAD_VERSION,
        data_through=DATA_THROUGH - timedelta(days=1),
        availability_reference_date=DATA_THROUGH,
        snapshot_generated_at=utc_now_naive() - timedelta(days=1),
        source='external_schedule',
    )
    db.session.add(previous)
    return previous


def _arm_reads(team_id, *, idle_constrained=False):
    records = [
        {
            'pitcher_id': team_id * 100 + index,
            'public_read': {'key': 'clean_option', 'label': 'Clean Option'},
            'evidence_state': {'data_state': 'stale' if index < 3 else 'fresh'},
        }
        for index in range(6)
    ] + [
        {
            'pitcher_id': team_id * 100 + 10 + index,
            'public_read': {'key': 'watch_arm', 'label': 'Watch Arm'},
            'evidence_state': {
                'data_state': 'stale' if idle_constrained and index == 0 else 'fresh',
            },
        }
        for index in range(2)
    ]
    return {'records': records}


def _wire(app, monkeypatch, candidate, *, idle_constrained_team=None):
    app.config['TEAM_STATE_PUBLICATION_PROOF_REQUIRED'] = True
    monkeypatch.setattr(dashboard_snapshot, 'product_current_date', lambda: AVAILABILITY)
    monkeypatch.setattr(team_state_source, 'is_valid_team_id', lambda _team_id: True)
    real_requirement = proof_service.require_transactional_publication_proof

    def resolver(team_id, **kwargs):
        readiness = _team_state_proof_readiness(kwargs['reference_dates_out'], candidate)
        readiness['freshness'] = {
            'data_through': DATA_THROUGH.isoformat(), 'freshness_state': 'current',
        }
        readiness['team'] = {
            'team_id': team_id, 'team_name': f'Team {team_id}',
            'team_abbreviation': f'T{team_id}',
        }
        readiness['readiness']['summary'] = 'Current bullpen state.'
        readiness['trust_metadata'] = {'confidence': 'high', 'data_state': 'fresh'}
        readiness['season_context'] = _season_context(team_id)
        kwargs['arm_reads_out'].update(
            _arm_reads(team_id, idle_constrained=team_id == idle_constrained_team)
        )
        return readiness

    monkeypatch.setattr(
        proof_service, 'require_transactional_publication_proof',
        lambda snapshot: real_requirement(
            snapshot, team_ids=MLB_TEAM_IDS, readiness_resolver=resolver,
        ),
    )


def test_world_series_publication_withholds_finished_clubs_and_commits(app, monkeypatch):
    with app.app_context():
        run = _create_sync_run(stage='started')
        candidate = _candidate(run)
        db.session.commit()
        artifacts_before = ShareArtifact.query.count()
        _wire(app, monkeypatch, candidate)

        dashboard_snapshot.publish_dashboard_snapshot(candidate)
        db.session.refresh(candidate)

        assert candidate.is_published is True
        receipts = candidate.payload['trusted_team_boards']['frozen_team_state_by_team_id']
        assert len(receipts) == 30
        published = {
            int(team_id): receipt['value'] for team_id, receipt in receipts.items()
        }
        for team_id, value in published.items():
            if team_id in PLAYING:
                assert value['available'] is True
                assert value['public_label'] == 'Fresh'
            else:
                assert value['available'] is False
                assert value['outcome'] == TEAM_STATE_SEASON_COMPLETE
                assert value['public_label'] is None
            assert value['data_through'] == DATA_THROUGH.isoformat()

        # The board serving path reads the same frozen withholding.
        present, value = receipt_value(candidate, 120)
        assert present is True and value['outcome'] == TEAM_STATE_SEASON_COMPLETE

        proof_row = TeamStatePublicationProof.query.one()
        proof = proof_row.proof
        assert proof['competition_withheld']['team_ids'] == sorted(
            team_id for team_id in MLB_TEAM_IDS if team_id not in PLAYING
        )
        assert proof['plausibility']['blocked'] is False
        assert proof['plausibility']['published_team_count'] == 2
        assert proof['distribution']['withheld'] == 28
        assert proof['distribution']['fresh'] == 2
        assert proof['invariants']['all_teams_published']['result'] == 'PASS'
        assert proof['invariants']['distribution_consistent']['result'] == 'PASS'
        # Withholding writes no artifact and changes no existing artifact.
        assert ShareArtifact.query.count() == artifacts_before


def test_idle_arm_counted_as_constraint_refuses_publication(app, monkeypatch):
    with app.app_context():
        serving_run = _create_sync_run()
        previous = _serving(serving_run)
        run = _create_sync_run(stage='started')
        candidate = _candidate(run)
        db.session.commit()
        _wire(app, monkeypatch, candidate, idle_constrained_team=PLAYING[0])

        with pytest.raises(TeamStatePlausibilityBlocked) as raised:
            dashboard_snapshot.publish_dashboard_snapshot(candidate)
        db.session.rollback()

        assert 'inactivity_counted_as_constraint' in str(raised.value)
        evidence = raised.value.publication_evidence
        assert evidence['blocking_checks'] == ['inactivity_counted_as_constraint']
        db.session.refresh(previous)
        db.session.refresh(candidate)
        assert previous.is_published is True
        assert candidate.is_published is False
        assert TeamStatePublicationProof.query.count() == 0
        assert dashboard_snapshot.get_latest_dashboard_snapshot().id == previous.id
