"""Grant-free, single-event SP-13 recovery for Murphy's September option."""

from importlib import import_module

from alembic import op

revision = 'de608f29a341'
down_revision = 'c71b09e45a82'
branch_labels = None
depends_on = None


def _certify_existing_roster_functions(head):
    # CREATE OR REPLACE preserves the previously reviewed bodies, owners and ACLs.
    prior = import_module("migrations.versions.c71b09e45a82_burgos_history_repair")
    for body in (prior.APPROVE, prior.APPLY):
        op.execute(
            body.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1).replace(
                "ARRAY['c71b09e45a82']", f"ARRAY['{head}']"
            )
        )


def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    _certify_existing_roster_functions(revision)
    op.execute("CREATE SCHEMA transaction_history_repair")
    op.execute("REVOKE ALL ON SCHEMA transaction_history_repair FROM PUBLIC")
    for body in (ADMISSION, SCOPE, CANONICAL_RECORD, EVIDENCE, APPROVE, APPLY):
        op.execute(body)
    op.execute("REVOKE ALL ON ALL FUNCTIONS IN SCHEMA transaction_history_repair FROM PUBLIC")
    op.execute("""
        DO $$
        DECLARE grantee_name name;
        BEGIN
          FOR grantee_name IN
            SELECT r.rolname FROM pg_namespace n CROSS JOIN LATERAL aclexplode(n.nspacl) a
              JOIN pg_roles r ON r.oid=a.grantee
              WHERE n.nspname='transaction_history_repair' AND r.oid<>n.nspowner
            UNION
            SELECT r.rolname FROM pg_proc p CROSS JOIN LATERAL aclexplode(p.proacl) a
              JOIN pg_roles r ON r.oid=a.grantee
              WHERE p.pronamespace='transaction_history_repair'::regnamespace AND r.oid<>p.proowner
          LOOP
            EXECUTE format('REVOKE ALL ON SCHEMA transaction_history_repair FROM %I',grantee_name);
            EXECUTE format('REVOKE ALL ON ALL FUNCTIONS IN SCHEMA transaction_history_repair FROM %I',grantee_name);
          END LOOP;
        END $$;
    """)


def downgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    for signature in (
        "apply_murphy(integer)",
        "approve_murphy(integer)",
        "source_event(integer)",
        "canonical_record(jsonb)",
        "murphy_scope(integer)",
        "require_certified_schema()",
    ):
        op.execute("DROP FUNCTION transaction_history_repair." + signature)
    op.execute("DROP SCHEMA transaction_history_repair")
    _certify_existing_roster_functions(down_revision)


ADMISSION = """
CREATE FUNCTION transaction_history_repair.require_certified_schema() RETURNS void
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    IF (SELECT array_agg(version_num::text) FROM
        (SELECT version_num FROM public.alembic_version FOR SHARE) heads)
        IS DISTINCT FROM ARRAY['de608f29a341'] THEN RAISE EXCEPTION 'uncertified schema'; END IF;
    IF current_setting('transaction_isolation') <> 'serializable' THEN
        RAISE EXCEPTION 'serializable transaction required';
    END IF;
END $$;
"""

SCOPE = """
CREATE FUNCTION transaction_history_repair.murphy_scope(observation_id integer) RETURNS jsonb
LANGUAGE sql IMMUTABLE STRICT SET search_path = pg_catalog, pg_temp AS $$
    SELECT jsonb_build_object('transaction_id','943752','player_mlb_id',702566,
        'from_team_id',144,'old_destination',431,'new_destination',464,
        'prior_version_id',644,'prior_observation_id',14269,'observation_id',observation_id,
        'dependent_evidence_ids',jsonb_build_array(1421545,1421789,1431943,1432187))
$$;
"""

# SP-05 canonicalizes flat transaction records with sorted keys and compact JSON.
CANONICAL_RECORD = """
CREATE FUNCTION transaction_history_repair.canonical_record(facts jsonb) RETURNS text
LANGUAGE sql IMMUTABLE STRICT SET search_path = pg_catalog, pg_temp AS $$
    SELECT CASE WHEN bool_and(jsonb_typeof(value) IN ('string','boolean','number','null'))
        THEN '{'||string_agg(to_jsonb(key)::text||':'||value::text,',' ORDER BY key COLLATE "C")||'}' END
    FROM jsonb_each(facts)
$$;
"""


