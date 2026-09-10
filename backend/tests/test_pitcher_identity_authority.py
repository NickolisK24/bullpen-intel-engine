"""Foundation 3C — completed-game evidence is not current-roster authority.

Production R2 reconciled 946 appearance rows to zero GameLog mutations and
reported PASS. The same report carried 942 pitcher-identity actions — 940
metadata updates and 2 reactivations across 423 pitchers — attached to rows
whose GameLog action was `unchanged`. Write mode would have applied every one
of them. The fingerprint did not cover them and the update manifest was empty.

These tests pin the repair (D-009): a completed game establishes WHO appeared
and the historical context of that appearance, and nothing about the person's
current situation. An existing Pitcher row is never modified from this path.
A missing one may be created minimally, claiming no current state.
"""

from datetime import date, datetime

import pytest
from flask import Flask

from tests.db_config import (
    configure_test_database, create_test_schema, drop_test_schema,
)

import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401
from models.game_ingestion_work_item import GameIngestionWorkItem
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.postgame_processed_game import PostgameProcessedGame
from models.scheduled_game import ScheduledGame
from models.sync_failure import SyncFailure
from services import appearance_team_authority
from services import game_driven_ingestion
from services import game_log_reconciliation as reconciliation
from services import pitcher_identity_reconciliation as identity
from services import sync as sync_service
from services.roster_status import STATUS_ACTIVE, STATUS_IL_15, STATUS_MINORS, STATUS_UNKNOWN
from tests.game_driven_fixtures import (
    AWAY_TEAM,
    HOME_TEAM,
    REFERENCE,
    BoxscoreClient,
    boxscore,
    final_game,
    pitcher as _pitcher,
    pitching_stats,
    schedule_final_game as _schedule,
)
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


def _stored_row(pitcher_row, game_pk, **overrides):
    values = {
        'pitcher_id': pitcher_row.id,
        'mlb_game_pk': game_pk,
        'game_date': REFERENCE,
        'game_type': 'R',
        'opponent': 'Away Club',
        'opponent_abbreviation': 'AWY',
        'games_started': 0,
        'innings_pitched': 1.0,
        'innings_pitched_outs': 3,
        'pitches_thrown': 15,
        'strikes': 10,
        'hits_allowed': 1,
        'runs_allowed': 0,
        'earned_runs': 0,
        'walks': 0,
        'strikeouts': 2,
        'home_runs_allowed': 0,
        'batters_faced': 4,
        'appearance_team_id': HOME_TEAM,
        'appearance_team_source': appearance_team_authority.SOURCE_BOXSCORE,
        'appearance_team_status': GameLog.APPEARANCE_TEAM_RESOLVED,
        'appearance_team_reason': (
            appearance_team_authority.REASON_RESOLVED_BOXSCORE
        ),
        'stat_correction_count': 0,
    }
    values.update(overrides)
    row = GameLog(**values)
    db.session.add(row)
    return row


def _plan_game(game_pk):
    """The canonical plan, read-only, exactly as shadow obtains it."""
    result = sync_service.process_completed_game_for_postgame_refresh(
        final_game(game_pk), schedule_date=REFERENCE, plan_only=True,
    )
    return result['reconciliation_plan'], result['reconciliation_summary']


def _write_game(game_pk):
    result = sync_service.process_completed_game_for_postgame_refresh(
        final_game(game_pk), schedule_date=REFERENCE, force=True,
    )
    db.session.commit()
    return result['reconciliation_plan'], result['reconciliation_summary']


def _pitcher_state(mlb_id):
    row = Pitcher.query.filter_by(mlb_id=mlb_id).one()
    return {
        'active': row.active,
        'full_name': row.full_name,
        'position': row.position,
        'team_id': row.team_id,
        'team_name': row.team_name,
        'team_abbreviation': row.team_abbreviation,
        'team_assignment_status': row.team_assignment_status,
        'team_assignment_source': row.team_assignment_source,
        'team_assignment_updated_at': row.team_assignment_updated_at,
        'roster_status': row.roster_status,
        'roster_status_source': row.roster_status_source,
        'roster_status_raw_code': row.roster_status_raw_code,
        'roster_status_raw_description': row.roster_status_raw_description,
        'roster_status_updated_at': row.roster_status_updated_at,
    }


def _all_pitcher_state():
    """Every field of every pitcher — the shadow read-only proof surface."""
    return {
        'rows': [
            (
                row.id, row.mlb_id, row.full_name, row.position, row.active,
                row.team_id, row.team_name, row.team_abbreviation,
                row.team_assignment_status, row.team_assignment_source,
                row.team_assignment_updated_at, row.roster_status,
                row.roster_status_source, row.roster_status_raw_code,
                row.roster_status_raw_description, row.roster_status_updated_at,
                row.throws, row.age, row.jersey_number, row.updated_at,
            )
            for row in Pitcher.query.order_by(Pitcher.id).all()
        ],
        'count': Pitcher.query.count(),
        'max_id': db.session.query(db.func.max(Pitcher.id)).scalar(),
    }


