from datetime import date, datetime, timedelta
from pathlib import Path
import logging

import pytest
from flask import Flask

import models.evidence_contract  # noqa: F401
import models.pitcher  # noqa: F401
import models.player_transaction  # noqa: F401
import models.roster_status_snapshot  # noqa: F401
import models.sync_failure  # noqa: F401
import models.sync_run  # noqa: F401
from models.evidence_contract import EvidenceObject
from models.pitcher import Pitcher
from models.player_transaction import PlayerTransaction, PlayerTransactionSyncWindow
from models.roster_status_snapshot import RosterStatusSnapshot
from models.sync_failure import SyncFailure
from models.sync_run import SyncRun
from services import sync as sync_service
from services import sync_metadata
import services.roster_depth_evidence as roster_service
from services.evidence_language import EvidenceLanguageError
from services.evidence_rules import (
    ClaimTemplate,
    ClaimTemplateRegistry,
    EvidenceRule,
    EvidenceRuleError,
    EvidenceRuleRegistry,
)
from services.roster_depth_evidence import (
    PITCHER_IL_ACTIVATION_CONTEXT_RULE_ID,
    PITCHER_IL_PLACEMENT_CONTEXT_RULE_ID,
    REASON_CHANGE_UNEXPLAINED,
    REASON_NO_PUBLIC_IL_FACT,
    REASON_RELIEVER_PARTITION_UNAVAILABLE,
    REASON_SNAPSHOT_MEMBERSHIP_UNKNOWN,
    REASON_SNAPSHOT_STALE,
    REASON_TRANSACTION_TYPE_UNKNOWN,
    REASON_TRANSACTION_WINDOW_UNCOVERED,
    ROSTER_DEPTH_RULE_IDS,
    RULE_VERSION,
    TEAM_ACTIVE_PITCHER_CENSUS_RULE_ID,
    TEAM_ACTIVE_RELIEVER_COUNT_RULE_ID,
    TEAM_DEPTH_DELTA_DAILY_RULE_ID,
    TEAM_OPTION_RECALL_CHURN_RULE_ID,
    TEAM_PUBLIC_IL_COUNT_RULE_ID,
    TEAM_ROSTER_CHANGES_EXPLAINED_RULE_ID,
    TEAM_ROSTER_CHANGES_UNEXPLAINED_RULE_ID,
    TEAM_ROSTER_MOVEMENT_CHURN_RULE_ID,
    TEAM_ROSTER_SNAPSHOT_STATE_RULE_ID,
    TEAM_TRANSACTION_ALIGNMENT_STATE_RULE_ID,
    TEAM_TRANSACTION_CATEGORY_COUNTS_WINDOW_RULE_ID,
    TEAM_TRANSACTION_CHURN_WINDOW_RULE_ID,
    _register_roster_depth_rule,
    _register_roster_depth_template,
    build_roster_depth_evidence,
    mark_player_transaction_correction_for_roster_depth,
    mark_roster_status_snapshot_correction_for_roster_depth,
    rebuild_marked_roster_depth_evidence,
    register_roster_depth_rules,
)
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCT_DATE = date(2026, 7, 4)


@pytest.fixture
def app(monkeypatch, tmp_path):
    monkeypatch.setattr(sync_service, 'STATUS_FILE', tmp_path / 'sync_status.json')
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


def _sync_run():
    run = SyncRun(
        job_name='phase0d_roster_depth_test',
        started_at=datetime(2026, 7, 4, 12, 0, 0),
        completed_at=datetime(2026, 7, 4, 12, 0, 1),
        status='success',
        stage='complete',
        source='test',
    )
    db.session.add(run)
    db.session.flush()
    return run


def _fixture_sync_run_id():
    existing = SyncRun.query.filter_by(
        job_name='phase0d_roster_depth_fixture',
        source='test_fixture',
    ).first()
    if existing is not None:
        return existing.id
    run = SyncRun(
        job_name='phase0d_roster_depth_fixture',
        started_at=datetime(2026, 7, 4, 9, 0, 0),
        completed_at=datetime(2026, 7, 4, 9, 0, 1),
        status='success',
        stage='fixture',
        source='test_fixture',
    )
    db.session.add(run)
    db.session.flush()
    return run.id


