"""Daily publication proof: the candidate's own reference dates, at any data age.

Production defect (daily sync run 44155845626, SyncRun 98033, 2026-11-17)::

    team_state_publication_proof_invariant_failed:reference_date_alignment

``require_transactional_publication_proof`` asks the production readiness
resolver for every club's read of the candidate snapshot and then checks that
each read used the candidate's governed pair of reference dates: membership on
the candidate's ``data_through`` and availability on the candidate's own
schedule-aware ``availability_reference_date`` (D-056).

``resolve_readiness_reference_dates`` only honoured the candidate's dates when
``serving_snapshot_freshness_authority`` returned an authority. That function is
a *currency* verdict: besides the canonical trust verdict it refuses any
snapshot whose ``data_through`` is more than ``ACTIVE_WINDOW_DAYS`` (14) before
the wall-clock product date. With no games after the 2026 World Series the
candidate's ``data_through`` stayed 2026-10-28, so from 2026-11-12 (data age 15)
the candidate lost its own dates, both dates fell back to the live global
reference, membership no longer equalled ``data_through``, and the proof refused
every daily publication. Snapshot 5827 (data through 2026-10-28, availability
2026-10-30) was the last one to publish, on 2026-11-11, the final day the window
admitted 2026-10-28.

These tests run the real trust verdict (``snapshot_unavailable_reason``), the
real freshness authority and the real date authorities against a pinned product
date. Only the database-backed readiness inputs are stubbed.
"""

from datetime import date, datetime
from types import SimpleNamespace

import pytest

from services import team_state_vnext_production_proof as proof_module
from services.dashboard_snapshot import (
    DASHBOARD_PAYLOAD_VERSION,
    SNAPSHOT_STATUS_READY,
    SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
)
from services.mlb_club_directory import MLB_TEAM_IDS
from tests.test_team_state_vnext_production_proof import _result


SNAPSHOT_ID = 5839
SYNC_RUN_ID = 98033


def _candidate(data_through, availability_reference_date, *, is_published=True,
               status=SNAPSHOT_STATUS_READY, payload_availability=None):
    """A daily candidate exactly as ``publish_dashboard_snapshot`` hands it to the proof.

    The publication transaction marks the candidate ready and published before the
    proof runs, so the canonical trust verdict sees it as the serving snapshot.
    """
    payload_availability = (
        availability_reference_date if payload_availability is None else payload_availability
    )
    return SimpleNamespace(
        id=SNAPSHOT_ID,
        sync_run_id=SYNC_RUN_ID,
        snapshot_type=SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
        payload_version=DASHBOARD_PAYLOAD_VERSION,
        subject_type=None,
        status=status,
        error_message=None,
        is_published=is_published,
        published_at=datetime(2026, 11, 17, 19, 18, 0),
        source='sync_completion',
        data_through=data_through,
        availability_reference_date=availability_reference_date,
        payload={
            'freshness': {
                'data_through': data_through.isoformat(),
                'availability_reference_date': payload_availability.isoformat(),
                'slate_coverage': {
                    'slate_date': data_through.isoformat(),
                    'validations_passed': True,
                    'complete_enough_to_publish': True,
                },
            },
            'what_changed_since_yesterday': {'state': 'unavailable'},
        },
    )


@pytest.fixture
def product_day(monkeypatch):
    """Pin the wall-clock product date seen by every date and trust authority."""
    import api.team_operations as team_ops
    import services.dashboard_snapshot as dashboard_snapshot
    import services.readiness_snapshot_freshness as freshness_mod

    def _pin(today):
        monkeypatch.setattr(dashboard_snapshot, 'product_current_date', lambda: today)
        monkeypatch.setattr(freshness_mod, 'product_current_date', lambda: today)
        monkeypatch.setattr(team_ops, '_sync_status_payload', lambda: {'status': 'success'})
        # The live global reference an unanchored read falls back to. It is the
        # product day here so a fallback can never coincide with the slate.
        monkeypatch.setattr(team_ops, '_availability_reference_date', lambda sync_status: today)

    return _pin


