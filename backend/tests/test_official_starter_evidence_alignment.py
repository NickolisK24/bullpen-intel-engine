"""Regression cover for the July 28 official-starter alignment incident.

The Team Board published a game narrative naming a reliever as the starter of a
game he did not start, under a date summary whose visible appearance rows came
from a different game. These tests pin the three guarantees that failed:

  * a game's pitcher set is owned by the official game side
    (``GameLog.appearance_team_id``), never by who is on the roster today;
  * the starter of a completed game comes only from the official per-game start
    signal for that exact ``mlb_game_pk`` and team side;
  * a published summary and the rows shown beneath it must reconcile, or the
    affected block does not render at all.
"""

import json
from datetime import date, timedelta
from pathlib import Path

import pytest
from flask import Flask

from api.team_recent_work import team_recent_work_bp
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.scheduled_game import ScheduledGame
from services import public_team_relief_work
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


BACKEND_DIR = Path(__file__).resolve().parents[1]

TEAM_ID = 113
OTHER_TEAM_ID = 158
ANCHOR = date(2026, 7, 28)

FRESHNESS = {
    'data_through': ANCHOR.isoformat(),
    'freshness_state': 'current',
    'is_current': True,
    'label': 'Public bullpen data is current through July 28, 2026.',
}


@pytest.fixture()
def app(monkeypatch):
    application = Flask('test_official_starter_evidence_alignment')
    configure_test_database(application)
    db.init_app(application)
    application.register_blueprint(team_recent_work_bp, url_prefix='/api/bullpen')
    with application.app_context():
        create_test_schema(application)
        monkeypatch.setattr(
            public_team_relief_work.board_freshness,
            'board_freshness_block',
            lambda: dict(FRESHNESS),
        )
        try:
            yield application
        finally:
            db.session.remove()
            drop_test_schema(application)


_next_mlb_id = [500000]


def _pitcher(name, *, team_id=TEAM_ID, team_abbreviation='CIN'):
    _next_mlb_id[0] += 1
    pitcher = Pitcher(
        mlb_id=_next_mlb_id[0],
        full_name=name,
        team_id=team_id,
        team_name='Cincinnati Reds' if team_id == TEAM_ID else 'Other Club',
        team_abbreviation=team_abbreviation if team_id == TEAM_ID else 'OTH',
        active=True,
        roster_status='Active',
    )
    db.session.add(pitcher)
    db.session.flush()
    return pitcher


def _final_game(team_id, game_pk, game_date, *, status_state=None):
    seen = db.session.info.setdefault('_final_games', set())
    if (team_id, game_pk) in seen:
        return
    seen.add((team_id, game_pk))
    db.session.add(ScheduledGame(
        team_id=team_id,
        game_pk=game_pk,
        game_date=game_date,
        game_type='R',
        status_state=status_state or ScheduledGame.STATE_FINAL,
        status_code='F' if status_state is None else 'I',
    ))


def _log(
    pitcher,
    game_pk,
    game_date,
    *,
    games_started=0,
    outs=3,
    pitches=10,
    appearance_team_id=TEAM_ID,
    appearance_team_status=GameLog.APPEARANCE_TEAM_RESOLVED,
    schedule_state=None,
    register_schedule=True,
    innings_pitched=None,
):
    if register_schedule and appearance_team_id is not None:
        _final_game(
            appearance_team_id, game_pk, game_date, status_state=schedule_state
        )
    log = GameLog(
        pitcher_id=pitcher.id,
        mlb_game_pk=game_pk,
        game_date=game_date,
        game_type='R',
        opponent='Milwaukee Brewers',
        opponent_abbreviation='MIL',
        games_started=games_started,
        innings_pitched=outs / 3 if innings_pitched is None else innings_pitched,
        innings_pitched_outs=outs,
        pitches_thrown=pitches,
        appearance_team_id=appearance_team_id,
        appearance_team_status=appearance_team_status,
        appearance_team_source='boxscore_side',
        appearance_team_reason='appearance_team_resolved_boxscore',
    )
    db.session.add(log)
    return log


def _payload(team_id=TEAM_ID):
    return public_team_relief_work.build_public_team_relief_work_payload(team_id)


