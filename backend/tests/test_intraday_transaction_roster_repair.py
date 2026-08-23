from datetime import date, datetime

import pytest
from flask import Flask
from sqlalchemy import event

import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401
from models.pitcher import Pitcher
from models.player_transaction import PlayerTransaction, PlayerTransactionSyncWindow
from models.roster_status_snapshot import RosterStatusSnapshot
from models.sync_run import SyncRun
from services.intraday_transaction_roster_repair import (
    CORRECTION_SOURCE,
    repair_current_window_transaction_roster_evidence,
    select_current_window_roster_repair_candidates,
)
from services.roster_status_sync import (
    ROSTER_TYPE_40_MAN,
    ROSTER_TYPE_ACTIVE,
    ROSTER_TYPE_FULL,
    ROSTER_TYPE_NON_ROSTER,
)
from utils.db import db
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema


DAY = date(2026, 8, 20)
START = date(2026, 8, 15)
END = date(2026, 8, 22)


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


class FakeRosterClient:
    def __init__(self, *, rosters=None, metadata=None, roster_error=None):
        self.rosters = rosters or {}
        self.metadata = metadata or {}
        self.roster_error = roster_error
        self.roster_calls = []
        self.metadata_calls = []

    def get_team_metadata(self, season):
        self.metadata_calls.append(season)
        return dict(self.metadata)

    def get_team_roster(self, team_id, roster_type='pitchers', date=None, **_kwargs):
        self.roster_calls.append((team_id, date, roster_type))
        if self.roster_error:
            raise self.roster_error
        return list(self.rosters.get((team_id, date, roster_type), ()))


def _pitcher(mlb_id=700101, *, team_id=999):
    row = Pitcher(
        mlb_id=mlb_id,
        full_name=f'Pitcher {mlb_id}',
        team_id=team_id,
        team_name='Mutable Current Team',
        team_abbreviation='MUT',
        active=True,
        position='P',
    )
    db.session.add(row)
    db.session.flush()
    return row


def _window(*, attempted_at=datetime(2026, 8, 22, 12, 0, 0)):
    row = PlayerTransactionSyncWindow(
        source='mlb_stats_api:transactions',
        source_endpoint='/transactions',
        source_query_start_date=START,
        source_query_end_date=END,
        attempted_at=attempted_at,
        successful_at=attempted_at,
        status='success',
        records_fetched=1,
        records_stored=1,
        created_at=attempted_at,
    )
    db.session.add(row)
    db.session.flush()
    return row


def _transaction(
    pitcher,
    *,
    transaction_id='938618',
    transaction_date=DAY,
    from_team_id=143,
    to_team_id=543,
    category='option',
    alignment='no_snapshot',
    reason='roster_snapshot_missing',
):
    row = PlayerTransaction(
        transaction_key=f'{transaction_id}:{pitcher.mlb_id}',
        transaction_id=transaction_id,
        pitcher_id=pitcher.id,
        player_mlb_id=pitcher.mlb_id,
        from_team_id=from_team_id,
        to_team_id=to_team_id,
        transaction_date=transaction_date,
        transaction_type_code='OPT',
        normalized_category=category,
        roster_snapshot_alignment=alignment,
        alignment_reason_code=reason,
        explanatory_linkage_eligible=False,
        participant_role='pitcher',
        participant_role_authority='canonical_pitcher',
        transaction_materiality='unresolved',
        subtype_status='unresolved',
        subtype_authority='unresolved',
        subtype_reason_code='legacy_unclassified',
        source='mlb_stats_api:transactions',
        source_endpoint='/transactions',
        source_query_start_date=START,
        source_query_end_date=END,
        first_seen_at=datetime(2026, 8, 20, 12, 0, 0),
        created_at=datetime(2026, 8, 20, 12, 0, 0),
        updated_at=datetime(2026, 8, 20, 12, 0, 0),
    )
    db.session.add(row)
    db.session.flush()
    return row


def _entry(mlb_id, *, status_code='A', status_description='Active'):
    return {
        'person': {'id': mlb_id, 'fullName': f'Pitcher {mlb_id}'},
        'position': {'code': '1', 'abbreviation': 'P', 'type': 'Pitcher'},
        'status': {
            'code': status_code,
            'description': status_description,
        },
    }


