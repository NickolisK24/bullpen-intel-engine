from datetime import date, datetime
from pathlib import Path

import pytest
from flask import Flask
from sqlalchemy import event

from models.pitcher import Pitcher
from models.player_transaction import PlayerTransaction, PlayerTransactionSyncWindow
from services.public_recent_transactions import (
    POPULATION_BASIS,
    TRANSACTION_PUBLIC_DESCRIPTIONS,
    TRANSACTION_PUBLIC_LABELS,
    build_public_recent_transactions,
)
from services.transaction_rehab_assignment import AUTHORITY as REHAB_AUTHORITY
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
    transaction_type_code=None,
    from_team_id=None,
    to_team_id=113,
    eligible=True,
    participant_role='unresolved',
    participant_role_authority='unresolved',
    participant_position_code=None,
    participant_position_abbreviation=None,
    participant_position_type=None,
    transaction_subtype=None,
    transaction_materiality='unresolved',
    subtype_status='unresolved',
    subtype_authority='unresolved',
    subtype_reason_code='legacy_unclassified',
    subtype_evidence=None,
):
    row = PlayerTransaction(
        transaction_key=f'key:{transaction_id}',
        transaction_id=transaction_id,
        pitcher_id=pitcher.id if pitcher else None,
        player_mlb_id=pitcher.mlb_id if pitcher else 799999,
        from_team_id=from_team_id,
        to_team_id=to_team_id,
        transaction_date=transaction_date,
        transaction_type_code=transaction_type_code or category.upper(),
        normalized_category=category,
        is_il_placement=category == 'il_placement',
        is_il_activation=category == 'il_activation',
        roster_snapshot_alignment='aligned' if eligible else 'unknown',
        explanatory_linkage_eligible=eligible,
        participant_role=participant_role,
        participant_role_authority=participant_role_authority,
        participant_position_code=participant_position_code,
        participant_position_abbreviation=participant_position_abbreviation,
        participant_position_type=participant_position_type,
        transaction_subtype=transaction_subtype,
        transaction_materiality=transaction_materiality,
        subtype_status=subtype_status,
        subtype_authority=subtype_authority,
        subtype_reason_code=subtype_reason_code,
        subtype_evidence=subtype_evidence,
        source='mlb_stats_api:transactions',
        source_endpoint='/transactions',
        source_query_start_date=date(2026, 8, 11),
        source_query_end_date=date(2026, 8, 18),
    )
    db.session.add(row)
    db.session.flush()
    return row


