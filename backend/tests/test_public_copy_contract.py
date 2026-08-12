"""FE-001 / #591 — the bullpen public-copy contract.

The board and dashboard publish a State, a Why sentence, and the evidence behind
it. All three are meaning-bearing public copy, and before this contract existed
they were only reader-safe because the browser rewrote them on the way to the
screen. These tests hold the line at the backend boundary instead: the payload a
reader receives must already be sayable, so the frontend can render it verbatim.

Three regressions are pinned permanently, because each one shipped:

  * ``Avoid``    — retired reader vocabulary, still an engine state
  * ``Monitor``  — engine vocabulary whose reader form is ``On Watch``
  * ``snapshot`` — internal framing in the stale-data limitation

Nothing here asserts WHICH state is chosen. That is the availability engine's
decision and #591 does not touch it. These tests assert only what a chosen state
is allowed to be CALLED.
"""

import re
from datetime import date, timedelta

import pytest
from flask import Flask

from api.bullpen import bullpen_bp
from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from services.bullpen_board import build_board_payload, build_team_context
from services.public_bullpen_copy import (
    PUBLIC_AVAILABILITY_LABELS,
    PUBLIC_AVAILABILITY_STATUSES,
    find_banned_public_prose,
    guard_public_prose,
    public_availability_label,
)
from services.roster_status import STATUS_ACTIVE
from services.team_state_public_vocabulary import PublicCopyGuardError
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db
from utils.time import utc_now_naive


# Every term that must never reach a reader inside a public sentence on this
# path. Written out literally rather than imported from the production set so
# that deleting a term from production cannot silently shrink what is policed.
PROHIBITED_PUBLIC_PROSE = (
    'Avoid',
    'Monitor',
    'snapshot',
    'restricted',
    'constrained',
    'recommendation engine',
    'deterministic',
)

# ``Rest-Restricted`` is a separately governed public pitcher-read label and is
# not part of this contract; see services/public_bullpen_copy.py.
PROSE_ALLOWANCES = ('rest-restricted',)


# Word-boundary matched, exactly as the production guard is. A naive substring
# scan flags "arms worth monitoring" and "unrestricted" — ordinary baseball
# English — and would make this contract useless by crying wolf.
_TERM_PATTERNS = {
    term: re.compile(rf'\b{re.escape(term)}\b', re.IGNORECASE)
    for term in PROHIBITED_PUBLIC_PROSE
}


def prose_violations(payload, path='$'):
    """Every public prose string in ``payload`` carrying a prohibited term."""
    found = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            found.extend(prose_violations(value, f'{path}.{key}'))
    elif isinstance(payload, (list, tuple)):
        for index, item in enumerate(payload):
            found.extend(prose_violations(item, f'{path}[{index}]'))
    elif isinstance(payload, str):
        candidate = payload
        for allowance in PROSE_ALLOWANCES:
            candidate = re.sub(re.escape(allowance), ' ', candidate, flags=re.IGNORECASE)
        for term, pattern in _TERM_PATTERNS.items():
            if pattern.search(candidate):
                found.append(f'{path}: {term!r} in {payload!r}')
    return found


# Only the fields that carry sentences a reader reads. Structured engine keys
# (``pct_restricted``, ``health.state``, ``supportingCounts``) are data, not
# copy, and are intentionally outside this contract.
def public_prose_of_context(context):
    health = context.get('health') or {}
    return {
        'why': health.get('label'),
        'reasons': health.get('reasons'),
        'limitations': context.get('limitations'),
    }


TEAM_ID = 221

SEEDED = (
    ('Fresh Arm', 9101, 12.0, 'LOW', 5),
    ('Watched Arm', 9102, 41.0, 'MODERATE', 1),
    ('Worked Arm', 9103, 68.0, 'HIGH', 1),
    ('Maxed Arm', 9104, 93.0, 'CRITICAL', 1),
)