def _metadata(*team_ids):
    return {
        team_id: {'id': team_id, 'sport_id': 1, 'parent_org_id': team_id}
        for team_id in team_ids
    }


def test_current_window_missing_snapshot_is_selected_and_repaired(app):
    with app.app_context():
        pitcher = _pitcher(team_id=999)
        _window()
        transaction = _transaction(pitcher)
        sync_run = SyncRun(
            job_name='intraday_repair',
            status='running',
            source='test',
            started_at=datetime(2026, 8, 22, 13, 0, 0),
        )
        db.session.add(sync_run)
        db.session.flush()
        client = FakeRosterClient(
            metadata=_metadata(143),
            rosters={(143, DAY.isoformat(), ROSTER_TYPE_ACTIVE): [_entry(pitcher.mlb_id)]},
        )

        result = repair_current_window_transaction_roster_evidence(
            client=client,
            timestamp=datetime(2026, 8, 22, 13, 0, 0),
            sync_run_id=sync_run.id,
        )
        db.session.commit()
        db.session.refresh(transaction)
        snapshot = RosterStatusSnapshot.query.one()

        assert result['repair_candidates'] == 1
        assert result['team_date_pairs'] == 1
        assert result['roster_gets_attempted'] == 4
        assert result['source_matches'] == 1
        assert result['snapshots_created'] == 1
        assert result['transactions_corrected'] == 1
        assert result['transactions_still_blocked'] == 0
        assert snapshot.snapshot_date == DAY
        assert snapshot.team_id == 143
        assert transaction.roster_snapshot_alignment == 'aligned'
        assert transaction.alignment_reason_code == 'roster_snapshot_team_match'
        assert transaction.explanatory_linkage_eligible is True
        assert transaction.correction_source == CORRECTION_SOURCE
        assert pitcher.team_id == 999

        assert client.roster_calls == [
            (143, DAY.isoformat(), ROSTER_TYPE_ACTIVE),
            (143, DAY.isoformat(), ROSTER_TYPE_40_MAN),
            (143, DAY.isoformat(), ROSTER_TYPE_FULL),
            (143, DAY.isoformat(), ROSTER_TYPE_NON_ROSTER),
        ]


def test_requests_deduplicate_by_exact_team_and_date_and_retry_is_idempotent(app):
    with app.app_context():
        pitcher = _pitcher()
        _window()
        first = _transaction(pitcher, transaction_id='one')
        second = _transaction(pitcher, transaction_id='two')
        client = FakeRosterClient(
            metadata=_metadata(143),
            rosters={(143, DAY.isoformat(), ROSTER_TYPE_FULL): [_entry(pitcher.mlb_id)]},
        )
        selects = []

        def capture(_conn, _cursor, statement, _parameters, _context, _many):
            normalized = ' '.join(statement.lower().split())
            if normalized.startswith('select'):
                selects.append(normalized)

        event.listen(db.engine, 'before_cursor_execute', capture)
        try:
            result = repair_current_window_transaction_roster_evidence(client=client)
        finally:
            event.remove(db.engine, 'before_cursor_execute', capture)
        db.session.commit()
        repeated = repair_current_window_transaction_roster_evidence(client=client)

        assert result['repair_candidates'] == 2
        assert result['team_date_pairs'] == 1
        assert result['roster_gets_attempted'] == 4
        assert result['snapshots_created'] == 1
        assert result['transactions_corrected'] == 2
        assert len(selects) <= 8
        assert sum('from player_transactions' in value for value in selects) == 1
        assert sum('from roster_status_snapshots' in value for value in selects) == 3
        assert RosterStatusSnapshot.query.count() == 1
        assert first.roster_snapshot_alignment == 'aligned'
        assert second.roster_snapshot_alignment == 'aligned'
        assert repeated['repair_candidates'] == 0
        assert len(client.roster_calls) == 4