def _certified_rehab_fields(pitcher, *, event_date, from_team_id=113, to_team_id=555):
    return {
        'category': 'unknown',
        'transaction_type_code': 'ASG',
        'eligible': False,
        'participant_role': 'pitcher',
        'participant_role_authority': 'canonical_pitcher_identity_v1',
        'transaction_subtype': 'rehab_assignment',
        'transaction_materiality': 'non_material',
        'subtype_status': 'certified',
        'subtype_authority': REHAB_AUTHORITY,
        'subtype_reason_code': 'certified_rehab_assignment',
        'subtype_evidence': {
            'authority': REHAB_AUTHORITY,
            'transaction_type_code': 'ASG',
            'pitcher_id': pitcher.id,
            'player_mlb_id': pitcher.mlb_id,
            'participant_role': 'pitcher',
            'from_team_id': from_team_id,
            'to_team_id': to_team_id,
            'destination_team_id': to_team_id,
            'destination_sport_id': 11,
            'destination_parent_org_id': from_team_id,
            'metadata_season': event_date.year,
            'roster_snapshot_id': 99,
            'roster_snapshot_date': event_date.isoformat(),
            'roster_team_id': from_team_id,
            'roster_status': 'IL_15',
            'active_roster': False,
        },
    }


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
    assert [event['description'] for event in payload['events']] == [
        'Newer Arm was recalled.',
        'Older Arm was optioned.',
    ]
    assert payload['events'][0]['player_id'] == newer.id
    assert payload['events'][0]['player_mlb_id'] == newer.mlb_id
    assert set(payload['events'][0]) == {
        'event_id', 'player_id', 'player_mlb_id', 'player_name', 'date', 'type',
        'label', 'description'
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


def test_reference_date_bounds_public_chronology_without_rewriting_source_window(app):
    with app.app_context():
        _window()
        pitcher = _pitcher(mlb_id=700012, name='Reference Date Arm')
        _transaction(
            pitcher,
            transaction_id='represented-date',
            transaction_date=date(2026, 8, 17),
        )
        _transaction(
            pitcher,
            transaction_id='future-to-board',
            transaction_date=date(2026, 8, 18),
        )
        db.session.commit()

        payload = build_public_recent_transactions(
            113,
            reference_date=date(2026, 8, 17),
        )

    assert [event['event_id'] for event in payload['events']] == ['represented-date']
    assert payload['window_start_date'] == '2026-08-11'
    assert payload['window_end_date'] == '2026-08-17'
    assert payload['represented_date'] == '2026-08-17'


def test_reference_date_before_latest_source_window_fails_closed(app):
    with app.app_context():
        _window()
        db.session.commit()

        payload = build_public_recent_transactions(
            113,
            reference_date=date(2026, 8, 10),
        )

    assert payload['status'] == 'unavailable'
    assert payload['events'] == []
    assert payload['represented_date'] == '2026-08-10'
    assert 'do not cover' in payload['limitations'][0]


@pytest.mark.parametrize(
    ('category', 'label', 'description'),
    (
        ('recall', 'Recalled', 'Typed Arm was recalled.'),
        ('dfa', 'Designated for assignment', 'Typed Arm was designated for assignment.'),
        ('contract_selection', 'Contract selected', "Typed Arm's contract was selected."),
        ('il_placement', 'Placed on injured list', 'Typed Arm was placed on the injured list.'),
        ('il_activation', 'Activated from injured list', 'Typed Arm was activated from the injured list.'),
    ),
)
def test_structured_categories_author_reader_descriptions(app, category, label, description):
    with app.app_context():
        _window()
        pitcher = _pitcher(mlb_id=700011, name='Typed Arm')
        _transaction(
            pitcher,
            transaction_id=f'typed-{category}',
            transaction_date=date(2026, 8, 17),
            category=category,
        )
        db.session.commit()

        payload = build_public_recent_transactions(113, reference_date=date(2026, 8, 18))

    assert payload['status'] == 'available'
    assert payload['events'][0]['label'] == label
    assert payload['events'][0]['description'] == description


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


def test_proven_non_pitcher_is_excluded_from_completeness_without_public_noise(app):
    with app.app_context():
        _window()
        pitcher = _pitcher(mlb_id=700021, name='Verified Arm')
        _transaction(
            pitcher,
            transaction_id='verified',
            transaction_date=date(2026, 8, 17),
        )
        _transaction(
            None,
            transaction_id='position-player',
            transaction_date=date(2026, 8, 16),
            category='unknown',
            eligible=False,
            participant_role='non_pitcher',
            participant_role_authority='mlb_people_primary_position_v1',
            participant_position_code='6',
            participant_position_abbreviation='SS',
            participant_position_type='Infielder',
        )
        db.session.commit()

        payload = build_public_recent_transactions(113, reference_date=date(2026, 8, 18))

    assert payload['status'] == 'available'
    assert [event['event_id'] for event in payload['events']] == ['verified']
    assert payload['limitations'] == []
    assert 'participant_role' not in payload


def test_certified_non_material_rehab_is_excluded_without_public_noise(app):
    with app.app_context():
        _window()
        verified = _pitcher(mlb_id=700030, name='Verified Arm')
        rehab = _pitcher(mlb_id=700031, name='Rehab Arm')
        _transaction(
            verified,
            transaction_id='verified',
            transaction_date=date(2026, 8, 17),
        )
        event_date = date(2026, 8, 16)
        _transaction(
            rehab,
            transaction_id='certified-rehab',
            transaction_date=event_date,
            from_team_id=113,
            to_team_id=555,
            **_certified_rehab_fields(rehab, event_date=event_date),
        )
        db.session.commit()

        payload = build_public_recent_transactions(113, reference_date=date(2026, 8, 18))

    assert payload['status'] == 'available'
    assert [event['event_id'] for event in payload['events']] == ['verified']
    assert payload['limitations'] == []
    assert set(payload) == {
        'capability', 'version', 'population_basis', 'status', 'events',
        'window_start_date', 'window_end_date', 'represented_date', 'limitations',
    }


def test_uncertified_or_tampered_asg_remains_blocking(app):
    with app.app_context():
        _window()
        pitcher = _pitcher(mlb_id=700032, name='Ambiguous Assignment')
        event_date = date(2026, 8, 16)
        fields = _certified_rehab_fields(pitcher, event_date=event_date)
        fields['subtype_evidence']['destination_parent_org_id'] = 114
        _transaction(
            pitcher,
            transaction_id='tampered-rehab',
            transaction_date=event_date,
            from_team_id=113,
            to_team_id=555,
            **fields,
        )
        db.session.commit()

        payload = build_public_recent_transactions(113, reference_date=date(2026, 8, 18))

    assert payload['status'] == 'partial'
    assert payload['events'] == []
    assert 'withheld' in payload['limitations'][0]


def test_participant_qualification_adds_no_public_reader_query(app):
    with app.app_context():
        _window()
        pitcher = _pitcher(mlb_id=700022, name='Verified Arm')
        _transaction(
            pitcher,
            transaction_id='verified',
            transaction_date=date(2026, 8, 17),
        )
        _transaction(
            None,
            transaction_id='position-player-one',
            transaction_date=date(2026, 8, 16),
            eligible=False,
            participant_role='non_pitcher',
            participant_role_authority='mlb_people_primary_position_v1',
            participant_position_code='6',
        )
        _transaction(
            None,
            transaction_id='position-player-two',
            transaction_date=date(2026, 8, 15),
            eligible=False,
            participant_role='non_pitcher',
            participant_role_authority='mlb_people_primary_position_v1',
            participant_position_code='8',
        )
        rehab = _pitcher(mlb_id=700023, name='Rehab Arm')
        event_date = date(2026, 8, 14)
        _transaction(
            rehab,
            transaction_id='certified-rehab',
            transaction_date=event_date,
            from_team_id=113,
            to_team_id=555,
            **_certified_rehab_fields(rehab, event_date=event_date),
        )
        db.session.commit()
        statements = []

        def capture(_conn, _cursor, statement, _parameters, _context, _executemany):
            if statement.lstrip().upper().startswith('SELECT'):
                statements.append(statement)

        event.listen(db.engine, 'before_cursor_execute', capture)
        try:
            payload = build_public_recent_transactions(113, reference_date=date(2026, 8, 18))
        finally:
            event.remove(db.engine, 'before_cursor_execute', capture)

    assert payload['status'] == 'available'
    assert [event_row['event_id'] for event_row in payload['events']] == ['verified']
    assert len(statements) == 3  # latest window, team transactions, canonical pitchers


@pytest.mark.parametrize(
    ('authority', 'code', 'abbreviation', 'position_type'),
    (
        ('unresolved', '6', 'SS', 'Infielder'),
        ('mlb_people_primary_position_v1', None, None, None),
        ('mlb_people_primary_position_v1', 'Y', 'TWP', 'Two-Way Player'),
    ),
)
def test_non_pitcher_stamp_must_carry_compatible_explicit_authority(
    app, authority, code, abbreviation, position_type
):
    with app.app_context():
        _window()
        _transaction(
            None,
            transaction_id='not-proven-irrelevant',
            transaction_date=date(2026, 8, 16),
            eligible=False,
            participant_role='non_pitcher',
            participant_role_authority=authority,
            participant_position_code=code,
            participant_position_abbreviation=abbreviation,
            participant_position_type=position_type,
        )
        db.session.commit()

        payload = build_public_recent_transactions(113, reference_date=date(2026, 8, 18))

    assert payload['status'] == 'partial'
    assert payload['events'] == []


def test_proven_pitcher_without_canonical_linkage_still_downgrades(app):
    with app.app_context():
        _window()
        _transaction(
            None,
            transaction_id='unlinked-pitcher',
            transaction_date=date(2026, 8, 16),
            eligible=False,
            participant_role='pitcher',
            participant_role_authority='mlb_people_primary_position_v1',
            participant_position_code='1',
            participant_position_abbreviation='P',
            participant_position_type='Pitcher',
        )
        db.session.commit()

        payload = build_public_recent_transactions(113, reference_date=date(2026, 8, 18))

    assert payload['status'] == 'partial'
    assert payload['events'] == []


def test_partial_source_window_remains_partial_when_failed_row_cannot_be_team_scoped(app):
    with app.app_context():
        _window(status='partial')
        db.session.commit()

        payload = build_public_recent_transactions(113, reference_date=date(2026, 8, 18))

    assert payload['status'] == 'partial'
    assert payload['events'] == []
    assert payload['limitations'] == [
        'Some records from the latest transaction source window are unavailable.'
    ]


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
    assert set(TRANSACTION_PUBLIC_DESCRIPTIONS) == set(TRANSACTION_PUBLIC_LABELS)


def test_projection_is_read_only_and_contains_no_change_or_impact_engine():
    source = Path(__file__).resolve().parents[1] / 'services' / 'public_recent_transactions.py'
    text = source.read_text(encoding='utf-8')

    for forbidden in (
        'db.session', '.commit(', '.add(', '.delete(', 'previous_roster',
        'team_state', 'role_change', 'impact_score', 'manager_intent',
    ):
        assert forbidden not in text