def _group_for(payload, game_date):
    for group in payload['relief_by_date']:
        if group['game_date'] == game_date.isoformat():
            return group
    return None


def _named_starters(payload):
    names = set()
    for group in payload['relief_by_date']:
        for block in group.get('games') or []:
            names.add(block['starter']['pitcher_full_name'])
    return names


def _totals_reconcile(group):
    rows = group['appearances']
    if group['relief_appearances'] != len(rows):
        return False
    if group['outs_total'] != sum(row['innings_pitched_outs'] for row in rows):
        return False
    known = [r['pitches_thrown'] for r in rows if r['pitches_thrown'] is not None]
    expected = sum(known) if len(known) == len(rows) else None
    return group['pitches_total'] == expected


# ── 1. Normal completed game ────────────────────────────────────────────────
def test_normal_completed_game_narrative_and_rows_reconcile(app):
    starter = _pitcher('Official Starter')
    relievers = [_pitcher(f'Reliever {n}') for n in ('One', 'Two', 'Three', 'Four')]
    _log(starter, 7001, ANCHOR, games_started=1, outs=18, pitches=88)
    for reliever, outs, pitches in zip(relievers, (3, 3, 4, 2), (11, 13, 17, 9)):
        _log(reliever, 7001, ANCHOR, outs=outs, pitches=pitches)
    db.session.commit()

    group = _group_for(_payload(), ANCHOR)
    assert group['relief_appearances'] == 4
    assert group['outs_total'] == 12
    assert group['pitches_total'] == 50
    assert group['game_pks'] == [7001]
    assert group['game_count'] == 1
    assert _totals_reconcile(group)

    block = group['games'][0]
    assert block['starter']['pitcher_full_name'] == 'Official Starter'
    assert block['starter_authority'] == 'official_completed_game_starter'
    assert block['reconciled'] is True
    assert block['relief']['pitcher_count'] == 4
    assert block['relief']['outs'] == 12
    assert block['relief']['pitches'] == 50
    assert block['relief']['pitcher_ids'] == sorted(r.id for r in relievers)
    # The narrative's pitcher set is exactly the rows shown beneath it.
    assert block['relief']['pitcher_ids'] == sorted(
        row['pitcher_id'] for row in group['appearances']
    )


# ── 2. A long relief run never makes a pitcher the starter ──────────────────
def test_pitcher_with_long_relief_history_is_never_named_starter(app):
    starter = _pitcher('Chase Burns')
    long_reliever = _pitcher('Caleb Ferguson')
    others = [_pitcher(f'Arm {n}') for n in ('A', 'B', 'C')]

    # Twenty-two prior relief outings for the reliever, none of them starts.
    for index in range(22):
        _log(long_reliever, 6000 + index, ANCHOR - timedelta(days=index + 1))

    _log(starter, 7002, ANCHOR, games_started=1, outs=15, pitches=78)
    _log(long_reliever, 7002, ANCHOR, outs=3, pitches=27)
    for other, outs, pitches in zip(others, (3, 3, 3), (8, 12, 10)):
        _log(other, 7002, ANCHOR, outs=outs, pitches=pitches)
    db.session.commit()

    payload = _payload()
    block = _group_for(payload, ANCHOR)['games'][0]
    assert block['starter']['pitcher_full_name'] == 'Chase Burns'
    assert block['starter']['pitcher_id'] == starter.id
    assert long_reliever.id in block['relief']['pitcher_ids']
    assert 'Caleb Ferguson' not in _named_starters(payload)


# ── 3. Per-game official designation beats season role ──────────────────────
def test_per_game_designation_wins_over_season_role(app):
    swing = _pitcher('Swing Arm')
    starter = _pitcher('Tonight Starter')
    mate = _pitcher('Bullpen Mate')

    # A genuine start earlier in the window does not make him tonight's starter.
    _log(swing, 7010, ANCHOR - timedelta(days=6), games_started=1, outs=15, pitches=80)
    _log(mate, 7010, ANCHOR - timedelta(days=6), outs=12, pitches=44)

    _log(starter, 7011, ANCHOR, games_started=1, outs=18, pitches=91)
    _log(swing, 7011, ANCHOR, outs=6, pitches=24)
    _log(mate, 7011, ANCHOR, outs=3, pitches=12)
    db.session.commit()

    payload = _payload()
    today = _group_for(payload, ANCHOR)['games'][0]
    assert today['starter']['pitcher_full_name'] == 'Tonight Starter'
    assert swing.id in today['relief']['pitcher_ids']

    earlier = _group_for(payload, ANCHOR - timedelta(days=6))['games'][0]
    assert earlier['starter']['pitcher_full_name'] == 'Swing Arm'


