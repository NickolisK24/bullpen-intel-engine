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
from models.composed_read import ComposedRead
from services.composed_read import validate_composed_read_integrity
from services.evidence_classification import validate_stored_evidence_integrity
from services.roster_depth_evidence import PITCHER_SCOPED_SNAPSHOT_LIMITATION
from services.starter_exposure_evidence import (
    APPEARANCES_NOT_DISTINCT_ARMS_LIMITATION,
    SCHEDULE_SUBJECT_TO_CHANGE_LIMITATION,
)
from services.team_daily_read import assert_roster_churn_content_allowed
from services.team_relief_composition_evidence import BASIS_DISCLAIMER
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from tests.qa_scenarios import (
    covered_window_zero_transactions,
    doubleheader,
    idle_team_trailing_windows,
    incomplete_slate,
    missing_contributor_basis,
    off_day_team,
    option_recall_churn,
    postponed_game,
    september_call_up,
    trade_deadline_churn,
    transaction_coverage_gap,
)
from utils.db import db


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def app():
    flask_app = Flask('test_qa_team_read_scenarios')
    configure_test_database(flask_app)
    db.init_app(flask_app)
    with flask_app.app_context():
        create_test_schema(flask_app)
        yield flask_app
        db.session.remove()
        drop_test_schema(flask_app)


@pytest.mark.parametrize('builder', [
    off_day_team,
    doubleheader,
    incomplete_slate,
    postponed_game,
    trade_deadline_churn,
    option_recall_churn,
    september_call_up,
    transaction_coverage_gap,
    idle_team_trailing_windows,
    missing_contributor_basis,
    covered_window_zero_transactions,
])
def test_team_scenarios_match_expected_state_maps_and_citations(app, builder):
    with app.app_context():
        handle = builder()
        _assert_expected_reads(handle)
        assert validate_stored_evidence_integrity()['evidence_rows_checked'] == len(
            handle.evidence_object_ids
        )
        if handle.composed_read_ids:
            integrity = validate_composed_read_integrity()
            assert integrity['read_rows_checked'] == len(handle.composed_read_ids)
            assert integrity['citation_rows_checked'] >= 2


def test_contributor_denominator_disclaimer_on_every_team_component(app):
    with app.app_context():
        handles = [off_day_team(), missing_contributor_basis()]
        reads = [
            db.session.get(ComposedRead, handle.composed_read_ids[0])
            for handle in handles
        ]

    for read in reads:
        component = _component(read, 'contributor_composition_component')
        assert BASIS_DISCLAIMER in component.limitations


def test_off_day_team_calendar_absence_does_not_degrade(app):
    with app.app_context():
        handle = off_day_team()
        read = db.session.get(ComposedRead, handle.composed_read_ids[0])

    assert read.completeness_state == ComposedRead.COMPLETENESS_COMPLETE
    assert read.component_summary['calendar_component']['state'] == 'absent'


def test_missing_contributor_basis_is_unknown_not_deleted(app):
    with app.app_context():
        handle = missing_contributor_basis()
        read = db.session.get(ComposedRead, handle.composed_read_ids[0])

    assert read is not None
    assert read.completeness_state == ComposedRead.COMPLETENESS_UNKNOWN
    assert (
        read.component_summary['contributor_composition_component']['state']
        == ComposedRead.COMPLETENESS_UNKNOWN
    )


def test_mandated_team_limitation_texts_are_verbatim(app):
    with app.app_context():
        doubleheader_handle = doubleheader()
        postponed_handle = postponed_game()
        churn_handle = trade_deadline_churn()
        doubleheader_read = db.session.get(ComposedRead, doubleheader_handle.composed_read_ids[0])
        postponed_read = db.session.get(ComposedRead, postponed_handle.composed_read_ids[0])
        churn_read = db.session.get(ComposedRead, churn_handle.composed_read_ids[0])

    assert APPEARANCES_NOT_DISTINCT_ARMS_LIMITATION in _component(
        doubleheader_read,
        'exposure_component',
    ).limitations
    assert SCHEDULE_SUBJECT_TO_CHANGE_LIMITATION in _component(
        postponed_read,
        'calendar_component',
    ).limitations
    assert PITCHER_SCOPED_SNAPSHOT_LIMITATION in _component(
        churn_read,
        'roster_churn_component',
    ).limitations


def test_roster_churn_language_negatives_and_scenarios_are_clean(app):
    for text in (
        'thin staff',
        'deep group',
        'depth issue',
        'available group',
        'quality problem',
    ):
        with pytest.raises(AssertionError):
            assert_roster_churn_content_allowed(text)

    with app.app_context():
        handles = [trade_deadline_churn(), option_recall_churn(), transaction_coverage_gap()]
        reads = [db.session.get(ComposedRead, handle.composed_read_ids[0]) for handle in handles]

    for read in reads:
        component = _component(read, 'roster_churn_component')
        text = ' '.join((component.reason_codes or []) + (component.limitations or []))
        assert_roster_churn_content_allowed(text)


def test_team_scenario_content_does_not_rank_or_filter_by_completeness_state():
    source = (REPO_ROOT / 'backend/tests/qa_scenarios/builders.py').read_text(
        encoding='utf-8'
    )
    assert not re.search(r'(rank|order|sort|filter)[^\n]{0,80}completeness_state', source, re.I)


def _assert_expected_reads(handle):
    for read_id, expected in handle.expected_state_map.get('reads', {}).items():
        read = db.session.get(ComposedRead, int(read_id))
        assert read is not None
        if 'read_type' in expected:
            assert read.read_type == expected['read_type']
        if 'completeness_state' in expected:
            assert read.completeness_state == expected['completeness_state']
        for code in expected.get('reason_codes', ()):
            assert code in (read.reason_codes or [])
        for limitation in expected.get('limitations', ()):
            assert _read_has_limitation(read, limitation)
        components = {component.component_name: component for component in read.components}
        for name, state in expected.get('component_states', {}).items():
            assert components[name].component_state == state


def _component(read, name):
    return [component for component in read.components if component.component_name == name][0]


def _read_has_limitation(read, limitation):
    values = list(read.limitations or [])
    return limitation in values or any(value.endswith(f':{limitation}') for value in values)