def _seed_bullpen():
    for index, (name, mlb_id, raw_score, risk, days_ago) in enumerate(SEEDED):
        pitcher = Pitcher(
            mlb_id=mlb_id,
            full_name=name,
            team_id=TEAM_ID,
            team_name='Copy Contract Club',
            team_abbreviation='CCC',
            active=True,
            position='P',
            throws='R',
            roster_status=STATUS_ACTIVE,
            roster_status_source='test_fixture',
            roster_status_updated_at=utc_now_naive(),
        )
        db.session.add(pitcher)
        db.session.flush()
        for appearance in range(3):
            db.session.add(GameLog(
                pitcher_id=pitcher.id,
                mlb_game_pk=95000 + index * 10 + appearance,
                game_date=date.today() - timedelta(days=days_ago + appearance * 2),
                games_started=0,
                innings_pitched=1.0,
                innings_pitched_outs=3,
                pitches_thrown=18 + appearance * 6,
                game_type='R',
            ))
        db.session.add(FatigueScore(
            pitcher_id=pitcher.id,
            calculated_at=utc_now_naive(),
            raw_score=raw_score,
            pitch_count_score=raw_score,
            rest_days_score=raw_score,
            appearances_score=raw_score,
            innings_score=raw_score,
            leverage_score=0.0,
            days_since_last_appearance=days_ago,
            appearances_last_7=3,
            appearances_last_14=3,
            pitches_last_7_days=54,
            innings_last_7_days=3.0,
            risk_level=risk,
        ))
    db.session.commit()


@pytest.fixture
def client():
    app = Flask('test_public_copy_contract')
    app.config['APP_ENV'] = 'development'
    configure_test_database(app)
    app.register_blueprint(bullpen_bp, url_prefix='/api/bullpen')
    db.init_app(app)
    with app.app_context():
        create_test_schema(app)
        _seed_bullpen()
        try:
            yield app.test_client()
        finally:
            db.session.remove()
            drop_test_schema(app)


# ---------------------------------------------------------------------------
# B2 — the three shipped regressions, pinned permanently.
# ---------------------------------------------------------------------------

class TestKnownRegressionsArePinned:
    def test_avoid_is_refused_in_public_prose(self):
        assert find_banned_public_prose(
            'why', 'No relievers are marked Avoid or Unavailable.',
        ) == ('why', 'avoid')

    def test_monitor_is_refused_in_public_prose(self):
        assert find_banned_public_prose(
            'why', 'Two relievers are in the Monitor group.',
        ) == ('why', 'monitor')

    def test_snapshot_is_refused_in_public_prose(self):
        assert find_banned_public_prose(
            'limitations',
            'Latest workload data is outside the active freshness window, so this '
            'snapshot may not reflect current bullpen planning.',
        ) == ('limitations', 'snapshot')

    def test_the_corrected_wording_passes(self):
        for approved in (
            'No relievers are marked Unavailable.',
            'Four relievers are Unavailable.',
            'Two relievers are in the On Watch group.',
            'Latest workload data is outside the active freshness window, so this '
            'bullpen read may not reflect current bullpen planning.',
        ):
            assert find_banned_public_prose('why', approved) is None, approved

    def test_guard_raises_the_shared_typed_refusal(self):
        with pytest.raises(PublicCopyGuardError) as excinfo:
            guard_public_prose('context.health.label', 'Several arms are in the Monitor group.')
        assert excinfo.value.field == 'context.health.label'
        assert excinfo.value.term == 'monitor'

    def test_guard_does_not_over_ban_a_governed_pitcher_read_label(self):
        # ``Rest-Restricted`` is separately governed; the bare-word ``restricted``
        # ban must not fire on it or the guard would refuse valid public copy.
        assert find_banned_public_prose('label', 'Rest-Restricted') is None


# ---------------------------------------------------------------------------
# B5 — public availability vocabulary is backend-owned.
# ---------------------------------------------------------------------------

