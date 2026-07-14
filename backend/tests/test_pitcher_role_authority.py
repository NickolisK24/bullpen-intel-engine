"""
Tests for the public role authority (services/pitcher_role_authority.py).

Two trust guarantees:
  * Observed relief roles are classified from confirmed regular-season relief
    appearances only — starts, non-regular-season games, and unknown start
    states are excluded and disclosed.
  * One backend-authored public role read owns the chip and the disclosure
    headline, so a guarded Limited Read card can never publicly headline a
    rejected concrete role.
"""

from datetime import date, timedelta

from services.pitcher_role import ROLE_WINDOW_DAYS
from services.pitcher_role_authority import (
    GUARDED_PUBLIC_REASON,
    NON_REGULAR_SEASON_EXCLUDED_LIMITATION,
    START_EXCLUDED_LIMITATION,
    UNKNOWN_START_EXCLUDED_LIMITATION,
    author_public_role_read,
    author_role_read_labels,
    qualifying_relief_logs,
    role_logs_by_pitcher,
)

REF = date(2026, 6, 20)


class LogStub:
    def __init__(self, days_ago, innings=1.0, games_started=0, game_type='R',
                 save=False, hold=False, save_situation=False, leverage_index=None,
                 game_date=None):
        self.game_date = game_date if game_date is not None else REF - timedelta(days=days_ago)
        self.innings_pitched = innings
        self.innings_pitched_outs = None if innings is None else int(round(innings * 3))
        self.games_started = games_started
        self.game_type = game_type
        self.save = save
        self.hold = hold
        self.save_situation = save_situation
        self.leverage_index = leverage_index


class PitcherStub:
    def __init__(self, pitcher_id=1):
        self.id = pitcher_id


def _record(pitcher_id=1, eligibility=None, roster_status=None):
    return {
        'pitcher': PitcherStub(pitcher_id),
        'availability': {
            'availability_status': 'Available',
            'data_state': 'fresh',
            'confidence': 'high',
        },
        'eligibility': eligibility or {'status': 'role_reliever'},
        'roster_status': roster_status or {'status': 'active'},
    }


def _author(logs, eligibility=None):
    record = _record(eligibility=eligibility)
    return author_role_read_labels(record, {1: logs}, reference_date=REF)


# ── Role-log filtering ───────────────────────────────────────────────────────

class TestQualifyingReliefLogs:
    def test_includes_regular_season_relief_appearances(self):
        logs = [LogStub(d, games_started=0, game_type='R') for d in (2, 5, 9)]
        qualifying, exclusions = qualifying_relief_logs(logs)
        assert len(qualifying) == 3
        assert all(count == 0 for count in exclusions.values())

    def test_excludes_starts(self):
        logs = [LogStub(2, games_started=1), LogStub(5, games_started=0)]
        qualifying, exclusions = qualifying_relief_logs(logs)
        assert len(qualifying) == 1
        assert exclusions['starts'] == 1

    def test_excludes_spring_training_and_postseason(self):
        logs = [
            LogStub(2, game_type='S'),
            LogStub(5, game_type='P'),
            LogStub(9, game_type='R'),
        ]
        qualifying, exclusions = qualifying_relief_logs(logs)
        assert len(qualifying) == 1
        assert exclusions['non_regular_season'] == 2

    def test_excludes_unknown_games_started(self):
        # Unknown start state stays unknown — never assumed to be relief.
        logs = [LogStub(2, games_started=None), LogStub(5, games_started=0)]
        qualifying, exclusions = qualifying_relief_logs(logs)
        assert len(qualifying) == 1
        assert exclusions['unknown_start'] == 1

    def test_excludes_rows_without_a_date(self):
        logs = [LogStub(2, game_date=False), LogStub(5)]
        logs[0].game_date = None
        qualifying, exclusions = qualifying_relief_logs(logs)
        assert len(qualifying) == 1
        assert exclusions['invalid_date'] == 1

    def test_role_window_is_unchanged_and_enforced(self, monkeypatch):
        # The observed-role log path keeps the existing 45-day window.
        assert ROLE_WINDOW_DAYS == 45
        captured = {}

        def fake_usage_logs(pitcher_ids, days=None, include_stale=None, reference_date=None):
            captured.update(days=days, include_stale=include_stale)
            return {}

        import services.pitcher_role_authority as authority
        monkeypatch.setattr(authority, 'usage_logs_by_pitcher', fake_usage_logs)
        role_logs_by_pitcher([1], reference_date=REF)
        assert captured == {'days': ROLE_WINDOW_DAYS, 'include_stale': False}


