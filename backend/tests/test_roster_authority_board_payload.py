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
    # CRC-6: the canonical roster-status category aggregates ride alongside the counts.
    assert 'category_counts' in authority and 'category_evidence' in authority


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


# 5. Parity (CRC-3 reconciled): the unknown-roster gap is closed.
def test_authority_and_legacy_agree_on_unknown_over_same_population(client):
    with client.application.app_context():
        _seed_team()
    expanded = _board(client, include_stale=True)
    authority = expanded['roster_authority']
    counts = authority['counts']
    population = authority['population']
    legacy = expanded['roster_status']

    # AGREES: on-the-active-roster count and (in the expanded view) the off-roster count.
    assert counts['bullpen_arms'] == legacy['active_mlb_count']
    assert counts['inactive_roster_context_count'] == legacy['inactive_context_count']

    # RECONCILED: the unknown-roster reliever now enters the authority population, so the
    # authority and legacy agree on unknown / known / total over this all-bullpen team.
    assert counts['roster_unknown_count'] == 1
    assert counts['roster_unknown_count'] == legacy['unknown_count']
    assert population['total_candidates'] == legacy['total_candidates'] == 6
    assert population['known_count'] == legacy['known_count'] == 5


# CRC-3: unknown-roster bullpen candidate is included WITH evidence.
def test_unknown_roster_candidate_included_with_evidence(client):
    with client.application.app_context():
        _seed_team()
    authority = _board(client)['roster_authority']
    counts = authority['counts']
    evidence = authority['evidence']['roster_unknown_count']

    assert counts['roster_unknown_count'] == 1
    assert len(evidence) == counts['roster_unknown_count']     # the count maps to evidence
    entry = evidence[0]
    assert entry['name'] == 'Quincy Question'
    assert set(entry) == {
        'pitcher_id', 'name', 'roster_status', 'roster_status_label',
        'roster_status_category', 'roster_status_category_label', 'availability', 'reason',
    }
    assert entry['roster_status'] == 'UNKNOWN'
    assert entry['roster_status_label']                        # human label present
    assert entry['roster_status_category'] == 'unknown'        # canonical category for unconfirmed
    assert entry['roster_status_category_label'] == 'Roster status pending'
    assert entry['reason']                                     # plain-language reason present


# CRC-3: total_candidates includes the unknown candidate and coverage drops below 1.0.
def test_total_candidates_includes_unknown_and_coverage_decreases(client):
    with client.application.app_context():
        _seed_team()
    population = _board(client)['roster_authority']['population']
    # 3 active + 2 off-roster + 1 unknown = 6.
    assert population['total_candidates'] == 6
    assert population['unknown_count'] == 1
    # Coverage = known / total = 5 / 6 < 1.0 (unknown candidate lowers coverage).
    assert population['roster_status_coverage'] == round(5 / 6, 4)
    assert population['roster_status_coverage'] < 1.0


# CRC-3: only BULLPEN-ELIGIBLE unknown-roster arms enter the authority. A clear starter
# with an unconfirmed roster status is excluded by the role filter (and documented).
def test_unknown_roster_starter_is_excluded_bullpen_eligible_only(client):
    with client.application.app_context():
        _seed_team()
        # A starter (clear gamesStarted signal) with no stored roster status.
        _seed_pitcher(
            'Stan Starter', team_id=TEAM_ID, mlb_id=70007, roster_status=None,
            raw_score=10.0, games=3, innings=[6.0, 6.0, 6.0], games_started=[1, 1, 1],
        )
    expanded = _board(client, include_stale=True)
    authority = expanded['roster_authority']['counts']
    legacy = expanded['roster_status']

    # The authority counts only the bullpen-eligible unknown-roster arm (the reliever),
    # not the starter — the role filter still governs bullpen eligibility.
    assert authority['roster_unknown_count'] == 1
    unknown_names = {e['name'] for e in expanded['roster_authority']['evidence']['roster_unknown_count']}
    assert unknown_names == {'Quincy Question'}
    assert 'Stan Starter' not in unknown_names
    # The legacy summary counts every active-roster pitcher's unknown status, including
    # the starter, so it is broader than the bullpen-eligible authority population.
    assert legacy['unknown_count'] == 2


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


