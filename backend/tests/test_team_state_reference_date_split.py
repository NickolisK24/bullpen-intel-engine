"""Team State reference-date split — membership on the slate, availability next day.

The published Team State path used to resolve the canonical availability reference
date (``data_through + 1``) and then overwrite that same local with the slate day
while anchoring the roster authority, so the slate day reached
``classify_latest_fatigue_rows``. Published Team State therefore classified arms one
day earlier than the Team Board, the readiness route, and the calibration shadow —
all three of which read at ``data_through + 1`` — and the artifact's own freshness
metadata disagreed with the date its arms were classified at.

These tests pin the two dates as independent values at the layer that decides them,
and prove the correction end to end on a seeded bullpen. The classifier itself is
unchanged and is pinned separately by ``test_team_state_vnext_contract_a.py``; a
Contract A unit test cannot catch this defect because the defect is in the inputs.
"""

from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from flask import Flask

from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.roster_status_snapshot import RosterStatusSnapshot
from models.sync_run import SyncRun
from services.availability_reference_date import (
    product_availability_reference_date,
    trusted_slate_reference_dates,
)
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db
from utils.time import utc_now_naive


SLATE = date(2026, 8, 17)
AVAILABILITY = date(2026, 8, 18)
TEAM_ID = 147
LIVE_REFERENCE = date(2026, 8, 18)


# ---------------------------------------------------------------------------
# 1. The shared date authority
# ---------------------------------------------------------------------------


def test_trusted_slate_reference_dates_splits_one_slate_into_two_dates():
    membership, availability = trusted_slate_reference_dates(SLATE)
    assert membership == SLATE
    assert availability == AVAILABILITY
    assert availability == product_availability_reference_date(latest_game_date=SLATE)
    assert membership != availability


@pytest.mark.parametrize('bad', [None, '', 'not-a-date', 17])
def test_trusted_slate_reference_dates_fails_closed_on_an_unusable_slate(bad):
    assert trusted_slate_reference_dates(bad) == (None, None)


def test_trusted_slate_reference_dates_accepts_an_iso_string():
    assert trusted_slate_reference_dates('2026-08-17') == (SLATE, AVAILABILITY)


# ---------------------------------------------------------------------------
# 2. The resolver's reference-date contract
# ---------------------------------------------------------------------------


def _league_snapshot(data_through=SLATE):
    return SimpleNamespace(
        id=437, data_through=data_through, sync_run_id=774,
        published_at=utc_now_naive(), subject_type=None,
    )


def _progressive_snapshot(data_through=SLATE):
    from models.share_artifact import SUBJECT_TYPE_TEAM_PROGRESSIVE
    return SimpleNamespace(
        id=901, data_through=data_through, sync_run_id=774,
        published_at=utc_now_naive(), subject_type=SUBJECT_TYPE_TEAM_PROGRESSIVE,
    )


@pytest.fixture
def trusted_source(monkeypatch):
    """A trusted, current serving snapshot and a live reference date past the slate."""
    import api.team_operations as team_ops
    import services.readiness_snapshot_freshness as freshness_mod

    monkeypatch.setattr(team_ops, '_sync_status_payload', lambda: {'status': 'success'})
    monkeypatch.setattr(
        team_ops, '_availability_reference_date', lambda sync_status: LIVE_REFERENCE,
    )
    monkeypatch.setattr(
        freshness_mod, 'serving_snapshot_freshness_authority',
        lambda snapshot, **kwargs: {
            'data_through': getattr(snapshot, 'data_through', None),
            'availability_reference_date': AVAILABILITY,
            'reference_date': AVAILABILITY,
            'active_window_days': 14,
            'reason_code': 'current_publication_critical_serving_snapshot',
            'source_scope': 'league_snapshot',
        },
    )
    return freshness_mod


def test_league_publication_membership_is_the_slate_and_availability_is_the_next_day(
    trusted_source,
):
    from services.share_artifact_generation import resolve_readiness_reference_dates

    membership, availability = resolve_readiness_reference_dates(_league_snapshot())
    assert membership == SLATE
    assert availability == AVAILABILITY


def test_team_progressive_source_uses_the_same_split(monkeypatch):
    import api.team_operations as team_ops
    import services.readiness_snapshot_freshness as freshness_mod
    from services.share_artifact_generation import resolve_readiness_reference_dates

    monkeypatch.setattr(team_ops, '_sync_status_payload', lambda: {'status': 'success'})
    monkeypatch.setattr(
        team_ops, '_availability_reference_date', lambda sync_status: LIVE_REFERENCE,
    )
    # A progressive checkpoint anchors on subject_type alone, with no freshness verdict.
    monkeypatch.setattr(
        freshness_mod, 'serving_snapshot_freshness_authority', lambda snapshot, **kw: None,
    )
    membership, availability = resolve_readiness_reference_dates(_progressive_snapshot())
    assert membership == SLATE
    assert availability == AVAILABILITY


