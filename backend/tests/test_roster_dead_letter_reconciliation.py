"""
Evidence-backed reconciliation of roster dead letters.

Public roster readiness fails closed on ANY unresolved roster dead letter
(reason code ``dead_letters_unresolved``). These tests prove that a dead
letter is resolved only when newer authoritative official roster evidence
conclusively supersedes the same entity's conflict — and that genuine or
ambiguous conflicts keep failing closed with no null/zero substitution.
"""

from datetime import date, datetime

import pytest
from flask import Flask
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401
from models.pitcher import Pitcher
from models.roster_status_snapshot import RosterStatusSnapshot
from models.sync_failure import SyncFailure
from models.sync_run import SyncRun
from services.public_roster_readiness import (
    apply_public_roster_readiness,
    build_public_roster_readiness,
)
from services.roster_status_sync import (
    ROSTER_STATUS_CONFLICT_ENTITY_TYPE,
    ROSTER_STATUS_IDENTITY_ENTITY_TYPE,
    ROSTER_TYPE_40_MAN,
    ROSTER_TYPE_ACTIVE,
    ROSTER_TYPE_FULL,
    ROSTER_TYPE_NON_ROSTER,
    sync_roster_statuses,
)
from utils.db import db


SNAPSHOT_DAY = date(2026, 7, 13)
SYNC_TIME = datetime(2026, 7, 13, 10, 55, 0)
EARLIER = datetime(2026, 7, 12, 10, 55, 0)


class FakeRosterClient:
    def __init__(self, rosters):
        self.rosters = rosters

    def get_team_roster(self, team_id, roster_type='pitchers', **_kwargs):
        value = self.rosters.get((team_id, roster_type), [])
        if isinstance(value, Exception):
            raise value
        return list(value)


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


def _sync_run():
    run = SyncRun(
        job_name='daily_sync',
        status='running',
        stage='roster_status',
        source='github_actions',
        started_at=SYNC_TIME,
    )
    db.session.add(run)
    db.session.commit()
    return run


def _pitcher(mlb_id, *, team_id=113, name=None):
    pitcher = Pitcher(
        mlb_id=mlb_id,
        full_name=name or f'Reconciled Arm {mlb_id}',
        team_id=team_id,
        team_name=f'Team {team_id}',
        team_abbreviation=f'T{team_id}',
        position='P',
        active=True,
    )
    db.session.add(pitcher)
    db.session.commit()
    return pitcher


def _roster_entry(mlb_id, name):
    return {
        'person': {'id': mlb_id, 'fullName': name},
        'position': {'abbreviation': 'P'},
    }


def _clean_feed(team_id, pitchers):
    rosters = {
        (team_id, ROSTER_TYPE_ACTIVE): [
            _roster_entry(p.mlb_id, p.full_name) for p in pitchers
        ],
        (team_id, ROSTER_TYPE_40_MAN): [],
        (team_id, ROSTER_TYPE_FULL): [],
        (team_id, ROSTER_TYPE_NON_ROSTER): [],
    }
    return rosters


def _conflict_dead_letter(mlb_id, *, snapshot_date='2026-07-12', created_at=EARLIER):
    failure = SyncFailure(
        job_name='daily_sync',
        entity_type=ROSTER_STATUS_CONFLICT_ENTITY_TYPE,
        entity_ref=str(mlb_id),
        payload={
            'mlb_id': mlb_id,
            'snapshot_date': snapshot_date,
            'existing_team_id': 999,
            'incoming_team_id': 113,
        },
        error='Roster snapshot team conflict for same pitcher/date',
        created_at=created_at,
        resolved=False,
    )
    db.session.add(failure)
    db.session.commit()
    return failure


def _identity_dead_letter(team_id, *, created_at=EARLIER):
    failure = SyncFailure(
        job_name='daily_sync',
        entity_type=ROSTER_STATUS_IDENTITY_ENTITY_TYPE,
        entity_ref=str(team_id),
        payload={
            'reason': 'missing_player_identity',
            'team_id': team_id,
            'roster_type': ROSTER_TYPE_ACTIVE,
        },
        error='Roster entry missing player identity',
        created_at=created_at,
        resolved=False,
    )
    db.session.add(failure)
    db.session.commit()
    return failure


def _run_sync(rosters, *, team_ids, run):
    return sync_roster_statuses(
        team_ids=team_ids,
        client=FakeRosterClient(rosters),
        timestamp=SYNC_TIME,
        sync_run_id=run.id,
        snapshot_date=SNAPSHOT_DAY,
    )


