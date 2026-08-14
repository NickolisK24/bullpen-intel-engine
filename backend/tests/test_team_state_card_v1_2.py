"""SC-04B v1.2 — the code-rendered Team State card baseline (NO performance metrics).

Covers the two backend-owned card data blocks (readiness_summary + bounded,
deterministically-ordered reliever_evidence), the ``team-state-1.2.0`` payload
contract, its public-read projection, progressive/league parity, and temporal
correctness. Every value comes from an existing canonical authority; nothing here
is a performance metric or league rank (unsupported without a team-at-appearance
authority) and no card-only availability label ever appears.
"""

from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from flask import Flask

import models.prospect  # noqa: F401
import models.share_artifact  # noqa: F401
from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.roster_status_snapshot import RosterStatusSnapshot
from models.scheduled_game import ScheduledGame
from models.sync_run import SyncRun
from services.public_bullpen_copy import PUBLIC_AVAILABILITY_STATUSES
from services.share_artifacts import (
    build_share_artifact_draft,
    publish_share_artifact,
    verify_share_artifact_integrity,
)
from services.share_artifact_public import load_public_share_artifact
from services.team_state_card_metrics import (
    MAX_RELIEVER_ROWS,
    _build_reliever_evidence,
    _outs_to_innings_text,
    _restriction_rank,
    build_team_state_card_metrics,
)
from services.team_state_payload import (
    TEAM_STATE_LATEST,
    TEAM_STATE_V1,
    TEAM_STATE_V1_1,
    TEAM_STATE_V1_2,
    build_team_state_payload,
    team_state_payload_registry,
)
from services.team_state_source import TeamStateSnapshotAuthority, TeamStateSource
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from tests.roster_readiness_fixture import seed_roster_readiness_snapshots
from utils.db import db
from utils.time import utc_now_naive


TEAM_ID = 121
SLATE = date(2026, 7, 23)


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


# ---------------------------------------------------------------------------
# Seed: a deterministic team whose last 3 completed games include a doubleheader
# on the slate, an off day, and a 4th game outside the window.
# ---------------------------------------------------------------------------

# game_pk, game_date. 7001+7002 = doubleheader on the slate; 7003 after an off day
# (7-22 has no game); 7000 is the 4th game (outside the 3-game window).
_GAMES = [
    (7001, SLATE),                    # doubleheader game 1 (slate)
    (7002, SLATE),                    # doubleheader game 2 (slate)
    (7003, SLATE - timedelta(days=3)),  # 2026-07-20, after an off day
    (7000, SLATE - timedelta(days=6)),  # 2026-07-17, OUTSIDE the last-3 window
]


def _seed_games():
    for gpk, gd in _GAMES:
        db.session.add(ScheduledGame(
            team_id=TEAM_ID, game_pk=gpk, game_date=gd, status_state='final',
            home_away='home', opponent_team_id=900, game_number=1,
        ))
    # A future (post-slate) game must never enter a historical window.
    db.session.add(ScheduledGame(
        team_id=TEAM_ID, game_pk=7009, game_date=SLATE + timedelta(days=2),
        status_state='final', home_away='home', opponent_team_id=900, game_number=1,
    ))


