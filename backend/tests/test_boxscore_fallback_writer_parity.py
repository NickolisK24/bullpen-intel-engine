"""The daily lane writing a field its own source cannot supply.

The defect class these tests own, stated as production found it:

* the completed-game box score said ``balls 19, strikes 26, pitches 45``
  (19 + 26 = 45);
* the player game-log split carried strikes and pitches but no ``balls`` key;
* the stored row said ``balls 20, strikes 26, pitches 45`` — 20 + 26 != 45 —
  with ``last_stat_correction_source = daily_game_log``.

The daily lane had already corrected that row. It corrected it again on later
sweeps. It could never correct ``balls``, because a governed optional statistic
is compared only when the source supplies it, and the split never did. The
value was uncorrectable, not disputed.

The repair adds no second comparator and no second writer. It enriches the
source with the one approved field, then feeds the enriched source through the
same canonical values builder, the same planner, and the same writer that
already governed every other field. These tests exist to prove that: that the
fallback changes what the lane can *see*, and nothing about what it may *do*.
"""

from datetime import date, datetime

import pytest
from flask import Flask

from tests.db_config import (
    configure_test_database, create_test_schema, drop_test_schema,
)

import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.scheduled_game import ScheduledGame
from services import gamelog_source_authority as authority
from services import sync as sync_service
from utils.db import db


SLATE = date(2026, 6, 20)
CUTOFF = date(2026, 6, 14)
GAME_PK = 970001
OTHER_GAME_PK = 970002
PITCHER_MLB_ID = 970100
OTHER_PITCHER_MLB_ID = 970200
HOME_TEAM_ID = 111
AWAY_TEAM_ID = 222


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


# ── Fixtures ────────────────────────────────────────────────────────────────


def _schedule(game_pk=GAME_PK, slate=SLATE):
    for team_id, opponent_id, side in (
        (HOME_TEAM_ID, AWAY_TEAM_ID, 'home'),
        (AWAY_TEAM_ID, HOME_TEAM_ID, 'away'),
    ):
        db.session.add(ScheduledGame(
            team_id=team_id, game_pk=game_pk, game_date=slate,
            game_datetime=datetime(2026, 6, 20, 19, 5),
            opponent_team_id=opponent_id, home_away=side, game_type='R',
            status_code='F', status_state=ScheduledGame.STATE_FINAL,
        ))


def _pitcher(mlb_id=PITCHER_MLB_ID, name='Test Arm'):
    pitcher = Pitcher(
        mlb_id=mlb_id, full_name=name, team_id=HOME_TEAM_ID,
        team_abbreviation='HOM', active=True,
    )
    db.session.add(pitcher)
    return pitcher


def _stored_row(pitcher, *, balls=20, game_pk=GAME_PK, **overrides):
    """The audited defect shape: an internally inconsistent stored triple."""
    fields = {
        'pitcher_id': pitcher.id, 'mlb_game_pk': game_pk, 'game_date': SLATE,
        'game_type': 'R', 'innings_pitched_outs': 9, 'innings_pitched': 3.0,
        'pitches_thrown': 45, 'strikes': 26, 'balls': balls, 'hits_allowed': 2,
        'runs_allowed': 1, 'earned_runs': 1, 'walks': 1, 'strikeouts': 4,
        'home_runs_allowed': 0, 'games_started': 0, 'batters_faced': 12,
        'opponent': 'Away Club', 'opponent_abbreviation': 'AWY',
        'last_stat_correction_source': (
            sync_service.DAILY_GAME_LOG_CORRECTION_SOURCE
        ),
        'stat_correction_count': 1,
    }
    fields.update(overrides)
    row = GameLog(**fields)
    db.session.add(row)
    return row


