"""Real PostgreSQL SP-13 scoping and SP-05 interval split on the migrated schema."""

from datetime import date, timedelta
from hashlib import sha256
import json
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from models.fatigue_score import FatigueScore  # noqa: F401 - Pitcher relationship
from models.game_log import GameLog  # noqa: F401 - Pitcher relationship
from models.dashboard_snapshot import DashboardSnapshot
from models.pitcher import Pitcher
from models.player_transaction import PlayerTransaction
from models.sync_run import SyncRun
from models.roster_status_snapshot import RosterStatusSnapshot
from tests.test_schedule_ingestion import fenced_database_url  # noqa: F401

APPLY = "SELECT roster_history_repair.apply_burgos(1)"
APPROVE = "SELECT roster_history_repair.approve_burgos()"


def observation(conn, day, present, kind="active"):
    records = [{"person": {"id": 670103}, "position": {"abbreviation": "P"}}] if present else []
    payload = json.dumps(
        {
            "records": records,
            "completeness_proof": {
                "authoritative_for_mlb_membership": True,
                "authoritative_for_absence": True,
            },
        }
    )
    parameters = json.dumps({"teamId": 111, "rosterType": kind, "date": day.isoformat()})
    key = sha256(parameters.encode()).hexdigest()
    subject = conn.execute(
        text("""
        INSERT INTO source_subjects(identity_key,provider,source_domain,endpoint,subject_type,
            subject_key,request_identity,request_schema_version,request_parameters,baseball_date,created_at,updated_at)
        VALUES (:key,'mlb_stats_api','roster','/teams/111/roster','team',:subject,:key,1,:params,:day,now(),now())
        RETURNING id
    """),
        dict(key=key, subject="111:" + kind, params=parameters, day=day),
    ).scalar_one()
    digest = sha256(payload.encode()).hexdigest()
    artifact = conn.execute(
        text("""
        INSERT INTO source_payload_artifacts(content_hash,hash_algorithm,payload_schema_version,payload_kind,
            storage_format,payload_json,payload_bytes,created_at)
        VALUES (:hash,'sha256',1,'normalized_json','json',:payload,:size,now())
        ON CONFLICT (content_hash,payload_schema_version,payload_kind)
        DO UPDATE SET content_hash=excluded.content_hash RETURNING id
    """),
        dict(hash=digest, payload=payload, size=len(payload)),
    ).scalar_one()
    return conn.execute(
        text("""
        INSERT INTO source_observations(source_subject_id,version_number,dedupe_key,fingerprint,
            fingerprint_algorithm,fingerprint_version,payload_schema_version,payload_artifact_id,
            completeness,outcome,is_change,is_authoritative,record_count,observed_at,created_at)
        VALUES (:subject,1,:key,:hash,'sha256','v1',1,:artifact,'complete',:outcome,true,true,:count,now(),now())
        RETURNING id
    """),
        dict(
            subject=subject,
            key=key,
            hash=digest,
            artifact=artifact,
            count=len(records),
            outcome="new" if present else "empty_valid",
        ),
    ).scalar_one()


def seed(conn):
    session = Session(conn)
    pitcher = Pitcher(id=1, mlb_id=670103, full_name="Raymond Burgos", team_id=133)
    session.add_all([pitcher, Pitcher(id=2, mlb_id=999002, full_name="Fixture pitcher", team_id=110)])
    session.flush()
    for day, code, category, tx, origin, destination in (
        (25, "OPT", "option", "943956", 111, 533),
        (28, "CU", "recall", "944806", 533, 111),
    ):
        d = date(2026, 9, day)
        session.add(
            PlayerTransaction(
                transaction_key=tx,
                transaction_id=tx,
                pitcher_id=1,
                player_mlb_id=670103,
                transaction_date=d,
                effective_date=d,
                normalized_category=category,
                transaction_type_code=code,
                from_team_id=origin,
                to_team_id=destination,
                source="mlb_stats_api:transactions",
                source_endpoint="/transactions",
                source_query_start_date=d,
                source_query_end_date=d,
            )
        )
    run = SyncRun(source="fixture", status="success")
    session.add(run)
    session.flush()
    snapshot = DashboardSnapshot(
        snapshot_type="league",
        sync_run_id=run.id,
        status="ready",
        is_published=True,
        payload={"manifest": "historical fixture"},
    )
    session.add(snapshot)
    session.flush()
    run.published_dashboard_snapshot_id = snapshot.id
    session.flush()
    for interval, kind, membership in (
        (129, "active", "active_roster"),
        (149, "40Man", "forty_man_roster"),
    ):
        obs = observation(conn, date(2026, 9, 10), True, kind)
        conn.execute(
            text("""
            INSERT INTO roster_membership_intervals(id,pitcher_id,player_mlb_id,team_id,organization_id,
                membership_type,effective_start_date,authority_type,opened_by_observation_id,created_at,updated_at)
            VALUES (:id,1,670103,111,111,:membership,'2026-09-10','official_mlb_roster_v1',:obs,now(),now())
        """),
            dict(id=interval, membership=membership, obs=obs),
        )
    session.add(
        RosterStatusSnapshot(
            pitcher_id=1,
            mlb_id=670103,
            team_id=111,
            snapshot_date=date(2026, 9, 28),
            active_roster=True,
            forty_man_roster=True,
            roster_status="active",
            source="mlb_stats_api:roster_sync:active",
        )
    )
    session.flush()
    for offset in range(7):
        observation(conn, date(2026, 9, 25) + timedelta(days=offset), offset in (0, 3, 6))
    for day in (25, 26):
        observation(conn, date(2026, 9, day), True, "40Man")
    seed_atomic_publication(conn)


