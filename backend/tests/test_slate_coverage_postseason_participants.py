"""Postseason participant changes must not leave phantom schedule rows.

Production (Daily Primary, SyncRun 93096, 2026-09-30): candidate snapshot 4130
(``data_through`` 2026-09-29, the four Wild Card Game 1s) was withheld with
``dashboard_snapshot_slate_coverage_incomplete`` although ingestion reported no
errors and the Sep 29 schedule refreshes succeeded. The store-time stale
finality refresh logged ``candidate_games=3 games_seen=4 games_ingested=4
rows_created=0 rows_updated=8``.

MLB lists an undecided postseason matchup under its final gamePk with a
placeholder team id, then fills in the real club under the same gamePk. The
same window's slate refresh accepted every Division Series game (16 seen, 16
``slate_games`` updated) although those opponents were still undecided, and
``slate_games`` accepts a game only when both team ids are positive, so the
placeholders carry positive ids. ``scheduled_games`` is keyed by
(team_id, game_pk): the real club's row is created and later updated to final,
but the placeholder's row is never addressed again and stays ``scheduled``.
Slate coverage groups every row of a gamePk, so {final, final, scheduled}
collapses to a non-final game; the game-driven planner reads the same rows as a
finality conflict. Three of the four Game 1s carried such a row, so three
distinct non-final gamePks were refresh candidates while MLB returned four
games whose eight real rows were rewritten and whose three phantom rows were not.

The fixture below replays that history through the real ingestion writer. Game
pks, placeholder ids and all matchups other than the documented Cubs at Padres
game are synthetic.
"""

import os
from datetime import date, datetime

import pytest
from sqlalchemy import text

from api import bullpen as bullpen_api
from models.dashboard_snapshot import DashboardSnapshot
from models.postgame_processed_game import PostgameProcessedGame
from models.scheduled_game import ScheduledGame
from models.slate_game import SlateGame
from models.sync_run import SyncRun
from services import dashboard_snapshot, game_ingestion_planner, schedule_ingestion, slate_coverage
from services import sync as sync_service
from services.schedule_ingestion import ingest_games
from tests.test_schedule_ingestion import (  # noqa: F401  (fenced PostgreSQL fixtures)
    _adopt_like_sync_pipeline,
    _fresh_rows,
    fenced_app,
    fenced_database_url,
)
from tests.test_slate_coverage import _marker, app  # noqa: F401
from utils.db import db


SLATE = date(2026, 9, 29)
CUBS, PADRES = 112, 135
# Four Wild Card Game 1s: (game_pk, home, away).
GAMES = (
    (813001, PADRES, CUBS),
    (813002, 111, 117),
    (813003, 147, 116),
    (813004, 143, 121),
)
# Before the bracket settled MLB listed one side of three games as a
# placeholder club. The fourth game's matchup was already decided.
PLACEHOLDERS = {813001: ('away', 9001), 813002: ('away', 9002), 813003: ('home', 9003)}

FINAL = ('F', 'Final', 'Final')
SCHEDULED = ('S', 'Scheduled', 'Preview')


def _mlb_game(game_pk, home_id, away_id, status=SCHEDULED):
    code, detailed, abstract = status
    return {
        'gamePk': game_pk,
        'gameType': 'F',
        'officialDate': SLATE.isoformat(),
        'gameDate': '2026-09-29T20:08:00Z',
        'doubleHeader': 'N',
        'gameNumber': 1,
        'seriesGameNumber': 1,
        'gamesInSeries': 3,
        'status': {'statusCode': code, 'detailedState': detailed, 'abstractGameState': abstract},
        'teams': {
            'home': {'team': {'id': home_id}},
            'away': {'team': {'id': away_id}},
        },
    }


