"""Local diagnostic: a passing assertion here confirms the B1 commit-window gap."""
from datetime import datetime
from models.dashboard_snapshot import DashboardSnapshot
from services import dashboard_snapshot, derived_intelligence as service
from tests.test_derived_intelligence import app, _plan, GAME_DATE
from utils.db import db


def test_selector_commit_after_revalidation_can_still_complete(app, monkeypatch):
    assert db.engine.dialect.name == 'postgresql'
    plan = _plan(domains=('read_models',))
    source = DashboardSnapshot(
        snapshot_type='bullpen_dashboard', status='ready', is_published=False,
        payload={'generation': 1}, data_through=GAME_DATE,
        snapshot_generated_at=datetime(2026, 9, 9, 4),
    )
    db.session.add(source)
    db.session.commit()
    first_id = source.id
    monkeypatch.setattr(
        dashboard_snapshot, 'get_latest_valid_dashboard_snapshot',
        lambda: DashboardSnapshot.query.filter_by(snapshot_type='bullpen_dashboard')
            .order_by(DashboardSnapshot.id.desc()).first(),
    )
    monkeypatch.setattr(
        service._DefaultDomainExecutor, '__call__',
        lambda executor, domain, snapshots: {
            'team': {'110': {'selected_source': executor.build_context.source_snapshot().id}},
        },
    )
    persist = service._persist_snapshots

    def advance_before_completion(cohort, snapshots):
        assert cohort.status == 'running'
        with db.engine.begin() as writer:
            writer.execute(DashboardSnapshot.__table__.insert().values(
                snapshot_type='bullpen_dashboard', status='ready', is_published=False,
                payload={'generation': 2}, data_through=GAME_DATE,
                snapshot_generated_at=datetime(2026, 9, 9, 5),
            ))
        persist(cohort, snapshots)

    monkeypatch.setattr(service, '_persist_snapshots', advance_before_completion)
    cohort = service.execute_derived_intelligence_plan(
        plan.id, publication_candidate_enabled=False,
    ).cohort
    assert cohort.status == 'complete'
    assert cohort.input_manifest_json[-1]['context']['selectors']['dashboard_snapshot_id'] == first_id
    assert not service.cohort_inputs_are_current(cohort, plan)
