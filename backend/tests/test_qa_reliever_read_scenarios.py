from pathlib import Path
import re

import pytest
from flask import Flask

import models.composed_read  # noqa: F401
import models.dashboard_snapshot  # noqa: F401
import models.evidence_contract  # noqa: F401
import models.game_log  # noqa: F401
import models.legacy_read_audit  # noqa: F401
import models.pitcher  # noqa: F401
import models.player_transaction  # noqa: F401
import models.play_by_play_foundation  # noqa: F401
import models.roster_status_snapshot  # noqa: F401
import models.scheduled_game  # noqa: F401
import models.sync_run  # noqa: F401
from models.composed_read import ComposedRead, ComposedReadEvidenceCitation
from services.appearance_context_evidence import BASE_STATE_LIMITATION
from services.composed_read import validate_composed_read_integrity
from services.evidence_classification import validate_stored_evidence_integrity
from services.inherited_traffic_evidence import HBP_ROE_LIMITATION
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from tests.qa_scenarios import (
    SCENARIO_BUILDERS,
    SCENARIO_NAMES,
    conflict_state_evidence,
    il_placement_activation_timing,
    locked_band_consumption_attempt,
    mid_window_correction_recompute,
    opening_week_small_samples,
    relief_history_missing_membership,
    roster_snapshot_stale,
    rostered_cold_arm_gap,
    suspended_resumed_game,
)
from utils.db import db


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def app():
    flask_app = Flask('test_qa_reliever_read_scenarios')
    configure_test_database(flask_app)
    db.init_app(flask_app)
    with flask_app.app_context():
        create_test_schema(flask_app)
        yield flask_app
        db.session.remove()
        drop_test_schema(flask_app)


def test_mandatory_scenario_builder_names_are_registered():
    assert tuple(SCENARIO_BUILDERS) == SCENARIO_NAMES
    assert set(SCENARIO_BUILDERS) == {
        'opening_week_small_samples',
        'off_day_team',
        'doubleheader',
        'suspended_resumed_game',
        'incomplete_slate',
        'postponed_game',
        'trade_deadline_churn',
        'option_recall_churn',
        'il_placement_activation_timing',
        'september_call_up',
        'roster_snapshot_stale',
        'transaction_coverage_gap',
        'idle_team_trailing_windows',
        'relief_history_missing_membership',
        'rostered_cold_arm_gap',
        'missing_contributor_basis',
        'legacy_snapshot_missing',
        'composed_reads_missing',
        'conflict_state_evidence',
        'mid_window_correction_recompute',
        'locked_band_consumption_attempt',
        'legacy_factual_field_contradiction',
        'covered_window_zero_transactions',
    }


@pytest.mark.parametrize('builder', [
    opening_week_small_samples,
    suspended_resumed_game,
    roster_snapshot_stale,
    relief_history_missing_membership,
    conflict_state_evidence,
    il_placement_activation_timing,
])
def test_reliever_scenarios_match_expected_state_maps_and_citations(app, builder):
    with app.app_context():
        handle = builder()
        _assert_expected_reads(handle)
        assert validate_stored_evidence_integrity()['evidence_rows_checked'] == len(
            handle.evidence_object_ids
        )
        if handle.composed_read_ids:
            integrity = validate_composed_read_integrity()
            assert integrity['read_rows_checked'] == len(handle.composed_read_ids)
            assert integrity['citation_rows_checked'] >= len(handle.evidence_object_ids) - 1


def test_mandated_reliever_limitation_texts_are_verbatim(app):
    with app.app_context():
        handle = suspended_resumed_game()
        read = db.session.get(ComposedRead, handle.composed_read_ids[0])
        limitations = _component(read, 'recent_outing_component').limitations

    assert BASE_STATE_LIMITATION in limitations
    assert HBP_ROE_LIMITATION in limitations


def test_rostered_cold_arm_gap_creates_no_reliever_read(app):
    with app.app_context():
        handle = rostered_cold_arm_gap()
        pitcher_id = str(handle.pitcher_ids['primary'])
        assert ComposedRead.query.filter_by(
            read_type='reliever_daily_read',
            subject_id=pitcher_id,
        ).count() == 0
        assert handle.expected_state_map['expected_absences']['reliever_daily_read']['reason'] == (
            'cold_arm_gap_no_trailing_relief_appearance'
        )


def test_mid_window_correction_marks_read_and_audit_skip(app):
    with app.app_context():
        handle = mid_window_correction_recompute()
        read = db.session.get(ComposedRead, handle.composed_read_ids[0])

    assert read.recompute_status == ComposedRead.RECOMPUTE_NEEDED
    assert 'component_evidence_superseded' in read.recompute_reason_codes
    assert handle.expected_state_map['cascade'] == ('evidence', 'read', 'audit_skip')
    assert handle.expected_state_map['audit_run_status'] == 'skipped_reads_missing'


def test_locked_band_and_team_active_reliever_count_attempts_fail(app):
    with app.app_context():
        handle = locked_band_consumption_attempt()

    messages = ' '.join(handle.expected_state_map['expected_failures'])
    assert 'evidence_type_not_allowed' in messages
    assert 'appearance_entry_band' in messages
    assert 'team_active_reliever_count' in messages
    assert not handle.composed_read_ids


def test_no_completeness_as_quality_order_rank_or_filter_path():
    scanned = []
    forbidden_patterns = (
        r'order_by\([^)]*completeness_state',
        r'sorted\([^)]*completeness_state',
        r'\.sort\([^)]*completeness_state',
        r'rank[^=\n]*completeness_state',
    )
    for path in (
        REPO_ROOT / 'backend/services',
        REPO_ROOT / 'backend/scripts',
    ):
        for file in path.rglob('*.py'):
            text = file.read_text(encoding='utf-8', errors='ignore')
            scanned.append(file)
            for pattern in forbidden_patterns:
                assert not re.search(pattern, text, re.I | re.S), (pattern, file)
    assert scanned


def _assert_expected_reads(handle):
    for read_id, expected in handle.expected_state_map.get('reads', {}).items():
        read = db.session.get(ComposedRead, int(read_id))
        assert read is not None
        if 'read_type' in expected:
            assert read.read_type == expected['read_type']
        if 'completeness_state' in expected:
            assert read.completeness_state == expected['completeness_state']
        if 'recompute_status' in expected:
            assert read.recompute_status == expected['recompute_status']
        for code in expected.get('reason_codes', ()):
            assert code in (read.reason_codes or [])
        for limitation in expected.get('limitations', ()):
            assert _read_has_limitation(read, limitation)
        components = {component.component_name: component for component in read.components}
        for name, state in expected.get('component_states', {}).items():
            assert components[name].component_state == state
        for component in read.components:
            for citation in component.evidence_citations:
                assert isinstance(citation, ComposedReadEvidenceCitation)
                assert citation.evidence_object is not None
                assert citation.evidence_object.citations
                assert all(
                    (source.provenance or {}).get('source')
                    for source in citation.evidence_object.citations
                )


def _component(read, name):
    return [component for component in read.components if component.component_name == name][0]


def _read_has_limitation(read, limitation):
    values = list(read.limitations or [])
    return limitation in values or any(value.endswith(f':{limitation}') for value in values)