# ── 4. Doubleheader: explicit date aggregation, isolated narratives ─────────
def test_doubleheader_aggregates_explicitly_and_isolates_narratives(app):
    starter_one = _pitcher('Game One Starter')
    starter_two = _pitcher('Game Two Starter')
    pen_one = _pitcher('Pen One')
    pen_two = _pitcher('Pen Two')

    _log(starter_one, 7020, ANCHOR, games_started=1, outs=18, pitches=85)
    _log(pen_one, 7020, ANCHOR, outs=9, pitches=40)
    _log(starter_two, 7021, ANCHOR, games_started=1, outs=15, pitches=72)
    _log(pen_two, 7021, ANCHOR, outs=12, pitches=55)
    db.session.commit()

    group = _group_for(_payload(), ANCHOR)
    assert group['game_count'] == 2
    assert group['game_pks'] == [7020, 7021]
    # A multi-game date total says so in the published sentence.
    assert 'across 2 games' in group['sentence']
    assert _totals_reconcile(group)

    blocks = {block['mlb_game_pk']: block for block in group['games']}
    assert blocks[7020]['relief']['pitcher_ids'] == [pen_one.id]
    assert blocks[7021]['relief']['pitcher_ids'] == [pen_two.id]
    assert blocks[7020]['relief']['outs'] == 9
    assert blocks[7021]['relief']['outs'] == 12


# ── 5. Appearance ownership survives a roster move ──────────────────────────
def test_appearance_stays_with_the_game_team_after_a_roster_move(app):
    # Currently rostered elsewhere, but this appearance was made for TEAM_ID.
    departed = _pitcher('Departed Arm', team_id=OTHER_TEAM_ID)
    starter = _pitcher('Home Starter')
    _log(starter, 7030, ANCHOR, games_started=1, outs=18, pitches=90)
    _log(departed, 7030, ANCHOR, outs=9, pitches=33)
    db.session.commit()

    group = _group_for(_payload(TEAM_ID), ANCHOR)
    assert [row['pitcher_id'] for row in group['appearances']] == [departed.id]
    assert group['appearances'][0]['appearance_team_id'] == TEAM_ID
    assert group['games'][0]['relief']['pitcher_ids'] == [departed.id]

    # The pitcher's current club does not inherit the appearance.
    _pitcher('Other Club Arm', team_id=OTHER_TEAM_ID)
    other_board = _payload(OTHER_TEAM_ID)
    assert other_board['relief_by_date'] == []


# ── 6. One game side cannot leak into the other ─────────────────────────────
def test_opposing_team_side_cannot_leak_into_the_board(app):
    home_starter = _pitcher('Home Starter')
    home_pen = _pitcher('Home Pen')
    away_starter = _pitcher('Away Starter', team_id=OTHER_TEAM_ID)
    away_pen = _pitcher('Away Pen', team_id=OTHER_TEAM_ID)

    _log(home_starter, 7040, ANCHOR, games_started=1, outs=18, pitches=84)
    _log(home_pen, 7040, ANCHOR, outs=9, pitches=36)
    _log(away_starter, 7040, ANCHOR, games_started=1, outs=15, pitches=79,
         appearance_team_id=OTHER_TEAM_ID)
    _log(away_pen, 7040, ANCHOR, outs=12, pitches=48,
         appearance_team_id=OTHER_TEAM_ID)
    db.session.commit()

    group = _group_for(_payload(TEAM_ID), ANCHOR)
    assert [row['pitcher_id'] for row in group['appearances']] == [home_pen.id]
    block = group['games'][0]
    assert block['starter']['pitcher_full_name'] == 'Home Starter'
    assert block['relief']['pitcher_ids'] == [home_pen.id]
    assert block['appearance_team_id'] == TEAM_ID

    away_group = _group_for(_payload(OTHER_TEAM_ID), ANCHOR)
    assert away_group['games'][0]['starter']['pitcher_full_name'] == 'Away Starter'
    assert away_group['games'][0]['relief']['pitcher_ids'] == [away_pen.id]