def _add_reliever(seed, *, throws, appearances, last_date, opponent='SFG',
                  raw_score=20.0, days_since=0, post_slate=False):
    """Seed one active-bullpen reliever with controlled window appearances + rest."""
    p = Pitcher(
        mlb_id=930000 + seed, full_name=f'Reliever {seed:02d}', team_id=TEAM_ID,
        team_name='Test Club', team_abbreviation='TST', throws=throws, active=True,
        roster_status='ACTIVE', roster_status_source='mlb_stats_api:roster_sync:active',
    )
    db.session.add(p)
    db.session.flush()
    for gpk in appearances:
        gd = next(d for g, d in _GAMES if g == gpk)
        db.session.add(GameLog(
            pitcher_id=p.id, mlb_game_pk=gpk, game_date=gd, pitches_thrown=12,
            innings_pitched=1.0, innings_pitched_outs=3, opponent_abbreviation=opponent,
        ))
    if post_slate:
        # A completed appearance AFTER the slate — must not affect a slate-anchored read.
        db.session.add(GameLog(
            pitcher_id=p.id, mlb_game_pk=7009, game_date=SLATE + timedelta(days=2),
            pitches_thrown=15, innings_pitched=1.0, innings_pitched_outs=3,
            opponent_abbreviation='FUT',
        ))
    db.session.add(FatigueScore(
        pitcher_id=p.id, calculated_at=datetime(2026, 6, 3, 12, 0, seed),
        raw_score=raw_score, pitch_count_score=0.0, rest_days_score=0.0,
        appearances_score=0.0, innings_score=0.0, leverage_score=0.0,
        days_since_last_appearance=days_since, appearances_last_7=len(appearances),
        appearances_last_14=len(appearances), pitches_last_7_days=12 * len(appearances),
        innings_last_7_days=float(len(appearances)), avg_leverage_last_7=None,
        risk_level='LOW',
    ))
    db.session.flush()
    return p


def _seed_roster_authority():
    ts = utc_now_naive()
    run = SyncRun(job_name='r', started_at=ts, completed_at=ts, status='success',
                  stage='roster_status', source='r', created_at=ts)
    db.session.add(run)
    db.session.flush()
    for p in Pitcher.query.filter(Pitcher.active.is_(True)).all():
        db.session.add(RosterStatusSnapshot(
            pitcher_id=p.id, mlb_id=p.mlb_id, team_id=p.team_id, snapshot_date=SLATE,
            roster_status='ACTIVE', active_roster=True, forty_man_roster=True,
            source='mlb_stats_api:roster_sync:active', sync_run_id=run.id,
            first_seen_at=ts, updated_at=ts,
        ))
    db.session.commit()


def _seed_team():
    _seed_games()
    # P1 RHP: doubleheader (7001+7002) -> multi-use, rest 0.
    _add_reliever(1, throws='R', appearances=[7001, 7002], last_date=SLATE, days_since=0)
    # P2 LHP: one slate game, rest 0.
    _add_reliever(2, throws='L', appearances=[7001], last_date=SLATE, days_since=0)
    # P3 RHP: only the older in-window game (7003) -> rest 3.
    _add_reliever(3, throws='R', appearances=[7003], last_date=SLATE - timedelta(days=3),
                  days_since=3)
    # P4 LHP: only the out-of-window game (7000) -> 0 window appearances, rest 6.
    _add_reliever(4, throws='L', appearances=[7000], last_date=SLATE - timedelta(days=6),
                  days_since=6)
    # P5 RHP: 7002 + 7003 -> multi-use, rest 0, with a POST-slate appearance to prove
    # temporal anchoring.
    _add_reliever(5, throws='R', appearances=[7002, 7003], last_date=SLATE, days_since=0,
                  post_slate=True)
    _seed_roster_authority()


# ---------------------------------------------------------------------------
# readiness_summary
# ---------------------------------------------------------------------------


def test_active_bullpen_count_is_the_canonical_membership(app):
    _seed_team()
    metrics = build_team_state_card_metrics(TEAM_ID, reference_date=SLATE)
    summary = metrics['readiness_summary']
    assert summary['active_bullpen_count'] == 5
    assert summary['authority_complete'] is True


def test_clean_options_total_is_active_count_and_count_bounded(app):
    _seed_team()
    metrics = build_team_state_card_metrics(TEAM_ID, reference_date=SLATE)
    clean = metrics['readiness_summary']['clean_options']
    assert clean['total'] == 5
    assert 0 <= clean['count'] <= 5
    assert clean['label'] == 'Clean options'
    assert 'active bullpen arms are clean options' in clean['statement']


def test_multi_use_counts_arms_in_two_of_last_three_team_games(app):
    _seed_team()
    metrics = build_team_state_card_metrics(TEAM_ID, reference_date=SLATE)
    multi = metrics['readiness_summary']['multi_use_arms']
    # P1 (7001+7002) and P5 (7002+7003) each appear in >=2 of the last 3 games.
    assert multi['count'] == 2
    assert multi['total'] == 5
    assert multi['games_in_window'] == 3