def _all_tables():
    return {
        'pitchers': _all_pitcher_state(),
        'game_logs': [
            (
                row.id, row.pitcher_id, row.mlb_game_pk,
                row.innings_pitched_outs, row.innings_pitched, row.earned_runs,
                row.runs_allowed, row.hits_allowed, row.appearance_team_id,
                row.appearance_team_source, row.appearance_team_status,
                row.appearance_team_reason, row.stat_correction_count,
                row.last_stat_correction_at, row.last_stat_correction_source,
                row.last_stat_correction_sync_run_id,
            )
            for row in GameLog.query.order_by(GameLog.id).all()
        ],
        'work_items': [
            row.to_dict()
            for row in GameIngestionWorkItem.query.order_by(
                GameIngestionWorkItem.id
            ).all()
        ],
        'postgame': [
            row.to_dict()
            for row in PostgameProcessedGame.query.order_by(
                PostgameProcessedGame.id
            ).all()
        ],
        'schedule': [
            row.to_dict()
            for row in ScheduledGame.query.order_by(ScheduledGame.id).all()
        ],
        'failures': SyncFailure.query.count(),
    }


# ═══════════════ 1. Existing inactive pitcher ═══════════════════════════════


def test_an_inactive_pitcher_is_not_reactivated_by_a_historical_game(
    app, monkeypatch,
):
    """The exact class behind the two production reactivations."""
    with app.app_context():
        _schedule(970001)
        arm = _pitcher(8001, active=False, roster_status=STATUS_MINORS)
        db.session.flush()
        _stored_row(arm, 970001)
        db.session.commit()
        before = _pitcher_state(8001)
        monkeypatch.setattr(sync_service, 'mlb_client', BoxscoreClient({
            970001: boxscore([(8001, 'home', pitching_stats())]),
        }))

        plan, summary = _plan_game(970001)

        assert plan[0]['action'] == reconciliation.ACTION_UNCHANGED
        assert plan[0]['pitcher_identity_action'] == identity.ACTION_UNCHANGED
        assert summary['pitcher_identity_mutations'] == 0
        assert summary['pitcher_identity_reactivations'] == 0
        assert summary['complete_mutation_count'] == 0
        # The refusal is visible rather than silent.
        assert 'active' in plan[0]['pitcher_identity'][
            'suppressed_current_state_fields'
        ]

        _write_game(970001)
        assert _pitcher_state(8001) == before

        # Replay converges: nothing left to do on either target.
        replay_plan, replay_summary = _plan_game(970001)
        assert replay_summary['complete_mutation_count'] == 0
        assert replay_plan[0]['action'] == reconciliation.ACTION_UNCHANGED


# ═══════════════ 2. Existing pitcher on a different current team ════════════


def test_a_historical_appearance_does_not_move_the_current_team(app, monkeypatch):
    with app.app_context():
        _schedule(970002)
        arm = _pitcher(8002, team_id=AWAY_TEAM)
        arm.team_name = 'Away Club'
        arm.team_assignment_status = 'ASSIGNED'
        arm.team_assignment_source = 'mlb_stats_api:roster_sync:fullRoster'
        arm.team_assignment_updated_at = datetime(2026, 7, 30, 9, 0, 0)
        arm.roster_status = STATUS_ACTIVE
        db.session.flush()
        # The appearance was recorded on the HOME side; the pitcher is now on
        # the away club.
        _stored_row(arm, 970002)
        db.session.commit()
        before = _pitcher_state(8002)
        monkeypatch.setattr(sync_service, 'mlb_client', BoxscoreClient({
            970002: boxscore([(8002, 'home', pitching_stats())]),
        }))

        plan, summary = _plan_game(970002)
        assert summary['pitcher_identity_mutations'] == 0
        assert 'team_id' in plan[0]['pitcher_identity'][
            'suppressed_current_state_fields'
        ]

        _write_game(970002)
        after = _pitcher_state(8002)

        assert after == before
        assert after['team_id'] == AWAY_TEAM
        assert after['team_assignment_updated_at'] == datetime(2026, 7, 30, 9, 0, 0)
        # The historical team still lives where it belongs.
        log = GameLog.query.filter_by(mlb_game_pk=970002).one()
        assert log.appearance_team_id == HOME_TEAM


# ═══════════════ 3-5. Roster status, provenance, name ═══════════════════════


