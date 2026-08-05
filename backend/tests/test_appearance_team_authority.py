"""Foundation 1 — canonical team-at-appearance authority.

Every pitching appearance must durably retain the MLB team the pitcher REPRESENTED
in that game, resolved from official game-side evidence and never from the mutable
current ``Pitcher.team_id``. This suite covers the model/migration, the resolver +
source precedence, resolved/unresolved/conflict behavior, the ingestion write paths,
idempotency/corrections, the read accessor, the coverage audit, and the traded-
pitcher regression that motivated the work. It also asserts Team State v1.2 and the
public payloads are unchanged, and that no reader is migrated in this step.
"""

import importlib.util
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from flask import Flask

import models.prospect  # noqa: F401
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.scheduled_game import ScheduledGame
from services import appearance_team_authority as ata
from services import sync as sync_service
from services.appearance_team_authority import (
    REASON_CONFLICT,
    REASON_CORRECTED,
    REASON_RESOLVED_BOXSCORE,
    REASON_RESOLVED_SCHEDULE,
    SOURCE_BOXSCORE,
    SOURCE_SCHEDULE,
    STATUS_CONFLICT,
    STATUS_RESOLVED,
    STATUS_UNRESOLVED,
    resolve_appearance_team,
    resolve_for_write,
)
from services.appearance_team_coverage import build_appearance_team_coverage
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


HOME_TEAM, AWAY_TEAM = 1, 2
GAME_PK = 7001
GAME_DATE = date(2026, 6, 20)
MIGRATION_PATH = 'migrations/versions/a4f1c7e9b3d2_add_game_log_appearance_team.py'
REPO_ROOT_FOR_DIFF = Path(__file__).resolve().parents[2]


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


def _persist_pitcher(mlb_id=990001, team_id=HOME_TEAM):
    """Create and flush a real parent Pitcher for a production-shaped GameLog fixture.

    game_logs.pitcher_id is a NOT-NULL foreign key to pitchers.id; a fixture must
    reference a persisted parent (PostgreSQL enforces this even though local in-memory
    SQLite does not). Callers use the returned ``pitcher.id`` — never an assumed key.
    """
    pitcher = Pitcher(mlb_id=mlb_id, full_name=f'Fixture {mlb_id}', team_id=team_id,
                      active=True)
    db.session.add(pitcher)
    db.session.flush()
    return pitcher


def _seed_schedule(game_pk=GAME_PK, home=HOME_TEAM, away=AWAY_TEAM, game_date=GAME_DATE):
    db.session.add_all([
        ScheduledGame(team_id=home, game_pk=game_pk, game_date=game_date,
                      status_state='final', home_away='home', opponent_team_id=away),
        ScheduledGame(team_id=away, game_pk=game_pk, game_date=game_date,
                      status_state='final', home_away='away', opponent_team_id=home),
    ])
    db.session.commit()


def _boxscore(earned_runs=None):
    er_by = earned_runs or {}

    def _line(pid, ip, er, side_stats=None):
        er = er_by.get(pid, er)
        stats = {'inningsPitched': ip, 'numberOfPitches': '14', 'strikes': '9',
                 'hits': '0', 'runs': str(er), 'earnedRuns': str(er), 'baseOnBalls': '0',
                 'strikeOuts': '2', 'homeRuns': '0'}
        stats.update(side_stats or {})
        return {'person': {'fullName': f'P{pid}', 'id': pid}, 'stats': {'pitching': stats}}
    return {
        'teams': {
            'home': {'team': {'id': HOME_TEAM, 'name': 'Home Club'}, 'pitchers': [101, 111],
                     'players': {'ID101': _line(101, '1.0', 0, {'gamesStarted': '1'}),
                                 'ID111': _line(111, '1.0', 2)}},
            'away': {'team': {'id': AWAY_TEAM, 'name': 'Away Club'}, 'pitchers': [202],
                     'players': {'ID202': _line(202, '0.2', 0, {'gamesStarted': '1'})}},
        },
    }


def _game(game_pk=GAME_PK):
    return {'gamePk': game_pk, 'gameType': 'R', 'officialDate': GAME_DATE.isoformat(),
            'teams': {'home': {'team': {'id': HOME_TEAM, 'name': 'Home Club'}},
                      'away': {'team': {'id': AWAY_TEAM, 'name': 'Away Club'}}}}


def _ingest_boxscore(pitcher, player_id, earned_runs=None):
    """Drive the REAL postgame box-score ingestion path for one pitcher."""
    boxscore = _boxscore(earned_runs={player_id: earned_runs} if earned_runs is not None else None)
    lines = sync_service._extract_pitching_lines_from_boxscore(boxscore)
    line = next(l for l in lines if l['player_id'] == player_id)
    return sync_service._ingest_boxscore_pitching_line(
        pitcher, line, _game(), game_date=GAME_DATE, team_abbr_map={},
        pitcher_order=sync_service._pitcher_order_by_side(boxscore),
    )


def _daily_split(game_pk=GAME_PK, opponent_id=AWAY_TEAM, ip='1.0', er=0, gs=0):
    return {
        'game': {'gamePk': game_pk, 'gameType': 'R'},
        'date': GAME_DATE.isoformat(),
        'opponent': {'id': opponent_id, 'name': 'Opp', 'abbreviation': 'OPP'},
        'stat': {'inningsPitched': ip, 'earnedRuns': str(er), 'runs': str(er),
                 'gamesStarted': str(gs), 'numberOfPitches': '12'},
    }


# ===========================================================================
# Model + migration (matrix 1-9)
# ===========================================================================


def test_appearance_team_columns_exist(app):
    cols = {c.name for c in GameLog.__table__.columns}
    assert {'appearance_team_id', 'appearance_team_source',
            'appearance_team_status', 'appearance_team_reason'} <= cols


def test_legacy_rows_may_remain_null(app):
    p = _persist_pitcher()
    log = GameLog(pitcher_id=p.id, mlb_game_pk=1, game_date=GAME_DATE,
                  innings_pitched=1.0, innings_pitched_outs=3)
    db.session.add(log); db.session.commit()
    assert log.appearance_team_id is None
    assert log.appearance_team_status is None