def _pitcher(pid, mlb_id, name, team_id=116):
    row = Pitcher(
        id=pid,
        mlb_id=mlb_id,
        full_name=name,
        team_id=team_id,
        team_abbreviation=f'T{team_id}',
        position='P',
        active=True,
    )
    db.session.add(row)
    db.session.flush()
    return row


def _snapshot(
    pitcher,
    *,
    team_id=None,
    snapshot_date=PRODUCT_DATE,
    roster_status='active',
    active_roster=True,
    two_way=False,
    source='test_roster_snapshot',
):
    row = RosterStatusSnapshot(
        pitcher_id=pitcher.id,
        mlb_id=pitcher.mlb_id,
        team_id=team_id if team_id is not None else pitcher.team_id,
        snapshot_date=snapshot_date,
        roster_status=roster_status,
        active_roster=active_roster,
        forty_man_roster=True,
        position_code='P',
        position_name='Pitcher',
        position_type='Pitcher',
        two_way_eligible=two_way,
        roster_status_raw='stored',
        roster_status_raw_code='stored',
        roster_status_raw_description='stored',
        source=source,
        sync_run_id=_fixture_sync_run_id(),
        first_seen_at=datetime(2026, 7, 4, 10, 0, 0),
        created_at=datetime(2026, 7, 4, 10, 0, 0),
        updated_at=datetime(2026, 7, 4, 10, 0, 0),
    )
    db.session.add(row)
    db.session.flush()
    return row


def _transaction(
    key,
    pitcher,
    *,
    days_ago=0,
    from_team_id=None,
    to_team_id=None,
    category='option',
    type_code='OPTION',
    il_placement=False,
    il_activation=False,
    il_list_type=None,
    retroactive_date=None,
    alignment='aligned',
    eligible=True,
):
    row = PlayerTransaction(
        transaction_key=key,
        transaction_id=key,
        pitcher_id=pitcher.id if pitcher else None,
        player_mlb_id=pitcher.mlb_id if pitcher else 999999,
        from_team_id=from_team_id,
        to_team_id=to_team_id,
        transaction_date=PRODUCT_DATE - timedelta(days=days_ago),
        effective_date=PRODUCT_DATE - timedelta(days=days_ago),
        resolution_date=None,
        transaction_type_code=type_code,
        normalized_category=category,
        is_il_placement=il_placement,
        is_il_activation=il_activation,
        il_list_type=il_list_type,
        retroactive_date=retroactive_date,
        roster_snapshot_alignment=alignment,
        alignment_reason_code='stored_alignment_fixture',
        explanatory_linkage_eligible=eligible,
        source='test_transactions',
        source_endpoint='/transactions',
        source_query_start_date=PRODUCT_DATE - timedelta(days=13),
        source_query_end_date=PRODUCT_DATE,
        sync_run_id=_fixture_sync_run_id(),
        first_seen_at=datetime(2026, 7, 4, 10, 0, 0),
        created_at=datetime(2026, 7, 4, 10, 0, 0),
        updated_at=datetime(2026, 7, 4, 10, 0, 0),
    )
    db.session.add(row)
    db.session.flush()
    return row


def _coverage(start_days_ago=13, end_days_ago=0, status='success'):
    row = PlayerTransactionSyncWindow(
        source='test_transactions',
        source_endpoint='/transactions',
        source_query_start_date=PRODUCT_DATE - timedelta(days=start_days_ago),
        source_query_end_date=PRODUCT_DATE - timedelta(days=end_days_ago),
        attempted_at=datetime(2026, 7, 4, 10, 0, 0),
        successful_at=datetime(2026, 7, 4, 10, 0, 0) if status == 'success' else None,
        status=status,
        records_fetched=3,
        records_stored=3,
        records_created=3,
        records_corrected=0,
        records_unchanged=0,
        unknown_type_count=0,
        alignment_unknown_count=0,
        alignment_misaligned_count=0,
        alignment_no_snapshot_count=0,
        records_failed=0 if status == 'success' else 1,
        sync_run_id=_fixture_sync_run_id(),
        created_at=datetime(2026, 7, 4, 10, 0, 0),
    )
    db.session.add(row)
    db.session.flush()
    return row


def _row(rule_id, *, team_id=116, subject_key_contains=None, subject_type='team'):
    query = EvidenceObject.query.filter_by(rule_id=rule_id, subject_type=subject_type)
    if subject_type == 'team':
        query = query.filter_by(subject_id=str(team_id))
    if subject_key_contains:
        query = query.filter(EvidenceObject.subject_key.contains(subject_key_contains))
    return query.one()


