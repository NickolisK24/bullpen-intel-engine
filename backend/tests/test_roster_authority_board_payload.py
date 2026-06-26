"""CRC Phase 2 — Roster Authority is exposed in the bullpen board payload.

Parallel/additive only: the canonical Roster Authority appears alongside the legacy
``roster_status``, is invariant across board views (Active vs Active+Unavailable /
Unavailable), and leaves the legacy payload untouched. These tests also record the
observed parity between the authority and the legacy summary. No consumer is migrated.
"""

import pytest
from flask import Flask
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

import services.sync as sync_service
import models.prospect  # noqa: F401  (register on db.metadata)
from api.bullpen import bullpen_bp, build_team_roster_authority
from services.roster_authority import CAPABILITY as ROSTER_AUTHORITY_CAPABILITY
from services.roster_status import STATUS_ACTIVE, STATUS_IL_60, STATUS_MINORS
from tests.test_bullpen_board import _seed_pitcher
from utils.db import db


TEAM_ID = 147


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_service, 'STATUS_FILE', tmp_path / 'sync_status.json')
    app = Flask(__name__)
    configure_test_database(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    app.register_blueprint(bullpen_bp, url_prefix='/api/bullpen')
    with app.app_context():
        create_test_schema(app)
        try:
            yield app.test_client()
        finally:
            db.session.remove()
            drop_test_schema(app)


def _seed_team():
    """3 active-roster arms, 2 off-roster arms, 1 unconfirmed-roster arm."""
    _seed_pitcher('Aaron Active', team_id=TEAM_ID, mlb_id=70001, roster_status=STATUS_ACTIVE, raw_score=10.0)
    _seed_pitcher('Bart Active', team_id=TEAM_ID, mlb_id=70002, roster_status=STATUS_ACTIVE, raw_score=20.0)
    _seed_pitcher('Cody Active', team_id=TEAM_ID, mlb_id=70003, roster_status=STATUS_ACTIVE, raw_score=30.0)
    _seed_pitcher('Ike Injured', team_id=TEAM_ID, mlb_id=70004, roster_status=STATUS_IL_60, raw_score=10.0)
    _seed_pitcher('Omar Optioned', team_id=TEAM_ID, mlb_id=70005, roster_status=STATUS_MINORS, raw_score=10.0)
    _seed_pitcher('Quincy Question', team_id=TEAM_ID, mlb_id=70006, roster_status=None, raw_score=10.0)


def _board(client, *, include_stale=False):
    url = f'/api/bullpen/teams/{TEAM_ID}/board'
    if include_stale:
        url += '?include_stale=true'
    return client.get(url).get_json()


# 1. Roster Authority appears in the board payload.
def test_roster_authority_present_in_board_payload(client):
    with client.application.app_context():
        _seed_team()
    body = _board(client)
    assert 'roster_authority' in body
    authority = body['roster_authority']
    assert authority['capability'] == ROSTER_AUTHORITY_CAPABILITY
    assert authority['invariant'] is True
    assert 'counts' in authority and 'evidence' in authority and 'population' in authority


# 2. Legacy payload remains unchanged (still present with its full structure).
def test_legacy_roster_status_still_present_and_intact(client):
    with client.application.app_context():
        _seed_team()
    legacy = _board(client)['roster_status']
    for key in (
        'authority', 'total_candidates', 'known_count', 'unknown_count',
        'active_mlb_count', 'inactive_context_count', 'excluded_inactive_count',
    ):
        assert key in legacy, f'legacy roster_status lost {key}'


# 3. Invariant fields match expected authority values, each backed by evidence.
def test_authority_invariant_fields_match_expected(client):
    with client.application.app_context():
        _seed_team()
    authority = _board(client)['roster_authority']
    counts = authority['counts']
    assert counts['bullpen_arms'] == 3                      # the active-roster bullpen
    assert counts['inactive_roster_context_count'] == 2     # IL_60 + Optioned
    for field, count in counts.items():
        assert len(authority['evidence'][field]) == count, f'evidence mismatch for {field}'


# 4. Different board views expose identical Roster Authority; only legacy may differ.
def test_authority_is_identical_across_board_views(client):
    with client.application.app_context():
        _seed_team()
    active_view = _board(client, include_stale=False)
    expanded_view = _board(client, include_stale=True)

    # Byte-identical authority regardless of the view filter — the whole point.
    assert active_view['roster_authority'] == expanded_view['roster_authority']

    # The legacy summary is allowed to move with the view (the defect the authority
    # fixes): off-roster arms are excluded from the count in the Active view.
    assert active_view['roster_status']['inactive_context_count'] == 0
    assert expanded_view['roster_status']['inactive_context_count'] == 2
    assert (
        active_view['roster_status']['inactive_context_count']
        != expanded_view['roster_status']['inactive_context_count']
    )


# 5. Parity observation (verify agreement; document differences, do not fix).
def test_observed_parity_between_authority_and_legacy(client):
    with client.application.app_context():
        _seed_team()
    expanded = _board(client, include_stale=True)
    authority = expanded['roster_authority']['counts']
    legacy = expanded['roster_status']

    # AGREES: on-the-active-roster count and (in the expanded view) the off-roster count.
    assert authority['bullpen_arms'] == legacy['active_mlb_count']
    assert authority['inactive_roster_context_count'] == legacy['inactive_context_count']

    # DIFFERS (documented, not fixed): the shared eligible-population helper gates out
    # unknown-roster arms, so the authority does not yet see them, while the legacy
    # summary counts them from the full classified statuses.
    assert authority['roster_unknown_count'] == 0
    assert legacy['unknown_count'] >= 1


# The standalone entrypoint produces the same authority the board exposes.
def test_standalone_entrypoint_matches_board_payload(client):
    with client.application.app_context():
        _seed_team()
        standalone = build_team_roster_authority(TEAM_ID)
    board_authority = _board(client, include_stale=True)['roster_authority']
    for key in ('counts', 'evidence', 'population'):
        assert standalone[key] == board_authority[key]


# Invariance holds at the API layer too: the board route never lets include_stale
# change a single authority count.
def test_board_route_authority_counts_unchanged_by_include_stale(client):
    with client.application.app_context():
        _seed_team()
    assert (
        _board(client, include_stale=False)['roster_authority']['counts']
        == _board(client, include_stale=True)['roster_authority']['counts']
    )