def _split(*, game_pk=GAME_PK, with_balls=None, **stat_overrides):
    """The player game-log split shape, which does not carry ``balls``."""
    stat = {
        'inningsPitched': '3.0', 'strikes': 26, 'numberOfPitches': 45,
        'hits': 2, 'runs': 1, 'earnedRuns': 1, 'baseOnBalls': 1,
        'strikeOuts': 4, 'homeRuns': 0, 'battersFaced': 12, 'gamesStarted': 0,
    }
    if with_balls is not None:
        stat['balls'] = with_balls
    stat.update(stat_overrides)
    return {
        'date': SLATE.isoformat(),
        'game': {
            'gamePk': game_pk, 'gameType': 'R',
            'status': {
                'statusCode': 'F', 'detailedState': 'Final',
                'abstractGameState': 'Final',
            },
        },
        'opponent': {'id': AWAY_TEAM_ID, 'name': 'Away Club'},
        'stat': stat,
    }


def _pitching_lines(*, balls=19, strikes=26, pitches=45,
                    player_id=PITCHER_MLB_ID):
    """The completed-game box score: coherent, and it carries ``balls``."""
    return [{
        'player_id': player_id, 'side': 'home', 'team_id': HOME_TEAM_ID,
        'stats': {
            'balls': balls, 'strikes': strikes, 'numberOfPitches': pitches,
            'inningsPitched': '3.0',
        },
    }]


def _ingest(pitcher, split, *, ledger, lines_cache=None):
    return sync_service._ingest_game_log_split(
        pitcher, split, CUTOFF, {AWAY_TEAM_ID: 'AWY'},
        existing_by_key=None,
        pitching_lines_cache=lines_cache if lines_cache is not None else {},
        fallback_ledger=ledger,
    )


@pytest.fixture
def lane(app, monkeypatch):
    """A prepared appearance plus a controllable box-score source."""
    calls = []

    def fake_lines(game_pk):
        calls.append(game_pk)
        return _pitching_lines()

    monkeypatch.setattr(sync_service.mlb_client, 'get_game_pitching_lines',
                        fake_lines)
    _schedule()
    pitcher = _pitcher()
    db.session.flush()
    row = _stored_row(pitcher)
    db.session.commit()
    return {'pitcher': pitcher, 'row': row, 'calls': calls}


# ── The defect class, end to end ────────────────────────────────────────────


def test_the_audited_defect_shape_is_corrected(lane):
    """Stored 20, split silent, box score 19 — the value finally moves."""
    ledger = authority.FallbackLedger()
    result = _ingest(lane['pitcher'], _split(), ledger=ledger)
    db.session.commit()

    assert result['status'] == 'corrected'
    assert result['changed_fields'] == ['balls']
    assert GameLog.query.one().balls == 19


def test_without_the_fallback_the_same_appearance_is_uncorrectable(lane):
    """The control. Omit the ledger and the lane behaves exactly as before.

    This is what made the stored value survive every sweep: the split has
    nothing to say about the field, and silence is not a correction.
    """
    result = _ingest(lane['pitcher'], _split(), ledger=None)
    db.session.commit()

    assert result['status'] == 'unchanged'
    assert GameLog.query.one().balls == 20
    assert lane['calls'] == []


def test_only_the_approved_field_moves(lane):
    """The whole authorization rests on this being true."""
    ledger = authority.FallbackLedger()
    before = {
        field: getattr(lane['row'], field)
        for field in ('strikes', 'pitches_thrown', 'innings_pitched_outs',
                      'hits_allowed', 'runs_allowed', 'earned_runs', 'walks',
                      'strikeouts', 'batters_faced', 'games_started',
                      'opponent', 'opponent_abbreviation', 'game_type')
    }
    _ingest(lane['pitcher'], _split(), ledger=ledger)
    db.session.commit()

    row = GameLog.query.one()
    for field, value in before.items():
        assert getattr(row, field) == value


def test_the_correction_is_attributed_to_the_source_that_supplied_it(lane):
    """Recording ``daily_game_log`` would credit an endpoint that never
    carried the value."""
    ledger = authority.FallbackLedger()
    _ingest(lane['pitcher'], _split(), ledger=ledger)
    db.session.commit()

    row = GameLog.query.one()
    assert row.last_stat_correction_source == (
        authority.CORRECTION_SOURCE_BOXSCORE_FALLBACK
    )
    assert row.stat_correction_count == 2