# ── Innings contamination ────────────────────────────────────────────────────

class TestStartInningsExclusion:
    def test_swingman_average_uses_relief_outings_only(self):
        # Starts average >= 5 IP; relief outings average 1 IP. The observed
        # role average must reflect only the one-inning relief work.
        logs = (
            [LogStub(d, innings=5.0, games_started=1) for d in (3, 10, 17)]
            + [LogStub(d, innings=1.0, games_started=0, leverage_index=0.9) for d in (2, 6, 12, 20)]
        )
        role, labels, public_read = _author(logs, eligibility={'status': 'role_ambiguous'})

        assert 'Average recent IP: 1.0' in role['evidence']
        assert '4 appearances in the recent window' in role['evidence']
        # Long starts cannot generate a long-relief/coverage read.
        assert role['role_key'] == 'middle_relief'
        assert public_read['key'] != 'coverage_arm'
        assert START_EXCLUDED_LIMITATION in role['limitations']
        assert '3 starting appearances excluded from the relief-role read' in role['evidence']


# ── Public role authority ────────────────────────────────────────────────────

class TestPublicRoleRead:
    def test_guarded_limited_read_owns_the_headline(self):
        role = {
            'role_key': 'late_high_leverage',
            'role': 'Late-Inning / High-Leverage Pattern',
            'confidence': 'high',
            'short_reason': 'Recent usage shows late-inning, high-leverage outings.',
            'evidence': ['9 appearances in the recent window', '1 save situation finish(es) recorded'],
            'limitations': ['Role is inferred from recent workload patterns only.'],
        }
        labels = {'role': {'kind': 'role', 'key': 'limited_read', 'label': 'Limited Read',
                           'source': 'backend:mixed_starter_reliever'}}
        public_read = author_public_role_read(role, labels)

        assert public_read['key'] == 'limited_read'
        assert public_read['label'] == 'Limited Read'
        assert public_read['headline'] == 'Limited Read'
        assert public_read['reason'] == GUARDED_PUBLIC_REASON
        assert public_read['confidence'] == 'low'
        # Evidence and limitations stay visible and auditable.
        assert public_read['evidence'] == role['evidence']
        assert public_read['limitations'] == role['limitations']
        # The rejected concrete role never headlines the public read.
        assert 'Late-Inning' not in public_read['headline']
        assert 'Late-Inning' not in (public_read['reason'] or '')

    def test_confirmed_concrete_roles_headline_their_pattern(self):
        cases = [
            ('late_high_leverage', 'Late-Inning / High-Leverage Pattern', 'trust_arm', 'Trusted Arm'),
            ('setup_bridge', 'Setup / Bridge Pattern', 'bridge_arm', 'Setup Arm'),
            ('middle_relief', 'Middle Relief Pattern', 'depth_arm', 'Middle Relief Arm'),
            ('long_multi_inning', 'Long Relief / Multi-Inning Pattern', 'coverage_arm', 'Coverage Arm'),
        ]
        for role_key, pattern, public_key, public_label in cases:
            role = {
                'role_key': role_key, 'role': pattern, 'confidence': 'high',
                'short_reason': 'reason', 'evidence': [], 'limitations': [],
            }
            labels = {'role': {'kind': 'role', 'key': public_key, 'label': public_label,
                               'source': f'backend:role_key:{role_key}'}}
            public_read = author_public_role_read(role, labels)
            assert public_read['key'] == public_key
            assert public_read['label'] == public_label
            assert public_read['headline'] == pattern

    def test_naturally_limited_roles_keep_their_specific_reason(self):
        role = {
            'role_key': 'insufficient_data', 'role': 'Insufficient Data', 'confidence': 'none',
            'short_reason': 'Not enough recent usage data to classify a role.',
            'evidence': [], 'limitations': [],
        }
        labels = {'role': {'kind': 'role', 'key': 'limited_read', 'label': 'Limited Read',
                           'source': 'backend:role_key:insufficient_data'}}
        public_read = author_public_role_read(role, labels)
        assert public_read['headline'] == 'Limited Read'
        assert public_read['reason'] == 'Not enough recent usage data to classify a role.'
        assert public_read['confidence'] == 'none'


# ── Implementation cases through the full authority ──────────────────────────

