"""Tests for the shared bullpen eligibility vocabulary (Phase C3B).

These cover the normalized vocabulary, the engine -> vocabulary mappings, the
guaranteed payload field set, and the fail-closed inclusion guard that replaced
the per-service fail-open checks.
"""

from datetime import date, timedelta
from types import SimpleNamespace

from services.bullpen_eligibility import (
    STATUS_BULLPEN_RELEVANT,
    STATUS_CLEAR_STARTER,
    STATUS_INACTIVE,
    STATUS_INACTIVE_BULLPEN_RELEVANT,
    STATUS_NON_PITCHER,
    STATUS_NO_USAGE,
    STATUS_UNCERTAIN,
    evaluate_bullpen_eligibility,
)
from services.bullpen_eligibility_vocabulary import (
    BULLPEN_PICTURE_TYPES,
    ELIGIBILITY_EXCLUDED,
    ELIGIBILITY_NORMAL_RELIEF,
    ELIGIBILITY_STARTER_PROTECTED,
    ELIGIBILITY_SWING_BULK_RELIEF,
    ELIGIBILITY_TYPES,
    ELIGIBILITY_UNKNOWN_LIMITED,
    SOURCE_FALLBACK,
    SOURCE_LEGACY_INNINGS,
    SOURCE_ROLE_AUTHORITY,
    eligibility_type_for,
    normalize_eligibility,
    record_is_bullpen_eligible,
)
from services.role_authority import (
    ROLE_AMBIGUOUS,
    ROLE_RELIEVER,
    ROLE_STARTER,
    ROLE_UNKNOWN,
    classify_role,
)

REF = date(2026, 6, 6)


class _LogStub:
    def __init__(
        self, innings_outs, games_started, save=False, hold=False,
        save_situation=False, days_ago=1, game_type='R',
    ):
        self.innings_pitched_outs = innings_outs
        self.innings_pitched = innings_outs / 3.0
        self.games_started = games_started
        self.save = save
        self.hold = hold
        self.save_situation = save_situation
        self.game_date = REF - timedelta(days=days_ago)
        self.game_type = game_type


def _pitcher(position='P', active=True):
    return SimpleNamespace(position=position, active=active)


# ── Guaranteed field set ─────────────────────────────────────────────────────

def test_normal_payload_is_preserved_and_typed():
    payload = {
        'eligible': True,
        'role': ROLE_RELIEVER,
        'status': 'role_reliever',
        'confidence': 'high',
        'reason': 'Recent usage is primarily relief.',
        'evidence': ['3 recent appearance(s).'],
        'limitations': [],
        'authority': 'games_started',
        'role_confidence': 'high',
    }
    normalized = normalize_eligibility(payload)

    assert normalized['eligible'] is True
    assert normalized['eligibility_type'] == ELIGIBILITY_NORMAL_RELIEF
    assert normalized['confidence'] == 'high'
    assert normalized['reason'] == 'Recent usage is primarily relief.'
    assert normalized['authority'] == 'games_started'
    assert normalized['source'] == SOURCE_ROLE_AUTHORITY
    # Original keys are preserved for backward compatibility.
    assert normalized['role'] == ROLE_RELIEVER
    assert normalized['role_confidence'] == 'high'
    assert normalized['evidence'] == ['3 recent appearance(s).']


def test_every_normalized_payload_carries_the_shared_field_set():
    for payload in (
        None,
        {},
        {'eligible': True, 'role': ROLE_RELIEVER},
        {'eligible': False, 'status': STATUS_CLEAR_STARTER},
        'garbage',
    ):
        normalized = normalize_eligibility(payload)
        for field in ('eligible', 'eligibility_type', 'confidence', 'reason', 'authority', 'source'):
            assert field in normalized, field
        assert isinstance(normalized['eligible'], bool)
        assert normalized['eligibility_type'] in ELIGIBILITY_TYPES


# ── Fail-closed handling ─────────────────────────────────────────────────────

def test_missing_payload_fails_closed():
    normalized = normalize_eligibility(None)

    assert normalized['eligible'] is False
    assert normalized['eligibility_type'] == ELIGIBILITY_UNKNOWN_LIMITED
    assert normalized['source'] == SOURCE_FALLBACK
    assert normalized['confidence'] == 'none'
    assert normalized['reason']


def test_record_without_eligibility_is_excluded():
    assert record_is_bullpen_eligible({}) is False
    assert record_is_bullpen_eligible({'eligibility': None}) is False
    assert record_is_bullpen_eligible({'eligibility': {}}) is False
    assert record_is_bullpen_eligible(None) is False


def test_record_with_eligible_payload_is_included():
    assert record_is_bullpen_eligible({'eligibility': {'eligible': True}}) is True
    assert record_is_bullpen_eligible({'eligibility': {'eligible': False}}) is False


# ── Vocabulary / enum ────────────────────────────────────────────────────────

def test_eligibility_vocabulary_values():
    assert ELIGIBILITY_TYPES == {
        ELIGIBILITY_NORMAL_RELIEF,
        ELIGIBILITY_SWING_BULK_RELIEF,
        ELIGIBILITY_STARTER_PROTECTED,
        ELIGIBILITY_EXCLUDED,
        ELIGIBILITY_UNKNOWN_LIMITED,
    }
    assert BULLPEN_PICTURE_TYPES <= ELIGIBILITY_TYPES


# ── Role Authority mapping ───────────────────────────────────────────────────

