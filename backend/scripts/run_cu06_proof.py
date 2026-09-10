#!/usr/bin/env python
"""Run CU-06 over the accepted 15-game continuous-update proof set."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import run_cu05_proof as cu05_proof


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    return parser.parse_args(argv)


def _snapshot(game_date, team_ids):
    from services import public_serving_authority

    return SimpleNamespace(
        id=6006,
        sync_run_id=6007,
        data_through=game_date,
        availability_reference_date=game_date,
        snapshot_generated_at=datetime.combine(
            game_date, datetime.min.time(), tzinfo=timezone.utc,
        ),
        payload={
            'freshness': {'data_through': game_date.isoformat()},
            public_serving_authority.TEAM_BOARD_PACKAGE_KEY: {
                'contract': public_serving_authority.TEAM_BOARD_PACKAGE_CONTRACT,
                'data_through': game_date.isoformat(),
                'availability_reference_date': game_date.isoformat(),
                'by_team_id': {
                    str(team_id): {
                        'team': {
                            'team_id': team_id,
                            'team_name': f'Team {team_id}',
                            'team_abbreviation': str(team_id),
                        },
                        'records': [],
                        'default_pitcher_ids': [],
                        'roster_authority': {},
                    }
                    for team_id in team_ids
                },
            },
        },
    )


def _builders():
    def board(team_id, snapshot, state):
        return {
            'team': {'team_id': team_id},
            'represented_date': snapshot.data_through.isoformat(),
            'team_state': deepcopy(state),
            'groups': [],
            'publication_affected': False,
        }

    def listing(_snapshot, states):
        return {
            'teams': [
                {
                    'team_id': team_id,
                    'team_name': f'Team {team_id}',
                    'team_abbreviation': str(team_id),
                    'team_state': deepcopy(state),
                }
                for team_id, state in sorted(states.items())
            ],
        }

    def matchup(game, _snapshot, states):
        return {
            'game': {'game_pk': game.game_pk},
            'away': deepcopy(states.get(game.away_team_id)),
            'home': deepcopy(states.get(game.home_team_id)),
            'prediction_applied': False,
        }

    def tonight(game, _snapshot, states, _records, _listing):
        return {
            'games': [{
                'game_pk': game.game_pk,
                'away': {'team_state': deepcopy(states.get(game.away_team_id))},
                'home': {'team_state': deepcopy(states.get(game.home_team_id))},
            }],
        }
    return board, listing, matchup, tonight


def _hook(**context):
    from models.slate_game import SlateGame
    from services import incremental_read_model_rebuild as cu06
    from utils.db import db

    source = context['source']
    game_pk = context['game']['game_pk']
    schedule = source['schedule'][str(game_pk)]
    teams = cu05_proof.cu01p._game_teams(schedule)
    away_team_id = int(teams['away']['id'])
    home_team_id = int(teams['home']['id'])
    row = SlateGame(
        game_pk=game_pk,
        game_date_et=context['game_date'],
        game_time_utc=datetime.combine(
            context['game_date'], datetime.min.time(),
        ),
        away_team_id=away_team_id,
        home_team_id=home_team_id,
        normalized_state=SlateGame.STATE_COMPLETED,
    )
    db.session.merge(row)
    db.session.flush()
    builders = _builders()
    result = cu06.rebuild_read_model_impact(
        context['cu05_result'],
        source_snapshot=_snapshot(
            context['game_date'], context['affected_team_ids'],
        ),
        team_board_builder=builders[0],
        league_listing_builder=builders[1],
        matchup_builder=builders[2],
        tonight_builder=builders[3],
    )
    return {
        'game_pk': game_pk,
        'evidence_mode': (
            'natural captured canonical chain plus controlled real-shape '
            'current serving composition'
        ),
        'team_boards_rebuilt': len(result.team_boards_rebuilt),
        'league_rows_rebuilt': len(result.league_rows_rebuilt),
        'matchups_rebuilt': len(result.matchups_rebuilt),
        'tonight_entries_rebuilt': len(result.tonight_entries_rebuilt),
        'pitcher_models_rebuilt': len(result.pitcher_models_rebuilt),
        'parity_objects': len(result.parity_entries),
        'parity_mismatches': len(result.parity_mismatches),
        'publication_affected': result.publication_affected,
        'cache_invalidation_triggered': result.cache_invalidation_triggered,
        'status': result.status,
        'rebuild_ms': result.rebuild_ms,
    }


def run():
    base = cu05_proof.run(proof_hook=_hook)
    rows = base.pop('extension_results')
    totals = {
        'games': len(rows),
        'team_boards_rebuilt': sum(row['team_boards_rebuilt'] for row in rows),
        'league_rows_rebuilt': sum(row['league_rows_rebuilt'] for row in rows),
        'matchups_rebuilt': sum(row['matchups_rebuilt'] for row in rows),
        'tonight_entries_rebuilt': sum(
            row['tonight_entries_rebuilt'] for row in rows
        ),
        'pitcher_models_rebuilt': sum(row['pitcher_models_rebuilt'] for row in rows),
        'parity_objects': sum(row['parity_objects'] for row in rows),
        'parity_mismatches': sum(row['parity_mismatches'] for row in rows),
        'rebuild_ms': round(sum(row['rebuild_ms'] for row in rows), 3),
    }
    result = {
        'proof_version': 'CU-06-v1',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'source': base['source'],
        'environment': base['environment'],
        'evidence_boundary': {
            **base['evidence_boundary'],
            'read_models': 'controlled real-shape authoritative builder injection',
        },
        'per_game': rows,
        'totals': totals,
        'upstream_cu05': base['totals'],
        'replay': {
            **base['replay'],
            'cu06_calls': 0 if base['replay']['canonical_mutations'] == 0 else None,
        },
        'position_players': base['position_players'],
        'publication_unchanged': base['publication_unchanged'],
    }
    result['passed'] = (
        base['passed']
        and len(rows) == 15
        and totals['parity_objects'] > 0
        and totals['parity_mismatches'] == 0
        and all(row['status'] == 'complete' for row in rows)
        and all(not row['publication_affected'] for row in rows)
        and all(not row['cache_invalidation_triggered'] for row in rows)
    )
    return result


def main(argv=None):
    args = parse_args(argv)
    result = run()
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding='utf-8')
    print(json.dumps({
        'output': str(output),
        'passed': result['passed'],
        'totals': result['totals'],
    }, indent=2, sort_keys=True))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
