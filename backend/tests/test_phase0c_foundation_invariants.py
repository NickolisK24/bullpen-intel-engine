import inspect
from pathlib import Path

import pytest

from models.game_log import GameLog
from models.play_by_play_foundation import GamePlayByPlayEvent, PlayByPlayProcessedGame
from models.player_transaction import PlayerTransaction
from models.roster_status_snapshot import RosterStatusSnapshot
from models.team_game_pitching_split import TeamGamePitchingSplit
from services import source_readiness
from services.source_correction_policies import (
    CorrectionPolicyError,
    correction_policy,
    registered_correction_policies,
    validate_correction_sensitive_model,
)


REPO_ROOT = Path(__file__).resolve().parents[2]

PHASE0C_MODELS = (
    GameLog,
    RosterStatusSnapshot,
    PlayerTransaction,
    GamePlayByPlayEvent,
    PlayByPlayProcessedGame,
    TeamGamePitchingSplit,
)

PUBLIC_PAYLOAD_SURFACES = (
    REPO_ROOT / 'backend/api/bullpen.py',
    REPO_ROOT / 'backend/services/dashboard_snapshot.py',
    REPO_ROOT / 'backend/services/bullpen_board.py',
    REPO_ROOT / 'backend/services/what_changed_since_yesterday.py',
    REPO_ROOT / 'backend/services/what_changed_since_yesterday_public.py',
    REPO_ROOT / 'backend/services/tonight_intelligence_snapshot.py',
)

PHASE0C_MODULES = (
    REPO_ROOT / 'backend/services/play_by_play_foundation.py',
    REPO_ROOT / 'backend/services/transaction_ingestion.py',
    REPO_ROOT / 'backend/services/roster_status_sync.py',
    REPO_ROOT / 'backend/services/team_game_pitching_splits.py',
    REPO_ROOT / 'backend/services/source_readiness.py',
    REPO_ROOT / 'backend/models/play_by_play_foundation.py',
    REPO_ROOT / 'backend/models/player_transaction.py',
    REPO_ROOT / 'backend/models/roster_status_snapshot.py',
    REPO_ROOT / 'backend/models/team_game_pitching_split.py',
)

EXPECTED_SOURCE_FAMILIES = {
    source_readiness.FAMILY_FINALITY_AUTHORITY,
    source_readiness.FAMILY_STATSAPI_CORE,
    source_readiness.FAMILY_GAME_LOGS,
    source_readiness.FAMILY_SLATE_COVERAGE,
    source_readiness.FAMILY_DASHBOARD_SNAPSHOTS,
    source_readiness.FAMILY_ROSTER_STATUS_SNAPSHOTS,
    source_readiness.FAMILY_PLAYER_TRANSACTIONS,
    source_readiness.FAMILY_FINAL_PLAY_BY_PLAY,
    source_readiness.FAMILY_TEAM_GAME_PITCHING_SPLITS,
    source_readiness.FAMILY_CALENDAR_CONTEXT,
}

CURRENT_PUBLIC_BLOCKERS = {
    source_readiness.FAMILY_FINALITY_AUTHORITY,
    source_readiness.FAMILY_STATSAPI_CORE,
    source_readiness.FAMILY_GAME_LOGS,
    source_readiness.FAMILY_SLATE_COVERAGE,
    source_readiness.FAMILY_DASHBOARD_SNAPSHOTS,
    source_readiness.FAMILY_ROSTER_STATUS_SNAPSHOTS,
    source_readiness.FAMILY_PLAYER_TRANSACTIONS,
}