def test_role_authority_role_mapping():
    cases = {
        ROLE_RELIEVER: ELIGIBILITY_NORMAL_RELIEF,
        ROLE_AMBIGUOUS: ELIGIBILITY_SWING_BULK_RELIEF,
        ROLE_STARTER: ELIGIBILITY_STARTER_PROTECTED,
        ROLE_UNKNOWN: ELIGIBILITY_UNKNOWN_LIMITED,
    }
    for role, expected in cases.items():
        assert eligibility_type_for({'role': role}) == expected


def test_role_authority_engine_output_maps_end_to_end():
    reliever = classify_role(
        _pitcher(),
        [_LogStub(3, 0, days_ago=1), _LogStub(3, 0, days_ago=3), _LogStub(4, 0, days_ago=5)],
        reference_date=REF,
    )
    normalized_reliever = normalize_eligibility(reliever)
    assert normalized_reliever['eligible'] is True
    assert normalized_reliever['eligibility_type'] == ELIGIBILITY_NORMAL_RELIEF
    assert normalized_reliever['source'] == SOURCE_ROLE_AUTHORITY

    starter = classify_role(
        _pitcher(),
        [_LogStub(18, 1, days_ago=day) for day in (1, 3, 5, 7, 9)],
        reference_date=REF,
    )
    normalized_starter = normalize_eligibility(starter)
    assert normalized_starter['eligible'] is False
    assert normalized_starter['eligibility_type'] == ELIGIBILITY_STARTER_PROTECTED


# ── Legacy innings-heuristic mapping ─────────────────────────────────────────

def test_legacy_engine_status_mapping():
    cases = {
        STATUS_BULLPEN_RELEVANT: ELIGIBILITY_NORMAL_RELIEF,
        STATUS_INACTIVE_BULLPEN_RELEVANT: ELIGIBILITY_NORMAL_RELIEF,
        STATUS_CLEAR_STARTER: ELIGIBILITY_STARTER_PROTECTED,
        STATUS_INACTIVE: ELIGIBILITY_EXCLUDED,
        STATUS_NON_PITCHER: ELIGIBILITY_EXCLUDED,
        STATUS_NO_USAGE: ELIGIBILITY_UNKNOWN_LIMITED,
        STATUS_UNCERTAIN: ELIGIBILITY_UNKNOWN_LIMITED,
    }
    for status, expected in cases.items():
        assert eligibility_type_for({'status': status}) == expected


def test_legacy_payload_source_and_authority():
    normalized = normalize_eligibility({
        'eligible': True,
        'status': STATUS_BULLPEN_RELEVANT,
        'confidence': 'high',
        'reason': 'relief',
    })
    assert normalized['source'] == SOURCE_LEGACY_INNINGS
    assert normalized['authority'] == SOURCE_LEGACY_INNINGS
    assert normalized['eligibility_type'] == ELIGIBILITY_NORMAL_RELIEF


def test_legacy_engine_output_maps_end_to_end():
    starter = evaluate_bullpen_eligibility(
        _pitcher(),
        [_LogStub(18, 1, days_ago=1), _LogStub(16, 1, days_ago=6), _LogStub(18, 1, days_ago=11)],
        reference_date=REF,
    )
    normalized = normalize_eligibility(starter)
    assert normalized['eligible'] is False
    assert normalized['eligibility_type'] == ELIGIBILITY_STARTER_PROTECTED
    assert normalized['source'] == SOURCE_LEGACY_INNINGS


# ── Malformed payloads ───────────────────────────────────────────────────────

def test_malformed_payloads_map_to_unknown_limited():
    for payload in (None, 'garbage', 123, [], {'role': 'Nonsense'}, {'status': 'nonsense'}, {}):
        assert eligibility_type_for(payload) == ELIGIBILITY_UNKNOWN_LIMITED

    normalized = normalize_eligibility('garbage')
    assert normalized['eligible'] is False
    assert normalized['eligibility_type'] == ELIGIBILITY_UNKNOWN_LIMITED
    assert record_is_bullpen_eligible({'eligibility': 'garbage'}) is False


def test_eligible_boolean_is_never_flipped():
    # Start-leaning ambiguous: engine marks eligible False, but the kind is swing.
    start_leaning = normalize_eligibility({
        'eligible': False, 'role': ROLE_AMBIGUOUS, 'status': 'role_ambiguous',
    })
    assert start_leaning['eligible'] is False
    assert start_leaning['eligibility_type'] == ELIGIBILITY_SWING_BULK_RELIEF

    # Swing-leaning ambiguous: eligible True, same kind.
    swing_leaning = normalize_eligibility({'eligible': True, 'role': ROLE_AMBIGUOUS})
    assert swing_leaning['eligible'] is True
    assert swing_leaning['eligibility_type'] == ELIGIBILITY_SWING_BULK_RELIEF

    starter = normalize_eligibility({'eligible': False, 'role': ROLE_STARTER})
    assert starter['eligible'] is False
    assert starter['eligibility_type'] == ELIGIBILITY_STARTER_PROTECTED


# ── Fail-closed wiring into every consuming guard ────────────────────────────

def test_fail_closed_is_wired_into_all_guards():
    from services.bullpen_capacity import _is_bullpen_record as capacity_guard
    from services.bullpen_resource_health import _is_bullpen_record as health_guard
    from services.bullpen_stability import _is_bullpen_record as stability_guard
    from services.bullpen_trust_hierarchy import _is_bullpen_record as trust_guard
    from services.injury_il_context import _is_bullpen_context as injury_guard

    guards = [capacity_guard, trust_guard, stability_guard, health_guard, injury_guard]
    for guard in guards:
        # Missing eligibility now fails closed (previously included).
        assert guard({}) is False
        assert guard({'eligibility': None}) is False
        # Explicit eligibility is still honored.
        assert guard({'eligibility': {'eligible': True}}) is True
        assert guard({'eligibility': {'eligible': False}}) is False