def seed_atomic_publication(conn):
    # Installed SP-11 generation and pointer, independent of the public dashboard pointer.
    conn.exec_driver_sql("""
        INSERT INTO canonical_impact_plans(id,plan_fingerprint,rules_version,authority_class,baseball_date,
          affected_game_ids_json,affected_team_ids_json,affected_pitcher_ids_json,affected_domains_json,
          source_observation_ids_json,status,supersedes_live,created_at)
        VALUES (1,'fixture','v1','final','2026-09-10','[]','[]','[]','[]','[]','dispatched',false,now());
        INSERT INTO derived_intelligence_cohorts(id,impact_plan_id,cohort_fingerprint,schema_version,authority_class,
          baseball_date,status,requested_domains_json,execution_domains_json,completed_domains_json,withheld_domains_json,
          affected_game_ids_json,affected_team_ids_json,affected_pitcher_ids_json,input_manifest_json,
          method_versions_json,started_at,created_at)
        VALUES (1,1,'fixture','v1','final','2026-09-10','complete','[]','[]','[]','[]','[]','[]','[]','[]','{}',now(),now());
        INSERT INTO atomic_publications(id,publication_fingerprint,schema_version,cohort_id,impact_plan_id,
          baseball_date,authority_class,status,completeness,source_data_through,affected_game_ids_json,
          affected_team_ids_json,affected_pitcher_ids_json,completed_domains_json,withheld_domains_json,
          method_versions_json,input_manifest_fingerprint,artifact_created_count,artifact_inherited_count,created_at)
        VALUES (1,'fixture','v1',1,1,'2026-09-10','final','published','complete',now(),'[]','[]','[]','[]','[]','{}',
          encode(sha256(convert_to('[]','UTF8')),'hex'),0,0,now());
        INSERT INTO atomic_publication_current(singleton_id,publication_id,updated_at) VALUES (1,1,now());
    """)


def contents(conn, tables):
    return {
        table: conn.exec_driver_sql(f"SELECT to_jsonb(t)::text FROM {table} t ORDER BY 1")
        .scalars()
        .all()
        for table in tables
    }


def refused(conn, sql, message):
    with pytest.raises(DBAPIError, match=message):
        with conn.begin_nested():
            conn.exec_driver_sql(sql)