@pytest.mark.parametrize('status,source', [
    (STATUS_IL_15, 'mlb_stats_api:roster_sync:fullRoster'),
    (STATUS_MINORS, 'mlb_stats_api:roster_sync:fullRoster'),
    # An UNVERIFIED status is protected exactly as strongly as an official one:
    # the rule is structural, not a source-precedence contest.
    (STATUS_UNKNOWN, 'some:unverified:source'),
])
def test_roster_status_and_provenance_survive_a_completed_game(
    app, monkeypatch, status, source,
):
    with app.app_context():
        _schedule(970003)
        arm = _pitcher(8003)
        arm.roster_status = status
        arm.roster_status_source = source
        arm.roster_status_updated_at = datetime(2026, 7, 28, 8, 0, 0)
        db.session.flush()
        _stored_row(arm, 970003)
        db.session.commit()
        before = _pitcher_state(8003)
        monkeypatch.setattr(sync_service, 'mlb_client', BoxscoreClient({
            970003: boxscore([(8003, 'home', pitching_stats())]),
        }))

        _write_game(970003)

        assert _pitcher_state(8003) == before


def test_an_existing_full_name_is_never_overwritten(app, monkeypatch):
    with app.app_context():
        _schedule(970004)
        arm = _pitcher(8004, full_name='Local Preferred Name')
        db.session.flush()
        _stored_row(arm, 970004)
        db.session.commit()
        monkeypatch.setattr(sync_service, 'mlb_client', BoxscoreClient({
            970004: boxscore([(8004, 'home', pitching_stats())]),
        }))

        _write_game(970004)

        assert _pitcher_state(8004)['full_name'] == 'Local Preferred Name'


def test_a_missing_full_name_is_not_silently_enriched(app, monkeypatch):
    """Enrichment would be a mutation, and no policy authorizes one here."""
    with app.app_context():
        _schedule(970005)
        # full_name is NOT NULL, so the reachable "missing" case is empty text.
        # The shared fixture substitutes a placeholder, so it is cleared here.
        arm = _pitcher(8005)
        arm.full_name = ''
        db.session.flush()
        _stored_row(arm, 970005)
        db.session.commit()
        monkeypatch.setattr(sync_service, 'mlb_client', BoxscoreClient({
            970005: boxscore([(8005, 'home', pitching_stats())]),
        }))

        plan, summary = _plan_game(970005)
        assert summary['pitcher_identity_mutations'] == 0
        assert 'full_name' in plan[0]['pitcher_identity'][
            'suppressed_current_state_fields'
        ]

        _write_game(970005)
        assert _pitcher_state(8005)['full_name'] == ''


# ═══════════════ 7-8. Position ══════════════════════════════════════════════


def test_an_existing_position_is_never_rewritten(app, monkeypatch):
    with app.app_context():
        _schedule(970006)
        arm = _pitcher(8006, position='DH')
        db.session.flush()
        _stored_row(arm, 970006)
        db.session.commit()
        monkeypatch.setattr(sync_service, 'mlb_client', BoxscoreClient({
            970006: boxscore([(8006, 'home', pitching_stats())]),
        }))

        _write_game(970006)

        assert _pitcher_state(8006)['position'] == 'DH'


# ═══════════════ 9-10. Minimal creation ═════════════════════════════════════


def test_a_missing_pitcher_is_created_without_any_current_state_claim(
    app, monkeypatch,
):
    with app.app_context():
        _schedule(970007)
        db.session.commit()
        monkeypatch.setattr(sync_service, 'mlb_client', BoxscoreClient({
            970007: boxscore([(8007, 'home', pitching_stats())]),
        }))

        plan, summary = _plan_game(970007)
        entry = plan[0]
        assert entry['action'] == reconciliation.ACTION_INSERT
        assert entry['pitcher_identity_action'] == (
            identity.ACTION_CREATE_MINIMAL_IDENTITY
        )
        assert summary['pitcher_identity_creations'] == 1
        assert summary['pitcher_identity_mutations'] == 1
        # The creation is fingerprinted by VALUE, not merely by shape.
        assert entry['pitcher_identity']['mutation_digest']
        created = entry['pitcher_identity']['creation_values']
        assert set(created) <= set(identity.MINIMAL_CREATION_FIELDS)
        assert 'team_id' not in created
        assert created['active'] is False

        _write_game(970007)
        state = _pitcher_state(8007)

        assert state['active'] is False
        assert state['team_id'] is None
        assert state['team_assignment_status'] is None
        assert state['team_assignment_updated_at'] is None
        assert state['roster_status'] == STATUS_UNKNOWN
        assert state['roster_status_source'] == identity.MINIMAL_IDENTITY_SOURCE
        assert GameLog.query.filter_by(mlb_game_pk=970007).count() == 1

        replay_plan, replay_summary = _plan_game(970007)
        assert replay_summary['complete_mutation_count'] == 0
        assert replay_plan[0]['pitcher_identity_action'] == (
            identity.ACTION_UNCHANGED
        )


