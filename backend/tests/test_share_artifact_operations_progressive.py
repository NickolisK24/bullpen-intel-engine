"""SC-04B v1.2 — operations league/progressive summary SEPARATION.

The operator surface reports two separate publication authorities and NEVER
combines their counts: the all-or-nothing LEAGUE batch coverage
(``build_coverage_overview``) and the LATEST PROGRESSIVE EVENT
(``build_latest_progressive_event``). Artifacts are scoped by the DURABLE
``subject_type`` discriminator; the progressive ``request_source`` is only
event/audit context. A missing progressive event returns cleanly.
"""

from datetime import date, datetime, timedelta

import pytest
from flask import Flask

import models.share_artifact  # noqa: F401
from models.share_artifact_generation_audit import ShareArtifactGenerationAudit as Audit
from models.team_progressive_publication import TeamProgressivePublication as TPP
from services.share_artifact_operations import (
    COVERAGE_GENERATED,
    COVERAGE_MISSING,
    COVERAGE_REFUSED,
    PROGRESSIVE_STATUS_COMPLETE,
    PROGRESSIVE_STATUS_COMPLETE_WITH_REFUSALS,
    PROGRESSIVE_STATUS_INCOMPLETE,
    PROGRESSIVE_STATUS_NONE,
    build_latest_progressive_event,
)
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


TRIGGER_GAME = 823196
GAME_DATE = date(2026, 7, 23)


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


def _checkpoint(team_id, *, trigger_game_pk=TRIGGER_GAME, trusted=True, created_at=None):
    cp = TPP(
        team_id=team_id, trigger_type=TPP.TRIGGER_GAME_FINAL,
        trigger_game_pk=trigger_game_pk, official_game_date=GAME_DATE,
        data_through=GAME_DATE, trusted=trusted, game_final=True, ledger_complete=True,
        evidence_complete=True, status=TPP.STATUS_TRUSTED if trusted else TPP.STATUS_WITHHELD,
        created_at=created_at or datetime(2026, 7, 24, 16, 0, 0),
    )
    db.session.add(cp)
    db.session.flush()
    return cp


def _audit(team_id, checkpoint_id, outcome, *, public_id=None, blocking=None):
    db.session.add(Audit(
        team_id=team_id, source_snapshot_id=checkpoint_id, outcome=outcome,
        request_source=TPP.REQUEST_SOURCE, artifact_public_id=public_id,
        blocking_conditions=blocking, resolved_product_date=GAME_DATE,
        created_at=datetime(2026, 7, 24, 16, 5, 0),
    ))


# ---------------------------------------------------------------------------
# No event
# ---------------------------------------------------------------------------


def test_no_progressive_event_returns_cleanly(app):
    event = build_latest_progressive_event()
    assert event['has_event'] is False
    assert event['status'] == PROGRESSIVE_STATUS_NONE
    assert event['teams'] == []
    assert event['trigger_game_pk'] is None
    assert event['request_source'] == TPP.REQUEST_SOURCE


# ---------------------------------------------------------------------------
# A published + refused event
# ---------------------------------------------------------------------------


def test_latest_progressive_event_reports_trigger_teams_and_counts(app):
    c1 = _checkpoint(137)
    c2 = _checkpoint(108)
    _audit(137, c1.id, Audit.OUTCOME_PUBLISHED, public_id='pubSF')
    _audit(108, c2.id, Audit.OUTCOME_REFUSED, blocking=['insufficient_trust'])
    db.session.commit()

    event = build_latest_progressive_event()
    assert event['has_event'] is True
    assert event['trigger_game_pk'] == TRIGGER_GAME
    assert event['official_game_date'] == GAME_DATE.isoformat()
    assert set(event['checkpoint_ids']) == {c1.id, c2.id}
    assert event['team_count'] == 2
    assert event['attempted_team_count'] == 2
    assert event['generated_team_count'] == 1
    assert event['refused_team_count'] == 1
    assert event['missing_team_count'] == 0
    assert event['status'] == PROGRESSIVE_STATUS_COMPLETE_WITH_REFUSALS

    by_team = {t['team_id']: t for t in event['teams']}
    assert by_team[137]['state'] == COVERAGE_GENERATED
    assert by_team[137]['public_id'] == 'pubSF'
    assert by_team[137]['checkpoint_id'] == c1.id
    assert by_team[108]['state'] == COVERAGE_REFUSED
    assert by_team[108]['reason_code'] == 'insufficient_trust'