EVIDENCE = """
CREATE FUNCTION transaction_history_repair.source_event(observation_id integer) RETURNS jsonb
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    payload jsonb;
    total integer;
    item jsonb;
    payload_hash text;
    observation_hash text;
    stored_size integer;
    encoded text;
    sorted_records text;
    encoded_count integer;
BEGIN
    SELECT a.payload_json::jsonb,o.record_count,a.content_hash,a.payload_bytes,o.fingerprint
    INTO STRICT payload,total,payload_hash,stored_size,observation_hash
    FROM public.source_observations o JOIN public.source_subjects s ON s.id=o.source_subject_id
    JOIN public.source_payload_artifacts a ON a.id=o.payload_artifact_id
    WHERE o.id=observation_id AND s.id=2411 AND s.provider='mlb_stats_api'
      AND s.source_domain='transactions' AND s.endpoint='/transactions' AND s.subject_type='date_range'
      AND s.range_start='2026-09-22' AND s.range_end='2026-09-24'
      AND s.subject_key='2026-09-22:2026-09-24:league' AND s.request_schema_version=1
      AND s.request_parameters::jsonb='{"startDate":"2026-09-22","endDate":"2026-09-24","limit": 1000,"sportId": 1}'
      AND o.fingerprint_version='source-json-sha256-v1' AND o.fingerprint_algorithm='sha256'
      AND o.is_authoritative AND o.completeness='complete' AND o.is_change
      AND o.outcome IN ('new','corrected','changed') AND o.payload_schema_version=1
      AND a.payload_schema_version=1 AND a.payload_kind='normalized_json'
      AND a.storage_format='json' AND a.hash_algorithm='sha256'
      AND ((o.id=14269 AND o.version_number=1) OR
           (o.predecessor_observation_id=14269 AND o.version_number=2
            AND o.observed_at > (SELECT observed_at FROM public.source_observations WHERE id=14269)
            AND NOT EXISTS (SELECT FROM public.source_observations newer
                WHERE newer.source_subject_id=s.id AND newer.version_number>o.version_number)));
    IF jsonb_typeof(payload) IS DISTINCT FROM 'array' OR total NOT BETWEEN 1 AND 999
       OR jsonb_array_length(payload) IS DISTINCT FROM total THEN
        RAISE EXCEPTION 'incomplete transaction response';
    END IF;
    SELECT '['||string_agg(record,',' ORDER BY position)||']',
           '['||string_agg(record,',' ORDER BY record COLLATE "C")||']',count(record)
      INTO encoded,sorted_records,encoded_count
      FROM (SELECT transaction_history_repair.canonical_record(x) AS record, position
            FROM jsonb_array_elements(payload) WITH ORDINALITY AS records(x,position)) normalized;
    IF encoded_count <> total OR octet_length(convert_to(encoded,'UTF8')) IS DISTINCT FROM stored_size
       OR encode(sha256(convert_to(encoded,'UTF8')),'hex') IS DISTINCT FROM payload_hash
       OR encode(sha256(convert_to(sorted_records,'UTF8')),'hex') IS DISTINCT FROM observation_hash THEN
        RAISE EXCEPTION 'source payload integrity mismatch';
    END IF;
    SELECT x INTO STRICT item FROM jsonb_array_elements(payload) x WHERE x->>'transaction_id'='943752';
    IF NOT item @> '{"transaction_id": 943752,"player_mlb_id": 702566,"from_team_id": 144,
            "transaction_date":"2026-09-23","effective_date":"2026-09-23",
            "transaction_type_code":"OPT","source_endpoint":"/transactions"}'::jsonb THEN
        RAISE EXCEPTION 'transaction identity differs';
    END IF;
    RETURN item;
END $$;
"""

