"""The governed width of Tonight snapshot provenance.

Production found this contract by failing on it. The 14:00 UTC morning slate
lane acquired its schedule successfully — ``/schedule`` returned HTTP 200 and
the schedule rows committed — and then died persisting the Tonight snapshot:

    psycopg2.errors.StringDataRightTruncation:
    value too long for type character varying(40)

The composed provenance is ``github_actions_morning:schedule_coherence``, which
is 41 characters. The column held 40. Deterministic, and therefore permanent
until the schema and the composition agreed.

These tests own the agreement. They are deliberately about the *contract* — one
constant, one composer, one failure reason — rather than about the number 128
repeated in several places, because a width asserted independently in three
files is three things that can drift.
"""

import pytest

from models.tonight_intelligence_snapshot import (
    TONIGHT_SNAPSHOT_SOURCE_MAX_LENGTH,
    TonightIntelligenceSnapshot,
)
from services import schedule_tonight_refresh
from services.tonight_intelligence_snapshot import (
    SNAPSHOT_SOURCE_EMPTY_BASE,
    SNAPSHOT_SOURCE_EMPTY_PURPOSE,
    SNAPSHOT_SOURCE_PURPOSE_SEPARATOR,
    SNAPSHOT_SOURCE_TOO_LONG,
    TonightSnapshotSourceError,
    compose_tonight_snapshot_source,
    validate_tonight_snapshot_source,
)


PRODUCTION_BASE = 'github_actions_morning'
PRODUCTION_PURPOSE = 'schedule_coherence'
PRODUCTION_SOURCE = 'github_actions_morning:schedule_coherence'


# ── The value that failed in production ─────────────────────────────────────


def test_the_production_value_is_accepted():
    assert compose_tonight_snapshot_source(
        PRODUCTION_BASE, PRODUCTION_PURPOSE,
    ) == PRODUCTION_SOURCE


def test_the_production_value_is_forty_one_characters():
    """The exact overflow. 41 against a column that held 40."""
    assert len(PRODUCTION_SOURCE) == 41


def test_the_production_value_no_longer_exceeds_the_governed_width():
    assert len(PRODUCTION_SOURCE) <= TONIGHT_SNAPSHOT_SOURCE_MAX_LENGTH


def test_the_lane_default_source_also_composed_to_forty_one():
    """The failure was structural, not caused by one workflow input.

    Shortening ``github_actions_morning`` would have moved the same defect one
    caller over: the service's own default composes to 41 characters too.
    """
    default_source = compose_tonight_snapshot_source(
        'morning_slate_schedule', PRODUCTION_PURPOSE,
    )
    assert len(default_source) == 41


# ── The boundary ────────────────────────────────────────────────────────────


def test_a_value_at_exactly_the_maximum_is_accepted():
    purpose = 'p' * (
        TONIGHT_SNAPSHOT_SOURCE_MAX_LENGTH - len(PRODUCTION_BASE) - 1
    )
    composed = compose_tonight_snapshot_source(PRODUCTION_BASE, purpose)
    assert len(composed) == TONIGHT_SNAPSHOT_SOURCE_MAX_LENGTH


def test_a_value_one_character_over_the_maximum_is_rejected():
    purpose = 'p' * (
        TONIGHT_SNAPSHOT_SOURCE_MAX_LENGTH - len(PRODUCTION_BASE)
    )
    with pytest.raises(TonightSnapshotSourceError) as excinfo:
        compose_tonight_snapshot_source(PRODUCTION_BASE, purpose)
    assert excinfo.value.reason == SNAPSHOT_SOURCE_TOO_LONG


def test_the_rejection_names_the_field_the_lengths_and_the_reason():
    """Enough to diagnose without reading the payload.

    A database truncation error names a column and a width and leaves the lane
    unidentified; this names what could not be stored and by how much.
    """
    purpose = 'p' * TONIGHT_SNAPSHOT_SOURCE_MAX_LENGTH
    with pytest.raises(TonightSnapshotSourceError) as excinfo:
        compose_tonight_snapshot_source(PRODUCTION_BASE, purpose)
    error = excinfo.value
    assert error.field == 'source'
    assert error.reason == SNAPSHOT_SOURCE_TOO_LONG
    assert error.max_length == TONIGHT_SNAPSHOT_SOURCE_MAX_LENGTH
    assert error.observed_length == len(PRODUCTION_BASE) + 1 + len(purpose)
    assert error.observed_length > error.max_length