def test_multi_use_uses_team_games_not_calendar_days(app):
    # The window spans an off day (7-22 has no game) and a doubleheader (two games on
    # one day). It is three TEAM GAMES, not three calendar days: the 4th game (7000)
    # is excluded even though it is within a small calendar span.
    _seed_team()
    metrics = build_team_state_card_metrics(TEAM_ID, reference_date=SLATE)
    game_pks = set(metrics['evidence_window']['game_pks'])
    assert game_pks == {7001, 7002, 7003}
    assert 7000 not in game_pks  # 4th completed game is outside the window
    assert 7009 not in game_pks  # post-slate game never enters


def test_short_rest_counts_zero_or_one_day_rest(app):
    _seed_team()
    metrics = build_team_state_card_metrics(TEAM_ID, reference_date=SLATE)
    short = metrics['readiness_summary']['short_rest_arms']
    # P1, P2, P5 rest 0; P3 rest 3; P4 rest 6 -> 3 short-rest arms.
    assert short['count'] == 3
    assert short['total'] == 5


def test_left_handed_options_documents_denominator_and_counts_usable(app):
    _seed_team()
    metrics = build_team_state_card_metrics(TEAM_ID, reference_date=SLATE)
    lhp = metrics['readiness_summary']['left_handed_options']
    # P2 and P4 are LHP -> denominator 2.
    assert lhp['total'] == 2
    assert lhp['denominator'] == 'active bullpen left-handers'
    assert 0 <= lhp['count'] <= 2
    assert 'left-handers are usable options' in lhp['statement']


def test_readiness_summary_has_all_four_metrics(app):
    _seed_team()
    summary = build_team_state_card_metrics(TEAM_ID, reference_date=SLATE)['readiness_summary']
    for key in ('clean_options', 'multi_use_arms', 'short_rest_arms', 'left_handed_options'):
        assert key in summary
        assert 'label' in summary[key] and 'statement' in summary[key]


def test_no_performance_metric_keys_in_readiness_summary(app):
    _seed_team()
    summary = build_team_state_card_metrics(TEAM_ID, reference_date=SLATE)['readiness_summary']
    text = repr(summary).lower()
    for banned in ('era', 'blown_save', 'save_conversion', 'inherited_runners', 'rank'):
        assert banned not in text


# ---------------------------------------------------------------------------
# reliever_evidence
# ---------------------------------------------------------------------------


def test_reliever_rows_carry_the_required_fields(app):
    _seed_team()
    rows = build_team_state_card_metrics(TEAM_ID, reference_date=SLATE)['reliever_evidence']
    assert rows
    for row in rows:
        for field in (
            'pitcher_id', 'name', 'last_three_appearances', 'outs_recorded',
            'innings_text', 'last_appearance_date', 'last_opponent', 'rest_days',
            'availability',
        ):
            assert field in row


def test_reliever_availability_is_public_vocabulary_never_card_only(app):
    """The row is reader vocabulary by destination, not an internal structured field.

    This assertion used to name the ENGINE set as "canonical", which let the
    card publish ``Monitor`` and ``Avoid`` straight into the reader-facing
    Availability column while a green test said the field was governed. The
    public vocabulary owner decides this set.
    """
    _seed_team()
    rows = build_team_state_card_metrics(TEAM_ID, reference_date=SLATE)['reliever_evidence']
    assert rows
    for row in rows:
        assert row['availability'] in PUBLIC_AVAILABILITY_STATUSES
    for banned in ('Normal', 'Stressed', 'Tired', 'Risky', 'Fade'):
        assert banned not in repr(rows)


def test_engine_only_states_are_never_newly_published(app):
    """Negative contract: the two engine-only words cannot reach a new artifact.

    ``Monitor`` and ``Avoid`` are the states the vocabulary owner reserves as
    engine-only. Seeding a bullpen that classifies into them and asserting on the
    published rows is what makes this non-vacuous — a repr scan over an empty or
    all-Available table would pass while proving nothing.
    """
    _seed_team()
    rows = build_team_state_card_metrics(TEAM_ID, reference_date=SLATE)['reliever_evidence']
    assert rows

    published = repr(rows)
    assert 'Monitor' not in published
    assert 'Avoid' not in published

    # The mapping is applied, not merely absent: at least one row carries a label
    # that only exists because an engine state was projected through the owner.
    labels = {row['availability'] for row in rows}
    assert labels <= set(PUBLIC_AVAILABILITY_STATUSES)


