from datetime import date, timedelta
from types import SimpleNamespace

from services import public_serving_authority
from services.team_board_recent_relief_work import (
    CONTRACT,
    DISPLAY_GAME_DATES,
    author_frozen_recent_relief_work,
)


PACKAGE = public_serving_authority.TEAM_BOARD_PACKAGE_CONTRACT


def _pitcher(pitcher_id, name, *, active=True, team_id=110):
    return SimpleNamespace(
        id=pitcher_id,
        mlb_id=700000 + pitcher_id,
        full_name=name,
        active=active,
        roster_status='active' if active else 'Optioned / Minors',
        team_id=team_id,
    )


def _log(log_id, pitcher_id, game_pk, game_date, *, team_id=110, pitches=15,
         outs=3, games_started=0, save=False, hold=False, finished=0):
    return SimpleNamespace(
        id=log_id,
        pitcher_id=pitcher_id,
        mlb_game_pk=game_pk,
        game_date=game_date,
        appearance_team_id=team_id,
        games_started=games_started,
        innings_pitched_outs=outs,
        pitches_thrown=pitches,
        save=save,
        hold=hold,
        games_finished=finished,
        opponent='Boston Red Sox',
        opponent_abbreviation='BOS',
    )


def _final(game_pk, game_date, *, number=1):
    return {
        game_pk: {
            'game_date': game_date.isoformat(),
            'game_number': number,
            'home_away': 'home',
            'status': 'final',
        }
    }


def _author(rows, finals, *, represented=date(2026, 9, 20), unresolved=0,
            active_pitcher_ids=None):
    if active_pitcher_ids is None:
        active_pitcher_ids = [
            pitcher.id for _log_row, pitcher in rows if pitcher.active
        ]
    return author_frozen_recent_relief_work(
        110,
        rows,
        data_through=represented,
        final_games=finals,
        unresolved_current_roster_count=unresolved,
        active_pitcher_ids=active_pitcher_ids,
        team_board_package_contract=PACKAGE,
    )


def test_ledger_is_latest_five_completed_game_dates_with_deterministic_order():
    represented = date(2026, 9, 20)
    rows = []
    finals = {}
    for offset in range(6):
        game_date = represented - timedelta(days=offset)
        game_pk = 9000 + offset
        pitcher = _pitcher(offset + 1, f'Arm {5 - offset}')
        rows.append((_log(offset + 1, pitcher.id, game_pk, game_date), pitcher))
        finals.update(_final(game_pk, game_date))

    carrier = _author(rows, finals, represented=represented)

    assert carrier['contract'] == CONTRACT
    assert carrier['status'] == 'complete'
    assert len({game['game_date'] for game in carrier['games']}) == DISPLAY_GAME_DATES
    assert [group['game_date'] for group in carrier['relief_by_date']] == [
        (represented - timedelta(days=offset)).isoformat() for offset in range(5)
    ]
    assert all(game['finality']['game_status'] == 'final' for game in carrier['games'])


def test_appearance_metrics_preserve_zero_unknown_multi_inning_and_off_active():
    game_date = date(2026, 9, 20)
    departed = _pitcher(2, 'Former Arm', active=False)
    rows = [(
        _log(1, departed.id, 9001, game_date, pitches=None, outs=4,
             save=True, hold=False, finished=1),
        departed,
    )]
    carrier = _author(rows, _final(9001, game_date))
    appearance = carrier['games'][0]['appearances'][0]

    assert appearance['current_roster']['active'] is False
    assert appearance['outs'] == {'value': 4, 'status': 'complete', 'reason_codes': []}
    assert appearance['pitches']['value'] is None
    assert appearance['pitches']['status'] == 'unknown'
    assert appearance['multi_inning']['value'] is True
    assert appearance['save']['value'] is True
    assert appearance['hold']['value'] is False
    assert appearance['game_finished']['value'] is True
    assert carrier['relief_by_date'][0]['pitches_total'] is None


def test_frozen_active_population_overrides_mutable_pitcher_active_flag():
    game_date = date(2026, 9, 20)
    stale_active_flag = _pitcher(2, 'Departed Arm', active=True)
    carrier = _author(
        [(_log(1, stale_active_flag.id, 9001, game_date), stale_active_flag)],
        _final(9001, game_date),
        active_pitcher_ids=[],
    )

    assert carrier['games'][0]['appearances'][0]['current_roster']['active'] is False


def test_wrong_team_prior_team_and_nonfinal_rows_never_enter_ledger():
    game_date = date(2026, 9, 20)
    acquired = _pitcher(1, 'Acquired Arm', team_id=110)
    prior = _log(1, acquired.id, 9001, game_date, team_id=111, pitches=99)
    nonfinal = _log(2, acquired.id, 9002, game_date, team_id=110, pitches=20)

    carrier = _author(
        [(prior, acquired), (nonfinal, acquired)],
        _final(9001, game_date),
    )

    assert carrier['appearance_count'] == 0
    assert carrier['games'] == []
    assert carrier['status'] == 'partial'
    assert 'final game authority is unavailable' in carrier['limitations'][0]


def test_unresolved_attribution_is_partial_without_manufacturing_rows():
    carrier = _author([], {}, unresolved=2)
    assert carrier['status'] == 'partial'
    assert carrier['games'] == []
    assert carrier['appearance_count'] == 0
    assert 'official team attribution is unresolved' in carrier['limitations'][0]


def test_frozen_reader_rejects_team_date_and_appearance_identity_mismatch():
    represented = date(2026, 9, 20)
    pitcher = _pitcher(1, 'Bound Arm')
    carrier = _author(
        [(_log(1, pitcher.id, 9001, represented), pitcher)],
        _final(9001, represented),
    )
    package = {
        'recent_relief_work': carrier,
        'recent_relief_work_authority': {
            'method_version': CONTRACT,
            'public_contract_version': CONTRACT,
            'team_board_package_contract': PACKAGE,
            'data_through': represented.isoformat(),
        },
    }
    snapshot = SimpleNamespace(data_through=represented)

    assert public_serving_authority._frozen_recent_relief_work_for_view(
        snapshot, package, 110,
    ) == carrier
    assert public_serving_authority._frozen_recent_relief_work_for_view(
        snapshot, package, 111,
    ) is None

    package['recent_relief_work']['games'][0]['appearances'][0]['appearance_team_id'] = 111
    assert public_serving_authority._frozen_recent_relief_work_for_view(
        snapshot, package, 110,
    ) is None


def test_frozen_reader_rejects_compatibility_view_that_diverges_from_ledger():
    represented = date(2026, 9, 20)
    pitcher = _pitcher(1, 'Bound Arm')
    carrier = _author(
        [(_log(1, pitcher.id, 9001, represented, pitches=19), pitcher)],
        _final(9001, represented),
    )
    package = {
        'recent_relief_work': carrier,
        'recent_relief_work_authority': {
            'method_version': CONTRACT,
            'public_contract_version': CONTRACT,
            'team_board_package_contract': PACKAGE,
            'data_through': represented.isoformat(),
        },
    }
    snapshot = SimpleNamespace(data_through=represented)

    package['recent_relief_work']['relief_by_date'][0]['appearances'][0][
        'pitches_thrown'
    ] = 999

    assert public_serving_authority._frozen_recent_relief_work_for_view(
        snapshot, package, 110,
    ) is None