def _pre_clinch_slate():
    """What MLB listed for Sep 29 before the bracket settled."""
    games = []
    for game_pk, home, away in GAMES:
        side, placeholder = PLACEHOLDERS.get(game_pk, (None, None))
        games.append(_mlb_game(
            game_pk,
            placeholder if side == 'home' else home,
            placeholder if side == 'away' else away,
        ))
    return games


def _slate(status):
    return [_mlb_game(game_pk, home, away, status) for game_pk, home, away in GAMES]


def _mark_all_fully_processed():
    for game_pk, _home, _away in GAMES:
        _marker(game_pk, SLATE)


def _seed_legacy_phantom_rows():
    """The production state the pre-fix writer left behind on Sep 30.

    Real rows are final; each placeholder row kept the pre-clinch status.
    """
    ingest_games(_slate(FINAL), source='daily_finality_preflight')
    for game_pk, (side, placeholder) in PLACEHOLDERS.items():
        home, away = next((h, a) for pk, h, a in GAMES if pk == game_pk)
        db.session.add(ScheduledGame(
            team_id=placeholder,
            game_pk=game_pk,
            game_date=SLATE,
            home_away=side,
            opponent_team_id=home if side == 'away' else away,
            game_type='F',
            status_code='S',
            status_state=ScheduledGame.STATE_SCHEDULED,
            source='daily_slate_schedule',
        ))
    db.session.commit()


def _rows_by_game():
    rows = {}
    for row in ScheduledGame.query.filter(ScheduledGame.game_date == SLATE).all():
        rows.setdefault(row.game_pk, set()).add((row.team_id, row.status_state))
    return rows


def _payload():
    return {
        'freshness': {
            'data_through': SLATE.isoformat(),
            'availability_reference_date': '2026-09-30',
            'sync_status': 'success',
        },
    }


def _stub_mlb(monkeypatch, games):
    calls = []

    def get_schedule(start_date=None, end_date=None, team_id=None):
        calls.append((start_date, end_date))
        return [game for game in games if game['officialDate'] >= start_date
                and game['officialDate'] <= end_date]

    monkeypatch.setattr(schedule_ingestion.mlb_client, 'get_schedule', get_schedule)
    return calls


# ── 1. Schedule authority: the writer keeps exactly the participants ────────

def test_bracket_settlement_leaves_exactly_the_two_participants_per_game(app):
    with app.app_context():
        ingest_games(_pre_clinch_slate(), source='daily_slate_schedule')
        assert {pk: len(rows) for pk, rows in _rows_by_game().items()} == {
            pk: 2 for pk, _h, _a in GAMES
        }

        settled = ingest_games(_slate(SCHEDULED), source='daily_slate_schedule')
        assert settled['rows_created'] == 3   # the three real clubs
        assert settled['rows_retired'] == 3   # the three placeholders
        final = ingest_games(_slate(FINAL), source='daily_finality_preflight')
        db.session.commit()

        assert final['rows_created'] == 0
        assert final['rows_updated'] == 8
        assert final['rows_retired'] == 0
        assert _rows_by_game() == {
            pk: {(home, 'final'), (away, 'final')} for pk, home, away in GAMES
        }
        # The game-centric slate authority always agreed.
        assert {
            (row.game_pk, row.home_team_id, row.away_team_id)
            for row in SlateGame.query.all()
        } == set(GAMES)


def test_the_planner_sees_four_final_games_and_no_finality_conflict(app):
    with app.app_context():
        ingest_games(_pre_clinch_slate(), source='daily_slate_schedule')
        ingest_games(_slate(SCHEDULED), source='daily_slate_schedule')
        ingest_games(_slate(FINAL), source='daily_finality_preflight')
        db.session.commit()

        plan = game_ingestion_planner.plan_game_work(date(2026, 9, 30))

    assert plan['planned_game_pks'] == [pk for pk, _h, _a in GAMES]
    assert plan['finality_conflicts'] == []


# ── 2-4. Payload and publication validation observe one complete cohort ────