def test_an_oversized_value_is_never_truncated_into_a_return():
    """Refusing is the point.

    A composer that returned a clipped value would keep the lane green while
    storing provenance that no longer identifies who wrote the snapshot.
    """
    purpose = 'p' * 400
    with pytest.raises(TonightSnapshotSourceError):
        compose_tonight_snapshot_source(PRODUCTION_BASE, purpose)


# ── Composition semantics ───────────────────────────────────────────────────


def test_composition_preserves_the_existing_separator():
    composed = compose_tonight_snapshot_source(PRODUCTION_BASE, PRODUCTION_PURPOSE)
    assert SNAPSHOT_SOURCE_PURPOSE_SEPARATOR == ':'
    assert composed.split(SNAPSHOT_SOURCE_PURPOSE_SEPARATOR) == [
        PRODUCTION_BASE, PRODUCTION_PURPOSE,
    ]


def test_composition_preserves_both_parts_whole():
    composed = compose_tonight_snapshot_source(PRODUCTION_BASE, PRODUCTION_PURPOSE)
    assert composed.startswith(PRODUCTION_BASE)
    assert composed.endswith(PRODUCTION_PURPOSE)


def test_composition_is_deterministic():
    first = compose_tonight_snapshot_source(PRODUCTION_BASE, PRODUCTION_PURPOSE)
    second = compose_tonight_snapshot_source(PRODUCTION_BASE, PRODUCTION_PURPOSE)
    assert first == second


@pytest.mark.parametrize('base', ['', '   ', None, 42])
def test_an_absent_base_source_is_rejected(base):
    with pytest.raises(TonightSnapshotSourceError) as excinfo:
        compose_tonight_snapshot_source(base, PRODUCTION_PURPOSE)
    assert excinfo.value.reason == SNAPSHOT_SOURCE_EMPTY_BASE


@pytest.mark.parametrize('purpose', ['', '   ', None, 42])
def test_an_absent_purpose_is_rejected(purpose):
    with pytest.raises(TonightSnapshotSourceError) as excinfo:
        compose_tonight_snapshot_source(PRODUCTION_BASE, purpose)
    assert excinfo.value.reason == SNAPSHOT_SOURCE_EMPTY_PURPOSE


# ── Already-composed values are held to the same contract ───────────────────


@pytest.mark.parametrize('source', ['on_demand', 'github_actions', 'intraday_repair'])
def test_existing_shorter_source_values_are_unchanged(source):
    assert validate_tonight_snapshot_source(source) == source


def test_a_whole_oversized_source_is_rejected_too():
    with pytest.raises(TonightSnapshotSourceError) as excinfo:
        validate_tonight_snapshot_source(
            'x' * (TONIGHT_SNAPSHOT_SOURCE_MAX_LENGTH + 1)
        )
    assert excinfo.value.reason == SNAPSHOT_SOURCE_TOO_LONG


# ── One contract, not three copies of a number ──────────────────────────────


def test_the_model_column_uses_the_shared_maximum():
    column = TonightIntelligenceSnapshot.__table__.columns['source']
    assert column.type.length == TONIGHT_SNAPSHOT_SOURCE_MAX_LENGTH


def test_the_validator_uses_the_same_maximum_as_the_model():
    column = TonightIntelligenceSnapshot.__table__.columns['source']
    at_limit = 'x' * column.type.length
    assert validate_tonight_snapshot_source(at_limit) == at_limit
    with pytest.raises(TonightSnapshotSourceError):
        validate_tonight_snapshot_source('x' * (column.type.length + 1))


def test_the_refresh_service_composes_through_the_shared_composer():
    """No local interpolation left at the call site.

    The original defect was an f-string in the service that no validator could
    see. This asserts the service reaches the governed composer instead.
    """
    import inspect

    body = inspect.getsource(schedule_tonight_refresh.refresh_schedule_and_tonight)
    assert 'compose_tonight_snapshot_source(' in body
    assert 'schedule_coherence' not in body.replace(
        'TONIGHT_REFRESH_PURPOSE', '',
    )


def test_the_refresh_purpose_still_composes_the_production_value():
    assert compose_tonight_snapshot_source(
        PRODUCTION_BASE, schedule_tonight_refresh.TONIGHT_REFRESH_PURPOSE,
    ) == PRODUCTION_SOURCE