def test_registration_guards_14_rules_unknown_reliever_and_language():
    registry, templates = register_roster_depth_rules(
        registry=EvidenceRuleRegistry(),
        template_registry=ClaimTemplateRegistry(),
    )
    rules = registry.all_rules()

    assert [rule.rule_id for rule in rules] == sorted(ROSTER_DEPTH_RULE_IDS)
    assert len(rules) == 14
    assert {rule.rule_version for rule in rules} == {RULE_VERSION}
    assert {rule.posture_default for rule in rules} == {EvidenceObject.POSTURE_INTERNAL_ONLY}
    assert registry.get(TEAM_ACTIVE_RELIEVER_COUNT_RULE_ID).allowed_completeness == ('unknown',)
    assert len(templates._templates) == 19

    with pytest.raises(EvidenceRuleError):
        _register_roster_depth_rule(
            EvidenceRuleRegistry(),
            EvidenceRule(
                rule_id='bad_public_roster_rule',
                rule_version=1,
                evidence_type='bad_public_roster_rule',
                plain_language_definition='A neutral roster fact.',
                required_input_families=('roster_status_snapshots',),
                required_cited_fields=('roster_status_snapshots.snapshot_date',),
                posture_default=EvidenceObject.POSTURE_PUBLIC_CANDIDATE,
            ),
        )

    for text in (
        'healthy',
        'injury-free',
        'full strength',
        'nobody is hurt',
        'available',
        'cleared',
        'ready',
        'recovered',
        'thin',
        'depleted',
        'overworked',
        'pressure',
        'fatigue',
    ):
        with pytest.raises(EvidenceLanguageError):
            _register_roster_depth_template(
                ClaimTemplateRegistry(),
                ClaimTemplate(
                    template_id=f'bad_{text.replace(" ", "_")}',
                    template_version=1,
                    template_text=text,
                ),
            )


def test_census_truth_table_two_way_partial_stale_and_reliever_unknown(app, monkeypatch):
    with app.app_context():
        p1 = _pitcher(1, 101, 'Known One')
        p2 = _pitcher(2, 102, 'Two Way')
        p3 = _pitcher(3, 103, 'Unknown Membership')
        p4 = _pitcher(4, 104, 'Stale Team', team_id=117)
        _snapshot(p1)
        _snapshot(p2, two_way=True)
        _snapshot(p3, active_roster=None)
        _snapshot(p4, team_id=117, snapshot_date=PRODUCT_DATE - timedelta(days=1))
        _coverage()

        build_roster_depth_evidence(PRODUCT_DATE)
        census = _row(TEAM_ACTIVE_PITCHER_CENSUS_RULE_ID)
        reliever = _row(TEAM_ACTIVE_RELIEVER_COUNT_RULE_ID)
        stale = _row(TEAM_ACTIVE_PITCHER_CENSUS_RULE_ID, team_id=117)

        assert census.completeness_state == EvidenceObject.COMPLETENESS_PARTIAL
        assert 'At least 2 active pitchers' in census.rendered_claim
        assert '1 with unknown membership' in census.rendered_claim
        assert REASON_SNAPSHOT_MEMBERSHIP_UNKNOWN in census.reason_codes
        assert census.computation_trace['two_way_count'] == 1
        assert reliever.completeness_state == EvidenceObject.COMPLETENESS_UNKNOWN
        assert REASON_RELIEVER_PARTITION_UNAVAILABLE in reliever.reason_codes
        assert stale.completeness_state == EvidenceObject.COMPLETENESS_UNKNOWN
        assert REASON_SNAPSHOT_STALE in stale.reason_codes

        rendered = ' '.join(row.rendered_claim.lower() for row in EvidenceObject.query.all())
        for forbidden in ('available', 'healthy', 'ready', 'pressure', 'fatigue'):
            assert forbidden not in rendered

        monkeypatch.setattr(
            'services.roster_depth_evidence._roster_source_state',
            lambda _date: {
                'status': 'degraded',
                'reason_codes': ['snapshot_cache_divergence'],
                'cache_divergence_count': 1,
            },
        )
        build_roster_depth_evidence(PRODUCT_DATE)
        degraded = _row(TEAM_ACTIVE_PITCHER_CENSUS_RULE_ID)
        assert degraded.completeness_state == EvidenceObject.COMPLETENESS_UNKNOWN
        assert 'snapshot_cache_divergence' in degraded.reason_codes


