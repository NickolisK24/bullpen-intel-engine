"""Correction-policy registry for source-backed storage.

Future 0C branches should register correction-sensitive tables and fields here
before those fields ship. The registry is intentionally small: it records which
fields may update, which fields fail to UNKNOWN on unsafe conflict, which
conflicts should dead-letter, and which fields are immutable identity keys.
"""

from __future__ import annotations

from dataclasses import dataclass


class CorrectionPolicyError(AssertionError):
    """Raised when correction-sensitive storage lacks an explicit policy."""


@dataclass(frozen=True)
class CorrectionFieldPolicy:
    field_name: str
    update_after_final: bool = False
    unknown_on_unsafe_conflict: bool = False
    dead_letter_on_conflict: bool = True
    identity_key: bool = False

    def to_dict(self) -> dict:
        return {
            'field_name': self.field_name,
            'update_after_final': self.update_after_final,
            'unknown_on_unsafe_conflict': self.unknown_on_unsafe_conflict,
            'dead_letter_on_conflict': self.dead_letter_on_conflict,
            'identity_key': self.identity_key,
        }


@dataclass(frozen=True)
class SourceCorrectionPolicy:
    name: str
    source_family: str
    model_name: str
    fields: tuple[CorrectionFieldPolicy, ...]

    @property
    def field_names(self) -> set[str]:
        return {field.field_name for field in self.fields}

    @property
    def identity_fields(self) -> set[str]:
        return {field.field_name for field in self.fields if field.identity_key}

    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'source_family': self.source_family,
            'model_name': self.model_name,
            'fields': [field.to_dict() for field in self.fields],
        }


_POLICIES: dict[str, SourceCorrectionPolicy] = {}


def register_correction_policy(policy: SourceCorrectionPolicy) -> SourceCorrectionPolicy:
    if policy.name in _POLICIES:
        raise CorrectionPolicyError(f'duplicate correction policy: {policy.name}')
    if not policy.fields:
        raise CorrectionPolicyError(f'correction policy has no fields: {policy.name}')
    _POLICIES[policy.name] = policy
    return policy


def registered_correction_policies() -> dict[str, SourceCorrectionPolicy]:
    return dict(_POLICIES)


def correction_policy(policy_name: str) -> SourceCorrectionPolicy:
    try:
        return _POLICIES[policy_name]
    except KeyError as exc:
        raise CorrectionPolicyError(
            f'missing correction policy: {policy_name}'
        ) from exc


def validate_correction_sensitive_model(model_class) -> bool:
    """Fail if a correction-sensitive model/field lacks a registered policy."""
    sensitive_fields = set(getattr(model_class, '__correction_sensitive_fields__', ()))
    identity_fields = set(getattr(model_class, '__correction_identity_fields__', ()))
    if not sensitive_fields and not identity_fields:
        return True

    policy_name = getattr(model_class, '__correction_policy_name__', None)
    if not policy_name:
        raise CorrectionPolicyError(
            f'{model_class.__name__} declares correction-sensitive storage '
            'without __correction_policy_name__'
        )

    policy = correction_policy(policy_name)
    if policy.model_name != model_class.__name__:
        raise CorrectionPolicyError(
            f'{model_class.__name__} uses policy {policy.name} owned by '
            f'{policy.model_name}'
        )

    missing_fields = sensitive_fields - policy.field_names
    if missing_fields:
        raise CorrectionPolicyError(
            f'{model_class.__name__} fields missing correction policy: '
            f'{sorted(missing_fields)}'
        )

    missing_identity = identity_fields - policy.identity_fields
    if missing_identity:
        raise CorrectionPolicyError(
            f'{model_class.__name__} identity fields missing identity policy: '
            f'{sorted(missing_identity)}'
        )
    return True


def validate_correction_sensitive_models(model_classes) -> bool:
    for model_class in model_classes:
        validate_correction_sensitive_model(model_class)
    return True


