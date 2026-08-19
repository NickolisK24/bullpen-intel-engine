from datetime import date, datetime
from pathlib import Path

import pytest
from flask import Flask

from models.pitcher import Pitcher
from models.player_transaction import PlayerTransaction, PlayerTransactionSyncWindow
from services.public_recent_transactions import (
    POPULATION_BASIS,
    TRANSACTION_PUBLIC_LABELS,
    build_public_recent_transactions,
)
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    flask_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(flask_app)
    with flask_app.app_context():
        create_test_schema(flask_app)
        try:
            yield flask_app
        finally:
            db.session.remove()
            drop_test_schema(flask_app)


def _window(*, status='success', start=date(2026, 8, 11), end=date(2026, 8, 18)):
    row = PlayerTransactionSyncWindow(
        source='mlb_stats_api:transactions',
        source_endpoint='/transactions',
        source_query_start_date=start,
        source_query_end_date=end,
        attempted_at=datetime(2026, 8, 18, 12, 0, 0),
        successful_at=datetime(2026, 8, 18, 12, 0, 0) if status != 'failed' else None,
        status=status,
        records_fetched=2,
        records_stored=2,
        records_created=2,
        records_corrected=0,
        records_unchanged=0,
        unknown_type_count=0,
        alignment_unknown_count=0,
        alignment_misaligned_count=0,
        alignment_no_snapshot_count=0,
        records_failed=1 if status == 'partial' else 0,
        created_at=datetime(2026, 8, 18, 12, 0, 0),
    )
    db.session.add(row)
    db.session.flush()
    return row


def _pitcher(*, mlb_id, name, team_id=999):
    row = Pitcher(
        mlb_id=mlb_id,
        full_name=name,
        team_id=team_id,
        team_name=f'Team {team_id}',
        team_abbreviation=f'T{team_id}',
        active=True,
    )
    db.session.add(row)
    db.session.flush()
    return row


def _transaction(
    pitcher,
    *,
    transaction_id,
    transaction_date,
    category='recall',
    from_team_id=None,
    to_team_id=113,
    eligible=True,
):
    row = PlayerTransaction(
        transaction_key=f'key:{transaction_id}',
        transaction_id=transaction_id,
        pitcher_id=pitcher.id if pitcher else None,
        player_mlb_id=pitcher.mlb_id if pitcher else 799999,
        from_team_id=from_team_id,
        to_team_id=to_team_id,
        transaction_date=transaction_date,
        transaction_type_code=category.upper(),
        normalized_category=category,
        is_il_placement=category == 'il_placement',
        is_il_activation=category == 'il_activation',
        roster_snapshot_alignment='aligned' if eligible else 'unknown',
        explanatory_linkage_eligible=eligible,
        source='mlb_stats_api:transactions',
        source_endpoint='/transactions',
        source_query_start_date=date(2026, 8, 11),
        source_query_end_date=date(2026, 8, 18),
    )
    db.session.add(row)
    db.session.flush()
    return row


def test_projects_typed_team_events_in_newest_first_source_order(app):
    with app.app_context():
        _window()
        older = _pitcher(mlb_id=700001, name='Older Arm')
        newer = _pitcher(mlb_id=700002, name='Newer Arm')
        other = _pitcher(mlb_id=700003, name='Other Team Arm')
        _transaction(
            older,
            transaction_id='older',
            transaction_date=date(2026, 8, 15),
            category='option',
            from_team_id=113,
            to_team_id=555,
        )
        _transaction(
            newer,
            transaction_id='newer',
            transaction_date=date(2026, 8, 17),
            category='recall',
            to_team_id=113,
        )
        _transaction(
            other,
            transaction_id='other',
            transaction_date=date(2026, 8, 18),
            category='recall',
            to_team_id=114,
        )
        db.session.commit()

        payload = build_public_recent_transactions(113, reference_date=date(2026, 8, 18))

    assert payload['population_basis'] == POPULATION_BASIS
    assert payload['status'] == 'available'
    assert [event['event_id'] for event in payload['events']] == ['newer', 'older']
    assert [event['label'] for event in payload['events']] == ['Recalled', 'Optioned']
    assert payload['events'][0]['player_id'] == newer.id
    assert payload['events'][0]['player_mlb_id'] == newer.mlb_id
    assert set(payload['events'][0]) == {
        'event_id', 'player_id', 'player_mlb_id', 'player_name', 'date', 'type', 'label'
    }
    assert payload['window_start_date'] == '2026-08-11'
    assert payload['represented_date'] == '2026-08-18'