def test_natural_history_publishes_the_complete_wild_card_slate(app, monkeypatch):
    calls = _stub_mlb(monkeypatch, _slate(FINAL))
    with app.app_context():
        ingest_games(_pre_clinch_slate(), source='daily_slate_schedule')
        ingest_games(_slate(SCHEDULED), source='daily_slate_schedule')
        ingest_games(_slate(FINAL), source='daily_finality_preflight')
        _mark_all_fully_processed()
        db.session.commit()

        assessed = slate_coverage.compute_slate_coverage(SLATE, sync_status='success')
        stored = dashboard_snapshot._payload_with_slate_coverage(
            {**_payload(), 'freshness': {**_payload()['freshness'], 'slate_coverage': assessed}},
            refresh_stale_finality=True,
            commit=False,
        )

    # Nothing was non-final, so publication never re-fetched: payload assembly
    # and validation read the same schedule state.
    assert calls == []
    coverage = stored['freshness']['slate_coverage']
    assert coverage == assessed
    assert coverage['games_scheduled'] == 4
    assert coverage['games_final'] == 4
    assert coverage['games_fully_ingested'] == 4
    assert coverage['reason_codes'] == ['slate_complete']
    assert dashboard_snapshot._payload_slate_coverage_unavailable_reason(stored) is None


def test_production_replay_store_time_refresh_retires_phantoms_and_publishes(app, monkeypatch, caplog):
    """SyncRun 93096: the exact state and refresh counts production logged."""
    calls = _stub_mlb(monkeypatch, _slate(FINAL))
    with app.app_context():
        _seed_legacy_phantom_rows()
        _mark_all_fully_processed()
        db.session.commit()

        before = slate_coverage.compute_slate_coverage(SLATE, sync_status='success')
        assert before['games_final'] == 1
        assert 'scheduled_games_not_final' in before['reason_codes']
        assert dashboard_snapshot._payload_slate_coverage_unavailable_reason({
            'freshness': {**_payload()['freshness'], 'slate_coverage': before},
        }) == 'dashboard_snapshot_slate_coverage_incomplete'

        refresh = schedule_ingestion.refresh_non_final_games_for_slate(
            SLATE, source='snapshot_slate_finality_refresh', commit=False,
        )
        assert refresh['candidate_game_pks'] == sorted(PLACEHOLDERS)
        assert refresh['summary']['games_seen'] == 4
        assert refresh['summary']['games_ingested'] == 4
        assert refresh['summary']['rows_created'] == 0
        assert refresh['summary']['rows_updated'] == 8
        assert refresh['summary']['rows_retired'] == 3
        assert refresh['summary']['errors'] == 0

        stored = dashboard_snapshot._payload_with_slate_coverage(
            _payload(), refresh_stale_finality=True, commit=False,
        )
        rows = _rows_by_game()

    assert calls == [(SLATE.isoformat(), SLATE.isoformat())]
    assert rows == {pk: {(home, 'final'), (away, 'final')} for pk, home, away in GAMES}
    coverage = stored['freshness']['slate_coverage']
    assert coverage['games_scheduled'] == 4
    assert coverage['games_final'] == 4
    assert coverage['complete_enough_to_publish'] is True
    assert dashboard_snapshot._payload_slate_coverage_unavailable_reason(stored) is None


# ── 5-6. Genuinely incomplete coverage still fails closed ──────────────────

def test_a_wild_card_game_without_ingested_appearances_still_withholds(app, monkeypatch):
    _stub_mlb(monkeypatch, _slate(FINAL))
    with app.app_context():
        _seed_legacy_phantom_rows()
        for game_pk, _home, _away in GAMES[:3]:
            _marker(game_pk, SLATE)
        _marker(GAMES[3][0], SLATE, status=PostgameProcessedGame.STATUS_INCOMPLETE)
        db.session.commit()

        stored = dashboard_snapshot._payload_with_slate_coverage(
            _payload(), refresh_stale_finality=True, commit=False,
        )

    coverage = stored['freshness']['slate_coverage']
    assert coverage['games_final'] == 4
    assert 'postgame_markers_incomplete' in coverage['reason_codes']
    assert dashboard_snapshot._payload_slate_coverage_unavailable_reason(stored) == (
        'dashboard_snapshot_slate_coverage_incomplete'
    )


