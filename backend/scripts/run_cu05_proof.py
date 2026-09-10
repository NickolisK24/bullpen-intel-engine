#!/usr/bin/env python
"""Run CU-05 against the accepted 15-game real-data proof set.

Canonical acquisition and CU-04 workload/rest are natural captured-game proof.
Current active-bullpen membership and higher-level state distribution use a
controlled real-shape overlay because the historical capture does not contain
the later roster snapshots needed to reproduce current membership.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.environ['AUTO_SYNC'] = 'false'

import run_cu01p_proof as cu01p  # noqa: E402
import run_cu04_proof as cu04_proof  # noqa: E402


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    return parser.parse_args(argv)


def _controlled_provider(team_by_pitcher, excluded_pitcher_ids=()):
    from services.pitcher_public_labels import build_public_arm_read
    from services.team_state_public_vocabulary import INTERNAL_TO_PUBLIC_STATE
    from team_operations import assemble_bullpen_readiness

    excluded_pitcher_ids = set(excluded_pitcher_ids)

    def provider(
        team_id, *, reference_dates_out, arm_reads_out,
        classified_record_overrides, represented_date_override, **_kwargs,
    ):
        availability_date = represented_date_override + timedelta(days=1)
        reference_dates_out.update({
            'membership_reference_date': represented_date_override,
            'availability_reference_date': availability_date,
        })
        selected = [
            record for pitcher_id, record in classified_record_overrides.items()
            if team_by_pitcher.get(pitcher_id) == team_id
            and pitcher_id not in excluded_pitcher_ids
        ]
        arm_records = []
        readiness_records = []
        for record in selected:
            pitcher = record['pitcher']
            availability = dict(record.get('availability') or {})
            arm_records.append({
            'pitcher_id': pitcher.id,
            'team_id': team_id,
            'public_read': build_public_arm_read(availability),
            'evidence_state': {
                'data_state': availability.get('data_state'),
                'confidence': availability.get('confidence'),
            },
            'roster_authority': {
                'version': 'controlled_real_shape_v1',
                'status': 'ACTIVE',
                'is_authoritative': True,
                'is_active_mlb': True,
            },
            })
            status = availability.get('availability_status')
            readiness_records.append({
            'availability_status': status,
            'workload_category': (
                'elevated' if status in {'Avoid', 'Unavailable'}
                else 'moderate' if status in {'Monitor', 'Limited'}
                else 'low'
            ),
            'throwing_hand': getattr(pitcher, 'throws', None) or 'unknown',
            'has_current_workload': availability.get('data_state') == 'fresh',
            'has_availability': bool(status),
            'active': True,
            })
        member_ids = sorted(record['pitcher_id'] for record in arm_records)
        arm_reads_out.update({
        'member_pitcher_ids': member_ids,
        'missing_record_pitcher_ids': [],
        'records': arm_records,
        })
        confidence = 'high' if readiness_records else 'unknown'
        data_state = 'fresh' if readiness_records else 'missing'
        trust = {
        'confidence': confidence,
        'confidence_reasons': ['controlled_real_shape_membership'],
        'data_state': data_state,
        'source_evidence_state': 'represented' if readiness_records else 'missing',
        'governance_state': 'internal_uncertified',
        'generated_at': f'{availability_date.isoformat()}T00:00:00+00:00',
        'limitations': [],
        'explanations': [],
        'refusal_reasons': [],
        'trust_validation_errors': [],
        'ranking_applied': False,
        'selection_made': False,
        }
        freshness = {
        'freshness_state': 'current',
        'data_through': represented_date_override.isoformat(),
        'latest_workload_date': represented_date_override.isoformat(),
        'last_successful_sync': f'{availability_date.isoformat()}T00:00:00+00:00',
        'sync_status': 'success',
        'is_current': True,
        'is_stale': False,
        'generated_at': f'{availability_date.isoformat()}T00:00:00+00:00',
        'limitations': [],
        'latest_fatigue_calculated_at': f'{availability_date.isoformat()}T00:00:00+00:00',
        'latest_sync_status': 'success',
        'missing_data_warning': False,
        'stale_warning': False,
        }
        payload = assemble_bullpen_readiness(
        team={
            'team_id': team_id,
            'team_name': f'Team {team_id}',
            'team_abbreviation': str(team_id),
        },
        pitcher_records=readiness_records,
        trust_metadata=trust,
        freshness=freshness,
        generated_at=f'{availability_date.isoformat()}T00:00:00+00:00',
        )
        assert payload['readiness']['status_code'] in set(INTERNAL_TO_PUBLIC_STATE) | {
            'data_limited'
        }
        return payload

    return provider


def run(*, proof_hook=None):
    from models.game_log import GameLog
    from models.pitcher import Pitcher
    from services import incremental_arm_read_team_state as cu05
    from services import incremental_workload_rest as cu04
    from services import sync as sync_service
    from utils.db import db

    source = cu01p._capture_source()
    with tempfile.TemporaryDirectory(prefix='baseballos-cu05-') as temp_root:
        database_path = Path(temp_root) / 'cu05.db'
        flask_app = cu01p._new_app(database_path)
        with flask_app.app_context():
            db.create_all()
        cu01p._seed_schedule_and_position_players(flask_app, source)
        prior_client = sync_service.mlb_client
        sync_service.mlb_client = cu01p.CapturedMlbClient(source)
        try:
            with flask_app.app_context():
                before_publication = cu01p._table_fingerprints()
                write = cu01p._run_reviewed_write(
                    date(2026, 8, 27),
                    [game_pk for game_pk, _day, _reason in cu01p.SELECTED_GAMES],
                )['write']
                game_dates = {
                    game_pk: date.fromisoformat(game_date)
                    for game_pk, game_date, _reason in cu01p.SELECTED_GAMES
                }
                per_game = []
                total_arm_entries = 0
                total_team_entries = 0
                total_mismatches = 0
                arm_ms = 0.0
                team_ms = 0.0
                state_counts = Counter()
                extension_results = []

                for game in write.get('games') or []:
                    impact = game.get('impact') or {}
                    pitcher_ids = tuple(impact.get('affected_pitcher_ids') or ())
                    team_ids = tuple(impact.get('affected_team_ids') or ())
                    mutations = cu04_proof._canonical_mutations(game)
                    workload = cu04.recompute_workload_rest_impact(
                        {
                            'game_pk': game['game_pk'],
                            'canonical_mutation_performed': mutations > 0,
                            'affected_pitcher_ids': pitcher_ids,
                            'affected_team_ids': team_ids,
                        },
                        data_through=game_dates[game['game_pk']],
                    )
                    appearance_rows = GameLog.query.filter_by(
                        mlb_game_pk=game['game_pk']
                    ).all()
                    team_by_pitcher = {
                        row.pitcher_id: row.appearance_team_id
                        for row in appearance_rows
                        if row.pitcher_id in pitcher_ids
                        and row.appearance_team_id is not None
                    }
                    excluded_ids = {
                        pitcher.id
                        for pitcher in Pitcher.query.filter(
                            Pitcher.mlb_id.in_(cu01p.POSITION_PLAYER_IDS)
                        ).all()
                    }
                    active_by_team = {}
                    for pitcher_id, team_id in team_by_pitcher.items():
                        if pitcher_id not in excluded_ids:
                            active_by_team.setdefault(int(team_id), set()).add(
                                pitcher_id
                            )

                    def membership_provider(team_id, _reference_date):
                        ids = frozenset(active_by_team.get(int(team_id), ()))
                        return ids, bool(ids)

                    result = cu05.recompute_arm_reads_team_state(
                        workload,
                        readiness_provider=_controlled_provider(
                            team_by_pitcher, excluded_ids,
                        ),
                        membership_provider=membership_provider,
                    )
                    arm_entries = sum(
                        row['scope'] == 'pitcher' for row in result.parity_entries
                    )
                    team_entries = sum(
                        row['scope'] == 'team' for row in result.parity_entries
                    )
                    total_arm_entries += arm_entries
                    total_team_entries += team_entries
                    total_mismatches += len(result.parity_mismatches)
                    arm_ms += result.arm_read_recomputation_ms
                    team_ms += result.team_state_recomputation_ms
                    for team in result.team_state_results.values():
                        label = (team.get('public_team_state') or {}).get('public_label')
                        state_counts[label or 'Limited/withheld'] += 1
                    per_game.append({
                        'game_pk': game['game_pk'],
                        'evidence_mode': 'natural canonical plus controlled real-shape membership',
                        'canonical_mutations': mutations,
                        'affected_pitchers': len(pitcher_ids),
                        'affected_teams': len(team_ids),
                        'cu04_pitchers': len(workload.pitchers_recomputed),
                        'cu04_teams': len(workload.teams_recomputed),
                        'arm_reads_recomputed': len(result.arm_reads_recomputed),
                        'teams_recomputed': len(result.teams_recomputed),
                        'arm_parity_fields': arm_entries,
                        'team_parity_fields': team_entries,
                        'parity_mismatches': len(result.parity_mismatches),
                        'status': result.status,
                    })
                    if proof_hook is not None:
                        extension_results.append(proof_hook(
                            app=flask_app,
                            source=source,
                            game=game,
                            game_date=game_dates[game['game_pk']],
                            canonical_mutations=mutations,
                            workload_result=workload,
                            cu05_result=result,
                            affected_pitcher_ids=pitcher_ids,
                            affected_team_ids=team_ids,
                        ))

                replay = cu01p._run_reviewed_write(
                    date(2026, 8, 27), list(cu01p.REPLAY_GAME_PKS),
                )['write']
                replay_mutations = sum(
                    cu04_proof._canonical_mutations(game)
                    for game in replay.get('games') or []
                )
                after_publication = cu01p._table_fingerprints()
                position_players = cu01p._position_player_proof()
                canonical_pitcher_count = Pitcher.query.count()
                proof_team_ids = {
                    team_id
                    for schedule in source['schedule'].values()
                    for team_id in (
                        cu01p._game_teams(schedule)['away']['id'],
                        cu01p._game_teams(schedule)['home']['id'],
                    )
                }
                arm_work_units = sum(
                    row['arm_reads_recomputed'] for row in per_game
                )
                team_work_units = sum(
                    row['teams_recomputed'] for row in per_game
                )
                result = {
                    'proof_version': 'CU-05-v1',
                    'generated_at': datetime.now(timezone.utc).isoformat(),
                    'environment': {
                        'database': 'disposable local SQLite',
                        'production_access': False,
                        'publication_authority': False,
                    },
                    'source': {
                        'captured_at': source['captured_at'],
                        'fingerprint': source['fingerprint'],
                        'games': len(cu01p.SELECTED_GAMES),
                    },
                    'evidence_boundary': {
                        'canonical_and_workload': 'natural captured real games',
                        'active_membership_and_team_state': 'controlled real-shape overlay',
                        'reason': 'historical capture has no reproducible current roster snapshots',
                    },
                    'per_game': per_game,
                    'extension_results': extension_results,
                    'totals': {
                        'games': len(per_game),
                        'arm_reads_recomputed': sum(
                            row['arm_reads_recomputed'] for row in per_game
                        ),
                        'team_recomputations': sum(
                            row['teams_recomputed'] for row in per_game
                        ),
                        'arm_parity_fields': total_arm_entries,
                        'team_parity_fields': total_team_entries,
                        'parity_fields': total_arm_entries + total_team_entries,
                        'parity_mismatches': total_mismatches,
                        'arm_read_recomputation_ms': round(arm_ms, 3),
                        'team_state_recomputation_ms': round(team_ms, 3),
                        'team_state_distribution': dict(sorted(state_counts.items())),
                    },
                    'replay': {
                        'game_pks': list(cu01p.REPLAY_GAME_PKS),
                        'canonical_mutations': replay_mutations,
                        'cu04_calls': 0 if replay_mutations == 0 else None,
                        'cu05_calls': 0 if replay_mutations == 0 else None,
                    },
                    'incremental_efficiency': {
                        'broad_pitcher_work_units': (
                            canonical_pitcher_count * len(per_game)
                        ),
                        'incremental_arm_read_work_units': arm_work_units,
                        'arm_read_work_ratio': round(
                            arm_work_units
                            / (canonical_pitcher_count * len(per_game)),
                            4,
                        ),
                        'broad_team_state_work_units': (
                            len(proof_team_ids) * len(per_game)
                        ),
                        'incremental_team_state_work_units': team_work_units,
                        'team_state_work_ratio': round(
                            team_work_units
                            / (len(proof_team_ids) * len(per_game)),
                            4,
                        ),
                    },
                    'position_players': position_players,
                    'publication_unchanged': before_publication == after_publication,
                }
                result['passed'] = (
                    len(per_game) == len(cu01p.SELECTED_GAMES)
                    and total_arm_entries > 0
                    and total_team_entries > 0
                    and total_mismatches == 0
                    and replay_mutations == 0
                    and result['publication_unchanged']
                    and all(
                        row.get('current_identity_preserved')
                        for row in position_players
                    )
                )
                db.session.remove()
                db.engine.dispose()
        finally:
            sync_service.mlb_client = prior_client
        return result


def main(argv=None):
    args = parse_args(argv)
    result = run()
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding='utf-8',
    )
    print(json.dumps({
        'output': str(output),
        'passed': result['passed'],
        'totals': result['totals'],
    }, indent=2, sort_keys=True))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