# ── 7. Two credited starters on one side fail closed ────────────────────────
def test_conflicting_official_starters_suppress_the_narrative(app):
    first = _pitcher('Credited One')
    second = _pitcher('Credited Two')
    pen = _pitcher('Pen Arm')
    _log(first, 7050, ANCHOR, games_started=1, outs=9, pitches=44)
    _log(second, 7050, ANCHOR, games_started=1, outs=9, pitches=41)
    _log(pen, 7050, ANCHOR, outs=9, pitches=38)
    db.session.commit()

    group = _group_for(_payload(), ANCHOR)
    assert group.get('games') is None
    # The appearance rows still publish; only the starter-dependent claim stops.
    assert group['relief_appearances'] == 1
    assert _totals_reconcile(group)


# ── 8. Missing official starter suppresses the narrative ────────────────────
def test_missing_official_starter_suppresses_the_narrative(app):
    pen_a = _pitcher('Pen A')
    pen_b = _pitcher('Pen B')
    _log(pen_a, 7060, ANCHOR, outs=12, pitches=50)
    _log(pen_b, 7060, ANCHOR, outs=15, pitches=61)
    db.session.commit()

    group = _group_for(_payload(), ANCHOR)
    assert group.get('games') is None
    assert group['relief_appearances'] == 2
    assert _totals_reconcile(group)


def test_unknown_start_flag_suppresses_the_narrative(app):
    starter = _pitcher('Maybe Starter')
    pen = _pitcher('Pen Arm')
    _log(starter, 7061, ANCHOR, games_started=1, outs=18, pitches=80)
    _log(pen, 7061, ANCHOR, outs=6, pitches=25)
    unknown = _log(pen, 7062, ANCHOR, outs=3, pitches=12)
    unknown.games_started = None
    db.session.commit()

    group = _group_for(_payload(), ANCHOR)
    blocks = {block['mlb_game_pk'] for block in (group.get('games') or [])}
    assert 7062 not in blocks


# ── 9. Summary/rows mismatch never renders ──────────────────────────────────
def test_summary_that_does_not_match_its_rows_is_refused():
    group = {
        'relief_appearances': 8,
        'outs_total': 34,
        'pitches_total': 165,
        'appearances_with_pitches': 8,
        'appearances': [
            {'pitcher_id': 1, 'innings_pitched_outs': 3, 'pitches_thrown': 8},
            {'pitcher_id': 2, 'innings_pitched_outs': 3, 'pitches_thrown': 10},
        ],
    }
    assert public_team_relief_work._group_totals_reconcile(group) is False


def test_narrative_pitcher_set_must_equal_the_rows_shown(app):
    group = {
        'game_pks': [7070],
        'appearances': [
            {'pitcher_id': 1, 'mlb_game_pk': 7070,
             'innings_pitched_outs': 3, 'pitches_thrown': 10},
        ],
    }
    # Claims a reliever that is not shown in the rows beneath it.
    block = {
        'mlb_game_pk': 7070,
        'starter': {'pitcher_id': 9},
        'relief': {'pitcher_count': 2, 'outs': 6, 'pitches': 20,
                   'pitcher_ids': [1, 2]},
    }
    assert public_team_relief_work._block_reconciles_with_appearances(
        block, group
    ) is False

    # Claims totals that do not match the rows beneath it.
    block = {
        'mlb_game_pk': 7070,
        'starter': {'pitcher_id': 9},
        'relief': {'pitcher_count': 1, 'outs': 22, 'pitches': 108,
                   'pitcher_ids': [1]},
    }
    assert public_team_relief_work._block_reconciles_with_appearances(
        block, group
    ) is False

    # Claims a game that is not represented in the rows beneath it.
    block = {
        'mlb_game_pk': 7099,
        'starter': {'pitcher_id': 9},
        'relief': {'pitcher_count': 1, 'outs': 3, 'pitches': 10,
                   'pitcher_ids': [1]},
    }
    assert public_team_relief_work._block_reconciles_with_appearances(
        block, group
    ) is False