@pytest.fixture
def readiness_pipeline(monkeypatch):
    """Stub only the DB-backed readiness inputs; record the dates each read used."""
    import api.team_operations as team_ops
    import services.availability_snapshot as availability_snapshot
    import services.share_artifact_generation as generation
    import team_operations as team_operations_pkg

    seen = []
    record = {'pitcher_id': 1, 'pitcher': SimpleNamespace(id=1), 'availability': {}}
    current = {}

    def _classify(rows, reference_date=None, mode=None):
        current['availability'] = reference_date
        return [record]

    def _population(records, *, team_id, reference_date):
        current['membership'] = reference_date
        return tuple(records), (frozenset({1}), True)

    def _assemble(**kwargs):
        seen.append(dict(current))
        return dict(_result(current.get('team_id', 0)).readiness)

    monkeypatch.setattr(availability_snapshot, 'latest_fatigue_rows', lambda **kw: [object()])
    monkeypatch.setattr(availability_snapshot, 'classify_latest_fatigue_rows', _classify)
    monkeypatch.setattr(team_ops, 'resolve_readiness_population', _population)
    monkeypatch.setattr(
        team_ops, '_team_operations_trust_metadata',
        lambda records, **kw: {'confidence': 'high', 'data_state': 'fresh'},
    )
    monkeypatch.setattr(
        team_ops, '_filter_records_by_team_abbreviation', lambda records, **kw: tuple(records),
    )
    monkeypatch.setattr(team_ops, '_generated_at', lambda rows: '2026-11-17T19:18:00+00:00')
    monkeypatch.setattr(team_ops, '_readiness_record', lambda record: dict(record))
    monkeypatch.setattr(team_ops, '_team_payload_from_records', lambda records, **kw: {})
    monkeypatch.setattr(
        team_ops, '_team_operations_freshness_metadata',
        lambda records, *, sync_status, generated_at: {'freshness_state': 'current'},
    )
    monkeypatch.setattr(team_operations_pkg, 'assemble_bullpen_readiness', _assemble)
    # Competition status reads stored schedule rows; it is not part of this defect.
    monkeypatch.setattr(
        generation, 'attach_season_context', lambda readiness, team_id, reference_date: readiness,
    )
    monkeypatch.setattr(
        proof_module, 'historical_team_state_inventory',
        lambda *_a, **_k: {'entries': [], 'count': 0, 'digest': proof_module._digest([])},
    )
    monkeypatch.setattr(proof_module, '_store_durable_proof', lambda *_a, **_k: None)
    return seen


def _prove(candidate):
    """Run the real transactional proof with the real default readiness resolver."""
    return proof_module.require_transactional_publication_proof(
        candidate, team_ids=MLB_TEAM_IDS,
    )


# ---------------------------------------------------------------------------
# 1. The transactional proof, end to end through the production resolver
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ('data_through', 'availability', 'today'),
    [
        pytest.param(
            date(2026, 8, 17), date(2026, 8, 18), date(2026, 8, 18),
            id='normal_game_day',
        ),
        pytest.param(
            # Schedule-aware: the candidate's own date sits past slate + 1 across a
            # league-wide off-day and must be honoured, not recomputed as slate + 1.
            date(2026, 9, 27), date(2026, 9, 29), date(2026, 9, 29),
            id='no_game_day',
        ),
        pytest.param(
            # Snapshot 5827's dates on the day it published (data age 14).
            date(2026, 10, 28), date(2026, 10, 30), date(2026, 11, 11),
            id='last_day_inside_window',
        ),
        pytest.param(
            # The first failing daily run (data age 15).
            date(2026, 10, 28), date(2026, 10, 30), date(2026, 11, 12),
            id='multi_day_gap_first_failing_day',
        ),
        pytest.param(
            # Production run 44155845626 / SyncRun 98033 (data age 20).
            date(2026, 10, 28), date(2026, 10, 30), date(2026, 11, 17),
            id='multi_day_gap_production_run_98033',
        ),
    ],
)
def test_candidate_reads_use_the_candidates_governed_dates(
    product_day, readiness_pipeline, data_through, availability, today,
):
    product_day(today)

    proof = _prove(_candidate(data_through, availability))

    assert proof['invariants']['reference_date_alignment']['result'] == proof_module.RESULT_PASS
    assert len(readiness_pipeline) == 30
    assert all(
        read == {'membership': data_through, 'availability': availability}
        for read in readiness_pipeline
    )
    assert {team['membership_reference_date'] for team in proof['teams']} == {
        data_through.isoformat()
    }
    assert {team['availability_reference_date'] for team in proof['teams']} == {
        availability.isoformat()
    }


