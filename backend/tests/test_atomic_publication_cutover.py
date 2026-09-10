from datetime import date, datetime

import pytest
from flask import Flask

from models.atomic_publication import AtomicPublication, AtomicPublicationCurrent
from models.canonical_impact import CanonicalImpactPlan
from models.derived_intelligence import DerivedCohortSnapshot, DerivedIntelligenceCohort
from services.atomic_publication import PublicationValidationError
from services.atomic_publication_cutover import (
    inspect_publication_candidates,
    publish_selected_cohort,
)
from services.mlb_club_directory import MLB_TEAM_IDS
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    db.init_app(flask_app)
    with flask_app.app_context():
        create_test_schema(flask_app)
        try:
            yield flask_app
        finally:
            db.session.remove()
            drop_test_schema(flask_app)


def _candidate(marker='a', status='complete'):
    plan = CanonicalImpactPlan(
        plan_fingerprint=(marker * 64)[:64], rules_version='canonical-impact-v1',
        authority_class='final', baseball_date=date(2026, 9, 9),
        correlation_id=f'cutover-{marker}', affected_game_ids_json=[777123],
        affected_team_ids_json=[110], affected_pitcher_ids_json=[10],
        affected_domains_json=['game_context', 'pitcher_snapshot', 'team_snapshot'],
        source_observation_ids_json=[], status='dispatched', supersedes_live=False,
    )
    db.session.add(plan)
    db.session.flush()
    cohort = DerivedIntelligenceCohort(
        impact_plan_id=plan.id, cohort_fingerprint=(marker.upper() * 64)[:64],
        schema_version='derived-cohort-v1', authority_class='final',
        baseball_date=date(2026, 9, 9), correlation_id=plan.correlation_id,
        status=status,
        requested_domains_json=['game_context', 'pitcher_snapshot', 'team_snapshot'],
        execution_domains_json=['game_context', 'pitcher_snapshot', 'team_snapshot'],
        completed_domains_json=['game_context', 'pitcher_snapshot', 'team_snapshot'],
        withheld_domains_json=[], affected_game_ids_json=[777123],
        affected_team_ids_json=[110], affected_pitcher_ids_json=[10],
        input_manifest_json=[], method_versions_json={'team_snapshot': 'test-v1'},
        completed_at=datetime(2026, 9, 9, 12, 0),
    )
    db.session.add(cohort)
    db.session.flush()
    for kind, key in (('game', 777123), ('team', 110), ('pitcher', 10)):
        payload = {f'{kind}_snapshot': {'marker': marker}}
        if kind == 'team':
            payload['read_models'] = {
                'team_board': {'team_id': key}, 'league_row': {'team_id': key},
            }
        elif kind == 'game':
            payload['read_models'] = {'matchup': {'game_pk': key}}
        db.session.add(DerivedCohortSnapshot(
            cohort_id=cohort.id, entity_type=kind, entity_key=str(key),
            snapshot_type=f'{kind}_intelligence', baseball_date=cohort.baseball_date,
            authority_class='final', payload_schema_version=1,
            payload_json=payload,
        ))
    for team_id in sorted(set(MLB_TEAM_IDS) - {110}):
        db.session.add(DerivedCohortSnapshot(
            cohort_id=cohort.id, entity_type='team', entity_key=str(team_id),
            snapshot_type='team_intelligence', baseball_date=cohort.baseball_date,
            authority_class='final', payload_schema_version=1,
            payload_json={
                'team_snapshot': {'marker': marker, 'team_id': team_id},
                'read_models': {
                    'team_board': {'team_id': team_id},
                    'league_row': {'team_id': team_id},
                },
            },
        ))
    db.session.commit()
    return cohort


def test_inspection_is_read_only_and_reports_eligible_cohort(app):
    cohort = _candidate()
    report = inspect_publication_candidates()
    assert report['current_publication_id'] is None
    assert report['eligible_candidates'][0]['cohort_id'] == cohort.id
    assert report['eligible_candidates'][0]['first_publication_baseline']['complete'] is True
    assert report['eligible_candidates'][0]['first_publication_baseline']['artifact_counts']['team'] == 30
    assert report['prepublication_health']['status'] in ('pass', 'fail')
    assert AtomicPublication.query.count() == 0


def test_inspection_blocks_incomplete_first_generation(app):
    cohort = _candidate()
    DerivedCohortSnapshot.query.filter_by(
        cohort_id=cohort.id, entity_type='team', entity_key='108',
    ).delete()
    db.session.commit()
    report = inspect_publication_candidates()
    candidate = report['reviewed_candidates'][0]
    assert candidate['eligible'] is False
    assert candidate['ineligible_reason'] == 'first_publication_team_coverage_incomplete:108'
    assert db.session.get(AtomicPublicationCurrent, 1) is None


def test_controlled_publication_uses_sp11_job_and_advances_once(app):
    cohort = _candidate()
    result = publish_selected_cohort(cohort.id)
    assert result['pointer_before'] is None
    assert result['pointer_after'] == result['publication_id']
    assert result['publication_job_status'] == 'succeeded'
    assert len(result['artifact_ids']) == 32
    assert result['artifact_created_count'] == 32
    assert result['artifact_inherited_count'] == 0
    assert db.session.get(AtomicPublicationCurrent, 1).publication_id == result['publication_id']


def test_invalid_candidate_does_not_move_pointer(app):
    cohort = _candidate(status='partial')
    with pytest.raises(PublicationValidationError, match='cohort_not_complete'):
        publish_selected_cohort(cohort.id)
    assert db.session.get(AtomicPublicationCurrent, 1) is None