def test_a_missing_pitcher_with_no_name_is_blocked(app, monkeypatch):
    with app.app_context():
        _schedule(970008)
        db.session.commit()
        payload = boxscore([(8008, 'home', pitching_stats())])
        payload['teams']['home']['players']['ID8008']['person']['fullName'] = None
        monkeypatch.setattr(
            sync_service, 'mlb_client', BoxscoreClient({970008: payload}),
        )

        plan, _summary = _plan_game(970008)

        assert plan[0]['action'] == reconciliation.ACTION_BLOCKED
        assert plan[0]['governed_and_safe'] is False
        assert Pitcher.query.filter_by(mlb_id=8008).count() == 0

        _write_game(970008)
        assert Pitcher.query.filter_by(mlb_id=8008).count() == 0
        assert GameLog.query.filter_by(mlb_game_pk=970008).count() == 0


def test_a_conflicting_identity_anchor_is_blocked_in_both_modes(app, monkeypatch):
    with app.app_context():
        _schedule(970009)
        db.session.commit()
        payload = boxscore([(8009, 'home', pitching_stats())])
        payload['teams']['home']['players']['ID8009']['person']['id'] = 999999
        monkeypatch.setattr(
            sync_service, 'mlb_client', BoxscoreClient({970009: payload}),
        )

        shadow_plan, _ = _plan_game(970009)
        write_plan, _ = _write_game(970009)

        for entry in (shadow_plan[0], write_plan[0]):
            assert entry['action'] == reconciliation.ACTION_BLOCKED
            assert entry['pitcher_identity_action'] == identity.ACTION_BLOCKED
        assert Pitcher.query.filter_by(mlb_id=8009).count() == 0


# ═══════════════ 13-15. Fingerprint coverage ════════════════════════════════


def test_the_complete_fingerprint_covers_an_identity_creation():
    """Two different created identities must not fingerprint identically."""
    first = identity.plan_identity(
        existing=None, player_mlb_id=5001, line_name='One',
    )
    second = identity.plan_identity(
        existing=None, player_mlb_id=5002, line_name='Two',
    )
    values = {'innings_pitched_outs': 3, 'mlb_game_pk': 1}
    row_one = reconciliation.plan_row(
        existing=None, values=values, stats={}, game_pk=1,
        pitcher_mlb_id=5001, identity_plan=first,
    )
    row_two = reconciliation.plan_row(
        existing=None, values=values, stats={}, game_pk=1,
        pitcher_mlb_id=5001, identity_plan=second,
    )
    assert reconciliation.plan_fingerprint([row_one]) != (
        reconciliation.plan_fingerprint([row_two])
    )


def test_the_complete_fingerprint_ignores_suppressed_current_state(app):
    """Refused evidence must not move a fingerprint that authorizes writes."""
    with app.app_context():
        clean = _pitcher(5101, team_id=HOME_TEAM)
        clean.roster_status = STATUS_ACTIVE
        drifted = _pitcher(5102, team_id=AWAY_TEAM, active=False)
        drifted.roster_status = STATUS_MINORS
        db.session.flush()

        values = {'innings_pitched_outs': 3, 'mlb_game_pk': 1}
        rows = []
        for row in (clean, drifted):
            plan = identity.plan_identity(
                existing=row, player_mlb_id=5001, line_name='X',
                appearance_team={'team_id': HOME_TEAM, 'team_name': 'Home Club'},
            )
            rows.append(reconciliation.plan_row(
                existing=None, values=values, stats={}, game_pk=1,
                pitcher_mlb_id=5001, identity_plan=plan,
            ))

        assert rows[1]['pitcher_identity']['suppressed_current_state_fields']
        assert reconciliation.plan_fingerprint([rows[0]]) == (
            reconciliation.plan_fingerprint([rows[1]])
        )


# ═══════════════ 16-17. Authorization and parity ════════════════════════════


def test_a_write_refuses_when_the_identity_plan_moved(app, monkeypatch):
    """A reviewed fingerprint no longer authorizes only the GameLog half."""
    with app.app_context():
        _schedule(970010)
        db.session.commit()
        monkeypatch.setattr(sync_service, 'mlb_client', BoxscoreClient({
            970010: boxscore([(8010, 'home', pitching_stats())]),
        }))
        shadow = game_driven_ingestion.run_game_driven_ingestion(
            REFERENCE, mode=game_driven_ingestion.MODE_SHADOW,
            only_game_pks=[970010],
        )
        db.session.rollback()
        reviewed = shadow['reconciliation_plan_fingerprint']
        assert shadow['pitcher_identity_creations'] == 1

        # The pitcher now exists, so the identity half of the plan changes from
        # a creation to unchanged while the GameLog half still inserts.
        _pitcher(8010)
        db.session.commit()

        refused = game_driven_ingestion.run_game_driven_ingestion(
            REFERENCE, mode=game_driven_ingestion.MODE_WRITE,
            only_game_pks=[970010], expected_plan_fingerprint=reviewed,
        )

        assert refused['status'] == (
            game_driven_ingestion.STATUS_PLAN_FINGERPRINT_MISMATCH
        )
        assert GameLog.query.filter_by(mlb_game_pk=970010).count() == 0


