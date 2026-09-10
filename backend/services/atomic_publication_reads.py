"""One-generation read boundary for SP-11 atomic publications."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import os

from services.atomic_publication import read_current_publication_bundle


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

    def __post_init__(self):
        publication_id = self.bundle.get('publication_id')
        artifacts = self.bundle.get('artifacts')
        if publication_id is None or not isinstance(artifacts, list):
            raise AtomicReadUnavailable('atomic_publication_bundle_invalid')
        if any(row.get('publication_id') != publication_id for row in artifacts):
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
        artifact = self.artifact('game', game_pk)
        return {'data': artifact['payload'], 'atomic_publication': self.metadata}

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


__all__ = [
    'ATOMIC_READS_FLAG', 'AtomicPublicationReadContext', 'AtomicReadUnavailable',
    'atomic_reads_enabled', 'resolve_atomic_read_context',
]