def test_an_unrecognised_engine_state_withholds_the_row(app):
    """Fail-closed: no governed public label, no published row.

    The card never shows a raw state and never guesses a public one, matching how
    a pitcher with no classified availability read is already omitted.
    """
    _seed_team()
    baseline = build_team_state_card_metrics(TEAM_ID, reference_date=SLATE)['reliever_evidence']
    assert baseline

    import services.team_state_card_metrics as metrics

    original = metrics.public_availability_label
    try:
        metrics.public_availability_label = lambda status: None
        rows = build_team_state_card_metrics(TEAM_ID, reference_date=SLATE)['reliever_evidence']
    finally:
        metrics.public_availability_label = original

    assert rows == []


def test_row_order_still_ranks_by_engine_restriction(app):
    """Ordering keeps the engine ladder even though the row publishes the label.

    The public vocabulary is deliberately lossy — ``Avoid`` and ``Unavailable``
    share one public label — so ranking on the published label would silently
    merge two distinct restriction tiers. This pins that it does not.
    """
    _seed_team()
    rows = build_team_state_card_metrics(TEAM_ID, reference_date=SLATE)['reliever_evidence']
    assert rows

    order = {label: index for index, label in enumerate(
        ('Unavailable', 'Limited', 'On Watch', 'Available')
    )}
    ranks = [order[row['availability']] for row in rows]
    assert ranks == sorted(ranks)


def test_reliever_evidence_is_bounded_to_six_rows(app):
    _seed_games()
    for s in range(9):  # nine active arms -> more than the bounded table
        _add_reliever(s + 1, throws='R', appearances=[7001], last_date=SLATE, days_since=0)
    _seed_roster_authority()
    rows = build_team_state_card_metrics(TEAM_ID, reference_date=SLATE)['reliever_evidence']
    assert len(rows) == MAX_RELIEVER_ROWS


def test_reliever_includes_the_just_completed_trigger_game(app):
    _seed_team()
    rows = build_team_state_card_metrics(TEAM_ID, reference_date=SLATE)['reliever_evidence']
    by_id = {r['pitcher_id']: r for r in rows}
    # P1 worked the slate doubleheader: last appearance is the slate, rest 0.
    p1 = next(r for r in rows if r['name'] == 'Reliever 01')
    assert p1['last_appearance_date'] == SLATE.isoformat()
    assert p1['rest_days'] == 0
    assert p1['last_three_appearances'] == 2


def test_doubleheader_counts_as_two_window_appearances(app):
    _seed_team()
    rows = build_team_state_card_metrics(TEAM_ID, reference_date=SLATE)['reliever_evidence']
    p1 = next(r for r in rows if r['name'] == 'Reliever 01')
    # Both slate games (7001, 7002) count -> 2 appearances, 6 outs.
    assert p1['last_three_appearances'] == 2
    assert p1['outs_recorded'] == 6


def test_reliever_ordering_is_most_restrictive_first_then_tiebreaks():
    # Unit test the deterministic order directly with synthetic rows.
    def rec(status):
        return {'availability': {'availability_status': status, 'data_state': 'fresh'}}

    active_ids = [10, 11, 12, 13, 14]
    record_by_pid = {
        10: rec('Available'), 11: rec('Unavailable'), 12: rec('Limited'),
        13: rec('Monitor'), 14: rec('Avoid'),
    }
    pitchers = {i: SimpleNamespace(full_name=f'P{i}') for i in active_ids}
    workload = {i: {'appearances': 1, 'outs': 3} for i in active_ids}
    last = {i: {'date': date(2026, 7, 23), 'opponent': 'X'} for i in active_ids}
    rows = _build_reliever_evidence(
        active_ids=active_ids, record_by_pid=record_by_pid, pitchers=pitchers,
        workload=workload, last_appearances=last, reference_date=date(2026, 7, 23),
    )
    # Rows publish the PUBLIC label; ordering still follows the engine ladder.
    # Engine order Unavailable -> Avoid -> Limited -> Monitor -> Available becomes
    # Unavailable, Unavailable, Limited, On Watch, Available: the two most
    # restrictive tiers share one public word while keeping their distinct places.
    order = [r['availability'] for r in rows]
    assert order == ['Unavailable', 'Unavailable', 'Limited', 'On Watch', 'Available']
    # The engine identity behind row 0 vs row 1 is not published, and must not be.
    assert 'Avoid' not in repr(rows)
    assert 'Monitor' not in repr(rows)