class TestAuthorityCases:
    def test_case_clean_setup_reliever(self):
        logs = [LogStub(d, innings=1.0, hold=(d in (2, 6)), leverage_index=1.2)
                for d in (2, 6, 11, 16, 22)]
        role, labels, public_read = _author(logs)
        assert role['role_key'] == 'setup_bridge'
        assert labels['role']['key'] == 'bridge_arm'
        assert public_read['label'] == 'Setup Arm'
        assert public_read['headline'] == 'Setup / Bridge Pattern'

    def test_case_clean_middle_reliever(self):
        logs = [LogStub(d, innings=1.0, leverage_index=0.9) for d in (2, 6, 11, 16, 22)]
        role, labels, public_read = _author(logs)
        assert role['role_key'] == 'middle_relief'
        assert public_read['key'] == 'depth_arm'
        assert public_read['label'] == 'Middle Relief Arm'
        assert public_read['headline'] == 'Middle Relief Pattern'

    def test_case_clean_coverage_reliever(self):
        logs = [LogStub(d, innings=2.0, leverage_index=0.7) for d in (2, 8, 15, 22)]
        role, labels, public_read = _author(logs)
        assert role['role_key'] == 'long_multi_inning'
        assert public_read['key'] == 'coverage_arm'
        assert public_read['headline'] == 'Long Relief / Multi-Inning Pattern'

    def test_case_opener_with_no_relief_appearances_fails_closed(self):
        logs = [LogStub(d, innings=1.0, games_started=1, leverage_index=1.1)
                for d in (2, 7, 12, 17, 22)]
        role, labels, public_read = _author(logs, eligibility={'status': 'role_ambiguous'})
        assert role['role_key'] == 'insufficient_data'
        assert public_read['key'] == 'limited_read'
        assert public_read['headline'] == 'Limited Read'
        assert public_read['label'] not in ('Setup Arm', 'Coverage Arm')
        assert START_EXCLUDED_LIMITATION in role['limitations']

    def test_case_spring_training_contamination_is_excluded(self):
        logs = (
            [LogStub(d, innings=1.0, save=(d == 40), hold=(d == 35), save_situation=(d == 40),
                     leverage_index=1.8, game_type='S') for d in (35, 40)]
            + [LogStub(d, innings=1.0, leverage_index=0.9) for d in (2, 6, 11, 16)]
        )
        role, labels, public_read = _author(logs)
        # Spring-training save/hold evidence never reaches the classifier.
        assert role['role_key'] == 'middle_relief'
        assert public_read['label'] == 'Middle Relief Arm'
        assert NON_REGULAR_SEASON_EXCLUDED_LIMITATION in role['limitations']

    def test_case_unknown_start_state_fails_closed_with_limitation(self):
        logs = (
            [LogStub(d, innings=1.0, games_started=None) for d in (2, 6, 11, 16)]
            + [LogStub(20, innings=1.0, games_started=0)]
        )
        role, labels, public_read = _author(logs)
        # One confirmed relief appearance cannot support a pattern.
        assert role['role_key'] == 'low_unclear'
        assert public_read['key'] == 'limited_read'
        assert public_read['headline'] == 'Limited Read'
        assert UNKNOWN_START_EXCLUDED_LIMITATION in role['limitations']
        assert UNKNOWN_START_EXCLUDED_LIMITATION in public_read['limitations']

    def test_case_paul_blackburn_style_conflict_resolves_to_one_limited_read(self):
        # Mixed start/relief usage, one save, one hold, longer outings, no
        # leverage-index data. The mixed guard rejects the concrete role; the
        # public read must present ONE Limited Read conclusion.
        logs = (
            [LogStub(d, innings=5.0, games_started=1) for d in (4, 11, 18, 25, 32)]
            + [LogStub(2, innings=1.2, save=True, save_situation=True)]
            + [LogStub(7, innings=1.1, hold=True)]
            + [LogStub(d, innings=1.5) for d in (13, 20, 27, 34, 40)]
        )
        role, labels, public_read = _author(logs, eligibility={'status': 'role_ambiguous'})

        # Diagnostic raw role may still be concrete (save/hold rules unchanged).
        assert role['role_key'] == 'late_high_leverage'
        # The public authority resolves to one Limited Read conclusion.
        assert labels['role']['key'] == 'limited_read'
        assert public_read['key'] == 'limited_read'
        assert public_read['label'] == 'Limited Read'
        assert public_read['headline'] == 'Limited Read'
        assert public_read['reason'] == GUARDED_PUBLIC_REASON
        assert 'Late-Inning' not in public_read['headline']
        # Evidence stays auditable: save, hold, innings, appearance counts.
        evidence_text = ' '.join(public_read['evidence'])
        assert 'save situation finish' in evidence_text
        assert 'hold(s) recorded' in evidence_text
        assert 'appearances in the recent window' in evidence_text
        assert 'starting appearances excluded' in evidence_text