class TestPublicAvailabilityVocabularyIsBackendOwned:
    def test_engine_states_map_to_approved_public_labels(self):
        assert public_availability_label('Monitor') == 'On Watch'
        assert public_availability_label('Avoid') == 'Unavailable'
        assert public_availability_label('Available') == 'Available'
        assert public_availability_label('Limited') == 'Limited'
        assert public_availability_label('Unavailable') == 'Unavailable'

    def test_every_public_label_is_in_the_approved_set(self):
        for label in PUBLIC_AVAILABILITY_LABELS.values():
            assert label in PUBLIC_AVAILABILITY_STATUSES

    def test_no_public_label_is_engine_vocabulary(self):
        assert 'Monitor' not in PUBLIC_AVAILABILITY_STATUSES
        assert 'Avoid' not in PUBLIC_AVAILABILITY_STATUSES

    def test_an_unknown_state_fails_closed_rather_than_guessing(self):
        assert public_availability_label('Nonsense') is None
        assert public_availability_label(None) is None
        assert public_availability_label('') is None

    def test_board_cards_carry_the_public_label(self, client):
        body = client.get(f'/api/bullpen/teams/{TEAM_ID}/board').get_json()
        cards = [card for group in body['groups'] for card in group['pitchers']]

        assert cards
        for card in cards:
            assert card['availability_public_label'] in PUBLIC_AVAILABILITY_STATUSES

    def test_board_group_labels_are_group_headings_not_pitcher_statuses(self, client):
        """VOC-001: a group HEADING is not an individual availability status.

        The headings used to be the availability labels verbatim, so a column
        header and a chip on a card inside it read as the same claim. They are
        now group-shaped, and the two restricted groups name the workload
        threshold each one crosses instead of both reading 'Unavailable'.
        """
        body = client.get(f'/api/bullpen/teams/{TEAM_ID}/board').get_json()
        labels = [group['label'] for group in body['groups']]

        assert labels == [
            'Available Arms',
            'On-Watch Arms',
            'Limited Arms',
            'Unavailable — Heavy Workload',
            'Unavailable — Severe Workload',
        ]

        # Engine vocabulary still never reaches a reader.
        assert 'Monitor' not in labels
        assert 'Avoid' not in labels

        # And no heading is a bare availability status any more — that
        # collision is the thing this change removes.
        for status in PUBLIC_AVAILABILITY_STATUSES:
            assert status not in labels, status

    def test_board_group_engine_keys_and_order_are_unchanged(self, client):
        """The reader-facing wording moved; nothing behind it did."""
        from services.bullpen_board import BOARD_GROUP_ORDER

        body = client.get(f'/api/bullpen/teams/{TEAM_ID}/board').get_json()
        assert [group['status'] for group in body['groups']] == list(BOARD_GROUP_ORDER)
        assert body['group_order'] == list(BOARD_GROUP_ORDER)
        assert list(BOARD_GROUP_ORDER) == [
            'Available', 'Monitor', 'Limited', 'Avoid', 'Unavailable',
        ]


# ---------------------------------------------------------------------------
# B1 / B4 — the served payloads.
# ---------------------------------------------------------------------------

class TestServedPayloadPublicCopy:
    def test_board_publishes_no_prohibited_public_prose(self, client):
        body = client.get(f'/api/bullpen/teams/{TEAM_ID}/board').get_json()
        context = body.get('context') or {}

        assert prose_violations(public_prose_of_context(context)) == []
        assert prose_violations(body.get('team_shape')) == []
        assert prose_violations([g.get('label') for g in body['groups']]) == []

    def test_board_context_carries_a_non_empty_why(self, client):
        body = client.get(f'/api/bullpen/teams/{TEAM_ID}/board').get_json()
        why = ((body.get('context') or {}).get('health') or {}).get('label')

        assert isinstance(why, str)
        assert why.strip()

    def test_board_context_carries_evidence_behind_the_why(self, client):
        body = client.get(f'/api/bullpen/teams/{TEAM_ID}/board').get_json()
        reasons = ((body.get('context') or {}).get('health') or {}).get('reasons')

        assert isinstance(reasons, list)
        assert [r for r in reasons if str(r).strip()]

    def test_seeded_population_is_actually_populated(self, client):
        """An absence proof over an empty payload proves nothing."""
        body = client.get(f'/api/bullpen/teams/{TEAM_ID}/board').get_json()
        cards = [card for group in body['groups'] for card in group['pitchers']]
        assert len(cards) == len(SEEDED)

    def test_every_health_state_publishes_safe_prose(self):
        """Walk all five health states, not just the one the fixture lands on."""
        from services.bullpen_board import BOARD_GROUP_ORDER

        distributions = (
            {'Available': 6, 'Monitor': 0, 'Limited': 0, 'Avoid': 0, 'Unavailable': 0},
            {'Available': 2, 'Monitor': 5, 'Limited': 0, 'Avoid': 0, 'Unavailable': 0},
            {'Available': 2, 'Monitor': 1, 'Limited': 1, 'Avoid': 1, 'Unavailable': 1},
            {'Available': 0, 'Monitor': 1, 'Limited': 1, 'Avoid': 3, 'Unavailable': 2},
            {'Available': 0, 'Monitor': 0, 'Limited': 0, 'Avoid': 0, 'Unavailable': 0},
        )
        for counts in distributions:
            groups = [
                {'status': status, 'count': counts[status]}
                for status in BOARD_GROUP_ORDER
            ]
            context = build_team_context(groups, freshness={'is_current': True})
            assert prose_violations(public_prose_of_context(context)) == [], counts

    def test_stale_freshness_limitation_is_public_safe(self):
        """The stale path is where 'snapshot' shipped; exercise it explicitly."""
        from services.bullpen_board import BOARD_GROUP_ORDER

        groups = [{'status': status, 'count': 1} for status in BOARD_GROUP_ORDER]
        context = build_team_context(groups, freshness={'is_current': False})

        assert context['limitations']
        assert prose_violations(public_prose_of_context(context)) == []


