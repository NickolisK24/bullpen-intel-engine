"""Read-only CR-04 production proof for publication-bound request paths."""

from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import sys
from time import perf_counter


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ['AUTO_SYNC'] = 'false'


IGNORED_KEYS = frozenset({
    'atomic_publication', 'elapsed_ms', 'generated_at', 'published_at',
    'served_from', 'snapshot_generated_at',
})


def _semantic(value):
    if isinstance(value, dict):
        return {
            key: _semantic(item) for key, item in sorted(value.items())
            if key not in IGNORED_KEYS
        }
    if isinstance(value, list):
        return [_semantic(item) for item in value]
    return value


def _fingerprint(value):
    body = json.dumps(_semantic(value), sort_keys=True, separators=(',', ':'), default=str)
    return sha256(body.encode('utf-8')).hexdigest()


def _request(client, path, atomic):
    os.environ['SYNC_PIPELINE_ATOMIC_READS_ENABLED'] = 'true' if atomic else 'false'
    started = perf_counter()
    response = client.get(path)
    payload = response.get_json(silent=True)
    return {
        'status_code': response.status_code,
        'elapsed_ms': round((perf_counter() - started) * 1000, 3),
        'payload_bytes': len(response.data),
        'payload_fingerprint': _fingerprint(payload),
        'top_level_keys': sorted(payload) if isinstance(payload, dict) else [],
        'publication_id': (
            ((payload or {}).get('atomic_publication') or {}).get('publication_id')
            if isinstance(payload, dict) else None
        ),
        'reason_code': payload.get('reason_code') if isinstance(payload, dict) else None,
        '_payload': payload,
    }


def _comparison(legacy, atomic):
    if atomic['status_code'] != 200:
        return 'blocker'
    if legacy['status_code'] != 200:
        return 'legacy_unavailable'
    if legacy['payload_fingerprint'] == atomic['payload_fingerprint']:
        return 'exact_parity'
    legacy_keys = set(legacy['top_level_keys']) - IGNORED_KEYS
    atomic_keys = set(atomic['top_level_keys']) - IGNORED_KEYS
    return 'structural_only' if legacy_keys == atomic_keys else 'blocker'