def test_unanchored_read_keeps_the_live_reference_date_for_both(monkeypatch):
    """No trusted source: prior behavior is preserved exactly, both dates live."""
    import api.team_operations as team_ops
    import services.readiness_snapshot_freshness as freshness_mod
    from services.share_artifact_generation import resolve_readiness_reference_dates

    monkeypatch.setattr(team_ops, '_sync_status_payload', lambda: {'status': 'success'})
    monkeypatch.setattr(
        team_ops, '_availability_reference_date', lambda sync_status: LIVE_REFERENCE,
    )
    monkeypatch.setattr(
        freshness_mod, 'serving_snapshot_freshness_authority', lambda snapshot, **kw: None,
    )
    assert resolve_readiness_reference_dates(None) == (LIVE_REFERENCE, LIVE_REFERENCE)


def test_trusted_source_without_a_usable_slate_falls_closed_to_the_live_date(
    trusted_source,
):
    from services.share_artifact_generation import resolve_readiness_reference_dates

    membership, availability = resolve_readiness_reference_dates(
        _league_snapshot(data_through=None)
    )
    assert (membership, availability) == (LIVE_REFERENCE, LIVE_REFERENCE)


# ---------------------------------------------------------------------------
# 3. The two call sites receive their own date (the defect contract)
# ---------------------------------------------------------------------------


@pytest.fixture
def resolver_call_recorder(monkeypatch, trusted_source):
    """Stub the readiness pipeline and record the date each call site receives."""
    import api.team_operations as team_ops
    import services.availability_snapshot as availability_snapshot
    import team_operations as team_operations_pkg

    seen = {}
    record = {'pitcher_id': 1, 'pitcher': SimpleNamespace(id=1), 'availability': {}}

    def _classify(rows, reference_date=None, mode=None):
        seen['classification'] = reference_date
        return [record]

    def _population(records, *, team_id, reference_date):
        seen['population'] = reference_date
        return tuple(records), (frozenset({1}), True)

    def _trust(records, *, sync_status, generated_at, team_id=None,
               reference_date=None, membership=None):
        seen['trust'] = reference_date
        return {'confidence': 'high', 'data_state': 'fresh'}

    monkeypatch.setattr(availability_snapshot, 'latest_fatigue_rows', lambda **kw: [object()])
    monkeypatch.setattr(availability_snapshot, 'classify_latest_fatigue_rows', _classify)
    monkeypatch.setattr(team_ops, 'resolve_readiness_population', _population)
    monkeypatch.setattr(team_ops, '_team_operations_trust_metadata', _trust)
    monkeypatch.setattr(
        team_ops, '_filter_records_by_team_abbreviation', lambda records, **kw: tuple(records),
    )
    monkeypatch.setattr(team_ops, '_generated_at', lambda rows: '2026-08-18T10:30:00+00:00')
    monkeypatch.setattr(team_ops, '_readiness_record', lambda record: dict(record))
    monkeypatch.setattr(team_ops, '_team_payload_from_records', lambda records, **kw: {})
    monkeypatch.setattr(
        team_ops, '_team_operations_freshness_metadata',
        lambda records, *, sync_status, generated_at: {
            'freshness_state': 'current',
            'availability_reference_date': (
                (sync_status.get('freshness') or {}).get('availability_reference_date')
            ),
        },
    )
    monkeypatch.setattr(
        team_operations_pkg, 'assemble_bullpen_readiness',
        lambda **kwargs: {'freshness': kwargs.get('freshness'), 'contract_version': 'v3_phase_5'},
    )
    return seen


def test_classification_gets_the_availability_date_and_population_gets_the_slate(
    resolver_call_recorder,
):
    """The exact defect contract.

    Before the split, both call sites received the slate day, so every arm that
    pitched on ``data_through - 1`` still carried ``days_rest <= 1`` and its pitch
    count still counted as "yesterday" — a second full game of used arms held out of
    the clean bucket.
    """
    from services.share_artifact_generation import resolve_team_readiness_payload

    resolve_team_readiness_payload(TEAM_ID, source_snapshot=_league_snapshot())

    assert resolver_call_recorder['classification'] == AVAILABILITY
    assert resolver_call_recorder['population'] == SLATE
    assert resolver_call_recorder['classification'] != resolver_call_recorder['population']