def test_missing_terminal_audit_is_missing_not_generated(app):
    c1 = _checkpoint(137)
    _checkpoint(108)  # no audit for team 108 -> missing
    _audit(137, c1.id, Audit.OUTCOME_PUBLISHED, public_id='pubSF')
    db.session.commit()

    event = build_latest_progressive_event()
    assert event['missing_team_count'] == 1
    assert event['status'] == PROGRESSIVE_STATUS_INCOMPLETE
    by_team = {t['team_id']: t for t in event['teams']}
    assert by_team[108]['state'] == COVERAGE_MISSING
    assert by_team[108]['public_id'] is None


def test_only_the_latest_event_is_summarized(app):
    # An older event (different game) must not bleed into the latest.
    old = _checkpoint(140, trigger_game_pk=820000, created_at=datetime(2026, 7, 20, 10, 0, 0))
    _audit(140, old.id, Audit.OUTCOME_PUBLISHED, public_id='old')
    c1 = _checkpoint(137, created_at=datetime(2026, 7, 24, 16, 0, 0))
    _audit(137, c1.id, Audit.OUTCOME_PUBLISHED, public_id='new')
    db.session.commit()

    event = build_latest_progressive_event()
    assert event['trigger_game_pk'] == TRIGGER_GAME
    assert event['team_count'] == 1
    assert {t['team_id'] for t in event['teams']} == {137}


def test_newest_checkpoint_per_team_wins_on_correction(app):
    # A genuine evidence correction mints a new checkpoint for the same team+game.
    first = _checkpoint(137, created_at=datetime(2026, 7, 24, 16, 0, 0))
    second = _checkpoint(137, created_at=datetime(2026, 7, 24, 18, 0, 0))
    _audit(137, first.id, Audit.OUTCOME_REFUSED, blocking=['stale'])
    _audit(137, second.id, Audit.OUTCOME_PUBLISHED, public_id='corrected')
    db.session.commit()

    event = build_latest_progressive_event()
    assert event['team_count'] == 1
    team = event['teams'][0]
    assert team['checkpoint_id'] == second.id
    assert team['state'] == COVERAGE_GENERATED
    assert team['public_id'] == 'corrected'


def test_progressive_request_source_isolates_from_league_audit(app):
    # A league-batch audit that shares the checkpoint's numeric source id must NOT be
    # mistaken for this progressive checkpoint's attempt.
    c1 = _checkpoint(137)
    _audit(137, c1.id, Audit.OUTCOME_PUBLISHED, public_id='progressive')
    # A league audit (no progressive request source) with the SAME source id.
    db.session.add(Audit(
        team_id=137, source_snapshot_id=c1.id, outcome=Audit.OUTCOME_REFUSED,
        request_source=None, resolved_product_date=GAME_DATE,
        created_at=datetime(2026, 7, 24, 17, 0, 0),
    ))
    db.session.commit()

    event = build_latest_progressive_event()
    team = event['teams'][0]
    # The progressive attempt (published) governs, not the league refusal.
    assert team['state'] == COVERAGE_GENERATED
    assert team['public_id'] == 'progressive'


def test_all_trusted_and_published_is_complete(app):
    c1 = _checkpoint(137)
    c2 = _checkpoint(108)
    _audit(137, c1.id, Audit.OUTCOME_PUBLISHED, public_id='a')
    _audit(108, c2.id, Audit.OUTCOME_REUSED, public_id='b')
    db.session.commit()
    event = build_latest_progressive_event()
    assert event['status'] == PROGRESSIVE_STATUS_COMPLETE
    assert event['generated_team_count'] == 1
    assert event['reused_team_count'] == 1


# ---------------------------------------------------------------------------
# One endpoint, two SEPARATE summaries — never combined
# ---------------------------------------------------------------------------


def test_overview_response_carries_both_league_and_progressive_summaries(app):
    from api.share_artifact_operations_api import build_overview_response

    c1 = _checkpoint(137)
    _audit(137, c1.id, Audit.OUTCOME_PUBLISHED, public_id='pubSF')
    db.session.commit()

    response, status = build_overview_response()
    assert status == 200
    body = response.get_json()
    # LEAGUE batch fields remain at the top level (unavailable here — no snapshot).
    assert 'generated_team_count' in body
    assert 'source_snapshot_id' in body
    # PROGRESSIVE event is a SEPARATE key; its counts are never merged into the league
    # batch counts.
    progressive = body['progressive_event']
    assert progressive['has_event'] is True
    assert progressive['trigger_game_pk'] == TRIGGER_GAME
    assert progressive['generated_team_count'] == 1
    # The league batch generated count is its own (0 here), not the progressive one.
    assert body['generated_team_count'] == 0