def test_il_rules_safe_phrasing_snapshot_precedence_and_no_absence_object(app):
    with app.app_context():
        p1 = _pitcher(10, 201, 'IL Pitcher')
        p2 = _pitcher(11, 202, 'Activation Pitcher')
        p3 = _pitcher(12, 203, 'Transaction Only')
        _snapshot(p1, roster_status='il', active_roster=False)
        _snapshot(p2, roster_status='active', active_roster=True)
        _snapshot(p3, roster_status='active', active_roster=True)
        _coverage()
        _transaction(
            'tx-il',
            p1,
            to_team_id=116,
            category='il_placement',
            type_code='IL_15',
            il_placement=True,
            il_list_type='15_day',
            retroactive_date=date(2026, 6, 26),
        )
        _transaction(
            'tx-act',
            p2,
            to_team_id=116,
            category='il_activation',
            type_code='IL_ACTIVATION',
            il_activation=True,
            il_list_type='15_day',
        )
        _transaction(
            'tx-il-no-current',
            p3,
            to_team_id=116,
            category='il_placement',
            type_code='IL_15',
            il_placement=True,
            il_list_type='15_day',
            alignment='no_snapshot',
            eligible=False,
        )

        build_roster_depth_evidence(PRODUCT_DATE)
        placement = _row(
            PITCHER_IL_PLACEMENT_CONTEXT_RULE_ID,
            subject_type='pitcher',
            subject_key_contains='transaction:tx-il:il-placement',
        )
        activation = _row(PITCHER_IL_ACTIVATION_CONTEXT_RULE_ID, subject_type='pitcher', subject_key_contains='tx-act')
        team_count = _row(TEAM_PUBLIC_IL_COUNT_RULE_ID)
        alignment = _row(TEAM_TRANSACTION_ALIGNMENT_STATE_RULE_ID, subject_key_contains='window-7')

        assert placement.rendered_claim == (
            'On the 15-day IL per MLB transaction data, placed 2026-07-04, '
            'retroactive to 2026-06-26.'
        )
        assert activation.rendered_claim == (
            'Activated from the 15-day IL per MLB transaction data on 2026-07-04.'
        )
        assert team_count.rendered_claim.startswith('1 pitchers on the IL per current snapshot')
        assert REASON_NO_PUBLIC_IL_FACT not in team_count.reason_codes
        assert '1 no-snapshot' in alignment.rendered_claim
        assert not EvidenceObject.query.filter(EvidenceObject.rendered_claim.contains('not on IL')).all()

        rendered = ' '.join(row.rendered_claim.lower() for row in EvidenceObject.query.all())
        for forbidden in ('healthy', 'severity', 'timetable', 'recovered', 'available'):
            assert forbidden not in rendered


def test_snapshot_il_without_transaction_counts_and_notes_missing_link(app):
    with app.app_context():
        p1 = _pitcher(20, 301, 'Snapshot IL')
        _snapshot(p1, roster_status='il', active_roster=False)
        _coverage()

        build_roster_depth_evidence(PRODUCT_DATE)
        team_count = _row(TEAM_PUBLIC_IL_COUNT_RULE_ID)

        assert team_count.completeness_state == EvidenceObject.COMPLETENESS_COMPLETE
        assert team_count.rendered_claim.startswith('1 pitchers on the IL per current snapshot')
        assert REASON_NO_PUBLIC_IL_FACT in team_count.reason_codes