def test_shadow_and_write_agree_across_every_identity_class(app, monkeypatch):
    with app.app_context():
        _schedule(970011)
        existing = _pitcher(8011, active=False, roster_status=STATUS_MINORS)
        correction = _pitcher(8012)
        db.session.flush()
        _stored_row(existing, 970011)
        _stored_row(correction, 970011, earned_runs=0)
        db.session.commit()
        monkeypatch.setattr(sync_service, 'mlb_client', BoxscoreClient({
            970011: boxscore([
                (8011, 'home', pitching_stats()),
                (8012, 'home', pitching_stats(earned_runs=3, runs=3)),
                (8013, 'away', pitching_stats()),
            ]),
        }))

        shadow_plan, shadow_summary = _plan_game(970011)
        db.session.rollback()
        write_plan, write_summary = _write_game(970011)

        def view(plan):
            return sorted(
                (
                    entry['pitcher_mlb_id'], entry['action'],
                    entry['pitcher_identity_action'],
                    tuple(entry['changed_fields']),
                    tuple(entry['mutation_categories']),
                    entry.get('blocked_reason') or '',
                    entry['mutation_digest'],
                    entry['pitcher_identity'].get('mutation_digest') or '',
                    tuple(entry['pitcher_identity'].get(
                        'suppressed_current_state_fields'
                    ) or ()),
                )
                for entry in plan
            )

        assert view(shadow_plan) == view(write_plan)
        for key in (
            'rows_inserted', 'rows_updated', 'rows_unchanged', 'rows_blocked',
            'pitcher_identity_mutations', 'pitcher_identity_creations',
            'pitcher_identity_unchanged', 'complete_mutation_count',
            'reconciliation_plan_fingerprint',
            'complete_reconciliation_fingerprint',
        ):
            assert shadow_summary[key] == write_summary[key], key


# ═══════════════ 18. Rollback ═══════════════════════════════════════════════


def test_a_failure_after_identity_creation_leaves_nothing_behind(
    app, monkeypatch,
):
    with app.app_context():
        _schedule(970012)
        db.session.commit()
        monkeypatch.setattr(sync_service, 'mlb_client', BoxscoreClient({
            970012: boxscore([(8014, 'home', pitching_stats())]),
        }))

        real_verify = game_driven_ingestion._verify_game_completeness

        def _explode(item, appearances):
            real_verify(item, appearances)
            raise RuntimeError('failure after identity creation')

        monkeypatch.setattr(
            game_driven_ingestion, '_verify_game_completeness', _explode,
        )

        report = game_driven_ingestion.run_game_driven_ingestion(
            REFERENCE, mode=game_driven_ingestion.MODE_WRITE,
        )

        assert report['games_failed'] == 1
        assert Pitcher.query.filter_by(mlb_id=8014).count() == 0
        assert GameLog.query.filter_by(mlb_game_pk=970012).count() == 0
        completed = GameIngestionWorkItem.query.filter_by(
            mlb_game_pk=970012,
            status=GameIngestionWorkItem.STATUS_COMPLETED,
        ).count()
        assert completed == 0


# ═══════════════ 19. Shadow read-only proof ═════════════════════════════════


def test_shadow_leaves_every_pitcher_field_untouched(app, monkeypatch):
    """Hundreds of suppressed differences must still produce zero drift."""
    with app.app_context():
        for index in range(6):
            game_pk = 970100 + index
            _schedule(game_pk)
            arm = _pitcher(
                8100 + index,
                team_id=AWAY_TEAM if index % 2 else HOME_TEAM,
                active=index % 3 != 0,
            )
            arm.roster_status = STATUS_MINORS if index % 2 else STATUS_ACTIVE
            db.session.flush()
            _stored_row(arm, game_pk)
        db.session.commit()
        monkeypatch.setattr(sync_service, 'mlb_client', BoxscoreClient({
            970100 + index: boxscore([
                (8100 + index, 'home', pitching_stats()),
            ])
            for index in range(6)
        }))

        before = _all_tables()
        report = game_driven_ingestion.run_game_driven_ingestion(
            REFERENCE, mode=game_driven_ingestion.MODE_SHADOW,
        )
        db.session.rollback()
        after = _all_tables()

        assert report['historical_current_state_changes_suppressed'] > 0
        assert report['pitcher_identity_mutations'] == 0
        assert report['complete_mutation_count'] == 0
        for table in before:
            assert before[table] == after[table], table