def test_a_game_mlb_still_reports_unfinished_still_withholds(app, monkeypatch):
    games = _slate(FINAL)
    games[0] = _mlb_game(*GAMES[0], status=('U', 'Suspended: Rain', 'Live'))
    _stub_mlb(monkeypatch, games)
    with app.app_context():
        _seed_legacy_phantom_rows()
        _mark_all_fully_processed()
        db.session.commit()

        stored = dashboard_snapshot._payload_with_slate_coverage(
            _payload(), refresh_stale_finality=True, commit=False,
        )
        rows = _rows_by_game()

    # The phantom is gone, but the real suspension is authoritative and blocks.
    assert rows[813001] == {(PADRES, 'suspended'), (CUBS, 'suspended')}
    coverage = stored['freshness']['slate_coverage']
    assert 'suspended_games_not_final' in coverage['reason_codes']
    assert dashboard_snapshot._payload_slate_coverage_unavailable_reason(stored) == (
        'dashboard_snapshot_slate_coverage_incomplete'
    )


@pytest.mark.parametrize('missing_side', ['home', 'away'])
def test_nothing_is_retired_when_mlb_does_not_name_both_participants(app, monkeypatch, missing_side):
    games = _slate(FINAL)
    game_pk, home, away = GAMES[0]
    games[0]['teams'][missing_side] = {'team': {}}
    _stub_mlb(monkeypatch, games)
    with app.app_context():
        _seed_legacy_phantom_rows()
        _mark_all_fully_processed()
        db.session.commit()

        stored = dashboard_snapshot._payload_with_slate_coverage(
            _payload(), refresh_stale_finality=True, commit=False,
        )
        rows = _rows_by_game()

    assert (9001, 'scheduled') in rows[game_pk]
    assert dashboard_snapshot._payload_slate_coverage_unavailable_reason(stored) == (
        'dashboard_snapshot_slate_coverage_incomplete'
    )


def test_a_doubleheader_keeps_both_games_rows(app):
    first = _mlb_game(813101, PADRES, CUBS, FINAL)
    second = {**_mlb_game(813102, PADRES, CUBS, FINAL), 'doubleHeader': 'S', 'gameNumber': 2}
    with app.app_context():
        summary = ingest_games([first, second], source='test')
        db.session.commit()
        rows = _rows_by_game()

    assert summary['rows_retired'] == 0
    assert rows == {
        813101: {(PADRES, 'final'), (CUBS, 'final')},
        813102: {(PADRES, 'final'), (CUBS, 'final')},
    }


# ── Production PostgreSQL: the fenced Daily path (SyncRun 93096 shape) ─────