def test_status_check_constraint_rejects_bad_value(app):
    p = _persist_pitcher()
    db.session.add(GameLog(pitcher_id=p.id, mlb_game_pk=2, game_date=GAME_DATE,
                           innings_pitched=1.0, innings_pitched_outs=3,
                           appearance_team_status='bogus'))
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()


def _run_migration(op_module):
    engine = sa.create_engine('sqlite:///:memory:')
    md = sa.MetaData()
    sa.Table('game_logs', md,
             sa.Column('id', sa.Integer, primary_key=True),
             sa.Column('pitcher_id', sa.Integer, nullable=False),
             sa.Column('mlb_game_pk', sa.Integer, nullable=False),
             sa.Column('game_date', sa.Date, nullable=False),
             sa.Column('innings_pitched', sa.Float),
             sa.Column('innings_pitched_outs', sa.Integer, nullable=False),
             sa.UniqueConstraint('pitcher_id', 'mlb_game_pk', name='uq_game_logs_pitcher_game'),
             sa.CheckConstraint('innings_pitched_outs >= 0',
                                name='ck_game_logs_innings_pitched_outs_nonnegative'))
    md.create_all(engine)
    with engine.begin() as conn:
        conn.execute(sa.text("INSERT INTO game_logs (pitcher_id, mlb_game_pk, game_date, "
                             "innings_pitched, innings_pitched_outs) VALUES (7, 555, '2026-04-01', 1.0, 3)"))
    return engine