def test_churn_windows_coverage_categories_cross_team_repeats_and_alignment(app):
    with app.app_context():
        p1 = _pitcher(30, 401, 'Option Repeat')
        p2 = _pitcher(31, 402, 'Trade Pitcher')
        p3 = _pitcher(32, 403, 'Unknown Type')
        _snapshot(p1)
        _snapshot(p2)
        _snapshot(p3)
        _coverage()
        _transaction('tx-option-1', p1, to_team_id=116, category='option', type_code='OPTION')
        _transaction('tx-recall-1', p1, to_team_id=116, category='recall', type_code='RECALL')
        _transaction('tx-trade', p2, from_team_id=116, to_team_id=117, category='trade', type_code='TRADE')
        _transaction(
            'tx-unknown',
            p3,
            to_team_id=116,
            category='unknown',
            type_code='???',
            alignment='unknown',
            eligible=False,
        )

        build_roster_depth_evidence(PRODUCT_DATE)
        churn = _row(TEAM_TRANSACTION_CHURN_WINDOW_RULE_ID, subject_key_contains='window-7')
        categories = _row(TEAM_TRANSACTION_CATEGORY_COUNTS_WINDOW_RULE_ID, subject_key_contains='window-7')
        option = _row(TEAM_OPTION_RECALL_CHURN_RULE_ID, subject_key_contains='window-7')
        movement = _row(TEAM_ROSTER_MOVEMENT_CHURN_RULE_ID, subject_key_contains='window-7')
        alignment = _row(TEAM_TRANSACTION_ALIGNMENT_STATE_RULE_ID, subject_key_contains='window-7')
        trade_for_117 = _row(TEAM_TRANSACTION_CHURN_WINDOW_RULE_ID, team_id=117, subject_key_contains='window-7')

        assert churn.completeness_state == EvidenceObject.COMPLETENESS_COMPLETE
        assert '4 transactions touching team 116' in churn.rendered_claim
        assert '1 unknown-type' in categories.rendered_claim
        assert REASON_TRANSACTION_TYPE_UNKNOWN in categories.reason_codes
        assert '1 options and 1 recalls' in option.rendered_claim
        assert '1 players have more than one option or recall event' in option.rendered_claim
        assert '1 roster-movement transactions' in movement.rendered_claim
        assert '1 unknown alignment' in alignment.rendered_claim
        assert '1 transactions touching team 117' in trade_for_117.rendered_claim


def test_uncovered_transaction_window_degrades_without_silent_complete(app):
    with app.app_context():
        p1 = _pitcher(40, 501, 'Partial Coverage')
        _snapshot(p1)
        _coverage(start_days_ago=13, end_days_ago=1, status='success')
        _transaction('tx-covered-subtotal', p1, to_team_id=116, category='option', type_code='OPTION')

        build_roster_depth_evidence(PRODUCT_DATE)
        churn = _row(TEAM_TRANSACTION_CHURN_WINDOW_RULE_ID, subject_key_contains='window-7')

        assert churn.completeness_state == EvidenceObject.COMPLETENESS_PARTIAL
        assert churn.rendered_claim.startswith('At least 1 transactions')
        assert REASON_TRANSACTION_WINDOW_UNCOVERED in churn.reason_codes
        assert any(c.citation_role == 'window_coverage' for c in churn.citations)
        assert churn.computation_trace['transaction_window_coverage_checks']['uncovered_ranges']


def test_depth_delta_explained_unexplained_and_membership_unknown(app):
    with app.app_context():
        p1 = _pitcher(50, 601, 'Holdover')
        p2 = _pitcher(51, 602, 'Explained Add')
        p3 = _pitcher(52, 603, 'Unexplained Remove')
        p4 = _pitcher(53, 604, 'Unknown Row', team_id=117)
        _snapshot(p1, snapshot_date=PRODUCT_DATE - timedelta(days=1))
        _snapshot(p3, snapshot_date=PRODUCT_DATE - timedelta(days=1))
        _snapshot(p1, snapshot_date=PRODUCT_DATE)
        _snapshot(p2, snapshot_date=PRODUCT_DATE)
        _snapshot(p4, team_id=117, snapshot_date=PRODUCT_DATE - timedelta(days=1), active_roster=None)
        _snapshot(p4, team_id=117, snapshot_date=PRODUCT_DATE)
        _coverage()
        _transaction(
            'tx-explained-add',
            p2,
            to_team_id=116,
            category='recall',
            type_code='RECALL',
            alignment='aligned',
            eligible=True,
        )

        build_roster_depth_evidence(PRODUCT_DATE)
        delta = _row(TEAM_DEPTH_DELTA_DAILY_RULE_ID)
        explained = _row(TEAM_ROSTER_CHANGES_EXPLAINED_RULE_ID)
        unexplained = _row(TEAM_ROSTER_CHANGES_UNEXPLAINED_RULE_ID)
        unknown_delta = _row(TEAM_DEPTH_DELTA_DAILY_RULE_ID, team_id=117)

        assert 'changed by +0' in delta.rendered_claim
        assert 'Explained Add added' in explained.rendered_claim
        assert explained.computation_trace['local_alignment_recomputed'] is False
        assert 'Unexplained Remove removed' in unexplained.rendered_claim
        assert REASON_CHANGE_UNEXPLAINED in unexplained.reason_codes
        assert any(c.citation_role == 'window_coverage' for c in unexplained.citations)
        assert unknown_delta.completeness_state == EvidenceObject.COMPLETENESS_UNKNOWN
        assert REASON_SNAPSHOT_MEMBERSHIP_UNKNOWN in unknown_delta.reason_codes
        assert unknown_delta.computation_trace['unknown_membership_exclusions']