def test_a_correction_the_split_drove_keeps_the_lanes_own_provenance(lane):
    """Attribution follows the values that actually moved.

    Here the box score confirms the stored ``balls``, and the split revises
    ``strikeouts``. The fallback supplied a value but changed nothing, so the
    lane's own source is the honest authority for this correction.
    """
    lane['row'].balls = 19
    db.session.commit()

    ledger = authority.FallbackLedger()
    _ingest(lane['pitcher'], _split(strikeOuts=5), ledger=ledger)
    db.session.commit()

    row = GameLog.query.one()
    assert row.strikeouts == 5
    assert row.last_stat_correction_source == (
        sync_service.DAILY_GAME_LOG_CORRECTION_SOURCE
    )


# ── Primacy and refusal ─────────────────────────────────────────────────────


def test_a_split_that_carries_the_field_is_never_overridden(lane):
    """Evidence beats fallback. The box score is not consulted at all."""
    ledger = authority.FallbackLedger()
    result = _ingest(lane['pitcher'], _split(with_balls=21), ledger=ledger)
    db.session.commit()

    assert GameLog.query.one().balls == 21
    assert result['changed_fields'] == ['balls']
    assert ledger.eligible_rows == 0
    assert lane['calls'] == []


def test_an_incoherent_box_score_leaves_the_stored_value_alone(lane, monkeypatch):
    """20 + 26 != 45 stored, and the box score does not add up either.

    Refusing is the only safe answer: correcting to an incoherent value would
    replace one unexplained number with another.
    """
    monkeypatch.setattr(
        sync_service.mlb_client, 'get_game_pitching_lines',
        lambda game_pk: _pitching_lines(balls=30),
    )
    ledger = authority.FallbackLedger()
    result = _ingest(lane['pitcher'], _split(), ledger=ledger)
    db.session.commit()

    assert result['status'] == 'unchanged'
    assert GameLog.query.one().balls == 20
    assert ledger.refused_rows == 1
    assert ledger.summary()['boxscore_fallback_refusal_reasons'] == {
        authority.REFUSED_INCONSISTENT_TRIPLE: 1,
    }


def test_an_unreachable_box_score_is_a_counted_non_event(lane, monkeypatch):
    def boom(game_pk):
        raise RuntimeError('source unavailable')

    monkeypatch.setattr(sync_service.mlb_client, 'get_game_pitching_lines', boom)
    ledger = authority.FallbackLedger()
    result = _ingest(lane['pitcher'], _split(), ledger=ledger)
    db.session.commit()

    assert result['status'] == 'unchanged'
    assert GameLog.query.one().balls == 20
    assert ledger.fetch_failures == 1
    assert ledger.summary()['boxscore_fallback_refusal_reasons'] == {
        authority.REFUSED_BOXSCORE_UNAVAILABLE: 1,
    }


def test_a_box_score_without_this_pitchers_line_refuses(lane, monkeypatch):
    monkeypatch.setattr(
        sync_service.mlb_client, 'get_game_pitching_lines',
        lambda game_pk: _pitching_lines(player_id=OTHER_PITCHER_MLB_ID),
    )
    ledger = authority.FallbackLedger()
    _ingest(lane['pitcher'], _split(), ledger=ledger)
    db.session.commit()

    assert GameLog.query.one().balls == 20
    assert ledger.summary()['boxscore_fallback_refusal_reasons'] == {
        authority.REFUSED_NO_PITCHING_LINE: 1,
    }


