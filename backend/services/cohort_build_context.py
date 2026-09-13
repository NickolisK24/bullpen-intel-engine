"""Captured SP-10 read-model source selection.

This is a source-selection context, not a closed-input manifest. Compatibility
rows and readiness dependencies still require their own captured authorities.
Do not use this object to certify legacy manifests as input-closed.
"""

from dataclasses import dataclass
from datetime import date, datetime
import json
import hashlib
from types import SimpleNamespace


SNAPSHOT_FIELDS = (
    'id', 'snapshot_type', 'sync_run_id', 'status', 'is_published',
    'published_at', 'payload_version', 'data_through',
    'availability_reference_date', 'snapshot_generated_at', 'source', 'error_message',
)
DATE_FIELDS = frozenset(('data_through', 'availability_reference_date'))
DATETIME_FIELDS = frozenset(('published_at', 'snapshot_generated_at'))
BUILD_CONTEXT_VERSION = 'cohort-build-context-v1'


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      allow_nan=False, default=_encode_date)


def _encode_date(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f'Unsupported captured input: {type(value).__name__}')


@dataclass(frozen=True)
class CohortBuildContext:
    """Immutable source selection shared by the CU-06 artifact family.

    Raw JSON stays in memory only. Each consumer receives a private copy so the
    existing shadow overlay cannot change the captured source. A captured miss
    remains a miss; it never falls through to another latest lookup.
    """

    represented_date: date
    requested_team_ids: tuple[int, ...]
    requested_pitcher_ids: tuple[int, ...]
    requested_game_ids: tuple[int, ...]
    publication_artifact_baseline: bool
    predecessor_cohort_id: int | None
    source_snapshot_json: str
    baseline_publication_id: int | None = None
    comparisons_json: str = '{}'
    read_model_selectors: bool = True

    def manifest_value(self):
        """Auditable selector identity; deliberately not a closed-input claim."""
        snapshot = json.loads(self.source_snapshot_json)
        comparisons = json.loads(self.comparisons_json)
        return {
            'schema_version': BUILD_CONTEXT_VERSION,
            'scope': {
                'represented_date': self.represented_date.isoformat(),
                'team_ids': list(self.requested_team_ids),
                'pitcher_ids': list(self.requested_pitcher_ids),
                'game_ids': list(self.requested_game_ids),
            },
            'selectors': {
                'read_model_selectors': self.read_model_selectors,
                'dashboard_snapshot_id': snapshot['id'] if snapshot else None,
                'publication_artifact_baseline': self.publication_artifact_baseline,
                'baseline_publication_id': self.baseline_publication_id,
                'predecessor_cohort_id': self.predecessor_cohort_id,
                'legacy_comparisons': {
                    key: value.get('comparison') for key, value in comparisons.items()
                },
            },
            'generations': {
                'dashboard_source': hashlib.sha256(
                    self.source_snapshot_json.encode('utf-8'),
                ).hexdigest(),
                'legacy_comparisons': hashlib.sha256(
                    self.comparisons_json.encode('utf-8'),
                ).hexdigest(),
            },
        }

    @property
    def fingerprint(self):
        return hashlib.sha256(_json(self.manifest_value()).encode('utf-8')).hexdigest()

    def manifest_entry(self, authority_class):
        return {
            'input_type': 'build_context', 'input_key': 'cohort',
            'input_version': BUILD_CONTEXT_VERSION,
            'input_fingerprint': self.fingerprint,
            'authority_class': authority_class, 'source_observation_id': None,
            'context': self.manifest_value(),
        }

    @classmethod
    def capture(cls, plan, *, source_snapshot, publication_artifact_baseline,
                predecessor_cohort_id, baseline_publication_id=None, comparisons=None,
                read_model_selectors=True):
        source = None
        if source_snapshot is not None:
            source = {
                field: getattr(source_snapshot, field, None)
                for field in SNAPSHOT_FIELDS
            }
            source['payload'] = getattr(source_snapshot, 'payload', None)
        return cls(
            represented_date=plan.baseball_date,
            requested_team_ids=tuple(sorted(set(plan.affected_team_ids_json or ()))),
            requested_pitcher_ids=tuple(sorted(set(plan.affected_pitcher_ids_json or ()))),
            # CU-06 currently uses the first game; preserve that governed input
            # order rather than silently changing which game is represented.
            requested_game_ids=tuple(plan.affected_game_ids_json or ()),
            publication_artifact_baseline=bool(publication_artifact_baseline),
            predecessor_cohort_id=predecessor_cohort_id,
            source_snapshot_json=_json(source),
            baseline_publication_id=baseline_publication_id,
            comparisons_json=_json(comparisons or {}),
            read_model_selectors=bool(read_model_selectors),
        )

    def comparison_for(self, team_id):
        comparisons = json.loads(self.comparisons_json)
        # An uncaptured team must never fall back to a newer legacy comparison.
        return comparisons[str(team_id)]

    def source_snapshot(self):
        source = json.loads(self.source_snapshot_json)
        if source is None:
            return None
        for key in DATE_FIELDS:
            if source[key] is not None:
                source[key] = date.fromisoformat(source[key])
        for key in DATETIME_FIELDS:
            if source[key] is not None:
                source[key] = datetime.fromisoformat(source[key])
        return SimpleNamespace(**source)

    def matches_source(self, source_snapshot):
        """Compare selected source meaning without mutating the captured copy."""
        candidate = type(self).capture(
            SimpleNamespace(
                baseball_date=self.represented_date,
                affected_team_ids_json=self.requested_team_ids,
                affected_pitcher_ids_json=self.requested_pitcher_ids,
                affected_game_ids_json=self.requested_game_ids,
            ),
            source_snapshot=source_snapshot,
            publication_artifact_baseline=self.publication_artifact_baseline,
            predecessor_cohort_id=self.predecessor_cohort_id,
            baseline_publication_id=self.baseline_publication_id,
        )
        return candidate.source_snapshot_json == self.source_snapshot_json
