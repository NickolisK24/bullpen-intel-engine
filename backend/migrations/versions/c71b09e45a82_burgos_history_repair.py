"""Install the bounded Boston roster repair. Deployment grants no operator access."""

from alembic import op

revision = 'c71b09e45a82'
down_revision = 'a7c3e9f1d2b5'
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("CREATE SCHEMA roster_history_repair")
    op.execute("REVOKE ALL ON SCHEMA roster_history_repair FROM PUBLIC")
    op.execute(SCOPE)
    op.execute(APPROVE)
    op.execute(EVIDENCE)
    op.execute(APPLY)
    op.execute("REVOKE ALL ON ALL FUNCTIONS IN SCHEMA roster_history_repair FROM PUBLIC")
    # Global ALTER DEFAULT PRIVILEGES may give named API roles EXECUTE even
    # in a new schema. Explicit operator grants must be the only admission.
    op.execute("""
        DO $$
        DECLARE granted_role name;
        BEGIN
            FOR granted_role IN
                SELECT DISTINCT r.rolname FROM pg_catalog.pg_proc p
                CROSS JOIN LATERAL pg_catalog.aclexplode(p.proacl) a
                JOIN pg_catalog.pg_roles r ON r.oid=a.grantee
                WHERE p.pronamespace='roster_history_repair'::regnamespace AND r.oid<>p.proowner
                UNION
                SELECT r.rolname FROM pg_catalog.pg_namespace n
                CROSS JOIN LATERAL pg_catalog.aclexplode(n.nspacl) a
                JOIN pg_catalog.pg_roles r ON r.oid=a.grantee
                WHERE n.nspname='roster_history_repair' AND r.oid<>n.nspowner
            LOOP
                EXECUTE format('REVOKE ALL ON SCHEMA roster_history_repair FROM %I', granted_role);
                EXECUTE format('REVOKE ALL ON ALL FUNCTIONS IN SCHEMA roster_history_repair FROM %I',
                               granted_role);
            END LOOP;
        END $$
    """)


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        for signature in (
            "apply_burgos(integer)",
            "membership_observation(date,text,boolean)",
            "approve_burgos()",
            "burgos_scope()",
        ):
            op.execute(f"DROP FUNCTION roster_history_repair.{signature}")
        op.execute("DROP SCHEMA roster_history_repair")


SCOPE = """
CREATE FUNCTION roster_history_repair.burgos_scope() RETURNS jsonb
LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $$
    SELECT '{"team_ids":[111],"player_mlb_id": 670103,"membership_type":"active_roster",
             "interval_id": 129,"exclusive_end":"2026-09-26",
             "later_stints":[{"start":"2026-09-28","end":"2026-09-29"},
                            {"start":"2026-10-01","preserve_end": true}]}'::jsonb
$$
"""

# The database administrator can grant schema USAGE and just approve_burgos()
# or apply_burgos(integer) to separate operators. Neither needs table grants.
APPROVE = """
CREATE FUNCTION roster_history_repair.approve_burgos() RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    request_id integer;
    scope jsonb := roster_history_repair.burgos_scope();
BEGIN
    IF (SELECT array_agg(version_num::text) FROM
        (SELECT version_num FROM public.alembic_version FOR SHARE) certified)
        IS DISTINCT FROM ARRAY['c71b09e45a82'] THEN
        RAISE EXCEPTION 'uncertified roster correction schema';
    END IF;
    INSERT INTO public.repair_requests
        (request_key,request_fingerprint,schema_version,plan_version,mode,status,
         requested_scope_type,scope_json,baseball_date_start,baseball_date_end,source_domain,
         reason,requested_by,trigger_type,dry_run,requested_method_versions_json,correlation_id,
         plan_json,estimated_counts_json,outcome_json,created_at,started_at,updated_at)
    VALUES ('boston-129-20260926-v1', encode(sha256(convert_to(scope::text,'UTF8')),'hex'),
            'repair-request-v1','burgos-split-v1','targeted_repair','running','player',
            scope,'2026-09-26','2026-10-01','roster','Restore the September Boston active stint',
            session_user,'manual',false,'{}',gen_random_uuid()::text,'{}','{}','{}',now(),now(),now())
    RETURNING id INTO request_id;
    RETURN request_id;
END $$;
"""

