"""One-generation read boundary for SP-11 atomic publications."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import os
from typing import Callable

from flask import g, has_request_context

from models.atomic_publication import AtomicPublicationArtifact
from services.atomic_publication import (
    get_current_publication,
    read_current_publication_bundle,
    resolve_artifact_snapshot,
)


ATOMIC_READS_FLAG = 'SYNC_PIPELINE_ATOMIC_READS_ENABLED'


class AtomicReadUnavailable(RuntimeError):
    pass


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
        artifact = self.artifact('pitcher', pitcher_id)
        return {'data': artifact['payload'], 'atomic_publication': self.metadata}

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
    'resolve_request_atomic_read_context',
]