def test_two_lines_claiming_one_pitcher_refuse_rather_than_choose(
    lane, monkeypatch,
):
    monkeypatch.setattr(
        sync_service.mlb_client, 'get_game_pitching_lines',
        lambda game_pk: _pitching_lines() + _pitching_lines(balls=3, strikes=3,
                                                            pitches=6),
    )
    ledger = authority.FallbackLedger()
    _ingest(lane['pitcher'], _split(), ledger=ledger)
    db.session.commit()

    assert GameLog.query.one().balls == 20
    assert ledger.summary()['boxscore_fallback_refusal_reasons'] == {
        authority.REFUSED_IDENTITY_AMBIGUOUS: 1,
    }


def test_a_partial_split_line_still_blocks_the_write(lane):
    """The correction-safety rule is upstream of the fallback and stays there.

    Enriching one field must not make an otherwise unsafe line look complete.
    """
    split = _split()
    del split['stat']['earnedRuns']
    ledger = authority.FallbackLedger()
    result = _ingest(lane['pitcher'], split, ledger=ledger)
    db.session.commit()

    assert result['status'] == 'unsafe'
    assert GameLog.query.one().balls == 20


def test_a_game_that_is_not_final_is_never_fetched(lane):
    """The finality gate runs before the fallback, so a live game costs
    nothing and can never contribute a partial line."""
    split = _split()
    split['game']['status'] = {
        'statusCode': 'I', 'detailedState': 'In Progress',
        'abstractGameState': 'Live',
    }
    ledger = authority.FallbackLedger()
    result = _ingest(lane['pitcher'], split, ledger=ledger)

    assert result['status'] == 'skipped'
    assert lane['calls'] == []
    assert ledger.eligible_rows == 0


# ── Convergence and idempotence ─────────────────────────────────────────────


def test_a_row_that_already_agrees_is_supplied_but_not_rewritten(lane):
    lane['row'].balls = 19
    db.session.commit()

    ledger = authority.FallbackLedger()
    result = _ingest(lane['pitcher'], _split(), ledger=ledger)
    db.session.commit()

    row = GameLog.query.one()
    assert result['status'] == 'unchanged'
    assert row.stat_correction_count == 1
    assert ledger.applied_rows == 1
    assert ledger.unchanged_rows == 1
    assert ledger.corrected_rows == 0


def test_a_second_sweep_corrects_nothing_further(lane):
    """The defect was a correction that replayed forever. It converges now."""
    first = authority.FallbackLedger()
    _ingest(lane['pitcher'], _split(), ledger=first)
    db.session.commit()

    second = authority.FallbackLedger()
    result = _ingest(lane['pitcher'], _split(), ledger=second)
    db.session.commit()

    row = GameLog.query.one()
    assert result['status'] == 'unchanged'
    assert row.balls == 19
    assert row.stat_correction_count == 2
    assert second.corrected_rows == 0


def test_a_missing_row_is_inserted_carrying_the_fallback_value(lane):
    GameLog.query.delete()
    db.session.commit()

    ledger = authority.FallbackLedger()
    result = _ingest(lane['pitcher'], _split(), ledger=ledger)
    db.session.commit()

    assert result['status'] == 'inserted'
    assert GameLog.query.one().balls == 19
    assert ledger.inserted_rows == 1
    assert ledger.unchanged_rows == 0


# ── Cost ────────────────────────────────────────────────────────────────────


def test_one_game_is_fetched_once_however_many_pitchers_appeared_in_it(lane):
    other = _pitcher(mlb_id=OTHER_PITCHER_MLB_ID, name='Second Arm')
    db.session.flush()
    _stored_row(other)
    db.session.commit()

    ledger = authority.FallbackLedger()
    cache = {}
    _ingest(lane['pitcher'], _split(), ledger=ledger, lines_cache=cache)
    _ingest(other, _split(), ledger=ledger, lines_cache=cache)
    db.session.commit()

    assert lane['calls'] == [GAME_PK]
    assert ledger.fetches == 1


def test_the_fallback_reuses_the_leverage_index_fetch(lane):
    """One cache, two consumers. A game already read for leverage index is
    never read again for the fallback."""
    cache = {GAME_PK: _pitching_lines()}
    ledger = authority.FallbackLedger()
    _ingest(lane['pitcher'], _split(), ledger=ledger, lines_cache=cache)
    db.session.commit()

    assert lane['calls'] == []
    assert ledger.fetches == 0
    assert GameLog.query.one().balls == 19


