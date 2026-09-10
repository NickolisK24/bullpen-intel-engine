"""CU-01 affected-entity and workload-input shadow proof.

This module does not write or publish. It makes the future incremental seam
explicit: one finalized game resolves to relief appearances, affected pitchers,
affected game-side teams, and a comparison with the canonical rows currently
owned by the scheduled sync path.
"""

from __future__ import annotations

from models.game_log import GameLog
from models.pitcher import Pitcher


WORKLOAD_INPUT_FIELDS = (
    ('game_date', 'game_date'),
    ('outs_recorded', 'innings_pitched_outs'),
    ('pitches_thrown', 'pitches_thrown'),
    ('games_started', 'games_started'),
    ('team_id', 'appearance_team_id'),
)

NEWLY_CAPTURED_APPEARANCE_FIELDS = (
    'hit_batters', 'wild_pitches', 'source_authority',
    'source_endpoint', 'source_revision',
)
NEWLY_CAPTURED_PITCH_DOMAINS = (
    'pitch_identity_and_outcome', 'velocity_spin_and_movement',
    'release_and_extension', 'zone_and_location', 'batted_ball_outcome',
)
DERIVED_FIELDS_EXCLUDED_FROM_PARITY = (
    'innings_pitched', 'fatigue', 'rest_and_availability', 'team_state',
)
OPTIONAL_SUPPORTED_APPEARANCE_FIELDS = (
    'pitches_thrown', 'strikes', 'hits_allowed', 'runs_allowed',
    'earned_runs', 'walks', 'strikeouts', 'home_runs_allowed',
    'batters_faced', 'balls', 'games_finished', 'hit_batters',
    'wild_pitches', 'inherited_runners', 'inherited_runners_scored',
    'save_situation', 'hold', 'blown_save', 'win', 'loss', 'save',
)


def build_game_impact(
    appearances,
    *,
    appearance_mutations=None,
    pitch_mutations=None,
) -> dict:
    relief = [row for row in appearances or () if row.get('is_reliever')]
    observed_pitcher_mlb_ids = sorted({
        row.get('pitcher_mlb_id') for row in relief
        if row.get('pitcher_mlb_id') is not None
    })
    observed_team_ids = sorted({
        row.get('team_id') for row in relief if row.get('team_id') is not None
    })
    relief_by_pitcher = {
        row.get('pitcher_mlb_id'): row for row in relief
        if row.get('pitcher_mlb_id') is not None
    }
    if appearance_mutations is None and pitch_mutations is None:
        affected_pitcher_mlb_ids = observed_pitcher_mlb_ids
    else:
        affected_pitcher_mlb_ids = {
            row.get('pitcher_mlb_id')
            for row in appearance_mutations or ()
            if row.get('action') in {'insert', 'update'}
            and row.get('pitcher_mlb_id') in relief_by_pitcher
        }
        affected_pitcher_mlb_ids.update(
            pitcher_mlb_id
            for pitcher_mlb_id in (
                (pitch_mutations or {}).get('affected_pitcher_mlb_ids') or ()
            )
            if pitcher_mlb_id in relief_by_pitcher
        )
        affected_pitcher_mlb_ids = sorted(affected_pitcher_mlb_ids)
    affected_team_ids = sorted({
        relief_by_pitcher[pitcher_mlb_id].get('team_id')
        for pitcher_mlb_id in affected_pitcher_mlb_ids
        if relief_by_pitcher[pitcher_mlb_id].get('team_id') is not None
    })
    local_ids = _local_pitcher_ids(observed_pitcher_mlb_ids)
    game_pks = sorted({
        row.get('game_pk') for row in relief if row.get('game_pk') is not None
    })
    stored = _stored_rows(game_pks, local_ids.values())

    rows = []
    equivalent_fields = set()
    differing_fields = set()
    unsupported_fields = set()
    unresolved = 0
    for appearance in relief:
        mlb_id = appearance.get('pitcher_mlb_id')
        game_pk = appearance.get('game_pk')
        local_id = local_ids.get(mlb_id)
        canonical = stored.get((local_id, game_pk)) if local_id is not None else None
        differences = []
        equivalents = []
        if canonical is None:
            unresolved += 1
            result = 'missing_canonical_row'
        else:
            for source_field, canonical_field in WORKLOAD_INPUT_FIELDS:
                if appearance.get(source_field) == getattr(canonical, canonical_field, None):
                    equivalents.append(canonical_field)
                    equivalent_fields.add(canonical_field)
                else:
                    differences.append(canonical_field)
                    differing_fields.add(canonical_field)
            result = 'equivalent' if not differences else 'different'
            if differences:
                unresolved += 1

        missing_optional = sorted(
            field for field in OPTIONAL_SUPPORTED_APPEARANCE_FIELDS
            if appearance.get(field) is None
        )
        unsupported_fields.update(missing_optional)
        rows.append({
            'game_pk': game_pk,
            'pitcher_mlb_id': mlb_id,
            'local_pitcher_id': local_id,
            'appearance_team_id': appearance.get('team_id'),
            'result': result,
            'equivalent_fields': sorted(equivalents),
            'differing_fields': sorted(differences),
            'source_unknown_fields': missing_optional,
        })

    return {
        'publication_affected': False,
        'affected_pitcher_mlb_ids': affected_pitcher_mlb_ids,
        'affected_pitcher_ids': sorted(
            local_ids[mlb_id] for mlb_id in affected_pitcher_mlb_ids
            if mlb_id in local_ids
        ),
        'affected_team_ids': affected_team_ids,
        'observed_pitcher_mlb_ids': observed_pitcher_mlb_ids,
        'observed_team_ids': observed_team_ids,
        'relief_appearance_count': len(relief),
        'workload_comparison': {
            'coverage_complete': unresolved == 0,
            'parity': unresolved == 0,
            'rows_compared': len(relief),
            'rows_unresolved': unresolved,
            'equivalent_fields': sorted(equivalent_fields),
            'differing_fields': sorted(differing_fields),
            'newly_captured_appearance_fields': list(NEWLY_CAPTURED_APPEARANCE_FIELDS),
            'newly_captured_pitch_domains': list(NEWLY_CAPTURED_PITCH_DOMAINS),
            'derived_fields_excluded': list(DERIVED_FIELDS_EXCLUDED_FROM_PARITY),
            'source_unknown_fields': sorted(unsupported_fields),
            'rows': rows,
        },
    }


def _local_pitcher_ids(mlb_ids):
    if not mlb_ids:
        return {}
    return {
        row.mlb_id: row.id
        for row in Pitcher.query.filter(Pitcher.mlb_id.in_(mlb_ids)).all()
    }


def _stored_rows(game_pks, local_ids):
    game_pks = list(game_pks)
    local_ids = list(local_ids)
    if not game_pks or not local_ids:
        return {}
    return {
        (row.pitcher_id, row.mlb_game_pk): row
        for row in GameLog.query.filter(
            GameLog.mlb_game_pk.in_(game_pks),
            GameLog.pitcher_id.in_(local_ids),
        ).all()
    }
