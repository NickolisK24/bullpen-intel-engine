"""Governed V5 observation vocabularies."""

from enum import Enum


class StringEnum(str, Enum):
    """String-valued enum with stable serialization values."""

    def __str__(self):
        return self.value


class ObservationFamily(StringEnum):
    INVENTORY = 'inventory'
    READINESS = 'readiness'
    WORKLOAD_PRESSURE = 'workload_pressure'
    CONSTRAINT = 'constraint'
    FRESHNESS = 'freshness'
    TRUST = 'trust'
    AVAILABILITY_MOVEMENT = 'availability_movement'
    SNAPSHOT_CHANGE = 'snapshot_change'


class ObservationType(StringEnum):
    INVENTORY = 'inventory'
    READINESS = 'readiness'
    WORKLOAD_PRESSURE = 'workload_pressure'
    CONSTRAINT = 'constraint'
    FRESHNESS = 'freshness'
    TRUST = 'trust'
    AVAILABILITY_MOVEMENT = 'availability_movement'
    SNAPSHOT_CHANGE = 'snapshot_change'


class ObservationSeverity(StringEnum):
    INFORMATIONAL = 'informational'
    MONITOR = 'monitor'
    ELEVATED = 'elevated'
    SIGNIFICANT = 'significant'


class ObservationTrustStatus(StringEnum):
    SUPPORTED = 'supported'
    LIMITED = 'limited'
    DATA_LIMITED = 'data_limited'
    STALE = 'stale'
    MISSING = 'missing'
    REFUSED = 'refused'
    FAIL_CLOSED = 'fail_closed'
    UNSUPPORTED = 'unsupported'


ALLOWED_OBSERVATION_FAMILIES = frozenset(family.value for family in ObservationFamily)
ALLOWED_OBSERVATION_TYPES = frozenset(observation.value for observation in ObservationType)
ALLOWED_OBSERVATION_SEVERITIES = frozenset(
    severity.value for severity in ObservationSeverity
)
ALLOWED_OBSERVATION_TRUST_STATUSES = frozenset(
    status.value for status in ObservationTrustStatus
)

# Severity is a descriptive display qualifier only. It is not ranking,
# recommendation strength, pitcher priority, or action priority.
OBSERVATION_SEVERITY_DESCRIPTIONS = {
    ObservationSeverity.INFORMATIONAL.value: (
        'Descriptive state is present and safely supported.'
    ),
    ObservationSeverity.MONITOR.value: (
        'Descriptive state merits visibility because evidence shows a notable '
        'condition or limitation.'
    ),
    ObservationSeverity.ELEVATED.value: (
        'Descriptive state shows increased pressure, contraction, degradation, '
        'or limitation.'
    ),
    ObservationSeverity.SIGNIFICANT.value: (
        'Descriptive state shows a material limitation, fail-closed condition, '
        'or broad degraded support.'
    ),
}