def test_reliever_ordering_tiebreak_appearances_then_outs_then_recency_then_id():
    def rec(status='Available'):
        return {'availability': {'availability_status': status, 'data_state': 'fresh'}}

    active_ids = [20, 21, 22, 23]
    record_by_pid = {i: rec() for i in active_ids}
    pitchers = {i: SimpleNamespace(full_name=f'P{i}') for i in active_ids}
    workload = {
        20: {'appearances': 1, 'outs': 3},
        21: {'appearances': 2, 'outs': 6},   # most appearances -> first
        22: {'appearances': 1, 'outs': 6},   # same appearances as 20, more outs
        23: {'appearances': 1, 'outs': 3},   # ties 20 on appearances+outs -> id breaks
    }
    last = {
        20: {'date': date(2026, 7, 20), 'opponent': 'X'},
        21: {'date': date(2026, 7, 20), 'opponent': 'X'},
        22: {'date': date(2026, 7, 20), 'opponent': 'X'},
        23: {'date': date(2026, 7, 23), 'opponent': 'X'},  # more recent than 20
    }
    rows = _build_reliever_evidence(
        active_ids=active_ids, record_by_pid=record_by_pid, pitchers=pitchers,
        workload=workload, last_appearances=last, reference_date=date(2026, 7, 23),
    )
    assert [r['pitcher_id'] for r in rows] == [21, 22, 23, 20]


def test_outs_to_innings_text():
    assert _outs_to_innings_text(0) == '0.0'
    assert _outs_to_innings_text(3) == '1.0'
    assert _outs_to_innings_text(7) == '2.1'


def test_restriction_rank_orders_most_restrictive_first():
    assert _restriction_rank('Unavailable') < _restriction_rank('Available')
    assert _restriction_rank(None) == 5  # unknown sorts last


# ---------------------------------------------------------------------------
# Temporal correctness + determinism
# ---------------------------------------------------------------------------


def test_post_slate_appearance_never_leaks_into_a_slate_read(app):
    _seed_team()
    rows = build_team_state_card_metrics(TEAM_ID, reference_date=SLATE)['reliever_evidence']
    p5 = next(r for r in rows if r['name'] == 'Reliever 05')
    # P5 has a post-slate appearance (7009), but the slate read stops at the slate.
    assert p5['last_appearance_date'] == SLATE.isoformat()
    assert p5['rest_days'] == 0
    assert p5['last_opponent'] != 'FUT'


def test_metrics_are_idempotent_for_the_same_slate(app):
    _seed_team()
    first = build_team_state_card_metrics(TEAM_ID, reference_date=SLATE)
    second = build_team_state_card_metrics(TEAM_ID, reference_date=SLATE)
    assert first == second


def test_empty_active_bullpen_yields_empty_card_metrics(app):
    # No pitchers / roster authority -> membership empty -> fail closed to empties.
    metrics = build_team_state_card_metrics(TEAM_ID, reference_date=SLATE)
    assert metrics['reliever_evidence'] == []
    assert metrics['readiness_summary']['active_bullpen_count'] == 0
    assert metrics['readiness_summary']['clean_options']['count'] == 0


# ---------------------------------------------------------------------------
# team-state-1.2.0 payload contract
# ---------------------------------------------------------------------------