# Use SP-05's request identity and retained collection; the represented date
# belongs to the old club's endpoint, independent of observation/ingestion time.
EVIDENCE = """
CREATE FUNCTION roster_history_repair.membership_observation(day date, roster_type text, expected boolean)
RETURNS integer LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    evidence record;
    records jsonb;
    matches integer;
BEGIN
    SELECT o.id,o.record_count,o.completeness,o.is_authoritative,o.outcome,
           a.payload_json::jsonb AS payload,s.request_parameters::jsonb AS parameters,
           s.request_schema_version,o.payload_schema_version,a.payload_kind
    INTO STRICT evidence
    FROM public.source_subjects s JOIN public.source_observations o ON o.source_subject_id=s.id
    LEFT JOIN public.source_payload_artifacts a ON a.id=o.payload_artifact_id
    WHERE s.provider='mlb_stats_api' AND s.source_domain='roster'
      AND s.subject_key='111:'||roster_type AND s.baseball_date=day
      AND s.endpoint='/teams/111/roster' AND s.subject_type='team';
    -- Multiple competing versions require separate review, including a partial
    -- or withdrawn version. Never choose a convenient older observation.
    records := evidence.payload->'records';
    IF evidence.parameters IS DISTINCT FROM jsonb_build_object(
          'teamId',111,'rosterType',roster_type,'date',to_char(day,'YYYY-MM-DD'))
       OR evidence.request_schema_version <> 1 OR evidence.payload_schema_version <> 1
       OR evidence.payload_kind IS DISTINCT FROM 'normalized_json'
       OR evidence.completeness <> 'complete' OR evidence.is_authoritative IS NOT TRUE
       OR evidence.outcome NOT IN ('new','changed','corrected','empty_valid')
       OR jsonb_typeof(records) IS DISTINCT FROM 'array'
       OR jsonb_array_length(records) IS DISTINCT FROM evidence.record_count
       OR evidence.payload #> '{completeness_proof,authoritative_for_mlb_membership}' IS DISTINCT FROM 'true'::jsonb
       OR evidence.payload #> '{completeness_proof,authoritative_for_absence}' IS DISTINCT FROM 'true'::jsonb
       OR EXISTS (SELECT FROM jsonb_array_elements(records) r
                  WHERE (r#>>'{person,id}') IS NULL OR (r#>>'{person,id}') !~ '^[1-9][0-9]*$'
                     OR (r ? 'parentTeamId' AND r->>'parentTeamId' IS DISTINCT FROM '111'))
    THEN RAISE EXCEPTION 'invalid old-club roster evidence for %',day; END IF;
    SELECT count(*) INTO matches FROM jsonb_array_elements(records) r
    WHERE r#>>'{person,id}'='670103';
    IF matches <> expected::integer OR (expected AND NOT EXISTS (
        SELECT FROM jsonb_array_elements(records) r WHERE r#>>'{person,id}'='670103'
           AND (r#>>'{position,abbreviation}' IN ('P','TWP')
                OR lower(r#>>'{position,type}') IN ('pitcher','two-way player'))))
    THEN RAISE EXCEPTION 'conflicting Boston membership for %',day; END IF;
    IF EXISTS (
        SELECT FROM public.roster_status_snapshots snap
        WHERE snap.mlb_id=670103 AND snap.snapshot_date=day AND (
          (snap.team_id=111 AND
           (CASE roster_type WHEN 'active' THEN snap.active_roster ELSE snap.forty_man_roster END) <> expected)
          OR (expected AND snap.team_id<>111 AND
           (CASE roster_type WHEN 'active' THEN snap.active_roster ELSE snap.forty_man_roster END))))
    THEN RAISE EXCEPTION 'retained roster snapshot conflicts on %',day; END IF;
    RETURN evidence.id;
END $$;
"""

