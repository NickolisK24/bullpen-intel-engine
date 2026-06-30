"""
Tests for the Board V2 team-context layer (services/bullpen_board.py).

Pure functions only — no DB/Flask/network. Covers the deterministic health
rules, their threshold boundaries, descriptive metrics, transparency
(count-referencing explanations), and stale-data behaviour.

The context layer must remain descriptive: no scores, rankings, orderings, or
pitcher-level preferences may appear in its output.
"""

from services.bullpen_board import (
    BOARD_GROUP_ORDER,
    HEALTH_CONSTRAINED,
    HEALTH_ELEVATED,
    HEALTH_LABELS,
    HEALTH_MANAGEABLE,
    HEALTH_MONITORING,
    HEALTH_NO_DATA,
    METHODOLOGY_REASON,
    build_board_payload,
    build_team_context,
    classify_bullpen_health,
)


def counts(available=0, monitor=0, limited=0, avoid=0, unavailable=0):
    return {
        'Available': available,
        'Monitor': monitor,
        'Limited': limited,
        'Avoid': avoid,
        'Unavailable': unavailable,
    }


def groups_from_counts(c):
    """Shape group_cards() produces — only status/count matter to the context."""
    return [{'status': status, 'count': c[status]} for status in BOARD_GROUP_ORDER]


def total_of(c):
    return sum(c.values())


def context_of(c, freshness=None):
    return build_team_context(groups_from_counts(c), freshness=freshness)


# ── Health classification ──────────────────────────────────────────────────

class TestHealthClassification:
    def test_no_data_when_empty(self):
        assert classify_bullpen_health(counts(), 0) == HEALTH_NO_DATA

    def test_manageable_when_mostly_available_and_unrestricted(self):
        c = counts(available=7, monitor=1, limited=2)
        assert classify_bullpen_health(c, total_of(c)) == HEALTH_MANAGEABLE

    def test_constrained_when_restricted_at_forty_percent(self):
        # 4 of 10 are Avoid/Unavailable — exactly the 40% boundary.
        c = counts(available=6, avoid=4)
        assert classify_bullpen_health(c, total_of(c)) == HEALTH_CONSTRAINED

    def test_constrained_when_nobody_available(self):
        c = counts(monitor=5, limited=5)
        assert classify_bullpen_health(c, total_of(c)) == HEALTH_CONSTRAINED

    def test_monitoring_when_monitor_reaches_forty_percent(self):
        c = counts(available=6, monitor=4)
        assert classify_bullpen_health(c, total_of(c)) == HEALTH_MONITORING

    def test_monitoring_when_monitor_is_largest_group(self):
        # Monitor (3) is the strict largest; restricted (2) would also satisfy
        # the elevated rule, so this also asserts monitoring outranks elevated.
        c = counts(available=2, monitor=3, limited=2, avoid=1, unavailable=1)
        assert classify_bullpen_health(c, total_of(c)) == HEALTH_MONITORING

    def test_elevated_when_restricted_at_twenty_percent(self):
        c = counts(available=8, avoid=2)
        assert classify_bullpen_health(c, total_of(c)) == HEALTH_ELEVATED

    def test_elevated_when_available_below_forty_percent(self):
        c = counts(available=3, limited=7)
        assert classify_bullpen_health(c, total_of(c)) == HEALTH_ELEVATED

    def test_priority_constrained_beats_monitoring(self):
        # Heavy restriction AND monitor-dominant → constrained wins.
        c = counts(available=0, monitor=5, avoid=3, unavailable=2)
        assert classify_bullpen_health(c, total_of(c)) == HEALTH_CONSTRAINED


# ── Metrics + transparency ─────────────────────────────────────────────────