def test_unreconciled_date_group_publishes_an_honest_unavailable_state():
    group = public_team_relief_work._unavailable_group(ANCHOR)
    assert group['unavailable'] is True
    assert group['appearances'] == []
    assert 'unavailable' in group['sentence']
    # No count, innings, or pitch total survives in the fallback sentence.
    assert not any(ch.isdigit() for ch in group['sentence'].replace('28', ''))


# ── 10. A canonical correction rebuilds every dependent claim ───────────────
def test_correcting_the_canonical_row_rebuilds_the_narrative(app):
    wrong_starter = _pitcher('Wrongly Credited')
    true_starter = _pitcher('Actually Started')
    pen = _pitcher('Pen Arm')
    wrong_log = _log(wrong_starter, 7080, ANCHOR, games_started=1, outs=5, pitches=27)
    true_log = _log(true_starter, 7080, ANCHOR, games_started=0, outs=15, pitches=78)
    _log(pen, 7080, ANCHOR, outs=7, pitches=30)
    db.session.commit()

    before = _group_for(_payload(), ANCHOR)['games'][0]
    assert before['starter']['pitcher_full_name'] == 'Wrongly Credited'

    # Official correction to the canonical pitching lines.
    wrong_log.games_started = 0
    true_log.games_started = 1
    db.session.commit()

    after_group = _group_for(_payload(), ANCHOR)
    after = after_group['games'][0]
    assert after['starter']['pitcher_full_name'] == 'Actually Started'
    assert wrong_starter.id in after['relief']['pitcher_ids']
    assert true_starter.id not in after['relief']['pitcher_ids']
    assert after['relief']['outs'] == after_group['outs_total']
    assert _totals_reconcile(after_group)


# ── 11. Integer outs are the authority; decimal innings is display only ─────
def test_integer_outs_are_the_authority_not_decimal_innings(app):
    starter = _pitcher('Outs Starter')
    pen_a = _pitcher('Outs Pen A')
    pen_b = _pitcher('Outs Pen B')
    _log(starter, 7090, ANCHOR, games_started=1, outs=16, pitches=80)
    # 1.2 IP and 1.1 IP in baseball notation are 5 and 4 outs, never 1.2 + 1.1.
    _log(pen_a, 7090, ANCHOR, outs=5, pitches=22)
    _log(pen_b, 7090, ANCHOR, outs=4, pitches=18)
    db.session.commit()

    group = _group_for(_payload(), ANCHOR)
    assert group['outs_total'] == 9
    assert '3.0 IP' in group['sentence']
    block = group['games'][0]
    assert block['relief']['outs'] == 9
    assert block['relief']['innings'] == '3.0'
    assert block['starter']['outs'] == 16
    assert block['starter']['innings'] == '5.1'
    assert block['total']['outs'] == 25
    assert block['total']['innings'] == '8.1'


# ── Final-game authority is required for a starter-dependent claim ──────────
def test_non_final_game_suppresses_the_narrative(app):
    starter = _pitcher('In Progress Starter')
    pen = _pitcher('In Progress Pen')
    _log(starter, 7095, ANCHOR, games_started=1, outs=18, pitches=85,
         schedule_state=ScheduledGame.STATE_SCHEDULED)
    _log(pen, 7095, ANCHOR, outs=6, pitches=25)
    db.session.commit()

    group = _group_for(_payload(), ANCHOR)
    assert group.get('games') is None
    assert group['relief_appearances'] == 1


def test_unresolved_appearance_team_is_excluded_and_disclosed(app):
    pen = _pitcher('Unresolved Arm')
    _log(pen, 7096, ANCHOR, outs=3, pitches=14,
         appearance_team_id=None,
         appearance_team_status=GameLog.APPEARANCE_TEAM_UNRESOLVED,
         register_schedule=False)
    db.session.commit()

    payload = _payload()
    assert payload['relief_by_date'] == []
    assert payload['unattributed_appearance_count'] == 1
    assert 'not counted here' in payload['unattributed_sentence']


