from datetime import date, datetime

import pytest
from flask import Flask

from models.atomic_publication import AtomicPublication, AtomicPublicationCurrent
from models.canonical_impact import CanonicalImpactPlan
from models.derived_intelligence import DerivedCohortSnapshot, DerivedIntelligenceCohort
from models.pitcher import Pitcher
from models.roster_membership import RosterMembershipInterval, RosterMembershipMutation
from models.source_observation import SourceObservation, SourceSubject
from services.atomic_publication import PublicationValidationError
from services.atomic_publication_cutover import (
    inspect_publication_cohort,
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
    from tests.test_atomic_publication import _reader_payload, _snapshot
    for team_id in MLB_TEAM_IDS:
        payload = _reader_payload('team', team_id, marker)
        _snapshot(cohort, 'team', team_id, {
            'read_models': {'team_board_v2': payload['read_models']['team_board_v2']},
        }, snapshot_type='team_board_v2_publication')
        _snapshot(cohort, 'team', team_id, {
            'what_changed': payload['what_changed'],
        }, snapshot_type='what_changed_publication')
    _snapshot(cohort, 'pitcher', 10, _reader_payload('pitcher', 10, marker),
              snapshot_type='pitcher_current_publication')
    db.session.commit()
    return cohort


def test_inspection_is_read_only_and_reports_eligible_cohort(app):
    cohort = _candidate()
    report = inspect_publication_candidates()
    assert report['current_publication_id'] is None
    assert report['eligible_candidates'][0]['cohort_id'] == cohort.id
    assert report['eligible_candidates'][0]['first_publication_baseline']['complete'] is True
    assert report['eligible_candidates'][0]['first_publication_baseline']['artifact_counts']['team'] == 90
    assert report['prepublication_health']['status'] in ('pass', 'fail')
    assert AtomicPublication.query.count() == 0


def test_single_cohort_inspection_reports_exact_watermark_revalidation(app):
    cohort = _candidate()
    report = inspect_publication_cohort(cohort.id)
    revalidation = report['cohort']['input_revalidation']
    assert revalidation['captured_input_manifest'] == []
    assert revalidation['completion_input_manifest'] == []
    assert revalidation['current_input_manifest'] == []
    assert revalidation['captured_input_fingerprint'] == revalidation['current_input_fingerprint']
    assert revalidation['difference'] == {'added': [], 'removed': [], 'changed': []}
    assert report['cohort']['candidate_snapshot_count'] == 93
    assert AtomicPublication.query.count() == 0


def test_single_cohort_inspection_traces_changed_roster_input(app):
    cohort = _candidate()
    plan = db.session.get(CanonicalImpactPlan, cohort.impact_plan_id)
    plan.authority_class = 'roster_authoritative'
    plan.affected_domains_json = ['roster_composition']
    cohort.authority_class = 'roster_authoritative'
    subject = SourceSubject(
        identity_key='r' * 64, provider='mlb_statsapi', source_domain='roster',
        endpoint='/roster', subject_type='team_roster', subject_key='110:40Man',
        request_identity='q' * 64, request_schema_version=1,
        request_parameters={}, baseball_date=date(2026, 9, 9),
    )
    db.session.add(subject)
    db.session.flush()
    observation = SourceObservation(
        source_subject_id=subject.id, version_number=1, dedupe_key='d' * 64,
        fingerprint='f' * 64, fingerprint_algorithm='sha256',
        fingerprint_version='source-fingerprint-v1', payload_schema_version=1,
        completeness='complete', outcome='new', is_change=True,
        is_authoritative=True, record_count=1,
        observed_at=datetime(2026, 9, 9, 12, 1),
    )
    db.session.add(observation)
    db.session.flush()
    db.session.add(Pitcher(
        id=10, mlb_id=10010, full_name='Roster Watermark Pitcher',
        team_id=110, team_name='Test Team', team_abbreviation='TST', active=True,
    ))
    db.session.flush()
    interval = RosterMembershipInterval(
        pitcher_id=10, player_mlb_id=10010, team_id=110,
        organization_id=110, membership_type='forty_man_roster',
        effective_start_date=date(2026, 9, 9), start_precision='date',
        authority_type='official_mlb_roster',
        opened_by_observation_id=observation.id,
    )
    db.session.add(interval)
    db.session.flush()
    cohort.input_manifest_json = [{
        'input_type': 'roster_membership', 'input_key': '110:10:forty_man_roster',
        'input_version': f'{interval.id}:2026-09-09:open',
        'input_fingerprint': None, 'authority_class': 'roster_authoritative',
        'source_observation_id': observation.id,
    }]
    interval.effective_end_date = date(2026, 9, 9)
    interval.closed_by_observation_id = observation.id
    mutation = RosterMembershipMutation(
        interval_id=interval.id, pitcher_id=10, player_mlb_id=10010,
        team_id=110, membership_type='forty_man_roster',
        mutation_type='membership_closed', baseball_date=date(2026, 9, 9),
        precision='date', source_observation_id=observation.id,
    )
    db.session.add(mutation)
    db.session.commit()

    report = inspect_publication_cohort(cohort.id)
    revalidation = report['cohort']['input_revalidation']
    assert len(revalidation['difference']['changed']) == 1
    detail = revalidation['changed_input_details'][0]
    assert detail['interval']['id'] == interval.id
    assert detail['interval']['closed_by_observation_id'] == observation.id
    assert detail['mutations'][0]['mutation_type'] == 'membership_closed'


def test_inspection_blocks_incomplete_first_generation(app):
    cohort = _candidate()
    DerivedCohortSnapshot.query.filter_by(
        cohort_id=cohort.id, entity_type='team', entity_key='108',
    ).delete()
    db.session.commit()
    report = inspect_publication_candidates()
    candidate = report['reviewed_candidates'][0]
    assert candidate['eligible'] is False
    assert 'team_coverage_incomplete' in candidate['ineligible_reason']
    assert '108' in candidate['ineligible_reason']
    assert db.session.get(AtomicPublicationCurrent, 1) is None


def test_controlled_publication_uses_sp11_job_and_advances_once(app):
    cohort = _candidate()
    result = publish_selected_cohort(cohort.id)
    assert result['pointer_before'] is None
    assert result['pointer_after'] == result['publication_id']
    assert result['publication_job_status'] == 'succeeded'
    assert len(result['artifact_ids']) == 93
    assert result['artifact_created_count'] == 93
    assert result['artifact_inherited_count'] == 0
    assert db.session.get(AtomicPublicationCurrent, 1).publication_id == result['publication_id']


def test_invalid_candidate_does_not_move_pointer(app):
    cohort = _candidate(status='partial')
    with pytest.raises(PublicationValidationError, match='cohort_not_complete'):
        publish_selected_cohort(cohort.id)
    assert db.session.get(AtomicPublicationCurrent, 1) is None