APPLY = """
CREATE FUNCTION roster_history_repair.apply_burgos(request_id integer) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    req public.repair_requests%ROWTYPE;
    original public.roster_membership_intervals%ROWTYPE;
    later public.roster_membership_intervals%ROWTYPE;
    closed_id integer;
    opening integer;
    exclusion integer;
    stint record;
    recall_obs integer;
    recall_end_obs integer;
    october_obs integer;
    stints integer[] := '{}';
    option_tx integer;
    recall_tx integer;
    day date;
BEGIN
    IF (SELECT array_agg(version_num::text) FROM
        (SELECT version_num FROM public.alembic_version FOR SHARE) certified)
        IS DISTINCT FROM ARRAY['c71b09e45a82'] THEN
        RAISE EXCEPTION 'uncertified roster correction schema';
    END IF;
    IF current_setting('transaction_isolation') <> 'serializable' THEN
        RAISE EXCEPTION 'serializable repair transaction required';
    END IF;
    PERFORM pg_advisory_xact_lock(505000111);
    SELECT * INTO STRICT req FROM public.repair_requests WHERE id=request_id FOR UPDATE;
    IF req.scope_json::jsonb IS DISTINCT FROM roster_history_repair.burgos_scope()
       OR req.request_key <> 'boston-129-20260926-v1' OR req.plan_version <> 'burgos-split-v1'
       OR req.mode <> 'targeted_repair' OR req.source_domain <> 'roster' OR req.dry_run
       OR req.status <> 'running' OR req.baseball_date_start <> '2026-09-26'
       OR req.baseball_date_end <> '2026-10-01' THEN
        RAISE EXCEPTION 'request is outside approved scope or already settled';
    END IF;
    SELECT * INTO STRICT original FROM public.roster_membership_intervals WHERE id=129 FOR UPDATE;
    IF original.player_mlb_id <> 670103 OR original.team_id <> 111 OR original.membership_type <> 'active_roster'
       OR original.effective_start_date <> '2026-09-10' OR original.effective_end_date IS NOT NULL
       OR NOT original.is_current_version OR original.is_void OR original.authority_type <> 'official_mlb_roster_v1'
       OR original.organization_id IS DISTINCT FROM 111 OR original.start_precision <> 'date' OR original.effective_start_at IS NOT NULL
       OR original.effective_end_at IS NOT NULL OR original.closed_by_observation_id IS NOT NULL
       OR original.closed_by_transaction_id IS NOT NULL
       OR NOT EXISTS (SELECT FROM public.pitchers WHERE id=original.pitcher_id AND mlb_id=670103)
       OR NOT EXISTS (SELECT FROM public.roster_membership_intervals WHERE id=149
           AND pitcher_id=original.pitcher_id AND player_mlb_id=670103 AND team_id=111
           AND membership_type='forty_man_roster' AND effective_start_date='2026-09-10'
           AND effective_end_date IS NULL AND is_current_version AND NOT is_void)
    THEN RAISE EXCEPTION 'original membership history changed'; END IF;
    PERFORM roster_history_repair.membership_observation('2026-09-25','40Man',true);
    PERFORM roster_history_repair.membership_observation('2026-09-26','40Man',true);
    SELECT id INTO STRICT option_tx FROM public.player_transactions WHERE player_mlb_id=670103
        AND transaction_id='943956' AND transaction_type_code='OPT' AND effective_date='2026-09-25'
        AND from_team_id=111 AND to_team_id=533 AND pitcher_id=original.pitcher_id
        AND source='mlb_stats_api:transactions' AND source_endpoint='/transactions';
    SELECT id INTO STRICT recall_tx FROM public.player_transactions WHERE player_mlb_id=670103
        AND transaction_id='944806' AND transaction_type_code='CU' AND effective_date='2026-09-28'
        AND from_team_id=533 AND to_team_id=111 AND pitcher_id=original.pitcher_id
        AND source='mlb_stats_api:transactions' AND source_endpoint='/transactions';
    IF EXISTS (
        SELECT FROM public.player_transactions t LEFT JOIN LATERAL (
            SELECT version_number,fact_json::jsonb AS facts FROM public.player_transaction_versions
            WHERE player_transaction_id=t.id ORDER BY version_number DESC LIMIT 1
        ) v ON true WHERE t.id IN (option_tx,recall_tx) AND (
            t.current_version_number IS DISTINCT FROM coalesce(v.version_number,0)
            OR (v.version_number IS NOT NULL AND NOT v.facts @> jsonb_build_object(
                'effective_date',t.effective_date,'transaction_type_code',t.transaction_type_code,
                'player_mlb_id',t.player_mlb_id,'from_team_id',t.from_team_id,'to_team_id',t.to_team_id))))
    THEN RAISE EXCEPTION 'transaction version conflicts with roster evidence'; END IF;
    opening := roster_history_repair.membership_observation(original.effective_start_date,'active',true);
    IF opening <> original.opened_by_observation_id THEN RAISE EXCEPTION 'opening lineage changed'; END IF;
    FOR day IN SELECT DISTINCT baseball_date FROM public.source_subjects
        WHERE provider='mlb_stats_api' AND source_domain='roster' AND subject_key='111:active'
          AND baseball_date > original.effective_start_date AND baseball_date < '2026-09-25'
    LOOP
        PERFORM roster_history_repair.membership_observation(day,'active',true);
    END LOOP;
    PERFORM roster_history_repair.membership_observation('2026-09-25','active',true);
    exclusion := roster_history_repair.membership_observation('2026-09-26','active',false);
    PERFORM roster_history_repair.membership_observation('2026-09-27','active',false);
    recall_obs := roster_history_repair.membership_observation('2026-09-28','active',true);
    recall_end_obs := roster_history_repair.membership_observation('2026-09-29','active',false);
    PERFORM roster_history_repair.membership_observation('2026-09-30','active',false);
    october_obs := roster_history_repair.membership_observation('2026-10-01','active',true);

    IF EXISTS (SELECT FROM public.roster_membership_intervals WHERE pitcher_id=original.pitcher_id
        AND membership_type='active_roster' AND is_current_version AND NOT is_void AND id<>129
        AND effective_start_date<'2026-09-28'
        AND (effective_end_date IS NULL OR effective_end_date > original.effective_start_date))
    THEN RAISE EXCEPTION 'overlapping active membership'; END IF;

    UPDATE public.roster_membership_intervals SET is_current_version=false,updated_at=now() WHERE id=original.id;
    INSERT INTO public.roster_membership_intervals
        (pitcher_id,player_mlb_id,team_id,organization_id,membership_type,effective_start_date,
         effective_end_date,start_precision,end_precision,authority_type,opened_by_observation_id,
         closed_by_observation_id,opened_by_transaction_id,closed_by_transaction_id,
         supersedes_interval_id,correction_reason,created_at,updated_at)
    VALUES (original.pitcher_id,670103,111,original.organization_id,'active_roster',original.effective_start_date,
            '2026-09-26',original.start_precision,'date',original.authority_type,opening,exclusion,
            original.opened_by_transaction_id,option_tx,original.id,'SP-13 request '||req.id,now(),now())
    RETURNING id INTO closed_id;
    -- Two distinct positive runs in the reviewed Boston evidence window.
    -- The recall transaction explains the first return only. The October
    -- opening is established independently by that day's club roster.
    FOR stint IN SELECT * FROM (VALUES
        (date '2026-09-28',date '2026-09-29',recall_obs,recall_end_obs,recall_tx),
        (date '2026-10-01',NULL,october_obs,NULL,NULL)
    ) AS slices(first_day,end_day,opening_obs,closing_obs,transaction_id)
    LOOP
        SELECT * INTO later FROM public.roster_membership_intervals
        WHERE pitcher_id=original.pitcher_id AND membership_type='active_roster'
          AND effective_start_date=stint.first_day AND is_current_version AND NOT is_void
        ORDER BY id LIMIT 1 FOR UPDATE;
        IF FOUND THEN
            IF later.team_id<>111 OR later.player_mlb_id<>670103 OR later.opened_by_observation_id<>stint.opening_obs
               OR later.effective_end_date<=stint.first_day
               OR (stint.end_day IS NOT NULL AND (later.effective_end_date IS DISTINCT FROM stint.end_day
                   OR later.closed_by_observation_id IS DISTINCT FROM stint.closing_obs))
            THEN RAISE EXCEPTION 'later membership needs independent review'; END IF;
        ELSE
            INSERT INTO public.roster_membership_intervals
                (pitcher_id,player_mlb_id,team_id,organization_id,membership_type,effective_start_date,
                 effective_end_date,end_precision,authority_type,opened_by_observation_id,closed_by_observation_id,
                 opened_by_transaction_id,supersedes_interval_id,correction_reason,created_at,updated_at)
            VALUES (original.pitcher_id,670103,111,original.organization_id,'active_roster',stint.first_day,
                    stint.end_day,CASE WHEN stint.end_day IS NOT NULL THEN 'date' END,original.authority_type,
                    stint.opening_obs,stint.closing_obs,stint.transaction_id,original.id,
                    'SP-13 request '||req.id,now(),now())
            RETURNING * INTO later;
            INSERT INTO public.roster_membership_mutations
                (interval_id,pitcher_id,player_mlb_id,team_id,membership_type,mutation_type,baseball_date,
                 source_observation_id,player_transaction_id,created_at)
            SELECT later.id,original.pitcher_id,670103,111,'active_roster',m.kind,m.day,m.obs,m.tx,now()
            FROM (VALUES ('membership_opened',stint.first_day,stint.opening_obs,stint.transaction_id),
                         ('membership_closed',stint.end_day,stint.closing_obs,NULL)) AS m(kind,day,obs,tx)
            WHERE m.day IS NOT NULL;
        END IF;
        IF stint.end_day IS NULL THEN
            -- Preserve a proven later end verbatim. Refuse an open suffix
            -- across a subsequent removal; deciding that boundary is outside
            -- this repair, including when the primary snapshot names a new club.
            FOR day IN SELECT DISTINCT baseball_date FROM public.source_subjects
                WHERE provider='mlb_stats_api' AND source_domain='roster' AND subject_key='111:active'
                  AND baseball_date>stint.first_day
                  AND (later.effective_end_date IS NULL OR baseball_date<later.effective_end_date)
            LOOP
                PERFORM roster_history_repair.membership_observation(day,'active',true);
            END LOOP;
            IF EXISTS (SELECT FROM public.roster_status_snapshots WHERE pitcher_id=original.pitcher_id
                AND snapshot_date>stint.first_day
                AND (later.effective_end_date IS NULL OR snapshot_date<later.effective_end_date)
                AND ((team_id=111 AND active_roster=false) OR (team_id<>111 AND active_roster=true)))
            THEN RAISE EXCEPTION 'later roster departure needs independent review'; END IF;
        END IF;
        IF EXISTS (SELECT FROM public.roster_membership_intervals WHERE pitcher_id=original.pitcher_id
            AND membership_type='active_roster' AND is_current_version AND NOT is_void AND id<>later.id
            AND daterange(effective_start_date,effective_end_date,'[)') &&
                daterange(later.effective_start_date,later.effective_end_date,'[)'))
        THEN RAISE EXCEPTION 'overlapping later stints'; END IF;
        stints := array_append(stints,later.id);
    END LOOP;
    IF EXISTS (SELECT FROM public.roster_membership_intervals WHERE pitcher_id=original.pitcher_id
        AND membership_type='active_roster' AND is_current_version AND NOT is_void AND
        daterange(effective_start_date,effective_end_date,'[)') && daterange('2026-09-29','2026-10-01','[)'))
    THEN RAISE EXCEPTION 'unexpected membership in the later absence window'; END IF;
    INSERT INTO public.roster_membership_mutations
        (interval_id,pitcher_id,player_mlb_id,team_id,membership_type,mutation_type,baseball_date,
         source_observation_id,player_transaction_id,created_at)
    VALUES (closed_id,original.pitcher_id,670103,111,'active_roster','membership_corrected',
            '2026-09-26',exclusion,option_tx,now());
    UPDATE public.repair_requests SET status='completed',completed_at=now(),updated_at=now(),
        outcome_json=json_build_object('original',original.id,'closed',closed_id,'later_stints',stints)
        WHERE id=req.id;
    RETURN closed_id;
END $$;
"""