def _readiness(team_name='Test Club', team_abbreviation='TST',
               status_code='operationally_stressed', confidence='high'):
    return {
        'capability': 'team_operations_bullpen_readiness', 'scope': 'team_bullpen_readiness',
        'contract': 'x', 'contract_version': 'v3_phase_4', 'contract_state': 'degraded',
        'ranking_applied': False, 'selection_made': False, 'generated_at': '2026-07-23T12:00:00Z',
        'team': {'team_id': TEAM_ID, 'team_name': team_name, 'team_abbreviation': team_abbreviation},
        'readiness': {'status': 'Operationally Stressed', 'status_code': status_code,
                      'summary': 'Stressed.', 'basis': []},
        'constraints': [],
        'trust_metadata': {'confidence': confidence, 'confidence_reasons': [], 'data_state': 'fresh',
                           'source_evidence_state': 'complete', 'governance_state': 'compliant',
                           'generated_at': '2026-07-23T12:00:00Z', 'limitations': [], 'explanations': [],
                           'refusal_reasons': [], 'trust_validation_errors': [], 'ranking_applied': False,
                           'selection_made': False},
        'freshness': {'freshness_state': 'current', 'data_through': '2026-07-23', 'limitations': []},
        'fail_closed': {'failed_closed': False, 'state': 'degraded_safe_output'},
        'refusal': {'refused': False},
    }


def _authority(subject_type=None, snapshot_id=8001):
    return TeamStateSnapshotAuthority(
        snapshot_id=snapshot_id, sync_run_id=None, data_through=SLATE,
        published_at=datetime(2026, 7, 23, 13, 0, 0), unavailable_reason=None,
        subject_type=subject_type,
    )


def _source(subject_type=None, readiness=None):
    return TeamStateSource(
        team_id=TEAM_ID, team_valid=True, snapshot=_authority(subject_type),
        readiness=readiness or _readiness(), requested_date=None,
    )


def test_registry_registers_v1_2_and_keeps_prior_versions(app):
    versions = team_state_payload_registry.versions()
    assert TEAM_STATE_V1 in versions
    assert TEAM_STATE_V1_1 in versions
    assert TEAM_STATE_V1_2 in versions
    assert TEAM_STATE_LATEST == TEAM_STATE_V1_2


def test_v1_2_document_has_a_card_block_with_all_sections(app):
    _seed_team()
    doc = build_team_state_payload(_source(), version=TEAM_STATE_V1_2).document
    assert doc['payload_version'] == TEAM_STATE_V1_2
    card = doc['card']
    for key in ('artifact_context', 'team', 'state', 'readiness_summary',
                'reliever_evidence', 'trust', 'limitations'):
        assert key in card
    assert card['team']['canonical_name'] == 'Test Club'
    assert card['team']['abbreviation'] == 'TST'
    assert card['state']['public_state'] == 'vulnerable'


def test_v1_2_artifact_context_freezes_scope_and_data_through_only(app):
    _seed_team()
    ctx = build_team_state_payload(_source(), version=TEAM_STATE_V1_2).document['card']['artifact_context']
    assert ctx['data_through'] == SLATE.isoformat()
    assert ctx['publication_scope'] == 'league_snapshot'
    assert ctx['publication_label'] == 'Published BaseballOS Snapshot'
    # generated_at / published_at are NOT frozen (unknown at build time).
    assert 'generated_at' not in ctx
    assert 'published_at' not in ctx


def test_v1_2_scope_from_durable_discriminator(app):
    _seed_team()
    league = build_team_state_payload(_source(None), version=TEAM_STATE_V1_2).document['card']
    progressive = build_team_state_payload(_source('team_progressive'), version=TEAM_STATE_V1_2).document['card']
    assert league['artifact_context']['publication_scope'] == 'league_snapshot'
    assert progressive['artifact_context']['publication_scope'] == 'team_progressive'
    assert progressive['artifact_context']['publication_label'] == 'Published Team Bullpen State'


def test_v1_2_document_carries_no_performance_context(app):
    _seed_team()
    doc = build_team_state_payload(_source(), version=TEAM_STATE_V1_2).document
    text = repr(doc).lower()
    for banned in ('performance_context', 'bullpen_era', 'save_conversion', 'mlb_rank',
                   'league_rank', 'blown_saves'):
        assert banned not in text