# CRC Phase 4 (board migration) contract: the board banner now reads these exact
# Roster Authority fields. Guard them so a backend change cannot silently break the
# migrated board, and confirm no engine field names leak into the evidence the UI shows.
def test_board_payload_exposes_frontend_banner_contract(client):
    with client.application.app_context():
        _seed_team()
    authority = _board(client)['roster_authority']
    counts = authority['counts']
    population = authority['population']
    evidence = authority['evidence']

    for field in ('bullpen_arms', 'inactive_roster_context_count', 'roster_unknown_count'):
        assert isinstance(counts.get(field), int)
        # Every displayed count maps to an evidence list of the same length.
        assert isinstance(evidence.get(field), list)
        assert len(evidence[field]) == counts[field]
        for entry in evidence[field]:
            # Exactly the presentation fields the banner renders — no engine internals
            # (is_active_mlb / is_inactive_context) leak to the surface. The roster-status
            # category and its baseball label are presentation fields too (CRC-6).
            assert set(entry.keys()) == {
                'pitcher_id', 'name', 'roster_status', 'roster_status_label',
                'roster_status_category', 'roster_status_category_label',
                'availability', 'reason',
            }
    assert isinstance(population.get('roster_status_coverage'), (int, float))


# CRC Phase 6: the board payload carries the canonical roster-status category aggregates,
# they reconcile with the existing counts, and they are invariant across board views.
def test_board_payload_exposes_category_counts_that_reconcile(client):
    with client.application.app_context():
        _seed_team()
    authority = _board(client)['roster_authority']
    counts = authority['counts']
    category_counts = authority['category_counts']
    category_evidence = authority['category_evidence']

    # The seeded team: 3 active, 1 IL_60 (injured), 1 optioned, 1 unconfirmed.
    assert category_counts['active'] == 3
    assert category_counts['injured_list'] == 1
    assert category_counts['optioned_or_minors'] == 1
    assert category_counts['unknown'] == 1
    assert category_counts['forty_man_not_active'] == 0
    assert category_counts['restricted_or_special_list'] == 0
    assert category_counts['non_roster_depth'] == 0

    # Reconciles with the roster buckets the authority already publishes.
    assert category_counts['active'] == counts['bullpen_arms']
    assert category_counts['unknown'] == counts['roster_unknown_count']
    off_roster = sum(
        category_counts[c] for c in (
            'injured_list', 'optioned_or_minors', 'forty_man_not_active',
            'restricted_or_special_list', 'non_roster_depth',
        )
    )
    assert off_roster == counts['inactive_roster_context_count']

    # Every category is backed by an evidence list of the same length.
    for category, count in category_counts.items():
        assert len(category_evidence[category]) == count, f'category evidence mismatch for {category}'


def test_board_payload_category_counts_invariant_across_views(client):
    with client.application.app_context():
        _seed_team()
    assert (
        _board(client, include_stale=False)['roster_authority']['category_counts']
        == _board(client, include_stale=True)['roster_authority']['category_counts']
    )


# CRC Phase 9 audit guard. The legacy board ``roster_status`` summary is intentionally
# RETAINED (not retired) because a live production consumer still reads it: the Home
# "Tonight's Bullpen Picture" (frontend ``Home.jsx``) reads
# ``board.roster_status.inactive_context_count``. No behaviour-preserving swap to Roster
# Authority exists — Home fetches the DEFAULT board, where the legacy count is structurally 0,
# while the canonical ``inactive_roster_context_count`` is view-invariant (the full off-roster
# count). Migrating Home to the canonical field would change the displayed value (0 -> N), a
# user-facing change out of scope for this no-behaviour-change cleanup phase. This guard locks
# the retain decision so the legacy summary is not removed before Home.jsx is migrated.
def test_legacy_board_roster_status_retained_pending_home_migration(client):
    with client.application.app_context():
        _seed_team()
    body = _board(client)  # the DEFAULT board — exactly what Home.jsx fetches (no include_stale)

    # Both payloads coexist: the canonical authority AND the retained legacy summary.
    assert 'roster_authority' in body and 'roster_status' in body

    # The exact divergence that blocks a behaviour-preserving Home.jsx migration: in the default
    # view the legacy count Home reads is 0, but the canonical invariant count is the full 2.
    legacy_inactive = body['roster_status']['inactive_context_count']
    canonical_inactive = body['roster_authority']['counts']['inactive_roster_context_count']
    assert legacy_inactive == 0
    assert canonical_inactive == 2
    assert legacy_inactive != canonical_inactive