def test_proof_still_rejects_a_candidate_whose_dates_contradict_its_payload(
    product_day, readiness_pipeline,
):
    """Genuinely inconsistent dates fail closed exactly as before."""
    product_day(date(2026, 11, 17))
    candidate = _candidate(
        date(2026, 10, 28), date(2026, 10, 30), payload_availability=date(2026, 10, 29),
    )

    with pytest.raises(ValueError, match='reference_date_alignment'):
        _prove(candidate)


def test_proof_still_rejects_a_candidate_past_the_unavailable_boundary(
    product_day, readiness_pipeline,
):
    """The canonical 30-day freshness fail-closed boundary is unchanged.

    At data age 30 the canonical trust verdict itself refuses the snapshot
    (``dashboard_snapshot_freshness_fail_closed``), so the candidate has no date
    authority and the proof keeps refusing publication.
    """
    product_day(date(2026, 11, 27))

    with pytest.raises(ValueError, match='reference_date_alignment'):
        _prove(_candidate(date(2026, 10, 28), date(2026, 10, 30)))


# ---------------------------------------------------------------------------
# 2. The resolver's authority boundary
# ---------------------------------------------------------------------------


OFFSEASON_SLATE = date(2026, 10, 28)
OFFSEASON_AVAILABILITY = date(2026, 10, 30)
OFFSEASON_TODAY = date(2026, 11, 17)


def test_publication_candidate_keeps_its_own_dates_past_the_freshness_window(product_day):
    from services.share_artifact_generation import resolve_readiness_reference_dates

    product_day(OFFSEASON_TODAY)
    dates = resolve_readiness_reference_dates(
        _candidate(OFFSEASON_SLATE, OFFSEASON_AVAILABILITY), publication_candidate=True,
    )
    assert dates == (OFFSEASON_SLATE, OFFSEASON_AVAILABILITY)


def test_an_ordinary_read_of_a_stale_snapshot_keeps_the_live_dates(product_day):
    """Only the transactional proof gains the distinction; public reads are unchanged."""
    from services.share_artifact_generation import resolve_readiness_reference_dates

    product_day(OFFSEASON_TODAY)
    dates = resolve_readiness_reference_dates(
        _candidate(OFFSEASON_SLATE, OFFSEASON_AVAILABILITY),
    )
    assert dates == (OFFSEASON_TODAY, OFFSEASON_TODAY)


@pytest.mark.parametrize(
    'overrides',
    [
        pytest.param({'is_published': False}, id='unpublished'),
        pytest.param({'status': 'building'}, id='not_ready'),
        pytest.param({'payload_availability': date(2026, 10, 29)}, id='payload_contradiction'),
    ],
)
def test_an_untrusted_snapshot_gains_no_authority_even_as_a_candidate(product_day, overrides):
    """The candidate distinction never makes an arbitrary unpublished snapshot trusted."""
    from services.share_artifact_generation import resolve_readiness_reference_dates

    product_day(OFFSEASON_TODAY)
    dates = resolve_readiness_reference_dates(
        _candidate(OFFSEASON_SLATE, OFFSEASON_AVAILABILITY, **overrides),
        publication_candidate=True,
    )
    assert dates == (OFFSEASON_TODAY, OFFSEASON_TODAY)


def test_a_candidate_does_not_anchor_its_freshness_verdict(
    product_day, readiness_pipeline, monkeypatch,
):
    """Only the dates follow the candidate; a stale candidate is still read as stale.

    The freshness anchor stays owned by ``serving_snapshot_freshness_authority`` and
    its 14-day window, so freshness and eligibility gates are unchanged.
    """
    import services.readiness_snapshot_freshness as freshness_mod
    from services.share_artifact_generation import resolve_team_readiness_payload

    product_day(OFFSEASON_TODAY)
    candidate = _candidate(OFFSEASON_SLATE, OFFSEASON_AVAILABILITY)
    assert freshness_mod.serving_snapshot_freshness_authority(candidate) is None

    anchored = []
    monkeypatch.setattr(
        freshness_mod, 'anchor_sync_status_to_serving_snapshot',
        lambda sync_status, authority: anchored.append(authority) or sync_status,
    )
    dates = {}
    resolve_team_readiness_payload(
        147, source_snapshot=candidate, reference_dates_out=dates,
        publication_candidate=True,
    )
    assert dates == {
        'membership_reference_date': OFFSEASON_SLATE,
        'availability_reference_date': OFFSEASON_AVAILABILITY,
    }
    assert anchored == []