def test_source_omission_and_fetch_failure_fail_closed(app):
    with app.app_context():
        pitcher = _pitcher()
        _window()
        transaction = _transaction(pitcher)
        missing = repair_current_window_transaction_roster_evidence(
            client=FakeRosterClient(metadata=_metadata(143)),
        )
        assert missing['status'] == 'success'
        assert missing['source_misses'] == 1
        assert missing['transactions_corrected'] == 0
        assert transaction.roster_snapshot_alignment == 'no_snapshot'
        assert RosterStatusSnapshot.query.count() == 0

        failed = repair_current_window_transaction_roster_evidence(
            client=FakeRosterClient(
                metadata=_metadata(143), roster_error=RuntimeError('source unavailable')
            ),
        )
        assert failed['status'] == 'failed'
        assert failed['fetch_failures'] == 4
        assert RosterStatusSnapshot.query.count() == 0


def test_both_endpoint_matches_fail_closed(app):
    with app.app_context():
        pitcher = _pitcher()
        _window()
        transaction = _transaction(pitcher, from_team_id=143, to_team_id=144)
        entry = _entry(pitcher.mlb_id)
        client = FakeRosterClient(
            metadata=_metadata(143, 144),
            rosters={
                (143, DAY.isoformat(), ROSTER_TYPE_FULL): [entry],
                (144, DAY.isoformat(), ROSTER_TYPE_FULL): [entry],
            },
        )
        result = repair_current_window_transaction_roster_evidence(client=client)

        assert result['team_date_pairs'] == 2
        assert result['roster_gets_attempted'] == 8
        assert result['conflicts'] == 1
        assert result['snapshots_created'] == 0
        assert result['transactions_corrected'] == 0
        assert transaction.roster_snapshot_alignment == 'no_snapshot'


def test_wrong_team_existing_snapshot_unknown_event_and_old_window_are_excluded(app):
    with app.app_context():
        wrong_team_pitcher = _pitcher(700201)
        unknown_pitcher = _pitcher(700202)
        old_pitcher = _pitcher(700203)
        _window(attempted_at=datetime(2026, 8, 22, 12, 0, 0))
        wrong = _transaction(wrong_team_pitcher, transaction_id='wrong')
        unknown = _transaction(
            unknown_pitcher, transaction_id='unknown', category='unknown'
        )
        old = _transaction(old_pitcher, transaction_id='old')
        old.source_query_start_date = date(2026, 8, 8)
        old.source_query_end_date = date(2026, 8, 14)
        db.session.add(RosterStatusSnapshot(
            pitcher_id=wrong_team_pitcher.id,
            mlb_id=wrong_team_pitcher.mlb_id,
            team_id=121,
            snapshot_date=DAY,
            roster_status='ACTIVE',
            active_roster=True,
            forty_man_roster=True,
            source='mlb_stats_api:roster_sync:active',
            first_seen_at=datetime(2026, 8, 20, 12, 0, 0),
            created_at=datetime(2026, 8, 20, 12, 0, 0),
            updated_at=datetime(2026, 8, 20, 12, 0, 0),
        ))
        db.session.flush()

        _window(attempted_at=datetime(2026, 8, 22, 13, 0, 0))
        _latest, candidates, _pitchers = select_current_window_roster_repair_candidates()

        assert candidates == []
        assert wrong.roster_snapshot_alignment == 'no_snapshot'
        assert unknown.normalized_category == 'unknown'


def test_non_pitcher_unlinked_and_misaligned_rows_are_not_candidates(app):
    with app.app_context():
        pitcher = _pitcher()
        _window()
        non_pitcher = _transaction(pitcher, transaction_id='non-pitcher')
        non_pitcher.participant_role = 'non_pitcher'
        misaligned = _transaction(
            pitcher,
            transaction_id='misaligned',
            alignment='misaligned',
            reason='roster_snapshot_team_mismatch',
        )
        unlinked = _transaction(pitcher, transaction_id='unlinked')
        unlinked.pitcher_id = None
        db.session.flush()

        _latest, candidates, _pitchers = select_current_window_roster_repair_candidates()

        assert candidates == []
        assert non_pitcher.participant_role == 'non_pitcher'
        assert misaligned.alignment_reason_code == 'roster_snapshot_team_mismatch'
        assert unlinked.pitcher_id is None
