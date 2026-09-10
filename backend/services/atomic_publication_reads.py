"""One-generation read boundary for SP-11 atomic publications."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
import os
from typing import Callable

from flask import g, has_request_context

from models.atomic_publication import AtomicPublication, AtomicPublicationArtifact
from models.derived_intelligence import DerivedCohortSnapshot
from services.atomic_publication import (
    get_current_publication,
    read_current_publication_bundle,
    resolve_artifact_snapshot,
)
from services.mlb_club_directory import MLB_TEAM_IDS
from utils.db import db


ATOMIC_READS_FLAG = 'SYNC_PIPELINE_ATOMIC_READS_ENABLED'


class AtomicReadUnavailable(RuntimeError):
    pass


def publication_reader_coverage(publication_id):
    publication = db.session.get(AtomicPublication, int(publication_id))
    if publication is None:
        return {
            'complete': False,
            'publication_id': int(publication_id),
            'reason': 'publication_missing',
        }
    return _cached_publication_reader_coverage(
        str(db.engine.url), publication.id, publication.publication_fingerprint,
    )


@lru_cache(maxsize=32)
def _cached_publication_reader_coverage(_database_identity, publication_id, _fingerprint):
    """Validate that one generation can serve every CR-04 reader family."""
    artifacts = AtomicPublicationArtifact.query.filter_by(
        publication_id=int(publication_id),
    ).all()
    direct_snapshot_ids = {
        artifact.source_snapshot_id for artifact in artifacts
        if artifact.source_snapshot_id is not None
    }
    direct_snapshots = {
        snapshot.id: snapshot
        for snapshot in DerivedCohortSnapshot.query.filter(
            DerivedCohortSnapshot.id.in_(direct_snapshot_ids),
        ).all()
    } if direct_snapshot_ids else {}
    present = {
        'team_board': set(),
        'team_board_v2': set(),
        'league_row': set(),
        'what_changed': set(),
        'pitcher_current': set(),
        'game_matchup': set(),
    }
    artifact_counts = {'team': 0, 'pitcher': 0, 'game': 0}
    for artifact in artifacts:
        if artifact.entity_type not in artifact_counts:
            continue
        artifact_counts[artifact.entity_type] += 1
        snapshot = direct_snapshots.get(artifact.source_snapshot_id)
        if snapshot is None:
            snapshot = resolve_artifact_snapshot(artifact)
        payload = snapshot.payload_json if isinstance(snapshot.payload_json, dict) else {}
        read_models = payload.get('read_models')
        read_models = read_models if isinstance(read_models, dict) else {}
        key = str(artifact.entity_key)
        if artifact.entity_type == 'team':
            if isinstance(read_models.get('team_board'), dict):
                present['team_board'].add(key)
            if isinstance(read_models.get('team_board_v2'), dict):
                present['team_board_v2'].add(key)
            if isinstance(read_models.get('league_row'), dict):
                present['league_row'].add(key)
            if isinstance(payload.get('what_changed'), dict):
                present['what_changed'].add(key)
        elif artifact.entity_type == 'pitcher':
            if isinstance(read_models.get('pitcher_current'), dict):
                present['pitcher_current'].add(key)
        elif artifact.entity_type == 'game':
            if isinstance(read_models.get('matchup'), dict):
                present['game_matchup'].add(key)

    expected_teams = {str(value) for value in MLB_TEAM_IDS}
    missing = {
        family: sorted(expected_teams - keys, key=int)
        for family, keys in present.items()
        if family in {'team_board', 'team_board_v2', 'league_row', 'what_changed'}
    }
    complete = (
        all(not values for values in missing.values())
        and artifact_counts['pitcher'] > 0
        and len(present['pitcher_current']) == artifact_counts['pitcher']
        and artifact_counts['game'] > 0
        and len(present['game_matchup']) == artifact_counts['game']
    )
    return {
        'complete': complete,
        'publication_id': int(publication_id),
        'artifact_counts': artifact_counts,
        'ready_counts': {key: len(values) for key, values in present.items()},
        'missing_team_ids': missing,
    }


def atomic_reads_enabled(env=None):
    values = os.environ if env is None else env
    return str(values.get(ATOMIC_READS_FLAG, 'false')).strip().lower() in {
        '1', 'true', 'yes', 'on',
    }


@dataclass(frozen=True)
class AtomicPublicationReadContext:
    """An immutable request-local view of exactly one publication bundle."""

    bundle: dict
    artifact_reader: Callable | None = None

    def __post_init__(self):
        publication_id = self.bundle.get('publication_id')
        artifacts = self.bundle.get('artifacts')
        if publication_id is None or (
            not isinstance(artifacts, list) and self.artifact_reader is None
        ):
            raise AtomicReadUnavailable('atomic_publication_bundle_invalid')
        if isinstance(artifacts, list) and any(
            row.get('publication_id') != publication_id for row in artifacts
        ):
            raise AtomicReadUnavailable('atomic_publication_generation_mixed')

    @property
    def publication_id(self):
        return self.bundle['publication_id']

    @property
    def metadata(self):
        return {
            'publication_id': self.publication_id,
            'publication_fingerprint': self.bundle.get('publication_fingerprint'),
            'published_at': self.bundle.get('published_at'),
            'source_data_through': self.bundle.get('source_data_through'),
            'authority_class': self.bundle.get('authority_class'),
            'method_versions': deepcopy(self.bundle.get('method_versions') or {}),
        }

    def artifact(self, entity_type, entity_key, *, artifact_type=None):
        if self.artifact_reader is not None:
            row = self.artifact_reader(
                self.publication_id, str(entity_type), str(entity_key), artifact_type,
            )
            if row is None or row.get('publication_id') != self.publication_id:
                raise AtomicReadUnavailable(
                    f'atomic_artifact_unavailable:{entity_type}:{entity_key}'
                )
            return deepcopy(row)
        matches = [
            row for row in self.bundle['artifacts']
            if row.get('entity_type') == str(entity_type)
            and row.get('entity_key') == str(entity_key)
            and (artifact_type is None or row.get('artifact_type') == artifact_type)
        ]
        if len(matches) != 1:
            raise AtomicReadUnavailable(
                f'atomic_artifact_unavailable:{entity_type}:{entity_key}'
            )
        return deepcopy(matches[0])

    def team_board(self, team_id):
        payload = self.artifact('team', team_id).get('payload') or {}
        board = (payload.get('read_models') or {}).get('team_board')
        if not isinstance(board, dict):
            raise AtomicReadUnavailable(f'atomic_team_board_unavailable:{team_id}')
        return {**deepcopy(board), 'atomic_publication': self.metadata}

    def pitcher(self, pitcher_id):
        payload = self.artifact('pitcher', pitcher_id).get('payload') or {}
        current = (payload.get('read_models') or {}).get('pitcher_current')
        if not isinstance(current, dict):
            raise AtomicReadUnavailable(
                f'atomic_pitcher_current_unavailable:{pitcher_id}'
            )
        return {**deepcopy(current), 'atomic_publication': self.metadata}

    def game(self, game_pk):
        payload = self.artifact('game', game_pk).get('payload') or {}
        matchup = (payload.get('read_models') or {}).get('matchup')
        if not isinstance(matchup, dict):
            raise AtomicReadUnavailable(f'atomic_matchup_unavailable:{game_pk}')
        return {**deepcopy(matchup), 'atomic_publication': self.metadata}

    def what_changed(self, team_id):
        payload = self.artifact('team', team_id).get('payload') or {}
        changes = payload.get('what_changed')
        if not isinstance(changes, dict):
            raise AtomicReadUnavailable(f'atomic_what_changed_unavailable:{team_id}')
        return {**deepcopy(changes), 'atomic_publication': self.metadata}

    def league(self, expected_team_ids):
        expected = tuple(sorted({int(value) for value in expected_team_ids}))
        rows = []
        for team_id in expected:
            payload = self.artifact('team', team_id).get('payload') or {}
            row = (payload.get('read_models') or {}).get('league_row')
            if not isinstance(row, dict):
                raise AtomicReadUnavailable(f'atomic_league_row_unavailable:{team_id}')
            rows.append(deepcopy(row))
        return {'teams': rows, 'atomic_publication': self.metadata}


def resolve_atomic_read_context(*, env=None, bundle_reader=read_current_publication_bundle):
    """Resolve current once; callers must reuse the returned request context."""
    if not atomic_reads_enabled(env):
        return None
    bundle = bundle_reader()
    if bundle is None:
        raise AtomicReadUnavailable('atomic_current_publication_unavailable')
    return AtomicPublicationReadContext(deepcopy(bundle))


def _database_artifact_reader(publication_id, entity_type, entity_key, artifact_type):
    query = AtomicPublicationArtifact.query.filter_by(
        publication_id=int(publication_id),
        entity_type=str(entity_type),
        entity_key=str(entity_key),
    )
    if artifact_type is not None:
        query = query.filter_by(artifact_type=str(artifact_type))
    rows = query.limit(2).all()
    if len(rows) != 1:
        return None
    artifact = rows[0]
    snapshot = resolve_artifact_snapshot(artifact)
    return {
        'publication_id': int(publication_id),
        'artifact_type': artifact.artifact_type,
        'entity_type': artifact.entity_type,
        'entity_key': artifact.entity_key,
        'payload_fingerprint': artifact.payload_fingerprint,
        'payload': snapshot.payload_json,
    }


def resolve_database_atomic_read_context(*, env=None):
    """Freeze the current publication once without loading unrelated artifacts."""
    if not atomic_reads_enabled(env):
        return None
    publication = get_current_publication()
    if publication is None:
        raise AtomicReadUnavailable('atomic_current_publication_unavailable')
    coverage = publication_reader_coverage(publication.id)
    if not coverage['complete']:
        raise AtomicReadUnavailable('atomic_publication_reader_coverage_incomplete')
    bundle = {
        'publication_id': publication.id,
        'publication_fingerprint': publication.publication_fingerprint,
        'published_at': (
            publication.published_at.isoformat() if publication.published_at else None
        ),
        'source_data_through': publication.source_data_through.isoformat(),
        'authority_class': publication.authority_class,
        'method_versions': publication.method_versions_json,
        'artifacts': None,
    }
    return AtomicPublicationReadContext(
        bundle, artifact_reader=_database_artifact_reader,
    )


def resolve_request_atomic_read_context(
    *, env=None, context_reader=resolve_database_atomic_read_context,
):
    """Resolve at most once for the active Flask request and freeze the bundle."""
    if not has_request_context():
        raise AtomicReadUnavailable('atomic_request_context_unavailable')
    cache_key = '_baseballos_atomic_publication_context'
    if cache_key not in g:
        setattr(g, cache_key, context_reader(env=env))
    return getattr(g, cache_key)


__all__ = [
    'ATOMIC_READS_FLAG', 'AtomicPublicationReadContext', 'AtomicReadUnavailable',
    'atomic_reads_enabled', 'resolve_atomic_read_context',
    'resolve_database_atomic_read_context',
    'resolve_request_atomic_read_context', 'publication_reader_coverage',
]