def main():
    from app import create_app
    from models.atomic_publication import (
        AtomicPublication,
        AtomicPublicationArtifact,
        AtomicPublicationCurrent,
    )
    from models.derived_intelligence import DerivedCohortSnapshot
    from models.source_observation import SourceObservation
    from services.atomic_publication_reads import publication_reader_coverage
    from utils.db import db

    os.environ['SYNC_PIPELINE_ATOMIC_READS_ENABLED'] = 'false'
    legacy_app = create_app(os.environ.get('APP_ENV', 'production'))
    os.environ['SYNC_PIPELINE_ATOMIC_READS_ENABLED'] = 'true'
    atomic_app = create_app(os.environ.get('APP_ENV', 'production'))
    # Config is imported once per process. Set the proof apps explicitly so
    # each models the corresponding startup configuration.
    legacy_app.config['SYNC_PIPELINE_ATOMIC_READS_ENABLED'] = False
    atomic_app.config['SYNC_PIPELINE_ATOMIC_READS_ENABLED'] = True
    app = atomic_app
    with app.app_context():
        pointer = db.session.get(AtomicPublicationCurrent, 1)
        if pointer is None:
            raise SystemExit('atomic current publication is unavailable')
        publication = db.session.get(AtomicPublication, pointer.publication_id)
        artifacts = AtomicPublicationArtifact.query.filter_by(
            publication_id=publication.id,
        ).order_by(
            AtomicPublicationArtifact.entity_type,
            AtomicPublicationArtifact.entity_key,
        ).all()
        by_type = {
            kind: [row.entity_key for row in artifacts if row.entity_type == kind]
            for kind in ('team', 'pitcher', 'game')
        }
        affected_teams = [str(value) for value in publication.affected_team_ids_json or ()]
        affected_pitchers = [str(value) for value in publication.affected_pitcher_ids_json or ()]
        affected_games = [str(value) for value in publication.affected_game_ids_json or ()]

        def sample(preferred, available, count):
            return list(dict.fromkeys(preferred + available))[:count]

        team_ids = sample(affected_teams, by_type['team'], 3)
        pitcher_ids = sample(affected_pitchers, by_type['pitcher'], 5)
        game_ids = sample(affected_games, by_type['game'], 2)
        before = {
            'publication_count': AtomicPublication.query.count(),
            'artifact_count': AtomicPublicationArtifact.query.count(),
            'source_observation_count': SourceObservation.query.count(),
            'derived_snapshot_count': DerivedCohortSnapshot.query.count(),
            'pointer_id': pointer.publication_id,
        }
        publication_id = publication.id
        publication_fingerprint = publication.publication_fingerprint
        reader_coverage = publication_reader_coverage(publication.id)

    # Do not retain an application context across requests. Flask stores `g`
    # on that context, so doing so would incorrectly reuse the first legacy
    # request's disabled resolver result for every later atomic request.
    paths = [
        *((f'team:{value}', f'/api/bullpen/teams/{value}/board') for value in team_ids),
        *((f'team_v2:{value}', f'/api/bullpen/teams/{value}/board-v2') for value in team_ids),
        *((f'pitcher:{value}', f'/api/bullpen/fatigue/{value}') for value in pitcher_ids),
        *((f'game:{value}', f'/api/bullpen/matchups/{value}') for value in game_ids),
        ('league', '/api/bullpen/team-states'),
        ('dashboard', '/api/bullpen/dashboard'),
        ('what_changed', f'/api/bullpen/teams/{team_ids[0]}/changes'),
    ]
    # Keep the two modes in separate request phases. Some legacy board helpers
    # retain an application context while assembling their snapshot response;
    # alternating flags request-by-request can therefore leak the legacy
    # resolver result into the following test-client request.
    atomic_results = {
        name: _request(atomic_app.test_client(), path, True) for name, path in paths
    }
    legacy_results = {
        name: _request(legacy_app.test_client(), path, False) for name, path in paths
    }
    cases = []
    atomic_payloads = {}
    for name, path in paths:
        legacy = legacy_results[name]
        atomic = atomic_results[name]
        atomic_payloads[name] = atomic.get('_payload')
        cases.append({
            'case': name,
            'path': path,
            'classification': _comparison(legacy, atomic),
            'legacy': {key: value for key, value in legacy.items() if key != '_payload'},
            'atomic': {key: value for key, value in atomic.items() if key != '_payload'},
        })

    with app.app_context():
        pointer_after = db.session.get(AtomicPublicationCurrent, 1)
        after = {
            'publication_count': AtomicPublication.query.count(),
            'artifact_count': AtomicPublicationArtifact.query.count(),
            'source_observation_count': SourceObservation.query.count(),
            'derived_snapshot_count': DerivedCohortSnapshot.query.count(),
            'pointer_id': pointer_after.publication_id,
        }
        report = {
            'mode': 'read_only',
            'publication_id': publication_id,
            'publication_fingerprint': publication_fingerprint,
            'reader_coverage': reader_coverage,
            'samples': {
                'team_ids': team_ids, 'pitcher_ids': pitcher_ids, 'game_ids': game_ids,
            },
            'cases': cases,
            'league_team_count': len(
                (atomic_payloads.get('league') or {}).get('teams') or ()
            ),
            'authority_rows_before': before,
            'authority_rows_after': after,
            'request_time_authority_writes': any(
                before[key] != after[key]
                for key in ('publication_count', 'artifact_count', 'pointer_id')
            ),
            'concurrent_pipeline_evidence_drift': {
                key: {'before': before[key], 'after': after[key]}
                for key in ('source_observation_count', 'derived_snapshot_count')
                if before[key] != after[key]
            },
            'all_atomic_reads_bound_to_current': all(
                row['atomic']['status_code'] == 200
                and row['atomic']['publication_id'] == publication_id
                for row in cases
            ),
        }
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