GAME_LOG_CORRECTION_POLICY = register_correction_policy(SourceCorrectionPolicy(
    name='game_log_pitching_line_corrections',
    source_family='game_logs',
    model_name='GameLog',
    fields=(
        CorrectionFieldPolicy('pitcher_id', identity_key=True),
        CorrectionFieldPolicy('mlb_game_pk', identity_key=True),
        CorrectionFieldPolicy('game_date', update_after_final=True),
        CorrectionFieldPolicy('game_type', update_after_final=True),
        CorrectionFieldPolicy('opponent', update_after_final=True),
        CorrectionFieldPolicy('opponent_abbreviation', update_after_final=True),
        CorrectionFieldPolicy('games_started', update_after_final=True),
        CorrectionFieldPolicy('innings_pitched', update_after_final=True),
        CorrectionFieldPolicy('innings_pitched_outs', update_after_final=True),
        CorrectionFieldPolicy(
            'pitches_thrown',
            update_after_final=True,
            unknown_on_unsafe_conflict=True,
        ),
        CorrectionFieldPolicy('strikes', update_after_final=True),
        CorrectionFieldPolicy('hits_allowed', update_after_final=True),
        CorrectionFieldPolicy('runs_allowed', update_after_final=True),
        CorrectionFieldPolicy('earned_runs', update_after_final=True),
        CorrectionFieldPolicy('walks', update_after_final=True),
        CorrectionFieldPolicy('strikeouts', update_after_final=True),
        CorrectionFieldPolicy('home_runs_allowed', update_after_final=True),
        CorrectionFieldPolicy('batters_faced', update_after_final=True),
        CorrectionFieldPolicy('balls', update_after_final=True),
        CorrectionFieldPolicy('games_finished', update_after_final=True),
        CorrectionFieldPolicy(
            'inherited_runners',
            update_after_final=True,
            unknown_on_unsafe_conflict=True,
        ),
        CorrectionFieldPolicy(
            'inherited_runners_scored',
            update_after_final=True,
            unknown_on_unsafe_conflict=True,
        ),
        CorrectionFieldPolicy('save_situation', update_after_final=True),
        CorrectionFieldPolicy('hold', update_after_final=True),
        CorrectionFieldPolicy('blown_save', update_after_final=True),
        CorrectionFieldPolicy('win', update_after_final=True),
        CorrectionFieldPolicy('loss', update_after_final=True),
        CorrectionFieldPolicy('save', update_after_final=True),
        CorrectionFieldPolicy('leverage_index', update_after_final=True),
    ),
))

ROSTER_STATUS_SNAPSHOT_CORRECTION_POLICY = register_correction_policy(SourceCorrectionPolicy(
    name='roster_status_snapshot_corrections',
    source_family='roster_status_snapshots',
    model_name='RosterStatusSnapshot',
    fields=(
        CorrectionFieldPolicy('pitcher_id', identity_key=True),
        CorrectionFieldPolicy('mlb_id', identity_key=True),
        CorrectionFieldPolicy('team_id', identity_key=True),
        CorrectionFieldPolicy('snapshot_date', identity_key=True),
        CorrectionFieldPolicy('roster_status', update_after_final=True),
        CorrectionFieldPolicy('active_roster', update_after_final=True),
        CorrectionFieldPolicy('forty_man_roster', update_after_final=True),
        CorrectionFieldPolicy('position_code', update_after_final=True),
        CorrectionFieldPolicy('position_name', update_after_final=True),
        CorrectionFieldPolicy('position_type', update_after_final=True),
        CorrectionFieldPolicy('two_way_eligible', update_after_final=True),
        CorrectionFieldPolicy('roster_status_raw', update_after_final=True),
        CorrectionFieldPolicy('roster_status_raw_code', update_after_final=True),
        CorrectionFieldPolicy('roster_status_raw_description', update_after_final=True),
        CorrectionFieldPolicy('source', update_after_final=True),
    ),
))