def test_fenced_daily_preflight_retires_phantoms_and_the_gate_reads_the_real_slate(
    fenced_app, monkeypatch,
):
    """Adopted games, the real migrated fence, the real Daily preflight and the
    real publication path, ending in the gate's own verdict."""
    game_pks = [pk for pk, _h, _a in GAMES]
    source = {'games': _pre_clinch_slate()}
    monkeypatch.setattr(
        schedule_ingestion.mlb_client, 'get_schedule',
        lambda start_date=None, end_date=None, team_id=None: [
            game for game in source['games']
            if start_date <= game['officialDate'] <= end_date
        ],
    )
    with fenced_app.app_context():
        # Before the bracket settled, then adopted by the sync-pipeline runtime.
        ingest_games(source['games'], source='daily_slate_schedule')
        db.session.commit()
        _adopt_like_sync_pipeline(game_pks)
        # The pre-fix writer then added the real clubs' rows beside the
        # placeholders' rows: the state production held on Sep 30.
        db.session.execute(text(
            "SELECT set_config('baseballos.schedule_owners', :keys, true)"
        ), {'keys': '[%s]' % ','.join(f'"{pk}"' for pk in game_pks)})
        for game_pk, (side, _placeholder) in PLACEHOLDERS.items():
            home, away = next((h, a) for pk, h, a in GAMES if pk == game_pk)
            real = away if side == 'away' else home
            db.session.add(ScheduledGame(
                team_id=real, game_pk=game_pk, game_date=SLATE, home_away=side,
                opponent_team_id=home if side == 'away' else away, game_type='F',
                status_code='S', status_state=ScheduledGame.STATE_SCHEDULED,
                source='daily_slate_schedule',
            ))
        db.session.commit()
        assert {pk: len(rows) for pk, rows in _rows_by_game().items()} == {
            813001: 3, 813002: 3, 813003: 3, 813004: 2,
        }

        run = SyncRun(job_name='daily_sync', status='running', stage='started',
                      source='scheduled')
        db.session.add(run)
        db.session.commit()
        run_id = run.id

        # 10:05 UTC Sep 30: MLB reports all four Game 1s final.
        source['games'] = _slate(FINAL)
        preflight = sync_service._refresh_daily_schedule_finality_window(
            date(2026, 9, 30), 7,
        )
        assert preflight['status'] == 'ok'
        assert preflight['summary']['rows_retired'] == 3
        assert db.session.execute(text(
            "SELECT count(*) FROM compatibility_write_events WHERE outcome='stale_suppressed'"
        )).scalar() == 0

        # Appearance markers are not written yet: the gate must still withhold,
        # now for the real reason and not for a phantom non-final game.
        monkeypatch.setattr(bullpen_api, 'build_bullpen_dashboard_payload',
                            lambda *_a, **_k: _payload())
        with pytest.raises(sync_service.DashboardSnapshotPublicationWithheld) as withheld:
            sync_service.complete_sync_run_with_snapshot(
                run_id, final_status='success', source='scheduled',
                snapshot_source='scheduled_sync',
            )
        assert str(withheld.value) == 'dashboard_snapshot_slate_coverage_incomplete'
        candidate_id = withheld.value.snapshot_id
        db.session.remove()

    rows = _fresh_rows(os.environ['DATABASE_URL'], 'scheduled_games',
                       'team_id, status_state', game_pks)
    assert sorted((pk, team, state) for pk, team, state in rows) == sorted(
        (pk, team, 'final') for pk, home, away in GAMES for team in (home, away)
    )

    with fenced_app.app_context():
        candidate = db.session.get(DashboardSnapshot, candidate_id)
        assert candidate.is_published is False
        coverage = candidate.payload['freshness']['slate_coverage']
        assert coverage['games_scheduled'] == 4
        assert coverage['games_final'] == 4
        assert 'scheduled_games_not_final' not in coverage['reason_codes']
        assert 'postgame_markers_incomplete' in coverage['reason_codes']

        # Once the four games are fully ingested, the same evaluator clears.
        for game_pk, home, away in GAMES:
            db.session.add(PostgameProcessedGame(
                mlb_game_pk=game_pk, game_date=SLATE, game_type='F',
                home_team_id=home, away_team_id=away,
                processing_status=PostgameProcessedGame.STATUS_FULLY_PROCESSED,
                processed_at=datetime(2026, 9, 30, 4, 0),
            ))
        db.session.commit()
        after = slate_coverage.compute_slate_coverage(SLATE, sync_status='success')
        assert after['reason_codes'] == ['slate_complete']
        assert dashboard_snapshot._payload_slate_coverage_unavailable_reason({
            'freshness': {**_payload()['freshness'], 'slate_coverage': after},
        }) is None
