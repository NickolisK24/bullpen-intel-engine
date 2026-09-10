#!/usr/bin/env python
"""Run CU-04 against the accepted 15-game real-data set in a disposable DB."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from time import perf_counter

from sqlalchemy import event


BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.environ['AUTO_SYNC'] = 'false'

import run_cu01p_proof as cu01p  # noqa: E402


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    return parser.parse_args(argv)


def _canonical_mutations(game):
    row_mutations = sum(
        row.get('action') != 'unchanged' for row in game.get('rows') or []
    )
    pitch_rows = (
        ((game.get('optional_source_domains') or {}).get('final_play_by_play') or {})
        .get('pitch_rows') or {}
    )
    pitch_mutations = sum(
        int(pitch_rows.get(field) or 0)
        for field in ('inserted', 'updated', 'superseded')
    )
    return row_mutations + pitch_mutations


def run():
    from models.pitcher import Pitcher
    from services import incremental_workload_rest as cu04
    from services import sync as sync_service
    from utils.db import db

    source = cu01p._capture_source()
    with tempfile.TemporaryDirectory(prefix='baseballos-cu04-') as temp_root:
        database_path = Path(temp_root) / 'cu04.db'
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
                total_entries = 0
                total_mismatches = 0
                total_pitcher_ms = 0.0
                total_team_ms = 0.0
                query_count = 0

                def count_query(*_args, **_kwargs):
                    nonlocal query_count
                    query_count += 1

                event.listen(db.engine, 'before_cursor_execute', count_query)
                try:
                    for game in write.get('games') or []:
                        impact = game.get('impact') or {}
                        local_ids = tuple(impact.get('affected_pitcher_ids') or ())
                        team_ids = tuple(impact.get('affected_team_ids') or ())
                        mutations = _canonical_mutations(game)
                        result = cu04.recompute_workload_rest_impact(
                            {
                                'game_pk': game['game_pk'],
                                'canonical_mutation_performed': mutations > 0,
                                'affected_pitcher_ids': local_ids,
                                'affected_team_ids': team_ids,
                            },
                            data_through=game_dates[game['game_pk']],
                        )
                        total_entries += len(result.parity_entries)
                        total_mismatches += len(result.parity_mismatches)
                        total_pitcher_ms += result.pitcher_recomputation_ms
                        total_team_ms += result.team_recomputation_ms
                        per_game.append({
                            'game_pk': game['game_pk'],
                            'data_through': result.data_through,
                            'canonical_mutations': mutations,
                            'affected_pitchers': len(local_ids),
                            'affected_teams': list(team_ids),
                            'pitchers_recomputed': len(result.pitchers_recomputed),
                            'teams_recomputed': len(result.teams_recomputed),
                            'parity_fields': len(result.parity_entries),
                            'parity_mismatches': len(result.parity_mismatches),
                            'status': result.status,
                        })
                finally:
                    event.remove(
                        db.engine, 'before_cursor_execute', count_query,
                    )

                replay = cu01p._run_reviewed_write(
                    date(2026, 8, 27), list(cu01p.REPLAY_GAME_PKS),
                )['write']
                replay_mutations = sum(
                    _canonical_mutations(game) for game in replay.get('games') or []
                )
                replay_affected_pitchers = sorted({
                    pitcher_id
                    for game in replay.get('games') or []
                    for pitcher_id in (
                        (game.get('impact') or {}).get('affected_pitcher_ids') or ()
                    )
                })
                replay_affected_teams = sorted({
                    team_id
                    for game in replay.get('games') or []
                    for team_id in (
                        (game.get('impact') or {}).get('affected_team_ids') or ()
                    )
                })
                after_publication = cu01p._table_fingerprints()
                position_players = cu01p._position_player_proof()
                canonical_pitcher_ids = [
                    row[0]
                    for row in db.session.query(Pitcher.id)
                    .all()
                ]
                team_ids = sorted({
                    team_id
                    for game in source['schedule'].values()
                    for team_id in (
                        cu01p._game_teams(game)['away']['id'],
                        cu01p._game_teams(game)['home']['id'],
                    )
                })
                full_pitcher_started = perf_counter()
                for pitcher_id in canonical_pitcher_ids:
                    cu04._compute_pitcher_workload_rest(
                        pitcher_id,
                        data_through=date(2026, 8, 27),
                        availability_reference_date=date(2026, 8, 28),
                    )
                full_pitcher_ms = (
                    perf_counter() - full_pitcher_started
                ) * 1000.0
                full_team_started = perf_counter()
                for team_id in team_ids:
                    cu04.author_workload_windows(
                        team_id, data_through=date(2026, 8, 27),
                    )
                full_team_ms = (perf_counter() - full_team_started) * 1000.0
                result = {
                    'proof_version': 'CU-04-v1',
                    'generated_at': datetime.now(timezone.utc).isoformat(),
                    'environment': {
                        'database': 'disposable local SQLite',
                        'production_access': False,
                        'publication_authority': False,
                        'raw_payload_retention': 'temporary directory only',
                    },
                    'source': {
                        'captured_at': source['captured_at'],
                        'fingerprint': source['fingerprint'],
                        'games': len(cu01p.SELECTED_GAMES),
                    },
                    'per_game': per_game,
                    'totals': {
                        'games': len(per_game),
                        'pitchers_recomputed': sum(
                            row['pitchers_recomputed'] for row in per_game
                        ),
                        'team_recomputations': sum(
                            row['teams_recomputed'] for row in per_game
                        ),
                        'database_queries_including_shadow_parity': query_count,
                        'parity_fields': total_entries,
                        'parity_mismatches': total_mismatches,
                        'pitcher_recomputation_ms': round(total_pitcher_ms, 3),
                        'team_recomputation_ms': round(total_team_ms, 3),
                    },
                    'replay': {
                        'game_pks': list(cu01p.REPLAY_GAME_PKS),
                        'canonical_mutations': replay_mutations,
                        'affected_pitchers': replay_affected_pitchers,
                        'affected_teams': replay_affected_teams,
                        'cu04_calls': 0 if replay_mutations == 0 else None,
                    },
                    'full_equivalent_measurement': {
                        'canonical_pitchers_one_cycle': len(canonical_pitcher_ids),
                        'teams_one_cycle': len(team_ids),
                        'pitcher_ms_one_cycle': round(full_pitcher_ms, 3),
                        'team_ms_one_cycle': round(full_team_ms, 3),
                        'pitcher_work_units_for_15_broad_cycles': (
                            len(canonical_pitcher_ids) * len(per_game)
                        ),
                        'team_work_units_for_15_broad_cycles': (
                            len(team_ids) * len(per_game)
                        ),
                    },
                    'position_players': position_players,
                    'publication_unchanged': before_publication == after_publication,
                }
                result['passed'] = (
                    len(per_game) == len(cu01p.SELECTED_GAMES)
                    and total_entries > 0
                    and total_mismatches == 0
                    and replay_mutations == 0
                    and not replay_affected_pitchers
                    and not replay_affected_teams
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
