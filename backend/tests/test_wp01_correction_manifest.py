"""WP-0.1 (EOS-003): dry-run correction manifest for frozen Team State artifacts.

The manifest proposes corrections; it never changes an artifact. These tests
pin the classification rules, determinism, the offline inventory, and that a
database dry run leaves every artifact byte-for-byte unchanged.
"""

from datetime import date, datetime
import random

import pytest
from flask import Flask

from models.dashboard_snapshot import DashboardSnapshot
from models.scheduled_game import ScheduledGame
from models.share_artifact import ShareArtifact
from models.sync_run import SyncRun
from models.team_state_publication_proof import TeamStatePublicationProof
from services.team_state_correction_manifest import (
    ACTION_RETAIN,
    ACTION_REVIEW,
    ACTION_SUPERSEDE,
    REASON_COMPETITION_UNDETERMINED,
    REASON_INACTIVITY_CONSTRAINT,
    REASON_INPUTS_MISSING,
    REASON_NOT_IN_COMPETITION,
    build_manifest,
    classify_artifact_for_correction,
    corrected_team_state,
    load_manifest_entries,
    static_inventory_entries,
)
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


THRESHOLDS = {
    'clean_share_fresh_min': [3, 5],
    'clean_count_fresh_min': 5,
    'severe_count_fresh_max': 1,
    'clean_count_vulnerable_max': 2,
    'severe_share_vulnerable_min': [1, 3],
}


def _inputs(clean, moderate, severe=0, unknown=0, *, stale_limited=0, missing_limited=0):
    arms = (
        [{'pitcher_id': index, 'public_read': {'key': 'clean_option'},
          'evidence_state': {'data_state': 'fresh'}} for index in range(clean)]
        + [{'pitcher_id': 100 + index, 'public_read': {'key': 'limited_read'},
            'evidence_state': {'data_state': 'stale'}} for index in range(stale_limited)]
        + [{'pitcher_id': 200 + index, 'public_read': {'key': 'limited_read'},
            'evidence_state': {'data_state': 'missing'}} for index in range(missing_limited)]
        + [{'pitcher_id': 300 + index, 'public_read': {'key': 'watch_arm'},
            'evidence_state': {'data_state': 'fresh'}}
           for index in range(moderate - stale_limited - missing_limited)]
    )
    return {
        'readiness': {'team_state_evidence': {
            'clean_count': clean, 'moderate_count': moderate,
            'severe_count': severe, 'unknown_count': unknown,
            'thresholds_applied': THRESHOLDS,
        }},
        'reference_dates': {'availability_reference_date': '2026-10-28'},
        'arm_reads': {'records': arms},
    }


def _artifact(state='vulnerable', team_id=120, public_id='178c7a7f812645e6b6d5126e06a92aab'):
    return {
        'public_id': public_id, 'team_id': team_id, 'team_abbreviation': 'WSH',
        'product_date': date(2026, 10, 27), 'source_snapshot_id': 5656,
        'published_public_state': state,
    }


def _status(status, basis='upcoming_scheduled_game'):
    return {'status': status, 'basis': basis, 'reference_date': '2026-10-28',
            'last_final_game_date': '2026-09-27'}


def test_club_out_of_competition_is_proposed_for_supersession():
    entry = classify_artifact_for_correction(
        _artifact(),
        competition_status=_status('season_complete', 'postseason_scheduled_without_club'),
        team_inputs=_inputs(0, 19, stale_limited=19),
    )
    assert entry['proposed_action'] == ACTION_SUPERSEDE
    assert entry['reasons'] == [REASON_NOT_IN_COMPETITION, REASON_INACTIVITY_CONSTRAINT]
    assert entry['error_timing'] == 'incorrect_when_published'
    # Washington: all 19 idle arms re-count as clean, so even as a current
    # read it would have been Fresh, not Vulnerable.
    assert entry['correction']['corrected_public_state'] == 'fresh'


def test_active_club_whose_idle_arms_decided_the_state_is_superseded():
    # 2 clean + 4 idle-but-counted-moderate + 2 real watch arms: published
    # Vulnerable (margin floor); corrected 6 clean / 2 moderate is Fresh.
    entry = classify_artifact_for_correction(
        _artifact(), competition_status=_status('active'),
        team_inputs=_inputs(2, 6, stale_limited=4),
    )
    assert entry['proposed_action'] == ACTION_SUPERSEDE
    assert entry['reasons'] == [REASON_INACTIVITY_CONSTRAINT]
    assert entry['correction']['corrected_partition']['clean_count'] == 6
    assert entry['correction']['idle_arms_counted_as_constraint'] == [100, 101, 102, 103]