def test_event_team_comes_from_stored_transaction_not_current_pitcher_assignment(app):
    with app.app_context():
        _window()
        pitcher = _pitcher(mlb_id=700010, name='Moved Arm', team_id=999)
        _transaction(
            pitcher,
            transaction_id='team-at-event',
            transaction_date=date(2026, 8, 17),
            from_team_id=113,
            to_team_id=114,
            category='trade',
        )
        db.session.commit()

        selected = build_public_recent_transactions(113, reference_date=date(2026, 8, 18))
        current = build_public_recent_transactions(999, reference_date=date(2026, 8, 18))

    assert [event['event_id'] for event in selected['events']] == ['team-at-event']
    assert current['events'] == []


def test_unverified_identity_or_type_is_withheld_and_section_is_partial(app):
    with app.app_context():
        _window()
        pitcher = _pitcher(mlb_id=700020, name='Verified Arm')
        _transaction(
            pitcher,
            transaction_id='verified',
            transaction_date=date(2026, 8, 17),
        )
        _transaction(
            None,
            transaction_id='unresolved',
            transaction_date=date(2026, 8, 16),
            category='unknown',
            eligible=False,
        )
        db.session.commit()

        payload = build_public_recent_transactions(113, reference_date=date(2026, 8, 18))

    assert payload['status'] == 'partial'
    assert [event['event_id'] for event in payload['events']] == ['verified']
    assert len(payload['limitations']) == 1
    assert 'withheld' in payload['limitations'][0]


def test_successful_empty_window_is_distinct_from_missing_failed_and_stale_authority(app):
    with app.app_context():
        _window()
        db.session.commit()
        empty = build_public_recent_transactions(113, reference_date=date(2026, 8, 18))

        PlayerTransactionSyncWindow.query.delete()
        db.session.commit()
        missing = build_public_recent_transactions(113, reference_date=date(2026, 8, 18))

        _window(status='failed')
        db.session.commit()
        failed = build_public_recent_transactions(113, reference_date=date(2026, 8, 18))

        PlayerTransactionSyncWindow.query.delete()
        _window(start=date(2026, 8, 1), end=date(2026, 8, 8))
        db.session.commit()
        stale = build_public_recent_transactions(113, reference_date=date(2026, 8, 18))

    assert empty['status'] == 'available' and empty['events'] == []
    assert missing['status'] == 'unavailable'
    assert failed['status'] == 'unavailable'
    assert stale['status'] == 'unavailable'
    assert 'recently' in stale['limitations'][0]


def test_public_vocabulary_is_exactly_the_existing_typed_categories():
    assert TRANSACTION_PUBLIC_LABELS == {
        'recall': 'Recalled',
        'option': 'Optioned',
        'il_placement': 'Placed on injured list',
        'il_activation': 'Activated from injured list',
        'roster_activation': 'Activated',
        'roster_deactivation': 'Deactivated',
        'trade': 'Traded',
        'dfa': 'Designated for assignment',
        'outright': 'Outrighted',
        'release': 'Released',
        'contract_selection': 'Contract selected',
        'suspension': 'Suspended',
        'bereavement': 'Placed on bereavement list',
        'paternity': 'Placed on paternity list',
        'restricted': 'Placed on restricted list',
    }


def test_projection_is_read_only_and_contains_no_change_or_impact_engine():
    source = Path(__file__).resolve().parents[1] / 'services' / 'public_recent_transactions.py'
    text = source.read_text(encoding='utf-8')

    for forbidden in (
        'db.session', '.commit(', '.add(', '.delete(', 'previous_roster',
        'team_state', 'role_change', 'impact_score', 'manager_intent',
    ):
        assert forbidden not in text