def assert_invalid_requests_are_atomic(conn, role, correction, protected):
    for setup, error in [
        ("UPDATE repair_requests SET scope_json='{}'", "outside approved scope"),
        (
            "UPDATE repair_requests SET scope_json=scope_json::jsonb || '{\"team_ids\":[110]}'",
            "outside approved scope",
        ),
        (
            "UPDATE repair_requests SET scope_json=scope_json::jsonb || '{\"player_mlb_id\":999}'",
            "outside approved scope",
        ),
        (
            'UPDATE repair_requests SET scope_json=scope_json::jsonb || \'{"membership_type":"forty_man_roster"}\'',
            "outside approved scope",
        ),
        (
            "UPDATE roster_status_snapshots SET active_roster=false WHERE snapshot_date='2026-09-28'",
            "retained roster snapshot conflicts",
        ),
        (
            "UPDATE roster_status_snapshots SET team_id=133,snapshot_date='2026-11-19' WHERE pitcher_id=1",
            "later roster departure needs independent review",
        ),
        ("UPDATE repair_requests SET dry_run=true", "outside approved scope"),
        ("UPDATE repair_requests SET baseball_date_end='2026-09-27'", "outside approved scope"),
        ("UPDATE source_observations SET completeness='partial' WHERE id=4", "invalid old-club"),
        (
            """INSERT INTO source_observations SELECT (jsonb_populate_record(o,
            jsonb_build_object('id',999,'dedupe_key','competing','version_number',2,
                               'predecessor_observation_id',o.id))).*
            FROM source_observations o WHERE id=4""",
            "more than one row",
        ),
        ("UPDATE source_observations SET is_authoritative=false WHERE id=4", "invalid old-club"),
        (
            "UPDATE player_transactions SET effective_date=NULL WHERE transaction_id='943956'",
            "no rows",
        ),
        (
            "UPDATE source_observations SET payload_artifact_id=1,record_count=1 WHERE id=4",
            "conflicting Boston",
        ),
        ("UPDATE alembic_version SET version_num='other'", "uncertified"),
        (
            "UPDATE roster_membership_intervals SET membership_type='organization' WHERE id=129",
            "history changed",
        ),
        (
            """CREATE FUNCTION pg_temp.inject_failure() RETURNS trigger LANGUAGE plpgsql AS
            'BEGIN RAISE EXCEPTION ''injected''; END'; CREATE TRIGGER injected BEFORE INSERT
            ON roster_membership_mutations FOR EACH ROW EXECUTE FUNCTION pg_temp.inject_failure()""",
            "injected",
        ),
    ]:
        sandbox = conn.begin_nested()
        conn.exec_driver_sql(setup)
        baseline = contents(conn, correction + protected)
        conn.exec_driver_sql(f"SET LOCAL ROLE {role}")
        refused(conn, APPLY, error)
        conn.exec_driver_sql("RESET ROLE")
        assert contents(conn, correction + protected) == baseline
        sandbox.rollback()


def assert_existing_recall_is_preserved(conn, role):
    # When a later stint is already materialized, retain its identity
    # and full row. A different opening observation cannot be replaced.
    later = conn.begin_nested()
    conn.exec_driver_sql("""INSERT INTO roster_membership_intervals
        (id,pitcher_id,player_mlb_id,team_id,organization_id,membership_type,effective_start_date,
         effective_end_date,authority_type,opened_by_observation_id,created_at,updated_at)
        VALUES (900,1,670103,111,111,'active_roster','2026-10-01','2026-11-18',
                'official_mlb_roster_v1',9,now(),now())""")
    # The existing end is an opaque fixture value, never inferred by the writer.
    later_row = "SELECT to_jsonb(i) FROM roster_membership_intervals i WHERE id=900"
    preserved = conn.exec_driver_sql(later_row).scalar_one()
    conflict = conn.begin_nested()
    conn.exec_driver_sql(
        "UPDATE roster_membership_intervals SET opened_by_observation_id=1 WHERE id=900"
    )
    refused(conn, APPLY, "later membership needs independent review")
    conflict.rollback()
    conn.exec_driver_sql(f"SET LOCAL ROLE {role}")
    conn.exec_driver_sql(APPLY)
    conn.exec_driver_sql("RESET ROLE")
    assert conn.exec_driver_sql(later_row).scalar_one() == preserved
    later.rollback()


