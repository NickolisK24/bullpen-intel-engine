"""PostgreSQL acceptance case for the SP-05 September 23 destination correction."""

from datetime import date
from hashlib import sha256
import json
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from models.evidence_contract import EvidenceCitation, EvidenceObject
from models.pitcher import Pitcher
from models.player_transaction import PlayerTransaction
from models.roster_status_snapshot import RosterStatusSnapshot
from tests.test_burgos_roster_history import contents, refused, seed_atomic_publication
from tests.test_schedule_ingestion import fenced_database_url  # noqa: F401

DAY = date(2026, 9, 23)
OLD = dict(
    transaction_id=943752,
    player_mlb_id=702566,
    from_team_id=144,
    to_team_id=431,
    transaction_date=str(DAY),
    effective_date=str(DAY),
    transaction_type_code="OPT",
    source_endpoint="/transactions",
)
NEIGHBOR = dict(OLD, transaction_id=943761, player_mlb_id=801725, from_team_id=110, to_team_id=568)
APPROVE = "SELECT transaction_history_repair.approve_murphy(14270)"
APPLY = "SELECT transaction_history_repair.apply_murphy(1)"


def stable(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return sha256(stable(value).encode()).hexdigest()


def seed(conn, source_windows=None):
    from services.transaction_ingestion import TRANSACTION_FACT_FIELDS

    session = Session(conn)
    session.add(Pitcher(id=764, mlb_id=702566, team_id=144, full_name="Owen Murphy"))
    session.flush()
    session.add(
        RosterStatusSnapshot(
            pitcher_id=764,
            mlb_id=702566,
            team_id=144,
            snapshot_date=DAY,
            roster_status="active",
            source="fixture",
            active_roster=True,
            forty_man_roster=True,
        )
    )
    session.flush()
    conn.exec_driver_sql("""INSERT INTO source_subjects(id,identity_key,provider,source_domain,
        endpoint,subject_type,subject_key,request_identity,request_schema_version,request_parameters,
        range_start,range_end,created_at,updated_at) VALUES (2411,'fixture','mlb_stats_api',
        'transactions','/transactions','date_range','2026-09-22:2026-09-24:league','fixture',1,
        '{"startDate":"2026-09-22","endDate":"2026-09-24","sportId":1,"limit":1000}',
        '2026-09-22','2026-09-24',now(),now())""")
    if source_windows is None:
        source_windows = ([OLD, NEIGHBOR], [dict(OLD, to_team_id=464), dict(NEIGHBOR, to_team_id=599)])
    for version, rows in enumerate(source_windows, start=1):
        artifact = conn.execute(
            text("""INSERT INTO source_payload_artifacts(content_hash,hash_algorithm,
            payload_schema_version,payload_kind,storage_format,payload_json,payload_bytes,created_at)
            VALUES (:hash,'sha256',1,'normalized_json','json',:payload,:size,now()) RETURNING id"""),
            dict(hash=digest(rows), payload=stable(rows), size=len(stable(rows).encode())),
        ).scalar_one()
        conn.execute(
            text(
                """INSERT INTO source_observations(id,source_subject_id,version_number,
            dedupe_key,fingerprint,fingerprint_algorithm,fingerprint_version,payload_schema_version,
            payload_artifact_id,completeness,outcome,is_change,is_authoritative,record_count,
            predecessor_observation_id,observed_at,created_at) VALUES (:id,2411,:v,:key,:hash,
            'sha256','source-json-sha256-v1',1,:artifact,'complete',:outcome,true,true,:count,:prior,now() + (:v * interval '1 second'),now())"""
            ),
            dict(
                id=14268 + version,
                count=len(rows),
                v=version,
                key=str(version),
                hash=digest(sorted(rows, key=stable)),
                artifact=artifact,
                outcome="new" if version == 1 else "corrected",
                prior=None if version == 1 else 14269,
            ),
        )
    for id_, item in [(644, OLD), (652, NEIGHBOR)]:
        tx = PlayerTransaction(
            transaction_key=f"statsapi:{item['transaction_id']}",
            transaction_id=str(item["transaction_id"]),
            player_mlb_id=item["player_mlb_id"],
            pitcher_id=764 if id_ == 644 else None,
            from_team_id=item["from_team_id"],
            to_team_id=item["to_team_id"],
            transaction_date=DAY,
            effective_date=DAY,
            normalized_category="option",
            transaction_type_code="OPT",
            source="mlb_stats_api:transactions",
            source_endpoint="/transactions",
            source_query_start_date=date(2026, 9, 22),
            source_query_end_date=date(2026, 9, 24),
            participant_role="pitcher",
            participant_role_authority="canonical_pitcher_identity_v1",
            roster_snapshot_alignment="aligned",
            alignment_reason_code="roster_snapshot_team_match",
            explanatory_linkage_eligible=True,
            subtype_reason_code="not_asg",
            subtype_authority="asg_pitcher_rehab_assignment_v1",
            subtype_status="not_certified",
            transaction_materiality="unresolved",
        )
        session.add(tx)
        session.flush()
        facts = {k: getattr(tx, k) for k in TRANSACTION_FACT_FIELDS if not k.startswith("source_query_")}
        if id_ == 644:
            for eid, date_, team_id in (
                (1421545, 5, 144),
                (1421789, 5, 431),
                (1431943, 6, 144),
                (1432187, 6, 431),
            ):
                seed_dependency(session, tx, eid, date_, team_id, "current")
            seed_dependency(session, tx, 1284542, 5, 144, "recompute_needed")
        facts["transaction_type_description"] = None  # Retained in the SP-05 version contract.
        facts = {k: (v.isoformat() if isinstance(v, date) else v) for k, v in facts.items()}
        conn.execute(
            text("""INSERT INTO player_transaction_versions(id,player_transaction_id,
            version_number,source_observation_id,fact_fingerprint,fact_schema_version,fact_json,created_at)
            VALUES (:id,:tx,1,14269,:hash,1,:facts,now())"""),
            dict(id=id_, tx=tx.id, hash=digest(facts), facts=stable(facts)),
        )
        conn.execute(
            text("""UPDATE player_transactions SET current_version_number=1,
            source_observation_id=14269 WHERE id=:tx"""),
            dict(tx=tx.id),
        )


def seed_dependency(session, tx, eid, day, team_id, status):
    evidence = EvidenceObject(
        id=eid,
        evidence_key=f"synthetic-citation-{eid}",
        evidence_type="fixture",
        subject_type="team",
        subject_key=f"team:{team_id}:2026-10-{day:02}:window-14:team_option_recall_churn",
        product_date=date(2026, 10, day),
        claim_template_id="fixture",
        rendered_claim="Historical option",
        rule_id="team_option_recall_churn",
        rule_version=1,
        rule_definition_hash="fixture",
        typed_cited_inputs=[],
        computation_trace={},
        completeness_state="complete",
        source="fixture",
        recompute_status=status,
    )
    session.add(evidence)
    session.flush()
    session.add(
        EvidenceCitation(
            evidence_object_id=evidence.id,
            source_family="transaction",
            source_table="player_transactions",
            source_pk=str(tx.id),
            source_field_names=["to_team_id"],
            provenance={},
        )
    )
    session.flush()


@pytest.mark.parametrize("fenced_database_url", ["restricted_owner"], indirect=True)
def test_single_event_recovery(fenced_database_url):
    engine = create_engine(fenced_database_url, isolation_level="SERIALIZABLE")
    role = "murphy_" + uuid4().hex
    approver = "approve_" + role
    try:
        with engine.connect() as conn, conn.begin():
            assert conn.exec_driver_sql("""SELECT NOT r.rolsuper AND NOT r.rolbypassrls
                FROM pg_proc p JOIN pg_roles r ON r.oid=p.proowner
                WHERE p.oid='transaction_history_repair.apply_murphy(integer)'::regprocedure""").scalar_one()
            seed(conn)
            seed_atomic_publication(conn)
            neighbor = """SELECT to_jsonb(p) FROM player_transactions p WHERE transaction_id='943761'"""
            original = (
                """SELECT to_jsonb(v) FROM player_transaction_versions v WHERE id IN (644,652) ORDER BY id"""
            )
            before_neighbor = conn.exec_driver_sql(neighbor).scalar_one()
            before_versions = conn.exec_driver_sql(original).scalars().all()
            protected = (
                "source_subjects",
                "source_observations",
                "source_payload_artifacts",
                "roster_status_snapshots",
                "atomic_publication_current",
                "atomic_publications",
                "atomic_publication_cache_handoffs",
                "sync_jobs",
                "evidence_citations",
            )
            historical_evidence = "SELECT to_jsonb(e) FROM evidence_objects e WHERE id=1284542"
            prior_evidence = conn.exec_driver_sql(historical_evidence).scalar_one()
            before = contents(conn, protected)
            for name, signature in [(approver, "approve_murphy(integer)"), (role, "apply_murphy(integer)")]:
                conn.exec_driver_sql(f"CREATE ROLE {name}")
                conn.exec_driver_sql(f"GRANT USAGE ON SCHEMA transaction_history_repair TO {name}")
                conn.exec_driver_sql(
                    f"GRANT EXECUTE ON FUNCTION transaction_history_repair.{signature} TO {name}"
                )
            conn.exec_driver_sql(f"SET LOCAL ROLE {approver}")
            refused(conn, "SELECT transaction_history_repair.approve_murphy(14269)", "lacks source evidence")
            assert conn.exec_driver_sql(APPROVE).scalar_one() == 1
            refused(conn, APPLY, "permission denied")
            conn.exec_driver_sql("RESET ROLE")
            conn.exec_driver_sql(f"SET LOCAL ROLE {role}")
            refused(conn, APPROVE, "permission denied")
            refused(conn, "UPDATE player_transactions SET to_team_id=464", "permission denied")
            conn.exec_driver_sql("RESET ROLE")
            # An unmarked caller must not inherit the repair key on function return.
            trial = conn.begin_nested()
            conn.exec_driver_sql(f"SET LOCAL ROLE {role}")
            conn.exec_driver_sql(APPLY)
            assert not conn.exec_driver_sql(
                "SELECT current_setting('baseballos.transaction_owner', true)"
            ).scalar_one()
            trial.rollback()
            conn.exec_driver_sql("SET LOCAL baseballos.transaction_owner = 'caller-context'")
            for setup, error in [
                ("UPDATE source_observations SET completeness='partial' WHERE id=14270", "no rows"),
                ("UPDATE source_payload_artifacts SET content_hash='bad' WHERE id=2", "integrity mismatch"),
                ("UPDATE evidence_objects SET recompute_status='current'", "dependent evidence"),
                ("UPDATE source_observations SET is_authoritative=false WHERE id=14270", "no rows"),
                ("UPDATE repair_requests SET scope_json='{}'", "outside scope"),
                (
                    "UPDATE evidence_objects SET subject_key='team:other' WHERE id=1421545",
                    "dependent evidence",
                ),
                (
                    "UPDATE source_observations SET observed_at=timestamp '2020-01-01' WHERE id=14270",
                    "no rows",
                ),
                (
                    """INSERT INTO source_observations SELECT (jsonb_populate_record(o,
                      jsonb_build_object('id',14271,'version_number',3,'dedupe_key','later',
                      'predecessor_observation_id',14270))).* FROM source_observations o WHERE id=14270""",
                    "no rows",
                ),
                ("UPDATE alembic_version SET version_num='unrecognized'", "uncertified"),
                (
                    """UPDATE source_payload_artifacts SET payload_json=(payload_json::jsonb || (payload_json::jsonb->0))
                   WHERE id=2""",
                    "incomplete transaction response",
                ),
                (
                    """CREATE FUNCTION pg_temp.abort_projection() RETURNS trigger LANGUAGE plpgsql AS
                   'BEGIN RAISE EXCEPTION ''projection failure''; END'; CREATE TRIGGER stop BEFORE UPDATE
                   ON player_transactions FOR EACH ROW EXECUTE FUNCTION pg_temp.abort_projection()""",
                    "projection failure",
                ),
                (
                    """CREATE FUNCTION pg_temp.abort_write() RETURNS trigger LANGUAGE plpgsql AS
                   'BEGIN RAISE EXCEPTION ''injected''; END'; CREATE TRIGGER stop BEFORE UPDATE OF
                   status ON repair_requests FOR EACH ROW EXECUTE FUNCTION pg_temp.abort_write()""",
                    "injected",
                ),
            ]:
                point = conn.begin_nested()
                conn.exec_driver_sql(setup)
                tables = (
                    "player_transactions",
                    "player_transaction_versions",
                    "repair_requests",
                    "evidence_objects",
                )
                initial = contents(conn, tables)
                conn.exec_driver_sql(f"SET LOCAL ROLE {role}")
                refused(conn, APPLY, error)
                assert conn.exec_driver_sql("SHOW baseballos.transaction_owner").scalar_one() == "caller-context"
                conn.exec_driver_sql("RESET ROLE")
                assert contents(conn, tables) == initial
                point.rollback()
            conn.exec_driver_sql(f"SET LOCAL ROLE {role}")
            successor = conn.exec_driver_sql(APPLY).scalar_one()
            assert conn.exec_driver_sql("SHOW baseballos.transaction_owner").scalar_one() == "caller-context"
            refused(conn, APPLY, "scope|settled")
            conn.exec_driver_sql("RESET ROLE")
            row = conn.execute(
                text("""SELECT predecessor_version_id,version_number,source_observation_id,
                fact_json,fact_fingerprint FROM player_transaction_versions WHERE id=:id"""),
                dict(id=successor),
            ).one()
            assert row[:3] == (644, 2, 14270)
            assert row.fact_json == dict(before_versions[0]["fact_json"], to_team_id=464)
            assert digest(row.fact_json) == row.fact_fingerprint
            for name in (role, approver):
                conn.exec_driver_sql(f"DROP OWNED BY {name}")
                conn.exec_driver_sql(f"DROP ROLE {name}")
        # A subsequent primary transaction on a fresh connection sees the committed successor.
        engine.dispose()
        with engine.begin() as conn:
            conn.exec_driver_sql(
                "UPDATE player_transactions SET to_team_id=431 WHERE transaction_id='943752'"
            )
            assert conn.exec_driver_sql("""SELECT to_team_id,current_version_number,source_observation_id
                FROM player_transactions WHERE transaction_id='943752'""").one() == (464, 2, 14270)
            assert conn.exec_driver_sql("""SELECT count(*) FROM compatibility_write_events
                WHERE resource_key='statsapi:943752' AND outcome='stale_suppressed'""").scalar_one() == 1
            assert conn.exec_driver_sql(neighbor).scalar_one() == before_neighbor
            assert conn.exec_driver_sql(original).scalars().all() == before_versions
            assert conn.exec_driver_sql("SELECT count(*) FROM player_transaction_versions").scalar_one() == 3
            changed = conn.exec_driver_sql("""SELECT id,invalidated_by_source_pk,recompute_reason_codes
                FROM evidence_objects WHERE recompute_status='recompute_needed' AND
                correction_source='upstream_source_correction' AND correction_count=1 ORDER BY id""").all()
            assert [r.id for r in changed] == [1421545, 1421789, 1431943, 1432187]
            assert all(
                r.invalidated_by_source_pk == str(before_versions[0]["player_transaction_id"])
                and r.recompute_reason_codes == ["roster_depth_source_corrected"]
                for r in changed
            )
            assert conn.exec_driver_sql(historical_evidence).scalar_one() == prior_evidence
            assert contents(conn, protected) == before

    finally:
        engine.dispose()