# ═══════════════ Production-shape regression ════════════════════════════════


def test_the_production_r2_shape_now_projects_no_mutations(app, monkeypatch):
    """The observed production population, modelled from its conditions.

    Not a hard-coded aggregate: the underlying conditions are built — existing
    pitchers, historical/current team differences, inactive rows, official
    roster authority, already-matching GameLogs, and decimal companion drift —
    and the repaired totals are asserted from what those conditions produce.
    """
    with app.app_context():
        games = []
        drifted = 0
        for index in range(12):
            game_pk = 971000 + index
            _schedule(game_pk)
            games.append(game_pk)
            arm = _pitcher(
                8200 + index,
                # Half the population sits on a different current team, which is
                # what produced 940 `update_metadata` actions in production.
                team_id=AWAY_TEAM if index % 2 else HOME_TEAM,
                active=index % 5 != 0,
            )
            arm.roster_status = STATUS_ACTIVE if index % 3 else STATUS_MINORS
            arm.roster_status_source = 'mlb_stats_api:roster_sync:fullRoster'
            db.session.flush()
            if index % 4 == 0:
                # Representation drift inside the CHECK constraint's tolerance.
                drifted += 1
                _stored_row(
                    arm, game_pk, innings_pitched_outs=1,
                    innings_pitched=0.333333, hits_allowed=0, strikeouts=1,
                    batters_faced=1, strikes=3, pitches_thrown=4,
                )
            else:
                _stored_row(arm, game_pk)
        db.session.commit()

        monkeypatch.setattr(sync_service, 'mlb_client', BoxscoreClient({
            971000 + index: boxscore([(
                8200 + index, 'home',
                pitching_stats(
                    innings='0.1', hits=0, strikeouts=1, batters_faced=1,
                    strikes=3, pitches=4,
                ) if index % 4 == 0 else pitching_stats(),
            )])
            for index in range(12)
        }))

        before = _all_tables()
        report = game_driven_ingestion.run_game_driven_ingestion(
            REFERENCE, mode=game_driven_ingestion.MODE_SHADOW,
        )
        db.session.rollback()

        assert report['games_planned'] == len(games)
        assert report['rows_expected'] == len(games)
        assert report['rows_updated'] == 0
        assert report['rows_inserted'] == 0
        assert report['rows_blocked'] == 0
        assert report['rows_unchanged'] == len(games)
        assert report['derived_companion_differences_ignored'] == drifted
        assert report['changed_fields_counts'] == {}

        # The repaired identity result: the population that used to plan 942
        # writes now plans none, and says so.
        assert report['pitcher_identity_mutations'] == 0
        assert report['pitcher_identity_reactivations'] == 0
        assert report['pitcher_identity_metadata_updates'] == 0
        assert report['pitcher_identity_creations'] == 0
        assert report['pitcher_identity_blocked'] == 0
        assert report['appearance_team_mutations'] == 0
        assert report['complete_mutation_count'] == 0
        assert report['historical_current_state_changes_suppressed'] > 0
        assert report['pitcher_identity_action_counts'] == {
            identity.ACTION_UNCHANGED: len(games),
        }
        assert _all_tables() == before


# ═══════════════ Planner unit contract ══════════════════════════════════════


def test_the_planner_never_emits_a_current_state_field_for_an_existing_row(app):
    """Structural, not source-dependent: no branch can produce one."""
    with app.app_context():
        arm = _pitcher(5200, team_id=AWAY_TEAM, active=False)
        arm.roster_status = STATUS_MINORS
        arm.full_name = ''
        arm.position = ''
        db.session.flush()

        plan = identity.plan_identity(
            existing=arm, player_mlb_id=5200, line_name='Someone',
            line_position='P',
            appearance_team={
                'team_id': HOME_TEAM, 'team_name': 'Home Club',
                'team_abbreviation': 'HOM',
            },
        )

        assert plan['action'] == identity.ACTION_UNCHANGED
        assert plan['changed_fields'] == []
        assert plan['applied_fields'] == []
        assert plan['mutation_digest'] == ''
        assert plan['current_authority_mutation_refused'] is True
        # Every difference the retired path would have written, refused.
        assert set(plan['suppressed_current_state_fields']) == {
            'active', 'full_name', 'position', 'roster_status',
            'team_abbreviation', 'team_id', 'team_name',
        }


@pytest.mark.parametrize('action', identity.RETIRED_WRITE_ACTIONS)
def test_the_retired_write_actions_are_not_valid_identity_actions(action):
    assert action not in identity.ACTIONS