def test_trust_classifier_keeps_the_slate_so_roster_authority_is_unchanged(
    resolver_call_recorder,
):
    """The run-476 repair is membership-side and is preserved byte for byte."""
    from services.share_artifact_generation import resolve_team_readiness_payload

    resolve_team_readiness_payload(TEAM_ID, source_snapshot=_league_snapshot())
    assert resolver_call_recorder['trust'] == SLATE


def test_published_freshness_reference_date_matches_the_classification_date(
    resolver_call_recorder,
):
    """Metadata agreement: the payload cannot claim a date it did not classify at.

    This is the assertion the artifact failed at snapshot 437 — freshness metadata
    said 2026-08-18 while the arms were classified as of 2026-08-17.
    """
    from services.share_artifact_generation import resolve_team_readiness_payload

    payload = resolve_team_readiness_payload(TEAM_ID, source_snapshot=_league_snapshot())
    stated = (payload.get('freshness') or {}).get('availability_reference_date')
    assert stated == AVAILABILITY.isoformat()
    assert stated == resolver_call_recorder['classification'].isoformat()


def test_reference_dates_out_records_the_dates_actually_used(resolver_call_recorder):
    from services.share_artifact_generation import resolve_team_readiness_payload

    captured = {}
    resolve_team_readiness_payload(
        TEAM_ID, source_snapshot=_league_snapshot(), reference_dates_out=captured,
    )
    assert captured['membership_reference_date'] == resolver_call_recorder['population']
    assert captured['availability_reference_date'] == resolver_call_recorder['classification']


# ---------------------------------------------------------------------------
# 4. A date-sensitive arm — the exact semantic difference
# ---------------------------------------------------------------------------


def _classify_one_arm(reference_date, *, pitches, game_date):
    """Classify a single arm's governed availability at ``reference_date``."""
    from services.availability import classify_availability

    log = SimpleNamespace(
        game_date=game_date, pitches_thrown=pitches, innings_pitched=1.0,
        innings_pitched_outs=3, mlb_game_pk=1,
    )
    score = SimpleNamespace(raw_score=20.0, risk_level='LOW')
    return classify_availability(
        score=score, game_logs=[log], reference_date=reference_date,
        latest_game_date=game_date, active_window_days=14,
    )['availability_status']


def test_an_arm_that_worked_the_day_before_the_slate_is_clean_only_at_the_next_day():
    """28 pitches on ``slate - 1`` is the whole defect in one arm.

    At the slate it reads Limited: those pitches land in the ``pitches_yesterday``
    window and rest is one day. At the canonical next-day reference the same arm is
    Available — nothing about the arm changed, only which day it was asked about.
    """
    worked = SLATE - timedelta(days=1)
    assert _classify_one_arm(SLATE, pitches=28, game_date=worked) == 'Limited'
    assert _classify_one_arm(AVAILABILITY, pitches=28, game_date=worked) == 'Available'


def test_an_arm_that_worked_the_slate_itself_is_not_clean_at_either_date():
    """The correction does not make used arms disappear — it moves the boundary by
    exactly one day. An arm that worked the slate is still held out of clean."""
    assert _classify_one_arm(SLATE, pitches=28, game_date=SLATE) != 'Available'
    assert _classify_one_arm(AVAILABILITY, pitches=28, game_date=SLATE) != 'Available'


# ---------------------------------------------------------------------------
# 5. End to end — a Yankees-shaped bullpen on a real seeded team
# ---------------------------------------------------------------------------


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    db.init_app(flask_app)
    with flask_app.app_context():
        create_test_schema(flask_app)
        try:
            yield flask_app
        finally:
            db.session.remove()
            drop_test_schema(flask_app)


def _add_arm(seed, *, worked_on, pitches):
    pitcher = Pitcher(
        mlb_id=940000 + seed, full_name=f'Arm {seed:02d}', team_id=TEAM_ID,
        team_name='Test Club', team_abbreviation='TST', throws='R', active=True,
        roster_status='ACTIVE', roster_status_source='mlb_stats_api:roster_sync:active',
    )
    db.session.add(pitcher)
    db.session.flush()
    if worked_on is not None:
        db.session.add(GameLog(
            pitcher_id=pitcher.id, mlb_game_pk=940000 + seed, game_date=worked_on,
            pitches_thrown=pitches, innings_pitched=1.0, innings_pitched_outs=3,
            opponent_abbreviation='OPP',
        ))
    db.session.add(FatigueScore(
        pitcher_id=pitcher.id, calculated_at=datetime(2026, 8, 17, 23, 0, seed),
        raw_score=20.0, pitch_count_score=0.0, rest_days_score=0.0,
        appearances_score=0.0, innings_score=0.0, leverage_score=0.0,
        days_since_last_appearance=1, appearances_last_7=1, appearances_last_14=1,
        pitches_last_7_days=pitches, innings_last_7_days=1.0, avg_leverage_last_7=None,
        risk_level='LOW',
    ))
    db.session.flush()
    return pitcher