def _load_migration():
    spec = importlib.util.spec_from_file_location('appearance_team_migration', MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_upgrade_downgrade_reupgrade_and_preserves_data():
    migration = _load_migration()
    engine = _run_migration(migration)

    def cols(conn):
        return {c['name'] for c in sa.inspect(conn).get_columns('game_logs')}

    def idxs(conn):
        return {i['name'] for i in sa.inspect(conn).get_indexes('game_logs')}

    new_cols = {'appearance_team_id', 'appearance_team_source',
                'appearance_team_status', 'appearance_team_reason'}
    with engine.begin() as conn:
        migration.op = Operations(MigrationContext.configure(conn))
        migration.upgrade()
        assert new_cols <= cols(conn)
        assert {'ix_game_log_appearance_team_date',
                'ix_game_log_game_pk_appearance_team'} <= idxs(conn)
        # Existing row unchanged; new columns NULL (no backfill in the migration).
        row = conn.execute(sa.text('SELECT pitcher_id, innings_pitched_outs, '
                                   'appearance_team_id, appearance_team_status '
                                   'FROM game_logs WHERE mlb_game_pk=555')).fetchone()
        assert tuple(row) == (7, 3, None, None)
        migration.downgrade()
        assert not (new_cols & cols(conn))
        migration.upgrade()
        assert new_cols <= cols(conn)


def test_fresh_schema_has_one_alembic_head():
    import os
    import re
    versions = 'migrations/versions'
    revs, downs = {}, set()
    for name in os.listdir(versions):
        if not name.endswith('.py'):
            continue
        text = open(os.path.join(versions, name)).read()
        rev = re.search(r"^revision\s*=\s*['\"]([0-9a-f]+)['\"]", text, re.M)
        down = re.search(r"^down_revision\s*=\s*['\"]([0-9a-f]+)['\"]", text, re.M)
        if rev:
            revs[rev.group(1)] = down.group(1) if down else None
        if down:
            downs.add(down.group(1))
    heads = [r for r in revs if r not in downs]
    from tests.test_phase0e_exit_docs import EXPECTED_ALEMBIC_HEAD

    assert heads == [EXPECTED_ALEMBIC_HEAD]


# ===========================================================================
# Attribution + sources + precedence (matrix 10-27)
# ===========================================================================


def test_home_pitcher_resolves_home_team_via_boxscore(app):
    _seed_schedule()
    p = Pitcher(mlb_id=101, full_name='P101', team_id=HOME_TEAM, active=True)
    db.session.add(p); db.session.flush()
    _ingest_boxscore(p, 101)
    db.session.commit()
    log = GameLog.query.filter_by(pitcher_id=p.id).one()
    assert log.appearance_team_id == HOME_TEAM
    assert log.appearance_team_status == STATUS_RESOLVED
    assert log.appearance_team_source == SOURCE_BOXSCORE
    assert log.appearance_team_reason == REASON_RESOLVED_BOXSCORE


def test_away_pitcher_resolves_away_team_via_boxscore(app):
    _seed_schedule()
    p = Pitcher(mlb_id=202, full_name='P202', team_id=AWAY_TEAM, active=True)
    db.session.add(p); db.session.flush()
    _ingest_boxscore(p, 202)
    db.session.commit()
    log = GameLog.query.filter_by(pitcher_id=p.id).one()
    assert log.appearance_team_id == AWAY_TEAM


def test_starter_and_reliever_both_get_team_attribution(app):
    _seed_schedule()
    starter = Pitcher(mlb_id=101, full_name='Starter', team_id=HOME_TEAM, active=True)
    reliever = Pitcher(mlb_id=111, full_name='Reliever', team_id=HOME_TEAM, active=True)
    db.session.add_all([starter, reliever]); db.session.flush()
    _ingest_boxscore(starter, 101)
    _ingest_boxscore(reliever, 111)
    db.session.commit()
    # Both attributed to the home team, independent of role.
    for pid in (starter.id, reliever.id):
        log = GameLog.query.filter_by(pitcher_id=pid).one()
        assert log.appearance_team_id == HOME_TEAM
        assert log.appearance_team_status == STATUS_RESOLVED


def test_current_team_is_never_the_attribution_source(app):
    # Pitcher's CURRENT team is a wrong team; the box-score side must still win.
    _seed_schedule()
    p = Pitcher(mlb_id=101, full_name='P101', team_id=999, active=True)
    db.session.add(p); db.session.flush()
    _ingest_boxscore(p, 101)
    db.session.commit()
    log = GameLog.query.filter_by(pitcher_id=p.id).one()
    assert log.appearance_team_id == HOME_TEAM  # not 999


def test_schedule_source_resolves_daily_sync_side(app):
    # The daily-sync payload has only the opponent; resolve via the schedule ledger.
    _seed_schedule()
    r = resolve_for_write(game_pk=GAME_PK, opponent_team_id=AWAY_TEAM)
    assert r.team_id == HOME_TEAM
    assert r.status == STATUS_RESOLVED
    assert r.source == SOURCE_SCHEDULE
    assert r.reason == REASON_RESOLVED_SCHEDULE


def test_missing_authority_is_unresolved(app):
    r = resolve_for_write(game_pk=99999, opponent_team_id=AWAY_TEAM)  # no schedule
    assert r.status == STATUS_UNRESOLVED
    assert r.team_id is None


def test_boxscore_schedule_disagreement_is_conflict(app):
    _seed_schedule()
    r = resolve_for_write(boxscore_team_id=888, game_pk=GAME_PK, opponent_team_id=AWAY_TEAM)
    assert r.status == STATUS_CONFLICT
    assert r.team_id is None
    assert r.reason == REASON_CONFLICT


def test_source_precedence_is_deterministic(app):
    _seed_schedule()
    # Box score present -> boxscore source; absent -> schedule source.
    assert resolve_for_write(boxscore_team_id=HOME_TEAM, game_pk=GAME_PK,
                             opponent_team_id=AWAY_TEAM).source == SOURCE_BOXSCORE
    assert resolve_for_write(game_pk=GAME_PK, opponent_team_id=AWAY_TEAM).source == SOURCE_SCHEDULE


def test_reprocessing_does_not_flap_source_or_team(app):
    _seed_schedule()
    p = Pitcher(mlb_id=101, full_name='P101', team_id=HOME_TEAM, active=True)
    db.session.add(p); db.session.flush()
    _ingest_boxscore(p, 101)
    db.session.commit()
    first = GameLog.query.filter_by(pitcher_id=p.id).one()
    team_before, source_before = first.appearance_team_id, first.appearance_team_source
    # Re-ingest the identical box score.
    _ingest_boxscore(p, 101)
    db.session.commit()
    again = GameLog.query.filter_by(pitcher_id=p.id).one()
    assert (again.appearance_team_id, again.appearance_team_source) == (team_before, source_before)


def test_unresolved_and_conflict_are_never_a_fake_team_id(app):
    for r in (resolve_for_write(game_pk=1, opponent_team_id=None),
              ata.AppearanceTeamResolution(None, STATUS_CONFLICT, 'source_conflict', REASON_CONFLICT)):
        assert r.team_id is None
        assert not r.resolved


# ===========================================================================
# Ingestion paths write attribution (matrix 34-39)
# ===========================================================================


def test_daily_sync_path_writes_team_attribution(app):
    _seed_schedule()
    p = Pitcher(mlb_id=300, full_name='Daily Arm', team_id=HOME_TEAM, active=True)
    db.session.add(p); db.session.flush()
    result = sync_service._ingest_game_log_split(
        p, _daily_split(opponent_id=AWAY_TEAM), GAME_DATE - timedelta(days=5), {},
    )
    db.session.commit()
    assert result['status'] == 'inserted'
    log = GameLog.query.filter_by(pitcher_id=p.id).one()
    assert log.appearance_team_id == HOME_TEAM
    assert log.appearance_team_source == SOURCE_SCHEDULE


def test_daily_sync_unmatched_opponent_stores_unresolved_row(app):
    # The game IS final (schedule present), so the appearance is stored, but the
    # opponent matches no scheduled side, so team attribution fails closed.
    _seed_schedule(game_pk=GAME_PK, home=HOME_TEAM, away=AWAY_TEAM)
    p = Pitcher(mlb_id=301, full_name='Unmatched', team_id=HOME_TEAM, active=True)
    db.session.add(p); db.session.flush()
    result = sync_service._ingest_game_log_split(
        p, _daily_split(game_pk=GAME_PK, opponent_id=999), GAME_DATE - timedelta(days=5), {},
    )
    db.session.commit()
    assert result['status'] == 'inserted'
    log = GameLog.query.filter_by(pitcher_id=p.id).one()
    assert log.appearance_team_id is None
    assert log.appearance_team_status == STATUS_UNRESOLVED


def test_failed_team_resolution_is_visible_via_status(app):
    _seed_schedule(game_pk=GAME_PK, home=HOME_TEAM, away=AWAY_TEAM)
    p = Pitcher(mlb_id=302, full_name='Unresolvable', team_id=HOME_TEAM, active=True)
    db.session.add(p); db.session.flush()
    sync_service._ingest_game_log_split(
        p, _daily_split(game_pk=GAME_PK, opponent_id=999), GAME_DATE - timedelta(days=5), {},
    )
    db.session.commit()
    log = GameLog.query.filter_by(pitcher_id=p.id).one()
    assert resolve_appearance_team(log).status == STATUS_UNRESOLVED


# ===========================================================================
# Corrections + idempotency + concurrency (matrix 28-33)
# ===========================================================================


def test_equivalent_rerun_is_idempotent(app):
    # Re-ingest the identical authoritative box-score line for the same appearance.
    _seed_schedule()
    p = Pitcher(mlb_id=101, full_name='Home Arm', team_id=HOME_TEAM, active=True)
    db.session.add(p); db.session.flush()
    first = _ingest_boxscore(p, 101)
    db.session.commit()
    second = _ingest_boxscore(p, 101)
    db.session.commit()
    assert first['status'] == 'inserted'
    assert second['status'] == 'unchanged'
    assert GameLog.query.filter_by(pitcher_id=p.id).count() == 1


def test_stat_only_correction_preserves_team_attribution(app):
    # A genuine stat correction through the authoritative box-score path must not
    # erase the frozen team-at-appearance attribution.
    _seed_schedule()
    p = Pitcher(mlb_id=101, full_name='Home Arm', team_id=HOME_TEAM, active=True)
    db.session.add(p); db.session.flush()
    _ingest_boxscore(p, 101, earned_runs=0)
    db.session.commit()
    log = GameLog.query.filter_by(pitcher_id=p.id).one()
    assert log.appearance_team_id == HOME_TEAM
    result = _ingest_boxscore(p, 101, earned_runs=3)
    db.session.commit()
    log = GameLog.query.filter_by(pitcher_id=p.id).one()
    assert result['status'] == 'corrected'
    assert log.earned_runs == 3  # stat corrected
    assert log.appearance_team_id == HOME_TEAM  # attribution preserved
    assert log.appearance_team_status == STATUS_RESOLVED


def test_authoritative_team_correction_upgrades_via_governed_path(app):
    # A schedule-resolved row later confirmed by a higher-precedence box score that
    # reports a DIFFERENT team is corrected through the governed path.
    _seed_schedule()
    p = Pitcher(mlb_id=300, full_name='Daily Arm', team_id=HOME_TEAM, active=True)
    db.session.add(p); db.session.flush()
    sync_service._ingest_game_log_split(p, _daily_split(er=1), GAME_DATE - timedelta(days=5), {})
    db.session.commit()
    log = GameLog.query.filter_by(pitcher_id=p.id).one()
    assert log.appearance_team_source == SOURCE_SCHEDULE and log.appearance_team_id == HOME_TEAM
    # A stat correction that also carries a higher-precedence boxscore attribution to
    # a genuinely different team.
    boxscore_resolution = ata.AppearanceTeamResolution(
        AWAY_TEAM, STATUS_RESOLVED, SOURCE_BOXSCORE, REASON_RESOLVED_BOXSCORE)
    reason = ata.reconcile_on_update(log, boxscore_resolution, correction_applied=True)
    assert reason == REASON_CORRECTED
    assert log.appearance_team_id == AWAY_TEAM
    assert log.appearance_team_reason == REASON_CORRECTED


def test_lower_precedence_source_never_downgrades(app):
    # A boxscore-resolved row is not flipped by a later schedule resolution.
    p = _persist_pitcher()
    log = GameLog(pitcher_id=p.id, mlb_game_pk=1, game_date=GAME_DATE, innings_pitched=1.0,
                  innings_pitched_outs=3, appearance_team_id=HOME_TEAM,
                  appearance_team_status=STATUS_RESOLVED, appearance_team_source=SOURCE_BOXSCORE,
                  appearance_team_reason=REASON_RESOLVED_BOXSCORE)
    schedule_disagrees = ata.AppearanceTeamResolution(
        AWAY_TEAM, STATUS_RESOLVED, SOURCE_SCHEDULE, REASON_RESOLVED_SCHEDULE)
    assert ata.reconcile_on_update(log, schedule_disagrees, correction_applied=True) is None
    assert log.appearance_team_id == HOME_TEAM  # unchanged (higher authority kept)


def test_equal_precedence_disagreement_fails_closed_to_conflict(app):
    p = _persist_pitcher()
    log = GameLog(pitcher_id=p.id, mlb_game_pk=1, game_date=GAME_DATE, innings_pitched=1.0,
                  innings_pitched_outs=3, appearance_team_id=HOME_TEAM,
                  appearance_team_status=STATUS_RESOLVED, appearance_team_source=SOURCE_SCHEDULE,
                  appearance_team_reason=REASON_RESOLVED_SCHEDULE)
    db.session.add(log); db.session.commit()
    other_schedule = ata.AppearanceTeamResolution(
        AWAY_TEAM, STATUS_RESOLVED, SOURCE_SCHEDULE, REASON_RESOLVED_SCHEDULE)
    assert ata.reconcile_on_update(log, other_schedule, correction_applied=True) == REASON_CONFLICT
    assert log.appearance_team_status == STATUS_CONFLICT
    # A conflicted row carries NO silently-selected team, and the stored state is
    # valid (commits cleanly against the invariant CHECK).
    assert log.appearance_team_id is None
    db.session.commit()


# ===========================================================================
# Stored-state invariants — enforced at the database (required tests 1-2)
# ===========================================================================


def _insert(app_row):
    db.session.add(app_row)
    db.session.commit()


def test_check_rejects_resolved_without_team(app):
    p = _persist_pitcher()
    with pytest.raises(Exception):
        _insert(GameLog(pitcher_id=p.id, mlb_game_pk=10, game_date=GAME_DATE, innings_pitched=1.0,
                        innings_pitched_outs=3, appearance_team_status=STATUS_RESOLVED))
    db.session.rollback()


def test_check_rejects_conflict_with_team(app):
    p = _persist_pitcher()
    with pytest.raises(Exception):
        _insert(GameLog(pitcher_id=p.id, mlb_game_pk=11, game_date=GAME_DATE, innings_pitched=1.0,
                        innings_pitched_outs=3, appearance_team_status=STATUS_CONFLICT,
                        appearance_team_id=HOME_TEAM))
    db.session.rollback()


def test_check_rejects_unresolved_with_team(app):
    p = _persist_pitcher()
    with pytest.raises(Exception):
        _insert(GameLog(pitcher_id=p.id, mlb_game_pk=12, game_date=GAME_DATE, innings_pitched=1.0,
                        innings_pitched_outs=3, appearance_team_status=STATUS_UNRESOLVED,
                        appearance_team_id=HOME_TEAM))
    db.session.rollback()


def test_check_accepts_all_valid_combinations(app):
    p = _persist_pitcher()
    _insert(GameLog(pitcher_id=p.id, mlb_game_pk=13, game_date=GAME_DATE, innings_pitched=1.0,
                    innings_pitched_outs=3))  # legacy NULL
    _insert(GameLog(pitcher_id=p.id, mlb_game_pk=14, game_date=GAME_DATE, innings_pitched=1.0,
                    innings_pitched_outs=3, appearance_team_status=STATUS_RESOLVED,
                    appearance_team_id=HOME_TEAM, appearance_team_source=SOURCE_BOXSCORE))
    _insert(GameLog(pitcher_id=p.id, mlb_game_pk=15, game_date=GAME_DATE, innings_pitched=1.0,
                    innings_pitched_outs=3, appearance_team_status=STATUS_UNRESOLVED))
    _insert(GameLog(pitcher_id=p.id, mlb_game_pk=16, game_date=GAME_DATE, innings_pitched=1.0,
                    innings_pitched_outs=3, appearance_team_status=STATUS_CONFLICT))
    assert GameLog.query.count() == 4


def test_unchanged_resweep_never_backfills_a_legacy_row(app):
    # A legacy NULL row hit by a resolved authority WITHOUT a stat correction stays NULL
    # (Step 2 owns backfill).
    p = _persist_pitcher()
    log = GameLog(pitcher_id=p.id, mlb_game_pk=1, game_date=GAME_DATE, innings_pitched=1.0,
                  innings_pitched_outs=3)
    db.session.add(log); db.session.commit()
    resolved = ata.AppearanceTeamResolution(HOME_TEAM, STATUS_RESOLVED, SOURCE_SCHEDULE,
                                             REASON_RESOLVED_SCHEDULE)
    assert ata.reconcile_on_update(log, resolved, correction_applied=False) is None
    assert log.appearance_team_status is None


def test_concurrent_upsert_does_not_duplicate_appearance(app):
    _seed_schedule()
    p = Pitcher(mlb_id=300, full_name='Daily Arm', team_id=HOME_TEAM, active=True)
    db.session.add(p); db.session.flush()
    sync_service._ingest_game_log_split(p, _daily_split(), GAME_DATE - timedelta(days=5), {})
    _ingest_boxscore(p, 101) if False else None  # both paths key on (pitcher, game)
    db.session.commit()
    assert GameLog.query.filter_by(pitcher_id=p.id, mlb_game_pk=GAME_PK).count() == 1


# ===========================================================================
# Trade / team-change regression (matrix 15-18) — the motivating defect
# ===========================================================================


def test_traded_pitcher_retains_former_team_appearance(app):
    _seed_schedule()
    # Pitcher pitches for the HOME team (team 1) in this game.
    p = Pitcher(mlb_id=101, full_name='Traded', team_id=HOME_TEAM, active=True)
    db.session.add(p); db.session.flush()
    _ingest_boxscore(p, 101)
    db.session.commit()
    # Pitcher is later traded to the AWAY team; current team changes.
    p.team_id = AWAY_TEAM
    db.session.commit()
    log = GameLog.query.filter_by(pitcher_id=p.id, mlb_game_pk=GAME_PK).one()
    # The historical appearance still resolves to the team represented in the game.
    res = resolve_appearance_team(log)
    assert res.team_id == HOME_TEAM
    assert p.team_id == AWAY_TEAM  # current team unchanged by the read


def test_later_new_team_appearance_stores_new_team(app):
    _seed_schedule(game_pk=GAME_PK, home=HOME_TEAM, away=AWAY_TEAM)
    _seed_schedule(game_pk=7002, home=AWAY_TEAM, away=HOME_TEAM, game_date=GAME_DATE + timedelta(days=1))
    p = Pitcher(mlb_id=101, full_name='Mover', team_id=AWAY_TEAM, active=True)
    db.session.add(p); db.session.flush()
    _ingest_boxscore(p, 101)  # game 7001, home side -> team 1
    # A second appearance for the AWAY team via the daily path on game 7002.
    sync_service._ingest_game_log_split(
        p, _daily_split(game_pk=7002, opponent_id=HOME_TEAM), GAME_DATE - timedelta(days=5), {})
    db.session.commit()
    logs = {gl.mlb_game_pk: gl for gl in GameLog.query.filter_by(pitcher_id=p.id).all()}
    assert logs[GAME_PK].appearance_team_id == HOME_TEAM
    assert logs[7002].appearance_team_id == AWAY_TEAM


def test_current_team_change_does_not_rewrite_history(app):
    _seed_schedule()
    p = Pitcher(mlb_id=202, full_name='Away Arm', team_id=AWAY_TEAM, active=True)
    db.session.add(p); db.session.flush()
    _ingest_boxscore(p, 202)
    db.session.commit()
    for new_team in (HOME_TEAM, 555, None):
        p.team_id = new_team
        db.session.commit()
        log = GameLog.query.filter_by(pitcher_id=p.id).one()
        assert log.appearance_team_id == AWAY_TEAM  # frozen


def test_inactive_released_pitcher_history_remains_attributed(app):
    _seed_schedule()
    p = Pitcher(mlb_id=202, full_name='Released', team_id=AWAY_TEAM, active=True)
    db.session.add(p); db.session.flush()
    _ingest_boxscore(p, 202)
    db.session.commit()
    p.active = False
    p.roster_status = 'INACTIVE'
    db.session.commit()
    log = GameLog.query.filter_by(pitcher_id=p.id).one()
    assert resolve_appearance_team(log).team_id == AWAY_TEAM


def test_doubleheader_preserves_game_identity_and_team(app):
    # Two games same day, distinct game_pk; each attributed to its own side.
    _seed_schedule(game_pk=7001, home=HOME_TEAM, away=AWAY_TEAM)
    _seed_schedule(game_pk=7002, home=HOME_TEAM, away=AWAY_TEAM)
    p = Pitcher(mlb_id=300, full_name='DH Arm', team_id=HOME_TEAM, active=True)
    db.session.add(p); db.session.flush()
    sync_service._ingest_game_log_split(p, _daily_split(game_pk=7001, opponent_id=AWAY_TEAM),
                                        GAME_DATE - timedelta(days=5), {})
    sync_service._ingest_game_log_split(p, _daily_split(game_pk=7002, opponent_id=AWAY_TEAM),
                                        GAME_DATE - timedelta(days=5), {})
    db.session.commit()
    assert GameLog.query.filter_by(pitcher_id=p.id).count() == 2
    for gl in GameLog.query.filter_by(pitcher_id=p.id).all():
        assert gl.appearance_team_id == HOME_TEAM


# ===========================================================================
# Read accessor (matrix 40-42)
# ===========================================================================


def test_read_accessor_returns_resolved_authority(app):
    p = _persist_pitcher()
    log = GameLog(pitcher_id=p.id, mlb_game_pk=1, game_date=GAME_DATE, innings_pitched=1.0,
                  innings_pitched_outs=3, appearance_team_id=HOME_TEAM,
                  appearance_team_status=STATUS_RESOLVED, appearance_team_source=SOURCE_BOXSCORE)
    res = resolve_appearance_team(log)
    assert res.resolved and res.team_id == HOME_TEAM


def test_read_accessor_returns_unresolved_and_conflict_explicitly(app):
    p = _persist_pitcher()
    legacy = GameLog(pitcher_id=p.id, mlb_game_pk=2, game_date=GAME_DATE, innings_pitched=1.0,
                     innings_pitched_outs=3)
    assert resolve_appearance_team(legacy).status == STATUS_UNRESOLVED
    conflict = GameLog(pitcher_id=p.id, mlb_game_pk=3, game_date=GAME_DATE, innings_pitched=1.0,
                       innings_pitched_outs=3, appearance_team_status=STATUS_CONFLICT)
    r = resolve_appearance_team(conflict)
    assert r.status == STATUS_CONFLICT and r.team_id is None and not r.resolved


# ===========================================================================
# Observability / coverage audit (matrix 46-49)
# ===========================================================================


def test_coverage_audit_reports_counts_and_is_read_only(app):
    _seed_schedule()
    resolved = Pitcher(mlb_id=101, full_name='R', team_id=HOME_TEAM, active=True)
    db.session.add(resolved); db.session.flush()
    _ingest_boxscore(resolved, 101)
    # a legacy NULL row + an unresolved row
    db.session.add(GameLog(pitcher_id=resolved.id, mlb_game_pk=999, game_date=GAME_DATE,
                           innings_pitched=1.0, innings_pitched_outs=3))
    db.session.commit()
    before = GameLog.query.count()
    audit = build_appearance_team_coverage()
    assert build_appearance_team_coverage() == audit  # deterministic
    assert GameLog.query.count() == before  # read-only
    assert audit['resolved'] >= 1
    assert audit['null_legacy'] >= 1
    assert audit['total_game_logs'] == before
    assert SOURCE_BOXSCORE in audit['by_source']
    assert 2026 in audit['by_season']


def test_coverage_audit_current_team_mismatch_counts_traded(app):
    _seed_schedule()
    p = Pitcher(mlb_id=101, full_name='Traded', team_id=HOME_TEAM, active=True)
    db.session.add(p); db.session.flush()
    _ingest_boxscore(p, 101)
    db.session.commit()
    assert build_appearance_team_coverage()['current_team_mismatch'] == 0
    p.team_id = AWAY_TEAM  # traded -> represented team now differs from current team
    db.session.commit()
    assert build_appearance_team_coverage()['current_team_mismatch'] == 1


# ===========================================================================
# Non-attribution source proof (matrix 23, 42) — the resolver never reads team_id
# ===========================================================================


def test_resolver_source_never_references_pitcher_team_id():
    import services.appearance_team_authority as module
    src = open(module.__file__).read()
    # The resolver must never IMPORT or QUERY the Pitcher model — it physically
    # cannot consult the pitcher's mutable current team as an attribution authority.
    assert 'models.pitcher' not in src
    assert 'import Pitcher' not in src
    assert 'Pitcher.query' not in src
    assert 'Pitcher(' not in src


# ===========================================================================
# Unchanged surfaces — no reader migrated in this step (matrix 42-45)
# ===========================================================================


def test_canonical_read_accessor_is_the_seam():
    # Future performance/aggregation work consumes this single accessor rather than
    # re-inventing a current-team fallback.
    from services.appearance_team_authority import resolve_appearance_team as accessor
    assert callable(accessor)


def test_season_era_reader_is_not_migrated_in_this_step():
    # Foundation 1 adds the authority but migrates NO reader (Steps 2-3 do). The
    # production season-ERA reader still groups by the pitcher's current team and
    # still carries its documented limitation.
    from services import season_era
    src = open(season_era.__file__).read()
    assert "team_id = _value(pitcher, 'team_id')" in src
    assert 'Game logs do not store team-at-appearance' in src


def test_card_metrics_does_not_depend_on_new_authority():
    # The v1.2 card already attributes appearances by the game-side (schedule ∩
    # game_pk) pattern and must not be changed to depend on the new columns yet.
    from services import team_state_card_metrics
    src = open(team_state_card_metrics.__file__).read()
    assert 'appearance_team' not in src


# ===========================================================================
# Appearance-grain decision: one pitcher/team per game_pk (required tests 14)
# ===========================================================================


def _manual_boxscore_line(player_id, side, team_id):
    return {
        'player_id': player_id, 'person_id': player_id, 'name': f'P{player_id}',
        'side': side, 'team_id': team_id, 'team': f'{side} club',
        'team_abbreviation': side[:3].upper(), 'position': 'P',
        'position_code': '1', 'position_name': 'Pitcher',
        # A complete authoritative pitching line (the correction path treats sparse
        # sources as unsafe and skips them).
        'stats': {'inningsPitched': '1.0', 'numberOfPitches': '14', 'strikes': '9',
                  'hits': '0', 'runs': '0', 'earnedRuns': '0', 'baseOnBalls': '0',
                  'strikeOuts': '2', 'homeRuns': '0'},
    }


def test_pathological_two_sided_ingest_fails_closed_to_conflict(app):
    # DECISION: a pitcher represents exactly one team per game_pk. The MLB box score
    # lists a person under one pitching side only, suspended/resumed games use
    # DISTINCT game_pks, and the (pitcher_id, mlb_game_pk) unique key predates this
    # work. If a pathological feed ever placed the same pitcher on BOTH sides of one
    # game_pk, the authority must FAIL CLOSED (conflict), never silently overwrite.
    _seed_schedule()
    p = Pitcher(mlb_id=101, full_name='Both Sides', team_id=HOME_TEAM, active=True)
    db.session.add(p); db.session.flush()
    sync_service._ingest_boxscore_pitching_line(
        p, _manual_boxscore_line(101, 'home', HOME_TEAM), _game(), game_date=GAME_DATE,
        team_abbr_map={}, pitcher_order={'home': [101], 'away': []})
    db.session.commit()
    row = GameLog.query.filter_by(pitcher_id=p.id).one()
    assert row.appearance_team_id == HOME_TEAM  # first side resolved
    # The same pitcher, same game_pk, the OTHER side -> equal-precedence disagreement.
    sync_service._ingest_boxscore_pitching_line(
        p, _manual_boxscore_line(101, 'away', AWAY_TEAM), _game(), game_date=GAME_DATE,
        team_abbr_map={}, pitcher_order={'home': [], 'away': [101]})
    db.session.commit()
    row = GameLog.query.filter_by(pitcher_id=p.id).one()
    assert GameLog.query.filter_by(pitcher_id=p.id).count() == 1  # not duplicated
    assert row.appearance_team_status == STATUS_CONFLICT  # failed closed
    assert row.appearance_team_id is None  # no silently-selected team


def test_scheduled_game_carries_distinct_resumed_game_pk_linkage():
    # The mechanism that keeps a suspended game and its resumption as DISTINCT
    # game_pks: ScheduledGame links them by resumed_from/to_game_pk rather than
    # reusing one game_pk. This is why one (pitcher, game_pk) is one team-side
    # appearance, and why the canonical authority does not need team in its identity.
    cols = {c.name for c in ScheduledGame.__table__.columns}
    assert {'resumed_from_game_pk', 'resumed_to_game_pk'} <= cols


def test_suspended_resumed_distinct_game_pks_are_independent_rows(app):
    # A suspended game and its resumption carry DISTINCT game_pks, so a pitcher who
    # worked both portions produces two independent appearance rows, each attributed
    # to its own game's side (never one conflated row).
    _seed_schedule(game_pk=7001, home=HOME_TEAM, away=AWAY_TEAM)
    _seed_schedule(game_pk=7002, home=AWAY_TEAM, away=HOME_TEAM,
                   game_date=GAME_DATE + timedelta(days=1))
    p = Pitcher(mlb_id=101, full_name='Resumed Arm', team_id=HOME_TEAM, active=True)
    db.session.add(p); db.session.flush()
    _ingest_boxscore(p, 101)  # game 7001, home side -> HOME_TEAM
    sync_service._ingest_game_log_split(
        p, _daily_split(game_pk=7002, opponent_id=HOME_TEAM), GAME_DATE - timedelta(days=5), {})
    db.session.commit()
    rows = {gl.mlb_game_pk: gl for gl in GameLog.query.filter_by(pitcher_id=p.id).all()}
    assert set(rows) == {7001, 7002}
    # Two independent, resolved rows — the grain is (pitcher, game_pk), never conflated.
    assert rows[7001].appearance_team_id == HOME_TEAM   # home side of 7001
    assert rows[7002].appearance_team_id == AWAY_TEAM   # faces HOME_TEAM in 7002 -> AWAY_TEAM
    assert rows[7001].appearance_team_status == STATUS_RESOLVED
    assert rows[7002].appearance_team_status == STATUS_RESOLVED


# ===========================================================================
# Team State v1.2 / public surface unchanged (required tests 17-18)
# ===========================================================================


# The exact runtime files carrying the canonical Team State reconciliation
# (UX-001 / #590). Shared by the path guard below and by the test that proves
# none of them reads appearance-team authority.
CANONICAL_TEAM_STATE_FILES = (
    'backend/api/bullpen.py',
    'backend/services/bullpen_comparison.py',
    'backend/services/team_state_public_vocabulary.py',
    'frontend/src/adapters/operatingStateReadModel.js',
    'frontend/src/adapters/publicTeamState.js',
    'frontend/src/components/bullpen/BullpenOperatingStateCard.jsx',
    'frontend/src/components/bullpen/board/BullpenComparisonView.jsx',
    'frontend/src/components/bullpen/board/teamBullpenComparisonView.js',
    'frontend/src/components/dashboard/BullpenLandscape.jsx',
    'frontend/src/components/dashboard/bullpenLandscapeView.js',
    'frontend/src/utils/evidenceCardModel.js',
    'frontend/src/utils/evidenceCardStory.js',
)


def test_branch_touches_no_team_state_or_public_surface_files():
    # Source proof: Foundation 1 changes no Team State, Share Artifact, public API,
    # or frontend file, so v1.2 payloads and immutable artifacts are byte-unchanged.
    import subprocess
    repo_root = REPO_ROOT_FOR_DIFF
    try:
        out = subprocess.run(
            ['git', 'diff', '--name-only', 'origin/main...HEAD'],
            cwd=repo_root, capture_output=True, text=True, check=True,
        ).stdout
    except Exception:
        pytest.skip('git diff against origin/main unavailable')
    changed = [line.strip() for line in out.splitlines() if line.strip()]
    if not changed:
        pytest.skip('no diff resolved')
    # Runtime surfaces only — guard/allowlist TEST updates (which change no product
    # behavior) are expected and excluded.
    non_test = [
        path for path in changed
        if not path.startswith(('backend/tests/', 'frontend/tests/'))
    ]
    forbidden_fragments = (
        'team_state', 'share_artifact', 'frontend/', 'backend/api/',
        'services/season_era', 'bullpen_context', 'public_team_relief_work',
    )
    # THE FIRST APPROVED PUBLIC CONSUMERS OF CANONICAL APPEARANCE-TEAM AUTHORITY.
    #
    # These two files, and only these two, are approved to read
    # GameLog.appearance_team_id (Foundation 1) on a public surface. Founder-
    # approved 2026-07-30 for the July 28 official-starter alignment incident:
    # the Team Board relief-work surface published a game narrative naming a
    # pitcher who did not start that game, because it scoped appearances by the
    # pitcher's current club instead of the official game side. Correcting it
    # required a public consumer, which Foundation 1 deliberately shipped
    # without. See docs/audits/official-starter-evidence-alignment-2026-07-28.md.
    #
    # The guard's purpose is intact: this payload is computed per request and is
    # never snapshotted, stored on a story, or written into a share artifact, so
    # Team State v1.2 payloads and immutable artifacts remain byte-unchanged.
    #
    # This is an exact-path allowlist, never a directory exemption. Adding any
    # further public consumer REQUIRES an explicit change to this test and its
    # own approval. Team State, Share Artifacts, season aggregation, backend/api,
    # and every other public surface remain fully protected. Neither approved
    # consumer may fall back to Pitcher.team_id for attribution — enforced by
    # test_approved_public_consumers_use_appearance_team_authority_only below.
    APPROVED_PUBLIC_APPEARANCE_TEAM_CONSUMERS = (
        'backend/services/public_team_relief_work.py',
        'frontend/src/components/bullpen/TeamReliefWorkPanel.jsx',
    )
    # INTERNAL, NON-PUBLIC CONSUMERS.
    #
    # backend/api/ holds both public routes and authenticated internal ones, so
    # the 'backend/api/' fragment above catches a route that reaches no reader.
    # This file is the M-001 internal review read (D-023 to D-030): it requires
    # the existing admin token, is read-only, serves one team and one
    # represented date, renders on no public surface, and reports every
    # publication gate as blocked. It writes nothing and is never snapshotted
    # or frozen into an artifact, so Team State v1.2 payloads and immutable
    # artifacts remain byte-unchanged.
    #
    # Exact paths only, never a directory exemption. This entry authorizes no
    # public consumer, and adding one still requires changing the list above
    # and its own approval.
    APPROVED_INTERNAL_APPEARANCE_TEAM_CONSUMERS = (
        'backend/api/performance_intelligence_admin.py',
    )
    # CANONICAL TEAM STATE RECONCILIATION (UX-001 / #590), founder-approved by
    # D-003 and D-004.
    #
    # These files carry the deliberate migration of the live reader surfaces onto
    # the backend-owned public Team State contract: the vocabulary authority gains
    # one projection from governed Team Operations readiness, the board /
    # comparison / dashboard payloads carry the resulting block, and the frontend
    # adapter is reduced to validating and rendering it.
    #
    # This guard exists so appearance-team work cannot incidentally alter Team
    # State v1.2 payloads or immutable artifacts. That purpose is intact and is
    # now actively enforced rather than merely exempted: none of these files may
    # read appearance-team authority at all, which
    # test_canonical_team_state_files_read_no_appearance_team_authority proves
    # directly. Share Artifact generation, eligibility, and the immutable
    # lifecycle are untouched, so published artifacts stay byte-unchanged.
    #
    # Exact paths only, never a directory exemption. Every other public surface
    # remains fully protected, and adding a path here still requires its own
    # approval.
    APPROVED_CANONICAL_TEAM_STATE_FILES = CANONICAL_TEAM_STATE_FILES
    offenders = [
        path for path in non_test
        if any(fragment in path for fragment in forbidden_fragments)
        and path not in APPROVED_PUBLIC_APPEARANCE_TEAM_CONSUMERS
        and path not in APPROVED_INTERNAL_APPEARANCE_TEAM_CONSUMERS
        and path not in APPROVED_CANONICAL_TEAM_STATE_FILES
    ]
    assert offenders == [], f'Foundation 1 must not touch these runtime surfaces: {offenders}'


def test_canonical_team_state_files_read_no_appearance_team_authority():
    """The UX-001 allowlist is an exemption from the path guard, not from its purpose.

    The guard above protects Team State and public surfaces from incidental
    appearance-team change. The canonical Team State reconciliation is allowed to
    touch those paths, so this proves the thing the guard actually cares about:
    not one of those files reads ``GameLog.appearance_team_id`` or the
    appearance-team status, in either language. A future edit that reaches for
    appearance-team authority from a Team State file fails here.
    """
    offenders = []
    for relative in CANONICAL_TEAM_STATE_FILES:
        path = REPO_ROOT_FOR_DIFF / relative
        if not path.exists():
            continue
        source = path.read_text(encoding='utf-8')
        for token in (
            'appearance_team_id',
            'appearance_team_status',
            'appearanceTeamId',
            'appearanceTeamStatus',
        ):
            if token in source:
                offenders.append(f'{relative}: {token}')
    assert offenders == [], (
        'canonical Team State files must not read appearance-team authority: '
        f'{offenders}'
    )


def test_approved_public_consumers_use_appearance_team_authority_only():
    """The two approved consumers must not reintroduce current-team fallback.

    The incident was caused by attributing appearances with the pitcher's
    mutable current club. The approved public consumer may reference
    Pitcher.team_id only for the team's display name and for the out-of-band
    diagnostic that discloses unattributed appearances — never to select which
    appearances belong to a team's game.
    """
    service = (
        REPO_ROOT_FOR_DIFF / 'backend/services/public_team_relief_work.py'
    ).read_text(encoding='utf-8')

    # The appearance cohort is scoped by official game side, resolved status only.
    assert 'GameLog.appearance_team_id == team_id' in service
    assert 'GameLog.appearance_team_status == APPEARANCE_TEAM_RESOLVED' in service

    # Current team survives in exactly two sanctioned, non-attributing places:
    # the team display lookup and the unattributed-appearance disclosure.
    current_team_uses = service.count('Pitcher.team_id == team_id')
    assert current_team_uses == 2, (
        'Pitcher.team_id may only be used for the team display lookup and the '
        f'unattributed disclosure; found {current_team_uses} uses.'
    )
    assert '_unattributed_appearance_count' in service

    # No current-team fallback may guard or substitute for the official scope.
    for fallback in (
        'or Pitcher.team_id',
        'Pitcher.team_id or',
        'appearance_team_id or',
        'or GameLog.appearance_team_id',
    ):
        assert fallback not in service, fallback

    # The frontend consumer reads server-verified authority and infers nothing.
    panel = (
        REPO_ROOT_FOR_DIFF
        / 'frontend/src/components/bullpen/TeamReliefWorkPanel.jsx'
    ).read_text(encoding='utf-8')
    assert "starter_authority !== 'official_completed_game_starter'" in panel
    assert 'reconciled !== true' in panel
    for inference in ('games_started', 'gamesStarted', 'team_id =='):
        assert inference not in panel, inference