# ── 12. The production-shaped incident ──────────────────────────────────────
def test_july_28_burns_ferguson_production_shape(app):
    """The exact incident: two July 28 games merged under one date header.

    The official Reds game was started by Chase Burns, who had since left the
    active roster. A second game's pitching lines — owned by another club —
    were pulled onto the Reds board by the old current-roster join, and its
    starter narrative rendered beneath the Reds' own appearance rows.
    """
    burns = _pitcher('Chase Burns', team_id=None)  # no longer on the roster
    burke = _pitcher('Brock Burke')
    johnson = _pitcher('Pierce Johnson')
    moll = _pitcher('Sam Moll')
    petty = _pitcher('Chase Petty')

    ferguson = _pitcher('Caleb Ferguson')
    franco = _pitcher('Jose Franco')
    garcia = _pitcher('Julian Garcia')
    antone = _pitcher('Tejay Antone')
    pagan = _pitcher('Emilio Pagan')

    # Official Reds game.
    _log(burns, 800001, ANCHOR, games_started=1, outs=15, pitches=78)
    for pitcher, pitches in ((burke, 8), (johnson, 12), (moll, 27), (petty, 10)):
        _log(pitcher, 800001, ANCHOR, outs=3, pitches=pitches)

    # A different club's game on the same date.
    _log(ferguson, 800002, ANCHOR, games_started=1, outs=5, pitches=27,
         appearance_team_id=OTHER_TEAM_ID)
    for pitcher, outs, pitches in (
        (franco, 11, 48), (garcia, 4, 18), (antone, 4, 25), (pagan, 3, 17),
    ):
        _log(pitcher, 800002, ANCHOR, outs=outs, pitches=pitches,
             appearance_team_id=OTHER_TEAM_ID)
    db.session.commit()

    payload = _payload(TEAM_ID)
    group = _group_for(payload, ANCHOR)

    # The date summary matches the official Reds box score, not a merged total.
    assert group['relief_appearances'] == 4
    assert group['outs_total'] == 12
    assert group['pitches_total'] == 57
    assert group['game_pks'] == [800001]
    assert _totals_reconcile(group)
    assert '8 relief appearances' not in group['sentence']
    assert '11.1 IP' not in group['sentence']
    assert '165 pitches' not in group['sentence']

    # The visible rows are exactly the official Reds relievers.
    assert sorted(row['pitcher_full_name'] for row in group['appearances']) == [
        'Brock Burke', 'Chase Petty', 'Pierce Johnson', 'Sam Moll',
    ]

    # The starter is the official starter, even though he left the roster.
    block = group['games'][0]
    assert block['mlb_game_pk'] == 800001
    assert block['starter']['pitcher_full_name'] == 'Chase Burns'
    assert block['starter']['outs'] == 15
    assert block['relief']['pitcher_ids'] == sorted(
        p.id for p in (burke, johnson, moll, petty)
    )

    # No Ferguson starter narrative, and no extended-coverage claim at all.
    assert _named_starters(payload) == {'Chase Burns'}
    assert block['context_label'] is None
    for sentence in block['context_sentences']:
        assert 'Caleb Ferguson' not in sentence
        assert '22 outs' not in sentence
        assert '108 pitches' not in sentence