def _seed_yankees_shaped_bullpen():
    """Eight active arms: six that last worked before the window, two on the slate.

    At the canonical availability reference this is 6 clean / 2 moderate / 0 severe
    / 0 unknown — Fresh. At the slate day the two arms that worked on ``slate - 4``
    would also be held out, and the published state would not be Fresh.
    """
    for seed in range(1, 7):
        _add_arm(seed, worked_on=SLATE - timedelta(days=5), pitches=12)
    for seed in (7, 8):
        _add_arm(seed, worked_on=SLATE, pitches=28)

    timestamp = utc_now_naive()
    run = SyncRun(
        job_name='roster', started_at=timestamp, completed_at=timestamp,
        status='success', stage='roster_status', source='test', created_at=timestamp,
    )
    db.session.add(run)
    db.session.flush()
    for pitcher in Pitcher.query.filter(Pitcher.active.is_(True)).all():
        db.session.add(RosterStatusSnapshot(
            pitcher_id=pitcher.id, mlb_id=pitcher.mlb_id, team_id=pitcher.team_id,
            snapshot_date=SLATE, roster_status='ACTIVE', active_roster=True,
            forty_man_roster=True, source='mlb_stats_api:roster_sync:active',
            sync_run_id=run.id, first_seen_at=timestamp, updated_at=timestamp,
        ))
    db.session.commit()


def test_yankees_shaped_bullpen_publishes_fresh_from_the_real_resolver(app, trusted_source):
    """Six clean plus two limited, through the production readiness resolver.

    The membership authority still resolves (the slate anchor is intact), the arms
    are classified at the next-day reference, and the governed partition is the
    6/2/0/0 the board showed while the artifact published Stretched.
    """
    _seed_yankees_shaped_bullpen()
    from services.share_artifact_generation import resolve_team_readiness_payload

    captured = {}
    payload = resolve_team_readiness_payload(
        TEAM_ID, source_snapshot=_league_snapshot(), reference_dates_out=captured,
    )

    assert payload is not None, 'roster authority must still resolve on the slate'
    evidence = payload['team_state_evidence']
    assert (
        evidence['clean_count'],
        evidence['moderate_count'],
        evidence['severe_count'],
        evidence['unknown_count'],
        evidence['active_pitcher_count'],
    ) == (6, 2, 0, 0, 8)
    assert payload['readiness']['status_code'] == 'operationally_stable'
    assert evidence['decisive_rule'] == 'fresh_coverage'
    assert captured == {
        'membership_reference_date': SLATE,
        'availability_reference_date': AVAILABILITY,
    }


def test_card_metrics_read_the_same_bullpen_at_the_same_availability_date(app):
    """The card and the Team State verdict must not describe two different days."""
    _seed_yankees_shaped_bullpen()
    from services.team_state_card_metrics import build_team_state_card_metrics

    metrics = build_team_state_card_metrics(TEAM_ID, reference_date=SLATE)
    summary = metrics['readiness_summary']

    # Membership stays on the slate: the roster authority resolves all eight arms.
    assert summary['active_bullpen_count'] == 8
    assert summary['authority_complete'] is True
    # Clean options are Available arms minus a workload warning, so they can never
    # exceed the classifier's clean count — and at the aligned date they do not.
    assert summary['clean_options']['count'] <= 6
    # Only the two arms that worked the slate are on short rest entering the next day.
    assert summary['short_rest_arms']['count'] == 2


def test_the_public_state_agrees_with_the_displayed_arm_breakdown(app, trusted_source):
    """End-to-end agreement: what the card shows and what the state says are one read."""
    _seed_yankees_shaped_bullpen()
    from services.share_artifact_generation import resolve_team_readiness_payload
    from services.team_state_card_metrics import build_team_state_card_metrics
    from services.team_state_public_vocabulary import INTERNAL_TO_PUBLIC_STATE

    payload = resolve_team_readiness_payload(TEAM_ID, source_snapshot=_league_snapshot())
    metrics = build_team_state_card_metrics(TEAM_ID, reference_date=SLATE)

    public_state = INTERNAL_TO_PUBLIC_STATE[payload['readiness']['status_code']]
    assert public_state == 'fresh'
    restricted = [
        row for row in metrics['reliever_evidence'] if row['availability'] != 'Available'
    ]
    assert len(restricted) == 2
    assert payload['team_state_evidence']['clean_count'] == 6