def _readiness(team_id=113):
    return build_public_roster_readiness(
        reference_date=SNAPSHOT_DAY,
        team_id=team_id,
        scope='team',
    )


def test_newer_official_evidence_resolves_matching_conflict(app):
    with app.app_context():
        run = _sync_run()
        pitcher = _pitcher(700001)
        failure = _conflict_dead_letter(pitcher.mlb_id)
        failure_id = failure.id

        result = _run_sync(_clean_feed(113, [pitcher]), team_ids=[113], run=run)
        db.session.commit()

        row = db.session.get(SyncFailure, failure_id)
        readiness = _readiness()

    assert result['dead_letters_resolved']['conflict'] == 1
    # Audit history preserved: same row, resolved flags only.
    assert row is not None
    assert row.resolved is True
    assert row.resolved_at is not None
    assert row.error == 'Roster snapshot team conflict for same pitcher/date'
    # Readiness restored by evidence, not by clearing.
    assert readiness['readiness_state'] == 'ready'
    assert readiness['claims_available'] is True
    assert readiness['counts_withheld'] is False
    assert readiness['reason_codes'] == []


def test_unrelated_evidence_does_not_resolve_conflict(app):
    with app.app_context():
        run = _sync_run()
        synced = _pitcher(700001, team_id=113)
        other = _pitcher(700002, team_id=114)
        failure = _conflict_dead_letter(other.mlb_id)
        failure_id = failure.id

        # Only team 113 is synced; the conflict belongs to team 114's pitcher.
        _run_sync(_clean_feed(113, [synced]), team_ids=[113], run=run)
        db.session.commit()

        row = db.session.get(SyncFailure, failure_id)
        readiness = _readiness()
        withheld_authority = apply_public_roster_readiness(
            {'counts': {'bullpen_arms': 5, 'available_count': 3}},
            readiness,
        )

    assert row.resolved is False
    assert readiness['claims_available'] is False
    assert readiness['counts_withheld'] is True
    assert 'dead_letters_unresolved' in readiness['reason_codes']
    # No null-to-zero substitution: withheld counts are None, never 0.
    assert withheld_authority['counts']['bullpen_arms'] is None
    assert withheld_authority['counts']['available_count'] is None


def test_ambiguous_conflict_stays_unresolved_and_withheld(app):
    with app.app_context():
        run = _sync_run()
        pitcher = _pitcher(700001, team_id=113)
        prior = _conflict_dead_letter(pitcher.mlb_id)
        prior_id = prior.id
        # Same pitcher/date snapshot already exists under a DIFFERENT team:
        # this run's upsert conflicts again — the ambiguity is live.
        db.session.add(RosterStatusSnapshot(
            pitcher_id=pitcher.id,
            mlb_id=pitcher.mlb_id,
            team_id=999,
            snapshot_date=SNAPSHOT_DAY,
            roster_status='ACTIVE',
            active_roster=True,
            forty_man_roster=True,
            source='mlb_stats_api:roster_sync:active',
            sync_run_id=run.id,
            first_seen_at=EARLIER,
            updated_at=EARLIER,
        ))
        db.session.commit()

        result = _run_sync(_clean_feed(113, [pitcher]), team_ids=[113], run=run)
        db.session.commit()

        prior_row = db.session.get(SyncFailure, prior_id)
        unresolved = SyncFailure.query.filter_by(
            entity_type=ROSTER_STATUS_CONFLICT_ENTITY_TYPE,
            resolved=False,
        ).count()
        readiness = _readiness()

    assert result['snapshot_conflicts'] == 1
    assert result['dead_letters_resolved']['conflict'] == 0
    assert prior_row.resolved is False
    assert unresolved == 2  # the historical row plus this run's fresh evidence
    assert readiness['claims_available'] is False
    assert 'dead_letters_unresolved' in readiness['reason_codes']


def test_reconciliation_is_idempotent(app):
    with app.app_context():
        run = _sync_run()
        pitcher = _pitcher(700001)
        failure = _conflict_dead_letter(pitcher.mlb_id)
        failure_id = failure.id

        _run_sync(_clean_feed(113, [pitcher]), team_ids=[113], run=run)
        db.session.commit()
        first_resolved_at = db.session.get(SyncFailure, failure_id).resolved_at

        second = _run_sync(_clean_feed(113, [pitcher]), team_ids=[113], run=run)
        db.session.commit()

        row = db.session.get(SyncFailure, failure_id)
        total_rows = SyncFailure.query.count()

    assert second['dead_letters_resolved']['conflict'] == 0
    assert row.resolved is True
    assert row.resolved_at == first_resolved_at
    assert total_rows == 1