# ── Bounded read-only audit command ─────────────────────────────────────────
def _load_audit_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        'run_official_starter_alignment_audit',
        str(BACKEND_DIR / 'scripts' / 'run_official_starter_alignment_audit.py'),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_audit_command_finds_the_incident_and_never_writes(app, monkeypatch):
    burns = _pitcher('Chase Burns', team_id=None)
    reds_pen = [_pitcher(n) for n in ('Brock Burke', 'Pierce Johnson', 'Sam Moll')]
    ferguson = _pitcher('Caleb Ferguson')
    other_pen = _pitcher('Jose Franco')

    _log(burns, 800001, ANCHOR, games_started=1, outs=15, pitches=78)
    for pitcher in reds_pen:
        _log(pitcher, 800001, ANCHOR, outs=3, pitches=10)
    _log(ferguson, 800002, ANCHOR, games_started=1, outs=5, pitches=27,
         appearance_team_id=OTHER_TEAM_ID)
    _log(other_pen, 800002, ANCHOR, outs=11, pitches=48,
         appearance_team_id=OTHER_TEAM_ID)
    db.session.commit()

    audit = _load_audit_module()
    args = audit._parse_args([
        '--through', ANCHOR.isoformat(), '--days', '7',
    ])
    committed = []
    monkeypatch.setattr(db.session, 'commit', lambda: committed.append(True))
    result = audit._run(args, app_factory=lambda: app)

    assert result['mode'] == 'read_only'
    assert result['result'] == 'AFFECTED'
    assert committed == []

    findings = result['findings']
    # Burns is the official starter but is absent from the roster-join cohort.
    starter_diff = findings['published_starter_differs_from_official']['listed']
    assert any(
        entry['mlb_game_pk'] == 800001
        and entry['official_starter_name'] == 'Chase Burns'
        and entry['roster_join_starter_pitcher_ids'] == []
        for entry in starter_diff
    )
    # The Reds date cohort under the old join spanned two games.
    mixed = findings['date_summaries_combining_multiple_games']['listed']
    assert any(
        entry['team_id'] == TEAM_ID and entry['mlb_game_pks'] == [800001, 800002]
        for entry in mixed
    )
    # Ferguson's appearance is owned by the other club, not his current one.
    owner = findings['appearance_owner_differs_from_current_club']['listed']
    assert any(
        entry['pitcher_full_name'] == 'Caleb Ferguson'
        and entry['appearance_team_id'] == OTHER_TEAM_ID
        and entry['current_team_id'] == TEAM_ID
        for entry in owner
    )


def test_audit_command_is_clean_on_a_well_formed_game(app):
    starter = _pitcher('Clean Starter')
    for name, pitches in (('Clean A', 11), ('Clean B', 13)):
        _log(_pitcher(name), 810001, ANCHOR, outs=3, pitches=pitches)
    _log(starter, 810001, ANCHOR, games_started=1, outs=21, pitches=95)
    db.session.commit()

    audit = _load_audit_module()
    result = audit._run(
        audit._parse_args(['--through', ANCHOR.isoformat(), '--days', '7']),
        app_factory=lambda: app,
    )

    assert result['result'] == 'CLEAN'
    assert all(
        section['count'] == 0 for section in result['findings'].values()
    )


# ── API contract: the route cannot serve a starter contradiction ────────────
def test_api_response_cannot_contradict_the_official_starter(app):
    burns = _pitcher('Chase Burns', team_id=None)
    reds_pen = [_pitcher(n) for n in ('Brock Burke', 'Pierce Johnson', 'Sam Moll')]
    ferguson = _pitcher('Caleb Ferguson')
    _log(burns, 800001, ANCHOR, games_started=1, outs=15, pitches=78)
    for pitcher in reds_pen:
        _log(pitcher, 800001, ANCHOR, outs=3, pitches=10)
    _log(ferguson, 800002, ANCHOR, games_started=1, outs=5, pitches=27,
         appearance_team_id=OTHER_TEAM_ID)
    db.session.commit()

    body = app.test_client().get(
        f'/api/bullpen/teams/{TEAM_ID}/relief-work'
    ).get_json()

    text = json.dumps(body)
    assert 'Caleb Ferguson' not in text
    assert 'Chase Burns' in text

    for group in body['relief_by_date']:
        rows = group.get('appearances') or []
        # Every published number reconciles to the rows shown beneath it.
        assert group['relief_appearances'] == len(rows)
        assert group['outs_total'] == sum(r['innings_pitched_outs'] for r in rows)
        shown_ids = {r['pitcher_id'] for r in rows}
        shown_games = {r['mlb_game_pk'] for r in rows}
        for block in group.get('games') or []:
            assert block['starter_authority'] == 'official_completed_game_starter'
            assert block['reconciled'] is True
            assert block['mlb_game_pk'] in shown_games
            assert set(block['relief']['pitcher_ids']) <= shown_ids
            assert block['starter']['pitcher_id'] not in shown_ids
            assert block['appearance_team_id'] == TEAM_ID