APPROVE = """
CREATE FUNCTION transaction_history_repair.approve_murphy(observation_id integer) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    scope jsonb := transaction_history_repair.murphy_scope(observation_id);
    request_id integer;
BEGIN
    PERFORM transaction_history_repair.require_certified_schema();
    IF transaction_history_repair.source_event(observation_id)->'to_team_id' IS DISTINCT FROM '464'::jsonb THEN
        RAISE EXCEPTION 'destination lacks source evidence';
    END IF;
    INSERT INTO public.repair_requests
        (request_key,request_fingerprint,schema_version,plan_version,mode,status,requested_scope_type,
         scope_json,baseball_date_start,baseball_date_end,source_domain,reason,requested_by,trigger_type,
         dry_run,requested_method_versions_json,correlation_id,plan_json,estimated_counts_json,outcome_json,
         created_at,started_at,updated_at)
    VALUES ('statsapi-943752-destination-v1',encode(sha256(convert_to(scope::text,'UTF8')),'hex'),
        'repair-request-v1','murphy-destination-v1','targeted_repair','running','transaction',scope,
        '2026-09-23','2026-09-23','transactions','Correct the destination of the September 23 option',
        session_user,'manual',false,'{}',gen_random_uuid()::text,'{}','{}','{}',now(),now(),now())
    RETURNING id INTO request_id;
    RETURN request_id;
END $$;
"""