def test_duplicate_rows_resolve_together_for_same_entity(app):
    with app.app_context():
        run = _sync_run()
        pitcher = _pitcher(700001)
        first = _conflict_dead_letter(pitcher.mlb_id, created_at=datetime(2026, 7, 10, 10, 0))
        second = _conflict_dead_letter(pitcher.mlb_id, created_at=EARLIER)
        ids = (first.id, second.id)

        result = _run_sync(_clean_feed(113, [pitcher]), team_ids=[113], run=run)
        db.session.commit()

        rows = [db.session.get(SyncFailure, row_id) for row_id in ids]
        readiness = _readiness()

    assert result['dead_letters_resolved']['conflict'] == 2
    assert all(row.resolved for row in rows)
    assert all(row.resolved_at is not None for row in rows)
    assert readiness['claims_available'] is True


def test_clean_team_parse_resolves_historical_identity_failure(app):
    with app.app_context():
        run = _sync_run()
        pitcher = _pitcher(700001)
        failure = _identity_dead_letter(113)
        failure_id = failure.id

        result = _run_sync(_clean_feed(113, [pitcher]), team_ids=[113], run=run)
        db.session.commit()

        row = db.session.get(SyncFailure, failure_id)
        readiness = _readiness()

    assert result['dead_letters_resolved']['identity'] == 1
    assert row.resolved is True
    assert readiness['claims_available'] is True


def test_recurring_identity_failure_blocks_resolution(app):
    with app.app_context():
        run = _sync_run()
        pitcher = _pitcher(700001)
        failure = _identity_dead_letter(113)
        failure_id = failure.id

        rosters = _clean_feed(113, [pitcher])
        rosters[(113, ROSTER_TYPE_ACTIVE)] = list(rosters[(113, ROSTER_TYPE_ACTIVE)]) + [
            {'person': {'fullName': 'Entry Without Identity'}, 'position': {'abbreviation': 'P'}},
        ]
        result = _run_sync(rosters, team_ids=[113], run=run)
        db.session.commit()

        row = db.session.get(SyncFailure, failure_id)
        unresolved = SyncFailure.query.filter_by(
            entity_type=ROSTER_STATUS_IDENTITY_ENTITY_TYPE,
            resolved=False,
        ).count()
        readiness = _readiness()

    assert result['dead_letters_resolved']['identity'] == 0
    assert row.resolved is False
    assert unresolved == 2  # historical row plus this run's fresh evidence
    assert readiness['claims_available'] is False


def test_remaining_genuine_conflict_keeps_league_gate_closed_for_clean_teams(app):
    with app.app_context():
        run = _sync_run()
        clean_pitcher = _pitcher(700001, team_id=113)
        conflicted = _pitcher(700002, team_id=114)
        resolved_failure = _conflict_dead_letter(clean_pitcher.mlb_id)
        genuine_failure = _conflict_dead_letter(conflicted.mlb_id)
        resolved_id = resolved_failure.id
        genuine_id = genuine_failure.id
        # Team 114's pitcher still carries a live same-day conflict.
        db.session.add(RosterStatusSnapshot(
            pitcher_id=conflicted.id,
            mlb_id=conflicted.mlb_id,
            team_id=999,
            snapshot_date=SNAPSHOT_DAY,
            roster_status='ACTIVE',
            active_roster=True,
            forty_man_roster=True,
            source='mlb_stats_api:roster_sync:active',
            sync_run_id=run.id,
            first_seen_at=EARLIER,
            updated_at=EARLIER,
        ))
        db.session.commit()

        rosters = _clean_feed(113, [clean_pitcher])
        rosters.update(_clean_feed(114, [conflicted]))
        result = _run_sync(rosters, team_ids=[113, 114], run=run)
        db.session.commit()

        resolved_row = db.session.get(SyncFailure, resolved_id)
        genuine_row = db.session.get(SyncFailure, genuine_id)
        team_113 = _readiness(team_id=113)
        team_114 = _readiness(team_id=114)

    # Only the safely reconciled conflict resolves; the genuine one is kept.
    assert result['dead_letters_resolved']['conflict'] == 1
    assert resolved_row.resolved is True
    assert genuine_row.resolved is False
    # The readiness gate is league-wide: a genuine unresolved conflict keeps
    # claims withheld even for teams whose own conflicts were reconciled.
    assert team_113['coverage']['team_covered'] is True
    assert team_113['claims_available'] is False
    assert team_114['claims_available'] is False
    assert 'dead_letters_unresolved' in team_113['reason_codes']