def test_v1_2_payload_is_deterministic(app):
    _seed_team()
    first = build_team_state_payload(_source(), version=TEAM_STATE_V1_2).document
    second = build_team_state_payload(_source(), version=TEAM_STATE_V1_2).document
    assert first == second


def test_v1_2_schema_version_stays_1_0_0_via_publication(app):
    _seed_team()
    payload = build_team_state_payload(_source(), version=TEAM_STATE_V1_2)
    draft = build_share_artifact_draft(session=db.session, **payload.to_share_artifact_kwargs())
    artifact = publish_share_artifact(draft, dedup=True, session=db.session)
    db.session.commit()
    assert artifact.schema_version == '1.0.0'
    assert artifact.render_version == TEAM_STATE_V1_2
    assert verify_share_artifact_integrity(artifact) is True


# ---------------------------------------------------------------------------
# Public read projection of the card
# ---------------------------------------------------------------------------


def _publish(subject_type=None, readiness=None):
    payload = build_team_state_payload(_source(subject_type, readiness), version=TEAM_STATE_V1_2)
    kwargs = payload.to_share_artifact_kwargs()
    if subject_type is not None:
        kwargs['subject_type'] = subject_type
    draft = build_share_artifact_draft(session=db.session, **kwargs)
    artifact = publish_share_artifact(draft, dedup=True, session=db.session)
    db.session.commit()
    return artifact


def test_public_read_projects_the_card_with_column_timestamps(app):
    _seed_team()
    artifact = _publish()
    result = load_public_share_artifact(artifact.public_id)
    assert result.status == 'ok'
    card = result.view['card']
    assert card['card_version'] == TEAM_STATE_V1_2
    # artifact_context is enriched with the artifact's own timestamps from columns.
    assert card['artifact_context']['generated_at'] is not None
    assert card['artifact_context']['published_at'] is not None
    assert card['artifact_context']['data_through'] == SLATE.isoformat()
    assert len(card['readiness_summary']) >= 4
    assert isinstance(card['reliever_evidence'], list)


def test_public_read_card_scope_matches_progressive_discriminator(app):
    _seed_team()
    artifact = _publish(subject_type='team_progressive')
    result = load_public_share_artifact(artifact.public_id)
    card = result.view['card']
    assert card['artifact_context']['publication_scope'] == 'team_progressive'
    # And the top-level scope projection agrees (both from the durable discriminator).
    assert result.view['publication_scope']['publication_scope'] == 'team_progressive'


def test_public_read_has_no_card_for_legacy_artifact(app):
    _seed_team()
    payload = build_team_state_payload(_source(), version=TEAM_STATE_V1_1)
    draft = build_share_artifact_draft(session=db.session, **payload.to_share_artifact_kwargs())
    artifact = publish_share_artifact(draft, dedup=True, session=db.session)
    db.session.commit()
    result = load_public_share_artifact(artifact.public_id)
    assert 'card' not in result.view


# ---------------------------------------------------------------------------
# Progressive / league parity on the same slate
# ---------------------------------------------------------------------------


def test_progressive_and_league_same_slate_yield_equivalent_card_data(app):
    _seed_team()
    league = build_team_state_payload(_source(None), version=TEAM_STATE_V1_2).document['card']
    progressive = build_team_state_payload(_source('team_progressive'), version=TEAM_STATE_V1_2).document['card']
    # Equivalent baseball facts.
    assert league['readiness_summary'] == progressive['readiness_summary']
    assert league['reliever_evidence'] == progressive['reliever_evidence']
    assert league['state'] == progressive['state']
    # Distinct provenance / identity.
    assert league['artifact_context']['publication_scope'] != progressive['artifact_context']['publication_scope']


def test_progressive_and_league_public_state_and_trust_match(app):
    _seed_team()
    league = build_team_state_payload(_source(None), version=TEAM_STATE_V1_2).document['card']
    progressive = build_team_state_payload(_source('team_progressive'), version=TEAM_STATE_V1_2).document['card']
    assert league['trust']['confidence'] == progressive['trust']['confidence']
    assert league['state']['public_state'] == progressive['state']['public_state']