def test_reaching_the_fetch_cap_refuses_visibly(lane, monkeypatch):
    """A bounded cost, and a bound that reports itself rather than looking
    like a source with nothing to say."""
    monkeypatch.setattr(sync_service, 'BOXSCORE_FALLBACK_FETCH_CAP', 0)
    ledger = authority.FallbackLedger()
    _ingest(lane['pitcher'], _split(), ledger=ledger)
    db.session.commit()

    assert GameLog.query.one().balls == 20
    assert ledger.fetch_cap_reached == 1
    assert ledger.fetches == 0
    assert ledger.summary()['boxscore_fallback_refusal_reasons'] == {
        authority.REFUSED_BOXSCORE_UNAVAILABLE: 1,
    }


# ── Evidence ────────────────────────────────────────────────────────────────


def test_an_applied_value_is_recorded_with_the_evidence_behind_it(lane):
    ledger = authority.FallbackLedger()
    _ingest(lane['pitcher'], _split(), ledger=ledger)
    db.session.commit()

    record = ledger.summary()['boxscore_fallback_records'][0]
    assert record['game_pk'] == GAME_PK
    assert record['pitcher_mlb_id'] == PITCHER_MLB_ID
    assert record['fields'] == ['balls']
    assert record['outcome'] == authority.OUTCOME_CORRECTED
    assert record['source_authority'] == authority.AUTHORITY_CONTRACT
    assert record['source_revision']
    assert record['plan_fingerprint']
    assert record['applied_target_state_digest']
    assert 'statistical_correction' in record['difference_classifications']


def test_the_recorded_revision_identifies_the_line_that_was_read(lane):
    ledger = authority.FallbackLedger()
    _ingest(lane['pitcher'], _split(), ledger=ledger)
    db.session.commit()

    record = ledger.summary()['boxscore_fallback_records'][0]
    assert record['source_revision'] == authority.fallback_evidence_revision(
        game_pk=GAME_PK, pitcher_mlb_id=PITCHER_MLB_ID,
        stats=_pitching_lines()[0]['stats'],
    )


def test_a_refused_row_records_no_application(lane, monkeypatch):
    monkeypatch.setattr(
        sync_service.mlb_client, 'get_game_pitching_lines',
        lambda game_pk: _pitching_lines(balls=30),
    )
    ledger = authority.FallbackLedger()
    _ingest(lane['pitcher'], _split(), ledger=ledger)
    db.session.commit()

    assert ledger.summary()['boxscore_fallback_records'] == []


def test_the_split_payload_is_never_mutated_by_enrichment(lane):
    split = _split()
    ledger = authority.FallbackLedger()
    _ingest(lane['pitcher'], split, ledger=ledger)
    db.session.commit()

    assert 'balls' not in split['stat']


def test_the_uncomparable_diagnostic_still_names_what_the_split_could_not_see(
    lane, monkeypatch,
):
    """The fallback does not paper over the asymmetry it compensates for.

    When the box score refuses, the plan must still say the split never looked
    at the field — otherwise a refused fallback would read as agreement.
    """
    monkeypatch.setattr(
        sync_service.mlb_client, 'get_game_pitching_lines',
        lambda game_pk: _pitching_lines(balls=30),
    )
    ledger = authority.FallbackLedger()
    result = _ingest(lane['pitcher'], _split(), ledger=ledger)
    db.session.commit()

    assert 'balls' in result['plan']['uncomparable_fields']


def test_a_supplied_field_is_no_longer_reported_uncomparable(lane):
    """Once the box score supplies it, the planner really did compare it."""
    ledger = authority.FallbackLedger()
    result = _ingest(lane['pitcher'], _split(), ledger=ledger)
    db.session.commit()

    assert 'balls' not in result['plan']['uncomparable_fields']