def test_minimal_creation_touches_no_current_team_field():
    values = identity.minimal_identity_values(
        player_mlb_id=1, line_name='Someone',
    )
    assert set(values) == set(identity.MINIMAL_CREATION_FIELDS)
    for field in (
        'team_id', 'team_name', 'team_abbreviation',
        'team_assignment_status', 'team_assignment_source',
        'team_assignment_updated_at', 'roster_status_updated_at',
    ):
        assert field not in values
    assert values['active'] is False
    assert values['roster_status'] == STATUS_UNKNOWN


def test_an_identity_summary_counts_a_pitcher_once_per_run():
    plans = [
        identity.plan_identity(existing=None, player_mlb_id=7, line_name='A'),
        identity.plan_identity(existing=None, player_mlb_id=7, line_name='A'),
    ]
    summary = identity.summarize(plans)
    assert summary['pitcher_identity_creations'] == 2
    assert summary['pitcher_identity_unique_pitchers_affected'] == 1


# ═══════════════ First-write forensics (read-only) ══════════════════════════


def test_the_forensic_tool_refuses_to_inspect_without_read_only_proof(app):
    """A guard that cannot prove protection must inspect nothing."""
    from scripts import inspect_first_write_pitcher_identity as forensics

    with app.app_context():
        original = db.session.get_bind

        class _NotPostgres:
            class dialect:
                name = 'sqlite'

        db.session.get_bind = lambda *args, **kwargs: _NotPostgres()
        try:
            with pytest.raises(forensics.ReadOnlyNotEnforced):
                forensics.inspect([970001])
        finally:
            db.session.get_bind = original


def test_the_forensic_tool_reports_evidence_without_inventing_prior_values(
    app,
):
    from scripts import inspect_first_write_pitcher_identity as forensics

    with app.app_context():
        arm = _pitcher(8300, team_id=AWAY_TEAM, active=False)
        arm.roster_status = STATUS_MINORS
        arm.team_assignment_source = forensics.RETIRED_POSTGAME_SOURCE
        db.session.flush()
        _stored_row(arm, 823518)
        db.session.commit()

        before = _all_tables()
        report = forensics.collect_evidence([823518])
        db.session.rollback()

        assert report['appearance_rows_examined'] == 1
        assert report['rows_attributable_to_completed_game_write'] == 1
        assert report['conclusion'] == forensics.CONCLUSION_PARTIAL
        assert report['prior_values_reconstructible'] is False
        assert report['cleanup_performed'] is False
        assert report['cleanup_proposed'] is False

        entry = report['games'][0]['entries'][0]
        assert entry['attribution']['prior_values_retained'] is False
        # Under the repaired rules this row would not be touched at all.
        assert entry['identity_plan_today']['would_mutate'] is False
        assert entry['identity_plan_today']['action'] == identity.ACTION_UNCHANGED
        assert entry['identity_plan_today']['suppressed_current_state_fields']

        assert _all_tables() == before


def test_the_forensic_tool_reports_inseparability_when_no_marker_remains(app):
    """A later roster sync erases the only attribution marker."""
    from scripts import inspect_first_write_pitcher_identity as forensics

    with app.app_context():
        arm = _pitcher(8301)
        arm.team_assignment_source = 'mlb_stats_api:roster_sync:fullRoster'
        arm.roster_status_source = 'mlb_stats_api:roster_sync:fullRoster'
        db.session.flush()
        _stored_row(arm, 824735)
        db.session.commit()

        report = forensics.collect_evidence([824735])
        db.session.rollback()

        assert report['rows_attributable_to_completed_game_write'] == 0
        assert report['conclusion'] == forensics.CONCLUSION_INSEPARABLE
        assert report['prior_values_reconstructible'] is False


def test_the_forensic_report_carries_no_credential_or_path(app):
    from scripts import inspect_first_write_pitcher_identity as forensics
    import json as _json

    with app.app_context():
        arm = _pitcher(8302)
        db.session.flush()
        _stored_row(arm, 823761)
        db.session.commit()

        encoded = _json.dumps(forensics.collect_evidence([823761]), default=str)
        db.session.rollback()

    for forbidden in (
        'postgresql://', 'postgres://', 'password=', 'Authorization',
        'SECRET_KEY', 'DATABASE_URL', 'Traceback', '/home/',
    ):
        assert forbidden not in encoded


# ═══════════════ Schema fit ═════════════════════════════════════════════════


