"""Phase 0E composed-read registry and validation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re

from models.composed_read import ComposedRead
from services.evidence_classification import EvidenceClassification, phase0d_rule_registry


class ComposedReadRegistryError(AssertionError):
    """Raised when a composed-read registration violates the Phase 0E contract."""


class ComposedReadTypeNotRegistered(ComposedReadRegistryError):
    """Raised when a caller tries to build an unregistered read type."""


@dataclass(frozen=True)
class ComponentSpec:
    name: str
    required: bool
    allowed_evidence_types: tuple[str, ...]
    plain_language_definition: str


@dataclass(frozen=True)
class ReadType:
    read_type: str
    read_version: int
    subject_type: str
    plain_language_definition: str
    components: tuple[ComponentSpec, ...]
    classification: EvidenceClassification | None

    @property
    def definition_hash(self) -> str:
        component_payload = '|'.join(
            '|'.join((
                component.name,
                str(component.required),
                ','.join(component.allowed_evidence_types),
                component.plain_language_definition,
            ))
            for component in self.components
        )
        payload = '|'.join((
            self.read_type,
            str(self.read_version),
            self.subject_type,
            self.plain_language_definition,
            component_payload,
            self.classification.value if self.classification else '',
        ))
        return sha256(payload.encode('utf-8')).hexdigest()


class ReadTypeRegistry:
    def __init__(self):
        self._read_types: dict[tuple[str, int], ReadType] = {}

    def register(self, read_type: ReadType) -> ReadType:
        validate_read_type(read_type)
        key = (read_type.read_type, read_type.read_version)
        if key in self._read_types:
            raise ComposedReadRegistryError(
                f'duplicate read type: {read_type.read_type} v{read_type.read_version}'
            )
        self._read_types[key] = read_type
        return read_type

    def get(self, read_type: str, read_version: int | None = None) -> ReadType:
        if read_version is not None:
            try:
                return self._read_types[(read_type, read_version)]
            except KeyError as exc:
                raise ComposedReadTypeNotRegistered(
                    f'composed read type not registered: {read_type} v{read_version}'
                ) from exc
        matches = [
            registered
            for (registered_type, _), registered in self._read_types.items()
            if registered_type == read_type
        ]
        if not matches:
            raise ComposedReadTypeNotRegistered(
                f'composed read type not registered: {read_type}'
            )
        return sorted(matches, key=lambda item: item.read_version)[-1]

    def all_read_types(self) -> tuple[ReadType, ...]:
        return tuple(
            self._read_types[key]
            for key in sorted(self._read_types, key=lambda item: (item[0], item[1]))
        )


read_type_registry = ReadTypeRegistry()

ALLOWED_READ_TYPE_CLASSIFICATIONS = frozenset({
    EvidenceClassification.PERMANENTLY_INTERNAL,
    EvidenceClassification.INTERNAL_ONLY_FOR_NOW,
})

LOCKED_BAND_EVIDENCE_TYPES = frozenset({
    'appearance_entry_band',
    'pitcher_entry_band_distribution',
    'team_active_reliever_count',
})

FORBIDDEN_READ_NAME_TOKENS = frozenset({
    'available',
    'availability',
    'bet',
    'cleared',
    'closer',
    'committee',
    'confidence',
    'deep',
    'depleted',
    'dominant',
    'expect',
    'fade',
    'fireman',
    'fresh',
    'full_strength',
    'gassed',
    'grade',
    'healthy',
    'headline',
    'high_leverage',
    'injury_free',
    'label',
    'leaned_on',
    'leverage',
    'likely',
    'lock',
    'long_man',
    'manager_choice',
    'nobody_is_hurt',
    'odds',
    'overworked',
    'pecking_order',
    'pressure',
    'prefers',
    'projects',
    'rank',
    'read_label',
    'ready',
    'reliable',
    'score',
    'setup',
    'shaky',
    'short_handed',
    'state_label',
    'stopper',
    'stretched',
    'stress',
    'structure',
    'thin',
    'tired',
    'trustworthy',
    'trusts',
    'unavailable',
    'vulnerable',
    'will',
    'workhorse',
})


def validate_read_type(read_type: ReadType) -> bool:
    if not read_type.read_type:
        raise ComposedReadRegistryError('read type requires read_type')
    if not isinstance(read_type.read_version, int) or read_type.read_version <= 0:
        raise ComposedReadRegistryError('read type requires positive integer read_version')
    if read_type.subject_type not in (
        ComposedRead.SUBJECT_PITCHER_DAY,
        ComposedRead.SUBJECT_TEAM_DAY,
    ):
        raise ComposedReadRegistryError(f'unsupported subject_type: {read_type.subject_type}')
    _assert_name_allowed(read_type.read_type)
    definition = (read_type.plain_language_definition or '').strip()
    if not definition:
        raise ComposedReadRegistryError('read type requires plain-language definition')
    lower_definition = definition.lower()
    if (
        'bundles' not in lower_definition
        or (
            'does not conclude' not in lower_definition
            and 'concludes nothing' not in lower_definition
        )
    ):
        raise ComposedReadRegistryError(
            'read type definition must state what it bundles and what it does not conclude'
        )
    if read_type.classification is None:
        raise ComposedReadRegistryError(f'{read_type.read_type} requires classification')
    if read_type.classification not in ALLOWED_READ_TYPE_CLASSIFICATIONS:
        raise ComposedReadRegistryError(
            f'{read_type.read_type} carries public-facing or unsupported classification'
        )
    if not read_type.components:
        raise ComposedReadRegistryError('read type requires components')

    component_names = set()
    evidence_types = _phase0d_evidence_types()
    for component in read_type.components:
        if component.name in component_names:
            raise ComposedReadRegistryError(f'duplicate component: {component.name}')
        component_names.add(component.name)
        _validate_component(component, evidence_types)
    return True


def validate_read_type_registry(registry: ReadTypeRegistry | None = None) -> dict:
    registry = registry or read_type_registry
    rows = registry.all_read_types()
    for row in rows:
        validate_read_type(row)
    return {
        'read_type_count': len(rows),
        'classified_count': len([row for row in rows if row.classification is not None]),
    }


def _validate_component(component: ComponentSpec, evidence_types: set[str]) -> None:
    if not component.name:
        raise ComposedReadRegistryError('component requires name')
    _assert_name_allowed(component.name)
    if not (component.plain_language_definition or '').strip():
        raise ComposedReadRegistryError(f'{component.name} requires plain-language definition')
    if not component.allowed_evidence_types:
        raise ComposedReadRegistryError(f'{component.name} requires allowed evidence types')
    locked = sorted(set(component.allowed_evidence_types) & LOCKED_BAND_EVIDENCE_TYPES)
    if locked:
        raise ComposedReadRegistryError(
            f'{component.name} cannot consume locked band evidence: {locked}'
        )
    unknown = sorted(set(component.allowed_evidence_types) - evidence_types)
    if unknown:
        raise ComposedReadRegistryError(
            f'{component.name} names unknown evidence types: {unknown}'
        )


def _assert_name_allowed(value: str) -> None:
    normalized = re.sub(r'[^a-z0-9]+', '_', value.lower()).strip('_')
    parts = set(filter(None, normalized.split('_')))
    compounds = {normalized}
    tokens = parts | compounds
    for forbidden in FORBIDDEN_READ_NAME_TOKENS:
        if forbidden in tokens or forbidden in normalized:
            raise ComposedReadRegistryError(f'forbidden read registry name: {value}')


def _phase0d_evidence_types() -> set[str]:
    registry, _ = phase0d_rule_registry()
    return {rule.evidence_type for rule in registry.all_rules()}