class TestContextMetrics:
    def test_metrics_count_each_group(self):
        ctx = context_of(counts(available=5, monitor=3, limited=2, avoid=1, unavailable=2))
        m = ctx['metrics']
        assert m['total_relievers'] == 13
        assert (m['available'], m['monitor'], m['limited'], m['avoid'], m['unavailable']) == (5, 3, 2, 1, 2)
        assert m['restricted'] == 3

    def test_percentages_are_whole_numbers(self):
        ctx = context_of(counts(available=7, monitor=1, limited=2))
        m = ctx['metrics']
        assert m['pct_available'] == 70
        assert m['pct_unavailable'] == 0

    def test_metrics_have_no_score_or_ranking_fields(self):
        ctx = context_of(counts(available=5, avoid=1))
        forbidden = ('score', 'rank', 'rating', 'quality', 'composite', 'priority', 'best')
        for key in ctx['metrics']:
            assert not any(term in key.lower() for term in forbidden), key


class TestTransparency:
    def test_reasons_reference_real_counts(self):
        ctx = context_of(counts(available=7, monitor=1, limited=2))
        reasons = ctx['health']['reasons']
        assert any('Seven relievers are available from the latest completed workload data.' == r for r in reasons)
        assert any('No relievers are marked Avoid or Unavailable.' == r for r in reasons)
        assert METHODOLOGY_REASON in reasons

    def test_restricted_count_is_explained(self):
        ctx = context_of(counts(available=6, avoid=2, unavailable=2))
        reasons = ctx['health']['reasons']
        assert any('Four relievers are Avoid or Unavailable.' == r for r in reasons)

    def test_every_state_has_a_label_and_reasons(self):
        scenarios = {
            HEALTH_MANAGEABLE: counts(available=8, monitor=2),
            HEALTH_MONITORING: counts(available=5, monitor=5),
            HEALTH_ELEVATED: counts(available=8, avoid=2),
            HEALTH_CONSTRAINED: counts(available=4, avoid=4, unavailable=2),
            HEALTH_NO_DATA: counts(),
        }
        for expected_state, c in scenarios.items():
            ctx = context_of(c)
            assert ctx['health']['state'] == expected_state
            assert ctx['health']['label'] == HEALTH_LABELS[expected_state]
            assert len(ctx['health']['reasons']) >= 1


# ── Freshness / confidence ─────────────────────────────────────────────────

class TestFreshness:
    def test_current_data_is_high_confidence(self):
        ctx = context_of(counts(available=5), freshness={'is_current': True})
        assert ctx['confidence'] == 'high'
        assert ctx['limitations'] == []

    def test_stale_data_degrades_confidence_and_explains_itself(self):
        ctx = context_of(counts(available=5, monitor=2), freshness={'is_current': False})
        assert ctx['confidence'] == 'low'
        assert len(ctx['limitations']) >= 1
        # The freshness caveat is surfaced in the explanation, not hidden.
        assert any('outside the active freshness window' in r for r in ctx['health']['reasons'])

    def test_empty_pen_reports_no_confidence(self):
        ctx = context_of(counts())
        assert ctx['confidence'] == 'none'
        assert ctx['health']['state'] == HEALTH_NO_DATA


# ── Payload integration ────────────────────────────────────────────────────

class TestContextInPayload:
    def _records(self, c):
        records = []
        pid = 1
        for status in BOARD_GROUP_ORDER:
            for _ in range(c[status]):
                records.append({
                    'name': f'P{pid}',
                    'pitcher_id': pid,
                    'fatigue_score': 20,
                    'availability': {'availability_status': status, 'confidence': 'high',
                                     'data_state': 'fresh', 'reasons': [], 'limitations': []},
                })
                pid += 1
        return records

    def test_payload_includes_context_and_stays_governance_safe(self):
        c = counts(available=7, monitor=1, limited=2)
        payload = build_board_payload(
            team={'team_id': 1, 'team_name': 'T', 'team_abbreviation': 'T'},
            records=self._records(c),
            freshness={'is_current': True},
            generated_at='2026-06-05T00:00:00+00:00',
        )
        assert payload['ranking_applied'] is False
        assert payload['selection_made'] is False
        assert payload['context']['health']['state'] == HEALTH_MANAGEABLE
        assert payload['context']['metrics']['total_relievers'] == 10
        # Context must not introduce its own raw governance flags.
        assert 'ranking_applied' not in payload['context']
        assert 'selection_made' not in payload['context']