APPLY = """
CREATE FUNCTION transaction_history_repair.apply_murphy(request_id integer) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp
SET baseballos.transaction_owner = '' AS $$
DECLARE
    req public.repair_requests%ROWTYPE;
    tx public.player_transactions%ROWTYPE;
    prior public.player_transaction_versions%ROWTYPE;
    evidence_id integer;
    old_event jsonb;
    new_event jsonb;
    facts jsonb;
    canonical text;
    successor integer;
    affected integer[];
    approved integer[] := ARRAY[1421545,1421789,1431943,1432187];
BEGIN
    PERFORM transaction_history_repair.require_certified_schema();
    SELECT * INTO STRICT req FROM public.repair_requests WHERE id=request_id FOR UPDATE;
    evidence_id := (req.scope_json->>'observation_id')::integer;
    IF evidence_id IS NULL OR req.scope_json::jsonb IS DISTINCT FROM transaction_history_repair.murphy_scope(evidence_id)
       OR req.request_key <> 'statsapi-943752-destination-v1' OR req.status <> 'running'
       OR req.schema_version <> 'repair-request-v1' OR req.trigger_type <> 'manual'
       OR req.plan_version <> 'murphy-destination-v1' OR req.mode <> 'targeted_repair' OR req.dry_run
       OR req.baseball_date_start <> '2026-09-23' OR req.baseball_date_end <> '2026-09-23'
       OR req.source_domain <> 'transactions' OR req.requested_scope_type <> 'transaction'
       OR req.request_fingerprint <> encode(sha256(convert_to(req.scope_json::jsonb::text,'UTF8')),'hex')
       THEN RAISE EXCEPTION 'request outside scope or settled'; END IF;
    PERFORM pg_advisory_xact_lock(509000000,hashtext('statsapi:943752'));
    SELECT * INTO STRICT tx FROM public.player_transactions WHERE transaction_key='statsapi:943752' FOR UPDATE;
    SELECT * INTO STRICT prior FROM public.player_transaction_versions WHERE id=644 AND
        player_transaction_id=tx.id AND version_number=1 AND fact_schema_version=1 AND
        predecessor_version_id IS NULL AND source_observation_id=14269;
    facts := prior.fact_json::jsonb;
    IF prior.fact_fingerprint <> 'ec2ecf9cff6998db35618de66c7dcb0214c3b824e1d8f448648a334208378e47'
       OR tx.current_version_number IS DISTINCT FROM 1 OR tx.source_observation_id IS DISTINCT FROM 14269
       OR NOT to_jsonb(tx) @> facts OR EXISTS (SELECT FROM public.player_transaction_versions
            WHERE player_transaction_id=tx.id AND version_number>1) THEN
        RAISE EXCEPTION 'version or projection changed';
    END IF;
    -- The option's roster alignment remains true via Atlanta for both destinations.
    IF (SELECT team_id FROM public.roster_status_snapshots WHERE pitcher_id=tx.pitcher_id
        AND snapshot_date='2026-09-23' ORDER BY updated_at DESC,id DESC LIMIT 1) IS DISTINCT FROM 144
       THEN RAISE EXCEPTION 'roster alignment changed'; END IF;
    -- Match the SP-05 citation invalidation contract. Stop if the reviewed
    -- current dependents have changed since approval of this recovery plan.
    SELECT array_agg(id ORDER BY id) INTO affected FROM (
        SELECT e.id FROM public.evidence_objects e WHERE e.recompute_status='current' AND EXISTS (
            SELECT FROM public.evidence_citations c WHERE c.source_table='player_transactions'
              AND c.source_pk=tx.id::text AND c.evidence_object_id=e.id)
        ORDER BY e.id LIMIT 5 FOR UPDATE) dependents;
    IF affected IS DISTINCT FROM approved OR EXISTS (
        SELECT FROM public.evidence_objects WHERE id=ANY(approved) AND
        (posture<>'internal_only' OR rule_id<>'team_option_recall_churn'
         OR subject_key IS DISTINCT FROM CASE id
             WHEN 1421545 THEN 'team:144:2026-10-05:window-14:team_option_recall_churn'
             WHEN 1421789 THEN 'team:431:2026-10-05:window-14:team_option_recall_churn'
             WHEN 1431943 THEN 'team:144:2026-10-06:window-14:team_option_recall_churn'
             WHEN 1432187 THEN 'team:431:2026-10-06:window-14:team_option_recall_churn' END
         OR product_date IS DISTINCT FROM CASE WHEN id IN (1421545,1421789)
             THEN date '2026-10-05' ELSE date '2026-10-06' END))
    THEN RAISE EXCEPTION 'dependent evidence outside reviewed scope'; END IF;
    old_event := transaction_history_repair.source_event(14269);
    new_event := transaction_history_repair.source_event(evidence_id);
    IF old_event->'to_team_id' IS DISTINCT FROM '431'::jsonb
       OR new_event IS DISTINCT FROM jsonb_set(old_event,'{to_team_id}','464') THEN
        RAISE EXCEPTION 'source change exceeds destination scope';
    END IF;
    -- The certified v1 has only scalar fields. Reproduce SP-05's sorted,
    -- compact JSON encoding and verify the original bytes before versioning.
    canonical := transaction_history_repair.canonical_record(facts);
    IF encode(sha256(convert_to(canonical,'UTF8')),'hex') IS DISTINCT FROM prior.fact_fingerprint THEN
        RAISE EXCEPTION 'predecessor fingerprint mismatch';
    END IF;
    canonical := transaction_history_repair.canonical_record(jsonb_set(facts,'{to_team_id}','464'));
    INSERT INTO public.player_transaction_versions(player_transaction_id,version_number,predecessor_version_id,
        source_observation_id,fact_schema_version,fact_json,fact_fingerprint,created_at)
    VALUES (tx.id,2,prior.id,evidence_id,1,canonical::json,encode(sha256(convert_to(canonical,'UTF8')),'hex'),now())
    RETURNING id INTO successor;
    PERFORM set_config('baseballos.transaction_owner',tx.transaction_key,true);
    UPDATE public.player_transactions SET to_team_id=464,current_version_number=2,source_observation_id=evidence_id,
        correction_count=correction_count+1,last_corrected_at=now(),correction_source=tx.source,
        sync_run_id=NULL,updated_at=now() WHERE id=tx.id RETURNING * INTO STRICT tx;
    IF tx.to_team_id IS DISTINCT FROM 464 OR tx.current_version_number IS DISTINCT FROM 2
       OR tx.source_observation_id IS DISTINCT FROM evidence_id THEN RAISE EXCEPTION 'write suppressed'; END IF;
    UPDATE public.evidence_objects SET recompute_status='recompute_needed',
        recompute_reason_codes=CASE WHEN coalesce(recompute_reason_codes::jsonb,'[]'::jsonb)
            @> '["roster_depth_source_corrected"]'::jsonb THEN recompute_reason_codes
            ELSE (coalesce(recompute_reason_codes::jsonb,'[]'::jsonb)
                  || '["roster_depth_source_corrected"]'::jsonb)::json END,
        invalidated_at=now(),invalidated_by_source_table='player_transactions',
        invalidated_by_source_pk=tx.id::text,last_corrected_at=now(),
        correction_count=correction_count+1,correction_source='upstream_source_correction',
        updated_at=now() WHERE id=ANY(affected);
    UPDATE public.repair_requests SET status='completed',completed_at=now(),updated_at=now(),
        outcome_json=json_build_object('predecessor',prior.id,'successor',successor,'observation_id',evidence_id,'invalidated_evidence',affected)
        WHERE id=request_id;
    RETURN successor;
END $$;
"""