def test_phase0c_unknown_safe_numeric_facts_remain_nullable_without_zero_defaults():
    columns = [
        GameLog.__table__.c.games_started,
        GameLog.__table__.c.pitches_thrown,
        GameLog.__table__.c.batters_faced,
        GameLog.__table__.c.balls,
        GameLog.__table__.c.games_finished,
        GameLog.__table__.c.inherited_runners,
        GameLog.__table__.c.inherited_runners_scored,
        GamePlayByPlayEvent.__table__.c.at_bat_index,
        GamePlayByPlayEvent.__table__.c.inning,
        GamePlayByPlayEvent.__table__.c.outs_at_event,
        GamePlayByPlayEvent.__table__.c.home_score_at_event,
        GamePlayByPlayEvent.__table__.c.away_score_at_event,
        GamePlayByPlayEvent.__table__.c.pitcher_mlb_id,
        GamePlayByPlayEvent.__table__.c.pitcher_id,
        GamePlayByPlayEvent.__table__.c.batter_mlb_id,
        GamePlayByPlayEvent.__table__.c.batting_team_id,
        GamePlayByPlayEvent.__table__.c.fielding_team_id,
        PlayByPlayProcessedGame.__table__.c.home_team_id,
        PlayByPlayProcessedGame.__table__.c.away_team_id,
        RosterStatusSnapshot.__table__.c.active_roster,
        RosterStatusSnapshot.__table__.c.forty_man_roster,
        RosterStatusSnapshot.__table__.c.two_way_eligible,
        TeamGamePitchingSplit.__table__.c.starter_pitcher_id,
        TeamGamePitchingSplit.__table__.c.starter_mlb_id,
        TeamGamePitchingSplit.__table__.c.starter_outs_recorded,
        TeamGamePitchingSplit.__table__.c.starter_pitches_thrown,
        TeamGamePitchingSplit.__table__.c.starter_batters_faced,
        TeamGamePitchingSplit.__table__.c.starter_balls,
        TeamGamePitchingSplit.__table__.c.starter_games_started,
        TeamGamePitchingSplit.__table__.c.bullpen_outs_recorded,
        TeamGamePitchingSplit.__table__.c.bullpen_pitches_thrown,
        TeamGamePitchingSplit.__table__.c.bullpen_batters_faced,
        TeamGamePitchingSplit.__table__.c.bullpen_balls,
        TeamGamePitchingSplit.__table__.c.relievers_used_count,
        TeamGamePitchingSplit.__table__.c.total_team_outs,
        TeamGamePitchingSplit.__table__.c.total_team_pitches,
        TeamGamePitchingSplit.__table__.c.total_team_batters_faced,
        TeamGamePitchingSplit.__table__.c.total_team_balls,
        TeamGamePitchingSplit.__table__.c.off_day_before,
        TeamGamePitchingSplit.__table__.c.off_day_after,
        TeamGamePitchingSplit.__table__.c.consecutive_game_day_count_entering,
        TeamGamePitchingSplit.__table__.c.series_game_number,
        TeamGamePitchingSplit.__table__.c.games_in_series,
        TeamGamePitchingSplit.__table__.c.doubleheader_flag,
        TeamGamePitchingSplit.__table__.c.game_number,
        TeamGamePitchingSplit.__table__.c.postponed_or_makeup_indicator,
        TeamGamePitchingSplit.__table__.c.extra_inning_indicator,
    ]

    for column in columns:
        assert column.nullable is True, column.name
        assert column.default is None, column.name
        assert column.server_default is None, column.name


def test_phase0c_correction_sensitive_models_are_registered():
    expected_policies = {
        'game_log_pitching_line_corrections',
        'roster_status_snapshot_corrections',
        'player_transaction_corrections',
        'game_play_by_play_event_corrections',
        'play_by_play_processed_game_corrections',
        'team_game_pitching_split_corrections',
    }

    assert expected_policies.issubset(set(registered_correction_policies()))
    for model in PHASE0C_MODELS:
        assert validate_correction_sensitive_model(model)
        policy = correction_policy(model.__correction_policy_name__)
        assert set(model.__correction_sensitive_fields__).issubset(policy.field_names)
        assert set(model.__correction_identity_fields__).issubset(policy.identity_fields)


def test_unregistered_phase0c_correction_sensitive_model_fails_contract():
    class FuturePhase0CModel:
        __name__ = 'FuturePhase0CModel'
        __correction_sensitive_fields__ = ('future_field',)

    with pytest.raises(CorrectionPolicyError):
        validate_correction_sensitive_model(FuturePhase0CModel)