# ---------------------------------------------------------------------------
# B3 — team-shape reads carry a guarded, backend-authored public summary.
# ---------------------------------------------------------------------------

def served_team_shape_reads(team_shape):
    """Every read a reader surface can resolve, from either served surface."""
    shape = team_shape or {}
    reads = list(shape.get('reads') or [])
    mapping = shape.get('byKey') or shape.get('by_key') or {}
    reads.extend(value for value in mapping.values() if isinstance(value, dict))
    return reads


class TestTeamShapePublicSummary:
    def test_every_authored_read_exposes_a_governed_summary(self):
        """Unit level: the authoring helper always emits the public field."""
        from services.team_bullpen_shape import _read

        read = _read('cleanOptions', 'Deep', 'The bullpen has clean choices.', {})
        assert read['summary'] == 'The bullpen has clean choices.'
        assert read['summary'] == read['explanation']

    def test_served_reads_carry_a_summary_and_pass_the_guard(self, client):
        body = client.get(f'/api/bullpen/teams/{TEAM_ID}/board').get_json()
        reads = served_team_shape_reads(body.get('team_shape'))

        for read in reads:
            assert 'summary' in read, read.get('key')
            assert isinstance(read['summary'], str) and read['summary'].strip()
        assert prose_violations([read.get('summary') for read in reads]) == []

    def test_withheld_team_shape_leaks_no_reads_on_either_surface(self, client):
        """Withholding must withhold on the key reader surfaces actually resolve.

        Clearing only ``reads`` and ``by_key`` left the camelCase ``byKey``
        populated, and the adapters resolve ``byKey`` first — so withheld copy
        was still readable.
        """
        body = client.get(f'/api/bullpen/teams/{TEAM_ID}/board').get_json()
        shape = body.get('team_shape') or {}
        if shape.get('counts_withheld') is not True:
            pytest.skip('fixture is not in the counts-withheld state')

        assert shape.get('reads') == []
        assert not (shape.get('byKey') or {})
        assert not (shape.get('by_key') or {})

    def test_publication_boundary_refuses_unsafe_team_shape_copy(self):
        """A guard that never fires is not a guard. Prove it refuses."""
        records = [{
            'name': 'Guarded Arm',
            'pitcher_id': 1,
            'fatigue_score': 20.0,
            'availability': {'availability_status': 'Available', 'confidence': 'high'},
        }]
        unsafe_shape = {'reads': [{'key': 'cleanOptions', 'summary': 'Monitor this group.'}]}

        from services import bullpen_board

        original = bullpen_board.build_team_bullpen_shape
        bullpen_board.build_team_bullpen_shape = lambda *a, **k: unsafe_shape
        try:
            with pytest.raises(PublicCopyGuardError):
                build_board_payload(team={'team_id': 1}, records=records)
        finally:
            bullpen_board.build_team_bullpen_shape = original
