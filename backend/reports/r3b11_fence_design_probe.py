"""Local PostgreSQL counterexamples; passing probes do not certify a fence."""
from datetime import datetime
from time import perf_counter

from sqlalchemy import select, update

from models.dashboard_snapshot import DashboardSnapshot
from models.derived_intelligence import DerivedIntelligenceCohort
from services.derived_intelligence import _latest_comparable_cohort
from tests.test_derived_intelligence import app, _plan, GAME_DATE
from tests.test_atomic_publication import _cohort
from utils.db import db


def _source():
    assert db.engine.dialect.name == 'postgresql'
    row = DashboardSnapshot(
        snapshot_type='bullpen_dashboard', status='ready', is_published=False,
        payload={'generation': 1}, data_through=GAME_DATE,
        snapshot_generated_at=datetime(2026, 9, 9, 4),
    )
    db.session.add(row)
    db.session.commit()
    return row.id


def _advance(writer):
    return writer.execute(DashboardSnapshot.__table__.insert().values(
        snapshot_type='bullpen_dashboard', status='ready', is_published=False,
        payload={'generation': 2}, data_through=GAME_DATE,
        snapshot_generated_at=datetime(2026, 9, 9, 5),
    ).returning(DashboardSnapshot.id)).scalar_one()


def test_locking_selected_row_does_not_block_new_latest_insert(app):
    first = _source()
    with db.engine.begin() as completion:
        completion.execute(select(DashboardSnapshot.id)
                           .where(DashboardSnapshot.id == first).with_for_update()).one()
        start = perf_counter()
        with db.engine.begin() as writer:
            writer.exec_driver_sql("SET LOCAL lock_timeout = '1s'")
            second = _advance(writer)
        elapsed = (perf_counter() - start) * 1000
        assert second > first
        assert completion.execute(select(DashboardSnapshot.id)
                                  .order_by(DashboardSnapshot.id.desc()).limit(1)).scalar_one() == second
        print(f'New latest insertion committed despite S1 FOR UPDATE: {elapsed:.3f} ms')


def test_serializable_alone_allows_coherent_old_generation_to_commit_later(app):
    first = _source()
    _, cohort = _cohort(marker='serializable-window', status='running')
    cohort_id = cohort.id
    with db.engine.connect().execution_options(isolation_level='SERIALIZABLE') as completion:
        with completion.begin():
            assert completion.execute(select(DashboardSnapshot.id)
                                      .order_by(DashboardSnapshot.id.desc()).limit(1)).scalar_one() == first
            with db.engine.connect().execution_options(isolation_level='SERIALIZABLE') as writer:
                with writer.begin():
                    second = _advance(writer)
            # A valid serial ordering places this completion before the writer,
            # even though the writer physically committed first. No SSI cycle.
            assert completion.execute(select(DashboardSnapshot.id)
                                      .order_by(DashboardSnapshot.id.desc()).limit(1)).scalar_one() == first
            completion.execute(update(DerivedIntelligenceCohort)
                               .where(DerivedIntelligenceCohort.id == cohort_id)
                               .values(status='complete'))
    db.session.expire_all()
    assert db.session.get(DerivedIntelligenceCohort, cohort_id).status == 'complete'
    assert DashboardSnapshot.query.order_by(DashboardSnapshot.id.desc()).first().id == second


def test_unrelated_cohorts_can_change_current_predecessor_selector(app):
    assert db.engine.dialect.name == 'postgresql'
    _, predecessor = _cohort(marker='scoped-predecessor')
    target = _plan(fingerprint='target'.ljust(64, '0'))
    assert _latest_comparable_cohort(target).id == predecessor.id
    other = _plan(fingerprint='other'.ljust(64, '0'), teams=(999,), pitchers=(999,), games=(999,))
    values = [dict(
        impact_plan_id=other.id, cohort_fingerprint=f'unrelated-{index:03d}'.ljust(64, 'x'),
        schema_version='derived-cohort-v1', authority_class='final',
        baseball_date=GAME_DATE, status='complete',
        requested_domains_json=['game_context'], execution_domains_json=['game_context'],
        completed_domains_json=['game_context'], withheld_domains_json=[],
        affected_game_ids_json=[999], affected_team_ids_json=[999],
        affected_pitcher_ids_json=[999], input_manifest_json=[], method_versions_json={},
    ) for index in range(100)]
    with db.engine.begin() as writer:
        writer.execute(DerivedIntelligenceCohort.__table__.insert(), values)
    assert _latest_comparable_cohort(target) is None