def test_burgos_history(fenced_database_url):
    engine = create_engine(fenced_database_url, isolation_level="SERIALIZABLE")
    role = "burgos_test_" + uuid4().hex
    approver = "burgos_approver_" + uuid4().hex
    protected = (
        "atomic_publication_current",
        "atomic_publications",
        "atomic_publication_cache_handoffs",
        "dashboard_snapshots",
        "sync_runs",
        "pitchers",
        "player_transactions",
        "source_observations",
        "roster_status_snapshots",
        "source_subjects",
        "source_payload_artifacts",
        "sync_jobs",
    )
    correction = ("repair_requests", "roster_membership_intervals", "roster_membership_mutations")
    try:
        with engine.begin() as conn:
            seed(conn)
            assert (
                conn.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one()
                == "de608f29a341"
            )
            assert conn.exec_driver_sql(
                "SELECT relrowsecurity FROM pg_class WHERE oid='repair_requests'::regclass"
            ).scalar_one()
            assert (
                conn.exec_driver_sql(
                    "SELECT count(*) FROM pg_trigger WHERE tgname='baseballos_pitcher_projection_fence' AND tgenabled='O'"
                ).scalar_one()
                == 1
            )
            conn.exec_driver_sql(f"CREATE ROLE {approver} NOSUPERUSER NOBYPASSRLS")
            conn.exec_driver_sql(f"GRANT USAGE ON SCHEMA roster_history_repair TO {approver}")
            conn.exec_driver_sql(
                f"GRANT EXECUTE ON FUNCTION roster_history_repair.approve_burgos() TO {approver}"
            )
            conn.exec_driver_sql(f"SET LOCAL ROLE {approver}")
            assert conn.exec_driver_sql(APPROVE).scalar_one() == 1
            refused(conn, APPLY, "permission denied")
            conn.exec_driver_sql("RESET ROLE")
            conn.exec_driver_sql(f"DROP OWNED BY {approver}")
            conn.exec_driver_sql(f"DROP ROLE {approver}")
        # A different transaction and capability consume the committed SP-13 request.
        with engine.begin() as conn:
            conn.exec_driver_sql(f"CREATE ROLE {role} NOSUPERUSER NOBYPASSRLS")
            conn.exec_driver_sql(f"GRANT USAGE ON SCHEMA roster_history_repair TO {role}")
            conn.exec_driver_sql(f"SET LOCAL ROLE {role}")
            refused(conn, APPROVE, "permission denied")
            refused(conn, APPLY, "permission denied")
            conn.exec_driver_sql("RESET ROLE")
            conn.exec_driver_sql(
                f"GRANT EXECUTE ON FUNCTION roster_history_repair.apply_burgos(integer) TO {role}"
            )
            conn.exec_driver_sql(f"SET LOCAL ROLE {role}")
            for table, field in [
                ("roster_membership_intervals", "id"),
                ("atomic_publication_current", "publication_id"),
                ("dashboard_snapshots", "id"),
                ("repair_requests", "id"),
            ]:
                refused(conn, f"UPDATE {table} SET {field}={field}", "permission denied")
            conn.exec_driver_sql("RESET ROLE")
            before = contents(conn, protected)
            assert_invalid_requests_are_atomic(conn, role, correction, protected)
            assert_existing_recall_is_preserved(conn, role)
            conn.exec_driver_sql(f"SET LOCAL ROLE {role}")
            conn.exec_driver_sql(APPLY)
            refused(conn, APPLY, "already settled")
            conn.exec_driver_sql("RESET ROLE")
            assert contents(conn, protected) == before
            assert (
                conn.exec_driver_sql("""SELECT id,is_current_version,effective_end_date FROM
                roster_membership_intervals WHERE id IN (129,149) ORDER BY id""").all()
                == [(129, False, None), (149, True, None)]
            )
            assert (
                conn.exec_driver_sql(
                    """SELECT effective_start_date,effective_end_date,opened_by_observation_id,
                closed_by_observation_id,supersedes_interval_id FROM roster_membership_intervals
                WHERE membership_type='active_roster' AND is_current_version ORDER BY effective_start_date"""
                ).all()
                == [
                    (date(2026, 9, 10), date(2026, 9, 26), 1, 4, 129),
                    (date(2026, 9, 28), date(2026, 9, 29), 6, 7, 129),
                    (date(2026, 10, 1), None, 9, None, 129),
                ]
            )
            for represented, active in [
                ("2026-09-25", True),
                ("2026-09-26", False),
                ("2026-09-28", True),
                ("2026-09-29", False),
                ("2026-10-01", True),
            ]:
                memberships = (
                    conn.execute(
                        text("""
                    SELECT membership_type FROM roster_membership_intervals WHERE player_mlb_id=670103
                      AND team_id=111 AND is_current_version AND NOT is_void AND effective_start_date<=:day
                      AND (effective_end_date IS NULL OR effective_end_date>:day)
                """),
                        dict(day=represented),
                    )
                    .scalars()
                    .all()
                )
                assert ("active_roster" in memberships) == active
                assert "forty_man_roster" in memberships
            conn.exec_driver_sql(f"DROP OWNED BY {role}")
            conn.exec_driver_sql(f"DROP ROLE {role}")
        with engine.begin() as conn:
            refused(conn, APPLY, "already settled")
            assert conn.exec_driver_sql("SELECT status FROM repair_requests").scalar_one() == "completed"
    finally:
        engine.dispose()
