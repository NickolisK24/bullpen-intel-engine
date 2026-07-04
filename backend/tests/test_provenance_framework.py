from datetime import datetime
from types import SimpleNamespace

import pytest

from models.game_log import GameLog
from models.play_by_play_foundation import GamePlayByPlayEvent, PlayByPlayProcessedGame
from models.player_transaction import PlayerTransaction
from models.roster_status_snapshot import RosterStatusSnapshot
from services import source_provenance
from services.source_correction_policies import (
    CorrectionPolicyError,
    correction_policy,
    validate_correction_sensitive_model,
)


def test_generic_provenance_helpers_set_and_serialize_fields():
    record = SimpleNamespace(
        source=None,
        sync_run_id=None,
        first_seen_at=None,
        last_corrected_at=None,
        correction_count=0,
        correction_source=None,
    )
    first_seen = datetime(2026, 6, 1, 12, 0, 0)
    corrected_at = datetime(2026, 6, 2, 12, 0, 0)

    source_provenance.apply_initial_source_provenance(
        record,
        source='statsapi_core',
        sync_run_id=10,
        first_seen_at=first_seen,
    )
    source_provenance.record_source_correction(
        record,
        correction_source='postgame_boxscore',
        sync_run_id=11,
        corrected_at=corrected_at,
    )
    payload = source_provenance.source_provenance_from_record(record).to_dict()

    assert payload == {
        'source': 'statsapi_core',
        'sync_run_id': 11,
        'first_seen_at': '2026-06-01T12:00:00',
        'last_corrected_at': '2026-06-02T12:00:00',
        'correction_count': 1,
        'correction_source': 'postgame_boxscore',
    }


def test_game_log_provenance_adapter_uses_existing_phase_0a_fields():
    log = SimpleNamespace(
        created_at=datetime(2026, 6, 1, 12, 0, 0),
        stat_correction_count=2,
        last_stat_correction_at=datetime(2026, 6, 2, 12, 0, 0),
        last_stat_correction_source='daily_game_log',
        last_stat_correction_sync_run_id=22,
    )

    payload = source_provenance.game_log_stat_correction_provenance(log).to_dict()

    assert payload['source'] == 'game_logs'
    assert payload['sync_run_id'] == 22
    assert payload['correction_count'] == 2
    assert payload['correction_source'] == 'daily_game_log'
    assert source_provenance.provenance_ready(
        source_provenance.game_log_stat_correction_provenance(log)
    )


def test_registered_game_log_policy_matches_existing_correction_behavior():
    assert validate_correction_sensitive_model(GameLog)

    policy = correction_policy('game_log_pitching_line_corrections')
    assert policy.source_family == 'game_logs'
    assert {'pitcher_id', 'mlb_game_pk'} == policy.identity_fields
    pitches_policy = [
        field for field in policy.fields if field.field_name == 'pitches_thrown'
    ][0]
    assert pitches_policy.update_after_final is True
    assert pitches_policy.unknown_on_unsafe_conflict is True
    assert pitches_policy.dead_letter_on_conflict is True


def test_registered_roster_snapshot_policy_matches_snapshot_authority():
    assert validate_correction_sensitive_model(RosterStatusSnapshot)

    policy = correction_policy('roster_status_snapshot_corrections')
    assert policy.source_family == 'roster_status_snapshots'
    assert {
        'pitcher_id',
        'mlb_id',
        'team_id',
        'snapshot_date',
    } == policy.identity_fields
    status_policy = [
        field for field in policy.fields if field.field_name == 'roster_status'
    ][0]
    assert status_policy.update_after_final is True
    assert status_policy.dead_letter_on_conflict is True


def test_registered_player_transaction_policy_matches_transaction_foundation():
    assert validate_correction_sensitive_model(PlayerTransaction)

    policy = correction_policy('player_transaction_corrections')
    assert policy.source_family == 'player_transactions'
    assert {'transaction_key'} == policy.identity_fields
    category_policy = [
        field for field in policy.fields if field.field_name == 'normalized_category'
    ][0]
    alignment_policy = [
        field for field in policy.fields if field.field_name == 'roster_snapshot_alignment'
    ][0]
    assert category_policy.update_after_final is True
    assert category_policy.unknown_on_unsafe_conflict is True
    assert alignment_policy.update_after_final is True
    assert alignment_policy.unknown_on_unsafe_conflict is True


def test_registered_final_pbp_event_policy_matches_foundation_storage():
    assert validate_correction_sensitive_model(GamePlayByPlayEvent)

    policy = correction_policy('game_play_by_play_event_corrections')
    assert policy.source_family == 'final_play_by_play'
    assert {'mlb_game_pk', 'event_index'} == policy.identity_fields
    event_type_policy = [
        field for field in policy.fields if field.field_name == 'event_type'
    ][0]
    pitcher_policy = [
        field for field in policy.fields if field.field_name == 'pitcher_mlb_id'
    ][0]
    assert event_type_policy.update_after_final is True
    assert event_type_policy.unknown_on_unsafe_conflict is True
    assert pitcher_policy.update_after_final is True
    assert pitcher_policy.unknown_on_unsafe_conflict is True


def test_registered_final_pbp_marker_policy_matches_marker_lifecycle():
    assert validate_correction_sensitive_model(PlayByPlayProcessedGame)

    policy = correction_policy('play_by_play_processed_game_corrections')
    assert policy.source_family == 'final_play_by_play'
    assert {'mlb_game_pk'} == policy.identity_fields
    status_policy = [
        field for field in policy.fields if field.field_name == 'processing_status'
    ][0]
    assert status_policy.update_after_final is True
    assert status_policy.unknown_on_unsafe_conflict is True


def test_unregistered_correction_sensitive_model_fails_contract():
    class FutureSourceModel:
        __correction_sensitive_fields__ = ('future_field',)

    with pytest.raises(CorrectionPolicyError):
        validate_correction_sensitive_model(FutureSourceModel)


def test_registered_policy_missing_sensitive_field_fails_contract():
    class BadGameLogExtension:
        __correction_policy_name__ = 'game_log_pitching_line_corrections'
        __correction_sensitive_fields__ = ('future_field',)

    with pytest.raises(CorrectionPolicyError):
        validate_correction_sensitive_model(BadGameLogExtension)
