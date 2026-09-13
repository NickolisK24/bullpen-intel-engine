from datetime import date, datetime
from types import SimpleNamespace
from models.pitcher import Pitcher
from services.derived_intelligence import capture_input_manifest
from services.public_pitcher_current import build_public_pitcher_current_payload
from services.publication_read_model_artifacts import build_what_changed_candidate
from services.what_changed_comparison_identity import build_comparison_identity
from tests.test_atomic_publication import app, _cohort
from utils.db import db

def test_f03_persisted_cohort_probe(app):
    import json
    from time import perf_counter
    from sqlalchemy import event
    from models.derived_intelligence import DerivedCohortSnapshot
    from services.derived_intelligence import execute_derived_intelligence_plan
    pitcher = Pitcher(id=10, mlb_id=100001, full_name='Revalidation Pitcher',
                      team_id=110, team_name='Club', team_abbreviation='C', active=True)
    db.session.add(pitcher)
    db.session.commit()
    first_plan, _ = _cohort(marker='f03-cohort-first', completed=('pitcher_snapshot',))
    kwargs = dict(freshness={'availability_reference_date': '2026-09-09', 'data_through': '2026-09-09'},
                  score_cutoff=datetime(2026,9,9,12))
    def executor(domain, snapshots):
        return {'pitcher': {'10': {'pitcher_snapshot': build_public_pitcher_current_payload(10, **kwargs)}}} if domain == 'pitcher_snapshot' else {}
    first = execute_derived_intelligence_plan(first_plan.id, domain_executor=executor,
                                             publication_candidate_enabled=False).cohort
    row = DerivedCohortSnapshot.query.filter_by(cohort_id=first.id).one()
    old_payload = json.dumps(row.payload_json, sort_keys=True)
    old_manifest = json.dumps(first.input_manifest_json, sort_keys=True)
    pitcher.roster_status = 'injured_list'
    db.session.commit()
    second_plan, _ = _cohort(marker='f03-cohort-second', completed=('pitcher_snapshot',))
    second = execute_derived_intelligence_plan(second_plan.id, domain_executor=executor,
                                              publication_candidate_enabled=False).cohort
    new_row = DerivedCohortSnapshot.query.filter_by(cohort_id=second.id).one()
    assert first.input_manifest_json == second.input_manifest_json == []
    assert first.status == second.status == 'complete'
    assert row.payload_json['pitcher_snapshot']['pitcher']['roster_status'] is None
    assert new_row.payload_json['pitcher_snapshot']['pitcher']['roster_status'] == 'injured_list'
    assert json.dumps(row.payload_json, sort_keys=True) == old_payload
    assert json.dumps(first.input_manifest_json, sort_keys=True) == old_manifest
    count = []
    def on_query(*args):
        count.append(1)
    event.listen(db.engine, 'before_cursor_execute', on_query)
    started = perf_counter()
    for _ in range(10):
        capture_input_manifest(second_plan)
    elapsed = (perf_counter() - started) * 1000 / 10
    event.remove(db.engine, 'before_cursor_execute', on_query)
    print(json.dumps({'fixture': 'sparse persisted cohort, injected public-pitcher executor',
                      'first_cohort_id': first.id, 'second_cohort_id': second.id,
                      'field': 'pitcher_snapshot.pitcher.roster_status',
                      'before': None, 'after': 'injured_list',
                      'manifest_bytes': len(old_manifest.encode()),
                      'manifest_selects_per_capture': len(count)/10,
                      'mean_manifest_ms': round(elapsed,3)}))

def test_f03_current_builder_changes_without_manifest_change(app):
    pitcher = Pitcher(id=10, mlb_id=100001, full_name='Revalidation Pitcher',
                      team_id=110, team_name='Club', team_abbreviation='C', active=True)
    db.session.add(pitcher)
    db.session.commit()
    plan, cohort = _cohort(marker='f03-revalidation')
    before_manifest = capture_input_manifest(plan)
    kwargs = dict(freshness={'reference_date': '2026-09-09', 'data_through': '2026-09-09'},
                  score_cutoff=datetime(2026,9,9,12))
    before = build_public_pitcher_current_payload(10, **kwargs)
    pitcher.roster_status = 'injured_list'
    db.session.commit()
    after = build_public_pitcher_current_payload(10, **kwargs)
    assert before['pitcher']['roster_status'] != after['pitcher']['roster_status']
    assert capture_input_manifest(plan) == before_manifest

def test_f05_atomic_predecessor_metadata_does_not_choose_comparison(app, monkeypatch):
    previous = SimpleNamespace(id=100, sync_run_id=200, payload_version=1,
                               data_through=date(2026,9,8), snapshot_type='dashboard')
    current = SimpleNamespace(id=101, sync_run_id=201, payload_version=1,
                              data_through=date(2026,9,9), snapshot_type='dashboard')
    identity = build_comparison_identity(current, previous)
    current.payload = {'what_changed_since_yesterday': {'comparison': {'identity': identity}}}
    calls=[]
    def capture(team_id, **kwargs):
        calls.append(kwargs)
        return {'team_id': team_id}
    monkeypatch.setattr('services.publication_read_model_artifacts.build_team_changes_payload', capture)
    values=[build_what_changed_candidate(110, board={'freshness': {}}, snapshot=current,
                                        predecessor_cohort_id=value) for value in (None, 99, 102)]
    assert [call['comparison_identity'] for call in calls] == [identity]*3
    assert [value['predecessor_source_snapshot_id'] for value in values] == [100]*3
    assert [value['publication_comparison_state'] for value in values] == ['frozen_predecessor_context']*3