def test_a_read_that_stands_under_corrected_semantics_is_retained():
    entry = classify_artifact_for_correction(
        _artifact(state='vulnerable'), competition_status=_status('active'),
        team_inputs=_inputs(2, 6),
    )
    assert entry['proposed_action'] == ACTION_RETAIN


def test_missing_evidence_arms_move_to_unknown_not_clean():
    correction = corrected_team_state(_inputs(5, 3, missing_limited=2))
    assert correction['corrected_partition'] == {
        'clean_count': 5, 'moderate_count': 1, 'severe_count': 0, 'unknown_count': 2,
    }
    assert correction['missing_evidence_arms_counted_as_constraint'] == [200, 201]


def test_unsettled_evidence_goes_to_a_person():
    missing = classify_artifact_for_correction(
        _artifact(), competition_status=_status('active'), team_inputs=None,
    )
    assert missing['proposed_action'] == ACTION_REVIEW
    assert missing['reasons'] == [REASON_INPUTS_MISSING]

    undetermined = classify_artifact_for_correction(
        _artifact(), competition_status=_status('undetermined', 'competition_status_unresolved'),
        team_inputs=_inputs(2, 6),
    )
    assert undetermined['proposed_action'] == ACTION_REVIEW
    assert undetermined['reasons'] == [REASON_COMPETITION_UNDETERMINED]


def test_withdrawal_is_never_proposed():
    for status in ('active', 'season_complete', 'undetermined', None):
        for inputs in (None, _inputs(0, 8, stale_limited=8), _inputs(6, 2)):
            entry = classify_artifact_for_correction(
                _artifact(), competition_status=_status(status) if status else None,
                team_inputs=inputs,
            )
            assert entry['proposed_action'] in {ACTION_SUPERSEDE, ACTION_RETAIN, ACTION_REVIEW}


def test_manifest_is_deterministic_and_marked_dry_run():
    entries = [
        classify_artifact_for_correction(
            _artifact(team_id=100 + index, public_id=f'id{index:02d}'),
            competition_status=_status('season_complete'), team_inputs=None,
        )
        for index in range(12)
    ]
    shuffled = list(entries)
    random.Random(7).shuffle(shuffled)
    first = build_manifest(entries, scope={'source': 'test'})
    second = build_manifest(shuffled, scope={'source': 'test'})
    assert first == second
    assert first['mode'] == 'dry_run'
    assert first['execution_authorized'] is False
    assert first['action_counts'] == {ACTION_SUPERSEDE: 12}
    assert first['entries_digest'].startswith('sha256:')


def test_static_inventory_reads_only_team_state_pages(tmp_path):
    def page(public_id, kind, team, state, data_through):
        directory = tmp_path / public_id
        directory.mkdir()
        (directory / 'index.html').write_text(
            f'<meta name="baseballos:public-id" content="{public_id}" />'
            f'<meta name="baseballos:artifact-type" content="{kind}" />'
            f'<meta name="baseballos:team" content="{team}" />'
            f'<meta name="baseballos:team-state" content="{state}" />'
            f'<meta name="baseballos:data-through" content="{data_through}" />'
            '<meta name="baseballos:snapshot-id" content="5656" />'
        )

    page('a1', 'team_state', 'WSH', 'Vulnerable', '2026-10-27')
    page('b2', 'since_yesterday_change', 'MIL', '', '2026-10-27')
    entries = static_inventory_entries(tmp_path)
    assert [entry['public_id'] for entry in entries] == ['a1']
    assert entries[0]['published_public_state'] == 'vulnerable'
    assert entries[0]['proposed_action'] == ACTION_REVIEW
    assert entries[0]['reasons'] == ['requires_database_dry_run']