def test_source_readiness_registers_every_phase0c_family_in_pipeline_health():
    payload_source = inspect.getsource(source_readiness.source_readiness_payload)

    assert source_readiness.CURRENT_BLOCKING_SOURCE_FAMILIES == CURRENT_PUBLIC_BLOCKERS
    assert EXPECTED_SOURCE_FAMILIES == {
        value
        for name, value in vars(source_readiness).items()
        if name.startswith('FAMILY_')
    }
    for family_constant in (
        'FAMILY_FINALITY_AUTHORITY',
        'FAMILY_STATSAPI_CORE',
        'FAMILY_GAME_LOGS',
        'FAMILY_SLATE_COVERAGE',
        'FAMILY_DASHBOARD_SNAPSHOTS',
        'FAMILY_ROSTER_STATUS_SNAPSHOTS',
        'FAMILY_PLAYER_TRANSACTIONS',
        'FAMILY_FINAL_PLAY_BY_PLAY',
        'FAMILY_TEAM_GAME_PITCHING_SPLITS',
        'FAMILY_CALENDAR_CONTEXT',
    ):
        assert family_constant in payload_source


def test_phase0c_tables_are_not_consumed_by_public_payload_surfaces():
    blocked_references = (
        'RosterStatusSnapshot',
        'roster_status_snapshots',
        'PlayerTransaction',
        'player_transactions',
        'GamePlayByPlayEvent',
        'game_play_by_play_events',
        'PlayByPlayProcessedGame',
        'play_by_play_processed_games',
        'TeamGamePitchingSplit',
        'team_game_pitching_splits',
    )

    for path in PUBLIC_PAYLOAD_SURFACES:
        text = path.read_text(encoding='utf-8')
        for reference in blocked_references:
            assert reference not in text, f'{reference} leaked into {path}'


def test_phase0c_models_do_not_persist_raw_or_free_text_source_payloads():
    forbidden_column_names = {
        'raw_json',
        'raw_response',
        'raw_payload',
        'raw_play_by_play_json',
        'raw_pbp_json',
        'raw_transaction_json',
        'injury_description',
        'injury_text',
        'free_text_injury',
    }
    for model in (
        RosterStatusSnapshot,
        PlayerTransaction,
        GamePlayByPlayEvent,
        PlayByPlayProcessedGame,
        TeamGamePitchingSplit,
    ):
        column_names = {column.name.lower() for column in model.__table__.columns}
        assert column_names.isdisjoint(forbidden_column_names), model.__name__


def test_phase0c_modules_do_not_add_live_pitch_level_or_statcast_ingestion():
    forbidden_text = (
        'feed/live',
        'raw_play_by_play_json',
        'raw_pbp_json',
        'raw_transaction_json',
        'statcast',
        'pitchdata',
        'pitch_data',
    )

    for path in PHASE0C_MODULES:
        text = path.read_text(encoding='utf-8').lower()
        for token in forbidden_text:
            assert token not in text, f'{token} found in {path}'


def test_phase0c_foundation_columns_do_not_encode_public_interpretation():
    forbidden_fragments = (
        'pressure',
        'traffic_label',
        'clean_traffic',
        'role_inference',
        'opener',
        'bulk',
        'health_claim',
        'prediction',
        'odds',
        'confidence',
        'manager_intent',
        'starter_pressure',
        'il_pressure',
    )

    for model in (
        RosterStatusSnapshot,
        PlayerTransaction,
        GamePlayByPlayEvent,
        PlayByPlayProcessedGame,
        TeamGamePitchingSplit,
    ):
        for column in model.__table__.columns:
            lowered = column.name.lower()
            for fragment in forbidden_fragments:
                assert fragment not in lowered, f'{fragment} found in {model.__name__}.{column.name}'


def test_phase0c_foundation_report_records_exit_and_sync_budget_boundaries():
    report = (REPO_ROOT / 'docs/phase0c/07_foundation_report.md').read_text(
        encoding='utf-8'
    )

    for heading in (
        '## Source Coverage Integration',
        '## Sync-Time Budget',
        '## Phase 0C Exit Checklist',
        '## Phase 0D Handoff',
    ):
        assert heading in report
    for family in (
        'finality/status authority',
        'boxscore expanded fields',
        'inherited-runner fabricated-zero repair',
        'roster status snapshots',
        'transaction and IL typed facts',
        'final play-by-play foundation',
        'team game pitching splits',
        'calendar context',
        'source readiness/provenance framework',
        'public payload isolation',
    ):
        assert family in report
    assert 'Result: PASS' in report
    assert 'timeout-minutes: 25' in report
    assert 'POSTGAME_REFRESH_SNAPSHOT' in report