def test_missing_prior_snapshot_delta_unknown(app):
    with app.app_context():
        p1 = _pitcher(60, 701, 'No Prior')
        _snapshot(p1)
        _coverage()

        build_roster_depth_evidence(PRODUCT_DATE)
        delta = _row(TEAM_DEPTH_DELTA_DAILY_RULE_ID)

        assert delta.completeness_state == EvidenceObject.COMPLETENESS_UNKNOWN
        assert 'delta_prior_snapshot_unavailable' in delta.reason_codes


def test_recompute_snapshot_and_transaction_corrections_are_bounded_idempotent(app):
    with app.app_context():
        run = _sync_run()
        p1 = _pitcher(70, 801, 'Recompute Target')
        p2 = _pitcher(71, 802, 'Recompute Other', team_id=117)
        target_snapshot = _snapshot(p1)
        _snapshot(p2, team_id=117)
        _coverage()
        target_tx = _transaction('tx-recompute-target', p1, to_team_id=116, category='option')
        _transaction('tx-recompute-other', p2, to_team_id=117, category='option')
        build_roster_depth_evidence(PRODUCT_DATE, sync_run_id=run.id)
        first_count = EvidenceObject.query.filter(EvidenceObject.rule_id.in_(ROSTER_DEPTH_RULE_IDS)).count()
        build_roster_depth_evidence(PRODUCT_DATE, sync_run_id=run.id)
        second_count = EvidenceObject.query.filter(EvidenceObject.rule_id.in_(ROSTER_DEPTH_RULE_IDS)).count()

        target_census = _row(TEAM_ACTIVE_PITCHER_CENSUS_RULE_ID)
        unrelated_census = _row(TEAM_ACTIVE_PITCHER_CENSUS_RULE_ID, team_id=117)
        unrelated_updated_at = unrelated_census.updated_at
        target_snapshot.active_roster = None
        marked_snapshot = mark_roster_status_snapshot_correction_for_roster_depth(
            target_snapshot,
            sync_run_id=run.id,
            batch_size=100,
        )
        marked_tx = mark_player_transaction_correction_for_roster_depth(
            target_tx,
            sync_run_id=run.id,
            batch_size=100,
        )
        rebuilt = rebuild_marked_roster_depth_evidence(sync_run_id=run.id)
        target_after = db.session.get(EvidenceObject, target_census.id)
        unrelated_after = db.session.get(EvidenceObject, unrelated_census.id)

        assert first_count == second_count
        assert target_census.id in marked_snapshot['evidence_ids']
        assert marked_snapshot['marked_count'] <= 100
        assert marked_tx['marked_count'] <= 100
        assert rebuilt['objects_rebuilt'] >= 1
        assert target_after.recompute_status == EvidenceObject.RECOMPUTE_CURRENT
        assert target_after.computation_trace['superseded_prior']['rendered_claim']
        assert unrelated_after.updated_at == unrelated_updated_at


def test_roster_depth_build_batches_upserts_and_logs_phase_counts(app, monkeypatch, caplog):
    with app.app_context():
        run = _sync_run()
        p1 = _pitcher(72, 872, 'Batch Target')
        p2 = _pitcher(73, 873, 'Batch Other', team_id=117)
        _snapshot(p1)
        _snapshot(p2, team_id=117)
        _coverage()
        _transaction('tx-batch-target', p1, to_team_id=116, category='option')

        monkeypatch.setattr(
            roster_service,
            '_upsert_evidence',
            lambda *_args, **_kwargs: pytest.fail('per-object roster-depth upsert was used'),
        )

        with caplog.at_level(logging.INFO, logger='baseballos.daily_sync'):
            result = build_roster_depth_evidence(PRODUCT_DATE, sync_run_id=run.id)
        messages = [record.getMessage() for record in caplog.records]

    assert result['status'] == 'built'
    assert result['objects_built'] > 0
    assert result['objects_created'] == result['objects_built']
    assert result['elapsed_ms'] >= 0
    assert any(
        'Roster depth context loaded:' in message
        and 'teams=' in message
        and 'transactions=' in message
        and 'elapsed_ms=' in message
        for message in messages
    )
    assert any(
        'Roster depth persistence completed:' in message
        and 'objects_built=' in message
        and 'objects_created=' in message
        and 'elapsed_ms=' in message
        for message in messages
    )
    assert any(
        'Roster depth build completed:' in message
        and 'teams_considered=' in message
        and 'elapsed_ms=' in message
        for message in messages
    )