@pytest.fixture
def app():
    app = Flask(__name__)
    configure_test_database(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    with app.app_context():
        create_test_schema(app)
        try:
            yield app
        finally:
            db.session.remove()
            drop_test_schema(app)


def test_database_dry_run_classifies_without_touching_any_artifact(app):
    with app.app_context():
        run = SyncRun(status='success', stage='published', source='test')
        db.session.add(run)
        db.session.flush()
        snapshot = DashboardSnapshot(
            snapshot_type='bullpen_dashboard', sync_run_id=run.id, status='ready',
            is_published=True, published_at=datetime(2026, 10, 28, 10, 7),
            payload={}, payload_version=1, data_through=date(2026, 10, 27),
            availability_reference_date=date(2026, 10, 28),
            snapshot_generated_at=datetime(2026, 10, 28, 10, 0), source='test',
        )
        db.session.add(snapshot)
        db.session.flush()
        db.session.add(TeamStatePublicationProof(
            snapshot_id=snapshot.id, sync_run_id=run.id, data_through=date(2026, 10, 27),
            proof={'snapshot_team_state_generation_inputs': {
                '120': _inputs(0, 19, stale_limited=19),
                '158': _inputs(2, 6, stale_limited=4),
            }},
            overall_verdict='PASS', captured_team_count=30,
        ))
        # Washington's season ended 2026-09-27; Milwaukee plays tonight.
        for team, opponent, game_date, game_type, state in (
            (120, 121, date(2026, 9, 27), 'R', 'final'),
            (158, 139, date(2026, 10, 27), 'W', 'final'),
            (158, 139, date(2026, 10, 28), 'W', 'scheduled'),
            (139, 158, date(2026, 10, 28), 'W', 'scheduled'),
        ):
            db.session.add(ScheduledGame(
                team_id=team, opponent_team_id=opponent,
                game_pk=hash((team, game_date)) % 10_000_000,
                game_date=game_date, game_type=game_type, status_state=state,
                games_in_series=7 if game_type == 'W' else None, source='test',
            ))
        artifacts = []
        for team_id, public_id in ((120, 'wsh-1027'), (158, 'mil-1027')):
            artifact = ShareArtifact(
                public_id=public_id, artifact_type='team_state', render_version='team-state-1.2.0',
                team_id=team_id, source_snapshot_id=snapshot.id,
                product_date=date(2026, 10, 27), lifecycle_state='published',
                payload={'public_copy': {'state': {'public_code': 'vulnerable'}},
                         'team': {'team_abbreviation': 'WSH' if team_id == 120 else 'MIL'}},
                trust_metadata={}, equivalence_key=f'eq-{public_id}', source='test',
                published_at=datetime(2026, 10, 28, 10, 9),
            )
            db.session.add(artifact)
            artifacts.append(artifact)
        db.session.commit()
        before = [
            (a.public_id, a.lifecycle_state, a.payload, a.updated_at,
             a.superseded_at, a.withdrawn_at)
            for a in ShareArtifact.query.order_by(ShareArtifact.public_id).all()
        ]

        entries = load_manifest_entries(date(2026, 9, 28), date(2026, 10, 31))
        db.session.rollback()

        by_id = {entry['public_id']: entry for entry in entries}
        assert by_id['wsh-1027']['proposed_action'] == ACTION_SUPERSEDE
        assert by_id['wsh-1027']['competition_status']['status'] == 'season_complete'
        assert by_id['mil-1027']['competition_status']['status'] == 'active'
        assert by_id['mil-1027']['proposed_action'] == ACTION_SUPERSEDE
        assert by_id['mil-1027']['reasons'] == [REASON_INACTIVITY_CONSTRAINT]
        after = [
            (a.public_id, a.lifecycle_state, a.payload, a.updated_at,
             a.superseded_at, a.withdrawn_at)
            for a in ShareArtifact.query.order_by(ShareArtifact.public_id).all()
        ]
        assert after == before


def test_database_dry_run_is_read_only_at_the_database(app, tmp_path, monkeypatch):
    """The CLI's database mode runs end to end and PostgreSQL refuses any write."""
    import json as _json

    from sqlalchemy import text

    from scripts import build_team_state_correction_manifest as cli
    from services import team_state_correction_manifest as manifest_service
    from utils.db import db

    output = tmp_path / 'manifest.json'
    with app.app_context():
        dialect = db.engine.dialect.name
    assert cli.main(['--start', '2026-09-28', '--output', str(output)]) == 0
    manifest = _json.loads(output.read_text())
    assert manifest['mode'] == 'dry_run'
    assert manifest['execution_authorized'] is False
    assert manifest['scope']['source'] == 'database_dry_run'

    if dialect != 'postgresql':
        return
    attempted = {}

    def writing_loader(start, end):
        try:
            db.session.execute(text('CREATE TEMPORARY TABLE wp01_write_probe (id int)'))
        except Exception as error:  # noqa: BLE001 - the refusal is the point
            attempted['refused'] = 'read-only' in str(error).lower()
            raise
        attempted['refused'] = False
        return []

    monkeypatch.setattr(manifest_service, 'load_manifest_entries', writing_loader)
    with pytest.raises(Exception):
        cli.main(['--start', '2026-09-28', '--output', str(output)])
    assert attempted == {'refused': True}