@pytest.mark.parametrize('position_override', [False, True])
def test_every_minimal_creation_value_fits_its_column(position_override):
    """PostgreSQL refuses an over-length VARCHAR; SQLite accepts it silently.

    A string that fits in the local test database and not in production is a
    write that fails only where it matters, so the widths are asserted against
    the model rather than trusted.
    """
    values = identity.minimal_identity_values(
        player_mlb_id=1, line_name='A Reasonably Long Pitcher Name',
        line_position='P', position_override=position_override,
    )
    columns = Pitcher.__table__.columns
    for field, value in values.items():
        if not isinstance(value, str):
            continue
        limit = getattr(columns[field].type, 'length', None)
        assert limit is not None, field
        assert len(value) <= limit, (field, len(value), limit)


def test_the_creation_provenance_reaches_postgres_intact(app, monkeypatch):
    """The exact insert that PostgreSQL rejected before this guard existed."""
    with app.app_context():
        _schedule(970200)
        db.session.commit()
        payload = boxscore([(8400, 'home', pitching_stats())])
        player = payload['teams']['home']['players']['ID8400']
        player['position'] = {
            'code': 'O', 'name': 'Designated Hitter', 'abbreviation': 'DH',
        }
        player['person']['primaryPosition'] = player['position']
        monkeypatch.setattr(
            sync_service, 'mlb_client', BoxscoreClient({970200: payload}),
        )

        _write_game(970200)

        created = Pitcher.query.filter_by(mlb_id=8400).one()
        assert created.roster_status_raw_description.endswith(
            'position_override_from_pitching_line'
        )
        assert len(created.roster_status_raw_description) <= 100


# ═══════════════ The identity half of the write authorization ═══════════════
#
# The complete fingerprint is what `--expected-plan-fingerprint` compares, and
# it is computed over the REPORTED row, not the raw planner plan. The identity
# component previously read a nested key that `_safe_row_entries` does not
# emit, so it collapsed to a constant: two different identity creations
# fingerprinted identically and a reviewed fingerprint authorized either one.


def _row_for(plan):
    from services.game_driven_ingestion import _safe_row_entries

    values = {'innings_pitched_outs': 3, 'mlb_game_pk': 1}
    return _safe_row_entries([reconciliation.plan_row(
        existing=None, values=values, stats={}, game_pk=1,
        pitcher_mlb_id=99, identity_plan=plan,
    )])


def test_two_different_identity_creations_do_not_share_a_fingerprint():
    """The exact hole: reviewing one creation must not authorize another."""
    one = identity.plan_identity(
        existing=None, player_mlb_id=111, line_name='Arm One',
    )
    two = identity.plan_identity(
        existing=None, player_mlb_id=222, line_name='Arm Two',
    )
    assert one['mutation_digest'] != two['mutation_digest']
    assert reconciliation.plan_fingerprint(_row_for(one)) != (
        reconciliation.plan_fingerprint(_row_for(two))
    )


def test_the_reported_row_fingerprints_the_same_as_the_raw_plan():
    """The write guard compares the reported row; they must not diverge."""
    plan = identity.plan_identity(
        existing=None, player_mlb_id=111, line_name='Arm One',
    )
    values = {'innings_pitched_outs': 3, 'mlb_game_pk': 1}
    raw = reconciliation.plan_row(
        existing=None, values=values, stats={}, game_pk=1,
        pitcher_mlb_id=99, identity_plan=plan,
    )
    assert reconciliation.plan_fingerprint([raw]) == (
        reconciliation.plan_fingerprint(_row_for(plan))
    )


def test_a_blocked_identity_moves_the_fingerprint():
    clean = identity.plan_identity(
        existing=None, player_mlb_id=111, line_name='Arm One',
    )
    blocked = identity.plan_identity(
        existing=None, player_mlb_id=111, line_name=None,
    )
    assert blocked['action'] == identity.ACTION_BLOCKED
    assert reconciliation.plan_fingerprint(_row_for(clean)) != (
        reconciliation.plan_fingerprint(_row_for(blocked))
    )


def test_suppressed_evidence_still_does_not_move_the_fingerprint(app):
    """Refused evidence must not move an authorization fingerprint."""
    with app.app_context():
        clean = _pitcher(5301, team_id=HOME_TEAM)
        clean.roster_status = STATUS_ACTIVE
        drifted = _pitcher(5302, team_id=AWAY_TEAM, active=False)
        drifted.roster_status = STATUS_MINORS
        db.session.flush()

        plans = [
            identity.plan_identity(
                existing=row, player_mlb_id=5001, line_name='X',
                appearance_team={'team_id': HOME_TEAM, 'team_name': 'Home Club'},
            )
            for row in (clean, drifted)
        ]
        assert plans[1]['suppressed_current_state_fields']
        assert reconciliation.plan_fingerprint(_row_for(plans[0])) == (
            reconciliation.plan_fingerprint(_row_for(plans[1]))
        )


def test_the_parity_contract_version_moved_with_the_algorithm():
    """A fingerprint reviewed under the old contract is stale by construction."""
    assert reconciliation.PARITY_CONTRACT_VERSION == '4'