def test_sync_stage_fail_soft_kill_switch_and_public_payload_shape(app, monkeypatch, caplog):
    with app.app_context():
        run = _sync_run()
        before = set(sync_metadata.build_sync_status_payload().keys())
        p1 = _pitcher(80, 901, 'Sync Pitcher')
        _snapshot(p1)
        _coverage()
        result = sync_service._safe_build_workload_recovery_evidence_stage(
            [PRODUCT_DATE],
            sync_run_id=run.id,
            source='test',
            run_logger=logging.getLogger('baseballos.daily_sync'),
        )
        after = set(sync_metadata.build_sync_status_payload().keys())

        def boom(*args, **kwargs):
            raise RuntimeError('roster depth stage exploded')

        import services.roster_depth_evidence as roster_service
        monkeypatch.setattr(roster_service, 'build_roster_depth_evidence', boom)
        with caplog.at_level(logging.WARNING, logger='baseballos.daily_sync'):
            failed = sync_service._safe_build_workload_recovery_evidence_stage(
                [PRODUCT_DATE],
                sync_run_id=run.id,
                source='test',
                run_logger=logging.getLogger('baseballos.daily_sync'),
            )
        failure = SyncFailure.query.order_by(SyncFailure.id.desc()).first()

        monkeypatch.setenv('PHASE0D_EVIDENCE_BUILD', 'false')
        monkeypatch.setattr(
            roster_service,
            'build_roster_depth_evidence',
            lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('should not run')),
        )
        skipped = sync_service._safe_build_workload_recovery_evidence_stage(
            [PRODUCT_DATE],
            sync_run_id=run.id,
            source='test',
            run_logger=logging.getLogger('baseballos.daily_sync'),
        )

    assert result['status'] == 'built'
    assert result['roster_depth_builds'][0]['objects_built'] > 0
    assert after == before
    assert failed['status'] == 'failed'
    assert failure.entity_type == sync_service.WORKLOAD_EVIDENCE_FAILURE_ENTITY_TYPE
    assert 'sync will continue' in caplog.text
    assert skipped['status'] == 'skipped'
    assert skipped['reason'] == 'disabled'


def test_public_isolation_and_service_does_not_read_blocked_sources(app):
    service_path = REPO_ROOT / 'backend/services/roster_depth_evidence.py'
    service_text = service_path.read_text(encoding='utf-8')
    blocked_service_imports = (
        'models.game_log',
        'GameLog',
        'models.play_by_play_foundation',
        'GamePlayByPlayEvent',
        'PlayByPlayProcessedGame',
        'Statcast',
    )
    for needle in blocked_service_imports:
        assert needle not in service_text
    assert 'transaction_description' not in service_text
    assert 'injury_description' not in service_text
    assert 'raw_transaction' not in service_text
    assert 'local_alignment_recomputed' in service_text

    public_paths = (
        REPO_ROOT / 'backend/api/bullpen.py',
        REPO_ROOT / 'backend/services/dashboard_snapshot.py',
        REPO_ROOT / 'backend/services/bullpen_board.py',
        REPO_ROOT / 'backend/services/what_changed_since_yesterday.py',
        REPO_ROOT / 'backend/services/what_changed_since_yesterday_public.py',
        REPO_ROOT / 'backend/services/tonight_intelligence_snapshot.py',
    )
    blocked_public = (
        'services.roster_depth_evidence',
        'roster_depth_evidence',
        *ROSTER_DEPTH_RULE_IDS,
    )
    for path in public_paths:
        text = path.read_text(encoding='utf-8')
        for needle in blocked_public:
            assert needle not in text
